# -*- coding: utf-8 -*-
"""
W40 (alerta diário 07:00) e W70 (retificações semanais) na instância real
(fopa-n8n 127.0.0.1:5679) e no Postgres de dev (127.0.0.1:5433) — sem mock,
pelo mesmo motivo do test_n8n.py: o que quebra no n8n é o que um mock esconde.

O que se prova:
  - os dois fluxos versionados têm o gatilho certo, Error Workflow = W90, fuso
    de São Paulo, Sticky com "regra — script:linha" e, no W70, os HTTP do PNCP
    com Timeout 60000 + Never Error + On Error → continue (plano §5);
  - W40 manual não enfileira e-mail (o produto manda só dois, db/038-039):
    registra a rodada em execucoes_workflow, com os números de cada prioridade
    e P4 "não coletado", que a página /execucoes mostra;
  - o renderizador do W40 (o Code "Montar e-mail", executado no Node do próprio
    container) faz o e-mail curto "nada novo" e distingue NADA A FAZER de
    NADA VISTO (ADR-007);
  - W70 com uma licitação de ENSAIO (identidade de uma compra real do PNCP que
    não está no banco): com o único documento conhecido — e RECUSADO por teto —
    nada muda; sem ele, vira 'retificada' pela fn_transicao, com evento e o
    carimbo do PNCP solto; reservada para a demo nunca é tocada, é contada à
    parte; o que passa do limite da rodada fica registrado.

Dado real não é alterado: tudo o que o teste cria tem controle próprio e é
apagado no fim (inclusive os eventos, que só o superusuário apaga).

    python -m pytest n8n/tests/test_w40_w70.py -v
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

import cliente  # noqa: E402
import executar  # noqa: E402
import importar  # noqa: E402

psycopg = pytest.importorskip("psycopg")

W40, W70 = "W40 Alerta diário", "W70 Retificações"
ARQ_W40 = importar.PASTA_WORKFLOWS / "W40.json"
ARQ_W70 = importar.PASTA_WORKFLOWS / "W70.json"

# W40: licitações de ensaio com CNPJ fictício (o W40 não chama o PNCP).
L_URGENTE = "99000000000001-1-000001/2026"
L_JEV = "99000000000001-1-000002/2026"
# W70: identidade de uma compra REAL do PNCP (1 documento ativo, seq 1) que não
# está no banco — o W70 precisa de resposta de verdade — e uma reservada fictícia.
L_W70 = "07598618000144-1-000095/2026"
L_W70_DEMO = "99000000000001-1-000003/2026"


@pytest.fixture(scope="module")
def instalado():
    if not cliente.no_ar():
        pytest.skip("fopa-n8n fora do ar em %s (docker compose up -d fopa-n8n)" % cliente.base())
    return importar.importar()


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


def _no(wf: dict, nome: str) -> dict:
    return next(n for n in wf["nodes"] if n["name"] == nome)


def _cron(wf: dict) -> str:
    gat = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.scheduleTrigger")
    return gat["parameters"]["rule"]["interval"][0]["expression"]


def _apagar_licitacoes(pg, controles):
    for c in controles:
        pg.execute("DELETE FROM revisoes_humanas WHERE controle = %s", (c,))
        pg.execute("DELETE FROM sinais_jev WHERE controle = %s", (c,))
        pg.execute("DELETE FROM licitacao_eventos WHERE controle = %s", (c,))
        pg.execute("DELETE FROM arquivos WHERE controle = %s", (c,))
        pg.execute("DELETE FROM emails WHERE controle = %s", (c,))
        pg.execute("DELETE FROM licitacoes WHERE controle = %s", (c,))


# ------------------------------------------------------------------ Node do container
def rodar_code_node(codigo: str, nos: dict, env: dict, entrada: dict | None = None) -> list:
    """Executa o jsCode de um Code node no Node do fopa-n8n, com $('Nó'), $env, $workflow e
    $execution de mentira. Testa o código versionado de verdade, sem Node no host."""
    if not shutil.which("docker"):
        pytest.skip("docker ausente: não há Node para rodar o Code node")
    harness = (
        "let s='';process.stdin.on('data',c=>s+=c).on('end',()=>{const c=JSON.parse(s);"
        "const $=(n)=>{if(!(n in c.nos))throw new Error('nó desconhecido: '+n);"
        "return {first:()=>({json:c.nos[n]}),item:{json:c.nos[n]}};};"
        "const $input={first:()=>({json:c.entrada}),all:()=>[{json:c.entrada}]};"
        "const f=new Function('$','$input','$json','$env','$workflow','$execution',c.codigo);"
        "const r=f($,$input,c.entrada,c.env,{id:'wfTESTE'},{id:'4242',mode:'manual'});"
        "process.stdout.write(JSON.stringify(r));});")
    corpo = json.dumps({"codigo": codigo, "nos": nos, "env": env, "entrada": entrada or {}})
    r = subprocess.run(["docker", "exec", "-i", "fopa-n8n", "node", "-e", harness], input=corpo.encode("utf-8"),
                       capture_output=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError("Code node falhou no Node do container: %s" % r.stderr.decode("utf-8", "replace")[-800:])
    return json.loads(r.stdout.decode("utf-8"))


# ------------------------------------------------------------------ versionados
def test_w40_e_w70_versionados_seguem_as_convencoes():
    w40 = json.loads(ARQ_W40.read_text(encoding="utf-8"))
    w70 = json.loads(ARQ_W70.read_text(encoding="utf-8"))
    assert w40["name"] == W40 and w70["name"] == W70
    assert _cron(w40) == "0 7 * * *", "alerta às 07:00 todo dia"
    assert _cron(w70) == "0 5 * * 0", "retificações domingo 05:00"
    for wf in (w40, w70):
        s = wf["settings"]
        assert s["errorWorkflow"] == "{{WF:W90}}" and s["timezone"] == "America/Sao_Paulo"
        assert s["executionOrder"] == "v1"
        assert any(n["type"] == "n8n-nodes-base.manualTrigger" for n in wf["nodes"])
        notas = [n["parameters"]["content"] for n in wf["nodes"] if n["type"] == "n8n-nodes-base.stickyNote"]
        assert any("—" in c and ".py:" in c for c in notas), wf["name"]
        for n in wf["nodes"]:
            if n["type"] == "n8n-nodes-base.postgres":
                assert n["typeVersion"] == 2.6
                assert n["credentials"]["postgres"]["id"] == "{{CRED:fopa-postgres (n8n_rw)}}"
    # W40 não manda nem enfileira e-mail (o produto manda só dois, db/038-039): o último nó só registra a
    # rodada em execucoes_workflow.
    bruto40 = ARQ_W40.read_text(encoding="utf-8")
    registro = re.sub(r"--[^\n]*", "", _no(w40, "Enfileirar alerta")["parameters"]["query"])
    assert re.search(r"\bINSERT\s+INTO\s+execucoes_workflow\b", registro) and "'W40'" in registro
    assert not re.search(r"\bINTO\s+emails\b", registro, re.I) and "alerta_diario" not in registro
    assert not any(n["type"] in ("n8n-nodes-base.emailSend", "n8n-nodes-base.gmail") for n in w40["nodes"])
    assert "<script" not in bruto40.lower()
    # Nenhuma consulta do W40 escreve em licitação, veredito ou escopo: só lê (e o INSERT final do registro).
    for n in w40["nodes"]:
        if n["type"] == "n8n-nodes-base.postgres" and n["name"] != "Enfileirar alerta":
            sql = re.sub(r"--[^\n]*", "", n["parameters"]["query"]).upper()
            assert not re.search(r"\b(UPDATE|INSERT|DELETE)\b", sql), n["name"]
    # W70: PNCP com Timeout explícito, Never Error, On Error → continue (plano §5, convenções).
    https = [n for n in w70["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"]
    assert len(https) == 2
    for n in https:
        p = n["parameters"]
        assert "pncp.gov.br/api/pncp/v1/orgaos/" in p["url"] and p["url"].endswith("/arquivos")
        assert p["options"]["timeout"] == 60000
        assert p["options"]["response"]["response"] == {"fullResponse": True, "neverError": True}
        assert n["onError"] == "continueErrorOutput"
    esperas = {n["name"]: n["parameters"]["amount"] for n in w70["nodes"] if n["type"] == "n8n-nodes-base.wait"}
    assert esperas == {"Pausa 3 s": 3, "Espera 30 s": 30}
    abrir = _no(w70, "Abrir rodada")["parameters"]["query"]
    for trecho in ("fn_no_recorte", "fn_transicao_permitida(l.estado, 'retificada')", "reserva_demo",
                   "w70_limite", "200", "fora_do_limite_controles", "puladas_reserva_demo"):
        assert trecho in abrir, trecho
    assert "fn_transicao(" in _no(w70, "Marcar retificada")["parameters"]["query"]


def test_w40_e_w70_publicados_com_error_workflow(instalado):
    api = cliente.N8n.autenticado()
    por_nome = {w["name"]: w for w in api.listar_workflows()}
    id_w90 = por_nome["W90 Erro"]["id"]
    for nome in (W40, W70):
        assert nome in por_nome, "%s não foi importado" % nome
        wf = api.workflow(por_nome[nome]["id"])
        assert wf.get("active") is True, "%s não está publicado" % nome
        assert (wf.get("settings") or {}).get("errorWorkflow") == id_w90
        assert "{{WF:" not in json.dumps(wf) and "{{CRED:" not in json.dumps(wf)


# ------------------------------------------------------------------ W40
def _fixtures_w40(pg):
    _apagar_licitacoes(pg, [L_URGENTE, L_JEV])
    hoje = pg.execute("SELECT (now() AT TIME ZONE 'America/Sao_Paulo')::date").fetchone()[0]
    sessao = dt.datetime.combine(hoje + dt.timedelta(days=2), dt.time(10, 0))
    pg.execute(
        "INSERT INTO licitacoes (controle, ano, seq, orgao, uf, municipio, modalidade, objeto, publicado_em,"
        " fim_prazo, fim_prazo_tem_hora, escopo_dentro, estado, ensaio, origem)"
        " VALUES (%s, 2026, 1, 'Ensaio W40', 'SP', 'Ensaio W40 Urgente', 'Pregão - Eletrônico',"
        " 'Teste do W40: cessão da folha de pagamento (licitação de ensaio)', %s,"
        " (%s::timestamp AT TIME ZONE 'America/Sao_Paulo'), true, true, 'baixada_ok', true, 'n8n')",
        (L_URGENTE, hoje, sessao))
    pg.execute("SELECT fn_transicao(%s, 'retificada', 'W70: documento novo no PNCP (teste W40)', NULL)",
               (L_URGENTE,))
    pg.execute("INSERT INTO revisoes_humanas (controle, pergunta_id, motivo, status)"
               " VALUES (%s, 'Q5', 'teste W40: conferir o valor mínimo', 'aberta')", (L_URGENTE,))
    pg.execute(
        "INSERT INTO licitacoes (controle, ano, seq, orgao, uf, municipio, modalidade, objeto, publicado_em,"
        " fim_prazo, fim_prazo_tem_hora, escopo_dentro, escopo_motivo, estado, ensaio, origem)"
        " VALUES (%s, 2026, 2, 'Ensaio W40', 'MG', 'Ensaio W40 Jev', 'Dispensa',"
        " 'Teste do W40: a regra recusou, o Jev discorda', %s,"
        " (%s::date + 10)::timestamp AT TIME ZONE 'America/Sao_Paulo', false, false, 'teste', 'fora_escopo',"
        " true, 'n8n')", (L_JEV, hoje, hoje))
    pg.execute("INSERT INTO sinais_jev (tipo, controle, criterio_versao, regra, resposta, p_sim, confianca,"
               " contexto_enviado, candidata) VALUES ('escopo', %s, 'teste-w40', 'fora', 'sim', 0.91, 0.82,"
               " 'objeto', true)", (L_JEV,))


def test_w40_manual_registra_a_rodada_sem_enfileirar_email(instalado, pg):
    _fixtures_w40(pg)
    (antes,) = pg.execute("SELECT coalesce(max(id), 0) FROM emails").fetchone()
    exec_id = None
    try:
        r = executar.executar(W40, timeout=180)
        exec_id = r["id"]
        assert r["status"] == "success", r
        novos = pg.execute("SELECT id FROM emails WHERE id > %s AND controle IS NULL"
                           " AND assunto LIKE '[FOPA] Alerta %%'", (antes,)).fetchall()
        assert novos == [], "o W40 não enfileira e-mail: o produto manda só dois (db/038-039)"
        reg = pg.execute("SELECT status, contadores FROM execucoes_workflow WHERE workflow = 'W40'"
                         " AND n8n_execution_id = %s", (exec_id,)).fetchone()
        assert reg, "a rodada do W40 fica registrada em execucoes_workflow, que a página /execucoes mostra"
        status, c = reg
        assert status == "ok"
        assert c["p1"] >= 1 and c["p2"] >= 1 and c["p5_licitacoes"] >= 1 and c["jev_candidatas"] >= 1
        assert c["p4"] == "não coletado"
    finally:
        if exec_id:
            pg.execute("DELETE FROM execucoes_workflow WHERE workflow = 'W40' AND n8n_execution_id = %s", (exec_id,))
        _apagar_licitacoes(pg, [L_URGENTE, L_JEV])


def _vazio():
    return {"n": 0, "itens": [], "sem_lance": 0, "novas": 0, "publicadas": 0, "perguntas_abertas": 0,
            "injecao": 0, "reprovadas": 0, "conflito": 0, "alerta": 0, "abertas": 0}


def _nos_w40(coleta):
    janela = {"agora": "2026-09-24 10:00:00+00", "desde": "2026-09-23 10:00:00+00", "desde_fmt": "23/09 07h00",
              "hoje": "2026-09-24", "hoje_fmt": "24/09/2026", "limite_fmt": "01/10",
              "agora_fmt": "24/09/2026 07h00", "ano_minimo": 2026}
    rodape = {"coleta": coleta, "w70": None, "processadas": 0, "falharam": 0, "erros_fluxo": 0, "chamadas": 0,
              "custo_brl": 0, "sem_preco": 0, "emails_falhos": 0, "provedor": "simulado"}
    nos = {n: _vazio() for n in ("P1 Sessão em até 7 dias", "P2 Retificações", "P3 Novas desde ontem",
                                 "P5 Revisões abertas", "P6 Extraídas que pedem olho humano",
                                 "Jev: o filtro pode ter errado")}
    nos["Janela do alerta"] = janela
    nos["Rodapé: coleta, custo, falhas"] = rodape
    return nos


def test_w40_dia_sem_nada_e_email_curto_e_distingue_nada_visto(instalado):
    codigo = _no(json.loads(ARQ_W40.read_text(encoding="utf-8")), "Montar e-mail")["parameters"]["jsCode"]
    env = {"FOPA_SITE_URL": "http://fopa-api:8080", "WEBHOOK_URL": "http://localhost:5679/"}
    coleta_ok = {"id": 1, "quem": "W01", "script_legado": None, "cego": False, "status": "ok",
                 "quando": "24/09 06h00", "na_janela": True, "cobertura": 98.5, "termos_falhos": 0, "termos": 12}

    (ok,) = rodar_code_node(codigo, _nos_w40(coleta_ok), env)
    j = ok["json"]
    assert j["assunto"] == "[FOPA] Alerta 24/09 · nada novo"
    assert j["contadores"]["nada_novo"] is True and j["contadores"]["nada_visto"] is None
    assert "NADA A FAZER" in j["corpo_html"] and "NADA VISTO" not in j["corpo_html"]
    assert "não coletado" in j["corpo_html"], "P4 aparece mesmo no e-mail curto"
    assert "P1 · sessão" not in j["corpo_html"], "dia sem nada é e-mail curto, sem as seções vazias"
    # o hostname interno do compose não vai para o e-mail; a execução linka sem barra dupla
    assert "fopa-api" not in j["corpo_html"] and "localhost:8080" in j["corpo_html"]
    assert "FOPA_SITE_PUBLIC_URL" in j["corpo_html"], "o fallback de URL do site é dito, não escondido"
    assert "http://localhost:5679/workflow/wfTESTE/executions/4242" in j["corpo_html"]

    for coleta, trecho in ((None, "nenhuma coleta do PNCP registrada"),
                           (dict(coleta_ok, na_janela=False), "nenhuma coleta do PNCP desde 23/09 07h00"),
                           (dict(coleta_ok, cego=True), "foi cega")):
        (cego,) = rodar_code_node(codigo, _nos_w40(coleta),
                                  {"FOPA_SITE_PUBLIC_URL": "https://fopa.exemplo.com.br/", "WEBHOOK_URL": ""})
        j = cego["json"]
        assert j["assunto"] == "[FOPA] Alerta 24/09 · NADA VISTO · nada novo"
        assert "NADA VISTO" in j["corpo_html"] and "NADA A FAZER" not in j["corpo_html"]
        assert trecho in j["corpo_html"] and "não consegui olhar" in j["corpo_html"]
        assert "FOPA_SITE_PUBLIC_URL" not in j["corpo_html"], "com URL pública definida não há aviso"
        assert "execução 4242" in j["corpo_html"] and "/workflow/wfTESTE" not in j["corpo_html"], \
            "sem base do n8n o e-mail dá o id sem link quebrado"


def test_w40_licitacao_linka_pela_url_publica_sem_barra_dupla(instalado):
    codigo = _no(json.loads(ARQ_W40.read_text(encoding="utf-8")), "Montar e-mail")["parameters"]["jsCode"]
    nos = _nos_w40({"id": 1, "quem": "W01", "script_legado": None, "cego": False, "status": "ok",
                    "quando": "24/09 06h00", "na_janela": True, "cobertura": None, "termos_falhos": 2, "termos": 12})
    nos["P1 Sessão em até 7 dias"] = {"n": 1, "sem_lance": 1, "itens": [{
        "controle": "12345678000199-1-000007/2026", "slug": "12345678000199-1-000007-2026", "local": "Cidade/UF",
        "modalidade": "Pregão", "estado": "preparada", "extraida": False, "dias": 3, "sessao": "27/09",
        "q5": None, "injecao_suspeita": False, "revisao_pendente": False}]}
    for base in ("https://fopa.exemplo.com.br", "https://fopa.exemplo.com.br/", "https://fopa.exemplo.com.br//"):
        (r,) = rodar_code_node(codigo, nos, {"FOPA_SITE_PUBLIC_URL": base, "N8N_EDITOR_BASE_URL": "https://n8n.x/"})
        corpo = r["json"]["corpo_html"]
        assert 'href="https://fopa.exemplo.com.br/licitacao/12345678000199-1-000007-2026"' in corpo, base
        assert "https://n8n.x/workflow/wfTESTE/executions/4242" in corpo
        assert "2 de 12 termos falharam" in corpo, "coleta parcial é piso, não total (20_monitor.py:421-431)"
        assert r["json"]["assunto"] == "[FOPA] Alerta 24/09 · 1 sessão em até 7 dias"



def test_w40_revisao_e_jev_linkam_para_a_fila_de_revisao():
    # O P5 dizia "decidir no site" e o Jev "aba escopo da revisão" sem link:
    # quem lê o alerta no celular tinha de achar a fila sozinho. Agora as duas
    # seções levam direto à /revisao (o Jev, à aba escopo), e o "e mais N" delas
    # vai para a fila, não para o painel.
    codigo = _no(json.loads(ARQ_W40.read_text(encoding="utf-8")), "Montar e-mail")["parameters"]["jsCode"]
    nos = _nos_w40({"id": 1, "quem": "W01", "script_legado": None, "cego": False, "status": "ok",
                    "quando": "24/09 06h00", "na_janela": True, "cobertura": 98.5, "termos_falhos": 0, "termos": 12})
    lic = {"controle": "12345678000199-1-000007/2026", "slug": "12345678000199-1-000007-2026",
           "local": "Cidade/UF", "modalidade": "Pregão", "dias": 3, "sessao": "27/09"}
    nos["P5 Revisões abertas"] = {"n": 20, "perguntas_abertas": 31, "novas": 0, "itens": [dict(
        lic, abertas=2, aberta_desde="23/09", perguntas="Q5 Q13", motivo="alerta de regra")]}
    nos["Jev: o filtro pode ter errado"] = {"n": 12, "abertas": 12, "itens": [dict(
        lic, regra="fora", p_sim=0.93, objeto="Serviços de gestão da folha de pagamento")]}
    nos["P6 Extraídas que pedem olho humano"] = {"n": 30, "injecao": 0, "reprovadas": 0, "conflito": 1,
                                                "alerta": 0, "itens": [dict(lic, conflitos=1)]}
    (r,) = rodar_code_node(codigo, nos, {"FOPA_SITE_PUBLIC_URL": "https://fopa.exemplo.com.br/"})
    corpo = r["json"]["corpo_html"]
    assert corpo.count('href="https://fopa.exemplo.com.br/revisao"') == 2, "P5: no texto e no 'e mais N'"
    assert corpo.count('href="https://fopa.exemplo.com.br/revisao?aba=escopo"') == 2, "Jev: no texto e no 'e mais N'"
    assert "e mais 19 na" in corpo and "e mais 11 na" in corpo
    assert "Decidir no site" not in corpo
    assert 'e mais 29 no <a href="https://fopa.exemplo.com.br/" style=' in corpo, \
        "as outras seções continuam mandando o resto para o painel"



def test_w40_p5_revisao_decidida_sai_do_alerta(pg):
    # Checklist F6: "decidir um REVISAR e vê-lo sair do alerta". O site grava a decisão em
    # revisoes_humanas sem tocar nas respostas (test_site.py::test_fila_e_decisao_de_revisao_sem_tocar_nas_respostas);
    # o elo que faltava é o P5 do W40. Roda o SQL do P5 COMO ESTÁ no W40 versionado, antes e depois de cada
    # decisão possível, numa transação desfeita no fim: nada de n8n, de e-mail nem de linha que sobre.
    (q,) = [n["parameters"]["query"] for n in json.loads(ARQ_W40.read_text(encoding="utf-8"))["nodes"]
            if n["name"] == "P5 Revisões abertas"]
    q = re.sub(r"\$(\d+)", r"%(p\1)s", q.replace("%", "%%"))
    ctrl = "00000000000000-1-000960/2026"
    par = {"p1": "2026-09-23 10:00:00+00", "p2": "2026-09-24"}

    def p5() -> list:
        itens = pg.execute(q, par).fetchone()[3] or []
        return [x["controle"] for x in itens]

    with pg.transaction(force_rollback=True):
        pg.execute("INSERT INTO licitacoes (controle, escopo_dentro, estado, orgao, uf, municipio, modalidade, objeto,"
                   " publicado_em, fim_prazo, ensaio) VALUES (%s, true, 'publicada', 'Prefeitura de Teste', 'SP',"
                   " 'Teste', 'Pregão Eletrônico', 'TESTE P5: cessão da folha', '2026-09-20', '2026-10-10 10:00-03',"
                   " true)", (ctrl,))
        (rid,) = pg.execute("INSERT INTO revisoes_humanas (controle, pergunta_id, motivo) VALUES (%s, 'Q5', 'TESTE P5')"
                            " RETURNING id", (ctrl,)).fetchone()
        assert ctrl in p5(), "revisão aberta tem de estar no P5"
        for decisao in ("aceita", "corrigida", "rejeitada"):
            pg.execute("UPDATE revisoes_humanas SET status = %s, decidido_por = 'teste', decidido_em = now()"
                       " WHERE id = %s", (decisao, rid))
            assert ctrl not in p5(), "decidida (%s) continuou no P5" % decisao
            pg.execute("UPDATE revisoes_humanas SET status = 'aberta', decidido_por = NULL, decidido_em = NULL"
                       " WHERE id = %s", (rid,))
            assert ctrl in p5(), "reaberta tem de voltar ao P5"
    assert not pg.execute("SELECT 1 FROM licitacoes WHERE controle = %s", (ctrl,)).fetchall()


# ------------------------------------------------------------------ W70
def _pncp_arquivos(controle: str):
    cnpj, _, resto = controle.partition("-1-")
    seq, ano = resto.split("/")
    url = "https://pncp.gov.br/api/pncp/v1/orgaos/%s/compras/%s/%d/arquivos" % (cnpj, ano, int(seq))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "FOPA/3"}), timeout=60) as r:
            return json.loads(r.read() or b"[]")
    except Exception as e:  # noqa: BLE001
        pytest.skip("PNCP indisponível para o teste do W70: %s" % str(e)[:120])


def _rodada_w70(pg, exec_id):
    return pg.execute("SELECT status, cego, argumentos, contadores FROM execucoes_workflow"
                      " WHERE workflow = 'W70' AND n8n_execution_id = %s", (exec_id,)).fetchone()


def test_w70_documento_novo_vira_retificada_e_sem_novidade_nao_muda(instalado, pg):
    if pg.execute("SELECT 1 FROM licitacoes WHERE controle = %s AND NOT ensaio", (L_W70,)).fetchone():
        pytest.skip("%s entrou no banco como licitação real: escolha outra compra para o ensaio" % L_W70)
    ativos = sorted({d["sequencialDocumento"] for d in _pncp_arquivos(L_W70) if d.get("statusAtivo") is not False})
    assert ativos, "a compra de ensaio precisa de ao menos um documento ativo no PNCP"
    _apagar_licitacoes(pg, [L_W70, L_W70_DEMO])
    limite_antes = pg.execute("SELECT valor FROM configuracao WHERE chave = 'w70_limite'").fetchone()
    execucoes = []
    try:
        hoje0 = "(now() AT TIME ZONE 'America/Sao_Paulo')::date::timestamp AT TIME ZONE 'America/Sao_Paulo'"
        for controle, demo in ((L_W70, False), (L_W70_DEMO, True)):
            cnpj, _, resto = controle.partition("-1-")
            pg.execute(
                "INSERT INTO licitacoes (controle, ano, seq, orgao, uf, municipio, modalidade, objeto, publicado_em,"
                " fim_prazo, fim_prazo_tem_hora, escopo_dentro, estado, ensaio, reserva_demo, origem,"
                " atualizado_pncp) VALUES (%s, 2026, %s, 'Ensaio W70', 'CE', 'Ensaio W70', 'Dispensa',"
                " 'Teste do W70 (identidade de uma compra real do PNCP)', current_date, " + hoje0 + ","
                " false, true, 'baixada_ok', true, %s, 'manual', '2026-01-01 00:00:00')",
                (controle, int(resto.split("/")[0]), demo))
            # O que o banco conhece: todos os seqs ativos, o 1º RECUSADO por teto (tem de contar como conhecido).
            for i, s in enumerate(ativos):
                pg.execute("INSERT INTO arquivos (controle, seq, nome, status, motivo) VALUES (%s, %s, %s, %s, %s)",
                           (controle, s, "ensaio-w70-seq%d.pdf" % s,
                            "recusado_politica" if i == 0 else "ok", "teste: acima do teto" if i == 0 else None))
        # A licitação de ensaio vai na frente (sessão hoje); o limite cobre só ela e os empates reais.
        (empates,) = pg.execute(
            "SELECT count(*) FROM licitacoes WHERE fim_prazo = " + hoje0 + " AND controle < %s AND NOT ensaio",
            (L_W70,)).fetchone()
        limite = 1 + empates
        pg.execute("INSERT INTO configuracao (chave, valor, descricao, alterado_por) VALUES ('w70_limite', %s::jsonb,"
                   " 'W70: licitações por rodada (padrão 200)', 'teste W70') ON CONFLICT (chave) DO UPDATE"
                   " SET valor = EXCLUDED.valor, alterado_por = EXCLUDED.alterado_por",
                   (json.dumps(limite),))

        # 1) Tudo conhecido (inclusive o recusado): nada muda.
        r1 = executar.executar(W70, timeout=300)
        execucoes.append(r1["id"])
        assert r1["status"] == "success", r1
        status, cego, argumentos, c1 = _rodada_w70(pg, r1["id"])
        if L_W70 in [x["controle"] for x in c1["nao_conferidas_controles"]]:
            pytest.skip("PNCP não respondeu ao W70 nesta rodada: %s" % c1["nao_conferidas_controles"])
        assert argumentos["limite"] == limite and c1["na_rodada"] == limite
        assert L_W70 in c1["sem_novidade_controles"], c1
        assert c1["fora_do_limite"] == c1["elegiveis"] - limite
        assert len(c1["fora_do_limite_controles"]) == c1["fora_do_limite"], "o que ficou de fora vai nomeado"
        assert L_W70_DEMO in c1["puladas_reserva_demo_controles"] and c1["puladas_reserva_demo"] >= 1
        assert L_W70_DEMO not in c1["fora_do_limite_controles"], "reservada não é 'fora do limite': é pulada"
        assert status in ("ok", "parcial") and cego is False
        assert pg.execute("SELECT estado::text FROM licitacoes WHERE controle = %s", (L_W70,)).fetchone()[0] \
            == "baixada_ok"
        assert not pg.execute("SELECT 1 FROM licitacao_eventos WHERE controle = %s", (L_W70,)).fetchone()

        # 2) Tira o documento conhecido: agora é "novo" no PNCP e a licitação vira retificada.
        novo = ativos[-1]
        pg.execute("DELETE FROM arquivos WHERE controle IN (%s, %s) AND seq = %s", (L_W70, L_W70_DEMO, novo))
        r2 = executar.executar(W70, timeout=300)
        execucoes.append(r2["id"])
        assert r2["status"] == "success", r2
        _, _, _, c2 = _rodada_w70(pg, r2["id"])
        if L_W70 in [x["controle"] for x in c2["nao_conferidas_controles"]]:
            pytest.skip("PNCP não respondeu ao W70 na 2ª rodada: %s" % c2["nao_conferidas_controles"])
        assert [x["controle"] for x in c2["retificadas_controles"]] == [L_W70], c2
        assert c2["retificadas_controles"][0]["novos"] == [novo]
        estado, carimbo = pg.execute("SELECT estado::text, atualizado_pncp FROM licitacoes WHERE controle = %s",
                                     (L_W70,)).fetchone()
        assert estado == "retificada"
        assert carimbo is None, "o carimbo do PNCP é solto para o W01 não acusar a mesma mudança de novo"
        ev = pg.execute("SELECT de::text, para::text, motivo, dados, n8n_execution_id FROM licitacao_eventos"
                        " WHERE controle = %s", (L_W70,)).fetchall()
        assert len(ev) == 1
        de, para, motivo, dados, ev_exec = ev[0]
        assert (de, para, motivo) == ("baixada_ok", "retificada", "W70: documento novo no PNCP")
        assert [n["seq"] for n in dados["novos"]] == [novo] and ev_exec == r2["id"]
        # A reservada para a demo ficou parada, mesmo com o documento "novo".
        assert pg.execute("SELECT estado::text FROM licitacoes WHERE controle = %s", (L_W70_DEMO,)).fetchone()[0] \
            == "baixada_ok"
        assert L_W70_DEMO in c2["puladas_reserva_demo_controles"]
    finally:
        _apagar_licitacoes(pg, [L_W70, L_W70_DEMO])
        for e in execucoes:
            pg.execute("DELETE FROM execucoes_workflow WHERE workflow = 'W70' AND n8n_execution_id = %s", (e,))
        if limite_antes is None:
            pg.execute("DELETE FROM configuracao WHERE chave = 'w70_limite'")
        else:
            pg.execute("UPDATE configuracao SET valor = %s::jsonb WHERE chave = 'w70_limite'",
                       (json.dumps(limite_antes[0]),))
