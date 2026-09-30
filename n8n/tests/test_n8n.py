# -*- coding: utf-8 -*-
"""
A instância n8n da FOPA de verdade: `fopa-n8n` em 127.0.0.1:5679 e o Postgres
da stack em 127.0.0.1:5433 (plano, seções 4 e 5, "Versionamento dos fluxos").

Sem mock de propósito. O que quebra no n8n é justamente o que um mock
esconderia: a REST interna muda entre versões, o nó Postgres parametriza de
um jeito próprio, o Send Email sem credencial pode falhar antes de chegar ao
ramo de erro, e publicar um fluxo que aponta para um sub não publicado é
recusado. Só a instância real responde isso.

O que se prova:
  - bootstrap idempotente: a 2ª execução não cria owner, chave nem credencial;
  - importar.py sobe W00, W50 e W90 e a 2ª execução não duplica nada;
  - exportar -> importar ida e volta preserva nós e ligações (os ids reais
    viram placeholders e voltam a ser ids);
  - W00 executado manualmente grava uma linha nova em `saude`, com o link da
    execução sem supor barra no fim do WEBHOOK_URL (e o caminho de falha, rodado
    no Node do container, escapa o motivo e não quebra o link sem a barra);
  - W50 com um e-mail pendente e SEM SMTP: a 1ª falha NÃO é definitiva — a linha
    volta para a fila com o erro e a hora da próxima tentativa; a espera cresce
    (2, 5, 15, 40 min) e só na 5ª tentativa vira 'falhou' (plano §11 item 9) —
    nunca silêncio;
  - W50 solta, no próprio claim, a marca 'em envio' de execução que morreu sem
    Error Workflow (reserva com mais de 30 min), e NÃO solta a de envio em curso.

Senhas saem do docker/.env pelo código e nunca aparecem em assert/print.
Se a stack não estiver de pé, os testes são PULADOS com o motivo, não aprovados.

    python -m pytest n8n/tests -v
"""
from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

import cliente  # noqa: E402
import bootstrap  # noqa: E402
import importar  # noqa: E402
import exportar  # noqa: E402
import executar  # noqa: E402

psycopg = pytest.importorskip("psycopg")

FLUXOS = {"W00 Saúde", "W50 Envio de e-mails", "W90 Erro"}


@pytest.fixture(scope="module")
def instalado():
    """Bootstrap + importação uma vez para o módulo: os testes partem daqui."""
    if not cliente.no_ar():
        pytest.skip("fopa-n8n fora do ar em %s (docker compose up -d fopa-n8n)" % cliente.base())
    return bootstrap.executar(), importar.importar()


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


def _fluxos_fopa(api) -> dict:
    return {w["name"]: w for w in api.listar_workflows() if w["name"] in FLUXOS}


# ------------------------------------------------------------------ bootstrap
def test_bootstrap_idempotente(instalado):
    api = cliente.N8n.autenticado()
    creds_antes = {c["name"]: c["id"] for c in api.listar_credenciais()}
    chaves_antes = sorted(k["id"] for k in api.listar_api_keys())

    rel = bootstrap.executar()

    assert rel["owner"] == "existente"
    assert rel["api_key"] == "existente"
    creds_depois = {c["name"]: c["id"] for c in api.listar_credenciais()}
    assert creds_depois == creds_antes, "a 2ª execução criou ou trocou credencial"
    assert sorted(k["id"] for k in api.listar_api_keys()) == chaves_antes
    for nome in ("fopa-postgres (n8n_rw)", "worker", "site"):
        assert nome in creds_depois
        assert rel["credenciais"][nome] == "existente"
    # SMTP_HOST vazio no docker/.env: a credencial NÃO existe e o motivo é dito.
    if not cliente.ler_env().get("SMTP_HOST"):
        assert "smtp" not in creds_depois
        assert rel["credenciais"]["smtp"].startswith("ausente")
    # Segredos só em n8n/.segredos (gitignorado), nunca no relatório.
    assert cliente.ARQ_API_KEY.exists() and cliente.ARQ_OWNER.exists()
    bruto = json.dumps(rel)
    env = cliente.ler_env()
    for k in ("N8N_RW_PASSWORD", "FOPA_WORKER_TOKEN", "FOPA_SITE_TOKEN", "JEV_API_KEY"):
        if env.get(k):
            assert env[k] not in bruto
    # Jev: credencial só com chave; sem ela, o motivo é dito (nunca silêncio).
    if env.get("JEV_API_KEY"):
        assert "jev" in creds_depois and rel["credenciais"]["jev"] == "existente"
    else:
        assert "jev" not in creds_depois and rel["credenciais"]["jev"].startswith("ausente")


# ------------------------------------------------------------------ importar
def test_importar_sobe_os_tres_e_nao_duplica(instalado):
    api = cliente.N8n.autenticado()
    antes = _fluxos_fopa(api)
    assert set(antes) == FLUXOS, "faltou fluxo: %s" % (FLUXOS - set(antes))

    rel2 = importar.importar()

    depois = _fluxos_fopa(api)
    assert {n: w["id"] for n, w in depois.items()} == {n: w["id"] for n, w in antes.items()}
    assert len([w for w in api.listar_workflows() if w["name"] in FLUXOS]) == 3
    for nome in FLUXOS:
        assert rel2[nome]["acao"] == "inalterado", rel2[nome]
        assert rel2[nome]["publicado"] is True


def test_placeholders_resolvidos_e_error_workflow_so_nas_raizes(instalado):
    api = cliente.N8n.autenticado()
    wfs = _fluxos_fopa(api)
    id_w90 = wfs["W90 Erro"]["id"]
    for nome in FLUXOS:
        wf = api.workflow(wfs[nome]["id"])
        bruto = json.dumps(wf, ensure_ascii=False)
        assert "{{WF:" not in bruto and "{{CRED:" not in bruto, nome
        erro = (wf.get("settings") or {}).get("errorWorkflow")
        if nome == "W90 Erro":
            assert not erro, "W90 apontando para si mesmo faria laço"
        else:
            assert erro == id_w90
        # Quem avalia lê o canvas: todo fluxo tem Sticky com 'regra — script:linha'.
        stickies = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.stickyNote"]
        assert any("—" in n["parameters"]["content"] and ".py:" in n["parameters"]["content"]
                   for n in stickies), nome
    # W00 exposto no MCP da instância.
    assert (api.workflow(wfs["W00 Saúde"]["id"]).get("settings") or {}).get("availableInMCP") is True


# ------------------------------------------------------------ exportar/importar
def _forma(wf: dict) -> tuple:
    nos = sorted((n["name"], n["type"], n.get("typeVersion"),
                  json.dumps(n.get("parameters"), sort_keys=True, ensure_ascii=False),
                  json.dumps(n.get("credentials"), sort_keys=True, ensure_ascii=False))
                 for n in wf["nodes"])
    return nos, json.dumps(wf["connections"], sort_keys=True, ensure_ascii=False)


def test_exportar_importar_ida_e_volta(instalado, tmp_path):
    arquivos = exportar.exportar(tmp_path)
    assert {p.name for p in arquivos} >= {"W00.json", "W50.json", "W90.json"}

    # Só o que está versionado faz a ida e volta. Um fluxo que outro trabalho ainda
    # monta na instância (sem JSON em n8n/workflows) sai do exportar mas NÃO volta:
    # importar publica, e publicar o rascunho alheio ligaria o schedule dele.
    versionados = {p.name for p in importar.PASTA_WORKFLOWS.glob("*.json")}
    for p in [p for p in arquivos if p.name not in versionados]:
        p.unlink()
    arquivos = [p for p in arquivos if p.name in versionados]

    for p in arquivos:
        exportado = json.loads(p.read_text(encoding="utf-8"))
        fonte = json.loads((importar.PASTA_WORKFLOWS / p.name).read_text(encoding="utf-8"))
        assert _forma(exportado) == _forma(fonte), "exportar não devolveu o mesmo fluxo: %s" % p.name
        bruto = p.read_text(encoding="utf-8")
        # Nenhum id real vai para o git: fluxo e credencial viram placeholder.
        assert "{{CRED:fopa-postgres (n8n_rw)}}" in bruto
        # Error Workflow volta como estava: {{WF:W90}} nas raízes (W00, W50, W20...),
        # ausente no W90 e nas folhas W21-W24 (plano §5 W90: nunca nas folhas).
        erro_fonte = (fonte.get("settings") or {}).get("errorWorkflow")
        assert (exportado.get("settings") or {}).get("errorWorkflow") == erro_fonte, p.name
        if erro_fonte:
            assert '"errorWorkflow": "{{WF:W90}}"' in bruto

    api = cliente.N8n.autenticado()
    ids_antes = {n: w["id"] for n, w in _fluxos_fopa(api).items()}
    rel = importar.importar(tmp_path)
    assert {n: w["id"] for n, w in _fluxos_fopa(api).items()} == ids_antes
    assert all(r["acao"] == "inalterado" for r in rel.values()), rel


# ------------------------------------------------------------------ W00
def test_w00_manual_grava_saude(instalado, pg):
    (ultimo,) = pg.execute("SELECT coalesce(max(id), 0) FROM saude").fetchone()

    execucao = executar.executar("W00 Saúde", timeout=120)

    assert execucao["status"] == "success", execucao
    linhas = pg.execute("SELECT worker_ok, tesseract, git_sha, tessdata_sha256, detalhes->>'link_execucao' "
                        "FROM saude WHERE id > %s AND detalhes->>'n8n_execution_id' = %s",
                        (ultimo, str(execucao["id"]))).fetchall()
    assert len(linhas) == 1, "W00 deveria gravar exatamente uma linha em saude"
    worker_ok, tesseract, git_sha, sha, link = linhas[0]
    assert worker_ok is True
    assert tesseract.startswith("5.4.0")
    assert git_sha
    assert sha == cliente.ler_env().get("FOPA_TESSDATA_SHA256", cliente.TESSDATA_SHA256_PADRAO)
    # O link sai da base pública do n8n SEM supor barra no fim (docker/compose.yml: WEBHOOK_URL e
    # N8N_EDITOR_BASE_URL = FOPA_N8N_PUBLIC_URL). Antes: $env.WEBHOOK_URL + 'workflow/...'.
    wid = next(w["id"] for w in cliente.N8n.autenticado().listar_workflows() if w["name"] == "W00 Saúde")
    base = cliente.ler_env().get("FOPA_N8N_PUBLIC_URL", "").strip().rstrip("/")
    assert link == ("%s/workflow/%s/executions/%s" % (base, wid, execucao["id"]) if base else "")


def rodar_code_node(codigo: str, nos: dict, env: dict, entrada: dict | None = None) -> list:
    """Executa o jsCode de um Code node no Node do próprio fopa-n8n, com $input, $('Nó'), $env,
    $workflow e $execution de mentira: testa o código versionado sem Node no host."""
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


def test_w00_link_da_execucao_nao_supoe_barra_no_fim(instalado):
    wf = json.loads((importar.PASTA_WORKFLOWS / "W00.json").read_text(encoding="utf-8"))
    nos = {n["name"]: n for n in wf["nodes"]}
    repl = nos["Enfileirar e-mail de erro"]["parameters"]["options"]["queryReplacement"]
    assert "WEBHOOK_URL" not in repl and "corpo_email" in repl, "o link frágil (supõe a barra) voltou ao e-mail"
    codigo = nos["Avaliar contrato"]["parameters"]["jsCode"]
    # O caminho de FALHA (é nele que o link vai para o e-mail): worker com Tesseract errado.
    health = {"statusCode": 503, "body": {"ok": False, "tesseract": "5.3.0", "erro": "tesseract <b>errado</b>"}}
    certo = "http://n8n.exemplo:5679/workflow/wfTESTE/executions/4242"
    for base, esperado in (("http://n8n.exemplo:5679/", certo), ("http://n8n.exemplo:5679", certo),
                           ("http://n8n.exemplo:5679//", certo), ("", "")):
        (r,) = rodar_code_node(codigo, {}, {"WEBHOOK_URL": base, "FOPA_TESSERACT_ESPERADO": "5.4.0"}, health)
        j = r["json"]
        assert j["worker_ok"] is False and j["motivos"], base
        assert j["link_execucao"] == esperado and j["detalhes"]["link_execucao"] == esperado, base
        assert "<b>errado</b>" not in j["corpo_email"] and "&lt;b&gt;errado" in j["corpo_email"], \
            "o motivo vem do worker: vai escapado para o HTML"
        if esperado:
            assert 'href="%s"' % esperado in j["corpo_email"]
        else:
            assert "href" not in j["corpo_email"] and "Execução 4242" in j["corpo_email"]
    # N8N_EDITOR_BASE_URL (a do editor) vale mais que WEBHOOK_URL quando existe.
    (r,) = rodar_code_node(codigo, {}, {"N8N_EDITOR_BASE_URL": "https://ed.x/", "WEBHOOK_URL": "https://wh.x/"},
                           health)
    assert r["json"]["link_execucao"] == "https://ed.x/workflow/wfTESTE/executions/4242"


# ------------------------------------------------------------------ W50
W50 = "W50 Envio de e-mails"
RE_PROXIMA = re.compile(r"nova tentativa a partir de (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")


def _linha_email(pg, eid):
    return pg.execute("SELECT status, erro, tentativas, canal FROM emails WHERE id = %s", (eid,)).fetchone()


def _esperar_fora_de_envio(pg, eid, tentativas_min, segundos=150):
    """Espera o W50 (agendado ou manual) terminar a tentativa: marca 'em envio' fora e contagem >= n."""
    limite = time.time() + segundos
    linha = None
    while time.time() < limite:
        linha = _linha_email(pg, eid)
        status, erro, tentativas, _ = linha
        if tentativas >= tentativas_min and not (erro or "").startswith("em envio"):
            return linha
        time.sleep(2)
    raise AssertionError("o W50 não terminou a tentativa %d em %d s: %r" % (tentativas_min, segundos, linha))


def test_w50_sem_smtp_1a_falha_volta_para_a_fila(instalado, pg):
    if cliente.ler_env().get("SMTP_HOST"):
        pytest.skip("SMTP_HOST preenchido: este teste prova o caminho SEM SMTP")
    assunto = "[FOPA][TESTE] W50 sem SMTP %s" % uuid.uuid4().hex[:8]
    (eid,) = pg.execute("INSERT INTO emails (tipo, assunto, corpo_html) VALUES ('licitacao_nova', %s, '<p>teste</p>') "
                        "RETURNING id", (assunto,)).fetchone()
    try:
        # O W50 publicado roda a cada minuto: é o caminho de produção, não um atalho.
        status, erro, tentativas, canal = _esperar_fora_de_envio(pg, eid, 1)
        # 'enviado' aqui seria mentira: foi o que a 1ª versão do W50 fez, porque o
        # n8n repassa o item de entrada sem marca de erro quando o Send Email
        # morre antes do laço (credencial ausente). O fluxo tem de conferir o aceite.
        assert status != "enviado", "e-mail marcado como enviado sem servidor SMTP"
        # A 1ª falha NÃO é definitiva (antes era: 'falhou' com tentativas=1). Volta para a fila,
        # com o motivo e a hora da próxima tentativa escritos na linha — nunca silêncio.
        assert status == "pendente", "a 1ª falha virou %r: devia voltar para a fila" % status
        assert tentativas == 1
        assert erro.startswith("tentativa 1/5 falhou; nova tentativa a partir de "), erro
        assert "smtp" in erro.lower(), "o erro tem de dizer que falta o SMTP: %r" % erro
        assert canal == "smtp"
        (espera,) = pg.execute("SELECT extract(epoch FROM %s::timestamptz - now())",
                               (RE_PROXIMA.search(erro).group(1),)).fetchone()
        assert 60 <= float(espera) <= 120, "a 1ª espera é de 2 min: %s s" % espera
    finally:
        pg.execute("DELETE FROM emails WHERE id = %s", (eid,))


def test_w50_retenta_com_espera_crescente_e_so_falha_na_5a(instalado, pg):
    if cliente.ler_env().get("SMTP_HOST"):
        pytest.skip("SMTP_HOST preenchido: este teste prova o caminho SEM SMTP")
    assunto = "[FOPA][TESTE] W50 5 tentativas %s" % uuid.uuid4().hex[:8]
    (eid,) = pg.execute("INSERT INTO emails (tipo, assunto, corpo_html) VALUES ('licitacao_nova', %s, '<p>teste</p>') "
                        "RETURNING id", (assunto,)).fetchone()
    esperas = []
    try:
        for k in range(1, 6):
            # O tempo "passa": a hora da próxima tentativa vai para o passado e o W50 roda pela mão.
            pg.execute("UPDATE emails SET erro = regexp_replace(erro, 'a partir de [0-9TZ:-]+',"
                       " 'a partir de 2000-01-01T00:00:00Z') WHERE id = %s AND erro LIKE 'tentativa %%'", (eid,))
            r = executar.executar(W50, timeout=120)
            assert r["status"] == "success", r
            status, erro, tentativas, canal = _esperar_fora_de_envio(pg, eid, k)
            assert tentativas == k and status != "enviado"
            if k < 5:
                assert status == "pendente", "tentativa %d virou %r: só a 5ª é definitiva" % (k, status)
                assert erro.startswith("tentativa %d/5 falhou; nova tentativa a partir de " % k), erro
                (espera,) = pg.execute("SELECT extract(epoch FROM %s::timestamptz - now())",
                                       (RE_PROXIMA.search(erro).group(1),)).fetchone()
                esperas.append(float(espera))
                if k == 1:
                    # Sem o tempo passar, a rodada seguinte NÃO pega o e-mail: a espera vale.
                    assert executar.executar(W50, timeout=120)["status"] == "success"
                    assert _linha_email(pg, eid)[2] == 1, "o W50 retentou antes da hora"
            else:
                assert status == "falhou", "na 5ª tentativa o e-mail tem de virar 'falhou': %r" % status
                assert erro.startswith("falhou nas 5 tentativas; a última: ") and "smtp" in erro.lower(), erro
                assert canal == "smtp"
        # 2, 5, 15, 40 min: cada espera maior que a anterior.
        assert all(a < b for a, b in zip(esperas, esperas[1:])), esperas
        assert 60 <= esperas[0] <= 120 and 38 * 60 <= esperas[-1] <= 40 * 60, esperas
    finally:
        pg.execute("DELETE FROM emails WHERE id = %s", (eid,))


def test_w50_solta_marca_orfa_e_respeita_envio_em_curso(instalado, pg):
    base = random.randint(900_000_000, 999_000_000)
    exec_orfa, exec_esgotada, exec_viva = (str(base + i) for i in (1, 2, 3))
    (inicio,) = pg.execute("SELECT now()").fetchone()
    ids = []
    try:
        for tentativas, exec_id in ((1, exec_orfa), (5, exec_esgotada), (1, exec_viva)):
            (eid,) = pg.execute(
                "INSERT INTO emails (tipo, assunto, corpo_html, tentativas, erro) VALUES ('licitacao_nova', %s, '<p>teste</p>',"
                " %s, %s) RETURNING id",
                ("[FOPA][TESTE] W50 marca órfã %s" % exec_id, tentativas, "em envio: W50 execução " + exec_id)
            ).fetchone()
            ids.append(eid)
        orfa, esgotada, viva = ids
        # A reserva da 'viva' é recente (execução em curso): a marca dela NÃO pode ser solta.
        pg.execute("INSERT INTO execucoes_workflow (workflow, n8n_execution_id, gatilho, status)"
                   " VALUES ('W50', %s, 'teste', 'em_curso')", (exec_viva,))

        assert executar.executar(W50, timeout=120)["status"] == "success"

        # Órfã (execução morta sem Error Workflow, sem registro de reserva): volta para a fila.
        status, erro, tentativas, _ = _esperar_fora_de_envio(pg, orfa, 1, segundos=90)
        assert status == "pendente" and erro != "em envio: W50 execução " + exec_orfa
        assert erro.startswith("marca órfã solta pelo W50 execução ") or erro.startswith("tentativa 2/5"), erro
        # Órfã que já gastou as 5 tentativas: vira 'falhou' com o motivo, nunca fica parada.
        status, erro, tentativas, _ = _linha_email(pg, esgotada)
        assert (status, tentativas) == ("falhou", 5) and "5 tentativas gastas" in erro, erro
        # Em curso: intocada.
        assert _linha_email(pg, viva)[:3] == ("pendente", "em envio: W50 execução " + exec_viva, 1)
        (soltas,) = pg.execute("SELECT coalesce(sum((contadores->>'orfas_soltas')::int), 0) FROM execucoes_workflow"
                               " WHERE workflow = 'W50' AND iniciado_em >= %s", (inicio,)).fetchone()
        assert soltas >= 2, "a rodada do W50 registra quantas marcas órfãs soltou"

        # 31 minutos depois da reserva, a mesma marca já é órfã.
        pg.execute("UPDATE execucoes_workflow SET iniciado_em = now() - interval '31 minutes'"
                   " WHERE workflow = 'W50' AND n8n_execution_id = %s AND gatilho = 'teste'", (exec_viva,))
        assert executar.executar(W50, timeout=120)["status"] == "success"
        status, erro, _, _ = _esperar_fora_de_envio(pg, viva, 1, segundos=90)
        assert status == "pendente" and erro != "em envio: W50 execução " + exec_viva, erro
    finally:
        for eid in ids:
            pg.execute("DELETE FROM emails WHERE id = %s", (eid,))
        pg.execute("DELETE FROM execucoes_workflow WHERE workflow = 'W50' AND n8n_execution_id = %s"
                   " AND gatilho = 'teste'", (exec_viva,))


# ------------------------------------------------------------------ W90
def _sql_no(arquivo: str, no: str) -> str:
    """A consulta do nó como está no JSON versionado, com $n trocado pelo placeholder do psycopg."""
    wf = json.loads((importar.PASTA_WORKFLOWS / arquivo).read_text(encoding="utf-8"))
    (q,) = [n["parameters"]["query"] for n in wf["nodes"] if n["name"] == no]
    return re.sub(r"\$(\d+)", r"%(p\1)s", q.replace("%", "%%"))


def test_w90_solta_emails_do_w50_com_a_mesma_espera_do_w50(pg):
    # Quando o W50 morria no meio do lote, o W90 marcava 'falhou' na hora os
    # e-mails 'em envio' daquela execução — enquanto o próprio W50 dá 5
    # tentativas com espera crescente. Uma queda do SMTP no meio do lote matava
    # e-mails que o W50 teria reenviado. Agora o W90 segue a regra do W50:
    # volta para a fila com "nova tentativa a partir de" (que a reserva lê) e só
    # vira 'falhou' na 5ª. Roda o SQL do JSON direto no Postgres, dentro de uma
    # transação desfeita no fim: o W50 agendado nunca vê as linhas de teste.
    sql = _sql_no("W90.json", "Soltar e-mails do W50")
    exec_id = "TESTE-W90-%s" % uuid.uuid4().hex[:8]
    with pg.transaction(force_rollback=True):
        ids = {}
        for nome, tent, marca in (("1a", 1, exec_id), ("5a", 5, exec_id), ("outra", 2, "OUTRA-" + exec_id)):
            (ids[nome],) = pg.execute(
                "INSERT INTO emails (tipo, assunto, corpo_html, tentativas, erro) "
                "VALUES ('licitacao_nova', %s, '<p>t</p>', %s, %s) RETURNING id",
                ("[FOPA][TESTE] W90 " + nome, tent, "em envio: W50 execução " + marca)).fetchone()
        antes = pg.execute("SELECT now()").fetchone()[0]
        soltos = pg.execute(sql, {"p1": exec_id, "p2": "SMTP caiu no meio do lote"}).fetchall()
        assert sorted(r[0] for r in soltos) == sorted([ids["1a"], ids["5a"]])

        status, erro, tentativas, _ = _linha_email(pg, ids["1a"])
        assert (status, tentativas) == ("pendente", 1), (status, erro)
        assert erro.startswith("tentativa 1/5 falhou; nova tentativa a partir de "), erro
        assert "W50 morreu no meio do envio (execução %s): SMTP caiu" % exec_id in erro, erro
        proxima = RE_PROXIMA.search(erro).group(1)
        atraso = pg.execute("SELECT extract(epoch FROM %s::timestamptz - %s)", (proxima, antes)).fetchone()[0]
        assert 100 <= atraso <= 130, "a 1ª espera do W50 é de 2 min: %s s" % atraso

        status, erro, tentativas, _ = _linha_email(pg, ids["5a"])
        assert (status, tentativas) == ("falhou", 5), (status, erro)
        assert erro.startswith("falhou nas 5 tentativas; a última: W50 morreu no meio do envio"), erro

        status, erro, _, _ = _linha_email(pg, ids["outra"])
        assert (status, erro) == ("pendente", "em envio: W50 execução OUTRA-" + exec_id), \
            "marca de OUTRA execução do W50 não é do W90 soltar"
    assert pg.execute("SELECT count(*) FROM emails WHERE assunto LIKE '[FOPA][TESTE] W90 %%'").fetchone()[0] == 0


def test_w50_manda_para_o_destinatario_da_linha_ou_para_os_admins(pg):
    # db/038: a extração do botão vai para QUEM pediu (emails.para); a licitação nova, sem `para`, vai
    # para os admins ativos. Roda o SQL da reserva do JSON direto no Postgres, numa transação desfeita no fim.
    sql = _sql_no("W50.json", "Reservar pendentes")
    with pg.transaction(force_rollback=True):
        admins = pg.execute("SELECT string_agg(email, ',' ORDER BY email) FROM usuarios"
                            " WHERE papel = 'admin' AND ativo").fetchone()[0]
        (com,) = pg.execute("INSERT INTO emails (tipo, assunto, para, em) VALUES ('extracao', '[FOPA][TESTE] W50 para',"
                            " 'quem@pediu.br', '2000-01-01') RETURNING id").fetchone()
        (sem,) = pg.execute("INSERT INTO emails (tipo, assunto, em) VALUES ('licitacao_nova',"
                            " '[FOPA][TESTE] W50 admins', '2000-01-01') RETURNING id").fetchone()
        para = {r[0]: r[6] for r in pg.execute(sql, {"p1": "TESTE-W50-PARA", "p2": "teste"}).fetchall()}
        assert para[com] == "quem@pediu.br"
        assert para[sem] == admins
    assert pg.execute("SELECT count(*) FROM emails WHERE assunto LIKE '[FOPA][TESTE] W50 %%'").fetchone()[0] == 0
