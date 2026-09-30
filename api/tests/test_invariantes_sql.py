# -*- coding: utf-8 -*-
"""
`db/invariantes.sql` num Postgres efêmero — CI do worker, plano 11.1 (b) e
checklist transversal (T6/T18/T23/T24/T27 viram SQL).

Duas metades, e a segunda é a que dá valor à primeira:

  1. Banco íntegro: Postgres 16 efêmero, migrações reais (`db/migrar.py`),
     acervo sintético entrando pelo importador de verdade e publicado pelo
     passo 7 (`migracao.publicar`) → a consulta devolve ZERO linhas. Também
     como `api_ro`, o papel só-leitura com que o CI roda o mesmo SQL na stack.

  2. O guarda sabe falhar: cada invariante do arquivo é violado de propósito,
     numa transação que volta atrás, e tem de aparecer na saída — com a
     referência certa e SOZINHO (o guarda não acusa o que não foi violado).
     Os nomes são lidos do próprio `invariantes.sql`: um invariante novo sem
     caso de violação aqui quebra `test_todo_invariante_tem_caso_de_violacao`.

O SQL só enxerga `arquivos.storage_key`; a outra metade do T24 (o objeto
existe no storage e tem o sha256 gravado) é conferida aqui, no disco do
storage `fs` que o importador preencheu — e também sabe falhar.

Sem rede paga, sem chave de modelo: o legado da fábrica é produzido pelo
verificador REAL (`fabrica.auditoria_verificada`), como em test_worker_nucleo.
"""
from __future__ import annotations

import hashlib
import re
import sys
from datetime import date
from pathlib import Path

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "migracao" / "tests"))

from api.storage import Storage  # noqa: E402
from migracao import importar, plano as plano_mod, publicar  # noqa: E402
from migracao.acervo import Acervo  # noqa: E402
from tests import pg_efemero  # noqa: E402

import fabrica  # noqa: E402
from fabrica import PastaFake  # noqa: E402

INVARIANTES = (RAIZ / "db" / "invariantes.sql").read_text(encoding="utf-8")
# Cada ramo do UNION começa com `SELECT '<nome>'` no início da linha.
NOMES_NO_SQL = sorted(set(re.findall(r"^\s*SELECT\s+'([a-z_]+)'", INVARIANTES, re.M)))

C1 = "12345678000101-1-000001/2026"     # agente: leitura congelada, páginas, verificação real
C2 = "12345678000102-1-000002/2026"     # API do v2: custo conhecido, sem páginas congeladas
EDITAL_C1 = b"%PDF edital do agente"
EDITAL_C2 = b"%PDF edital da api"


def _paginas_e_respostas():
    rs = fabrica.respostas("01 - Edital.pdf")
    # Trechos longos e únicos: "trecho Q1" estaria contido em "trecho Q10".
    for r in rs:
        if r["trecho_literal"]:
            r["trecho_literal"] = ("Conforme o item %s do edital, a informação pedida consta "
                                   "deste parágrafo." % r["id"])
    texto = "\n".join(r["trecho_literal"] for r in rs if r["trecho_literal"])
    return rs, [("01 - Edital.pdf", 1, texto), ("01 - Edital.pdf", 2, "anexo sem os trechos")]


def _acervo(raiz: Path) -> Acervo:
    rs, paginas = _paginas_e_respostas()
    agente = PastaFake(
        nome="Pregão - Eletrônico - Agente-SP", controle=C1, pdfs={"01 - Edital.pdf": EDITAL_C1},
        auditoria=fabrica.auditoria_verificada("Pregão - Eletrônico - Agente-SP", rs, paginas),
        leitura_paginas=paginas, respostas_agente=rs,
        finalizado=fabrica.finalizado("Pregão - Eletrônico - Agente-SP"))
    aud_api = fabrica.auditoria_verificada("Dispensa - Api-RS", rs, paginas,
                                           modelo="claude-opus-5", agente=False)
    # Uma execução da API com custo: o importador guarda o custo legado em
    # `brl_legado` e deixa `brl` NULL (seção 9, passo 4: nunca recalculado).
    aud_api["uso"].update(chamadas=3, usd=0.9471, brl=4.83)
    api = PastaFake(nome="Dispensa - Api-RS", controle=C2, pdfs={"01 - Edital.pdf": EDITAL_C2},
                    auditoria=aud_api)
    snap, vivo = fabrica.criar(str(raiz), [agente, api])
    return Acervo(snap, vivo)


@pytest.fixture(scope="module")
def banco(tmp_path_factory):
    """Postgres efêmero migrado, acervo importado e publicado. Somente leitura para os testes:
    toda violação acontece dentro de uma transação que volta atrás."""
    raiz = tmp_path_factory.mktemp("invariantes")
    storage = Storage(str(raiz / "dados"))
    with pg_efemero.subir() as url:
        pg_efemero.migrar(url)
        acervo = _acervo(raiz)
        with psycopg.connect(url) as conn:
            importar.aplicar(conn, plano_mod.montar(acervo, hoje=date(2026, 9, 24)), acervo, storage)
        with psycopg.connect(url) as conn:
            pub = publicar.publicar(conn, storage)
        assert pub == {"publicadas": 2, "falhas": []}, pub
        yield {"url": url, "storage": storage}


def _invariantes(cur) -> list[tuple]:
    return [tuple(r) for r in cur.execute(INVARIANTES).fetchall()]


def _um(cur, sql, *args):
    return cur.execute(sql, args).fetchone()


# ------------------------------------------------------------------ 1. banco íntegro
def test_o_fixture_exercita_o_que_os_invariantes_olham(banco):
    # Zero linhas só vale se havia o que olhar: publicadas com vigente, uma
    # APROVADA com página citada, uma execução 'api' com custo, arquivos 'ok'.
    with psycopg.connect(banco["url"]) as c:
        assert _um(c, "SELECT count(*) FROM licitacoes WHERE estado = 'publicada'")[0] == 2
        assert _um(c, "SELECT count(*) FROM verificacoes WHERE vigente")[0] == 2
        assert _um(c, "SELECT count(*) FROM verificacao_respostas vr JOIN verificacoes v"
                      " ON v.id = vr.verificacao_id WHERE v.leitura_id IS NOT NULL"
                      " AND vr.veredito = 'APROVADO' AND vr.ausencia IS NULL")[0] > 0
        assert _um(c, "SELECT count(*) FROM execucoes_modelo WHERE origem = 'api'"
                      " AND brl IS NULL AND brl_legado = 4.83")[0] == 1
        assert _um(c, "SELECT count(*) FROM arquivos WHERE status = 'ok'")[0] == 2


def test_banco_integro_devolve_zero_linhas(banco):
    with psycopg.connect(banco["url"]) as c:
        assert _invariantes(c) == []


def test_o_papel_so_leitura_roda_os_invariantes(banco):
    # É como o CI roda o mesmo SQL na stack viva: sem superusuário.
    with psycopg.connect(pg_efemero.url_papel(banco["url"], "api_ro")) as c:
        assert _invariantes(c) == []


# ------------------------------------------------------------------ 2. o guarda sabe falhar
def _vigente(cur, controle):
    return _um(cur, "SELECT id, execucao_id, leitura_id FROM verificacoes"
                    " WHERE controle = %s AND vigente", controle)


def _viola_publicada_sem_vigente(cur):
    # A vigente some (um UPDATE de superusuário não passa por fn_transicao).
    cur.execute("UPDATE verificacoes SET vigente = false WHERE controle = %s", (C1,))
    return [("publicada_sem_vigente", C1, "estado=publicada, vigentes=0")]


def _viola_publicada_direto_sem_verificacao(cur):
    # Nasce publicada sem verificação nenhuma: o caminho que a 013 fecha em
    # fn_transicao, mas que um INSERT direto não atravessa.
    c3 = "12345678000103-1-000003/2026"
    cur.execute("INSERT INTO licitacoes (controle, escopo_dentro, estado) VALUES (%s, true, 'publicada')",
                (c3,))
    return [("publicada_sem_vigente", c3, "estado=publicada, vigentes=0")]


def _viola_aprovada_sem_pagina(cur):
    vid, _, leitura = _vigente(cur, C1)
    pid, arquivo = _um(cur, "SELECT pergunta_id, arquivo_canonico FROM verificacao_respostas"
                            " WHERE verificacao_id = %s AND veredito = 'APROVADO' AND ausencia IS NULL"
                            " ORDER BY pergunta_id LIMIT 1", vid)
    cur.execute("UPDATE verificacao_respostas SET pagina_final = 999"
                " WHERE verificacao_id = %s AND pergunta_id = %s", (vid, pid))
    return [("aprovada_sem_pagina", "%s/%s" % (vid, pid),
             "arquivo=%s pagina=999 leitura=%s" % (arquivo, leitura))]


def _viola_aprovada_com_pagina_de_outro_arquivo(cur):
    # A página existe, mas no texto congelado de OUTRO arquivo: nome canônico conta.
    vid, _, leitura = _vigente(cur, C1)
    pid, pagina = _um(cur, "SELECT pergunta_id, pagina_final FROM verificacao_respostas"
                           " WHERE verificacao_id = %s AND veredito = 'APROVADO' AND ausencia IS NULL"
                           " ORDER BY pergunta_id DESC LIMIT 1", vid)
    cur.execute("UPDATE verificacao_respostas SET arquivo_canonico = '99 - Outro.pdf'"
                " WHERE verificacao_id = %s AND pergunta_id = %s", (vid, pid))
    return [("aprovada_sem_pagina", "%s/%s" % (vid, pid),
             "arquivo=99 - Outro.pdf pagina=%s leitura=%s" % (pagina, leitura))]


def _viola_api_com_brl_zero(cur):
    eid = _um(cur, "SELECT id FROM execucoes_modelo WHERE origem = 'api'")[0]
    provedor, modelo = _um(cur, "SELECT provedor, modelo FROM execucoes_modelo WHERE id = %s", eid)
    # Preço conhecido é legítimo; o que o invariante caça é o zero.
    cur.execute("UPDATE execucoes_modelo SET brl = 4.83 WHERE id = %s", (eid,))
    assert _invariantes(cur) == [], "brl > 0 numa execução da API é o caso legítimo"
    cur.execute("UPDATE execucoes_modelo SET brl = 0 WHERE id = %s", (eid,))
    return [("api_com_brl_zero", str(eid), "provedor=%s modelo=%s brl=0.000" % (provedor, modelo))]


def _viola_arquivo_ok_sem_storage(cur):
    aid, nome = _um(cur, "SELECT id, nome FROM arquivos WHERE controle = %s AND status = 'ok'", C1)
    cur.execute("UPDATE arquivos SET storage_key = NULL WHERE id = %s", (aid,))
    return [("arquivo_ok_sem_storage", str(aid), "controle=%s nome=%s" % (C1, nome))]


def _viola_arquivo_ok_com_chave_vazia(cur):
    aid, nome = _um(cur, "SELECT id, nome FROM arquivos WHERE controle = %s AND status = 'ok'", C2)
    cur.execute("UPDATE arquivos SET storage_key = '' WHERE id = %s", (aid,))
    return [("arquivo_ok_sem_storage", str(aid), "controle=%s nome=%s" % (C2, nome))]


def _sem_gatilhos(cur, sql, *args):
    """
    Desde a 024 o banco RECUSA os dois contornos da T15 na hora (prova abaixo).
    O invariante continua sendo a segunda linha: quem roda com os gatilhos
    desligados (superusuário, carga em massa com session_replication_role =
    replica) ainda passa por baixo, e é isso que ele tem de pegar.
    """
    cur.execute("SAVEPOINT t15")
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute(sql, args)
    cur.execute("ROLLBACK TO SAVEPOINT t15")
    cur.execute("SET LOCAL session_replication_role = replica")
    cur.execute(sql, args)
    cur.execute("SET LOCAL session_replication_role = origin")


def _viola_simulado_vigente_por_update_da_origem(cur):
    # Vigente de execução real; a execução "vira" simulado depois.
    vid, eid, _ = _vigente(cur, C1)
    _sem_gatilhos(cur, "UPDATE execucoes_modelo SET origem = 'simulado', canonica = false WHERE id = %s", eid)
    return [("simulado_vigente_sem_ensaio", C1, "verificacao=%s origem=simulado" % vid)]


def _viola_simulado_vigente_quando_o_ensaio_acaba(cur):
    # Legítimo enquanto a licitação é ensaio (T15) — e o invariante não acusa;
    # desligar o ensaio depois deixa a vigente simulada publicada como real.
    cur.execute("UPDATE licitacoes SET ensaio = true WHERE controle = %s", (C2,))
    eid = _um(cur, "INSERT INTO execucoes_modelo (controle, origem, provedor, modelo, status, canonica)"
                   " VALUES (%s, 'simulado', 'simulado', 'simulado', 'ok', false) RETURNING id", C2)[0]
    vid = _um(cur, "INSERT INTO verificacoes (execucao_id, controle, versao_regras)"
                   " VALUES (%s, %s, 'ci-ensaio') RETURNING id", eid, C2)[0]
    cur.execute("UPDATE verificacoes SET vigente = false WHERE controle = %s AND vigente", (C2,))
    cur.execute("UPDATE verificacoes SET vigente = true WHERE id = %s", (vid,))
    assert _invariantes(cur) == [], "ensaio=true com simulado vigente é o caso legítimo (T15)"
    _sem_gatilhos(cur, "UPDATE licitacoes SET ensaio = false WHERE controle = %s", C2)
    return [("simulado_vigente_sem_ensaio", C2, "verificacao=%s origem=simulado" % vid)]


CASOS = {
    "publicada_sem_vigente: vigente desligada": _viola_publicada_sem_vigente,
    "publicada_sem_vigente: publicada direto, sem verificação": _viola_publicada_direto_sem_verificacao,
    "aprovada_sem_pagina: página inexistente": _viola_aprovada_sem_pagina,
    "aprovada_sem_pagina: página de outro arquivo": _viola_aprovada_com_pagina_de_outro_arquivo,
    "api_com_brl_zero: preço esquecido": _viola_api_com_brl_zero,
    "arquivo_ok_sem_storage: chave nula": _viola_arquivo_ok_sem_storage,
    "arquivo_ok_sem_storage: chave vazia": _viola_arquivo_ok_com_chave_vazia,
    "simulado_vigente_sem_ensaio: origem trocada depois": _viola_simulado_vigente_por_update_da_origem,
    "simulado_vigente_sem_ensaio: ensaio desligado depois": _viola_simulado_vigente_quando_o_ensaio_acaba,
}


def test_todo_invariante_tem_caso_de_violacao():
    assert NOMES_NO_SQL, "nenhum `SELECT '<nome>'` achado em db/invariantes.sql"
    cobertos = {k.split(":", 1)[0] for k in CASOS}
    assert cobertos == set(NOMES_NO_SQL), (
        "invariantes.sql tem %s; casos de violação cobrem %s" % (NOMES_NO_SQL, sorted(cobertos)))


@pytest.mark.parametrize("caso", list(CASOS), ids=list(CASOS))
def test_cada_violacao_aparece_sozinha_na_saida(banco, caso):
    with psycopg.connect(banco["url"]) as conn:
        with conn.transaction(force_rollback=True):
            with conn.cursor() as cur:
                esperado = CASOS[caso](cur)
                obtido = _invariantes(cur)
        # A transação voltou atrás: o banco segue íntegro para o próximo caso.
        assert _invariantes(conn) == []
    assert obtido == esperado


def test_o_upsert_direto_de_vigente_simulada_ainda_e_barrado_pelo_trigger(banco):
    # O invariante é a rede de baixo; o trigger (T15) é a de cima e continua de pé.
    with psycopg.connect(banco["url"]) as conn:
        with conn.transaction(force_rollback=True):
            eid = _um(conn, "INSERT INTO execucoes_modelo (controle, origem, status, canonica)"
                            " VALUES (%s, 'simulado', 'ok', false) RETURNING id", C1)[0]
            conn.execute("UPDATE verificacoes SET vigente = false WHERE controle = %s", (C1,))
            with pytest.raises(psycopg.errors.RaiseException, match="T15"):
                with conn.transaction():
                    conn.execute("INSERT INTO verificacoes (execucao_id, controle, versao_regras, vigente)"
                                 " VALUES (%s, %s, 'ci', true)", (eid, C1))


# ------------------------------------------------------------------ T24 no storage
def _objetos_divergentes(conn, storage: Storage) -> list[tuple]:
    """Todo `arquivos.status='ok'` tem objeto no storage com o sha256 gravado."""
    ruins = []
    for aid, chave, sha in conn.execute(
            "SELECT id, storage_key, sha256 FROM arquivos WHERE status = 'ok' ORDER BY id").fetchall():
        if not chave or not storage.existe(chave):
            ruins.append((aid, "sem objeto"))
        elif hashlib.sha256(storage.get(chave)).hexdigest() != sha:
            ruins.append((aid, "sha diverge"))
    return ruins


def test_todo_arquivo_ok_tem_objeto_com_o_sha_gravado(banco):
    with psycopg.connect(banco["url"]) as c:
        assert _objetos_divergentes(c, banco["storage"]) == []


def test_objeto_adulterado_ou_sumido_aparece(banco):
    storage = banco["storage"]
    with psycopg.connect(banco["url"]) as c:
        (a1, k1), (a2, k2) = c.execute("SELECT id, storage_key FROM arquivos WHERE status = 'ok'"
                                       " ORDER BY id").fetchall()
        p1, p2 = Path(storage.caminho(k1)), Path(storage.caminho(k2))
        original1, original2 = p1.read_bytes(), p2.read_bytes()
        try:
            p1.write_bytes(original1 + b" adulterado")    # direto no disco: put() recusaria
            p2.unlink()
            assert _objetos_divergentes(c, storage) == [(a1, "sha diverge"), (a2, "sem objeto")]
        finally:
            p1.write_bytes(original1)
            p2.write_bytes(original2)
        assert _objetos_divergentes(c, storage) == []
