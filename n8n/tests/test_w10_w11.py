# -*- coding: utf-8 -*-
"""
W10 Fila e W11 Ações do site na instância real (fopa-n8n 127.0.0.1:5679) e no
Postgres de dev (127.0.0.1:5433). Sem mock, como os outros testes do n8n: o que
quebra no n8n (bigint que volta como texto, `$execution.mode` que não é o que o
nome diz, sub-fluxo sem esperar) só a instância mostra.

O que se prova:
  0. os JSON seguem as convenções; a agenda do W10 está DESLIGADA;
  1. o W10 devolve o lease vencido (baixando -> falha_rede, com backoff) e
     reivindica respeitando lease vivo, escopo, recorte de 2026, reserva da
     demo e prazo; dispara um W20 por reivindicada, sem esperar;
  2. disjuntor aberto -> UM e-mail (não um por rodada) e nada reivindicado;
  3. fopa/verificar -> 202 {execucao_id} rápido; a linha existe e o W01 a usa;
  4. fopa/processar -> 422 no formato ruim; aceita/recusa pelo db/022; forcar
     reabre o terminal; compra desconhecida é buscada no PNCP e registrada;
     reservada + forcar vai direto ao W20 (sem passar pela fila);
  5. fopa/reverificar -> 202 e UMA linha em execucoes_workflow; numa licitação
     de teste publicada de verdade (W23 + W24, simulado, ensaio) e envelhecida
     à mão: /reverificar -> W24 modo republicar troca a vigente (e-mail
     'republicada' com o diff); 409 "já verificada" retoma a verificação que
     ficou sem republicar; nada pendente = pulada. Sem vigente = linha 'erro';
  6. sem X-FOPA-Token (ou com o errado) -> 403, e nada roda;
  7. fopa/importar-respostas (ADR-014, custo zero): formato ruim, licitação
     desconhecida, sem leitura, em curso, com lease de outro fluxo e resposta
     que o worker recusa voltam 409/422 com o motivo e NADA muda; numa
     `preparada` as 17 respostas do agente viram execução `agente` →
     extraindo → respondida → W24 publicar (vigente, e-mail, lease solto, uma
     linha W11); importar de novo na publicada = o worker verifica e o W24
     republica.

NENHUMA LICITAÇÃO REAL É TOCADA. A estratégia:
  - tudo o que o teste cria tem controle 00000000000000-1-0009[5-9]x/2026
    (CNPJ zerado: o PNCP responde 400 e o W21 falha em 0,1 s sem baixar nada),
    `ensaio = true`, e é apagado no fim com eventos, e-mails e as linhas
    W10/W11/W20 que gerou;
  - a fila real (centenas em `preparada`, prioridade 0) nunca é alcançada: o
    W10 reivindica no máximo 4 - extraindo, por prioridade DESC. Antes de CADA
    rodada que pode chegar ao fn_reivindicar o teste põe uma ALMOFADA de 4
    licitações de teste elegíveis com prioridade 50: elas ocupam todas as
    vagas. O `orcamento` vigente NÃO é mexido (o site e outros testes o leem).
    E o teste confere, pela linha do próprio W10, que só controles de teste
    foram reivindicados;
  - as ARMADILHAS (lease vivo, fora do escopo, fora do recorte, reservada,
    prazo vencido) têm prioridade 60, ACIMA da almofada: se a regra falhasse,
    seriam elas as escolhidas;
  - o W20 disparado roda de verdade (W21 -> PNCP 400 -> falha_rede); as linhas
    'erro' do W20 que isso gera são apagadas logo em seguida, para não abrir o
    disjuntor de verdade;
  - o "Verificar agora" (test_3) roda o W01 seco de verdade (lê o PNCP, não
    grava licitação): a linha W01 que o W11 abre e as buscas/buscas_paginas
    que o W01 grava nela são apagadas no fim, numa transação;
  - a compra desconhecida é real (15126437000305-1-003711/2026, agulhas e
    seringas do CHC/UFPR, fora da folha): só leitura grátis na API de consulta
    do PNCP; a linha que o W11 grava é apagada no fim;
  - antes de rodar o W10 o teste confere que nenhuma licitação real tem lease
    vencido (o W10 a devolveria), que nenhuma real tem prioridade >= 50 e que o
    provedor é de custo zero.

O disjuntor conta TODAS as linhas W20 dos últimos 30 min: se outra frente
rodou um W20 com sucesso nesse intervalo, ele não abre. O teste 2 espera até
FOPA_ESPERA_DISJUNTOR_S segundos (padrão 0) e, se a janela não limpar, é
PULADO com o motivo.

NÃO rode junto com test_w01.py (o fopa/verificar abre uma linha W01 e o
test_w01 conta as linhas W01) nem com test_nucleo.py (os dois disparam o W20).

    python -m pytest n8n/tests/test_w10_w11.py -v -s
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

import cliente  # noqa: E402
import executar  # noqa: E402
import importar  # noqa: E402

psycopg = pytest.importorskip("psycopg")
from psycopg.rows import dict_row  # noqa: E402

W10, W11 = "W10 Fila", "W11 Ações do site"
# Os Execute do W11 que ESPERAM o sub-fluxo: o site já recebeu o 202 e a linha do fim registra o que o W24 fez.
ESPERAM_O_W24 = {"Republicar (W24)", "Publicar a importada (W24)", "Republicar a importada (W24)"}
# FOPA_W10_JSON / FOPA_W11_JSON apontam o rascunho durante a construção; o padrão é o versionado.
ARQ_W10 = Path(os.environ.get("FOPA_W10_JSON") or importar.PASTA_WORKFLOWS / "W10.json")
ARQ_W11 = Path(os.environ.get("FOPA_W11_JSON") or importar.PASTA_WORKFLOWS / "W11.json")

QUEM = "test_w10_w11"
# 000950-000999: o test_nucleo usa 000920/000921; nada daqui encosta neles.
TODOS = ["00000000000000-1-%06d/2026" % n for n in range(950, 1000)]
_livres = iter(TODOS)
DESCONHECIDA_REAL = "15126437000305-1-003711/2026"
ASSUNTO_DISJUNTOR = "[FOPA][FILA] disjuntor aberto: 3+ falhas do W20 em 30 min"
ESPERA_DISJUNTOR = int(os.environ.get("FOPA_ESPERA_DISJUNTOR_S") or 0)
PRIO_ALMOFADA, PRIO_ARMADILHA = 50, 60
TIMEOUT_SITE = 15.0            # api/site.py TIMEOUT_N8N: o site desiste do webhook depois disto


def novo() -> str:
    return next(_livres)


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def pg():
    env = cliente.ler_env()
    url = "postgresql://postgres:%s@127.0.0.1:5433/fopa" % env["POSTGRES_PASSWORD"]
    try:
        con = psycopg.connect(url, connect_timeout=5, autocommit=True, row_factory=dict_row)
    except psycopg.OperationalError:
        pytest.skip("fopa-postgres fora do ar em 127.0.0.1:5433")
    yield con
    con.close()


@pytest.fixture(scope="module")
def api():
    if not cliente.no_ar():
        pytest.skip("fopa-n8n fora do ar em %s (docker compose up -d fopa-n8n)" % cliente.base())
    return cliente.N8n.autenticado()


@pytest.fixture(scope="module")
def token():
    t = cliente.ler_env().get("FOPA_SITE_TOKEN")
    if not t:
        pytest.skip("FOPA_SITE_TOKEN vazio em docker/.env")
    return Segredo(t)


class Segredo(str):
    """O valor vai no header; o repr (que o pytest mostra nos argumentos de um teste que falha) não."""

    def __repr__(self):
        return "<FOPA_SITE_TOKEN oculto>"

    __str__ = __repr__

    def valor(self) -> str:
        return str.__str__(self)


def _pasta_w10_w11() -> Path:
    d = Path(tempfile.mkdtemp(prefix="w10w11_"))
    shutil.copy(ARQ_W10, d / "W10.json")
    shutil.copy(ARQ_W11, d / "W11.json")
    return d


@pytest.fixture(scope="module")
def instalado(api, pg):
    """Sobe SÓ o W10 e o W11 (os outros fluxos são de outras frentes); limpa sobras antes e tudo no fim."""
    for a in (ARQ_W10, ARQ_W11):
        if not a.exists():
            pytest.skip("%s não existe" % a)
    rel = importar.importar(_pasta_w10_w11(), api)
    assert rel[W10]["publicado"] is True and rel[W11]["publicado"] is True, rel
    inicio = agora(pg)
    apagar_tudo(pg, inicio)
    yield {"w10": rel[W10]["id"], "w11": rel[W11]["id"], "inicio": inicio}
    esperar_ociosa(pg, inicio)
    apagar_tudo(pg, inicio)


@pytest.fixture(autouse=True)
def limpo(request):
    """Cada teste começa sem licitação de teste na fila: a almofada de um não vira candidata do outro."""
    yield
    if "instalado" in request.fixturenames:
        pg, inst = request.getfixturevalue("pg"), request.getfixturevalue("instalado")
        esperar_ociosa(pg, inst["inicio"])
        apagar_tudo(pg, inst["inicio"])


# ------------------------------------------------------------------ ajudantes
def agora(pg):
    return pg.execute("SELECT now() AS t").fetchone()["t"]


def criar(pg, controle: str, **campos) -> str:
    """Licitação de TESTE (ensaio, CNPJ zerado). Padrão: elegível para a fila, prioridade da almofada."""
    t = agora(pg)
    base = {"ano": 2026, "seq": int(controle.split("-")[2].split("/")[0]), "orgao": "TESTE %s (apagar)" % QUEM,
            "uf": "SP", "municipio": "Teste", "modalidade": "Pregão - Eletrônico",
            "objeto": "TESTE %s: contratação de banco para a folha de pagamento" % QUEM,
            "situacao": "Divulgada no PNCP", "publicado_em": dt.date(2026, 9, 1),
            "fim_prazo": t + dt.timedelta(days=10), "escopo_dentro": True, "escopo_motivo": "teste",
            "escopo_versao": "teste", "estado": "nova", "prioridade": PRIO_ALMOFADA, "ensaio": True,
            "origem": "manual", "lease_por": None, "lease_ate": None, "reserva_demo": False, "tentativas": 0}
    base.update(campos)
    cols = list(base)
    vals = ["%s::estado_licitacao" if c == "estado" else "%s" for c in cols]
    pg.execute("INSERT INTO licitacoes (controle, %s) VALUES (%%s, %s)" % (", ".join(cols), ", ".join(vals)),
               [controle] + [base[c] for c in cols])
    return controle


def almofada(pg, n: int = 4) -> list:
    """4 elegíveis de teste com prioridade 50: ocupam todas as vagas do fn_reivindicar (4 - extraindo)."""
    return [criar(pg, novo(), objeto="TESTE %s: almofada da fila (folha de pagamento)" % QUEM) for _ in range(n)]


def lic(pg, controle: str) -> dict | None:
    return pg.execute("SELECT * FROM licitacoes WHERE controle = %s", (controle,)).fetchone()


def guardas_da_fila(pg) -> int:
    """O W10 só roda se nada real puder ser tocado. Devolve quantas estão em 'extraindo' agora."""
    prov = pg.execute("SELECT valor #>> '{}' AS v FROM configuracao WHERE chave = 'provedor'").fetchone()
    if not prov or prov["v"] not in ("simulado", "gravado"):
        pytest.fail("configuracao.provedor = %r: o W20 poderia gastar; este teste só roda com simulado/gravado"
                    % (prov and prov["v"]))
    vencidas = [r["controle"] for r in pg.execute(
        "SELECT controle FROM licitacoes WHERE lease_por IS NOT NULL AND lease_ate < now() "
        "AND NOT (controle = ANY(%s))", (TODOS,)).fetchall()]
    if vencidas:
        pytest.skip("licitação REAL com lease vencido (%s): o W10 a devolveria; não rodo" % vencidas[:3])
    altas = pg.execute("SELECT count(*) AS n FROM licitacoes WHERE prioridade >= %s AND NOT (controle = ANY(%s))",
                       (PRIO_ALMOFADA, TODOS)).fetchone()["n"]
    if altas:
        pytest.skip("%d licitação(ões) real(is) com prioridade >= %d: a almofada não as protegeria" % (altas, PRIO_ALMOFADA))
    extraindo = pg.execute("SELECT count(*) AS n FROM licitacoes WHERE estado = 'extraindo'").fetchone()["n"]
    if extraindo >= 4:
        pytest.skip("4 licitações em 'extraindo' agora: o W10 não tem vaga para reivindicar")
    return extraindo


def post(caminho: str, corpo: dict, token: str | None) -> tuple[int, object, float]:
    h = {"Content-Type": "application/json"}
    if token is not None:
        h["X-FOPA-Token"] = token.valor() if isinstance(token, Segredo) else token
    req = urllib.request.Request("%s/webhook/%s" % (cliente.base(), caminho), data=json.dumps(corpo).encode("utf-8"),
                                 headers=h, method="POST")
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status, txt = r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        status, txt = e.code, e.read().decode("utf-8", "replace")
    dur = time.monotonic() - t
    try:
        return status, json.loads(txt), dur
    except ValueError:
        return status, txt, dur


def ultimo_id_n8n(api) -> int:
    d = api.publica("GET", "/executions?limit=1").get("data") or []
    return int(d[0]["id"]) if d else 0


def execucoes_n8n(api, wid: str, depois_de: int) -> list:
    d = api.publica("GET", "/executions?workflowId=%s&limit=50" % wid).get("data") or []
    return sorted(({"id": e["id"], "status": e["status"], "mode": e["mode"]} for e in d if int(e["id"]) > depois_de),
                  key=lambda e: int(e["id"]))


def rodar_w10(api) -> dict:
    """W10 pelo gatilho Manual (a mesma rodada feita à mão), com a saída de cada nó."""
    r = executar.executar(W10, timeout=120, api=api, com_saidas=True)
    assert r["status"] == "success", "W10 %s terminou %s: %s" % (r["id"], r["status"], r["erro"])
    return r


def linha_w10(pg, n8n_id: str) -> dict:
    return pg.execute("SELECT * FROM execucoes_workflow WHERE workflow = 'W10' AND n8n_execution_id = %s",
                      (str(n8n_id),)).fetchone()


def esperar(cond, timeout: float, passo: float = 2.0, oque: str = ""):
    limite = time.monotonic() + timeout
    while True:
        v = cond()
        if v:
            return v
        if time.monotonic() > limite:
            raise AssertionError("não aconteceu em %d s: %s" % (timeout, oque))
        time.sleep(passo)


def esperar_w20(pg, controles, desde, timeout: float = 180) -> list:
    """Cada controle com a sua linha W20 TERMINADA desde `desde` (o W10/W11 não esperam; o teste espera)."""
    controles = set(controles)

    def pronto():
        linhas = pg.execute(
            "SELECT id, controle, status, gatilho, n8n_execution_id, argumentos, erro FROM execucoes_workflow "
            "WHERE workflow = 'W20' AND controle = ANY(%s) AND iniciado_em >= %s ORDER BY id",
            (list(controles), desde)).fetchall()
        feitos = {x["controle"] for x in linhas if x["status"] != "em_curso"}
        if controles <= feitos and all(x["status"] != "em_curso" for x in linhas):
            return linhas
        return None
    return esperar(pronto, timeout, oque="W20 de %s" % sorted(controles))


def esperar_w10_subfluxo(pg, desde, timeout: float = 120) -> dict:
    def pronto():
        x = pg.execute("SELECT * FROM execucoes_workflow WHERE workflow = 'W10' AND gatilho = 'subfluxo' "
                       "AND iniciado_em >= %s ORDER BY id DESC LIMIT 1", (desde,)).fetchone()
        return x if x and x["status"] != "em_curso" else None
    return esperar(pronto, timeout, oque="o W10 chamado pelo W11")


def esperar_ociosa(pg, inicio, timeout: float = 180):
    """Nenhum W10/W20 de teste em curso nem lease de fluxo nas licitações de teste (fora as armadilhas 'W20:teste-')."""
    def ociosa():
        leases = pg.execute("SELECT count(*) AS n FROM licitacoes WHERE controle = ANY(%s) AND lease_por IS NOT NULL "
                            "AND lease_por NOT LIKE 'W20:teste-%%'", (TODOS,)).fetchone()["n"]
        curso = pg.execute("SELECT count(*) AS n FROM execucoes_workflow WHERE status = 'em_curso' AND iniciado_em >= %s "
                           "AND (controle = ANY(%s) OR workflow = 'W10')", (inicio, TODOS)).fetchone()["n"]
        return leases == 0 and curso == 0
    esperar(ociosa, timeout, oque="fila de teste ociosa")


def apagar_w20_de_teste(pg):
    """As linhas 'erro' do W20 de teste alimentariam o disjuntor REAL: saem logo depois de conferidas."""
    pg.execute("DELETE FROM execucoes_workflow WHERE workflow = 'W20' AND controle = ANY(%s)", (TODOS,))


def apagar_fundo(pg, controles: list) -> None:
    """Tudo o que o W23/W24/W11 gravam de uma licitação de TESTE publicada (o _limpar do test_nucleo), antes da
    própria licitação. Só controles de CNPJ zerado; o RELATORIO que o /render gravou no storage vai junto."""
    assert all(c.startswith("00000000000000-") for c in controles), controles
    com_fundo = [r["controle"] for r in pg.execute(
        "SELECT controle FROM licitacoes WHERE controle = ANY(%s) AND (leitura_vigente_id IS NOT NULL OR EXISTS "
        "(SELECT 1 FROM verificacoes v WHERE v.controle = licitacoes.controle) OR EXISTS "
        "(SELECT 1 FROM execucoes_modelo e WHERE e.controle = licitacoes.controle))", (controles,)).fetchall()]
    if not com_fundo:
        return
    c = (com_fundo,)
    with pg.transaction():
        pg.execute("UPDATE licitacoes SET leitura_vigente_id = NULL, gemea_de = NULL WHERE controle = ANY(%s)", c)
        pg.execute("DELETE FROM revisoes_humanas WHERE controle = ANY(%s)", c)
        pg.execute("DELETE FROM sinais_jev WHERE controle = ANY(%s)", c)
        pg.execute("DELETE FROM publicacoes WHERE controle = ANY(%s)", c)
        pg.execute("DELETE FROM verificacao_respostas WHERE verificacao_id IN "
                   "(SELECT id FROM verificacoes WHERE controle = ANY(%s))", c)
        pg.execute("DELETE FROM verificacoes WHERE controle = ANY(%s)", c)
        pg.execute("DELETE FROM respostas WHERE execucao_id IN (SELECT id FROM execucoes_modelo WHERE controle = ANY(%s))", c)
        pg.execute("DELETE FROM chamadas_modelo WHERE execucao_id IN "
                   "(SELECT id FROM execucoes_modelo WHERE controle = ANY(%s))", c)
        pg.execute("DELETE FROM execucoes_modelo WHERE controle = ANY(%s)", c)
        pg.execute("DELETE FROM paginas WHERE leitura_id IN (SELECT id FROM leituras WHERE controle = ANY(%s))", c)
        pg.execute("DELETE FROM leituras WHERE controle = ANY(%s)", c)
        for tabela in ("arquivos", "itens_api", "jobs"):
            pg.execute("DELETE FROM %s WHERE controle = ANY(%%s)" % tabela, c)
    if shutil.which("docker"):
        for controle in com_fundo:
            subprocess.run(["docker", "exec", "fopa-worker", "rm", "-rf", "--",
                            "/dados/html/" + controle.replace("/", "-")], capture_output=True, timeout=60)


def apagar_verificar_agora(pg, inicio) -> None:
    """As linhas W01 que o "Verificar agora" deste teste abriu (gatilho site, solicitado_por = QUEM), com as
    buscas e buscas_paginas que o W01 seco gravou nelas — filhas primeiro, numa transação."""
    ids = [r["id"] for r in pg.execute(
        "SELECT id FROM execucoes_workflow WHERE workflow = 'W01' AND gatilho = 'site' "
        "AND argumentos ->> 'solicitado_por' = %s AND iniciado_em >= %s AND status <> 'em_curso'",
        (QUEM, inicio)).fetchall()]
    if ids:
        with pg.transaction():
            pg.execute("DELETE FROM buscas_paginas WHERE workflow_execucao_id = ANY(%s)", (ids,))
            pg.execute("DELETE FROM buscas WHERE workflow_execucao_id = ANY(%s)", (ids,))
            pg.execute("DELETE FROM execucoes_workflow WHERE id = ANY(%s)", (ids,))


def apagar_tudo(pg, inicio):
    todos = TODOS + [DESCONHECIDA_REAL]
    # A desconhecida real só sai se foi ESTE teste que a gravou (origem n8n, criada depois do início).
    real = pg.execute("SELECT 1 FROM licitacoes WHERE controle = %s AND origem = 'n8n' AND criado_em >= %s",
                      (DESCONHECIDA_REAL, inicio)).fetchone()
    alvo = TODOS + ([DESCONHECIDA_REAL] if real else [])
    apagar_fundo(pg, TODOS)          # antes das linhas de execução: execucoes_modelo aponta para elas
    pg.execute("DELETE FROM emails WHERE controle = ANY(%s) OR (assunto = %s AND em >= %s)",
               (alvo, ASSUNTO_DISJUNTOR, inicio))
    pg.execute("DELETE FROM execucoes_workflow WHERE controle = ANY(%s)", (alvo,))
    pg.execute("DELETE FROM execucoes_workflow WHERE workflow = 'W11' AND argumentos ->> 'controle' = ANY(%s)", (todos,))
    # Ninguém mais dispara o W10 (a agenda está desligada): as linhas W10 desde o início são deste teste.
    pg.execute("DELETE FROM execucoes_workflow WHERE workflow = 'W10' AND iniciado_em >= %s", (inicio,))
    apagar_verificar_agora(pg, inicio)
    for tabela in ("revisoes_humanas", "sinais_jev", "licitacao_eventos", "arquivos"):
        pg.execute("DELETE FROM %s WHERE controle = ANY(%%s)" % tabela, (alvo,))
    pg.execute("DELETE FROM licitacoes WHERE controle = ANY(%s)", (alvo,))


# ------------------------------------------------------------------ 0. os JSON
def _nos(arq: Path) -> tuple[dict, dict]:
    wf = json.loads(arq.read_text(encoding="utf-8"))
    return wf, {n["name"]: n for n in wf["nodes"]}


def test_0_json_convencoes_e_agenda_das_6h():
    for a in (ARQ_W10, ARQ_W11):
        if not a.exists():
            pytest.skip("%s não existe" % a)
    w10, n10 = _nos(ARQ_W10)
    w11, n11 = _nos(ARQ_W11)
    assert w10["name"] == W10 and w11["name"] == W11
    for wf in (w10, w11):
        s = wf["settings"]
        assert s["executionOrder"] == "v1" and s["timezone"] == "America/Sao_Paulo"
        assert s["errorWorkflow"] == "{{WF:W90}}", "%s é raiz: o erro vai ao W90" % wf["name"]
        bruto = json.dumps(wf, ensure_ascii=False).lower()
        assert "anthropic" not in bruto and "openai" not in bruto
        for n in wf["nodes"]:
            for ref in (n.get("credentials") or {}).values():
                assert ref["id"] == "{{CRED:%s}}" % ref["name"], n["name"]
            if n["type"] == "n8n-nodes-base.postgres":
                assert n["credentials"]["postgres"]["name"] == "fopa-postgres (n8n_rw)"
            if n["type"] == "n8n-nodes-base.executeWorkflow" and n["name"] not in ESPERAM_O_W24:
                assert n["parameters"]["options"]["waitForSubWorkflow"] is False, "%s espera o sub-fluxo" % n["name"]
        notas = [n["parameters"]["content"] for n in wf["nodes"] if n["type"] == "n8n-nodes-base.stickyNote"]
        assert any("regra —" in c and ".py:" in c for c in notas), wf["name"]

    # W10 ligado em 24/09/2026: a fila de extração roda sozinha todo dia de manhã,
    # a cada 10 min das 6h às 7h50 (4 por rodada). Sem provedor real ela só baixa e lê (db/032).
    agenda = n10["Todo dia às 6h (a cada 10 min até 7h50)"]
    assert agenda["parameters"]["rule"]["interval"][0]["expression"] == "*/10 6-7 * * *"
    assert agenda.get("disabled") is not True, "a agenda do W10 roda todo dia às 6h"
    assert "rodou('Todo dia às 6h (a cada 10 min até 7h50)')" in n10["Abrir execução"]["parameters"]["options"]["queryReplacement"]
    assert n10["Chamado por outro fluxo"]["parameters"]["inputSource"] == "passthrough"
    assert "Manual" in n10
    # A regra é do banco; o gatilho sai do canvas, não de $execution.mode ('test'/'production' no 2.x).
    assert "fn_liberar_leases_vencidos()" in n10["Liberar leases vencidos"]["parameters"]["query"]
    assert "fn_disjuntor_w20_aberto()" in n10["Disjuntor e orçamento"]["parameters"]["query"]
    reiv = n10["Reivindicar"]["parameters"]
    assert "fn_reivindicar(" in reiv["query"] and "'agenda'" in reiv["query"]
    assert "$execution.mode" not in json.dumps(w10), "no n8n 2.x $execution.mode é só test/production"
    assert "isExecuted" in n10["Abrir execução"]["parameters"]["options"]["queryReplacement"]
    w20 = n10["Disparar W20 (sem esperar)"]["parameters"]
    assert w20["workflowId"]["value"] == "{{WF:W20}}" and w20["mode"] == "each"
    assert set(w20["workflowInputs"]["value"]) == {"controle", "forcar"} and w20["workflowInputs"]["value"]["forcar"] is False

    # W11: quatro webhooks com X-FOPA-Token (credencial 'site'), respondendo por nó.
    ganchos = {n["parameters"]["path"]: n for n in n11.values() if n["type"] == "n8n-nodes-base.webhook"}
    assert set(ganchos) == {"fopa/verificar", "fopa/processar", "fopa/reverificar", "fopa/importar-respostas"}
    for g in ganchos.values():
        p = g["parameters"]
        assert p["httpMethod"] == "POST" and p["authentication"] == "headerAuth" and p["responseMode"] == "responseNode"
        assert g["credentials"]["httpHeaderAuth"]["name"] == "site"
    codigos = sorted(n["parameters"]["options"]["responseCode"] for n in n11.values()
                     if n["type"] == "n8n-nodes-base.respondToWebhook")
    # importar-respostas: 202, e as recusas com motivo — 409 (estado), 422 (formato, desconhecida, respostas), 502
    assert codigos == [202, 202, 202, 202, 409, 422, 422, 422, 422, 502]
    w01 = n11["W01 seco (sem esperar)"]["parameters"]
    assert w01["workflowId"]["value"] == "{{WF:W01}}"
    assert w01["workflowInputs"]["value"]["seco"] is True and "Number(" in w01["workflowInputs"]["value"]["execucao_id"]
    assert n11["W10 (sem esperar)"]["parameters"]["workflowId"]["value"] == "{{WF:W10}}"
    direto = n11["W20 direto, forcar (sem esperar)"]["parameters"]
    assert direto["workflowId"]["value"] == "{{WF:W20}}" and direto["workflowInputs"]["value"]["forcar"] is True
    assert "fn_pedir_processamento(" in n11["Pedir processamento (db/022)"]["parameters"]["query"]
    assert "fn_registrar_vista(" in n11["Registrar a compra (db/020)"]["parameters"]["query"]
    for nome in ("Pedir processamento (db/022)", "Registrar a compra (db/020)"):
        assert n11[nome]["parameters"]["options"]["queryBatching"] == "independently"
    pncp = n11["Buscar a compra no PNCP"]
    assert pncp["parameters"]["url"].startswith("={{ 'https://pncp.gov.br/api/consulta/v1/orgaos/'")
    assert pncp["parameters"]["options"]["response"]["response"] == {"fullResponse": True, "neverError": True}
    assert pncp["onError"] == "continueRegularOutput"
    for nome in ("Escopo (worker)", "POST /reverificar no worker", "GET /versao (retomada)",
                 "POST /importar-respostas no worker"):
        assert n11[nome]["credentials"]["httpHeaderAuth"]["name"] == "worker"
    # reverificar: 202 ANTES do trabalho; /reverificar -> W24 modo republicar (o único Execute que espera: o site já
    # tem a resposta); 409 'já foi verificada' -> retomada; tudo termina numa linha só.
    lig = w11["connections"]
    seguinte = lambda a, i=0: [c["node"] for c in lig[a]["main"][i]]  # noqa: E731
    assert seguinte("POST fopa/reverificar") == ["Pedido (reverificar)"]
    assert seguinte("Pedido (reverificar)") == ["Responder 202 (reverificar)"]
    assert seguinte("Responder 202 (reverificar)") == ["POST /reverificar no worker"]
    assert seguinte("POST /reverificar no worker") == ["Reverificou?"]
    assert [seguinte("Reverificou?", i) for i in range(3)] == [["Republicar (W24)"], ["GET /versao (retomada)"],
                                                              ["Resultado da reverificação"]]
    assert [seguinte("Achou a verificação?", i) for i in range(2)] == [["Republicar (W24)"],
                                                                      ["Resultado da reverificação"]]
    assert seguinte("Republicar (W24)") == ["Resultado da reverificação"]
    assert seguinte("Resultado da reverificação") == ["Registrar a reverificação"]
    regras = n11["Reverificou?"]["parameters"]["rules"]["values"]
    assert "statusCode === 409" in regras[1]["conditions"]["conditions"][0]["leftValue"]
    assert "já foi verificada" in regras[1]["conditions"]["conditions"][0]["leftValue"]
    rep = n11["Republicar (W24)"]
    assert rep["parameters"]["workflowId"]["value"] == "{{WF:W24}}" and rep["parameters"]["mode"] == "once"
    assert rep["parameters"]["options"]["waitForSubWorkflow"] is True and rep["onError"] == "continueRegularOutput"
    assert rep["parameters"]["workflowInputs"]["value"]["modo"] == "republicar"
    assert "vig.vigente AND vig.execucao_id = v.execucao_id" in n11["Verificação já gravada"]["parameters"]["query"]
    reg = n11["Registrar a reverificação"]["parameters"]["query"]
    assert reg.count("INSERT INTO execucoes_workflow") == 1 and "'W11'" in reg and "custo_brl" in reg

    # importar-respostas: nada muda antes de o worker aceitar; 202 logo depois dele; primeira extração pelo fim do
    # W23 (lease do W11 → extraindo → respondida → W24 publicar), publicada → W24 republicar; uma linha no fim.
    assert seguinte("POST fopa/importar-respostas") == ["Pedido (importar)"]
    assert [seguinte("Importação válida?", i) for i in range(2)] == [["Estado para importar"], ["Responder 422 (importar)"]]
    assert [seguinte("Pode importar?", i) for i in range(3)] == [
        ["POST /importar-respostas no worker"], ["Responder 409 (importar)"], ["Responder 422 (desconhecida)"]]
    assert [seguinte("Importou?", i) for i in range(3)] == [
        ["Responder 202 (importar)"], ["Responder 422 (respostas)"], ["Responder 502 (worker)"]]
    assert seguinte("Responder 202 (importar)") == ["Primeira extração?"]
    assert [seguinte("Primeira extração?", i) for i in range(2)] == [["Lease e → extraindo"],
                                                                    ["Republicar a importada (W24)"]]
    assert [seguinte("Tomou o lease?", i) for i in range(2)] == [["→ respondida"], ["Resultado da importação"]]
    assert seguinte("→ respondida") == ["Publicar a importada (W24)"]
    for nome in ("Publicar a importada (W24)", "Republicar a importada (W24)"):
        assert seguinte(nome) == ["Resultado da importação"]
        p = n11[nome]["parameters"]
        assert p["workflowId"]["value"] == "{{WF:W24}}" and p["options"]["waitForSubWorkflow"] is True
        assert n11[nome]["onError"] == "continueRegularOutput"
    assert n11["Publicar a importada (W24)"]["parameters"]["workflowInputs"]["value"]["modo"] == "publicar"
    assert n11["Republicar a importada (W24)"]["parameters"]["workflowInputs"]["value"]["modo"] == "republicar"
    assert seguinte("Resultado da importação") == ["Soltar o lease e registrar"]
    estado = n11["Estado para importar"]
    assert estado["alwaysOutputData"] is True and "UPDATE" not in estado["parameters"]["query"].upper()
    trans = n11["Lease e → extraindo"]["parameters"]["query"] + n11["→ respondida"]["parameters"]["query"]
    assert "fn_transicao(l.controle, 'extraindo'" in trans and "fn_transicao($1, 'respondida'" in trans
    assert "'W11:' || $2" in trans and "lease_ate < now()" in trans
    assert "verificar: $json.modo === 'republicar'" in n11["POST /importar-respostas no worker"]["parameters"]["jsonBody"]
    soltar = n11["Soltar o lease e registrar"]["parameters"]["query"]
    assert "lease_por = 'W11:' || $1" in soltar and soltar.count("INSERT INTO execucoes_workflow") == 1


def test_0_instancia_igual_ao_versionado(api, instalado):
    """O que roda é o que está no arquivo (2ª importação não muda nada) e a agenda das 6h está ligada lá também."""
    rel = importar.importar(_pasta_w10_w11(), api)
    assert rel[W10] == {"id": instalado["w10"], "acao": "inalterado", "publicado": True, "avisos": []}
    assert rel[W11] == {"id": instalado["w11"], "acao": "inalterado", "publicado": True, "avisos": []}
    no_ar = api.workflow(instalado["w10"])
    agenda = next(n for n in no_ar["nodes"] if n["name"] == "Todo dia às 6h (a cada 10 min até 7h50)")
    assert agenda.get("disabled") is not True and no_ar["active"] is True


# ------------------------------------------------------------------ 1. W10: lease vencido e claim
def test_1_w10_libera_lease_vencido_e_reivindica_so_o_que_pode(api, pg, instalado):
    extraindo = guardas_da_fila(pg)
    if pg.execute("SELECT fn_disjuntor_w20_aberto() AS a").fetchone()["a"]:
        pytest.skip("o disjuntor REAL está aberto agora (W20 de outra frente): o W10 não reivindicaria")
    t = agora(pg)
    vencido = criar(pg, novo(), estado="baixando", lease_por="W20:teste-morto",
                    lease_ate=t - dt.timedelta(hours=1), prioridade=PRIO_ALMOFADA)
    armadilhas = {
        "lease vivo": criar(pg, novo(), prioridade=PRIO_ARMADILHA, lease_por="W20:teste-vivo",
                            lease_ate=t + dt.timedelta(hours=1)),
        "fora do escopo": criar(pg, novo(), prioridade=PRIO_ARMADILHA, escopo_dentro=False,
                                escopo_motivo="teste: regra recusou"),
        "fora do recorte": criar(pg, novo(), prioridade=PRIO_ARMADILHA, publicado_em=dt.date(2025, 11, 10),
                                 fim_prazo=None),
        "reservada": criar(pg, novo(), prioridade=PRIO_ARMADILHA, reserva_demo=True),
        "prazo vencido": criar(pg, novo(), prioridade=PRIO_ARMADILHA, fim_prazo=t - dt.timedelta(days=2)),
    }
    elegiveis = almofada(pg)

    r = rodar_w10(api)

    w = linha_w10(pg, r["id"])
    print("\n[W10 claim] execução n8n %s · linha %s · %s" % (r["id"], w["id"], json.dumps(
        {"contadores": w["contadores"], "argumentos": w["argumentos"]}, ensure_ascii=False, default=str)))
    assert (w["status"], w["gatilho"]) == ("ok", "manual")
    # 1. lease vencido devolvido: baixando -> falha_rede pela fn_registrar_falha (tentativa + backoff de 15 min).
    lib = r["saidas"]["Liberar leases vencidos"][0][0]
    assert {"controle": vencido, "estado_antes": "baixando", "resultado": "falha_rede"} in lib["detalhe"]
    assert w["contadores"]["liberados"] == lib["liberados"] >= 1
    v = lic(pg, vencido)
    assert (v["estado"], v["tentativas"], v["lease_por"]) == ("falha_rede", 1, None)
    atraso = (v["proxima_tentativa_em"] - agora(pg)).total_seconds()
    assert 13 * 60 < atraso <= 15 * 60, "backoff da 1ª falha é 15 min (db/021 fn_backoff)"
    assert pg.execute("SELECT count(*) AS n FROM licitacao_eventos WHERE controle = %s AND para = 'falha_rede' "
                      "AND motivo LIKE 'W10: lease vencido%%'", (vencido,)).fetchone()["n"] == 1
    # 2. reivindicou só a almofada: nada real, nenhuma armadilha, nem o que acabou de falhar (backoff).
    reivindicadas = w["argumentos"]["controles"]
    assert reivindicadas and set(reivindicadas) <= set(elegiveis), reivindicadas
    assert w["contadores"]["reivindicadas"] == len(reivindicadas)
    if extraindo == 0:
        assert set(reivindicadas) == set(elegiveis), "com 0 em 'extraindo' são 4 vagas"
    assert [x["controle"] for x in r["saidas"]["Reivindicar"][0]] == reivindicadas
    for motivo, c in armadilhas.items():
        x = lic(pg, c)
        assert x["estado"] == "nova", "%s: %s" % (motivo, x["estado"])
        assert x["lease_por"] == ("W20:teste-vivo" if motivo == "lease vivo" else None), motivo
    # 3. um W20 por reivindicada, sem esperar, com forcar=false (o W10 não força nada).
    assert r["nos"]["Disparar W20 (sem esperar)"]["itens"] == [len(reivindicadas)]
    w20 = esperar_w20(pg, reivindicadas, t)
    print("[W10 claim] W20 disparados (n8n): %s" % ", ".join("%s→%s" % (x["n8n_execution_id"], x["status"]) for x in w20))
    assert len(w20) == len(reivindicadas)
    for x in w20:
        assert x["argumentos"] == {"controle": x["controle"], "forcar": False}
        # CNPJ zerado: o PNCP responde 400 no /arquivos -> falha_rede com backoff (nada baixado, nada gasto).
        assert x["status"] == "erro" and lic(pg, x["controle"])["estado"] == "falha_rede"
    apagar_w20_de_teste(pg)


# ------------------------------------------------------------------ 2. disjuntor
def _sem_email_de_disjuntor_recente(pg):
    if pg.execute("SELECT 1 FROM emails WHERE tipo = 'erro' AND assunto = %s AND em > now() - interval '30 minutes'",
                  (ASSUNTO_DISJUNTOR,)).fetchone():
        pytest.skip("já há um e-mail de disjuntor na última meia hora: o 'uma vez só' não seria deste teste")


def _tres_falhas_do_w20(pg, controle):
    for i in range(3):
        pg.execute("INSERT INTO execucoes_workflow (workflow, gatilho, status, controle, erro, argumentos) "
                   "VALUES ('W20', 'teste', 'erro', %s, %s, %s)",
                   (controle, "TESTE %s: falha %d da fonte, para abrir o disjuntor" % (QUEM, i + 1),
                    json.dumps({"teste": QUEM})))


def _prova_do_disjuntor(pg, rodar, elegiveis, t, rotulo):
    """Duas rodadas com o disjuntor aberto: status 'disjuntor', nada reivindicado, nenhum e-mail (db/038-039)."""
    r1, r2 = rodar(), rodar()
    w1, w2 = linha_w10(pg, r1["id"]), linha_w10(pg, r2["id"])
    print("\n[%s] execuções n8n %s e %s · contadores %s / %s" % (rotulo, r1["id"], r2["id"], json.dumps(
        w1["contadores"], ensure_ascii=False), json.dumps(w2["contadores"], ensure_ascii=False)))
    for r, w in ((r1, w1), (r2, w2)):
        assert w["status"] == "disjuntor" and w["contadores"]["reivindicadas"] == 0
        assert "Reivindicar" not in r["nos"] and "Disparar W20 (sem esperar)" not in r["nos"]
    # E-mail de disjuntor saiu do produto (o produto manda só DOIS; db/038-039): o aviso é o status.
    assert pg.execute("SELECT count(*) AS n FROM emails WHERE em >= %s AND controle IS NULL", (t,)).fetchone()["n"] == 0
    assert w1["contadores"]["email_id"] is None and w2["contadores"]["email_id"] is None
    # Nada reivindicado: a almofada continua livre.
    for c in elegiveis:
        x = lic(pg, c)
        assert (x["estado"], x["lease_por"]) == ("nova", None)
    apagar_w20_de_teste(pg)


def test_2_w10_disjuntor_aberto_sem_email_e_nada_reivindicado(api, pg, instalado):
    """O W10 de verdade com o fn_disjuntor_w20_aberto() de verdade (db/021)."""
    guardas_da_fila(pg)

    def sucesso_recente():
        return pg.execute("SELECT max(iniciado_em) AS t FROM execucoes_workflow WHERE workflow = 'W20' "
                          "AND status = 'ok' AND iniciado_em > now() - interval '30 minutes'").fetchone()["t"]
    limite = time.monotonic() + ESPERA_DISJUNTOR
    while sucesso_recente() and time.monotonic() < limite:
        time.sleep(15)
    if sucesso_recente():
        pytest.skip("um W20 de outra frente terminou 'ok' às %s (UTC): o disjuntor real não abre nos 30 min "
                    "seguintes (o test_2b prova o canvas). FOPA_ESPERA_DISJUNTOR_S=1800 espera a janela."
                    % sucesso_recente())
    _sem_email_de_disjuntor_recente(pg)
    elegiveis = almofada(pg)          # se o disjuntor falhasse, o W10 pegaria estas (nunca uma real)
    t = agora(pg)
    _tres_falhas_do_w20(pg, elegiveis[0])
    assert pg.execute("SELECT fn_disjuntor_w20_aberto() AS a").fetchone()["a"] is True
    _prova_do_disjuntor(pg, lambda: rodar_w10(api), elegiveis, t, "disjuntor")


def test_2b_w10_disjuntor_no_canvas_com_a_regra_restrita_ao_teste(api, pg, instalado):
    """Cópia de TESTE do W10 (apagada no fim) em que o disjuntor é a MESMA regra do db/021 contada só nas linhas
    deste teste: o W20 de outra frente que terminou 'ok' não fecha o disjuntor, e o canvas (e-mail uma vez,
    nada reivindicado, status 'disjuntor') é provado sem esperar janela. A função em si é do
    db/tests/test_migracoes.py::test_disjuntor_abre_com_tres_erros_sem_sucesso."""
    guardas_da_fila(pg)
    _sem_email_de_disjuntor_recente(pg)
    wf = json.loads(ARQ_W10.read_text(encoding="utf-8"))
    bruto = json.dumps(wf, ensure_ascii=False)
    assert bruto.count("SELECT fn_disjuntor_w20_aberto() AS aberto") == 1
    # A regra do db/021, só nas licitações deste teste (000950-000999; o test_nucleo usa 00092x).
    restrita = ("(SELECT count(*) FILTER (WHERE status = 'erro') >= 3 AND count(*) FILTER (WHERE status = 'ok') = 0 "
                "FROM execucoes_workflow WHERE workflow = 'W20' AND iniciado_em > now() - interval '30 minutes' "
                "AND controle ~ '^00000000000000-1-0009[5-9][0-9]/2026$')")
    teste = json.loads(bruto.replace("SELECT fn_disjuntor_w20_aberto() AS aberto", "SELECT " + restrita + " AS aberto"))
    ids_wf = {importar.codigo(w["name"]): w["id"] for w in api.listar_workflows() if importar.codigo(w["name"])}
    ids_cred = {c["name"]: c["id"] for c in api.listar_credenciais()}
    teste = importar.resolver(teste, ids_wf, ids_cred, [])
    teste["name"] = "TESTE W10 disjuntor (apagar)"            # sem prefixo Wnn: o exportar.py ignora
    teste["settings"].pop("errorWorkflow", None)
    criado = api.publica("POST", "/workflows", importar.corpo(teste))
    try:
        elegiveis = almofada(pg)
        t = agora(pg)
        _tres_falhas_do_w20(pg, elegiveis[0])

        def rodar():
            r = executar.executar(teste["name"], timeout=120, api=api, com_saidas=True)
            assert r["status"] == "success", "cópia %s terminou %s: %s" % (r["id"], r["status"], r["erro"])
            return r
        _prova_do_disjuntor(pg, rodar, elegiveis, t, "disjuntor na cópia")
    finally:
        api.publica("DELETE", "/workflows/" + criado["id"])


# ------------------------------------------------------------------ 3. verificar
def test_3_w11_verificar_responde_202_rapido_e_o_w01_usa_a_linha(api, pg, instalado, token):
    antes = ultimo_id_n8n(api)
    st, corpo, dur = post("fopa/verificar", {"solicitado_por": QUEM}, token)
    print("\n[verificar] HTTP %s em %.2f s: %s" % (st, dur, corpo))
    assert st == 202 and isinstance(corpo, dict) and set(corpo) == {"execucao_id"}
    assert isinstance(corpo["execucao_id"], int), "o site (tipos.ts) espera número"
    assert dur < 3, "o site nunca espera a coleta"
    linha = pg.execute("SELECT * FROM execucoes_workflow WHERE id = %s", (corpo["execucao_id"],)).fetchone()
    assert linha and linha["workflow"] == "W01" and linha["gatilho"] == "site"
    assert linha["argumentos"]["solicitado_por"] == QUEM and linha["argumentos"]["seco"] is True
    # O W01 seco roda depois (1-3 min) na MESMA linha: é o que o site acompanha em /api/execucoes/{id}.
    fim = esperar(lambda: (lambda x: x if x["status"] != "em_curso" else None)(
        pg.execute("SELECT * FROM execucoes_workflow WHERE id = %s", (corpo["execucao_id"],)).fetchone()),
        900, 5, "o W01 fechar a linha %s" % corpo["execucao_id"])
    w11 = execucoes_n8n(api, instalado["w11"], antes)
    print("[verificar] W11 %s · W01 n8n %s · linha %s %s · %s" % (
        [x["id"] for x in w11], fim["n8n_execution_id"], fim["id"], fim["status"],
        json.dumps({k: fim["contadores"].get(k) for k in ("seco", "vistas", "cego")}, ensure_ascii=False)))
    assert [x["status"] for x in w11] == ["success"]
    assert fim["status"] == "ok" and fim["n8n_execution_id"] and fim["contadores"]["seco"] is True
    assert fim["gatilho"] == "site", "o W01 reaproveitou a linha do W11, não abriu outra"


# ------------------------------------------------------------------ 4. processar
def test_4a_w11_processar_valida_o_formato(api, pg, instalado, token):
    antes = pg.execute("SELECT count(*) AS n FROM licitacao_eventos WHERE motivo LIKE 'W11:%%'").fetchone()["n"]
    casos = [({"controles": ["abc", TODOS[-1]]}, "fora do formato do PNCP: abc"),
             ({"controles": []}, "de 1 a 20"),
             ({}, "de 1 a 20"),
             ({"controles": ["00000000000000-1-%06d/2026" % i for i in range(21)]}, "no máximo 20")]
    for corpo, trecho in casos:
        st, resp, dur = post("fopa/processar", dict(corpo, solicitado_por=QUEM), token)
        print("[processar 422] %s -> %s %s" % (json.dumps(corpo)[:60], st, resp))
        assert st == 422 and trecho in resp["detail"] and dur < TIMEOUT_SITE
    assert pg.execute("SELECT count(*) AS n FROM licitacao_eventos WHERE motivo LIKE 'W11:%%'").fetchone()["n"] == antes


def test_4b_w11_processar_aceita_e_recusa_pelo_banco(api, pg, instalado, token):
    guardas_da_fila(pg)
    elegivel = criar(pg, novo(), prioridade=0)
    fora_escopo = criar(pg, novo(), prioridade=0, escopo_dentro=False, escopo_motivo="teste: regra recusou")
    fora_recorte = criar(pg, novo(), prioridade=0, publicado_em=dt.date(2025, 11, 10), fim_prazo=None)
    terminal = criar(pg, novo(), prioridade=0, estado="erro_definitivo", tentativas=4)
    colchao = almofada(pg)             # o W10 que o W11 dispara pega estas, nunca a fila real
    t = agora(pg)
    antes = ultimo_id_n8n(api)

    st, resp, dur = post("fopa/processar", {"controles": [elegivel, fora_escopo, fora_recorte, terminal],
                                            "forcar": False, "solicitado_por": QUEM}, token)

    print("\n[processar] HTTP %s em %.2f s: %s" % (st, dur, json.dumps(resp, ensure_ascii=False)))
    assert st == 202 and dur < TIMEOUT_SITE
    assert resp["aceitos"] == [elegivel]
    rec = {x.split(": ", 1)[0]: x.split(": ", 1)[1] for x in resp["recusados"]}
    assert set(rec) == {fora_escopo, fora_recorte, terminal}
    assert rec[fora_escopo].startswith("fora do escopo de folha pela regra")
    assert rec[fora_recorte].startswith("fora do recorte de 2026")
    assert rec[terminal].startswith("estado erro_definitivo: reenvie com forcar=true")
    e = lic(pg, elegivel)
    assert (e["prioridade"], e["solicitante"]) == (1, QUEM), "db/022: prioridade 1 e quem pediu"
    for c in (fora_escopo, fora_recorte):
        assert (lic(pg, c)["prioridade"], lic(pg, c)["solicitante"]) == (0, None)
    x = lic(pg, terminal)
    assert (x["estado"], x["tentativas"]) == ("erro_definitivo", 4), "terminal sem forcar não muda"
    # A fila roda sem o site esperar: W10 (sub-fluxo) -> só a almofada -> W20.
    w10 = esperar_w10_subfluxo(pg, t)
    reivindicadas = w10["argumentos"]["controles"]
    print("[processar] W10 n8n %s reivindicou %s" % (w10["n8n_execution_id"], reivindicadas))
    assert w10["status"] == "ok" and reivindicadas and set(reivindicadas) <= set(colchao)
    w20 = esperar_w20(pg, reivindicadas, t)
    w11 = execucoes_n8n(api, instalado["w11"], antes)
    print("[processar] W11 %s · W20 %s" % ([x["id"] for x in w11], [x["n8n_execution_id"] for x in w20]))
    assert [x["status"] for x in w11] == ["success"]
    apagar_w20_de_teste(pg)


def test_4c_w11_processar_forcar_reabre_o_terminal(api, pg, instalado, token):
    guardas_da_fila(pg)
    terminal = criar(pg, novo(), prioridade=0, estado="erro_definitivo", tentativas=4,
                     proxima_tentativa_em=None)
    colchao = almofada(pg)
    t = agora(pg)

    st, resp, dur = post("fopa/processar", {"controles": [terminal], "forcar": True, "solicitado_por": QUEM}, token)

    print("\n[processar forcar] HTTP %s em %.2f s: %s" % (st, dur, json.dumps(resp, ensure_ascii=False)))
    assert st == 202 and resp == {"aceitos": [terminal], "recusados": []}
    x = lic(pg, terminal)
    assert (x["estado"], x["tentativas"], x["prioridade"], x["solicitante"]) == ("nova", 0, 1, QUEM)
    ev = pg.execute("SELECT de::text, para::text, motivo, dados FROM licitacao_eventos WHERE controle = %s",
                    (terminal,)).fetchall()
    assert ev == [{"de": "erro_definitivo", "para": "nova", "motivo": "W11: %s forçou o reprocessamento" % QUEM,
                   "dados": {"de": "erro_definitivo", "solicitante": QUEM}}], ev
    w10 = esperar_w10_subfluxo(pg, t)
    assert w10["status"] == "ok" and set(w10["argumentos"]["controles"]) <= set(colchao)
    print("[processar forcar] W10 n8n %s reivindicou %s" % (w10["n8n_execution_id"], w10["argumentos"]["controles"]))
    esperar_w20(pg, w10["argumentos"]["controles"], t)
    apagar_w20_de_teste(pg)


def test_4d_w11_processar_desconhecida_e_buscada_no_pncp_e_registrada(api, pg, instalado, token):
    if lic(pg, DESCONHECIDA_REAL):
        pytest.skip("%s já está no banco: escolha outra compra real de 2026 fora dele" % DESCONHECIDA_REAL)
    nao_achada = novo()                # CNPJ zerado: o PNCP responde 400
    guardas_da_fila(pg)
    almofada(pg)                       # se a regra dissesse 'dentro', o W10 rodaria: pega a almofada
    t = agora(pg)
    antes = ultimo_id_n8n(api)

    for tentativa in range(4):
        st, resp, dur = post("fopa/processar", {"controles": [DESCONHECIDA_REAL, nao_achada],
                                                "solicitado_por": QUEM}, token)
        print("\n[processar desconhecida] HTTP %s em %.2f s: %s" % (st, dur, json.dumps(resp, ensure_ascii=False)))
        # 429 do PNCP é passageiro e o W11 o diz com todas as letras (test_4f); o teste só tenta de novo.
        if st != 202 or "PNCP indisponível" not in json.dumps(resp, ensure_ascii=False):
            break
        time.sleep(30)
    assert st == 202 and dur < TIMEOUT_SITE
    x = lic(pg, DESCONHECIDA_REAL)
    assert x, "a compra desconhecida não foi registrada"
    print("[processar desconhecida] registrada: %s" % json.dumps(
        {k: x[k] for k in ("estado", "orgao", "uf", "municipio", "modalidade", "publicado_em", "fim_prazo",
                           "escopo_dentro", "escopo_motivo", "escopo_versao", "origem", "atualizado_pncp")},
        ensure_ascii=False, default=str))
    # Os dados vieram da API de consulta do PNCP (não do pedido) e a regra de escopo do worker decidiu.
    assert x["origem"] == "n8n" and x["orgao"] == "EMPRESA BRASILEIRA DE SERVICOS HOSPITALARES - EBSERH"
    assert (x["uf"], x["municipio"], x["ano"], x["seq"]) == ("PR", "Curitiba", 2026, 3711)
    assert "agulhas e seringas" in x["objeto"] and x["publicado_em"] == dt.date(2026, 9, 15)
    assert x["link"] == "https://pncp.gov.br/app/editais/15126437000305/2026/3711"
    assert len(x["escopo_versao"] or "") == 64, "escopo_versao é o sha256 da regra (api/versao.py)"
    assert x["atualizado_pncp"] is None, "carimbo vazio de propósito: o W01 compara o da busca"
    # Agulhas não é folha: entra como fora_escopo (fica para o Jev/rótulo) e o pedido é recusado pelo db/022.
    assert (x["estado"], x["escopo_dentro"]) == ("fora_escopo", False)
    assert resp["aceitos"] == []
    rec = {r.split(": ", 1)[0]: r.split(": ", 1)[1] for r in resp["recusados"]}
    assert rec[DESCONHECIDA_REAL].startswith("fora do escopo de folha pela regra")
    assert rec[nao_achada] == "não achada no PNCP" and lic(pg, nao_achada) is None
    # Nada aceito: o W10 não foi chamado.
    time.sleep(3)
    assert not pg.execute("SELECT 1 FROM execucoes_workflow WHERE workflow = 'W10' AND iniciado_em >= %s",
                          (t,)).fetchone()
    w11 = execucoes_n8n(api, instalado["w11"], antes)
    print("[processar desconhecida] W11 %s" % [x["id"] for x in w11])
    assert [x["status"] for x in w11] == ["success"] * (tentativa + 1), "uma execução do W11 por pedido"


def test_4f_w11_processar_pncp_fora_do_ar_nao_e_nao_achada(api, pg, instalado, token):
    """Cópia de TESTE do W11 com a API de consulta numa porta fechada e webhooks próprios (apagada no fim).

    Achado da construção: o 429 do PNCP voltava como 'não achada no PNCP'. Agora a desconhecida volta
    recusada com 'PNCP indisponível' e nada é gravado; a conhecida segue pelo banco, PNCP fora ou não.
    """
    if lic(pg, DESCONHECIDA_REAL):
        pytest.skip("%s já está no banco" % DESCONHECIDA_REAL)
    guardas_da_fila(pg)
    wf = json.loads(ARQ_W11.read_text(encoding="utf-8"))
    bruto = json.dumps(wf, ensure_ascii=False)
    base_pncp = "https://pncp.gov.br/api/consulta/v1/orgaos/"
    assert bruto.count(base_pncp) == 1, "a URL da API de consulta deveria morar num lugar só"
    teste = json.loads(bruto.replace(base_pncp, "http://127.0.0.1:9/api/consulta/v1/orgaos/"))
    ids_wf = {importar.codigo(w["name"]): w["id"] for w in api.listar_workflows() if importar.codigo(w["name"])}
    ids_cred = {c["name"]: c["id"] for c in api.listar_credenciais()}
    teste = importar.resolver(teste, ids_wf, ids_cred, [])
    teste["name"] = "TESTE W11 com PNCP fora (apagar)"      # sem prefixo Wnn: o exportar.py ignora
    teste["settings"].pop("errorWorkflow", None)
    for n in teste["nodes"]:
        if n["type"] == "n8n-nodes-base.webhook":
            n["parameters"]["path"] = "teste-w11-pncp-fora/" + n["parameters"]["path"].split("/")[-1]
            n["webhookId"] = str(uuid.uuid4())
    criado = api.publica("POST", "/workflows", importar.corpo(teste))
    try:
        importar.publicar(api, criado["id"])
        conhecida = criar(pg, novo(), prioridade=0)
        almofada(pg)                   # a conhecida é aceita -> o W10 de verdade roda -> pega a almofada
        t = agora(pg)
        st, resp, dur = post("teste-w11-pncp-fora/processar",
                             {"controles": [DESCONHECIDA_REAL, conhecida], "solicitado_por": QUEM}, token)
        print("\n[PNCP fora] HTTP %s em %.2f s: %s" % (st, dur, json.dumps(resp, ensure_ascii=False)))
        assert st == 202 and resp["aceitos"] == [conhecida]
        (rec,) = resp["recusados"]
        assert rec.startswith(DESCONHECIDA_REAL + ": PNCP indisponível agora (sem resposta"), rec
        assert rec.endswith("tente de novo em instantes")
        assert lic(pg, DESCONHECIDA_REAL) is None, "PNCP fora do ar não pode gravar nada"
        w10 = esperar_w10_subfluxo(pg, t)
        assert set(w10["argumentos"]["controles"]) <= set(TODOS)
        esperar_w20(pg, w10["argumentos"]["controles"], t)
        apagar_w20_de_teste(pg)
    finally:
        api.publica("DELETE", "/workflows/" + criado["id"])


def test_4e_w11_processar_reservada_com_forcar_vai_direto_ao_w20(api, pg, instalado, token):
    guardas_da_fila(pg)
    reservada = criar(pg, novo(), prioridade=0, reserva_demo=True)
    t = agora(pg)
    antes = ultimo_id_n8n(api)

    st, resp, dur = post("fopa/processar", {"controles": [reservada], "forcar": True, "solicitado_por": QUEM}, token)

    print("\n[processar reservada] HTTP %s em %.2f s: %s" % (st, dur, json.dumps(resp, ensure_ascii=False)))
    assert st == 202 and resp == {"aceitos": [reservada], "recusados": []}
    (w20,) = esperar_w20(pg, [reservada], t)
    print("[processar reservada] W20 n8n %s · %s · %s" % (w20["n8n_execution_id"], w20["status"], w20["erro"]))
    # O W20 recebeu forcar=true e passou da guarda da demo (sem forcar ele devolveria 'recusado').
    assert w20["argumentos"] == {"controle": reservada, "forcar": True}
    assert w20["status"] != "recusado"
    assert pg.execute("SELECT count(*) AS n FROM licitacao_eventos WHERE controle = %s AND para = 'baixando'",
                      (reservada,)).fetchone()["n"] == 1, "o W20 foi ao W21"
    # Direto: a fila não entrou (nenhum W10), e o W11 terminou bem.
    assert not pg.execute("SELECT 1 FROM execucoes_workflow WHERE workflow = 'W10' AND iniciado_em >= %s",
                          (t,)).fetchone()
    w11 = execucoes_n8n(api, instalado["w11"], antes)
    print("[processar reservada] W11 %s" % [x["id"] for x in w11])
    assert [x["status"] for x in w11] == ["success"]
    apagar_w20_de_teste(pg)


# ------------------------------------------------------------------ 5. reverificar
def test_5_w11_reverificar_responde_202_e_registra(api, pg, instalado, token):
    sem_verificacao = criar(pg, novo(), prioridade=0)
    st, resp, dur = post("fopa/reverificar", {"controle": sem_verificacao, "solicitado_por": QUEM}, token)
    print("\n[reverificar] HTTP %s em %.2f s: %s" % (st, dur, resp))
    assert st == 202 and resp == {"aceito": True, "controle": sem_verificacao} and dur < 3

    def linha():
        return pg.execute("SELECT * FROM execucoes_workflow WHERE workflow = 'W11' "
                          "AND argumentos ->> 'controle' = %s", (sem_verificacao,)).fetchone()
    x = esperar(linha, 60, oque="a linha W11 do reverificar")
    print("[reverificar] W11 n8n %s · linha %s · %s · %s" % (x["n8n_execution_id"], x["id"], x["status"], x["erro"]))
    assert x["gatilho"] == "site" and x["n8n_execution_id"]
    assert x["argumentos"]["acao"] == "reverificar" and x["argumentos"]["solicitado_por"] == QUEM
    # Licitação de teste não tem verificação: o worker diz 404 e isso fica ESCRITO (nunca silêncio).
    assert x["status"] == "erro" and "sem verificação vigente" in x["erro"] and "HTTP 404" in x["erro"]
    assert x["controle"] == sem_verificacao and x["custo_brl"] == 0 and x["duracao_s"] is not None
    assert (x["contadores"]["falhas"], x["contadores"]["republicadas"]) == (1, 0)
    assert lic(pg, sem_verificacao)["estado"] == "nova", "reverificar não muda estado"
    assert pg.execute("SELECT count(*) AS n FROM execucoes_workflow WHERE workflow = 'W11' "
                      "AND argumentos ->> 'controle' = %s", (sem_verificacao,)).fetchone()["n"] == 1, "uma linha só"


W23, W24 = "W23 Extrair", "W24 Verificar e publicar"
NOME_PDF = "01 - Edital - teste.pdf"
TEXTO = ("PREFEITURA DE TESTE. EDITAL DE DISPENSA Nº 1/2026. OBJETO: contratação de instituição financeira "
         "para processamento da folha de pagamento dos servidores. VIGÊNCIA: 60 (sessenta) meses. "
         "VALOR MÍNIMO: R$ 1.000.000,00. PRAZO PARA ASSINATURA DO CONTRATO: 5 (cinco) dias úteis.")


def _sub(api, fluxo: str, **entrada) -> dict:
    """Um sub-fluxo do núcleo pelo gatilho de sub-fluxo, como o W20/W30 o chamariam; devolve o que ele retornou."""
    r = executar.executar(fluxo, timeout=600, api=api, itens=[entrada], com_saidas=True)
    assert r["status"] == "success", "%s execução %s: %s (último nó %s)" % (fluxo, r["id"], r["erro"], r["ultimo_no"])
    return r["saidas"][r["ultimo_no"]][0][0]


def _preparada_sintetica(pg, para_que: str) -> str:
    """Licitação de TESTE (CNPJ zerado, ensaio) em `preparada` com leitura sintética de 1 página: sem PDF, sem OCR,
    sem rede. Os itens da API vão vazios, para o W24 não ir ao PNCP."""
    c = criar(pg, novo(), estado="preparada", prioridade=0,
              objeto="TESTE %s: folha de pagamento — %s" % (QUEM, para_que))
    aid = pg.execute("INSERT INTO arquivos (controle, seq, nome, sha256, bytes, status, proveniencia)"
                     " VALUES (%s, 1, %s, repeat('1', 64), 1, 'ok', '{\"teste\": true}') RETURNING id",
                     (c, NOME_PDF)).fetchone()["id"]
    assinatura = json.dumps({NOME_PDF: "1" * 64})
    lid = pg.execute(
        "INSERT INTO leituras (controle, versao_ocr, condicoes, hashes_bytes, assinatura, assinatura_conjunto,"
        " assinatura_nomes, modo_sugerido, chars_total, procedencia_texto, vigente)"
        " VALUES (%s, 'teste-sem-ocr', '{}', '{}', %s::jsonb, repeat('b', 64), fn_assinatura_nomes(%s::jsonb),"
        " 'contexto-completo', %s, 'worker', true) RETURNING id",
        (c, assinatura, assinatura, len(TEXTO))).fetchone()["id"]
    pg.execute("INSERT INTO paginas (leitura_id, arquivo_id, arquivo_nome, numero, ordem, texto)"
               " VALUES (%s, %s, %s, 1, 0, %s)", (lid, aid, NOME_PDF, TEXTO))
    pg.execute("UPDATE licitacoes SET leitura_vigente_id = %s WHERE controle = %s", (lid, c))
    pg.execute("INSERT INTO itens_api (controle, payload) VALUES (%s, '[]')", (c,))   # o W24 não vai ao PNCP
    return c


def _publicada_e_envelhecida(api, pg) -> dict:
    """Licitação de TESTE (CNPJ zerado, ensaio) publicada DE VERDADE — leitura sintética de 1 página (sem PDF, sem
    OCR, sem rede) → W23 simulado → W24 — e depois envelhecida à mão como o legado do acervo (o `republicavel` do
    test_nucleo): a vigente passa a ser de outra `versao_regras`, com o veredito da Q2 trocado e um alerta a mais.
    Assim o /reverificar grava uma verificação nova e o diff tem conteúdo conhecido."""
    prov = pg.execute("SELECT valor #>> '{}' AS v FROM configuracao WHERE chave = 'provedor'").fetchone()
    if not prov or prov["v"] not in ("simulado", "gravado"):
        pytest.fail("configuracao.provedor = %r: o W23 gastaria; este teste só roda com simulado/gravado"
                    % (prov and prov["v"]))
    c = _preparada_sintetica(pg, "reverificar pelo site e republicar")
    r23 = _sub(api, W23, controle=c)
    assert r23["estado"] == "respondida", r23
    r24 = _sub(api, W24, controle=c)
    assert r24["estado"] == "publicada", r24
    v1 = int(r24["verificacao_id"])
    atual = pg.execute("SELECT veredito FROM verificacao_respostas WHERE verificacao_id = %s AND pergunta_id = 'Q2'",
                       (v1,)).fetchone()["veredito"]
    velho = "APROVADO" if atual != "APROVADO" else "REVISAR"
    pg.execute("UPDATE verificacoes SET versao_regras = 'legado:teste-w11',"
               " alertas_globais = array_append(coalesce(alertas_globais, '{}'), 'teste: alerta que sai')"
               " WHERE id = %s", (v1,))
    pg.execute("UPDATE verificacao_respostas SET veredito = %s WHERE verificacao_id = %s AND pergunta_id = 'Q2'",
               (velho, v1))
    return {"controle": c, "v1": v1, "velho": velho, "atual": atual}


def _vigente(pg, controle: str):
    return pg.execute("SELECT id, versao_regras FROM verificacoes WHERE controle = %s AND vigente", (controle,)).fetchone()


def _reverificar_pelo_site(api, pg, token, controle: str) -> tuple[dict, list]:
    """POST fopa/reverificar como o site (api/site.py _chamar_n8n) e a linha W11 que o pedido deixou (e só uma)."""
    antes_linha = pg.execute("SELECT coalesce(max(id), 0) AS m FROM execucoes_workflow").fetchone()["m"]
    antes_n8n = ultimo_id_n8n(api)
    st, resp, dur = post("fopa/reverificar", {"controle": controle, "solicitado_por": QUEM}, token)
    assert st == 202 and resp == {"aceito": True, "controle": controle} and dur < 3, (st, resp, dur)

    def linha():
        x = pg.execute("SELECT * FROM execucoes_workflow WHERE workflow = 'W11' AND id > %s "
                       "AND argumentos ->> 'controle' = %s", (antes_linha, controle)).fetchall()
        return x or None
    (x,) = esperar(linha, 120, oque="a linha W11 do reverificar de %s" % controle)
    w24 = execucoes_n8n(api, instalado_ids(api)["W24"], antes_n8n)
    return x, w24


def instalado_ids(api) -> dict:
    return {importar.codigo(w["name"]): w["id"] for w in api.listar_workflows() if importar.codigo(w["name"])}


def test_5b_w11_reverificar_republica_retoma_e_pula(api, pg, instalado, token):
    """O reverificar do site faz, para UMA licitação, o que o W30 faz em lote: /reverificar -> W24 modo republicar."""
    alvo = _publicada_e_envelhecida(api, pg)
    c, v1 = alvo["controle"], alvo["v1"]
    email_antes = pg.execute("SELECT coalesce(max(id), 0) AS m FROM emails").fetchone()["m"]

    # 1. Verificação nova (200) -> W24 republicar: a nova vira a vigente, com o diff do envelhecimento.
    x, w24 = _reverificar_pelo_site(api, pg, token, c)
    k = x["contadores"]
    print("\n[reverificar 200] W11 n8n %s · W24 n8n %s · linha %s · %s · %s" % (
        x["n8n_execution_id"], [e["id"] for e in w24], x["id"], x["status"],
        json.dumps({i: k[i] for i in ("republicadas", "vereditos_mudados", "retomada", "antes_verificacao_id",
                                      "verificacao_id", "mudaram")}, ensure_ascii=False)))
    assert (x["status"], x["gatilho"], x["controle"], x["erro"]) == ("ok", "site", c, None)
    assert x["argumentos"] == {"acao": "reverificar", "controle": c, "solicitado_por": QUEM}
    assert (k["republicadas"], k["falhas"], k["puladas"], k["retomada"], k["reverificacao_http"]) == (1, 0, 0, False, 200)
    assert all(isinstance(k[i], int) for i in ("verificacao_id", "antes_verificacao_id", "email_id")), k
    v2 = int(k["verificacao_id"])
    assert v2 != v1 and int(k["antes_verificacao_id"]) == v1 and int(k["base_verificacao_id"]) == v1
    assert k["mudaram"] == ["Q2"] and k["vereditos_mudados"] == 1 and k["estado"] == "publicada"
    assert [e["status"] for e in w24] == ["success"], "um W24 (modo republicar) por pedido"
    vig = _vigente(pg, c)
    assert vig["id"] == v2 and vig["versao_regras"] == k["versao_regras"] != "legado:teste-w11"
    assert lic(pg, c)["estado"] == "publicada"
    ultimos = [(e["de"], e["para"]) for e in pg.execute(
        "SELECT de::text, para::text FROM licitacao_eventos WHERE controle = %s ORDER BY id DESC LIMIT 2",
        (c,)).fetchall()][::-1]
    assert ultimos == [("publicada", "verificada"), ("verificada", "publicada")]
    assert pg.execute("SELECT 1 FROM publicacoes WHERE controle = %s AND verificacao_id = %s", (c, v2)).fetchone()
    rep = pg.execute("SELECT id, assunto, corpo_html FROM emails WHERE id > %s AND controle = %s AND tipo = 'republicada'",
                     (email_antes, c)).fetchall()
    assert len(rep) == 1 and int(k["email_id"]) == rep[0]["id"] and "1 veredito(s) mudaram" in rep[0]["assunto"]
    assert "teste: alerta que sai" in rep[0]["corpo_html"]

    # 2. Retomada: como se o W24 tivesse morrido antes de trocar a vigente. /reverificar diz 409 "já foi verificada";
    #    a verificação desta versão que ficou sem republicar é a que se republica (nada se reverifica duas vezes).
    pg.execute("UPDATE verificacoes SET vigente = false WHERE id = %s", (v2,))
    pg.execute("UPDATE verificacoes SET vigente = true WHERE id = %s", (v1,))
    x, w24 = _reverificar_pelo_site(api, pg, token, c)
    k = x["contadores"]
    print("[reverificar 409 retomada] W11 n8n %s · W24 n8n %s · linha %s · %s · verificacao %s" % (
        x["n8n_execution_id"], [e["id"] for e in w24], x["id"], x["status"], k["verificacao_id"]))
    assert (x["status"], k["republicadas"], k["retomada"], k["reverificacao_http"]) == ("ok", 1, True, 409)
    assert int(k["verificacao_id"]) == v2 and _vigente(pg, c)["id"] == v2
    assert [e["status"] for e in w24] == ["success"]
    assert pg.execute("SELECT count(*) AS n FROM verificacoes WHERE controle = %s", (c,)).fetchone()["n"] == 2

    # 3. Já nas regras atuais e nada pendente: pulada (ok), nada muda, o W24 nem é chamado.
    x, w24 = _reverificar_pelo_site(api, pg, token, c)
    k = x["contadores"]
    print("[reverificar 409 pulada] W11 n8n %s · linha %s · %s · %s" % (x["n8n_execution_id"], x["id"], x["status"],
                                                                        k["motivo"]))
    assert (x["status"], k["republicadas"], k["puladas"], k["retomada"]) == ("ok", 0, 1, True)
    assert "já verificada nesta versão" in k["motivo"] and w24 == []
    assert _vigente(pg, c)["id"] == v2
    assert pg.execute("SELECT count(*) AS n FROM verificacoes WHERE controle = %s", (c,)).fetchone()["n"] == 2
    # Simulado na licitação de ensaio: nem revisão humana nem Jev na republicação; custo R$ 0 nas três linhas.
    assert pg.execute("SELECT count(*) AS n FROM revisoes_humanas WHERE verificacao_id = %s", (v2,)).fetchone()["n"] == 0
    assert pg.execute("SELECT count(*) AS n FROM sinais_jev WHERE controle = %s", (c,)).fetchone()["n"] == 0
    assert pg.execute("SELECT count(*) AS n, sum(custo_brl) AS s FROM execucoes_workflow WHERE workflow = 'W11' "
                      "AND controle = %s", (c,)).fetchone() == {"n": 3, "s": 0}


# ------------------------------------------------------------------ 6. sem token
def test_6_webhooks_sem_token_recusam_e_nada_roda(api, pg, instalado, token):
    antes = ultimo_id_n8n(api)
    marca = QUEM + "-sem-token"
    for caminho, corpo in (("fopa/verificar", {"solicitado_por": marca}),
                           ("fopa/processar", {"controles": [TODOS[-1]], "solicitado_por": marca}),
                           ("fopa/reverificar", {"controle": TODOS[-1], "solicitado_por": marca}),
                           ("fopa/importar-respostas", {"controle": TODOS[-1], "respostas": [], "solicitado_por": marca})):
        for tk in (None, "errado-" + "x" * 8, token[:-1]):
            st, resp, _ = post(caminho, corpo, tk)
            assert st in (401, 403), "%s sem o token certo respondeu %s" % (caminho, st)
        print("[sem token] %s -> %s %s" % (caminho, st, resp))
    time.sleep(2)
    assert execucoes_n8n(api, instalado["w11"], antes) == [], "o W11 rodou sem o token"
    assert not pg.execute("SELECT 1 FROM execucoes_workflow WHERE argumentos ->> 'solicitado_por' = %s",
                          (marca,)).fetchone()


# ------------------------------------------------------------------ 7. importar-respostas (ADR-014)
CITADAS = {
    "Q2": ("Contratação de instituição financeira para processar a folha de pagamento dos servidores.",
           "OBJETO: contratação de instituição financeira para processamento da folha de pagamento dos servidores."),
    "Q3": ("Dispensa (edital de dispensa nº 1/2026).", "EDITAL DE DISPENSA Nº 1/2026"),
    "Q5": ("R$ 1.000.000,00", "VALOR MÍNIMO: R$ 1.000.000,00"),
    "Q7": ("5 (cinco) dias úteis", "PRAZO PARA ASSINATURA DO CONTRATO: 5 (cinco) dias úteis"),
    "Q9": ("60 (sessenta) meses", "VIGÊNCIA: 60 (sessenta) meses"),
}


def _respostas_do_agente(**trocas) -> list:
    """As 17 respostas no formato do respostas.json do agente (70_extracao_por_agente.py): 5 citam a página
    sintética, o resto é "Não localizado"."""
    out = []
    for i in range(1, 18):
        q = "Q%d" % i
        if q in CITADAS:
            resposta, trecho = CITADAS[q]
            out.append({"id": q, "resposta": trocas.get(q, resposta), "arquivo": NOME_PDF, "pagina": 1,
                        "trecho_literal": trecho, "conflito": None, "confianca": "alta"})
        else:
            out.append({"id": q, "resposta": "Não localizado.", "arquivo": None, "pagina": None,
                        "trecho_literal": None, "conflito": None, "confianca": "media"})
    return out


def _importar(controle: str, respostas, token) -> tuple[int, object, float]:
    """POST fopa/importar-respostas com o corpo que o site manda (api/site.py acao_importar_respostas)."""
    return post("fopa/importar-respostas", {"controle": controle, "respostas": respostas, "solicitado_por": QUEM,
                                            "procedencia": {"provedor": "claude-code", "modelo": "claude-opus-5-5",
                                                            "sessao": "teste %s" % QUEM}}, token)


def _linha_importar(pg, controle: str, depois_de: int, timeout: float = 240) -> dict:
    def linha():
        return pg.execute("SELECT * FROM execucoes_workflow WHERE workflow = 'W11' AND id > %s "
                          "AND argumentos ->> 'acao' = 'importar-respostas' AND argumentos ->> 'controle' = %s",
                          (depois_de, controle)).fetchone()
    return esperar(linha, timeout, oque="a linha W11 da importação de %s" % controle)


def _nada_mudou(pg, controle: str, estado: str, antes_linha: int):
    x = lic(pg, controle)
    assert x["estado"] == estado, "a recusa mudou o estado de %s" % controle
    assert not pg.execute("SELECT 1 FROM execucoes_modelo WHERE controle = %s AND origem = 'agente'",
                          (controle,)).fetchone(), "a recusa criou execução"
    assert not pg.execute("SELECT 1 FROM execucoes_workflow WHERE workflow = 'W11' AND id > %s "
                          "AND argumentos ->> 'controle' = %s", (antes_linha, controle)).fetchone()


def test_7a_w11_importar_recusa_com_motivo_e_nada_muda(api, pg, instalado, token):
    antes_linha = pg.execute("SELECT coalesce(max(id), 0) AS m FROM execucoes_workflow").fetchone()["m"]
    boas = _respostas_do_agente()
    # formato: o W11 é a 2ª cerca (o site já confere)
    st, resp, _ = _importar("12345", boas, token)
    assert st == 422 and "formato do PNCP" in resp["detail"], (st, resp)
    st, resp, _ = _importar(TODOS[-1], boas[:16], token)
    assert st == 422 and "17 respostas" in resp["detail"], (st, resp)
    # controle que a v3 não conhece: 422 (404 o site leria como "webhook não registrado")
    st, resp, _ = _importar(TODOS[-2], boas, token)
    assert st == 422 and "desconhecida" in resp["detail"], (st, resp)
    # sem leitura congelada (nova): 409 com o motivo
    nova = criar(pg, novo(), prioridade=0)
    st, resp, _ = _importar(nova, boas, token)
    print("\n[importar nova] %s %s" % (st, resp))
    assert st == 409 and "sem leitura congelada" in resp["detail"] and resp["estado"] == "nova", (st, resp)
    _nada_mudou(pg, nova, "nova", antes_linha)
    # em curso por outro fluxo (lease vivo) e estado que não é de importar
    c = _preparada_sintetica(pg, "importar recusado")
    pg.execute("UPDATE licitacoes SET lease_por = 'W20:teste', lease_ate = now() + interval '1 hour' "
               "WHERE controle = %s", (c,))
    st, resp, _ = _importar(c, boas, token)
    assert st == 409 and "em processamento agora (W20:teste)" in resp["detail"], (st, resp)
    pg.execute("UPDATE licitacoes SET lease_por = NULL, lease_ate = NULL, estado = 'lendo' WHERE controle = %s", (c,))
    st, resp, _ = _importar(c, boas, token)
    assert st == 409 and "estado lendo" in resp["detail"], (st, resp)
    _nada_mudou(pg, c, "lendo", antes_linha)
    # resposta que o worker recusa (confiança fora do domínio): 422 com a mensagem DELE, nenhuma execução
    pg.execute("UPDATE licitacoes SET estado = 'preparada' WHERE controle = %s", (c,))
    ruins = _respostas_do_agente()
    ruins[2]["confianca"] = "total"
    st, resp, _ = _importar(c, ruins, token)
    print("[importar ruins] %s %s" % (st, resp))
    assert st == 422 and "Q3: confianca fora de alta/media/baixa" in resp["detail"], (st, resp)
    _nada_mudou(pg, c, "preparada", antes_linha)


def test_7b_w11_importar_publica_e_importar_de_novo_republica(api, pg, instalado, token):
    c = _preparada_sintetica(pg, "importar as respostas do agente")
    antes_linha = pg.execute("SELECT coalesce(max(id), 0) AS m FROM execucoes_workflow").fetchone()["m"]
    antes_evento = pg.execute("SELECT coalesce(max(id), 0) AS m FROM licitacao_eventos").fetchone()["m"]

    # 1. primeira extração: 202 assim que o worker aceita; o W24 publica depois
    st, resp, dur = _importar(c, _respostas_do_agente(), token)
    print("\n[importar 1] HTTP %s em %.2f s: %s" % (st, dur, resp))
    assert st == 202 and dur < TIMEOUT_SITE, (st, resp, dur)
    assert (resp["aceito"], resp["controle"], resp["modo"], resp["verificacao_id"]) == (True, c, "publicar", None)
    e1 = resp["execucao_id"]
    assert isinstance(e1, int)
    x = _linha_importar(pg, c, antes_linha)
    k = x["contadores"]
    print("[importar 1] W11 n8n %s · linha %s · %s · %s" % (x["n8n_execution_id"], x["id"], x["status"],
                                                           json.dumps(k, ensure_ascii=False)))
    assert (x["status"], x["erro"], x["gatilho"], x["controle"], x["custo_brl"]) == ("ok", None, "site", c, 0)
    assert x["argumentos"]["procedencia"] == {"provedor": "claude-code", "modelo": "claude-opus-5-5",
                                              "sessao": "teste %s" % QUEM}
    assert (k["importadas"], k["publicadas"], k["republicadas"], k["falhas"]) == (1, 1, 0, 0)
    assert (k["estado_antes"], k["estado"], k["execucao_id"]) == ("preparada", "publicada", e1)
    assert (k["ancoradas"], k["respondidas"]) == (5, 5), k
    x_lic = lic(pg, c)
    assert x_lic["estado"] == "publicada" and x_lic["lease_por"] is None, "publicada e com o lease do W11 solto"
    ex = pg.execute("SELECT origem, provedor, modelo, status, canonica, fonte_migracao FROM execucoes_modelo "
                    "WHERE id = %s", (e1,)).fetchone()
    assert (ex["origem"], ex["provedor"], ex["modelo"], ex["canonica"]) == ("agente", "claude-code", "claude-opus-5-5", True)
    assert ex["status"] != "em_curso" and ex["fonte_migracao"]["via"] == "/importar-respostas"
    vig = pg.execute("SELECT id, execucao_id FROM verificacoes WHERE controle = %s AND vigente", (c,)).fetchone()
    assert vig["execucao_id"] == e1 and vig["id"] == k["verificacao_id"]
    caminho = [r["para"] for r in pg.execute(
        "SELECT para::text AS para FROM licitacao_eventos WHERE controle = %s AND id > %s AND para IS NOT NULL "
        "ORDER BY id", (c, antes_evento)).fetchall()]
    assert caminho == ["extraindo", "respondida", "verificada", "publicada"], caminho
    assert pg.execute("SELECT count(*) AS n FROM emails WHERE controle = %s", (c,)).fetchone()["n"] == 1

    # 2. extração nova sobre a mesma leitura: o worker verifica já, o W24 republica
    antes_linha = x["id"]
    st, resp, dur = _importar(c, _respostas_do_agente(Q2="Objeto: banco para a folha dos servidores."), token)
    print("[importar 2] HTTP %s em %.2f s: %s" % (st, dur, resp))
    assert st == 202 and dur < TIMEOUT_SITE and resp["modo"] == "republicar", (st, resp, dur)
    e2, v2 = resp["execucao_id"], resp["verificacao_id"]
    assert isinstance(e2, int) and isinstance(v2, int) and e2 != e1
    x = _linha_importar(pg, c, antes_linha)
    k = x["contadores"]
    print("[importar 2] W11 n8n %s · linha %s · %s · %s" % (x["n8n_execution_id"], x["id"], x["status"],
                                                           json.dumps(k, ensure_ascii=False)))
    assert (x["status"], k["publicadas"], k["republicadas"], k["estado_antes"], k["estado"]) == (
        "ok", 0, 1, "publicada", "publicada")
    vig = pg.execute("SELECT id, execucao_id FROM verificacoes WHERE controle = %s AND vigente", (c,)).fetchone()
    assert (vig["id"], vig["execucao_id"]) == (v2, e2), "a vigente é a verificação da importação nova"
    assert lic(pg, c)["lease_por"] is None
    assert pg.execute("SELECT count(*) AS n FROM emails WHERE controle = %s", (c,)).fetchone()["n"] == 2
    assert pg.execute("SELECT count(*) AS n, sum(custo_brl) AS s FROM execucoes_workflow WHERE workflow = 'W11' "
                      "AND controle = %s", (c,)).fetchone() == {"n": 2, "s": 0}
