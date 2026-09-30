# -*- coding: utf-8 -*-
"""
W01 Descoberta na instância de verdade: `fopa-n8n` (127.0.0.1:5679), o Postgres
da stack (127.0.0.1:5433) e o PNCP real (grátis). O Jev é pago (centavos): a
rodada real destes testes sai pelo gatilho Manual, cujo teto é 100 chamadas.

O que se prova (o recorte de escopo já na consulta à API, que traz muito ruído):

  0. o JSON versionado segue as convenções (gatilhos, PNCP com saída de erro,
     paginação explícita, credenciais por placeholder) e a consulta leva
     `anos=` e `status=recebendo_proposta`; no fim da rodada, IF `!seco &&
     orcamento.auto_processar` → W10 sem esperar, com o Execute DESLIGADO
     (a ativação da esteira depende de aprovação do gestor do projeto);
  1. seco (o "Verificar agora" do W11, com a linha de execucoes_workflow que o
     W11 já abriu) não escreve NADA em licitacoes, usa a linha dada e lista as
     novas;
  2. PNCP inalcançável (cópia de teste do fluxo com a URL numa porta fechada)
     -> cego=true, e-mail 'cego' na fila, nenhuma licitação tocada;
  2b. o mesmo em PRODUÇÃO (cópia disparada por Webhook, Error Workflow = W90
     de verdade), nas duas variantes do plano §11.3 — porta fechada e 429 com
     corpo HTML de um PNCP FALSO (fluxo de teste no próprio n8n): cego=true,
     'cego' na fila, nenhuma licitação tocada e NENHUM [ERRO] do W90;
  3. rodada real insere só o que está no recorte de 2026 (fn_no_recorte) e a
     2ª rodada logo em seguida não insere nada (idempotente);
  4. o Jev pontua as inseridas (sinais_jev com p_sim; p_filtro_ok batendo com
     o banco), sem passar do teto;
  5. o fim da rodada numa CÓPIA de teste com o Execute do W10 LIGADO (PNCP numa
     porta fechada, um termo: nada lido, nada gravado em licitacoes, Jev nem
     roda): seco e `auto_processar = false` barram; a rodada que grava chama o
     W10 de verdade, que só alcança a ALMOFADA de licitações de teste
     (00000000000000-1-00093x, prioridade 50: ocupam as 4 vagas do
     fn_reivindicar, a fila real nunca é tocada). O `orcamento` não é mexido.

Senhas saem do docker/.env pelo código e nunca aparecem em assert/print. Sem a
stack de pé, os testes são PULADOS com o motivo.

    python -m pytest n8n/tests/test_w01.py -v -s
    # sem PNCP de verdade e sem Jev (as rodadas reais 3 e 4 leem o PNCP inteiro e pagam o Jev):
    python -m pytest n8n/tests/test_w01.py -v -s -k "json or instancia or fim_da_rodada or em_producao"
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

import cliente  # noqa: E402
import importar  # noqa: E402

psycopg = pytest.importorskip("psycopg")

NOME = "W01 Descoberta"
# FOPA_W01_JSON aponta um rascunho durante a construção; o padrão é o versionado.
ARQ = Path(os.environ.get("FOPA_W01_JSON") or importar.PASTA_WORKFLOWS / "W01.json")
PNCP = "https://pncp.gov.br/api/search/"
TERMINAIS = {"success", "error", "crashed", "canceled"}
TETO_JEV_TESTE = 100          # gatilho Manual: é a rodada de teste (o Jev custa ~US$ 0,00002/chamada)


def criterio_escopo_do_worker() -> str:
    """O critério vigente mora em api/jev.py (o worker grava 'escopo-' + ele): o teste não fixa versão."""
    import re
    txt = (AQUI.parent.parent / "api" / "jev.py").read_text(encoding="utf-8")
    return "escopo-" + re.search(r'^CRITERIO_ESCOPO = "([^"]+)"', txt, re.M).group(1)


# ------------------------------------------------------------------ ajudantes
def disparar(api, wid: str, gatilho: str, itens: list) -> str:
    """Execução manual pela REST interna a partir do gatilho escolhido, com os itens dados.

    É o único jeito de exercitar o gatilho "When Executed by Another Workflow" sem
    um fluxo-pai (o W11 ainda não existe): `triggerToStartFrom.data` vira a saída
    do gatilho, exatamente o `{seco, execucao_id}` que o W11 passará.
    """
    wf = api.interna("GET", "/rest/workflows/" + wid)
    corpo = {
        "workflowData": {**wf, "pinData": {}},
        "runData": {},
        "startNodes": [],
        "triggerToStartFrom": {
            "name": gatilho,
            "data": {"startTime": 0, "executionTime": 0, "source": [], "executionStatus": "success",
                     "data": {"main": [[{"json": j} for j in itens]]}},
        },
    }
    return str(api.interna("POST", "/rest/workflows/%s/run" % wid, corpo)["executionId"])


def esperar(api, eid: str, timeout: int = 1500) -> dict:
    """Espera pela API pública SEM dados (a execução do W01 tem megabytes) e só no fim pede tudo."""
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        time.sleep(4)
        e = api.publica("GET", "/executions/%s?includeData=false" % eid, ok=(200, 404))
        if isinstance(e, dict) and e.get("status") in TERMINAIS:
            return api.publica("GET", "/executions/%s?includeData=true" % eid)
    raise AssertionError("execução %s não terminou em %d s" % (eid, timeout))


def rodar(api, wid: str, gatilho: str, itens: list | None = None, timeout: int = 1500) -> tuple[str, dict, dict]:
    eid = disparar(api, wid, gatilho, itens or [{}])
    e = esperar(api, eid, timeout)
    rd = e["data"]["resultData"]
    erro = (rd.get("error") or {}).get("message")
    assert e["status"] == "success", "execução %s terminou %s: %s" % (eid, e["status"], erro)
    saida = rd["runData"]["Saída da rodada"][-1]["data"]["main"][0][0]["json"]
    return eid, saida, rd["runData"]


def fotografia(pg, controles=None) -> dict:
    """As marcas que SÓ o W01 põe numa licitação (visto_em, carimbo do PNCP). O estado fica de fora: outras
    frentes (W2x) mudam estado em paralelo, e a retificação do W01 também troca o carimbo."""
    sql = "SELECT controle, visto_em, atualizado_pncp FROM licitacoes"
    linhas = (pg.execute(sql + " WHERE controle = ANY(%s)", (list(controles),)).fetchall()
              if controles is not None else pg.execute(sql).fetchall())
    return {c: (v, a) for c, v, a in linhas}


def controles_vistos(pg, execucao_id) -> set:
    return {c for (c,) in pg.execute(
        "SELECT DISTINCT i ->> 'numero_controle_pncp' FROM buscas_paginas b, "
        "jsonb_array_elements(CASE WHEN jsonb_typeof(b.itens) = 'array' THEN b.itens ELSE '[]'::jsonb END) i "
        "WHERE b.workflow_execucao_id = %s AND NOT b.falhou", (execucao_id,)).fetchall()}


def inseridas_pelo_w01_desde(pg, instante) -> list:
    """Outras frentes criam licitações em paralelo (origem manual/corpus): conta só as do n8n."""
    return [c for (c,) in pg.execute("SELECT controle FROM licitacoes WHERE criado_em >= %s AND origem = 'n8n'",
                                     (instante,)).fetchall()]


def marcas_mudadas(antes: dict, depois: dict) -> list:
    return sorted(c for c, v in antes.items() if c in depois and depois[c] != v)


def eventos_w01_desde(pg, instante) -> int:
    # O motivo exato da retificação do fn_registrar_vista (db/020); "W01: regra de escopo reaplicada" é do
    # fn_aplicar_escopo (db/019), que outra frente roda em paralelo.
    return pg.execute("SELECT count(*) FROM licitacao_eventos WHERE em >= %s "
                      "AND motivo = 'W01: carimbo do PNCP mudou'", (instante,)).fetchone()[0]


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def pg():
    env = cliente.ler_env()
    url = "postgresql://postgres:%s@127.0.0.1:5433/fopa" % env["POSTGRES_PASSWORD"]
    try:
        con = psycopg.connect(url, connect_timeout=5, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("fopa-postgres fora do ar em 127.0.0.1:5433")
    yield con
    con.close()


@pytest.fixture(scope="module")
def api():
    if not cliente.no_ar():
        pytest.skip("fopa-n8n fora do ar em %s (docker compose up -d fopa-n8n)" % cliente.base())
    return cliente.N8n.autenticado()


def _pasta_so_w01() -> Path:
    d = Path(tempfile.mkdtemp(prefix="w01_"))
    shutil.copy(ARQ, d / "W01.json")
    return d


@pytest.fixture(scope="module")
def w01(api):
    """Sobe SÓ o W01 versionado (os outros fluxos da pasta são de outras frentes) e devolve o id."""
    if not ARQ.exists():
        pytest.skip("%s não existe" % ARQ)
    rel = importar.importar(_pasta_so_w01(), api)
    assert rel[NOME]["publicado"] is True, rel
    return rel[NOME]["id"]


# ------------------------------------------------------------------ 0. o JSON
def test_json_convencoes_e_recorte_na_consulta():
    if not ARQ.exists():
        pytest.skip("%s não existe" % ARQ)
    wf = json.loads(ARQ.read_text(encoding="utf-8"))
    nos = {n["name"]: n for n in wf["nodes"]}
    s = wf["settings"]
    assert s["executionOrder"] == "v1" and s["timezone"] == "America/Sao_Paulo"
    assert s["errorWorkflow"] == "{{WF:W90}}", "W01 é raiz: erro vai ao W90"

    # Gatilhos: agenda seg-sex 06:00, Manual, e o do W11 com {seco, execucao_id}.
    agenda = [n for n in nos.values() if n["type"] == "n8n-nodes-base.scheduleTrigger"]
    assert [a["parameters"]["rule"]["interval"][0]["expression"] for a in agenda] == ["0 6 * * 1-5"]
    assert any(n["type"] == "n8n-nodes-base.manualTrigger" for n in nos.values())
    sub = [n for n in nos.values() if n["type"] == "n8n-nodes-base.executeWorkflowTrigger"]
    assert len(sub) == 1
    campos = {v["name"]: v["type"] for v in sub[0]["parameters"]["workflowInputs"]["values"]}
    assert campos == {"seco": "boolean", "execucao_id": "number"}

    # PNCP: timeout explícito, Never Error, saída de erro, e NUNCA a paginação embutida.
    pncp = [n for n in nos.values() if n["name"].startswith("GET página")]
    assert len(pncp) == 2
    for n in pncp:
        o = n["parameters"]["options"]
        assert o["timeout"] == 60000
        assert o["response"]["response"] == {"fullResponse": True, "neverError": True}
        assert n["onError"] == "continueErrorOutput"
        assert "pagination" not in o
        cab = {h["name"]: h["value"] for h in n["parameters"]["headerParameters"]["parameters"]}
        assert cab["User-Agent"].startswith("FOPA/")
    assert len([n for n in nos.values() if n["type"] == "n8n-nodes-base.splitInBatches"]) == 2

    # O recorte está NA CONSULTA: anos=ano_minimo..ano atual e a consulta das abertas sem ano.
    js = nos["Página 1 de cada consulta"]["parameters"]["jsCode"]
    assert "anos: anos.join('|')" in js and "status: 'todos'" in js
    assert "status: 'recebendo_proposta'" in js and "[abertas]" in js
    assert "tipos_documento: 'edital'" in js and "ordenacao: '-data'" in js
    assert "fn_ano_minimo()" in nos["Termos ativos"]["parameters"]["query"]
    assert "'https://pncp.gov.br/api/search/'" in nos["Parâmetros da rodada"]["parameters"]["jsCode"]

    # Uma chamada de fn_registrar_vista por item (o nó roda uma consulta por item).
    reg = nos["Registrar vista"]["parameters"]
    assert "fn_registrar_vista(" in reg["query"] and reg["options"]["queryBatching"] == "independently"

    # Credenciais só por placeholder; Jev e worker por Header Auth.
    bruto = json.dumps(wf, ensure_ascii=False)
    for n in nos.values():
        for tipo, ref in (n.get("credentials") or {}).items():
            assert ref["id"] == "{{CRED:%s}}" % ref["name"], n["name"]
    assert nos["Jev (TypeSafe)"]["credentials"]["httpHeaderAuth"]["name"] == "jev"
    assert nos["Jev (TypeSafe)"]["parameters"]["options"]["batching"]["batch"]["batchSize"] <= 10
    assert nos["Regra de escopo (worker)"]["credentials"]["httpHeaderAuth"]["name"] == "worker"

    # Fim da rodada → W10 (plano §5 W01 passo 19): IF !seco && auto_processar → Execute W10 sem esperar.
    # O Execute sai DESLIGADO: o orçamento vigente tem auto_processar=true e a agenda roda seg-sex 06:00;
    # ligado, a fila real iria ao W20 com o provedor simulado. A ativação da esteira depende de aprovação do gestor
    # do projeto.
    exe = [n for n in nos.values() if n["type"] == "n8n-nodes-base.executeWorkflow"]
    assert [n["name"] for n in exe] == ["W10 Fila (sem esperar)"]
    w10 = exe[0]
    assert w10.get("disabled") is True, "o Execute do W10 tem de sair desligado"
    p = w10["parameters"]
    assert p["workflowId"]["value"] == "{{WF:W10}}" and p["mode"] == "once"
    assert p["options"]["waitForSubWorkflow"] is False, "o W01 não espera a fila"
    se = nos["Empurrar a fila?"]
    assert not se.get("disabled"), "IF desligado deixaria o item passar direto para o W10"
    (cond,) = se["parameters"]["conditions"]["conditions"]
    assert cond["leftValue"] == "={{ !$('Parâmetros da rodada').first().json.seco && $json.auto_processar === true }}"
    assert cond["operator"] == {"type": "boolean", "operation": "true", "singleValue": True}
    orc = nos["Orçamento: auto_processar?"]
    assert "COALESCE(o.auto_processar, true) AS auto_processar" in orc["parameters"]["query"]
    assert "LEFT JOIN orcamento o ON o.vigente" in orc["parameters"]["query"]
    assert not orc.get("disabled") and orc["credentials"]["postgres"]["name"] == "fopa-postgres (n8n_rw)"
    con = wf["connections"]
    assert con["Orçamento: auto_processar?"]["main"] == [[{"node": "Empurrar a fila?", "type": "main", "index": 0}]]
    # Só a saída "true" vai ao W10; a "false" não tem ligação.
    assert con["Empurrar a fila?"]["main"] == [[{"node": "W10 Fila (sem esperar)", "type": "main", "index": 0}]]
    assert {c["node"] for c in con["Fechar execução"]["main"][0]} == {"Orçamento: auto_processar?", "Saída da rodada"}
    # executionOrder v1: o ramo de cima roda primeiro; a Saída fica embaixo e é o último nó (o que o fluxo devolve).
    assert nos["Orçamento: auto_processar?"]["position"][1] < nos["Saída da rodada"]["position"][1]
    assert "W10 a construir" not in nos
    nota = [n["parameters"]["content"] for n in nos.values() if n["name"].startswith("Fim da rodada → W10")]
    assert len(nota) == 1 and "DESLIGADO" in nota[0] and "Como ligar" in nota[0] and "auto_processar" in nota[0]
    assert "anthropic" not in bruto.lower() and "openai" not in bruto.lower()
    # Quem avalia lê o canvas: nota com 'regra — script:linha'.
    notas = [n["parameters"]["content"] for n in nos.values() if n["type"] == "n8n-nodes-base.stickyNote"]
    assert any("—" in c and ".py:" in c for c in notas)



def _rodar_no(codigo: str, nos: dict, entrada: dict) -> list:
    """Roda o jsCode de um Code node no Node do fopa-n8n. `nos` é {nome: [itens]}: nó ausente = não executado
    ($(nome) lança, como no n8n), então `isExecuted` e `.all()` se comportam como no fluxo."""
    if not shutil.which("docker"):
        pytest.skip("docker ausente: não há Node para rodar o Code node")
    harness = (
        "let s='';process.stdin.on('data',c=>s+=c).on('end',()=>{const c=JSON.parse(s);"
        "const $=(n)=>{if(!(n in c.nos))throw new Error('nó não executado: '+n);const a=c.nos[n];"
        "return {isExecuted:true,first:()=>({json:a[0]}),all:()=>a.map(j=>({json:j}))};};"
        "const $input={first:()=>({json:c.entrada}),all:()=>[{json:c.entrada}]};"
        "const f=new Function('$','$input','$env','$workflow','$execution',c.codigo);"
        "process.stdout.write(JSON.stringify(f($,$input,{WEBHOOK_URL:'http://n8n/'},{id:'wf'},{id:'1'})));});")
    corpo = json.dumps({"codigo": codigo, "nos": nos, "entrada": entrada})
    r = subprocess.run(["docker", "exec", "-i", "fopa-n8n", "node", "-e", harness], input=corpo.encode("utf-8"),
                       capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-800:]
    return json.loads(r.stdout.decode("utf-8"))


def test_resumo_guarda_a_lista_das_novas_para_a_tela():
    # O "Verificar agora" do site é seco: as novas não entram em licitacoes, e a tela só mostrava a
    # CONTAGEM. O resumo guarda até 50, com município, objeto, prazo e link, em contadores.novas_lista.
    wf = json.loads((AQUI.parent / "workflows" / "W01.json").read_text(encoding="utf-8"))
    (codigo,) = [n["parameters"]["jsCode"] for n in wf["nodes"] if n["name"] == "Resumo da rodada"]
    novas = ["12345678000199-1-%06d/2026" % n for n in range(1, 56)]
    conhecida = "12345678000199-1-000900/2026"
    nos = {
        "Parâmetros da rodada": [{"seco": True, "hoje": "2026-09-24", "jev_teto": 300, "inicio": "x"}],
        "Abrir execução": [{"execucao_id": 7}],
        "Registrar vista": [{"acao": "inserir_nova", "controle": c} for c in novas]
                           + [{"acao": "visto", "controle": conhecida}],
        "Normalizar": [{"controle": c, "payload": {
            "municipio": "Cidade %d" % i, "uf": "SP", "modalidade": "Pregão - Eletrônico",
            "objeto": "Cessão da folha de pagamento " + "x" * 300, "fim_prazo": "2026-10-15T09:00:00",
            "link": "https://pncp.gov.br/app/editais/12345678000199/2026/%d" % (i + 1)}}
            for i, c in enumerate(novas + [conhecida])],
        "Itens únicos da rodada": [{"controle": c} for c in novas + [conhecida]],
    }
    cons = {"paginas_lidas": 3, "lidos": 56, "consultas_falhas": 0, "n_consultas": 12, "consultas": [], "cego": False}
    (r,) = _rodar_no(codigo, nos, cons)
    cont = r["json"]["contadores"]
    assert cont["novas"] == 55 and cont["conhecidas"] == 1
    lista = cont["novas_lista"]
    assert [x["controle"] for x in lista] == novas[:50], "até 50, na ordem da rodada; a contagem segue sendo o total"
    assert lista[0] == {"controle": novas[0], "municipio": "Cidade 0", "uf": "SP", "modalidade": "Pregão - Eletrônico",
                        "objeto": ("Cessão da folha de pagamento " + "x" * 300)[:200], "fim_prazo": "2026-10-15T09:00:00",
                        "link": "https://pncp.gov.br/app/editais/12345678000199/2026/1"}
    assert conhecida not in [x["controle"] for x in lista]


def test_resumo_monta_um_aviso_por_licitacao_nova_e_nenhum_na_seca():
    # O 1º dos DOIS e-mails do produto: o aviso de licitação nova que passa no filtro. Um por 'inserir_nova' (dentro
    # do escopo e da janela); a conhecida não avisa; a seca, nada.
    wf = json.loads((AQUI.parent / "workflows" / "W01.json").read_text(encoding="utf-8"))
    (codigo,) = [n["parameters"]["jsCode"] for n in wf["nodes"] if n["name"] == "Resumo da rodada"]
    novas = ["12345678000199-1-000001/2026", "12345678000199-1-000002/2026"]
    conhecida = "12345678000199-1-000900/2026"
    fora = "12345678000199-1-000901/2026"

    def nos(seco):
        return {
            "Parâmetros da rodada": [{"seco": seco, "hoje": "2026-09-25", "jev_teto": 300, "inicio": "x"}],
            "Abrir execução": [{"execucao_id": 7}],
            "Registrar vista": [{"acao": "inserir_nova", "controle": c} for c in novas]
                               + [{"acao": "visto", "controle": conhecida},
                                  {"acao": "inserir_fora_escopo", "controle": fora}],
            "Normalizar": [{"controle": c, "payload": {
                "municipio": "Cidade %d" % i, "uf": "SP", "orgao": "Prefeitura de Cidade %d" % i,
                "modalidade": "Pregão - Eletrônico", "objeto": "Cessão da folha de pagamento dos servidores",
                "fim_prazo": "2026-10-15T12:00:00Z", "link": "https://pncp.gov.br/app/editais/12345678000199/2026/%d" % i}}
                for i, c in enumerate(novas + [conhecida, fora])],
            "Itens únicos da rodada": [{"controle": c} for c in novas + [conhecida, fora]],
        }

    cons = {"paginas_lidas": 1, "lidos": 4, "consultas_falhas": 0, "n_consultas": 12, "consultas": [], "cego": False}
    (r,) = _rodar_no(codigo, nos(False), cons)
    avisos = r["json"]["avisos"]
    assert [a["controle"] for a in avisos] == novas
    assert avisos[0]["assunto"] == "[FOPA] Licitação nova de folha: Cidade 0/SP · Pregão - Eletrônico"
    corpo = avisos[0]["corpo_html"]
    assert "Prefeitura de Cidade 0" in corpo and "Cessão da folha de pagamento" in corpo and "15/10/2026" in corpo
    assert 'href="/licitacao/12345678000199-1-000001-2026"' in corpo          # sem FOPA_SITE_PUBLIC_URL: relativo
    assert 'href="https://pncp.gov.br/app/editais/12345678000199/2026/0"' in corpo
    assert "assunto" not in r["json"] and "corpo_html" not in r["json"]       # o e-mail de coleta cega saiu
    (seca,) = _rodar_no(codigo, nos(True), cons)
    assert seca["json"]["avisos"] == []


def test_instancia_igual_ao_versionado(api, w01):
    """O que roda na instância é o que está no git (2ª importação não muda nada)."""
    rel = importar.importar(_pasta_so_w01(), api)
    assert rel[NOME] == {"id": w01, "acao": "inalterado", "publicado": True, "avisos": []}
    # E o que está publicado tem o Execute do W10 desligado, apontando para o W10 da instância.
    no_ar = api.workflow(w01)
    exe = next(n for n in no_ar["nodes"] if n["name"] == "W10 Fila (sem esperar)")
    ids = {importar.codigo(w["name"]): w["id"] for w in api.listar_workflows() if importar.codigo(w["name"])}
    assert exe.get("disabled") is True and exe["parameters"]["workflowId"]["value"] == ids["W10"]
    assert no_ar["active"] is True and no_ar["activeVersionId"] == no_ar["versionId"]


# ------------------------------------------------------------------ 1. seco
def test_seco_nao_grava_licitacoes_usa_linha_do_w11_e_lista_novas(api, w01, pg):
    # O W11 abre a linha ANTES e devolve o id ao site (plano §5 W11): o W01 tem de usar esta.
    (eid_w11,) = pg.execute(
        "INSERT INTO execucoes_workflow (workflow, gatilho, status, argumentos) "
        "VALUES ('W01', 'W11', 'em_curso', '{\"solicitado_por\": \"test_w01\"}') RETURNING id").fetchone()
    foto = fotografia(pg)
    inicio = pg.execute("SELECT now()").fetchone()[0]

    eid, saida, runs = rodar(api, w01, "Chamado por outro fluxo", [{"seco": True, "execucao_id": eid_w11}])

    print("\n[seco] execução n8n %s · linha %s · %s" % (eid, eid_w11, json.dumps(
        {k: saida[k] for k in ("vistas", "por_acao", "cego")}, ensure_ascii=False)))
    print("[seco] novas (%d): %s" % (len(saida["novas"]), saida["novas"]))
    assert saida["seco"] is True
    assert str(saida["execucao_id"]) == str(eid_w11), "o W01 abriu outra linha em vez de usar a do W11"
    # Nada em licitacoes: nem linha nova, nem visto_em, nem carimbo, nem evento de retificação.
    assert inseridas_pelo_w01_desde(pg, inicio) == []
    vistos = controles_vistos(pg, eid_w11)
    assert vistos, "nenhuma página lida: o PNCP caiu inteiro? (ver buscas)"
    mudou = marcas_mudadas(foto, fotografia(pg))
    assert not mudou, "seco escreveu em licitacoes: %s" % mudou[:5]
    assert eventos_w01_desde(pg, inicio) == 0
    assert "Jev (TypeSafe)" not in runs and "Jev: montar corpos (worker)" not in runs, "seco chamou o Jev"
    assert saida["jev"]["chamadas"] == 0
    # As novas foram LISTADAS, não gravadas.
    assert len(saida["novas"]) == saida["por_acao"].get("inserir_nova", 0)
    if saida["novas"]:
        assert pg.execute("SELECT count(*) FROM licitacoes WHERE controle = ANY(%s)",
                          (saida["novas"],)).fetchone()[0] == 0
    # A linha do W11 foi usada e fechada; esta execução não abriu outra (conta só as DELA: outra suíte pode
    # estar rodando o W01 ao mesmo tempo).
    assert pg.execute("SELECT count(*) FROM execucoes_workflow WHERE workflow = 'W01' AND n8n_execution_id = %s "
                      "AND id <> %s", (eid, eid_w11)).fetchone()[0] == 0
    st, cego, cont, n8n_id, gat = pg.execute(
        "SELECT status, cego, contadores, n8n_execution_id, gatilho FROM execucoes_workflow WHERE id = %s",
        (eid_w11,)).fetchone()
    assert (st, cego, n8n_id, gat) == ("ok", False, eid, "W11")
    assert cont["seco"] is True and cont["vistas"] == saida["vistas"]
    buscas = pg.execute("SELECT termo FROM buscas WHERE workflow_execucao_id = %s", (eid_w11,)).fetchall()
    termos_ativos = pg.execute("SELECT count(*) FROM termos WHERE ativo").fetchone()[0]
    assert len(buscas) == 2 * termos_ativos
    assert all(t.endswith(" [2026]") or t.endswith(" [abertas]") for (t,) in buscas)
    assert pg.execute("SELECT count(*) FROM buscas_paginas WHERE workflow_execucao_id = %s",
                      (eid_w11,)).fetchone()[0] >= 2 * termos_ativos


# ------------------------------------------------------------------ 2. cego
def test_pncp_inalcancavel_fica_cego_sem_email_e_sem_tocar_licitacoes(api, w01, pg):
    """Cópia de TESTE do fluxo com a URL do PNCP numa porta fechada (127.0.0.1:9 no container)."""
    wf = json.loads(ARQ.read_text(encoding="utf-8"))
    bruto = json.dumps(wf, ensure_ascii=False)
    assert bruto.count(PNCP) == 1, "a URL base do PNCP deveria morar num lugar só"
    teste = json.loads(bruto.replace(PNCP, "http://127.0.0.1:9/api/search/"))
    # Resolve placeholders como o importar e tira o Error Workflow (a cópia não alarma o W90).
    ids_wf = {importar.codigo(w["name"]): w["id"] for w in api.listar_workflows() if importar.codigo(w["name"])}
    ids_cred = {c["name"]: c["id"] for c in api.listar_credenciais()}
    teste = importar.resolver(teste, ids_wf, ids_cred, [])
    teste["name"] = "TESTE cego do W01 (apagar)"      # sem prefixo Wnn: o exportar.py ignora
    teste["settings"].pop("errorWorkflow", None)
    criado = api.publica("POST", "/workflows", importar.corpo(teste))
    try:
        foto = fotografia(pg)
        inicio = pg.execute("SELECT now()").fetchone()[0]

        eid, saida, runs = rodar(api, criado["id"], "Manual", [{}], timeout=900)

        print("\n[cego] execução n8n %s · linha %s" % (eid, saida["execucao_id"]))
        assert saida["cego"] is True
        assert saida["vistas"] == 0 and saida["novas"] == [] and saida["jev"]["chamadas"] == 0
        assert all(c["falhou"] and c["pagina_falha"] == 1 and "rede" in (c["motivo"] or "")
                   for c in saida["consultas"])
        cego, st, cont = pg.execute("SELECT cego, status, contadores FROM execucoes_workflow WHERE id = %s",
                                    (saida["execucao_id"],)).fetchone()
        assert cego is True and st == "ok" and cont["consultas_falhas"] == len(saida["consultas"])
        assert pg.execute("SELECT bool_and(falhou), count(*) FROM buscas WHERE workflow_execucao_id = %s",
                          (saida["execucao_id"],)).fetchone()[0] is True
        # A coleta cega fica em execucoes_workflow.cego (o site mostra); e-mail, não: o produto manda só DOIS
        # (licitação nova e a extração do botão; db/038-039).
        assert saida["email_cego_id"] is None and saida["emails_novas"] == 0
        assert pg.execute("SELECT count(*) FROM emails WHERE em >= %s AND controle IS NULL", (inicio,)).fetchone()[0] == 0
        # Nenhuma licitação tocada.
        assert inseridas_pelo_w01_desde(pg, inicio) == []
        assert marcas_mudadas(foto, fotografia(pg)) == []
        assert eventos_w01_desde(pg, inicio) == 0
    finally:
        # A linha W01 da rodada cega (com buscas/buscas_paginas) sai antes da cópia: as execuções vão junto com ela,
        # e é por elas que a linha é achada.
        _apagar_rodadas_da_copia(api, pg, [criado["id"]])
        api.publica("DELETE", "/workflows/" + criado["id"])


# ------------------------------------------------------------------ 2b. cego em PRODUÇÃO, com o W90 armado
# Plano §11.3, teste negativo nas duas variantes: (i) erro de rede (porta fechada no lugar do pncp.gov.br) e (ii) o
# PNCP respondendo 429 com corpo HTML (é assim que ele limita: sem Retry-After, `body` string). Nas duas: cego=true,
# nenhum e-mail (db/038-039), nenhuma licitação marcada e NENHUM "[ERRO]" do W90.
#
# O teste 2 acima roda uma cópia SEM Error Workflow pelo Manual — e execução manual nem dispara o Error Trigger
# (limitação do n8n): o "nenhum [ERRO]" não se prova assim. Aqui a cópia MANTÉM o Error Workflow = W90 de verdade e
# roda em PRODUÇÃO (um Webhook no lugar da agenda). Se a rodada cega lançasse exceção em algum nó, o W90 gravaria o
# [ERRO]; test_nucleo.py::test_w20_em_producao_folha_que_morre_chama_o_w90_uma_vez prova que, nessa montagem, ele
# grava. O 429 vem de um fluxo FALSO de teste no próprio fopa-n8n (Webhook → 429 text/html): nenhum PNCP é tocado.
PORTA_N8N_NO_CONTAINER = "http://127.0.0.1:5678/webhook/"      # a 5679 é a do host; dentro do container é 5678
HTML_429 = ("<!DOCTYPE html><html><head><title>429 Too Many Requests</title></head><body><center>"
            "<h1>429 Too Many Requests</h1></center><hr><center>nginx</center></body></html>")


def _pncp_429_falso(nome: str, caminho: str) -> dict:
    """Fluxo FALSO de teste (sem Error Workflow): GET no caminho → HTTP 429 com HTML, como o PNCP quando limita."""
    return {
        "name": nome,
        "nodes": [
            {"parameters": {"httpMethod": "GET", "path": caminho, "responseMode": "responseNode", "options": {}},
             "id": str(uuid.uuid4()), "name": "GET do W01", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
             "position": [0, 0], "webhookId": str(uuid.uuid4())},
            {"parameters": {"respondWith": "text", "responseBody": HTML_429,
                            "options": {"responseCode": 429, "responseHeaders": {"entries": [
                                {"name": "Content-Type", "value": "text/html; charset=utf-8"}]}}},
             "id": str(uuid.uuid4()), "name": "429 em HTML", "type": "n8n-nodes-base.respondToWebhook",
             "typeVersion": 1.1, "position": [300, 0]},
        ],
        "connections": {"GET do W01": {"main": [[{"node": "429 em HTML", "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1"},
    }


def _copia_cega_em_producao(api, nome: str, base_pncp: str, caminho: str) -> dict:
    """Cópia de TESTE do W01 (sem prefixo Wnn; apagada no fim) com Error Workflow = W90, disparada por WEBHOOK.

    - a URL do PNCP vira `base_pncp` (porta fechada ou o fluxo falso do 429);
    - um termo só (as mesmas 2 consultas por termo; rodada de 1-2 min);
    - a AGENDA sai da cópia: publicada, ela rodaria seg-sex 06:00 se o teste morresse antes de apagá-la;
    - o Webhook entra ligado ao mesmo 1º nó. Sem o gatilho de sub-fluxo executado, 'Parâmetros da rodada' cai em
      gatilho 'manual' → seco=false: é a rodada que GRAVA (a que enfileira o 'cego'), mas sem PNCP nada é lido;
    - o Execute do W10 continua DESLIGADO, como no versionado."""
    wf = json.loads(ARQ.read_text(encoding="utf-8"))
    bruto = json.dumps(wf, ensure_ascii=False)
    assert bruto.count(PNCP) == 1, "a URL base do PNCP deveria morar num lugar só"
    teste = json.loads(bruto.replace(PNCP, base_pncp))
    nos = {n["name"]: n for n in teste["nodes"]}
    q = nos["Termos ativos"]["parameters"]["query"]
    assert q.count(UM_TERMO[0]) == 1
    nos["Termos ativos"]["parameters"]["query"] = q.replace(*UM_TERMO)
    assert nos["W10 Fila (sem esperar)"].get("disabled") is True
    (agenda,) = [n for n in teste["nodes"] if n["type"] == "n8n-nodes-base.scheduleTrigger"]
    teste["nodes"].remove(agenda)
    teste["connections"].pop(agenda["name"])
    teste["nodes"].append({"parameters": {"httpMethod": "POST", "path": caminho, "responseMode": "onReceived",
                                          "options": {}},
                           "id": str(uuid.uuid4()), "name": "POST teste (produção)", "type": "n8n-nodes-base.webhook",
                           "typeVersion": 2, "position": [0, 600], "webhookId": str(uuid.uuid4())})
    teste["connections"]["POST teste (produção)"] = {
        "main": [[{"node": "Parâmetros da rodada", "type": "main", "index": 0}]]}
    ids_wf = {importar.codigo(w["name"]): w["id"] for w in api.listar_workflows() if importar.codigo(w["name"])}
    ids_cred = {c["name"]: c["id"] for c in api.listar_credenciais()}
    teste = importar.resolver(teste, ids_wf, ids_cred, [])
    teste["name"] = nome
    assert teste["settings"]["errorWorkflow"] == ids_wf["W90"], "a cópia alarma o W90 de verdade"
    assert "pncp.gov.br/api" not in json.dumps(teste, ensure_ascii=False)
    criado = api.publica("POST", "/workflows", importar.corpo(teste))
    return criado


def _execucoes_de(api, wid: str, depois_de: int) -> list:
    d = api.publica("GET", "/executions?workflowId=%s&limit=50" % wid).get("data") or []
    return sorted(({"id": str(e["id"]), "status": e["status"], "mode": e["mode"]} for e in d
                   if int(e["id"]) > depois_de), key=lambda e: int(e["id"]))


@pytest.mark.parametrize("variante", ["porta_fechada", "429_html"])
def test_pncp_fora_em_producao_fica_cego_sem_erro_do_w90(api, w01, pg, variante):
    tag = uuid.uuid4().hex[:8]
    nome = "TESTE cego do W01 em produção %s %s (apagar)" % (variante, tag)
    falso, copia = None, None
    try:
        if variante == "429_html":
            caminho_falso = "teste-pncp-429-%s" % tag
            falso = api.publica("POST", "/workflows", _pncp_429_falso("TESTE PNCP 429 falso %s (apagar)" % tag,
                                                                       caminho_falso))
            importar.publicar(api, falso["id"])
            base = PORTA_N8N_NO_CONTAINER + caminho_falso        # a consulta vira <base>?q=...
        else:
            base = PORTA_FECHADA
        caminho = "teste-w01-cego-%s" % tag
        copia = _copia_cega_em_producao(api, nome, base, caminho)
        importar.publicar(api, copia["id"])
        ids_wf = {importar.codigo(w["name"]): w["id"] for w in api.listar_workflows() if importar.codigo(w["name"])}
        assert (api.workflow(copia["id"])["settings"] or {}).get("errorWorkflow") == ids_wf["W90"]
        foto = fotografia(pg)
        inicio = pg.execute("SELECT now()").fetchone()[0]
        d = api.publica("GET", "/executions?limit=1").get("data") or []
        antes = int(d[0]["id"]) if d else 0

        req = urllib.request.Request("%s/webhook/%s" % (cliente.base(), caminho), data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            assert r.status == 200

        (ex,) = _esperar(lambda: (lambda x: x if x and all(e["status"] in TERMINAIS for e in x) else None)(
            _execucoes_de(api, copia["id"], antes)), 600, "a rodada da cópia terminar")
        e = api.publica("GET", "/executions/%s?includeData=true" % ex["id"])
        rd = e["data"]["resultData"]
        assert (ex["mode"], ex["status"]) == ("webhook", "success"), (ex, (rd.get("error") or {}).get("message"))
        saida = rd["runData"]["Saída da rodada"][-1]["data"]["main"][0][0]["json"]
        time.sleep(5)          # um W90 disparado pela cópia já teria aparecido
        w90 = _execucoes_de(api, ids_wf["W90"], antes)
        erros = pg.execute("SELECT id, assunto FROM emails WHERE tipo = 'erro' AND em >= %s", (inicio,)).fetchall()
        hits = _execucoes_de(api, falso["id"], antes) if falso else []
        print("\n[cego em produção · %s] execução n8n %s (%s) · linha %s · e-mail cego %s · W90 %s · [ERRO] %s · "
              "chamadas ao PNCP falso %s" % (variante, ex["id"], ex["mode"], saida["execucao_id"], saida["email_cego_id"],
                                             w90, erros, len(hits)))
        print("[cego em produção · %s] motivos: %s" % (variante, [c["motivo"] for c in saida["consultas"]]))

        # Cega de verdade: nenhuma consulta terminou, nada lido, Jev nem roda.
        assert saida["cego"] is True and saida["seco"] is False
        assert saida["vistas"] == 0 and saida["novas"] == [] and saida["jev"]["chamadas"] == 0
        assert len(saida["consultas"]) == 2 and all(c["falhou"] and c["pagina_falha"] == 1 for c in saida["consultas"])
        if variante == "429_html":
            # 429 → espera 30 s → UMA nova tentativa → 429 de novo: a página falha como 'limite', não como rede.
            assert all(c["motivo"] == "1ª: HTTP 429 | 2ª: HTTP 429" for c in saida["consultas"]), saida["consultas"]
            assert len(hits) == 4 and all(h["status"] == "success" for h in hits), "2 consultas × 2 tentativas"
        else:
            assert all("rede" in (c["motivo"] or "") for c in saida["consultas"])
        cego, st, n8n_id = pg.execute("SELECT cego, status, n8n_execution_id FROM execucoes_workflow WHERE id = %s",
                                      (saida["execucao_id"],)).fetchone()
        assert (cego, st, n8n_id) == (True, "ok", ex["id"])
        assert saida["email_cego_id"] is None          # e-mail de coleta cega saiu do produto (db/038-039)
        # Nenhuma licitação tocada.
        assert inseridas_pelo_w01_desde(pg, inicio) == []
        assert marcas_mudadas(foto, fotografia(pg)) == []
        assert eventos_w01_desde(pg, inicio) == 0
        # E nenhum [ERRO]: a cópia com o W90 armado, em produção, não lançou nada.
        assert w90 == [], "o W90 disparou numa rodada cega: %s" % w90
        assert erros == [], "e-mail [ERRO] numa rodada cega: %s" % erros
        assert not pg.execute("SELECT 1 FROM execucoes_workflow WHERE gatilho = 'erro' AND workflow = %s",
                              (nome,)).fetchone()
    finally:
        if copia:
            _apagar_rodadas_da_copia(api, pg, [copia["id"]])     # antes de apagar a cópia (as execuções vão junto)
            api.publica("DELETE", "/workflows/" + copia["id"])
        if falso:
            api.publica("DELETE", "/workflows/" + falso["id"])
        # Se o W90 tivesse disparado, o que ele gravou também sai (o assert acima já contou).
        pg.execute("DELETE FROM emails WHERE tipo = 'erro' AND assunto LIKE %s", ("%" + tag + "%",))
        pg.execute("DELETE FROM execucoes_workflow WHERE gatilho = 'erro' AND workflow LIKE %s", ("%" + tag + "%",))


# ------------------------------------------------------------------ 3 e 4. rodada real
@pytest.fixture(scope="module")
def rodadas_reais(api, w01, pg):
    antes_jev = pg.execute("SELECT coalesce(max(id), 0) FROM sinais_jev").fetchone()[0]
    inicio = pg.execute("SELECT now()").fetchone()[0]
    eid1, s1, _ = rodar(api, w01, "Manual")
    meio = pg.execute("SELECT now()").fetchone()[0]
    eid2, s2, _ = rodar(api, w01, "Manual")
    for rot, eid, s in (("1ª", eid1, s1), ("2ª", eid2, s2)):
        print("\n[real %s] execução n8n %s · linha %s · %s" % (rot, eid, s["execucao_id"], json.dumps(
            {k: s[k] for k in ("vistas", "por_acao", "cego", "jev")}, ensure_ascii=False)))
    return {"s1": s1, "s2": s2, "eid1": eid1, "eid2": eid2, "antes_jev": antes_jev, "inicio": inicio,
            "meio": meio}


INSERIR = ("inserir_nova", "inserir_fora_escopo", "inserir_fora_janela")


def test_rodada_real_insere_so_o_recorte_e_a_segunda_nao_insere(rodadas_reais, pg):
    r = rodadas_reais
    s1, s2 = r["s1"], r["s2"]
    assert s1["seco"] is False and s1["cego"] is False
    inseridas1 = sum(s1["por_acao"].get(a, 0) for a in INSERIR)
    novas = pg.execute(
        "SELECT controle, estado::text, origem, fn_no_recorte(fim_prazo, publicado_em), escopo_dentro, escopo_versao "
        "FROM licitacoes WHERE criado_em >= %s AND criado_em < %s AND origem = 'n8n'",
        (r["inicio"], r["meio"])).fetchall()
    assert len(novas) == inseridas1
    fora = [c for c, _, _, recorte, _, _ in novas if recorte is not True]
    assert not fora, "inseriu fora do recorte de 2026: %s" % fora[:5]
    por_estado = {}
    for _, estado, _, _, dentro, versao in novas:
        por_estado[estado] = por_estado.get(estado, 0) + 1
        assert versao, "escopo_versao tem de ir junto (db/019 reavalia por ela)"
    assert por_estado.get("nova", 0) == s1["por_acao"].get("inserir_nova", 0)
    assert por_estado.get("fora_escopo", 0) == s1["por_acao"].get("inserir_fora_escopo", 0)
    assert por_estado.get("fora_janela", 0) == s1["por_acao"].get("inserir_fora_janela", 0)
    assert set(s1["novas"]) == {c for c, e, *_ in novas if e == "nova"}
    # O que não é folha fica de fora: nova só com a regra dizendo dentro.
    assert all(d for _, e, _, _, d, _ in novas if e == "nova")
    print("\n[real] novas de 2026 na fila: %d · fora de escopo guardadas: %d · fora de janela: %d"
          % (por_estado.get("nova", 0), por_estado.get("fora_escopo", 0), por_estado.get("fora_janela", 0)))

    # Idempotente: a 2ª rodada, logo depois, não insere nada que a 1ª já viu.
    vistos1 = controles_vistos(pg, s1["execucao_id"])
    inseridas2 = inseridas_pelo_w01_desde(pg, r["meio"])
    assert all(c not in vistos1 for c in inseridas2), "a 2ª rodada reinseriu o que a 1ª viu"
    assert sum(s2["por_acao"].get(a, 0) for a in INSERIR) == len(inseridas2)
    assert s2["por_acao"].get("visto", 0) > 0 and s2["jev"]["chamadas"] <= len(inseridas2)


def test_jev_pontua_as_inseridas_com_p_filtro_ok(rodadas_reais, pg):
    r = rodadas_reais
    s1 = r["s1"]
    inseridas = s1["por_acao"].get("inserir_nova", 0) + s1["por_acao"].get("inserir_fora_escopo", 0)
    assert s1["jev"]["chamadas"] == min(inseridas, TETO_JEV_TESTE)
    assert s1["jev"]["fora_do_teto"] == max(0, inseridas - TETO_JEV_TESTE)
    if inseridas:
        # Só os sinais das linhas que a 1ª rodada inseriu (um backfill pode escrever em sinais_jev em paralelo).
        j, novas = s1["jev"], s1["novas"]
        onde, args = "s.id > %s AND l.criado_em >= %s AND l.criado_em < %s", (r["antes_jev"], r["inicio"], r["meio"])
    else:
        # Nada novo no PNCP desde a última rodada (é o normal ao repetir a suíte): o Jev não foi chamado, e o
        # que se confere é o que ficou gravado da última rodada do W01 que pontuou.
        ult = pg.execute(
            "SELECT iniciado_em, iniciado_em + duracao_s * interval '1 second', contadores FROM execucoes_workflow"
            " WHERE workflow = 'W01' AND status = 'ok' AND (contadores ->> 'jev_chamadas')::int > 0"
            " ORDER BY id DESC LIMIT 1").fetchone()
        if ult is None:
            pytest.skip("nenhuma rodada do W01 inseriu nada ainda: não há o que o Jev pontuar")
        j = dict(ult[2]["jev"], fora_do_teto=len(ult[2]["jev"]["fora_do_teto"]))
        novas = []
        onde, args = "s.em >= %s AND s.em <= %s", (ult[0], ult[1])
    sinais = pg.execute(
        "SELECT s.controle, s.regra, s.p_sim, s.usd, s.criterio_versao, s.modelo_jev, l.escopo_dentro, l.estado::text,"
        " (CASE WHEN s.regra = 'dentro' THEN s.p_sim ELSE 1 - s.p_sim END)::float8 AS p_filtro_ok"
        " FROM sinais_jev s JOIN licitacoes l USING (controle)"
        " WHERE s.tipo = 'escopo' AND l.origem = 'n8n' AND " + onde, args).fetchall()
    assert sinais, "nenhum sinal do Jev gravado para as inseridas"
    assert len(sinais) == j["chamadas"]
    # Só as que a rodada inseriu (nova e fora de escopo), e as novas primeiro. O estado pode ter andado
    # (W10/W20 levam a nova adiante), por isso a conferência é pela ORIGEM n8n e pela regra gravada.
    assert {c for c, *_ in sinais} >= set(novas[:TETO_JEV_TESTE])
    for controle, regra, p_sim, usd, crit, modelo, dentro, estado, pfo in sinais:
        # A regra que o Jev pontuou é a que decidiu a linha (T25: o Jev não muda escopo_dentro).
        assert regra == ("dentro" if dentro else "fora"), controle
        assert crit.startswith("escopo-v")
        if inseridas:
            assert crit == criterio_escopo_do_worker()
    com_p = [x for x in sinais if x[2] is not None]
    assert len(com_p) == j["com_resposta"] and len(com_p) >= 0.9 * len(sinais), "o Jev respondeu pouco"
    media = round(sum(x[8] for x in com_p) / len(com_p), 4)
    assert j["p_filtro_ok_medio"] == pytest.approx(media, abs=1e-4)
    usd = float(sum(x[3] or 0 for x in sinais))
    assert usd == pytest.approx(j["usd"], abs=1e-7) and usd < 0.01
    print("\n[jev%s] chamadas %d · com resposta %d · p_filtro_ok médio %.4f · candidatas %d · US$ %.6f · fora do teto %d"
          % ("" if inseridas else " (última rodada que pontuou)", j["chamadas"], j["com_resposta"], media,
             len(j["candidatas"]), usd, j["fora_do_teto"]))


# ------------------------------------------------------------------ 5. fim da rodada → W10 (cópia ligada)
ALMOFADA = ["00000000000000-1-%06d/2026" % n for n in range(930, 934)]   # test_nucleo: 92x; test_w10_w11: 95x-99x
PRIO_ALMOFADA = 50
PORTA_FECHADA = "http://127.0.0.1:9/api/search/"
UM_TERMO = ("  FROM termos\n WHERE ativo",
            "  FROM (SELECT * FROM termos WHERE ativo ORDER BY prioridade, termo LIMIT 1) termos\n WHERE ativo")
ORC_DO_BANCO = "COALESCE(o.auto_processar, true) AS auto_processar"


def _copia_com_w10_ligado(api, nome: str, orcamento_diz_nao: bool = False) -> dict:
    """Cópia de TESTE do W01 (sem prefixo Wnn: o exportar.py ignora; apagada no fim) com o Execute do W10 LIGADO.

    Nada nela alcança o mundo: o PNCP fica numa porta fechada (a rodada sai cega: nada lido, nada gravado em
    licitacoes, e sem item inserido o Jev nem roda) e só um termo é consultado (rodada de ~1 min). Com
    `orcamento_diz_nao`, a leitura do orçamento devolve auto_processar=false (o `orcamento` real não é mexido)."""
    wf = json.loads(ARQ.read_text(encoding="utf-8"))
    bruto = json.dumps(wf, ensure_ascii=False)
    assert bruto.count(PNCP) == 1, "a URL base do PNCP deveria morar num lugar só"
    teste = json.loads(bruto.replace(PNCP, PORTA_FECHADA))
    nos = {n["name"]: n for n in teste["nodes"]}
    q = nos["Termos ativos"]["parameters"]["query"]
    assert q.count(UM_TERMO[0]) == 1
    nos["Termos ativos"]["parameters"]["query"] = q.replace(*UM_TERMO)
    assert nos["W10 Fila (sem esperar)"].pop("disabled") is True
    if orcamento_diz_nao:
        q = nos["Orçamento: auto_processar?"]["parameters"]["query"]
        assert q.count(ORC_DO_BANCO) == 1
        nos["Orçamento: auto_processar?"]["parameters"]["query"] = q.replace(ORC_DO_BANCO, "false AS auto_processar")
    ids_wf = {importar.codigo(w["name"]): w["id"] for w in api.listar_workflows() if importar.codigo(w["name"])}
    ids_cred = {c["name"]: c["id"] for c in api.listar_credenciais()}
    teste = importar.resolver(teste, ids_wf, ids_cred, [])
    teste["name"] = nome
    teste["settings"].pop("errorWorkflow", None)            # a cópia não alarma o W90
    # A trava que importa: nenhuma API do PNCP de verdade sobrou na cópia que roda pelo Manual (seco=false). O que
    # resta de "pncp.gov.br" é o link /app/editais/ que o Normalizar monta (texto, não requisição).
    assert "pncp.gov.br/api" not in json.dumps(teste, ensure_ascii=False)
    return api.publica("POST", "/workflows", importar.corpo(teste))


def _guardas_da_fila(pg) -> None:
    """O W10 de verdade só roda se nada real puder ser tocado (as mesmas guardas do test_w10_w11)."""
    (prov,) = pg.execute("SELECT valor #>> '{}' FROM configuracao WHERE chave = 'provedor'").fetchone()
    if prov not in ("simulado", "gravado"):
        pytest.fail("configuracao.provedor = %r: o W20 poderia gastar; este teste só roda com simulado/gravado" % prov)
    (vencidas,) = pg.execute("SELECT count(*) FROM licitacoes WHERE lease_por IS NOT NULL AND lease_ate < now() "
                             "AND NOT (controle = ANY(%s))", (ALMOFADA,)).fetchone()
    if vencidas:
        pytest.skip("%d licitação(ões) REAL(is) com lease vencido: o W10 as devolveria; não rodo" % vencidas)
    (altas,) = pg.execute("SELECT count(*) FROM licitacoes WHERE prioridade >= %s AND NOT (controle = ANY(%s))",
                          (PRIO_ALMOFADA, ALMOFADA)).fetchone()
    if altas:
        pytest.skip("%d licitação(ões) real(is) com prioridade >= %d: a almofada não as protegeria"
                    % (altas, PRIO_ALMOFADA))
    if pg.execute("SELECT fn_disjuntor_w20_aberto()").fetchone()[0]:
        pytest.skip("o disjuntor do W20 está aberto agora: o W10 não reivindicaria nada")


def _almofada(pg) -> list:
    """4 licitações de TESTE elegíveis, prioridade 50: ocupam todas as vagas do fn_reivindicar (4 - extraindo)."""
    for c in ALMOFADA:
        seq = int(c.split("-")[2].split("/")[0])
        pg.execute(
            "INSERT INTO licitacoes (controle, ano, seq, orgao, uf, municipio, modalidade, objeto, situacao,"
            " publicado_em, fim_prazo, escopo_dentro, escopo_motivo, escopo_versao, estado, prioridade, ensaio,"
            " origem) VALUES (%s, 2026, %s, 'TESTE test_w01 (apagar)', 'SP', 'Teste', 'Pregão - Eletrônico',"
            " 'TESTE test_w01: almofada da fila (folha de pagamento)', 'Divulgada no PNCP', '2026-09-01',"
            " now() + interval '10 days', true, 'teste', 'teste', 'nova', %s, true, 'manual')",
            (c, seq, PRIO_ALMOFADA))
    return list(ALMOFADA)


def _apagar_almofada(pg, desde) -> None:
    pg.execute("DELETE FROM emails WHERE controle = ANY(%s)", (ALMOFADA,))
    pg.execute("DELETE FROM execucoes_workflow WHERE controle = ANY(%s)", (ALMOFADA,))
    # Ninguém mais dispara o W10 nesta janela (a agenda dele está desligada): as linhas W10 desde o início são daqui.
    if desde is not None:
        pg.execute("DELETE FROM execucoes_workflow WHERE workflow = 'W10' AND iniciado_em >= %s", (desde,))
    for tabela in ("revisoes_humanas", "sinais_jev", "licitacao_eventos", "arquivos"):
        pg.execute("DELETE FROM %s WHERE controle = ANY(%%s)" % tabela, (ALMOFADA,))
    pg.execute("DELETE FROM licitacoes WHERE controle = ANY(%s)", (ALMOFADA,))


def _apagar_rodadas_da_copia(api, pg, copias: list) -> None:
    """As linhas W01 que as execuções das cópias abriram (com buscas/buscas_paginas, numa transação) e o e-mail
    'cego' de cada uma. Achadas pelas execuções da cópia no n8n: vale também para a rodada que falhou no meio.
    Tem de rodar ANTES de apagar as cópias (as execuções vão junto com o fluxo)."""
    n8n_ids = []
    for wid in copias:
        n8n_ids += [str(e["id"]) for e in api.publica("GET", "/executions?workflowId=%s&limit=50" % wid).get("data") or []]
    linhas = [r[0] for r in pg.execute("SELECT id FROM execucoes_workflow WHERE workflow = 'W01' "
                                       "AND n8n_execution_id = ANY(%s)", (n8n_ids,)).fetchall()]
    if not linhas:
        return
    with pg.transaction():
        for lid in linhas:
            # O corpo do 'cego' cita a linha (W01 "Resumo da rodada"): "· linha N de execucoes_workflow".
            pg.execute("DELETE FROM emails WHERE tipo = 'cego' AND corpo_html LIKE %s",
                       ("%% linha %d de execucoes_workflow%%" % lid,))
        pg.execute("DELETE FROM buscas_paginas WHERE workflow_execucao_id = ANY(%s)", (linhas,))
        pg.execute("DELETE FROM buscas WHERE workflow_execucao_id = ANY(%s)", (linhas,))
        pg.execute("DELETE FROM execucoes_workflow WHERE workflow = 'W01' AND id = ANY(%s)", (linhas,))


def _saidas_do_if(runs: dict) -> list:
    return [len(x or []) for x in runs["Empurrar a fila?"][-1]["data"]["main"]]


def _esperar(cond, timeout: float, oque: str):
    limite = time.monotonic() + timeout
    while True:
        v = cond()
        if v:
            return v
        if time.monotonic() > limite:
            raise AssertionError("não aconteceu em %d s: %s" % (timeout, oque))
        time.sleep(2)


def test_fim_da_rodada_chama_o_w10_so_sem_seco_e_com_orcamento(api, w01, pg):
    _guardas_da_fila(pg)
    inicio = pg.execute("SELECT now()").fetchone()[0]
    _apagar_almofada(pg, None)                     # sobra de uma rodada interrompida
    copias = []
    try:
        ligada = _copia_com_w10_ligado(api, "TESTE W01 com W10 ligado (apagar)")
        copias.append(ligada["id"])
        sem_orc = _copia_com_w10_ligado(api, "TESTE W01 com W10 ligado, orçamento diz não (apagar)", True)
        copias.append(sem_orc["id"])
        foto = fotografia(pg)

        # 1. Seco (o "Verificar agora" do W11): o IF barra, o W10 nem é chamado.
        eid1, s1, runs1 = rodar(api, ligada["id"], "Chamado por outro fluxo", [{"seco": True}], timeout=900)
        print("\n[W01->W10 seco] execução n8n %s · IF %s · cega %s" % (eid1, _saidas_do_if(runs1), s1["cego"]))
        assert s1["seco"] is True and s1["cego"] is True and s1["vistas"] == 0
        assert _saidas_do_if(runs1) == [0, 1] and "W10 Fila (sem esperar)" not in runs1

        # 2. Rodada que grava (Manual, seco=false), mas o orçamento diz auto_processar=false: o IF barra.
        eid2, s2, runs2 = rodar(api, sem_orc["id"], "Manual", [{}], timeout=900)
        print("[W01->W10 orçamento diz não] execução n8n %s · IF %s" % (eid2, _saidas_do_if(runs2)))
        assert s2["seco"] is False and s2["cego"] is True and s2["vistas"] == 0
        assert _saidas_do_if(runs2) == [0, 1] and "W10 Fila (sem esperar)" not in runs2
        assert not pg.execute("SELECT 1 FROM execucoes_workflow WHERE workflow = 'W10' AND iniciado_em >= %s",
                              (inicio,)).fetchone(), "o W10 rodou sem o IF deixar"

        # 3. Rodada que grava + orçamento vigente com auto_processar=true: o W10 de verdade é chamado, sem esperar.
        (auto,) = pg.execute("SELECT COALESCE(o.auto_processar, true) FROM (SELECT 1) u "
                             "LEFT JOIN orcamento o ON o.vigente").fetchone()
        if auto is not True:
            pytest.skip("orcamento vigente com auto_processar=false: o ramo que chama o W10 não se prova sem mexer nele")
        almofada = _almofada(pg)
        t = pg.execute("SELECT now()").fetchone()[0]
        eid3, s3, runs3 = rodar(api, ligada["id"], "Manual", [{}], timeout=900)
        print("[W01->W10 grava] execução n8n %s · IF %s" % (eid3, _saidas_do_if(runs3)))
        assert s3["seco"] is False and s3["cego"] is True and s3["vistas"] == 0 and s3["jev"]["chamadas"] == 0
        assert _saidas_do_if(runs3) == [1, 0] and "W10 Fila (sem esperar)" in runs3
        assert "Jev (TypeSafe)" not in runs3 and "Registrar vista" not in runs3
        # A Saída continua sendo o último nó (o que o fluxo devolve a quem esperar por ele).
        ultimo = max(runs3, key=lambda n: runs3[n][-1]["startTime"])
        assert ultimo == "Saída da rodada", ultimo

        def w10_fechado():
            x = pg.execute("SELECT n8n_execution_id, gatilho, status, argumentos FROM execucoes_workflow"
                           " WHERE workflow = 'W10' AND iniciado_em >= %s ORDER BY id", (t,)).fetchall()
            return x if x and all(r[2] != "em_curso" for r in x) else None
        (w10,) = _esperar(w10_fechado, 120, "o W10 chamado pelo W01 fechar a linha")
        w10_n8n, gat, st, args = w10
        print("[W01->W10 grava] W10 n8n %s · %s · %s · reivindicou %s" % (w10_n8n, gat, st, args["controles"]))
        assert (gat, st) == ("subfluxo", "ok")
        assert args["controles"] and set(args["controles"]) <= set(almofada), "o W10 pegou fora da almofada!"

        def w20_fechados():
            x = pg.execute("SELECT controle, status, n8n_execution_id FROM execucoes_workflow WHERE workflow = 'W20'"
                           " AND controle = ANY(%s) AND iniciado_em >= %s", (args["controles"], t)).fetchall()
            return x if len(x) == len(args["controles"]) and all(r[1] != "em_curso" for r in x) else None
        w20 = _esperar(w20_fechados, 180, "os W20 da almofada terminarem")
        print("[W01->W10 grava] W20 %s" % ", ".join("%s->%s" % (r[2], r[1]) for r in w20))
        # Nenhuma licitação real tocada pelas três rodadas (nem visto_em, nem carimbo, nem inserção).
        assert inseridas_pelo_w01_desde(pg, inicio) == []
        assert marcas_mudadas(foto, fotografia(pg)) == []
    finally:
        _apagar_rodadas_da_copia(api, pg, copias)
        for wid in copias:
            api.publica("DELETE", "/workflows/" + wid)
        _apagar_almofada(pg, inicio)
