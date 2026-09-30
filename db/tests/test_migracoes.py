# -*- coding: utf-8 -*-
"""
Testes das migrações do Postgres da v3 contra um postgres:16-alpine efêmero.

POR QUE UM CONTAINER E NÃO O PG17 NATIVO DA MÁQUINA
  As migrações criam papéis (cluster-wide) e um ENUM; testar no PG17 do host
  deixaria resíduo entre execuções e a suíte deixaria de ser reprodutível.
  O container nasce vazio, a porta é sorteada pelo Docker (`-p 127.0.0.1:0:5432`)
  para não brigar com a 5432 nativa nem com a 5433 do compose, e é derrubado
  no fim da sessão de teste.

O QUE SE TESTA
  Comportamento real do banco: a máquina de estados (fn_transicao), a fila de
  extração (fn_tomar_vaga_extracao), a classificação do monitor
  (fn_classificar_vista), o trigger que impede execução simulada de virar
  verificação vigente de licitação real (T15), o papel n8n_rw sem UPDATE nas
  tabelas de procedência e os invariantes SQL da seção 3 do plano. Nada é
  mockado: se o SQL estiver errado, o teste quebra.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg
import pytest
from psycopg import errors

DB = Path(__file__).resolve().parents[1]
RAIZ = DB.parent
MIGRAR = DB / "migrar.py"
INVARIANTES = DB / "invariantes.sql"

SENHA_ADMIN = "fopa-teste"
SENHA_N8N = "n8n-teste"
SENHA_WORKER = "worker-teste"
SENHA_API = "api-teste"
SENHA_API_RW = "api-rw-teste"

# Controles válidos pela regra `^\d{14}-\d+-\d+/\d{4}$` (pncp.py:270).
CTRL = "12345678000199-1-000%03d/2026"


def _controle(n: int) -> str:
    return CTRL % n


def _docker(*args: str, check: bool = True) -> str:
    r = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("docker %s falhou: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


@pytest.fixture(scope="session")
def pg_url():
    """Sobe o Postgres efêmero, espera aceitar conexão, devolve a URL, derruba."""
    cid = _docker(
        "run", "-d", "--rm",
        "-e", "POSTGRES_PASSWORD=" + SENHA_ADMIN,
        "-e", "POSTGRES_DB=fopa",
        "-p", "127.0.0.1:0:5432",
        "postgres:16-alpine",
    )
    try:
        porta = _docker("port", cid, "5432/tcp").splitlines()[0].rsplit(":", 1)[1]
        url = "postgresql://postgres:%s@127.0.0.1:%s/fopa" % (SENHA_ADMIN, porta)
        # `pg_isready` dentro do container responde antes do restart que o
        # entrypoint faz após o init; por isso, além dele, exigimos uma conexão
        # TCP real pelo host antes de liberar a URL.
        limite = time.time() + 90
        pronto = False
        while time.time() < limite:
            ok = subprocess.run(
                ["docker", "exec", cid, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                capture_output=True).returncode == 0
            if ok:
                try:
                    with psycopg.connect(url, connect_timeout=3) as c:
                        c.execute("SELECT 1")
                    pronto = True
                    break
                except psycopg.OperationalError:
                    pass
            time.sleep(1)
        if not pronto:
            raise RuntimeError("Postgres efêmero não ficou pronto em 90 s:\n"
                               + _docker("logs", cid, check=False))
        yield url
    finally:
        # `-v`: sem ele o volume anônimo do Postgres (dados do teste) fica órfão a cada rodada (28/09).
        _docker("rm", "-f", "-v", cid, check=False)


def _rodar_migrar(url: str) -> str:
    env = dict(os.environ, DATABASE_URL=url,
               N8N_RW_PASSWORD=SENHA_N8N, WORKER_RW_PASSWORD=SENHA_WORKER,
               API_RO_PASSWORD=SENHA_API, API_RW_PASSWORD=SENHA_API_RW,
               PYTHONIOENCODING="utf-8")
    env.pop("ANTHROPIC_API_KEY", None)
    r = subprocess.run([sys.executable, str(MIGRAR)], env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, "migrar.py falhou:\n%s\n%s" % (r.stdout, r.stderr)
    return r.stdout


@pytest.fixture(scope="session")
def banco(pg_url):
    """Aplica as migrações duas vezes: a segunda tem de ser um no-op."""
    saida1 = _rodar_migrar(pg_url)
    saida2 = _rodar_migrar(pg_url)
    assert "aplicadas=0" in saida2.strip().splitlines()[-1], saida2
    return dict(url=pg_url, saida1=saida1, saida2=saida2)


@pytest.fixture
def conn(banco):
    """Conexão de superusuário com rollback no fim: cada teste começa limpo."""
    with psycopg.connect(banco["url"]) as c:
        yield c
        c.rollback()


def _licitacao(conn, n: int, estado: str = "nova", **campos) -> str:
    ctrl = _controle(n)
    base = dict(controle=ctrl, escopo_dentro=True, estado=estado,
                orgao="Prefeitura de Teste", uf="SP", municipio="Teste",
                modalidade="Pregão Eletrônico", objeto="cessão da folha",
                publicado_em="2026-09-01")   # dentro do recorte de 2026 (018)
    base.update(campos)
    cols = ", ".join(base)
    vals = ", ".join("%%(%s)s" % k for k in base)
    conn.execute("INSERT INTO licitacoes (%s) VALUES (%s)" % (cols, vals), base)
    return ctrl


def _execucao(conn, ctrl: str, origem: str = "api", canonica: bool = True) -> int:
    row = conn.execute(
        "INSERT INTO execucoes_modelo (controle, origem, provedor, modelo, status, canonica)"
        " VALUES (%s, %s, %s, %s, 'ok', %s) RETURNING id",
        (ctrl, origem, "claude" if origem == "api" else origem, "claude-opus-5", canonica),
    ).fetchone()
    return row[0]


def _verificacao(conn, ctrl: str, exec_id: int, vigente: bool = False,
                 versao: str = "v1") -> int:
    return conn.execute(
        "INSERT INTO verificacoes (execucao_id, controle, versao_regras, vigente)"
        " VALUES (%s, %s, %s, %s) RETURNING id", (exec_id, ctrl, versao, vigente)
    ).fetchone()[0]


# ------------------------------------------------------------------ migrações

def test_migrar_registra_e_pula(banco, conn):
    assert "aplicadas=0" not in banco["saida1"].strip().splitlines()[-1]
    nomes = [r[0] for r in conn.execute(
        "SELECT nome FROM schema_migracoes ORDER BY nome")]
    esperados = sorted(p.name for p in DB.glob("[0-9][0-9][0-9]_*.sql"))
    assert nomes == esperados
    assert len(nomes) >= 10


def test_migrar_aborta_se_sha_mudou(banco, pg_url):
    # Simula um arquivo já aplicado que foi editado depois: o sha gravado
    # diverge do sha do disco e o migrador tem de recusar, não reaplicar.
    with psycopg.connect(pg_url, autocommit=True) as c:
        nome = c.execute("SELECT min(nome) FROM schema_migracoes").fetchone()[0]
        c.execute("UPDATE schema_migracoes SET sha256 = repeat('0', 64) WHERE nome = %s",
                  (nome,))
        try:
            env = dict(os.environ, DATABASE_URL=pg_url, PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, str(MIGRAR)], env=env,
                               capture_output=True, text=True, encoding="utf-8")
            assert r.returncode != 0
            assert "sha" in (r.stdout + r.stderr).lower()
        finally:
            # Restaura o sha real para os demais testes.
            # Mesmo cálculo do migrar.py (CRLF normalizado): num checkout Windows
            # o arquivo tem CRLF e o sha cru não seria o que o migrador grava.
            sha = hashlib.sha256((DB / nome).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            c.execute("UPDATE schema_migracoes SET sha256 = %s WHERE nome = %s", (sha, nome))


def test_seed_perguntas_bate_com_o_modulo(conn):
    sys.path.insert(0, str(RAIZ / "scripts"))
    from fopa import questionario  # noqa: E402
    rows = {r[0]: r for r in conn.execute(
        "SELECT id, texto, critico, formato FROM perguntas")}
    assert len(rows) == 17
    for p in questionario.PERGUNTAS:
        assert p.id in rows, p.id
        assert rows[p.id][1] == p.texto
        assert rows[p.id][2] == p.critico
        # O módulo usa '' para "sem formato"; no banco isso é NULL.
        assert (rows[p.id][3] or "") == p.formato


def test_seed_termos_orcamento_usuario(conn):
    termos = [r[0] for r in conn.execute(
        "SELECT termo FROM termos WHERE ativo ORDER BY prioridade")]
    assert len(termos) == 6
    assert termos[0] == "cessão onerosa folha de pagamento"
    teto, auto = conn.execute(
        "SELECT teto_brl_dia, auto_processar FROM orcamento WHERE vigente").fetchone()
    assert teto is None and auto is True
    papel = conn.execute(
        "SELECT papel FROM usuarios WHERE email = 'admin@exemplo.com'"
    ).fetchone()[0]
    assert papel == "admin"


# ------------------------------------------------------------- fn_transicao

def test_transicao_invalida_levanta_erro(conn):
    ctrl = _licitacao(conn, 1)
    with pytest.raises(errors.RaiseException):
        conn.execute("SELECT fn_transicao(%s, 'publicada', 'pulo', NULL)", (ctrl,))


def test_nova_para_baixando_grava_evento(conn):
    ctrl = _licitacao(conn, 2)
    conn.execute("SELECT fn_transicao(%s, 'baixando', 'W21', %s)",
                 (ctrl, '{"n8n_execution_id": "77"}'))
    estado, motivo = conn.execute(
        "SELECT estado, estado_motivo FROM licitacoes WHERE controle = %s", (ctrl,)
    ).fetchone()
    assert (estado, motivo) == ("baixando", "W21")
    ev = conn.execute(
        "SELECT de, para, motivo, n8n_execution_id FROM licitacao_eventos "
        "WHERE controle = %s ORDER BY id DESC LIMIT 1", (ctrl,)).fetchone()
    assert ev == ("nova", "baixando", "W21", "77")


def test_publicada_para_publicada_e_noop(conn):
    ctrl = _licitacao(conn, 3, estado="publicada")
    conn.execute("SELECT fn_transicao(%s, 'publicada', 'ramo de erro', NULL)", (ctrl,))
    n = conn.execute("SELECT count(*) FROM licitacao_eventos WHERE controle = %s",
                     (ctrl,)).fetchone()[0]
    assert n == 0


def test_erro_volta_ao_estado_anterior(conn):
    ctrl = _licitacao(conn, 4, estado="lendo")
    conn.execute("SELECT fn_transicao(%s, 'erro_leitura', 'ocr caiu', NULL)", (ctrl,))
    conn.execute("SELECT fn_transicao(%s, 'lendo', 'retentativa', NULL)", (ctrl,))
    assert conn.execute("SELECT estado FROM licitacoes WHERE controle = %s",
                        (ctrl,)).fetchone()[0] == "lendo"
    # erro_extracao volta para extraindo, nunca para lendo.
    ctrl2 = _licitacao(conn, 5, estado="erro_extracao")
    with pytest.raises(errors.RaiseException):
        conn.execute("SELECT fn_transicao(%s, 'lendo', NULL, NULL)", (ctrl2,))


def test_operador_baixa_de_novo_a_que_ja_tinha_pdf(conn):
    # 042 (ADR-017): com o fluxo de exceção, o anexo que o download recusou pelo formato agora vira PDF. A licitação
    # que tinha outro PDF (baixada_ok, preparada) volta ao download sem passar por `retificada` — que a marcaria como
    # retificada no PNCP sem ela ter mudado.
    for n, estado in ((210, "baixada_ok"), (211, "preparada")):
        ctrl = _licitacao(conn, n, estado=estado)
        conn.execute("SELECT fn_transicao(%s, 'nova', 'operador: baixar de novo', NULL)", (ctrl,))
        assert conn.execute("SELECT estado FROM licitacoes WHERE controle = %s", (ctrl,)).fetchone()[0] == "nova"
        assert conn.execute("SELECT de, para FROM licitacao_eventos WHERE controle = %s ORDER BY id DESC LIMIT 1",
                            (ctrl,)).fetchone() == (estado, "nova")


def test_arquivo_marca_ocr_forcado_e_giro(conn):
    # 043 (Pacote B): a marcação é do arquivo e fica gravada; o giro só aceita os quatro ângulos retos.
    ctrl = _licitacao(conn, 212)
    aid = conn.execute("INSERT INTO arquivos (controle, nome, status) VALUES (%s, 'a.pdf', 'ok') RETURNING id",
                       (ctrl,)).fetchone()[0]
    assert conn.execute("SELECT forcar_ocr, girar FROM arquivos WHERE id = %s", (aid,)).fetchone() == (False, 0)
    conn.execute("UPDATE arquivos SET forcar_ocr = true, girar = 180 WHERE id = %s", (aid,))
    assert conn.execute("SELECT forcar_ocr, girar FROM arquivos WHERE id = %s", (aid,)).fetchone() == (True, 180)
    with pytest.raises(errors.CheckViolation):
        with conn.transaction():
            conn.execute("UPDATE arquivos SET girar = 45 WHERE id = %s", (aid,))


def test_evento_direto_fora_da_tabela_e_bloqueado(conn):
    ctrl = _licitacao(conn, 6)
    with pytest.raises(errors.RaiseException):
        conn.execute("INSERT INTO licitacao_eventos (controle, de, para) "
                     "VALUES (%s, 'nova', 'publicada')", (ctrl,))


# ---------------------------------------------------- fn_tomar_vaga_extracao

def test_vaga_recusa_a_quinta_e_aceita_apos_liberar(conn):
    ocupadas = [_licitacao(conn, 10 + i, estado="extraindo") for i in range(4)]
    ctrl = _licitacao(conn, 20, estado="preparada")
    ok, motivo = conn.execute(
        "SELECT ok, motivo FROM fn_tomar_vaga_extracao(%s, 4, NULL)", (ctrl,)).fetchone()
    assert (ok, motivo) == (False, "sem_vaga")
    assert conn.execute("SELECT estado FROM licitacoes WHERE controle = %s",
                        (ctrl,)).fetchone()[0] == "preparada"
    conn.execute("SELECT fn_transicao(%s, 'respondida', 'fim', NULL)", (ocupadas[0],))
    ok, motivo = conn.execute(
        "SELECT ok, motivo FROM fn_tomar_vaga_extracao(%s, 4, NULL)", (ctrl,)).fetchone()
    assert ok is True
    assert conn.execute("SELECT estado FROM licitacoes WHERE controle = %s",
                        (ctrl,)).fetchone()[0] == "extraindo"
    assert conn.execute("SELECT count(*) FROM licitacoes WHERE estado = 'extraindo'"
                        ).fetchone()[0] == 4


def test_vaga_respeita_teto(conn):
    _licitacao(conn, 30, estado="extraindo")
    ctrl = _licitacao(conn, 31, estado="preparada")
    ok, motivo = conn.execute(
        "SELECT ok, motivo FROM fn_tomar_vaga_extracao(%s, 4, 1)", (ctrl,)).fetchone()
    assert (ok, motivo) == (False, "sem_orcamento")   # 0 + 1 x 6,56 > 1
    ok, _ = conn.execute(
        "SELECT ok, motivo FROM fn_tomar_vaga_extracao(%s, 4, 100)", (ctrl,)).fetchone()
    assert ok is True


def test_vaga_exige_estado_extraivel(conn):
    ctrl = _licitacao(conn, 32, estado="nova")
    ok, motivo = conn.execute(
        "SELECT ok, motivo FROM fn_tomar_vaga_extracao(%s, 4, NULL)", (ctrl,)).fetchone()
    assert ok is False and "estado" in motivo


# ------------------------------------------------------ fn_classificar_vista

def test_classificar_vista(conn):
    hoje = "2026-09-24"
    futuro = ('{"fim_prazo": "2026-10-10", "escopo_dentro": true, '
              '"atualizado_pncp": "2026-09-20T10:00:00"}')
    passado = ('{"fim_prazo": "2026-09-01", "escopo_dentro": true, '
               '"atualizado_pncp": "2026-09-20T10:00:00"}')
    q = "SELECT fn_classificar_vista(%s, %s::jsonb, %s::date)"
    assert conn.execute(q, (_controle(40), futuro, hoje)).fetchone()[0] == "nova"
    assert conn.execute(q, (_controle(41), passado, hoje)).fetchone()[0] == "encerrada"
    # Conhecida, publicada, com carimbo mais novo no PNCP: retificada.
    ctrl = _licitacao(conn, 42, estado="publicada",
                      atualizado_pncp="2026-09-10 08:00:00", fim_prazo="2026-10-10")
    assert conn.execute(q, (ctrl, futuro, hoje)).fetchone()[0] == "retificada"
    # Mesmo carimbo: só conhecida.
    conn.execute("UPDATE licitacoes SET atualizado_pncp = '2026-09-20 10:00:00' "
                 "WHERE controle = %s", (ctrl,))
    assert conn.execute(q, (ctrl, futuro, hoje)).fetchone()[0] == "conhecida"
    # Registro antigo sem carimbo: guarda o carimbo e não reprocessa (20_monitor.py:148-153).
    ctrl2 = _licitacao(conn, 43, estado="publicada", atualizado_pncp=None)
    assert conn.execute(q, (ctrl2, futuro, hoje)).fetchone()[0] == "conhecida"
    assert conn.execute("SELECT atualizado_pncp FROM licitacoes WHERE controle = %s",
                        (ctrl2,)).fetchone()[0] is not None


# --------------------------------------------------------- vigente x ensaio

def test_trigger_vigente_bloqueia_simulado_sem_ensaio(conn):
    ctrl = _licitacao(conn, 50, estado="verificada")
    ex = _execucao(conn, ctrl, origem="simulado", canonica=False)
    with pytest.raises(errors.RaiseException):
        with conn.transaction():
            _verificacao(conn, ctrl, ex, vigente=True)
    conn.execute("UPDATE licitacoes SET ensaio = true WHERE controle = %s", (ctrl,))
    vid = _verificacao(conn, ctrl, ex, vigente=True)
    assert conn.execute("SELECT vigente FROM verificacoes WHERE id = %s",
                        (vid,)).fetchone()[0] is True


def test_check_simulado_nunca_canonica(conn):
    ctrl = _licitacao(conn, 51)
    with pytest.raises(errors.CheckViolation):
        _execucao(conn, ctrl, origem="simulado", canonica=True)


def test_uma_vigente_por_controle(conn):
    ctrl = _licitacao(conn, 52, estado="verificada")
    ex = _execucao(conn, ctrl)
    _verificacao(conn, ctrl, ex, vigente=True, versao="a")
    with pytest.raises(errors.UniqueViolation):
        _verificacao(conn, ctrl, ex, vigente=True, versao="b")


# -------------------------------------------------------------------- papéis

def test_n8n_rw_nao_atualiza_respostas(banco):
    url = banco["url"].replace("postgres:" + SENHA_ADMIN, "n8n_rw:" + SENHA_N8N)
    with psycopg.connect(url) as c:
        c.execute("SELECT count(*) FROM respostas")          # ler pode
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("UPDATE respostas SET resposta = 'x'")
        c.rollback()
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("DELETE FROM chamadas_modelo")
        c.rollback()
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("UPDATE paginas SET texto = 'x'")
        c.rollback()


def test_api_ro_so_le(banco):
    url = banco["url"].replace("postgres:" + SENHA_ADMIN, "api_ro:" + SENHA_API)
    with psycopg.connect(url) as c:
        c.execute("SELECT * FROM v_card LIMIT 1")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("INSERT INTO termos (termo) VALUES ('x')")
        c.rollback()


# ------------------------------------------------------------------ views

def test_gasto_diario_soma_chamadas(conn):
    ctrl = _licitacao(conn, 60, estado="extraindo")
    ex = _execucao(conn, ctrl)
    conn.execute("INSERT INTO chamadas_modelo (execucao_id, brl, preco_conhecido) "
                 "VALUES (%s, 2.5, true), (%s, 1.5, true), (%s, NULL, false)", (ex, ex, ex))
    brl, sem_preco = conn.execute(
        "SELECT brl, sem_preco FROM gasto_diario WHERE dia = "
        "(now() AT TIME ZONE 'America/Sao_Paulo')::date").fetchone()
    assert float(brl) == 4.0 and sem_preco == 1


def test_v_card_extraida_e_exists_vigente(conn):
    ctrl = _licitacao(conn, 61, estado="publicada")
    assert conn.execute("SELECT extraida FROM v_card WHERE controle = %s",
                        (ctrl,)).fetchone()[0] is False
    ex = _execucao(conn, ctrl)
    _verificacao(conn, ctrl, ex, vigente=True)
    row = conn.execute("SELECT extraida, local FROM v_card WHERE controle = %s",
                       (ctrl,)).fetchone()
    assert row == (True, "Teste/SP")
    assert "dias" not in [d.name for d in conn.execute(
        "SELECT * FROM v_card LIMIT 0").description]
    conn.execute("SELECT * FROM v_detalhe WHERE controle = %s", (ctrl,)).fetchone()


# ------------------------------------------------------------- invariantes

def test_invariantes_rodam_num_banco_vazio(conn):
    sql = INVARIANTES.read_text(encoding="utf-8")
    rows = conn.execute(sql).fetchall()
    assert rows == []


def test_invariantes_pegam_violacao(conn):
    # Publicada sem verificação vigente é exatamente o que o T6 caçava.
    ctrl = _licitacao(conn, 70, estado="publicada")
    sql = INVARIANTES.read_text(encoding="utf-8")
    rows = conn.execute(sql).fetchall()
    assert any(r[1] == ctrl for r in rows), rows


# ------------------------------------------------ correções da revisão da F0
# A revisão da F0 achou dois defeitos importantes e alguns menores no 002/009/011.
# As migrações aplicadas são imutáveis (migrar.py aborta se o sha mudar), então
# a correção é a 013 — e cada teste abaixo nasceu de uma sonda que falhou.

def test_conhecida_com_prazo_vencido_nao_vira_encerrada(conn):
    # 20_monitor.py:454-475: a CONHECIDA é olhada primeiro; só a desconhecida
    # com prazo vencido é "encerrada". Antes, uma publicada com sessão passada
    # voltava "encerrada" e o W01 tentaria levá-la para fora_janela.
    hoje = "2026-09-24"
    q = "SELECT fn_classificar_vista(%s, %s::jsonb, %s::date)"
    ctrl = _licitacao(conn, 80, estado="publicada", fim_prazo="2026-09-01",
                      atualizado_pncp="2026-09-20 10:00:00")
    igual = '{"fim_prazo": "2026-09-01", "escopo_dentro": true, "atualizado_pncp": "2026-09-20T10:00:00"}'
    novo = '{"fim_prazo": "2026-09-01", "escopo_dentro": true, "atualizado_pncp": "2026-09-22T10:00:00"}'
    assert conn.execute(q, (ctrl, igual, hoje)).fetchone()[0] == "conhecida"
    assert conn.execute(q, (ctrl, novo, hoje)).fetchone()[0] == "retificada"


def test_retificacao_alcanca_quem_nao_leu(conn):
    # Uma sem_pdf_legivel que ganhou documento novo é justamente o caso que
    # importa detectar: o PDF legível pode ter chegado na retificação.
    hoje = "2026-09-24"
    q = "SELECT fn_classificar_vista(%s, %s::jsonb, %s::date)"
    novo = '{"fim_prazo": "2026-10-10", "escopo_dentro": true, "atualizado_pncp": "2026-09-22T10:00:00"}'
    for n, estado in enumerate(("sem_pdf_legivel", "formato_nao_suportado", "erro_definitivo")):
        ctrl = _licitacao(conn, 81 + n, estado=estado, atualizado_pncp="2026-09-20 10:00:00")
        assert conn.execute(q, (ctrl, novo, hoje)).fetchone()[0] == "retificada", estado
        conn.execute("SELECT fn_transicao(%s, 'retificada', 'W01', NULL)", (ctrl,))
        conn.execute("SELECT fn_transicao(%s, 'baixando', 'W21', NULL)", (ctrl,))


def test_mesmo_estado_e_noop_sem_evento(conn):
    # W23 sem vaga deixa `preparada` em `preparada`; W24 republica a partir de
    # `verificada`. Sem isto, o caminho normal do W23 estourava a tabela.
    for n, estado in enumerate(("preparada", "aguardando_orcamento", "verificada")):
        ctrl = _licitacao(conn, 90 + n, estado=estado)
        assert conn.execute("SELECT fn_transicao(%s, %s, 'mesmo estado', NULL)",
                            (ctrl, estado)).fetchone()[0] is None
        assert conn.execute("SELECT count(*) FROM licitacao_eventos WHERE controle = %s",
                            (ctrl,)).fetchone()[0] == 0


def test_publicada_exige_verificacao_vigente(conn):
    # ADR-004 / seção 3: verificacoes.vigente é pré-condição de publicada.
    ctrl = _licitacao(conn, 95, estado="verificada")
    with pytest.raises(errors.RaiseException):
        with conn.transaction():
            conn.execute("SELECT fn_transicao(%s, 'publicada', 'W24', NULL)", (ctrl,))
    ex = _execucao(conn, ctrl)
    _verificacao(conn, ctrl, ex, vigente=True)
    conn.execute("SELECT fn_transicao(%s, 'publicada', 'W24', NULL)", (ctrl,))
    assert conn.execute("SELECT estado FROM licitacoes WHERE controle = %s",
                        (ctrl,)).fetchone()[0] == "publicada"


def test_vaga_reserva_tambem_a_de_quem_pede(conn):
    # Com teto 5 e nada em curso, a extração que pede a vaga pode gastar até
    # R$ 6,56: reservar orçamento é contar ela também (seção 11, teste 7).
    ctrl = _licitacao(conn, 96, estado="preparada")
    ok, motivo = conn.execute(
        "SELECT ok, motivo FROM fn_tomar_vaga_extracao(%s, 4, 5)", (ctrl,)).fetchone()
    assert (ok, motivo) == (False, "sem_orcamento")
    ok, _ = conn.execute(
        "SELECT ok, motivo FROM fn_tomar_vaga_extracao(%s, 4, 7)", (ctrl,)).fetchone()
    assert ok is True


def test_worker_nao_apaga_texto_congelado_nem_verificacao(banco):
    # DELETE em leituras/verificacoes contornava a imutabilidade de paginas e
    # verificacao_respostas pelo CASCADE. A leitura nasce numa transação só:
    # abortada, nem chega a existir — o worker não precisa apagar nada.
    url = banco["url"].replace("postgres:" + SENHA_ADMIN, "worker_rw:" + SENHA_WORKER)
    with psycopg.connect(url) as c:
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("DELETE FROM leituras")
        c.rollback()
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("DELETE FROM verificacoes")
        c.rollback()


def test_assinatura_nomes_no_banco_e_no_python_sao_a_mesma(conn):
    # A 015 recalcula a identidade das leituras que já existiam; se o SQL e o
    # Python divergirem, o importador cria uma segunda leitura para o mesmo texto.
    sys.path.insert(0, str(RAIZ))
    from migracao import regras  # noqa: E402
    casos = [{}, {"b.pdf": "x2", "a.pdf": "x1"},
             {"03 - Termo de Referência - ação.pdf": "e22386", "01 - Edital.PDF.pdf": "4a6211",
              "Ärger.pdf": "00", "zeta.pdf": "ff"}]
    for a in casos:
        sql = conn.execute("SELECT fn_assinatura_nomes(%s::jsonb)", (json.dumps(a),)).fetchone()[0]
        assert sql == regras.assinatura_nomes(a), a


# ------------------------------------------------ 016: configuração e papel do site
def test_configuracao_semeada_com_provedor_simulado(conn):
    # "API só em produção": o provedor nasce simulado e só vira claude por
    # decisão explícita no admin (plano, seção 2). Mora no Postgres para o site
    # editar e o n8n ler do mesmo lugar.
    cfg = dict(conn.execute("SELECT chave, valor #>> '{}' FROM configuracao").fetchall())
    assert cfg["provedor"] == "simulado"
    assert cfg["modelo"] == "claude-opus-5" and cfg["effort"] == "high"
    # k_rag nasce 6 na 016 e a 026 sobe para 12 (os testes mostraram 12 páginas melhor)
    assert cfg["lote"] == "6" and cfg["k_rag"] == "12" and cfg["max_tokens"] == "16000"


def test_api_rw_grava_so_o_que_e_do_site(banco):
    # O site escreve revisões, rótulos, orçamento, termos, usuários, sessões e a
    # configuração; nunca respostas, verificações ou o estado da licitação.
    url = banco["url"].replace("postgres:" + SENHA_ADMIN, "api_rw:" + SENHA_API_RW)
    with psycopg.connect(url) as c:
        c.execute("UPDATE configuracao SET valor = '\"simulado\"' WHERE chave = 'provedor'")
        c.execute("INSERT INTO termos (termo) VALUES ('teste api_rw')")
        c.execute("INSERT INTO sessoes (id, email, expira_em) VALUES ('s1', 'admin@exemplo.com', now())")
        c.execute("DELETE FROM usuarios WHERE false")      # o supremo remove usuário pelo site (048)
        c.rollback()
        c.execute("SELECT count(*) FROM pncp_contratos, pncp_contrato_termos")   # o site lê os contratos (049)
        for comando in ("UPDATE respostas SET resposta = 'x'", "DELETE FROM verificacoes",
                        "UPDATE licitacoes SET estado = 'publicada'", "INSERT INTO paginas"
                        " (leitura_id, arquivo_nome, numero, ordem, texto) VALUES (1, 'a', 1, 1, 'x')",
                        # quem escreve contrato é o coletor, como worker_rw (049)
                        "INSERT INTO pncp_contratos (controle, payload, escopo_dentro) VALUES ('x', '{}', true)"):
            with pytest.raises(errors.InsufficientPrivilege):
                c.execute(comando)
            c.rollback()
        # reservar para a demo é do admin do site (plano, seção 8)
        c.execute("UPDATE licitacoes SET reserva_demo = true, fim_prazo = now() WHERE false")
        c.rollback()


# ------------------------------------------------ 018: recorte de 2026 (ADR-015)
def test_recorte_segue_a_adr_015(conn):
    # Só entra o que é de 2026: sessão em 2026 ou
    # depois; sem data de sessão, publicada em 2026 ou depois (_proximas.de_2026).
    q = "SELECT fn_no_recorte(%s::timestamptz, %s::date)"
    casos = [("2026-01-05 09:00-03", None, True),
             ("2025-12-31 23:30-03", "2026-01-02", False),   # a sessão manda, não a publicação
             ("2027-03-01 10:00-03", "2025-11-01", True),    # credenciamento com janela até 2027
             (None, "2026-02-01", True),
             (None, "2025-12-31", False),
             (None, None, False),                           # sem data nenhuma: fora, como no de_2026
             ("2026-01-01 01:00+00", None, False)]          # 31/12 22h em São Paulo: dia civil de SP
    for fim, pub, esperado in casos:
        assert conn.execute(q, (fim, pub)).fetchone()[0] is esperado, (fim, pub)
    # O ano mora na configuração: o admin muda sem migração.
    conn.execute("UPDATE configuracao SET valor = '2027' WHERE chave = 'ano_minimo'")
    assert conn.execute(q, ("2026-06-01 10:00-03", None)).fetchone()[0] is False


def test_descoberta_fora_do_recorte_nao_entra(conn):
    hoje = "2026-09-24"
    q = "SELECT fn_classificar_vista(%s, %s::jsonb, %s::date)"
    velha = '{"escopo_dentro": true, "publicado_em": "2025-06-10"}'
    recente = '{"escopo_dentro": true, "data_publicacao_pncp": "2026-09-20T08:00:00"}'
    sessao_velha = '{"escopo_dentro": true, "fim_prazo": "2025-11-30", "publicado_em": "2025-11-01"}'
    assert conn.execute(q, (_controle(90), velha, hoje)).fetchone()[0] == "fora_recorte"
    assert conn.execute(q, (_controle(91), recente, hoje)).fetchone()[0] == "nova"
    assert conn.execute(q, (_controle(92), sessao_velha, hoje)).fetchone()[0] == "fora_recorte"
    assert conn.execute(q, (_controle(93), '{"escopo_dentro": true}', hoje)).fetchone()[0] == "fora_recorte"


def test_conhecida_de_antes_de_2026_nao_reprocessa_na_retificacao(conn):
    # Uma publicada de 2025 que o PNCP retificou continua histórico: nada de
    # gastar extração com ela. O carimbo é guardado para não reavaliar sempre.
    hoje = "2026-09-24"
    q = "SELECT fn_classificar_vista(%s, %s::jsonb, %s::date)"
    ctrl = _licitacao(conn, 94, estado="publicada", fim_prazo="2025-08-01 10:00-03",
                      publicado_em="2025-07-01", atualizado_pncp="2026-09-20 10:00:00")
    novo = '{"escopo_dentro": true, "atualizado_pncp": "2026-09-22T10:00:00"}'
    assert conn.execute(q, (ctrl, novo, hoje)).fetchone()[0] == "conhecida"
    assert str(conn.execute("SELECT atualizado_pncp FROM licitacoes WHERE controle = %s",
                            (ctrl,)).fetchone()[0]).startswith("2026-09-22 10:00")
    # a mesma, de 2026, retifica normalmente
    ctrl2 = _licitacao(conn, 95, estado="publicada", fim_prazo="2026-08-01 10:00-03",
                       atualizado_pncp="2026-09-20 10:00:00")
    assert conn.execute(q, (ctrl2, novo, hoje)).fetchone()[0] == "retificada"


def test_configuracao_tem_ano_minimo_2026(conn):
    assert conn.execute("SELECT valor #>> '{}' FROM configuracao WHERE chave = 'ano_minimo'"
                        ).fetchone()[0] == "2026"


# ------------------------------------------ 019: fila guardada e escopo reavaliado
def test_fila_recusa_fora_do_escopo_e_fora_do_recorte(conn):
    # A vaga de extração é onde o dinheiro sai: nem objeto que a regra de hoje
    # recusa, nem licitação de antes de 2026 (ADR-015), passam daqui.
    q = "SELECT ok, motivo FROM fn_tomar_vaga_extracao(%s, 4, NULL)"
    fora = _licitacao(conn, 100, estado="preparada", escopo_dentro=False)
    velha = _licitacao(conn, 101, estado="preparada", fim_prazo="2025-10-10 10:00-03")
    boa = _licitacao(conn, 102, estado="preparada", fim_prazo="2026-10-10 10:00-03")
    ok, motivo = conn.execute(q, (fora,)).fetchone()
    assert ok is False and "escopo" in motivo
    ok, motivo = conn.execute(q, (velha,)).fetchone()
    assert ok is False and "recorte" in motivo
    assert conn.execute(q, (boa,)).fetchone()[0] is True
    estados = dict(conn.execute("SELECT controle, estado::text FROM licitacoes WHERE controle IN (%s, %s)",
                                (fora, velha)).fetchall())
    assert set(estados.values()) == {"preparada"}


def test_aplicar_escopo_tira_da_fila_e_devolve(conn):
    q = "SELECT fn_aplicar_escopo(%s, %s, %s, %s, %s)"
    prep = _licitacao(conn, 103, estado="preparada")
    assert conn.execute(q, (prep, False, "serviço bancário pago pelo órgão", "v2", "W01: reavaliação")
                        ).fetchone()[0] == "fora_escopo"
    linha = conn.execute("SELECT estado::text, escopo_dentro, escopo_motivo, escopo_versao FROM licitacoes"
                         " WHERE controle = %s", (prep,)).fetchone()
    assert linha == ("fora_escopo", False, "serviço bancário pago pelo órgão", "v2")
    # a regra voltou a aceitar: volta para o começo do funil, não para onde estava
    assert conn.execute(q, (prep, True, "cessão", "v3", "W01: reavaliação")).fetchone()[0] == "nova"
    # mesma decisão, versão nova: só a marca muda, sem evento
    n = conn.execute("SELECT count(*) FROM licitacao_eventos WHERE controle = %s", (prep,)).fetchone()[0]
    assert conn.execute(q, (prep, True, "cessão", "v4", "W01")).fetchone()[0] == "mesma_decisao"
    assert conn.execute("SELECT count(*) FROM licitacao_eventos WHERE controle = %s", (prep,)).fetchone()[0] == n
    # publicada não perde o relatório: só a marca muda (a evidência já existe)
    pub = _licitacao(conn, 104, estado="publicada")
    assert conn.execute(q, (pub, False, "consignado", "v2", "W01")).fetchone()[0] == "so_marcada"
    assert conn.execute("SELECT estado::text, escopo_dentro FROM licitacoes WHERE controle = %s",
                        (pub,)).fetchone() == ("publicada", False)


# ------------------------------------------------ 020: o W01 grava cada vista numa chamada
def _payload(n, **kw):
    base = {"controle": _controle(n), "ano": 2026, "seq": n, "orgao": "MUNICIPIO DE TESTE", "uf": "SP",
            "municipio": "Teste", "modalidade": "Pregão - Eletrônico", "objeto": "Cessão onerosa da folha",
            "situacao": "Divulgada no PNCP", "publicado_em": "2026-09-20", "fim_prazo": "2026-10-15T09:00",
            "link": "https://pncp.gov.br/app/editais/x", "atualizado_pncp": "2026-09-20T10:00:00",
            "escopo_dentro": True, "escopo_motivo": "cessão", "escopo_versao": "v-teste"}
    base.update(kw)
    return json.dumps(base)


def test_registrar_vista_insere_nova_com_os_campos(conn):
    q = "SELECT vista, acao FROM fn_registrar_vista(%s, %s::jsonb, %s::date, %s, %s)"
    ctrl = _controle(110)
    assert conn.execute(q, (ctrl, _payload(110), "2026-09-24", False, "W01")).fetchone() == ("nova", "inserir_nova")
    r = conn.execute("SELECT estado::text, origem, escopo_versao, uf, visto_em::text, fim_prazo_tem_hora,"
                     " to_char(fim_prazo AT TIME ZONE 'America/Sao_Paulo', 'YYYY-MM-DD HH24:MI'),"
                     " atualizado_pncp::text FROM licitacoes WHERE controle = %s", (ctrl,)).fetchone()
    assert r == ("nova", "n8n", "v-teste", "SP", "2026-09-24", True, "2026-10-15 09:00", "2026-09-20 10:00:00")
    # segunda vista, mesmo carimbo: só visto_em
    assert conn.execute(q, (ctrl, _payload(110), "2026-09-25", False, "W01")).fetchone() == ("conhecida", "visto")
    assert conn.execute("SELECT visto_em::text FROM licitacoes WHERE controle = %s", (ctrl,)).fetchone()[0] == "2026-09-25"


def test_registrar_vista_fora_do_escopo_encerrada_e_fora_do_recorte(conn):
    q = "SELECT vista, acao FROM fn_registrar_vista(%s, %s::jsonb, %s::date, %s, %s)"
    fora = _payload(111, escopo_dentro=False, escopo_motivo="consignado")
    assert conn.execute(q, (_controle(111), fora, "2026-09-24", False, "W01")).fetchone()[1] == "inserir_fora_escopo"
    enc = _payload(112, fim_prazo="2026-09-01T09:00")
    assert conn.execute(q, (_controle(112), enc, "2026-09-24", False, "W01")).fetchone()[1] == "inserir_fora_janela"
    velha = _payload(113, fim_prazo="2025-11-30T09:00", publicado_em="2025-11-01")
    assert conn.execute(q, (_controle(113), velha, "2026-09-24", False, "W01")).fetchone() == ("fora_recorte", "ignorar")
    estados = dict(conn.execute("SELECT controle, estado::text FROM licitacoes WHERE controle IN (%s, %s, %s)",
                                (_controle(111), _controle(112), _controle(113))).fetchall())
    assert estados == {_controle(111): "fora_escopo", _controle(112): "fora_janela"}


def test_registrar_vista_seco_nao_escreve_nem_carimba(conn):
    # "Verificar agora" (seco) não pode engolir uma retificação: se carimbasse,
    # a rodada real seguinte veria "conhecida" e a retificação se perderia.
    q = "SELECT vista, acao FROM fn_registrar_vista(%s, %s::jsonb, %s::date, %s, %s)"
    ctrl = _licitacao(conn, 114, estado="publicada", fim_prazo="2026-10-10 10:00-03",
                      atualizado_pncp="2026-09-20 10:00:00")
    novo = _payload(114, atualizado_pncp="2026-09-22T10:00:00")
    assert conn.execute(q, (ctrl, novo, "2026-09-24", True, "W01")).fetchone() == ("retificada", "retificar")
    assert str(conn.execute("SELECT atualizado_pncp FROM licitacoes WHERE controle = %s", (ctrl,)).fetchone()[0]
               ).startswith("2026-09-20")
    assert conn.execute(q, (_controle(115), _payload(115), "2026-09-24", True, "W01")).fetchone()[1] == "inserir_nova"
    assert conn.execute("SELECT count(*) FROM licitacoes WHERE controle = %s", (_controle(115),)).fetchone()[0] == 0
    # a real, depois: retifica de verdade e carimba
    assert conn.execute(q, (ctrl, novo, "2026-09-24", False, "W01")).fetchone() == ("retificada", "retificar")
    assert conn.execute("SELECT estado::text FROM licitacoes WHERE controle = %s", (ctrl,)).fetchone()[0] == "retificada"


def test_classificar_vista_continua_igual_depois_da_020(conn):
    # fn_classificar_vista passa a usar a mesma lógica pura; o comportamento
    # coberto pelos testes de 009/013/018 não muda (eles rodam de novo aqui).
    hoje = "2026-09-24"
    q = "SELECT fn_classificar_vista(%s, %s::jsonb, %s::date)"
    ctrl = _licitacao(conn, 116, estado="publicada", atualizado_pncp=None)
    assert conn.execute(q, (ctrl, '{"fim_prazo": "2026-10-10", "atualizado_pncp": "2026-09-20T10:00:00"}',
                            hoje)).fetchone()[0] == "conhecida"
    assert conn.execute("SELECT atualizado_pncp FROM licitacoes WHERE controle = %s", (ctrl,)).fetchone()[0] is not None


# ------------------------------------------------ 021: a fila do W10 no banco


def test_reivindicar_respeita_lease_escopo_recorte_e_prazo(conn):
    conn.execute("UPDATE configuracao SET valor = '\"openai\"' WHERE chave = 'provedor'")   # 032: provedor real
    a = _licitacao(conn, 120, estado="nova", fim_prazo="2026-12-01 10:00-03", prioridade=5)
    b = _licitacao(conn, 121, estado="preparada", fim_prazo="2026-12-02 10:00-03")
    c = _licitacao(conn, 122, estado="nova", fim_prazo="2026-12-03 10:00-03",
                   lease_por="W20:9", lease_ate="2999-01-01")                        # já com lease vivo
    d = _licitacao(conn, 123, estado="nova", fim_prazo="2026-12-03 10:00-03", escopo_dentro=False)
    e = _licitacao(conn, 124, estado="nova", fim_prazo="2025-12-03 10:00-03")        # fora do recorte
    f = _licitacao(conn, 125, estado="nova", fim_prazo="2026-12-03 10:00-03", reserva_demo=True)
    g = _licitacao(conn, 126, estado="falha_rede", fim_prazo="2026-12-03 10:00-03",
                   proxima_tentativa_em="2999-01-01")                                 # em backoff
    todos = (a, b, c, d, e, f, g)
    got = [r[0] for r in conn.execute("SELECT controle FROM fn_reivindicar('W10:1', NULL)").fetchall()
           if r[0] in todos]
    assert got == [a, b]                                   # prioridade primeiro, depois prazo
    leases = dict(conn.execute("SELECT controle, lease_por FROM licitacoes WHERE controle IN (%s, %s)",
                               (a, b)).fetchall())
    assert leases == {a: "W10:1", b: "W10:1"}
    # a segunda execução do W10 não pega de novo o que já tem lease
    assert not [r for r in conn.execute("SELECT controle FROM fn_reivindicar('W10:2', NULL)").fetchall()
                if r[0] in todos]



def test_carimbo_mudado_a_mao_retifica_e_o_w10_pega_primeiro(conn):
    # Checklist F5: o carimbo `atualizado_pncp` muda (e nada mais) → a vista devolve `retificada`, a
    # licitação reentra na fila e o W10 a reivindica ANTES de uma nova com prazo mais cedo
    # (db/021: ORDER BY prioridade DESC, (estado = 'retificada') DESC, fim_prazo).
    q = "SELECT vista, acao FROM fn_registrar_vista(%s, %s::jsonb, %s::date, %s, %s)"
    ret = _licitacao(conn, 150, estado="publicada", fim_prazo="2026-12-20 10:00-03",
                     atualizado_pncp="2026-09-20 10:00:00")
    cedo = _licitacao(conn, 151, estado="nova", fim_prazo="2026-12-01 10:00-03")
    novo = _payload(150, fim_prazo="2026-12-20T10:00", atualizado_pncp="2026-09-23T08:00:00")
    assert conn.execute(q, (ret, novo, "2026-09-24", False, "W01")).fetchone() == ("retificada", "retificar")
    assert conn.execute("SELECT estado::text FROM licitacoes WHERE controle = %s", (ret,)).fetchone()[0] == "retificada"
    got = [r[0] for r in conn.execute("SELECT controle FROM fn_reivindicar('W10:15', NULL)").fetchall()
           if r[0] in (ret, cedo)]
    assert got == [ret, cedo], "a retificada passa na frente da nova de prazo mais cedo"


def test_032_fila_respeita_rotulo_e_sem_provedor_real_so_baixa_e_le(conn):
    # A fila roda todo dia às 6 — e o rótulo humano (db/031) vale para ela. Sem provedor real
    # (a semente é `simulado`), licitação real só vai adiante para BAIXAR e LER (R$ 0): a extração de mentira seria
    # recusada na publicação (T15) e as tentativas acabariam em erro_definitivo. Ensaio segue inteiro.
    assert conn.execute("SELECT fn_provedor_real()").fetchone()[0] is False
    nova = _licitacao(conn, 160, estado="nova", fim_prazo="2026-12-01 10:00-03")
    preparada = _licitacao(conn, 161, estado="preparada", fim_prazo="2026-12-01 10:00-03")
    ensaio = _licitacao(conn, 162, estado="preparada", fim_prazo="2026-12-01 10:00-03", ensaio=True)
    tirada = _licitacao(conn, 163, estado="nova", fim_prazo="2026-12-01 10:00-03")
    posta = _licitacao(conn, 164, estado="fora_escopo", fim_prazo="2026-12-01 10:00-03", escopo_dentro=False)
    conn.execute("INSERT INTO rotulos_escopo (controle, veredito, por) VALUES (%s, 'fora', 'admin'), (%s, 'dentro', 'admin')",
                 (tirada, posta))
    # o rótulo "dentro" tira a licitação de fora_escopo pela transição nova (032)
    conn.execute("SELECT fn_transicao(%s, 'nova', 'rótulo humano: é folha', '{}'::jsonb)", (posta,))
    todos = (nova, preparada, ensaio, tirada, posta)
    got = {r[0] for r in conn.execute("SELECT controle FROM fn_reivindicar('W10:32', NULL)").fetchall()} & set(todos)
    assert got == {nova, ensaio, posta}
    # com o provedor real, a preparada real também vai (e a tirada continua fora)
    conn.execute("UPDATE licitacoes SET lease_por = NULL, lease_ate = NULL WHERE controle = ANY(%s)", (list(todos),))
    conn.execute("UPDATE configuracao SET valor = '\"openai\"' WHERE chave = 'provedor'")
    got = {r[0] for r in conn.execute("SELECT controle FROM fn_reivindicar('W10:33', NULL)").fetchall()} & set(todos)
    assert got == {nova, preparada, ensaio, posta}


def test_033_pedido_de_extracao_com_ia_libera_so_aquela_licitacao(conn):
    # O botão "Extrair com GPT": o provedor global continua simulado; a licitação com pedido
    # pendente vai à extração (a preparada é reivindicada), a outra preparada real não. Usado o pedido, acabou.
    assert conn.execute("SELECT fn_provedor_real()").fetchone()[0] is False
    com = _licitacao(conn, 170, estado="preparada", fim_prazo="2026-12-01 10:00-03")
    sem = _licitacao(conn, 171, estado="preparada", fim_prazo="2026-12-01 10:00-03")
    conn.execute("INSERT INTO pedidos_extracao (controle, provedor, pedido_por) VALUES (%s, 'openai', 'admin')", (com,))
    assert conn.execute("SELECT fn_provedor_pedido(%s), fn_extrai_com_ia(%s), fn_extrai_com_ia(%s)",
                        (com, com, sem)).fetchone() == ("openai", True, False)
    got = {r[0] for r in conn.execute("SELECT controle FROM fn_reivindicar('W10:40', NULL)").fetchall()} & {com, sem}
    assert got == {com}
    conn.execute("UPDATE pedidos_extracao SET usado_em = now() WHERE controle = %s", (com,))
    assert conn.execute("SELECT fn_provedor_pedido(%s), fn_extrai_com_ia(%s)", (com, com)).fetchone() == (None, False)


def _escopo_ia(conn, ctrl, p, contexto="objeto"):
    conn.execute("INSERT INTO sinais_jev (tipo, controle, criterio_versao, regra, resposta, p_sim, contexto_enviado,"
                 " candidata) VALUES ('escopo', %s, 'escopo-v3', 'dentro', 'x', %s, %s, false)", (ctrl, p, contexto))


def test_034_a_ia_que_nao_reconhece_fopa_trava_a_fila_e_o_rotulo_humano_manda(conn):
    # A extração para quando a IA não reconhece a licitação como folha. A nota é a média do
    # só-objeto com o objeto+edital (a mesma da tela); a trava é a convicção (<= 0,25) e o rótulo "dentro" manda.
    ia_nao = _licitacao(conn, 180, estado="nova", fim_prazo="2026-12-01 10:00-03")
    duvida = _licitacao(conn, 181, estado="nova", fim_prazo="2026-12-01 10:00-03")
    rotulada = _licitacao(conn, 182, estado="nova", fim_prazo="2026-12-01 10:00-03")
    sem_nota = _licitacao(conn, 183, estado="nova", fim_prazo="2026-12-01 10:00-03")
    _escopo_ia(conn, ia_nao, 0.30)
    _escopo_ia(conn, ia_nao, 0.10, "edital RAG 3p (9000 caracteres)")          # média 0,20: convicção
    _escopo_ia(conn, duvida, 0.40)                                              # 0,40: dúvida, não trava
    _escopo_ia(conn, rotulada, 0.05)
    conn.execute("INSERT INTO rotulos_escopo (controle, veredito, por) VALUES (%s, 'dentro', 'admin')", (rotulada,))
    q = "SELECT fn_ia_nao_fopa(%s, 0.25), fn_ia_nao_fopa(%s, 0.5)"
    assert conn.execute(q, (ia_nao, ia_nao)).fetchone() == (True, True)
    assert conn.execute(q, (duvida, duvida)).fetchone() == (False, True)      # o filtro "apenas FOPA" esconde
    assert conn.execute(q, (rotulada, rotulada)).fetchone() == (False, False)  # gente disse que é
    assert conn.execute(q, (sem_nota, sem_nota)).fetchone() == (False, False)  # sem nota, sem trava
    assert float(conn.execute("SELECT fn_ia_p_folha(%s)", (ia_nao,)).fetchone()[0]) == pytest.approx(0.20)
    got = {r[0] for r in conn.execute("SELECT controle FROM fn_reivindicar('W10:34', NULL)").fetchall()}
    assert ia_nao not in got and {duvida, rotulada, sem_nota} <= got


def test_034_a_vaga_de_extracao_para_o_que_a_ia_recusa_e_segue_o_escopo_efetivo(conn):
    # A vaga é o único freio de TODA extração (fila, "Processar", botão do GPT): a trava da IA vale ali também, sem
    # chamar provedor nem mudar estado; e o escopo é o efetivo (db/031) — o rótulo humano manda nos dois sentidos.
    q = "SELECT ok, motivo FROM fn_tomar_vaga_extracao(%s, 4, NULL)"
    ia_nao = _licitacao(conn, 185, estado="preparada", fim_prazo="2026-12-01 10:00-03")
    _escopo_ia(conn, ia_nao, 0.20)
    _escopo_ia(conn, ia_nao, 0.10, "edital RAG 2p (5000 caracteres)")
    ok, motivo = conn.execute(q, (ia_nao,)).fetchone()
    assert ok is False and "IA" in motivo and "histórico" in motivo
    assert conn.execute("SELECT estado::text FROM licitacoes WHERE controle = %s", (ia_nao,)).fetchone()[0] == "preparada"
    conn.execute("INSERT INTO rotulos_escopo (controle, veredito, por) VALUES (%s, 'dentro', 'admin')", (ia_nao,))
    assert conn.execute(q, (ia_nao,)).fetchone()[0] is True                      # gente disse que é: destrava
    regra_fora = _licitacao(conn, 186, estado="preparada", escopo_dentro=False, fim_prazo="2026-12-01 10:00-03")
    conn.execute("INSERT INTO rotulos_escopo (controle, veredito, por) VALUES (%s, 'dentro', 'admin')", (regra_fora,))
    assert conn.execute(q, (regra_fora,)).fetchone()[0] is True                  # o rótulo libera o que a regra recusou
    regra_dentro = _licitacao(conn, 187, estado="preparada", fim_prazo="2026-12-01 10:00-03")
    conn.execute("INSERT INTO rotulos_escopo (controle, veredito, por) VALUES (%s, 'fora', 'admin')", (regra_dentro,))
    ok, motivo = conn.execute(q, (regra_dentro,)).fetchone()
    assert ok is False and "escopo" in motivo                                    # e barra o que a regra aceitou


def test_035_a_trava_so_age_depois_de_a_ia_ver_o_edital(conn):
    # A nota SÓ-OBJETO tem o ponto cego do credenciamento (as 5 discordâncias do painel; "instituição financeira ...
    # administração e processamento" com 0,24 no histórico): barrar por ela na fila seria nunca ler o edital de uma
    # folha legítima. A trava espera a nota com o edital, que o W22 pede depois da leitura.
    q = "SELECT ok, motivo FROM fn_tomar_vaga_extracao(%s, 4, NULL)"
    credenciamento = _licitacao(conn, 188, estado="nova", fim_prazo="2026-12-01 10:00-03")
    _escopo_ia(conn, credenciamento, 0.10)                                      # só o objeto, e com convicção
    assert conn.execute("SELECT fn_ia_trava(%s), fn_ia_nao_fopa(%s, 0.5)", (credenciamento, credenciamento)
                        ).fetchone() == (False, True)                            # não trava; o filtro esconde
    got = {r[0] for r in conn.execute("SELECT controle FROM fn_reivindicar('W10:35', NULL)").fetchall()}
    assert credenciamento in got                                                 # vai à fila: será lido
    conn.execute("UPDATE licitacoes SET estado = 'preparada', lease_por = NULL WHERE controle = %s", (credenciamento,))
    assert conn.execute(q, (credenciamento,)).fetchone()[0] is True              # e a vaga não para
    conn.execute("SELECT fn_transicao(%s, 'erro_extracao', 'teste', NULL)", (credenciamento,))
    # a IA viu o edital e segue achando que não: agora trava (média 0,10/0,20 = 0,15)
    _escopo_ia(conn, credenciamento, 0.20, "edital RAG 3p (8000 caracteres)")
    assert conn.execute("SELECT fn_ia_trava(%s)", (credenciamento,)).fetchone()[0] is True
    ok, motivo = conn.execute(q, (credenciamento,)).fetchone()
    assert ok is False and "edital" in motivo
    # com o edital a IA reconhece (média 0,10/0,90 = 0,50): não trava
    _escopo_ia(conn, credenciamento, 0.90, "edital RAG 3p (8000 caracteres)")
    assert conn.execute("SELECT fn_ia_trava(%s)", (credenciamento,)).fetchone()[0] is False


def test_036_a_fila_pega_o_que_parou_entre_baixar_e_ler(conn):
    # Em 25/09, o "Extrair com GPT" em Poá não fez nada. Poá estava em `baixada_ok` (baixada às 00h30,
    # nunca lida): o W11 aceitou e deu prioridade, mas a fila não tinha baixada_ok/erro_leitura na lista — o W20 sabe
    # continuar deles (vai direto à leitura) e ninguém os entregava. Ler é de graça: entram mesmo sem provedor real.
    baixada = _licitacao(conn, 190, estado="baixada_ok", fim_prazo="2026-12-01 10:00-03")
    erro_leitura = _licitacao(conn, 191, estado="erro_leitura", fim_prazo="2026-12-01 10:00-03")
    respondida = _licitacao(conn, 192, estado="respondida", fim_prazo="2026-12-01 10:00-03")
    conn.execute("UPDATE licitacoes SET prioridade = 1 WHERE controle = %s", (baixada,))   # o clique do site (db/022)
    got = [r[0] for r in conn.execute("SELECT controle FROM fn_reivindicar('W10:36', NULL)").fetchall()]
    assert got[0] == baixada                           # a pedida vem primeiro
    assert erro_leitura in got                         # releitura: de graça
    assert respondida not in got                       # verificar/publicar só com provedor real (T15)


def test_037_o_pedido_leva_modelo_esforco_e_teto(conn):
    # Provedor, modelo e esforço escolhidos no botão. O W23 lê a escolha do pedido PENDENTE mais recente.
    ctrl = _licitacao(conn, 195, estado="preparada", fim_prazo="2026-12-01 10:00-03")
    conn.execute("INSERT INTO pedidos_extracao (controle, provedor, pedido_por, modelo, effort, max_tokens, usado_em)"
                 " VALUES (%s, 'openai', 'admin', 'gpt-5.6-sol', 'high', 16000, now())", (ctrl,))          # já usado
    conn.execute("INSERT INTO pedidos_extracao (controle, provedor, pedido_por, modelo, effort, max_tokens)"
                 " VALUES (%s, 'claude', 'admin', 'claude-opus-5', 'max', 64000)", (ctrl,))
    assert conn.execute("SELECT * FROM fn_pedido_ia(%s)", (ctrl,)).fetchone() == ("claude", "claude-opus-5", "max", 64000)
    assert conn.execute("SELECT fn_provedor_pedido(%s)", (ctrl,)).fetchone()[0] == "claude"
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO pedidos_extracao (controle, provedor, pedido_por, max_tokens) VALUES (%s, 'openai', 'x', 999999)",
                     (ctrl,))


def test_038_039_o_produto_so_manda_dois_emails(conn):
    # Só dois e-mails: a licitação nova que passa no filtro e, para quem pediu, o resultado da extração pela API.
    # O destinatário mora na linha (`para`); NULL = os admins ativos, resolvido pelo W50 na hora do envio.
    ctrl = _licitacao(conn, 196, fim_prazo="2026-12-01 10:00-03")
    conn.execute("INSERT INTO emails (tipo, controle, assunto) VALUES ('licitacao_nova', %s, 'nova')", (ctrl,))
    conn.execute("INSERT INTO emails (tipo, controle, assunto, para) VALUES ('extracao', %s, 'extração', %s)",
                 (ctrl, "quem@pediu.br"))
    assert conn.execute("SELECT tipo, para, status FROM emails WHERE controle = %s ORDER BY id", (ctrl,)).fetchall() == \
        [("licitacao_nova", None, "pendente"), ("extracao", "quem@pediu.br", "pendente")]
    for velho in ("carregada", "processada", "erro", "alerta_diario", "orcamento", "cego", "furtivo", "republicada",
                  "reverificacao"):
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute("INSERT INTO emails (tipo, assunto) VALUES (%s, 'x')", (velho,))


def test_reivindicar_limite_pelas_vagas_de_extracao(conn):
    for n in range(130, 134):
        _licitacao(conn, n, estado="extraindo", fim_prazo="2026-12-01 10:00-03")
    _licitacao(conn, 134, estado="nova", fim_prazo="2026-12-01 10:00-03")
    assert conn.execute("SELECT count(*) FROM fn_reivindicar('W10:3', NULL)").fetchone()[0] == 0


def test_falha_registrada_faz_backoff_e_vira_definitiva_na_quarta(conn):
    ctrl = _licitacao(conn, 140, estado="baixando", fim_prazo="2026-12-01 10:00-03", lease_por="W20:1",
                      lease_ate="2999-01-01")
    esperas = []
    for _ in range(3):
        conn.execute("SELECT fn_registrar_falha(%s, 'falha_rede', 'PNCP 503', false)", (ctrl,))
        estado, tent, espera, lease = conn.execute(
            "SELECT estado::text, tentativas, round(extract(epoch FROM proxima_tentativa_em - now()) / 60),"
            " lease_por FROM licitacoes WHERE controle = %s", (ctrl,)).fetchone()
        assert estado == "falha_rede" and lease is None
        esperas.append((tent, int(espera)))
        conn.execute("SELECT fn_transicao(%s, 'baixando', 'retentativa', NULL)", (ctrl,))
    assert esperas == [(1, 15), (2, 120), (3, 720)]
    conn.execute("SELECT fn_registrar_falha(%s, 'falha_rede', 'PNCP 503', false)", (ctrl,))
    assert conn.execute("SELECT estado::text, tentativas FROM licitacoes WHERE controle = %s",
                        (ctrl,)).fetchone() == ("erro_definitivo", 4)


def test_falha_de_coleta_cega_nao_conta_tentativa(conn):
    ctrl = _licitacao(conn, 141, estado="baixando", fim_prazo="2026-12-01 10:00-03")
    conn.execute("SELECT fn_registrar_falha(%s, 'falha_rede', 'PNCP fora', true)", (ctrl,))
    assert conn.execute("SELECT estado::text, tentativas FROM licitacoes WHERE controle = %s",
                        (ctrl,)).fetchone() == ("falha_rede", 0)


def test_lease_vencido_devolve_quem_morreu_no_meio(conn):
    # worker morto durante um job: o lease vence e o W10 devolve a licitação
    # como falha do passo em que estava (baixando -> falha_rede, lendo ->
    # erro_leitura, extraindo -> erro_extracao), com tentativa e backoff.
    casos = {"baixando": "falha_rede", "lendo": "erro_leitura", "extraindo": "erro_extracao"}
    ctrls = {}
    for n, (de, _) in enumerate(casos.items()):
        ctrls[de] = _licitacao(conn, 150 + n, estado=de, fim_prazo="2026-12-01 10:00-03",
                               lease_por="W20:7", lease_ate="2000-01-01")
    parada = _licitacao(conn, 153, estado="preparada", lease_por="W10:7", lease_ate="2000-01-01")
    viva = _licitacao(conn, 154, estado="lendo", lease_por="W20:8", lease_ate="2999-01-01")
    conn.execute("SELECT * FROM fn_liberar_leases_vencidos()").fetchall()
    for de, para in casos.items():
        assert conn.execute("SELECT estado::text, tentativas, lease_por FROM licitacoes WHERE controle = %s",
                            (ctrls[de],)).fetchone() == (para, 1, None), de
    assert conn.execute("SELECT estado::text, lease_por FROM licitacoes WHERE controle = %s",
                        (parada,)).fetchone() == ("preparada", None)
    assert conn.execute("SELECT lease_por FROM licitacoes WHERE controle = %s", (viva,)).fetchone()[0] == "W20:8"


def test_disjuntor_abre_com_tres_erros_sem_sucesso(conn):
    conn.execute("DELETE FROM execucoes_workflow WHERE workflow = 'W20'")
    assert conn.execute("SELECT fn_disjuntor_w20_aberto()").fetchone()[0] is False
    for _ in range(3):
        conn.execute("INSERT INTO execucoes_workflow (workflow, status) VALUES ('W20', 'erro')")
    assert conn.execute("SELECT fn_disjuntor_w20_aberto()").fetchone()[0] is True
    conn.execute("INSERT INTO execucoes_workflow (workflow, status) VALUES ('W20', 'ok')")
    assert conn.execute("SELECT fn_disjuntor_w20_aberto()").fetchone()[0] is False


# ------------------------------------------------ 022: o pedido do site (W11 fopa/processar)
def test_pedir_processamento_prioriza_sem_forcar(conn):
    q = "SELECT aceito, estado, motivo FROM fn_pedir_processamento(%s, %s, %s)"
    ctrl = _licitacao(conn, 160, estado="preparada", fim_prazo="2026-12-01 10:00-03")
    assert conn.execute(q, (ctrl, False, "operador@x")).fetchone() == (True, "preparada", "na fila, com prioridade")
    assert conn.execute("SELECT prioridade, solicitante FROM licitacoes WHERE controle = %s",
                        (ctrl,)).fetchone() == (1, "operador@x")


def test_pedir_processamento_forcar_recomeca_com_evento(conn):
    q = "SELECT aceito, estado, motivo FROM fn_pedir_processamento(%s, %s, %s)"
    for n, de in enumerate(("fora_janela", "erro_definitivo", "publicada")):
        ctrl = _licitacao(conn, 161 + n, estado=de, fim_prazo="2026-12-01 10:00-03", tentativas=4,
                          proxima_tentativa_em="2999-01-01")
        sem = conn.execute(q, (ctrl, False, "op@x")).fetchone()
        assert sem[0] is False and "forcar" in sem[2], de
        assert conn.execute(q, (ctrl, True, "op@x")).fetchone()[:2] == (True, "nova"), de
        linha = conn.execute("SELECT estado::text, tentativas, proxima_tentativa_em FROM licitacoes"
                             " WHERE controle = %s", (ctrl,)).fetchone()
        assert linha == ("nova", 0, None), de
        assert conn.execute("SELECT count(*) FROM licitacao_eventos WHERE controle = %s AND para = 'nova'",
                            (ctrl,)).fetchone()[0] == 1, de


def test_pedir_processamento_recusa_fora_do_escopo_do_recorte_e_desconhecida(conn):
    q = "SELECT aceito, estado, motivo FROM fn_pedir_processamento(%s, %s, %s)"
    fora = _licitacao(conn, 165, estado="fora_escopo", escopo_dentro=False)
    r = conn.execute(q, (fora, True, "op@x")).fetchone()
    assert r[0] is False and "escopo" in r[2]                      # o rótulo humano vai para /revisao, não aqui
    velha = _licitacao(conn, 166, estado="preparada", fim_prazo="2025-05-01 10:00-03")
    r = conn.execute(q, (velha, True, "op@x")).fetchone()
    assert r[0] is False and "recorte" in r[2]
    r = conn.execute(q, (_controle(167), False, "op@x")).fetchone()
    assert r == (False, None, "desconhecida")                      # o W11 busca no PNCP e registra antes


# ------------------------------------------------ 023: a demo reservada fica de pé
def test_rearmar_so_para_reservada_da_demo(conn):
    # demo_reservar --rearmar: publicada -> preparada, para o ensaio repetir 3x
    # e o plano B (gravado) ter o que repetir. Só com reserva_demo.
    livre = _licitacao(conn, 170, estado="publicada")
    with pytest.raises(errors.RaiseException):
        conn.execute("SELECT fn_transicao(%s, 'preparada', 'teste', NULL)", (livre,))
    conn.rollback()
    reservada = _licitacao(conn, 171, estado="publicada", reserva_demo=True, ensaio=True)
    conn.execute("SELECT fn_transicao(%s, 'preparada', 'demo: rearmar', NULL)", (reservada,))
    assert conn.execute("SELECT estado::text FROM licitacoes WHERE controle = %s",
                        (reservada,)).fetchone()[0] == "preparada"


def test_reservada_nao_retifica_no_dia_da_demo_e_retifica_depois(conn):
    q = "SELECT vista, acao FROM fn_registrar_vista(%s, %s::jsonb, %s::date, %s, %s)"
    ctrl = _licitacao(conn, 172, estado="preparada", reserva_demo=True, ensaio=True,
                      fim_prazo="2026-10-10 10:00-03", atualizado_pncp="2026-09-20 10:00:00")
    novo = _payload(172, atualizado_pncp="2026-09-22T10:00:00")
    assert conn.execute(q, (ctrl, novo, "2026-09-24", False, "W01")).fetchone() == ("retificada", "visto_reservada")
    linha = conn.execute("SELECT estado::text, atualizado_pncp::text FROM licitacoes WHERE controle = %s",
                         (ctrl,)).fetchone()
    assert linha == ("preparada", "2026-09-20 10:00:00")        # sem carimbo: a retificação não se perde
    conn.execute("UPDATE licitacoes SET reserva_demo = false WHERE controle = %s", (ctrl,))
    assert conn.execute(q, (ctrl, novo, "2026-09-25", False, "W01")).fetchone() == ("retificada", "retificar")


# ------------------------------------------------ 024: T15 também pelos outros dois lados
def test_t15_nao_se_contorna_trocando_a_origem_da_execucao(conn):
    # Achado do CI (24/09): o gatilho só olhava `verificacoes`. Uma vigente de
    # execução real numa licitação real, com a execução "virando" simulado
    # depois, ficava publicada sem nada barrar.
    ctrl = _licitacao(conn, 180, estado="verificada")
    ex = _execucao(conn, ctrl, origem="api", canonica=True)
    _verificacao(conn, ctrl, ex, vigente=True)
    with pytest.raises(errors.RaiseException):
        with conn.transaction():
            conn.execute("UPDATE execucoes_modelo SET origem = 'simulado', canonica = false WHERE id = %s", (ex,))
    # sem vigente, a troca é permitida (nada publicado depende dela)
    ex2 = _execucao(conn, ctrl, origem="api", canonica=False)
    conn.execute("UPDATE execucoes_modelo SET origem = 'gravado' WHERE id = %s", (ex2,))


def test_t15_nao_se_contorna_desligando_o_ensaio(conn):
    ctrl = _licitacao(conn, 181, estado="verificada", ensaio=True)
    ex = _execucao(conn, ctrl, origem="simulado", canonica=False)
    _verificacao(conn, ctrl, ex, vigente=True)
    with pytest.raises(errors.RaiseException):
        with conn.transaction():
            conn.execute("UPDATE licitacoes SET ensaio = false WHERE controle = %s", (ctrl,))
    # ensaio de licitação cuja vigente é real pode ser desligado
    ctrl2 = _licitacao(conn, 182, estado="verificada", ensaio=True)
    _verificacao(conn, ctrl2, _execucao(conn, ctrl2, origem="api"), vigente=True)
    conn.execute("UPDATE licitacoes SET ensaio = false WHERE controle = %s", (ctrl2,))


# ------------------------------------------------ 025: dois W01 ao mesmo tempo
def test_registrar_vista_concorrente_so_um_insere(banco):
    # Achado do W01 (24/09): duas rodadas simultâneas viam a mesma licitação
    # como desconhecida; a segunda esperava o INSERT da primeira e, com o
    # ON CONFLICT DO NOTHING, ainda devolvia 'inserir_nova' — e o W01 chamava
    # o Jev duas vezes para a mesma linha.
    import threading
    ctrl = _controle(190)
    q = "SELECT vista, acao FROM fn_registrar_vista(%s, %s::jsonb, %s::date, %s, %s)"
    payload = _payload(190)
    a = psycopg.connect(banco["url"])
    b = psycopg.connect(banco["url"])
    try:
        ra = a.execute(q, (ctrl, payload, "2026-09-24", False, "W01")).fetchone()   # transação aberta
        rb = {}

        def segunda():
            rb["r"] = b.execute(q, (ctrl, payload, "2026-09-24", False, "W01")).fetchone()
            b.commit()

        t = threading.Thread(target=segunda)
        t.start()
        t.join(1.5)
        assert t.is_alive(), "a segunda rodada deveria esperar o INSERT da primeira"
        a.commit()
        t.join(10)
        assert ra[1] == "inserir_nova"
        assert rb["r"][1] != "inserir_nova", rb["r"]
    finally:
        with psycopg.connect(banco["url"], autocommit=True) as c:
            c.execute("DELETE FROM licitacoes WHERE controle = %s", (ctrl,))
        a.close()
        b.close()


def test_047_data_de_sessao_absurda_vira_sem_data_no_card(conn):
    # Brasília/DF aparecia a 3.522 dias da sessão. No PNCP, Brasília foi
    # publicada em 18/05/2026 com sessão em 19/05/2036 (2026 digitado 2036) — e já homologada. Sessão mais de 2 anos
    # depois da publicação é data inválida: o card trata como sem data e guarda a do PNCP à parte. 366 dias é o
    # credenciamento aberto por 12 meses (54 no acervo de 27/09): fica como está.
    absurda = _licitacao(conn, 9701, publicado_em="2026-05-18", fim_prazo="2036-05-19T10:00:00-03:00")
    doze_meses = _licitacao(conn, 9702, publicado_em="2026-06-30", fim_prazo="2027-07-01T10:00:00-03:00")
    dois_anos = _licitacao(conn, 9703, publicado_em="2026-01-10", fim_prazo="2028-01-10T10:00:00-03:00")
    linhas = dict((c, (f, inv)) for c, f, inv in conn.execute(
        "SELECT controle, fim_prazo, fim_prazo_pncp_invalido FROM v_card WHERE controle IN (%s, %s, %s)",
        (absurda, doze_meses, dois_anos)).fetchall())
    f, inv = linhas[absurda]
    assert f is None and inv.date().isoformat() == "2036-05-19"
    for ctrl in (doze_meses, dois_anos):                  # até 730 dias depois da publicação vale
        f, inv = linhas[ctrl]
        assert f is not None and inv is None
    # o detalhe herda do card; a tabela guarda o que o PNCP mandou
    assert conn.execute("SELECT fim_prazo FROM v_detalhe WHERE controle = %s", (absurda,)).fetchone()[0] is None
    assert conn.execute("SELECT fim_prazo FROM licitacoes WHERE controle = %s", (absurda,)).fetchone()[0] is not None


def test_050_melhor_de_n_rodada_registro_e_configuracao(conn):
    # Best-of-N: rodada 0 = o lote normal; 1..N-1 = o reforço das perguntas que
    # falharam (W23 + POST /reforco). O registro da escolha fica na verificação; N mora na configuração (3).
    ctrl = _licitacao(conn, 9801)
    exec_id = _execucao(conn, ctrl)
    conn.execute("INSERT INTO chamadas_modelo (execucao_id, lote_ids) VALUES (%s, ARRAY['Q1'])", (exec_id,))
    conn.execute("INSERT INTO chamadas_modelo (execucao_id, lote_ids, rodada) VALUES (%s, ARRAY['Q7'], 2)", (exec_id,))
    assert [r[0] for r in conn.execute(
        "SELECT rodada FROM chamadas_modelo WHERE execucao_id = %s ORDER BY id", (exec_id,))] == [0, 2]
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute("INSERT INTO chamadas_modelo (execucao_id, lote_ids, rodada) VALUES (%s, ARRAY['Q7'], -1)",
                         (exec_id,))
    vid = _verificacao(conn, ctrl, exec_id)
    conn.execute("UPDATE verificacoes SET melhor_de_n = %s WHERE id = %s",
                 ('{"n": 3, "rodadas": 1, "perguntas": {"Q7": {"tentativas": 2, "escolhida": 1}}}', vid))
    assert conn.execute("SELECT melhor_de_n #>> '{perguntas,Q7,escolhida}' FROM verificacoes WHERE id = %s",
                        (vid,)).fetchone()[0] == "1"
    assert conn.execute("SELECT valor FROM configuracao WHERE chave = 'melhor_de_n'").fetchone()[0] == 3
    # quem grava: o n8n (W23) insere a chamada com a rodada; o worker grava o registro na verificação
    privs = dict(conn.execute(
        "SELECT grantee, string_agg(privilege_type, ',') FROM information_schema.column_privileges"
        " WHERE table_name = 'verificacoes' AND column_name = 'melhor_de_n' AND grantee IN ('worker_rw')"
        " GROUP BY grantee").fetchall())
    assert "UPDATE" in privs.get("worker_rw", "")


def test_051_descricao_da_k_rag_sem_citacao_pessoal(conn):
    # A página Admin mostra a descrição da configuração: fica a ADR e o valor, sem o nome de quem pediu. A 051 só troca
    # o texto que a 026 gravou; um valor editado depois pelo site não é tocado.
    assert conn.execute("SELECT descricao, alterado_por FROM configuracao WHERE chave = 'k_rag'").fetchone() == (
        "ADR-010: páginas por pergunta no modo RAG (12 desde 24/09/2026)", "db/026")
