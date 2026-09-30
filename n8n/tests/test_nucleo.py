# -*- coding: utf-8 -*-
"""
O núcleo do n8n da FOPA contra a instância e o banco de verdade: W21 Baixar,
W22 Ler, W23 Extrair, W24 Verificar e publicar e o orquestrador W20 (plano,
seção 5). Sem mock, como test_n8n.py: o que quebra no n8n (bigint que o nó
Postgres devolve como texto, laço Wait → GET, sub-fluxo que não devolve item)
só a instância real mostra.

DINHEIRO: zero. O provedor vem de `configuracao.provedor` (db/016) e o módulo
se recusa a rodar se ele não for `simulado` ou `gravado`, e se existir na
instância qualquer credencial de modelo pago. Os ramos `claude`/`openai` do W23
existem no canvas e aqui só se confere a forma deles — nunca são executados.

DADOS:
  - ENSAIO — Presidente Getúlio/SC 83102434000120-1-000111/2026: licitação
    REAL de 2026, 1 PDF digital de 216 KB, marcada `ensaio = true` (T15: é a
    única forma de uma execução simulada virar verificação vigente sem sujar o
    acervo real). O PNCP é consultado de verdade (grátis): 2 downloads por
    rodada do módulo, sempre dela. A cada rodada ela é "retificada" por
    fn_transicao e percorre o caminho inteiro de novo.
  - FALHA / PARCIAL — controles de teste (CNPJ zerado) criados e APAGADOS pelo
    próprio teste: o ramo de erro (PDF ausente do storage) e a retomada de uma
    execução parcial. Nada de rede, nada no storage.
  - Guarda: uma licitação de 2025 `preparada` e uma fora do escopo, lidas do
    acervo; o W23 as recusa sem gravar nada (só se confere que nada mudou).
  - REPUB — controle de teste que percorre W23 + W24 (simulado, ensaio) e tem a
    vigente "envelhecida" à mão (versao_regras de outra versão, um veredito e um
    alerta trocados): é o alvo do W30 e do W24 modo republicar. Apagado no fim.
    O W30 roda SEMPRE com `controles` explícitos: rodado sem eles reverificaria
    o acervo publicado inteiro (ADR-014: mudar número é decisão).
  - JEV — só com FOPA_TESTE_JEV_REAL=1: uma licitação de teste com execução de
    `agente` (não simulada) para provar a chamada real ao Jev (centavos de US$).

Execuções manuais NÃO disparam o W90 (limitação do n8n): o que se prova aqui é
o ramo `{ok:false}` do próprio W20, não a morte do W20.

Outros agentes testam na mesma instância: este módulo importa SÓ os fluxos dele
(W20-W24, W30) e não pode rodar em paralelo consigo mesmo.

    python -m pytest n8n/tests/test_nucleo.py -v
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
import sys

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

import cliente  # noqa: E402
import executar  # noqa: E402
import importar  # noqa: E402

psycopg = pytest.importorskip("psycopg")
from psycopg.rows import dict_row  # noqa: E402

ENSAIO = "83102434000120-1-000111/2026"
FALHA = "00000000000000-1-000920/2026"
PARCIAL = "00000000000000-1-000921/2026"
REPUB = "00000000000000-1-000922/2026"
JEVTESTE = "00000000000000-1-000923/2026"
IDS = ["Q%d" % i for i in range(1, 18)]

W20, W21, W22, W23, W24 = ("W20 Processar uma licitação", "W21 Baixar", "W22 Ler", "W23 Extrair",
                           "W24 Verificar e publicar")
W30 = "W30 Reverificar em lote"
NUCLEO = (W20, W21, W22, W23, W24)
NOS_PAGOS = ("Anthropic /v1/messages", "OpenAI /v1/responses")
NOS_JEV = ("Jev: montar corpos (worker)", "Jev (TypeSafe)", "Jev: interpretar (worker)")
RAIZ = AQUI.parent.parent


def json_do_fluxo(codigo: str) -> Path:
    """O versionado em n8n/workflows; enquanto não foi movido, o do rascunho (n8n/rascunho/<Wnn>)."""
    p = importar.PASTA_WORKFLOWS / ("%s.json" % codigo)
    return p if p.exists() else AQUI.parent / "rascunho" / codigo / ("%s.json" % codigo)


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def instalado(tmp_path_factory):
    """Importa SÓ os fluxos deste módulo: a pasta n8n/workflows tem os de outros agentes em curso."""
    if not cliente.no_ar():
        pytest.skip("fopa-n8n fora do ar em %s" % cliente.base())
    pasta = tmp_path_factory.mktemp("nucleo")
    for codigo in ("W20", "W21", "W22", "W23", "W24", "W30"):
        shutil.copy(json_do_fluxo(codigo), pasta / ("%s.json" % codigo))
    rel = importar.importar(pasta)
    for nome in NUCLEO + (W30,):
        assert rel[nome]["publicado"] is True, rel[nome]
    return rel


@pytest.fixture(scope="module")
def pg():
    env = cliente.ler_env()
    url = "postgresql://postgres:%s@127.0.0.1:5433/fopa" % env["POSTGRES_PASSWORD"]
    try:
        con = psycopg.connect(url, connect_timeout=5, autocommit=True, row_factory=dict_row)
    except psycopg.OperationalError:
        pytest.skip("fopa-postgres fora do ar em 127.0.0.1:5433")
    # Duas rodadas deste módulo ao mesmo tempo (a CI e um agente, 24/09 09:15) disputam a MESMA licitação de
    # ensaio: um W21 tentou lendo → baixada_ok e morreu com o lease na mão. Uma trava de sessão no Postgres
    # põe a segunda rodada na fila (qualquer processo, qualquer máquina que use este banco).
    con.execute("SET lock_timeout = '20min'")
    con.execute("SELECT pg_advisory_lock(hashtext('fopa:n8n/tests/test_nucleo'))")
    yield con
    con.execute("SELECT pg_advisory_unlock(hashtext('fopa:n8n/tests/test_nucleo'))")
    con.close()


@pytest.fixture(scope="module")
def gratis(pg, instalado):
    """
    Trava de dinheiro: só roda W23 com provedor de custo zero e sem pedido de IA paga na licitação de ensaio.

    Até 25/09 a trava era "nenhuma credencial paga na instância". Então foi criada a `openai` para o botão "Extrair com
    GPT" (db/033): ter a credencial não gasta — gasta o PEDIDO, que vale só para a licitação pedida
    (fn_provedor_pedido), e o provedor geral segue simulado. A trava passa a ser essa.
    """
    (prov,) = pg.execute("SELECT valor #>> '{}' FROM configuracao WHERE chave = 'provedor'").fetchone().values()
    if prov not in ("simulado", "gravado"):
        pytest.fail("configuracao.provedor = %r GASTA: o teste não roda o W23 (só simulado/gravado)" % prov)
    (pedido,) = pg.execute("SELECT fn_provedor_pedido(%s)", (ENSAIO,)).fetchone().values()
    assert pedido is None, "há pedido de extração com %s na licitação de ensaio: o W23 GASTARIA" % pedido
    return prov


# Revisões que o W24 abre na licitação de ENSAIO a cada publicação simulada (REVISAR em pergunta
# crítica) são ruído na fila humana do site: nenhum modelo respondeu. O módulo as fecha no fim,
# com nome e motivo — nunca apaga (revisoes_humanas é a camada humana, T25).
SQL_FECHAR_REVISOES_DO_ENSAIO = """
UPDATE revisoes_humanas r
   SET status = 'rejeitada', decidido_por = 'n8n/tests/test_nucleo.py', decidido_em = now(),
       nota = 'fechada pelo teste do núcleo: aberta por execução ' || e.origem || ' na licitação de ensaio '
              || '(provedor sem modelo; não há resposta de modelo a revisar)'
  FROM verificacoes v JOIN execucoes_modelo e ON e.id = v.execucao_id
 WHERE r.verificacao_id = v.id AND r.controle = %s AND r.status = 'aberta'
   AND e.origem IN ('simulado', 'gravado')
RETURNING r.id, r.verificacao_id, r.pergunta_id"""


RESUMOS_W30: list = []      # e-mails 'reverificacao' das rodadas de TESTE do W30 (controle NULL: o _limpar não os vê)


@pytest.fixture(scope="module", autouse=True)
def fechar_revisoes_do_ensaio(pg):
    yield
    pg.execute(SQL_FECHAR_REVISOES_DO_ENSAIO, (ENSAIO,))
    if RESUMOS_W30:
        pg.execute("DELETE FROM emails WHERE tipo = 'reverificacao' AND id = ANY(%s)", (RESUMOS_W30,))


def _limpar(pg, controle: str) -> None:
    """Apaga TUDO de um controle de teste (só os de CNPJ zerado; nunca o acervo)."""
    assert controle.startswith("00000000000000-"), controle
    c = (controle,)
    pg.execute("UPDATE licitacoes SET leitura_vigente_id = NULL, gemea_de = NULL WHERE controle = %s", c)
    pg.execute("UPDATE licitacoes SET gemea_de = NULL WHERE gemea_de = %s", c)
    pg.execute("DELETE FROM revisoes_humanas WHERE controle = %s", c)
    pg.execute("DELETE FROM sinais_jev WHERE controle = %s", c)          # antes de verificacoes (FK)
    pg.execute("DELETE FROM publicacoes WHERE controle = %s", c)
    pg.execute("DELETE FROM verificacao_respostas WHERE verificacao_id IN "
               "(SELECT id FROM verificacoes WHERE controle = %s)", c)
    pg.execute("DELETE FROM verificacoes WHERE controle = %s", c)
    pg.execute("DELETE FROM respostas WHERE execucao_id IN (SELECT id FROM execucoes_modelo WHERE controle = %s)", c)
    pg.execute("DELETE FROM chamadas_modelo WHERE execucao_id IN "
               "(SELECT id FROM execucoes_modelo WHERE controle = %s)", c)
    pg.execute("DELETE FROM execucoes_modelo WHERE controle = %s", c)
    pg.execute("DELETE FROM paginas WHERE leitura_id IN (SELECT id FROM leituras WHERE controle = %s)", c)
    pg.execute("DELETE FROM leituras WHERE controle = %s", c)
    for tabela in ("arquivos", "emails", "jobs", "licitacao_eventos", "execucoes_workflow", "itens_api",
                   "rotulos_escopo", "gabaritos", "pastas_legado"):
        pg.execute("DELETE FROM %s WHERE controle = %%s" % tabela, c)
    pg.execute("DELETE FROM licitacoes WHERE controle = %s", c)
    # Os RELATORIOs que o /render gravou para o controle de teste (html/{slug}/...) somem junto.
    if shutil.which("docker"):
        subprocess.run(["docker", "exec", "fopa-worker", "rm", "-rf", "--",
                        "/dados/html/" + controle.replace("/", "-")], capture_output=True, timeout=60)


def _nascer(pg, controle: str, estado: str, objeto: str) -> None:
    pg.execute(
        "INSERT INTO licitacoes (controle, orgao, uf, municipio, modalidade, objeto, publicado_em, escopo_dentro,"
        " escopo_motivo, estado, ensaio, origem, solicitante)"
        " VALUES (%s, 'TESTE n8n núcleo', 'SC', 'Teste', 'Dispensa', %s, '2026-09-01', true, 'teste', %s, true,"
        " 'manual', 'n8n/tests/test_nucleo.py')", (controle, objeto, estado))


@pytest.fixture
def quebrada(pg):
    """`baixada_ok` com um arquivo `ok` cujo objeto NÃO está no storage: o job de leitura falha de verdade."""
    _limpar(pg, FALHA)
    _nascer(pg, FALHA, "baixada_ok", "folha de pagamento — TESTE: PDF ausente do storage (ramo de erro do W20)")
    pg.execute("INSERT INTO arquivos (controle, seq, tipo, titulo, nome, sha256, bytes, status, storage_key, proveniencia)"
               " VALUES (%s, 1, 'Edital', 'teste', '01 - Edital - teste.pdf', repeat('0', 64), 1, 'ok',"
               " 'pdf/00000000000000/2026/920/' || repeat('0', 64) || '.pdf', '{\"teste\": true}')", (FALHA,))
    yield FALHA
    _limpar(pg, FALHA)


NOME_PDF = "01 - Edital - teste.pdf"
TEXTO = ("PREFEITURA DE TESTE. EDITAL DE DISPENSA Nº 1/2026. OBJETO: contratação de instituição financeira "
         "para processamento da folha de pagamento dos servidores. VIGÊNCIA: 60 (sessenta) meses. "
         "VALOR MÍNIMO: R$ 1.000.000,00. PRAZO PARA ASSINATURA DO CONTRATO: 5 (cinco) dias úteis.")


def _leitura_sintetica(pg, controle: str) -> tuple[int, int]:
    """Um arquivo e uma leitura vigente de 1 página com TEXTO — sem PDF, sem OCR, sem rede. (arquivo_id, leitura_id)"""
    (aid,) = pg.execute("INSERT INTO arquivos (controle, seq, nome, sha256, bytes, status, proveniencia)"
                        " VALUES (%s, 1, %s, repeat('1', 64), 1, 'ok', '{\"teste\": true}') RETURNING id",
                        (controle, NOME_PDF)).fetchone().values()
    assinatura = json.dumps({NOME_PDF: "1" * 64})
    (lid,) = pg.execute(
        "INSERT INTO leituras (controle, versao_ocr, condicoes, hashes_bytes, assinatura, assinatura_conjunto,"
        " assinatura_nomes, modo_sugerido, chars_total, procedencia_texto, vigente)"
        " VALUES (%s, 'teste-sem-ocr', '{}', '{}', %s::jsonb, repeat('b', 64), fn_assinatura_nomes(%s::jsonb),"
        " 'contexto-completo', %s, 'worker', true) RETURNING id",
        (controle, assinatura, assinatura, len(TEXTO))).fetchone().values()
    pg.execute("INSERT INTO paginas (leitura_id, arquivo_id, arquivo_nome, numero, ordem, texto)"
               " VALUES (%s, %s, %s, 1, 0, %s)", (lid, aid, NOME_PDF, TEXTO))
    pg.execute("UPDATE licitacoes SET leitura_vigente_id = %s WHERE controle = %s", (lid, controle))
    # sem itens da API: o W24 não vai ao PNCP por um CNPJ que não existe
    pg.execute("INSERT INTO itens_api (controle, payload) VALUES (%s, '[]')", (controle,))
    return aid, lid


@pytest.fixture
def parcial(pg, gratis):
    """
    `erro_extracao` com leitura sintética e uma execução PARCIAL que já pagou o lote Q1-Q6 — o que o W23
    deixa quando um lote falha (plano §5 W23 passo 13). A próxima extração tem de mandar só Q7..Q17.
    """
    _limpar(pg, PARCIAL)
    _nascer(pg, PARCIAL, "erro_extracao", "folha de pagamento — TESTE: retomada de execução parcial")
    aid, lid = _leitura_sintetica(pg, PARCIAL)
    (eid,) = pg.execute(
        "INSERT INTO execucoes_modelo (controle, leitura_id, origem, provedor, modelo, modo, effort, lote, k_rag,"
        " status, erro, canonica) VALUES (%s, %s, %s, %s, 'claude-opus-5', 'contexto-completo', 'high', 6, 6,"
        " 'parcial', 'teste: lote Q7-Q12 falhou', false) RETURNING id",
        (PARCIAL, lid, gratis, gratis)).fetchone().values()
    dados = {"respostas": [{"id": i, "resposta": "Não localizado", "arquivo": None, "pagina": None,
                            "trecho_literal": None, "conflito": None, "confianca": "baixa"} for i in IDS[:6]]}
    pg.execute("INSERT INTO chamadas_modelo (execucao_id, lote_ids, dados, stop_reason, http_status, tentativas,"
               " tok_entrada, tok_saida, tok_cache_escrita, tok_cache_leitura, usd, brl, preco_conhecido)"
               " VALUES (%s, %s, %s::jsonb, 'end_turn', 200, 1, 0, 0, 0, 0, 0, 0, true)",
               (eid, IDS[:6], json.dumps(dados)))
    # a tentativa que falhou também foi gravada (não conta como coberta)
    pg.execute("INSERT INTO chamadas_modelo (execucao_id, lote_ids, dados, stop_reason, http_status, tentativas)"
               " VALUES (%s, %s, '{\"erro\": \"teste\"}', NULL, 503, 3)", (eid, IDS[6:12]))
    yield {"controle": PARCIAL, "execucao_id": eid, "leitura_id": lid}
    _limpar(pg, PARCIAL)


@pytest.fixture
def republicavel(pg, gratis, instalado):
    """
    Publicada DE VERDADE (W23 + W24, simulado, ensaio) e depois envelhecida à mão, como o legado do acervo:
    a vigente passa a ser de outra `versao_regras`, com um veredito (Q2) e um alerta que as regras atuais
    não dão. Assim o /reverificar grava uma verificação nova e o diff tem conteúdo conhecido.
    """
    _limpar(pg, REPUB)
    _nascer(pg, REPUB, "preparada", "folha de pagamento — TESTE: reverificação em lote e republicação")
    _leitura_sintetica(pg, REPUB)
    _, r23 = rodar(W23, controle=REPUB)
    assert r23["estado"] == "respondida", r23
    _, r24 = rodar(W24, controle=REPUB)
    assert r24["estado"] == "publicada", r24
    v1 = int(r24["verificacao_id"])
    atual = pg.execute("SELECT veredito FROM verificacao_respostas WHERE verificacao_id = %s AND pergunta_id = 'Q2'",
                       (v1,)).fetchone()["veredito"]
    velho = "APROVADO" if atual != "APROVADO" else "REVISAR"
    pg.execute("UPDATE verificacoes SET versao_regras = 'legado:teste-w30',"
               " alertas_globais = array_append(coalesce(alertas_globais, '{}'), 'teste: alerta que sai')"
               " WHERE id = %s", (v1,))
    pg.execute("UPDATE verificacao_respostas SET veredito = %s WHERE verificacao_id = %s AND pergunta_id = 'Q2'",
               (velho, v1))
    yield {"controle": REPUB, "v1": v1, "velho": velho, "atual": atual}
    _limpar(pg, REPUB)


@pytest.fixture
def agente_respondida(pg, instalado):
    """
    `respondida` com uma execução de AGENTE (não simulada) cujas respostas citam o TEXTO literalmente: o
    verificador aprova algumas e o W24 pede o sinal do Jev sobre elas. Só para o teste pago (opt-in).
    """
    _limpar(pg, JEVTESTE)
    _nascer(pg, JEVTESTE, "respondida", "folha de pagamento — TESTE: sinal do Jev sobre resposta aprovada")
    _, lid = _leitura_sintetica(pg, JEVTESTE)
    citadas = {
        "Q2": ("contratação de instituição financeira para processamento da folha de pagamento dos servidores",
               "OBJETO: contratação de instituição financeira para processamento da folha de pagamento dos servidores"),
        "Q9": ("60 (sessenta) meses", "VIGÊNCIA: 60 (sessenta) meses"),
    }
    respostas = []
    for i in IDS:
        if i in citadas:
            respostas.append({"id": i, "resposta": citadas[i][0], "arquivo": NOME_PDF, "pagina": 1,
                              "trecho_literal": citadas[i][1], "conflito": None, "confianca": "alta"})
        else:
            respostas.append({"id": i, "resposta": "Não localizado", "arquivo": None, "pagina": None,
                              "trecho_literal": None, "conflito": None, "confianca": "baixa"})
    (eid,) = pg.execute(
        "INSERT INTO execucoes_modelo (controle, leitura_id, origem, provedor, modelo, modo, effort, lote, status,"
        " canonica) VALUES (%s, %s, 'agente', 'claude-code', 'claude-opus-5-5', 'agente', 'agente', 17, 'em_curso',"
        " true) RETURNING id", (JEVTESTE, lid)).fetchone().values()
    pg.execute("INSERT INTO chamadas_modelo (execucao_id, lote_ids, dados, stop_reason, tentativas, preco_conhecido)"
               " VALUES (%s, %s, %s::jsonb, 'end_turn', 1, false)", (eid, IDS, json.dumps({"respostas": respostas})))
    yield {"controle": JEVTESTE, "execucao_id": eid}
    _limpar(pg, JEVTESTE)


# ------------------------------------------------------------------ ajudantes
def rodar(fluxo: str, **entrada):
    # O W30 tem dois gatilhos e o Manual é o acervo INTEIRO: aqui ele parte SEMPRE do de sub-fluxo, pelo nome.
    gatilho = "Chamado por outro fluxo" if fluxo == W30 else None
    r = executar.executar(fluxo, timeout=900, itens=[entrada], com_saidas=True, gatilho=gatilho)
    assert r["status"] == "success", "%s execução %s: %s (último nó %s)" % (fluxo, r["id"], r["erro"], r["ultimo_no"])
    saida = r["saidas"][r["ultimo_no"]][0][0]
    if fluxo == W30 and saida.get("email_id"):
        RESUMOS_W30.append(int(saida["email_id"]))
    return r, saida


def lic(pg, controle: str) -> dict:
    return pg.execute("SELECT * FROM licitacoes WHERE controle = %s", (controle,)).fetchone()


def eventos(pg, controle: str, execucao: str) -> list:
    return [(e["de"], e["para"]) for e in pg.execute(
        "SELECT de::text, para::text FROM licitacao_eventos WHERE controle = %s AND n8n_execution_id = %s"
        " ORDER BY id", (controle, str(execucao))).fetchall()]


def maximo(pg, tabela: str) -> int:
    return pg.execute("SELECT coalesce(max(id), 0) AS m FROM %s" % tabela).fetchone()["m"]


# Estados de onde a licitação de ensaio não pode ir direto para `retificada`: o que um teste
# interrompido pode ter deixado. A ponte passa pela transição que o W90/W10 faria.
PONTE = {"baixando": "falha_rede", "lendo": "erro_leitura", "extraindo": "erro_extracao", "respondida": "verificada"}


def rearmar(pg, controle: str) -> str:
    """Volta a licitação de ensaio ao começo do caminho (nova ou retificada), por fn_transicao."""
    pg.execute("UPDATE licitacoes SET lease_por = NULL, lease_ate = NULL WHERE controle = %s", (controle,))
    estado = lic(pg, controle)["estado"]
    if estado in PONTE:
        pg.execute("SELECT fn_transicao(%s, %s, 'teste n8n núcleo: destravar', NULL)", (controle, PONTE[estado]))
        estado = PONTE[estado]
    if estado not in ("nova", "retificada"):
        pg.execute("SELECT fn_transicao(%s, 'retificada', 'teste n8n núcleo: reprocessar a licitação de ensaio',"
                   " '{\"origem\": \"n8n/tests/test_nucleo.py\"}')", (controle,))
    return lic(pg, controle)["estado"]


# ------------------------------------------------------------------ forma dos fluxos
def test_forma_dos_fluxos_do_nucleo(instalado):
    api = cliente.N8n.autenticado()
    por_nome = {w["name"]: w for w in api.listar_workflows()}
    id_w90 = por_nome["W90 Erro"]["id"]
    for nome in NUCLEO + (W30,):
        wf = api.workflow(por_nome[nome]["id"])
        assert wf.get("active") is True, nome
        s = wf.get("settings") or {}
        assert s.get("executionOrder") == "v1" and s.get("timezone") == "America/Sao_Paulo", nome
        # Error Workflow só nas raízes (plano §5 W90): nas folhas ele dispararia em cascata.
        assert s.get("errorWorkflow") == (id_w90 if nome in (W20, W30) else None), nome
        stickies = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.stickyNote"]
        assert any("—" in n["parameters"]["content"] and ".py:" in n["parameters"]["content"] for n in stickies), nome
        for n in wf["nodes"]:
            if n["type"] == "n8n-nodes-base.httpRequest":
                assert n["typeVersion"] == 4.2
                assert n["parameters"]["options"].get("timeout"), "%s/%s sem timeout explícito" % (nome, n["name"])
                url = n["parameters"]["url"]
                if "FOPA_WORKER_URL" in url:
                    assert n["credentials"]["httpHeaderAuth"]["name"] == "worker", n["name"]
            if n["type"] == "n8n-nodes-base.postgres":
                assert n["typeVersion"] == 2.6 and n["credentials"]["postgres"]["name"] == "fopa-postgres (n8n_rw)"
    # Os ramos pagos existem (construídos), com credencial predefinida / Header Auth, e nunca rodam aqui.
    w23 = {n["name"]: n for n in api.workflow(por_nome[W23]["id"])["nodes"]}
    assert w23["Anthropic /v1/messages"]["parameters"]["nodeCredentialType"] == "anthropicApi"
    assert w23["Anthropic /v1/messages"]["parameters"]["options"]["timeout"] == 600000
    assert "httpHeaderAuth" in w23["OpenAI /v1/responses"]["credentials"]
    # O Jev do W24: credencial própria, uma chamada por vez, falha não derruba a publicação.
    w24 = {n["name"]: n for n in api.workflow(por_nome[W24]["id"])["nodes"]}
    jev = w24["Jev (TypeSafe)"]
    assert jev["credentials"]["httpHeaderAuth"]["name"] == "jev" and jev["onError"] == "continueRegularOutput"
    assert jev["parameters"]["options"]["batching"]["batch"]["batchSize"] == 1
    assert "simulado" in w24["Pedir sinal ao Jev?"]["parameters"]["conditions"]["conditions"][0]["leftValue"]
    # W30 nunca parte sem saber a versão das regras e só republica pelo W24 (nunca troca vigente sozinho).
    w30 = {n["name"]: n for n in api.workflow(por_nome[W30]["id"])["nodes"]}
    assert {"Manual", "Chamado por outro fluxo", "GET /versao", "POST /reverificar", "Republicar (W24)"} <= set(w30)
    assert not any("vigente = true" in json.dumps(n["parameters"]) for n in w30.values())


# ------------------------------------------------------------------ 1. W21 + W22
def test_w21_w22_baixam_e_congelam_licitacao_real(instalado, pg):
    antes = rearmar(pg, ENSAIO)
    assert antes in ("nova", "retificada")
    email_antes = maximo(pg, "emails")

    r21, ret = rodar(W21, controle=ENSAIO)
    assert ret["ok"] is True and ret["continuar"] is True and ret["estado"] == "baixada_ok", ret
    assert lic(pg, ENSAIO)["estado"] == "baixada_ok"
    assert eventos(pg, ENSAIO, r21["id"]) == [(antes, "baixando"), ("baixando", "baixada_ok")]
    assert "Motivo da falha" not in r21["nos"]
    arquivos = pg.execute("SELECT nome, sha256, storage_key, paginas FROM arquivos WHERE controle = %s"
                          " AND status = 'ok'", (ENSAIO,)).fetchall()
    assert arquivos and all(a["storage_key"] and len(a["sha256"].strip()) == 64 for a in arquivos)
    assert ret["arquivos"] == len(arquivos)
    # O produto manda só DOIS e-mails (licitação nova e a extração do botão; db/038-039): baixar não avisa.
    assert pg.execute("SELECT count(*) AS n FROM emails WHERE id > %s AND controle = %s",
                      (email_antes, ENSAIO)).fetchone()["n"] == 0

    r22, ret = rodar(W22, controle=ENSAIO)
    assert ret["ok"] is True and ret["continuar"] is True and ret["estado"] == "preparada", ret
    l = lic(pg, ENSAIO)
    assert l["estado"] == "preparada" and l["leitura_vigente_id"] == ret["leitura_id"]
    assert eventos(pg, ENSAIO, r22["id"]) == [("baixada_ok", "lendo"), ("lendo", "preparada")]
    leitura = pg.execute("SELECT vigente, versao_ocr, (SELECT count(*) FROM paginas p WHERE p.leitura_id = l.id) AS n"
                         " FROM leituras l WHERE id = %s", (ret["leitura_id"],)).fetchone()
    assert leitura["vigente"] is True and leitura["n"] == ret["n_paginas"] > 0
    assert leitura["versao_ocr"].startswith("linux-5.4.0"), leitura["versao_ocr"]


# ------------------------------------------------------------------ 2. W23 simulado
def test_w23_simulado_responde_sem_gastar(instalado, pg, gratis):
    l = lic(pg, ENSAIO)
    if l["estado"] != "preparada":
        pytest.skip("depende do teste do W21/W22 (estado %s)" % l["estado"])
    exec_antes = maximo(pg, "execucoes_modelo")

    r, ret = rodar(W23, controle=ENSAIO)
    assert ret["ok"] is True and ret["estado"] == "respondida", ret
    for no in NOS_PAGOS:
        assert no not in r["nos"], "ramo pago executado: %s" % no
    # 3 lotes; no simulado, o reforço do Best-of-N (v3.1) pode somar rodadas — de graça, e é o que ensaia o laço.
    # O gravado nunca tem reforço (/reforco devolve fim).
    rodadas = r["nos"]["Worker /responder-simulado" if gratis == "simulado" else "Worker /gravado/v1/messages"]["rodadas"]
    assert rodadas >= 3 if gratis == "simulado" else rodadas == 3
    eid = int(ret["execucao_id"])
    assert eid > exec_antes
    e = pg.execute("SELECT * FROM execucoes_modelo WHERE id = %s", (eid,)).fetchone()
    assert (e["origem"], e["provedor"], e["canonica"], e["status"]) == (gratis, gratis, False, "em_curso")
    assert e["leitura_id"] == l["leitura_vigente_id"] and e["controle"] == ENSAIO
    ch = pg.execute("SELECT * FROM chamadas_modelo WHERE execucao_id = %s AND rodada = 0 ORDER BY id",
                    (eid,)).fetchall()
    assert len(ch) == 3                                   # os lotes normais; o reforço é rodada > 0
    assert sorted(i for c in ch for i in c["lote_ids"]) == sorted(IDS)
    assert all(len(c["lote_ids"]) <= 6 for c in ch)
    assert all(c["http_status"] == 200 and c["stop_reason"] == "end_turn" and c["tentativas"] == 1 for c in ch)
    assert all(c["request_sha256"] and len(c["request_sha256"]) == 64 for c in ch)
    # Custo pelo /custo (T17): zero tokens → R$ 0 com preço conhecido do modelo configurado; nunca gasto.
    assert all(c["brl"] is None or c["brl"] == 0 for c in ch)
    assert all(c["preco_conhecido"] is not None for c in ch)
    assert lic(pg, ENSAIO)["estado"] == "respondida"
    assert ("extraindo", "respondida") in eventos(pg, ENSAIO, r["id"])


# ------------------------------------------------------------------ 3. W24
def test_w24_verifica_e_publica_o_ensaio(instalado, pg):
    l = lic(pg, ENSAIO)
    if l["estado"] != "respondida":
        pytest.skip("depende do teste do W23 (estado %s)" % l["estado"])
    email_antes = maximo(pg, "emails")
    # O 2º e-mail do produto (db/038): a extração que nasceu do botão vai para QUEM pediu. O ensaio é
    # simulado; aqui ele faz o papel do pedido já gasto pelo W23 (usado_em + execucao_id), sem gastar nada.
    exec_w23 = pg.execute("SELECT id FROM execucoes_modelo WHERE controle = %s ORDER BY id DESC LIMIT 1",
                          (ENSAIO,)).fetchone()["id"]
    pedido = pg.execute("INSERT INTO pedidos_extracao (controle, provedor, pedido_por, usado_em, execucao_id)"
                        " VALUES (%s, 'openai', 'pedido@teste.br', now(), %s) RETURNING id",
                        (ENSAIO, exec_w23)).fetchone()["id"]
    try:
        r, ret = rodar(W24, controle=ENSAIO)
    finally:
        pg.execute("DELETE FROM pedidos_extracao WHERE id = %s", (pedido,))
    assert ret["ok"] is True and ret["estado"] == "publicada", ret
    vid = int(ret["verificacao_id"])
    v = pg.execute("SELECT * FROM verificacoes WHERE id = %s", (vid,)).fetchone()
    assert v["vigente"] is True and v["controle"] == ENSAIO
    assert pg.execute("SELECT count(*) AS n FROM verificacoes WHERE controle = %s AND vigente",
                      (ENSAIO,)).fetchone()["n"] == 1
    e = pg.execute("SELECT status, origem, brl FROM execucoes_modelo WHERE id = %s", (v["execucao_id"],)).fetchone()
    assert e["status"] == "ok" and e["origem"] in ("simulado", "gravado")        # T15: só vigente porque é ensaio
    pub = pg.execute("SELECT html_uri FROM publicacoes WHERE controle = %s AND verificacao_id = %s",
                     (ENSAIO, vid)).fetchone()
    assert pub["html_uri"] == "html/%s/%d.html" % (l["slug"], vid) == ret["html_uri"]
    assert v["execucao_id"] == exec_w23
    mail = pg.execute("SELECT tipo, status, assunto, para FROM emails WHERE id > %s AND controle = %s",
                      (email_antes, ENSAIO)).fetchall()
    assert [(m["tipo"], m["para"]) for m in mail] == [("extracao", "pedido@teste.br")]
    assert "Processada" in mail[0]["assunto"] and "ENSAIO" in mail[0]["assunto"]
    assert mail[0]["status"] in ("pendente", "falhou")
    pg.execute("DELETE FROM emails WHERE id > %s AND controle = %s", (email_antes, ENSAIO))
    # A regra de revisão (injeção, REPROVADO, REVISAR em crítica) DISPARARIA aqui — mas a execução é simulada:
    # resposta de regex não vai para a fila humana (só ruído). Nenhuma revisão, nenhum sinal do Jev.
    disparariam = pg.execute(
        "SELECT count(*) AS n FROM verificacao_respostas vr JOIN perguntas p ON p.id = vr.pergunta_id"
        " WHERE vr.verificacao_id = %s AND (vr.veredito = 'REPROVADO' OR (vr.veredito = 'REVISAR' AND p.critico))",
        (vid,)).fetchone()["n"]
    assert disparariam > 0, "o teste perdeu o sentido: nenhuma pergunta dispararia revisão"
    assert pg.execute("SELECT count(*) AS n FROM revisoes_humanas WHERE verificacao_id = %s",
                      (vid,)).fetchone()["n"] == 0 and ret["revisoes_abertas"] == 0
    for no in NOS_JEV:
        assert no not in r["nos"], "o Jev foi chamado para resposta simulada: %s" % no
    assert r["nos"]["Pedir sinal ao Jev?"]["itens"] == [0, 1]
    assert pg.execute("SELECT count(*) AS n FROM sinais_jev WHERE verificacao_id = %s", (vid,)).fetchone()["n"] == 0
    assert ret["jev"] is None and ret["modo"] == "publicar" and ret["email_tipo"] == "processada"
    assert lic(pg, ENSAIO)["estado"] == "publicada"
    assert eventos(pg, ENSAIO, r["id"]) == [("respondida", "verificada"), ("verificada", "publicada")]


# ------------------------------------------------------------------ 4. W20 ponta a ponta
def test_w20_ponta_a_ponta_toma_e_devolve_o_lease(instalado, pg, gratis):
    antes = rearmar(pg, ENSAIO)
    vigente_antes = pg.execute("SELECT id FROM verificacoes WHERE controle = %s AND vigente", (ENSAIO,)).fetchone()

    r, ret = rodar(W20, controle=ENSAIO, forcar=False)
    lease = r["saidas"]["Tomar lease"][0][0]
    assert lease["lease_por"] == "W20:%s" % r["id"] and lease["estado"] == antes
    assert ret["ok"] is True and ret["estado_final"] == "publicada", ret
    assert [(p["passo"], p["ok"], p["estado"]) for p in ret["passos"]] == [
        ("W21", True, "baixada_ok"), ("W22", True, "preparada"), ("W23", True, "respondida"), ("W24", True, "publicada")]
    assert ret["lease_devolvido"] is True and ret["custo_brl"] in (None, 0)
    l = lic(pg, ENSAIO)
    assert (l["estado"], l["lease_por"], l["lease_ate"], l["tentativas"], l["proxima_tentativa_em"]) == (
        "publicada", None, None, 0, None)
    w = pg.execute("SELECT * FROM execucoes_workflow WHERE workflow = 'W20' AND n8n_execution_id = %s",
                   (str(r["id"]),)).fetchone()
    assert w["status"] == "ok" and w["controle"] == ENSAIO and w["duracao_s"] > 0
    assert pg.execute("SELECT count(*) AS n FROM execucoes_modelo WHERE workflow_execucao_id = %s",
                      (w["id"],)).fetchone()["n"] == 1
    # A vigência passou da verificação anterior para a nova, sem duas vigentes no meio.
    nova = pg.execute("SELECT id FROM verificacoes WHERE controle = %s AND vigente", (ENSAIO,)).fetchone()
    assert nova["id"] == int(ret["verificacao_id"])
    if vigente_antes:
        assert nova["id"] != vigente_antes["id"]
    # Simulado: nem revisão humana nem Jev.
    assert pg.execute("SELECT count(*) AS n FROM revisoes_humanas WHERE verificacao_id = %s",
                      (nova["id"],)).fetchone()["n"] == 0
    assert pg.execute("SELECT count(*) AS n FROM sinais_jev WHERE verificacao_id = %s",
                      (nova["id"],)).fetchone()["n"] == 0


def test_w20_ramo_de_erro_conta_tentativa_e_devolve_o_lease(instalado, pg, quebrada):
    r, ret = rodar(W20, controle=quebrada, forcar=False)
    lease = r["saidas"]["Tomar lease"][0][0]
    assert lease["lease_por"] == "W20:%s" % r["id"]
    assert ret["ok"] is False and ret["estado_inicial"] == "baixada_ok" and ret["estado_final"] == "erro_leitura", ret
    assert "ObjetoInexistente" in ret["motivo"]
    assert ret["lease_devolvido"] is True and ret["tentativas"] == 1
    l = lic(pg, quebrada)
    assert (l["estado"], l["lease_por"], l["tentativas"]) == ("erro_leitura", None, 1)
    # fn_registrar_falha (db/021): 1ª falha → backoff de 15 min.
    agora = pg.execute("SELECT now() AS t").fetchone()["t"]
    assert dt.timedelta(minutes=14) < l["proxima_tentativa_em"] - agora <= dt.timedelta(minutes=15)
    w = pg.execute("SELECT status, erro FROM execucoes_workflow WHERE workflow = 'W20' AND n8n_execution_id = %s",
                   (str(r["id"]),)).fetchone()
    assert w["status"] == "erro" and "ObjetoInexistente" in w["erro"]
    assert [p["passo"] for p in ret["passos"]] == ["W22"]


def test_w20_nao_toma_lease_de_outro_w20(instalado, pg, quebrada):
    pg.execute("UPDATE licitacoes SET lease_por = 'W20:999999', lease_ate = now() + interval '1 hour'"
               " WHERE controle = %s", (quebrada,))
    antes = lic(pg, quebrada)
    r, ret = rodar(W20, controle=quebrada, forcar=False)
    assert ret["ok"] is False and "lease ocupado por W20:999999" in ret["motivo"], ret
    depois = lic(pg, quebrada)
    assert (depois["estado"], depois["lease_por"], depois["tentativas"]) == (
        antes["estado"], "W20:999999", antes["tentativas"])
    assert "Executar W22 Ler" not in r["nos"]


def test_w20_reservada_para_demo_so_com_forcar(instalado, pg, quebrada):
    pg.execute("UPDATE licitacoes SET reserva_demo = true WHERE controle = %s", (quebrada,))
    r, ret = rodar(W20, controle=quebrada, forcar=False)
    assert ret["ok"] is False and "reservada para demo" in ret["motivo"] and ret["lease_devolvido"] is True, ret
    l = lic(pg, quebrada)
    assert (l["estado"], l["lease_por"], l["tentativas"]) == ("baixada_ok", None, 0)
    w = pg.execute("SELECT status FROM execucoes_workflow WHERE workflow = 'W20' AND n8n_execution_id = %s",
                   (str(r["id"]),)).fetchone()
    assert w["status"] == "recusado"            # fora do disjuntor do W10 (conta só 'erro')
    assert not any(n.startswith("Executar") for n in r["nos"])


# ------------------------------------------------------------------ 5. guarda da fila
def _alvo(pg, where: str):
    linha = pg.execute("SELECT controle, estado::text AS estado FROM licitacoes WHERE %s"
                       " ORDER BY controle LIMIT 1" % where).fetchone()
    if not linha:
        pytest.skip("o acervo não tem licitação para: %s" % where)
    return linha["controle"]


@pytest.mark.parametrize("onde,trecho", [
    ("estado = 'preparada' AND escopo_dentro AND NOT fn_no_recorte(fim_prazo, publicado_em)", "recorte"),
    ("NOT escopo_dentro AND fn_no_recorte(fim_prazo, publicado_em)", "escopo"),
])
def test_w23_guarda_recusa_sem_chamar_provedor(instalado, pg, gratis, onde, trecho):
    controle = _alvo(pg, onde)
    antes = lic(pg, controle)
    execs = pg.execute("SELECT count(*) AS n FROM execucoes_modelo WHERE controle = %s", (controle,)).fetchone()["n"]
    ch_antes = maximo(pg, "chamadas_modelo")
    ev_antes = pg.execute("SELECT count(*) AS n FROM licitacao_eventos WHERE controle = %s",
                          (controle,)).fetchone()["n"]

    r, ret = rodar(W23, controle=controle)
    assert ret["ok"] is False and ret.get("recusada") is True and trecho in ret["motivo"], ret
    for no in NOS_PAGOS + ("POST /prompt", "Abrir execução", "Worker /responder-simulado",
                           "Worker /gravado/v1/messages"):
        assert no not in r["nos"], "a guarda deixou passar até %s" % no
    depois = lic(pg, controle)
    assert (depois["estado"], depois["tentativas"], depois["lease_por"]) == (
        antes["estado"], antes["tentativas"], antes["lease_por"])
    assert pg.execute("SELECT count(*) AS n FROM execucoes_modelo WHERE controle = %s",
                      (controle,)).fetchone()["n"] == execs
    assert maximo(pg, "chamadas_modelo") == ch_antes
    assert pg.execute("SELECT count(*) AS n FROM licitacao_eventos WHERE controle = %s",
                      (controle,)).fetchone()["n"] == ev_antes


# ------------------------------------------------------------------ retomada da parcial
def test_w23_retoma_a_parcial_so_com_os_ids_pendentes(instalado, pg, parcial):
    r, ret = rodar(W23, controle=parcial["controle"])
    assert ret["ok"] is True and ret["estado"] == "respondida", ret
    assert ret["reaproveitada"] is True and int(ret["execucao_id"]) == parcial["execucao_id"]
    novas = pg.execute("SELECT lote_ids, http_status FROM chamadas_modelo WHERE execucao_id = %s ORDER BY id",
                       (parcial["execucao_id"],)).fetchall()[2:]
    assert sorted(i for c in novas for i in c["lote_ids"]) == sorted(IDS[6:])       # só Q7..Q17
    assert all(c["http_status"] == 200 for c in novas)
    for no in NOS_PAGOS:
        assert no not in r["nos"]
    e = pg.execute("SELECT status, erro FROM execucoes_modelo WHERE id = %s", (parcial["execucao_id"],)).fetchone()
    assert (e["status"], e["erro"]) == ("em_curso", None)
    assert pg.execute("SELECT count(*) AS n FROM execucoes_modelo WHERE controle = %s",
                      (parcial["controle"],)).fetchone()["n"] == 1
    assert lic(pg, parcial["controle"])["estado"] == "respondida"


# ------------------------------------------------------------------ W30 + W24 republicar
def _vigente(pg, controle: str):
    return pg.execute("SELECT id, versao_regras FROM verificacoes WHERE controle = %s AND vigente", (controle,)).fetchone()


def test_w30_reverifica_so_os_controles_pedidos_e_republica(instalado, pg, republicavel):
    ensaio_antes = _vigente(pg, ENSAIO)
    email_antes = maximo(pg, "emails")

    r, ret = rodar(W30, controles=[REPUB, ENSAIO])
    vr = ret["versao_regras"]
    assert ret["ok"] is True and ret["vigentes"] == (2 if ensaio_antes else 1), ret
    assert ret["a_reverificar"] == 1 and ret["republicadas"] == 1 and ret["falhas"] == 0
    assert ret["ja_na_versao"] == (1 if ensaio_antes and ensaio_antes["versao_regras"] == vr else 0)
    (res,) = ret["resultados"]
    assert res["controle"] == REPUB and res["ok"] is True and res["antes"] == republicavel["v1"]
    v2 = res["depois"]
    assert v2 and v2 != republicavel["v1"]
    # O diff é o de uma reverificação: o veredito envelhecido volta ao que as regras atuais dão; o alerta sai.
    assert res["mudaram"] == ["Q2"]
    assert res["diff"]["vereditos"] == {"Q2": [republicavel["velho"], republicavel["atual"]]}
    assert "teste: alerta que sai" in res["diff"]["alertas_sairam"]

    vig = _vigente(pg, REPUB)
    assert vig["id"] == v2 and vig["versao_regras"] == vr
    assert pg.execute("SELECT vigente FROM verificacoes WHERE id = %s", (republicavel["v1"],)).fetchone()["vigente"] is False
    assert pg.execute("SELECT count(*) AS n FROM verificacoes WHERE controle = %s", (REPUB,)).fetchone()["n"] == 2
    assert pg.execute("SELECT html_uri FROM publicacoes WHERE controle = %s AND verificacao_id = %s",
                      (REPUB, v2)).fetchone()["html_uri"].endswith("/%d.html" % v2)
    assert lic(pg, REPUB)["estado"] == "publicada"
    ultimos = [(e["de"], e["para"]) for e in pg.execute(
        "SELECT de::text, para::text FROM licitacao_eventos WHERE controle = %s ORDER BY id DESC LIMIT 2",
        (REPUB,)).fetchall()][::-1]
    assert ultimos == [("publicada", "verificada"), ("verificada", "publicada")]
    # ENSAIO já estava nas regras atuais: não foi tocada.
    assert _vigente(pg, ENSAIO) == ensaio_antes
    # E-mails: nenhum. O produto manda só DOIS (licitação nova e a extração do botão; db/038-039): nem o
    # 'republicada' por licitação nem o resumo da rodada.
    assert pg.execute("SELECT count(*) AS n FROM emails WHERE id > %s AND (controle IS NULL OR controle = ANY(%s))",
                      (email_antes, [REPUB, ENSAIO])).fetchone()["n"] == 0
    assert ret["email_id"] is None
    w = pg.execute("SELECT status, custo_brl, contadores FROM execucoes_workflow WHERE workflow = 'W30'"
                   " AND n8n_execution_id = %s", (str(r["id"]),)).fetchone()
    assert w["status"] == "ok" and w["custo_brl"] == 0 and w["contadores"]["republicadas"] == 1
    # Simulado na licitação de ensaio: nem revisão humana nem Jev na republicação.
    assert pg.execute("SELECT count(*) AS n FROM revisoes_humanas WHERE verificacao_id = %s", (v2,)).fetchone()["n"] == 0
    assert pg.execute("SELECT count(*) AS n FROM sinais_jev WHERE controle = %s", (REPUB,)).fetchone()["n"] == 0


def test_w30_retoma_a_verificacao_ja_gravada(instalado, pg, republicavel):
    _, ret1 = rodar(W30, controles=[REPUB])
    v2 = ret1["resultados"][0]["depois"]
    # Como se o W24 tivesse morrido antes de trocar a vigente: a nova existe, a velha ainda vale.
    pg.execute("UPDATE verificacoes SET vigente = false WHERE id = %s", (v2,))
    pg.execute("UPDATE verificacoes SET vigente = true WHERE id = %s", (republicavel["v1"],))

    r, ret = rodar(W30, controles=[REPUB])
    assert r["nos"]["Reverificou?"]["itens"] == [0, 1, 0]           # 409: já verificada nesta versão
    assert "Verificação já gravada" in r["nos"]
    assert ret["republicadas"] == 1 and ret["resultados"][0]["depois"] == v2
    assert _vigente(pg, REPUB)["id"] == v2
    assert pg.execute("SELECT count(*) AS n FROM verificacoes WHERE controle = %s", (REPUB,)).fetchone()["n"] == 2


def test_executar_com_itens_parte_do_gatilho_de_sub_fluxo():
    # A causa da execução 436: com itens, o Manual do W30 foi escolhido e os itens se perderam.
    wf = json.loads(json_do_fluxo("W30").read_text(encoding="utf-8"))
    assert executar.achar_gatilho(wf, com_itens=True)["name"] == "Chamado por outro fluxo"
    assert executar.achar_gatilho(wf)["name"] == "Manual"


def test_w30_chamado_sem_controles_nem_todos_nao_reverifica_nada(instalado, pg):
    r, ret = rodar(W30)                                              # nem controles nem todos
    assert ret["ok"] is True and ret["vigentes"] == 0 and ret["a_reverificar"] == 0 and ret["reverificadas"] == 0
    assert "POST /reverificar" not in r["nos"]
    par = r["saidas"]["Parâmetros"][0][0]
    assert par["controles"] == [] and par["todos"] is False


def test_w30_sem_alvo_so_resume(instalado, pg):
    r, ret = rodar(W30, controles=[ENSAIO])
    assert ret["ok"] is True and ret["reverificadas"] == 0 and ret["a_reverificar"] == 0
    assert "POST /reverificar" not in r["nos"] and "Loop vigentes" not in r["nos"]
    assert ret["email_id"] is None          # o resumo por e-mail saiu do produto (db/038-039)


def test_w24_republicar_recusa_verificacao_de_outra_licitacao(instalado, pg, republicavel):
    alheia = _vigente(pg, ENSAIO)
    if not alheia:
        pytest.skip("a licitação de ensaio não tem vigente")
    antes = _vigente(pg, REPUB)
    r, ret = rodar(W24, controle=REPUB, verificacao_id=alheia["id"], modo="republicar")
    assert ret["ok"] is False and "não é desta licitação" in ret["motivo"], ret
    assert _vigente(pg, REPUB) == antes and _vigente(pg, ENSAIO) == alheia
    assert "Tornar vigente" not in r["nos"] and "POST /render" not in r["nos"]


# ------------------------------------------------------------------ links do site nos e-mails
def _rodar_code_node(codigo: str, nos: dict, env: dict, entrada: dict | None = None) -> list:
    """O jsCode versionado rodando no Node do próprio fopa-n8n, com $input, $('Nó'), $env, $workflow e $execution
    de mentira (mesmo molde do test_n8n.py): prova o código sem precisar recriar o container para mudar a env."""
    if not shutil.which("docker"):
        pytest.skip("docker ausente: não há Node para rodar o Code node")
    harness = (
        "let s='';process.stdin.on('data',c=>s+=c).on('end',()=>{const c=JSON.parse(s);"
        "const $=(n)=>{if(!(n in c.nos))throw new Error('nó desconhecido: '+n);"
        "return {first:()=>({json:c.nos[n]}),item:{json:c.nos[n]},isExecuted:true};};"
        "const $input={first:()=>({json:c.entrada}),all:()=>[{json:c.entrada}]};"
        "const f=new Function('$','$input','$json','$env','$workflow','$execution',c.codigo);"
        "const r=f($,$input,c.entrada,c.env,{id:'wfTESTE'},{id:'4242',mode:'manual'});"
        "process.stdout.write(JSON.stringify(r));});")
    corpo = json.dumps({"codigo": codigo, "nos": nos, "env": env, "entrada": entrada or {}})
    r = subprocess.run(["docker", "exec", "-i", "fopa-n8n", "node", "-e", harness], input=corpo.encode("utf-8"),
                       capture_output=True, timeout=60)
    assert r.returncode == 0, "Code node falhou: %s" % r.stderr.decode("utf-8", "replace")[-800:]
    return json.loads(r.stdout.decode("utf-8"))


def _codigo(codigo_wf: str, no: str) -> str:
    wf = json.loads(json_do_fluxo(codigo_wf).read_text(encoding="utf-8"))
    return next(n for n in wf["nodes"] if n["name"] == no)["parameters"]["jsCode"]


LIC = {"controle": "00000000000000-1-000001/2026", "slug": "00000000000000-1-000001-2026", "orgao": "Órgão <b>",
       "uf": "SC", "municipio": "Teste", "modalidade": "Dispensa", "objeto": "folha", "fim_prazo": None,
       "fim_prazo_tem_hora": None, "link": None, "cnpj": "00000000000000", "ano": 2026, "seq": 1}
VERIF = dict(LIC, verificacao_id=7, aprovadas=1, revisar=0, reprovadas=0, nao_localizado=16, ancoradas=1,
             respondidas=1, alertas_globais=[], tags=[], versao_regras="abc123", origem="api", provedor="claude",
             modelo="claude-opus-5", brl=None, preco_conhecido=False, revisoes_abertas=0,
             respostas=[{"id": "Q2", "texto": "Objeto?", "critico": False, "veredito": "APROVADO", "pagina": 3,
                         "arquivo": "edital.pdf", "arquivo_id": 99, "resposta": "folha", "alertas": []}])
CASOS_EMAIL = [
    ("W21", "Montar e-mail carregada", {
        "Transição → baixando": LIC,
        "Estado pelo resultado": {"n_arquivos": 1, "n_paginas": 2, "n_ocr": 0, "recusados": [], "falhas_download": [],
                                  "arquivos": [{"nome": "edital.pdf", "pag": 2, "requer_ocr": False}]}}, None),
    ("W22", "Montar aviso furtivo", {
        "Transição → lendo": LIC, "Leitura": {"leitura_id": 1, "furtivos": ["texto branco"]}}, None),
    ("W23", "Montar aviso de orçamento", {"Parâmetros da extração": {"controle": LIC["controle"], "teto_brl_dia": 25}},
     None),
    ("W24", "Montar e-mail", {"Contexto da licitação": {"modo": "publicar"}}, VERIF),
    ("W24", "Montar e-mail", {"Contexto da licitação": {"modo": "republicar"},
                              "Diff contra a vigente": {"antes_id": 6, "depois_id": 7, "versao_regras": "abc123",
                                                        "versao_regras_antes": "legado:x",
                                                        "vereditos": {"Q2": ["REVISAR", "APROVADO"]},
                                                        "alertas_entraram": [], "alertas_sairam": ["velho"]}}, VERIF),
    ("W30", "Montar e-mail de resumo", {"Resumo da rodada": {
        "versao_regras": "abc123", "contadores": {"vigentes": 1, "a_reverificar": 1, "ja_na_versao": 0,
                                                  "pendentes_de_leitura": 0, "reverificadas": 1, "republicadas": 1,
                                                  "com_veredito_mudado": 1, "vereditos_mudados": 1, "puladas": 0,
                                                  "falhas": 0},
        "resultados": [{"controle": LIC["controle"], "ok": True, "antes": 6, "depois": 7, "mudaram": ["Q2"],
                        "motivo": "ok"}]}}, None),
]


def test_w22_espera_a_leitura_longa_ate_40_min():
    # 26/09: Lapa/PR (544 páginas com OCR) terminou em 776 s e Massaranduba/SC em 881 s, mas o W22 desistia em 675 s
    # (45 voltas de 15 s) e marcava erro_leitura com o texto pronto — e desde o ADR-018 a folha pega todos os arquivos.
    import re
    w22 = json.loads(json_do_fluxo("W22").read_text(encoding="utf-8"))
    js = next(n["parameters"]["jsCode"] for n in w22["nodes"] if n["name"] == "Status do job")
    espera = next(n["parameters"]["amount"] for n in w22["nodes"] if n["type"] == "n8n-nodes-base.wait")
    voltas = int(re.search(r"const MAX = (\d+);", js).group(1))
    assert voltas * espera >= 40 * 60


def test_compose_da_ao_n8n_a_url_publica_do_site():
    texto = (RAIZ / "docker" / "compose.yml").read_text(encoding="utf-8")
    bloco = texto.split("  fopa-n8n:", 1)[1].split("\n  fopa-", 1)[0]
    assert "FOPA_SITE_PUBLIC_URL: ${FOPA_SITE_URL:-http://localhost:8080}" in bloco
    assert "FOPA_SITE_URL: http://fopa-api:8080" in bloco          # a interna continua (W24 avisa o site por ela)


@pytest.mark.parametrize("codigo_wf,no,nos,entrada", CASOS_EMAIL,
                         ids=["W21-carregada", "W22-furtivo", "W23-orcamento", "W24-processada", "W24-republicada",
                              "W30-resumo"])
def test_emails_linkam_o_site_publico(codigo_wf, no, nos, entrada):
    codigo = _codigo(codigo_wf, no)
    env = {"FOPA_SITE_PUBLIC_URL": "https://fopa.exemplo/", "FOPA_SITE_URL": "http://fopa-api:8080",
           "WEBHOOK_URL": "http://n8n.exemplo:5679/"}
    (item,) = _rodar_code_node(codigo, nos, env, entrada)
    corpo = item["json"]["corpo_html"]
    assert 'href="https://fopa.exemplo/' in corpo, corpo[:400]
    assert "fopa-api" not in corpo and "https://fopa.exemplo//" not in corpo
    assert "http://n8n.exemplo:5679/workflow/wfTESTE/executions/4242" in corpo
    assert "<b>" not in item["json"]["assunto"]
    # Sem a variável (container ainda não recriado): link relativo, que funciona na página /emails do site.
    (sem,) = _rodar_code_node(codigo, nos, {"WEBHOOK_URL": "http://n8n.exemplo:5679"}, entrada)
    assert 'href="/' in sem["json"]["corpo_html"] and "localhost" not in sem["json"]["corpo_html"]


# ------------------------------------------------------------------ Jev de verdade (opt-in, centavos)
@pytest.mark.skipif(os.environ.get("FOPA_TESTE_JEV_REAL") != "1",
                    reason="chama o Jev pago (~US$ 0,0001 por resposta aprovada): FOPA_TESTE_JEV_REAL=1")
def test_w24_pede_o_sinal_do_jev_para_resposta_de_agente(instalado, pg, agente_respondida):
    r, ret = rodar(W24, controle=JEVTESTE)
    assert ret["ok"] is True and ret["estado"] == "publicada", ret
    vid = int(ret["verificacao_id"])
    aprovadas = [x["pergunta_id"] for x in pg.execute(
        "SELECT vr.pergunta_id FROM verificacao_respostas vr JOIN respostas rs ON rs.execucao_id = %s"
        " AND rs.pergunta_id = vr.pergunta_id WHERE vr.verificacao_id = %s AND vr.veredito = 'APROVADO'"
        " AND vr.ausencia IS NULL AND coalesce(rs.trecho_literal, '') <> '' ORDER BY 1",
        (agente_respondida["execucao_id"], vid)).fetchall()]
    assert aprovadas, "nenhuma resposta aprovada: o Jev não teria o que julgar"
    assert r["nos"]["Jev (TypeSafe)"]["rodadas"] == 1
    sinais = pg.execute("SELECT pergunta_id, resposta, p_sim, usd, candidata FROM sinais_jev"
                        " WHERE verificacao_id = %s AND tipo = 'sustenta' ORDER BY pergunta_id", (vid,)).fetchall()
    assert [s["pergunta_id"] for s in sinais] == aprovadas
    assert all(s["resposta"] in ("sustenta", "contradiz", "nada_diz") for s in sinais), sinais
    custo = sum(float(s["usd"] or 0) for s in sinais)
    print("\nJev: %d chamada(s), US$ %.6f, respostas %s" % (len(sinais), custo, [s["resposta"] for s in sinais]))
    assert ret["jev"]["sinais"] == len(sinais)
    # T25: o sinal nunca muda o veredito.
    assert all(x["veredito"] == "APROVADO" for x in pg.execute(
        "SELECT veredito FROM verificacao_respostas WHERE verificacao_id = %s AND pergunta_id = ANY(%s)",
        (vid, aprovadas)).fetchall())


# ------------------------------------------------------------------ W20 em PRODUÇÃO com token do worker inválido
# Checklist F4 "Token inválido via webhook → W90 grava e-mail de erro e o estado fica coerente" e plano §11.5.
#
# Execução manual não dispara o Error Trigger (limitação do n8n), então aqui o W20 roda em PRODUÇÃO: um fluxo
# chamador de TESTE com Webhook (o papel do W11/W10: raiz, dispara o W20 sem esperar) chama uma CÓPIA de teste do
# W20 cujo Error Workflow é o W90 DE VERDADE; a cópia do W20 chama uma CÓPIA do W22 (folha, sem Error Workflow, como
# a real) que fala com o worker por uma credencial TEMPORÁRIA com Bearer errado. Nada real é editado: nem a
# credencial 'worker', nem os fluxos W20/W22/W90. O worker recusa o Bearer (403) antes de qualquer trabalho.
#
# Por que o W22 e não o W21: com CNPJ zerado o W21 cai no 400 do PNCP antes de chegar ao worker; `baixada_ok` vai
# direto ao W22, cuja 1ª chamada é ao worker (POST /jobs/paginas). Sem PNCP, sem storage, sem modelo.
#
# Os nomes das cópias NÃO começam por Wnn: o importar/exportar os ignoram, e o W90 grava o nome inteiro em
# execucoes_workflow.workflow — então a linha de erro da cópia nunca entra no disjuntor do W10 (que conta 'W20') e a
# regra anti-tempestade (mesmo fluxo + mensagem em 1 h) não a confunde com erro real: cada rodada tem nome único.
TOKEN_INVALIDO = "00000000000000-1-000940/2026"      # test_nucleo: 92x; test_w01: 93x; test_w10_w11: 95x-99x
TERMINAIS = {"success", "error", "crashed", "canceled"}


class _Oculto(str):
    """O Bearer errado da credencial temporária: não é segredo, mas segue a regra — nunca em repr/print."""

    def __repr__(self):
        return "<token oculto>"

    __str__ = __repr__

    def valor(self) -> str:
        return str.__str__(self)


def _foto_reais(pg) -> dict:
    """Licitações REAIS (NOT ensaio): contagem por estado + md5 de estado/prioridade/lease/tentativas/reserva."""
    por_estado = {r["estado"]: r["n"] for r in pg.execute(
        "SELECT estado::text AS estado, count(*) AS n FROM licitacoes WHERE NOT ensaio GROUP BY 1").fetchall()}
    md5 = pg.execute(
        "SELECT md5(string_agg(concat_ws('|', controle, estado::text, prioridade, lease_por, lease_ate, tentativas,"
        " proxima_tentativa_em, reserva_demo), ',' ORDER BY controle)) AS m FROM licitacoes WHERE NOT ensaio"
    ).fetchone()["m"]
    return {"por_estado": por_estado, "md5": md5}


def _ultimo_id_n8n(api) -> int:
    d = api.publica("GET", "/executions?limit=1").get("data") or []
    return int(d[0]["id"]) if d else 0


def _execucoes(api, wid: str, depois_de: int) -> list:
    d = api.publica("GET", "/executions?workflowId=%s&limit=50" % wid).get("data") or []
    return sorted(({"id": str(e["id"]), "status": e["status"], "mode": e["mode"]} for e in d
                   if int(e["id"]) > depois_de), key=lambda e: int(e["id"]))


def _terminadas(api, wid: str, depois_de: int):
    x = _execucoes(api, wid, depois_de)
    return x if x and all(e["status"] in TERMINAIS for e in x) else None


def _esperar(cond, timeout: float, oque: str, passo: float = 2.0):
    limite = time.monotonic() + timeout
    while True:
        v = cond()
        if v:
            return v
        if time.monotonic() > limite:
            raise AssertionError("não aconteceu em %d s: %s" % (timeout, oque))
        time.sleep(passo)


def _chamador(nome: str, caminho: str, w20_id: str, controle: str, w90_id: str) -> dict:
    """Raiz de TESTE no papel do W11/W10: Webhook → Execute W20 SEM ESPERAR, com Error Workflow = W90 como as raízes
    reais. Sem esperar, a morte do W20 não sobe para o chamador (que já terminou): se subisse, seriam 2 e-mails."""
    return {
        "name": nome,
        "nodes": [
            {"parameters": {"httpMethod": "POST", "path": caminho, "responseMode": "onReceived", "options": {}},
             "id": str(uuid.uuid4()), "name": "POST teste", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
             "position": [0, 0], "webhookId": str(uuid.uuid4())},
            # O controle é FIXO no fluxo (não vem do corpo): o webhook aberto por segundos não processa outra coisa.
            {"parameters": {
                "workflowId": {"__rl": True, "value": w20_id, "mode": "id"},
                "workflowInputs": {"mappingMode": "defineBelow", "value": {"controle": controle, "forcar": False},
                                   "matchingColumns": [],
                                   "schema": [{"id": k, "displayName": k, "required": False, "defaultMatch": False,
                                               "display": True, "canBeUsedToMatch": True, "type": t}
                                              for k, t in (("controle", "string"), ("forcar", "boolean"))],
                                   "attemptToConvertTypes": False, "convertFieldsToString": False},
                "mode": "once", "options": {"waitForSubWorkflow": False}},
             "id": str(uuid.uuid4()), "name": "W20 (sem esperar)", "type": "n8n-nodes-base.executeWorkflow",
             "typeVersion": 1.2, "position": [300, 0]},
        ],
        "connections": {"POST teste": {"main": [[{"node": "W20 (sem esperar)", "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1", "timezone": "America/Sao_Paulo", "errorWorkflow": w90_id},
    }


@contextmanager
def _producao_com_token_invalido(pg, morre: bool):
    """Credencial temporária com Bearer errado + cópias do W22 e do W20 + chamador com Webhook, todos publicados; a
    licitação de teste em `baixada_ok`. `morre`: a cópia do W22 NÃO trata o erro HTTP (o nó lança, como lançaria
    qualquer falha não prevista numa folha); sem `morre`, é o tratamento versionado (saída de erro → erro_leitura)."""
    api = cliente.N8n.autenticado()
    tag = uuid.uuid4().hex[:8]
    nomes = {"cred": "TESTE worker com token inválido %s (apagar)" % tag,
             "w22": "TESTE W22 token inválido %s (apagar)" % tag,
             "w20": "TESTE W20 token inválido %s (apagar)" % tag,
             "chamador": "TESTE chamador do W20 %s (apagar)" % tag}
    caminho = "teste-w90-token-%s" % tag
    criados, cred = [], None
    _limpar(pg, TOKEN_INVALIDO)
    try:
        cred = api.publica("POST", "/credentials", {"name": nomes["cred"], "type": "httpHeaderAuth", "data": {
            "name": "Authorization", "value": "Bearer " + _Oculto("teste-errado-" + secrets.token_hex(16)).valor()}})
        ids_wf = {importar.codigo(w["name"]): w["id"] for w in api.listar_workflows() if importar.codigo(w["name"])}
        ids_cred = {c["name"]: c["id"] for c in api.listar_credenciais()}

        w22 = json.loads(json_do_fluxo("W22").read_text(encoding="utf-8"))
        assert "errorWorkflow" not in w22["settings"], "folha sem Error Workflow (plano §5 W90)"
        trocadas = 0
        for n in w22["nodes"]:
            ref = (n.get("credentials") or {}).get("httpHeaderAuth")
            if ref and ref["name"] == "worker":
                n["credentials"]["httpHeaderAuth"] = {"id": cred["id"], "name": nomes["cred"]}
                trocadas += 1
        assert trocadas == 4, "o W22 fala com o worker em POST /jobs/paginas, GET /jobs/{id} e nas duas pontas do Jev com o edital (db/035)"
        if morre:
            no = next(n for n in w22["nodes"] if n["name"] == "POST /jobs/paginas")
            assert no.pop("onError") == "continueErrorOutput"
            no["parameters"]["options"]["response"]["response"]["neverError"] = False
            saidas = w22["connections"]["POST /jobs/paginas"]["main"]
            w22["connections"]["POST /jobs/paginas"]["main"] = saidas[:1]
        w22 = importar.resolver(w22, ids_wf, ids_cred, [])
        w22["name"] = nomes["w22"]
        c22 = api.publica("POST", "/workflows", importar.corpo(w22))
        criados.append(c22["id"])
        importar.publicar(api, c22["id"])      # o W20 publicado só chama sub-fluxo publicado (n8n 2.x)

        bruto = json.dumps(json.loads(json_do_fluxo("W20").read_text(encoding="utf-8")), ensure_ascii=False)
        assert bruto.count("{{WF:W22}}") == 1
        w20 = importar.resolver(json.loads(bruto.replace("{{WF:W22}}", c22["id"])), ids_wf, ids_cred, [])
        w20["name"] = nomes["w20"]
        assert w20["settings"]["errorWorkflow"] == ids_wf["W90"], "a cópia do W20 alarma o W90 de verdade"
        c20 = api.publica("POST", "/workflows", importar.corpo(w20))
        criados.append(c20["id"])
        importar.publicar(api, c20["id"])

        cc = api.publica("POST", "/workflows", _chamador(nomes["chamador"], caminho, c20["id"], TOKEN_INVALIDO,
                                                         ids_wf["W90"]))
        criados.append(cc["id"])
        importar.publicar(api, cc["id"])

        _nascer(pg, TOKEN_INVALIDO, "baixada_ok", "folha de pagamento — TESTE: token do worker inválido (W90)")
        yield {"api": api, "tag": tag, "nomes": nomes, "caminho": caminho, "w22": c22["id"], "w20": c20["id"],
               "chamador": cc["id"], "w90": ids_wf["W90"]}
    finally:
        for wid in reversed(criados):          # as execuções das cópias vão junto com elas
            try:
                api.publica("DELETE", "/workflows/" + wid)
            except cliente.ErroN8n as e:
                print("\n[token inválido] não apaguei o fluxo %s: %s" % (wid, e))
        if cred:
            api.publica("DELETE", "/credentials/" + cred["id"])
        pg.execute("DELETE FROM emails WHERE tipo = 'erro' AND assunto LIKE %s", ("%" + tag + "%",))
        pg.execute("DELETE FROM execucoes_workflow WHERE workflow LIKE %s", ("%" + tag + "%",))
        _limpar(pg, TOKEN_INVALIDO)


def _disparar(caminho: str) -> int:
    req = urllib.request.Request("%s/webhook/%s" % (cliente.base(), caminho), data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def _backoff_de_15_min(pg, l) -> bool:
    agora = pg.execute("SELECT now() AS t").fetchone()["t"]
    return dt.timedelta(minutes=13) < l["proxima_tentativa_em"] - agora <= dt.timedelta(minutes=15)


def test_w20_em_producao_folha_que_morre_chama_o_w90_uma_vez(instalado, pg):
    """A folha (W22) MORRE no meio de um W20 de produção: o erro sobe para o W20, que é raiz → o W90 dispara UMA vez,
    com o id da execução do W20 (o `lease_por = 'W20:'||id` casa), devolve o lease e aplica o estado de erro com o
    backoff do W10. UM W90, não 2-3: prova que o Error Workflow está só nas raízes (plano §5 W90). E-mail de erro
    não sai mais (o produto manda só dois; db/038-039)."""
    foto = _foto_reais(pg)
    with _producao_com_token_invalido(pg, morre=True) as p:
        api = p["api"]
        antes = _ultimo_id_n8n(api)
        t = pg.execute("SELECT now() AS t").fetchone()["t"]

        assert _disparar(p["caminho"]) == 200

        (e20,) = _esperar(lambda: _terminadas(api, p["w20"], antes), 120, "a cópia do W20 terminar")
        (e22,) = _terminadas(api, p["w22"], antes)
        (ech,) = _terminadas(api, p["chamador"], antes)

        def linhas_da_execucao():
            return pg.execute("SELECT * FROM execucoes_workflow WHERE n8n_execution_id = %s ORDER BY id",
                              (str(e20["id"]),)).fetchall()
        _esperar(lambda: [x for x in linhas_da_execucao() if x["status"] == "erro"], 60,
                 "o W90 fechar como erro a linha do W20")
        _esperar(lambda: _terminadas(api, p["w90"], antes), 60, "o W90 terminar")
        time.sleep(8)          # tempo para uma cascata (W90 da folha, do chamador) aparecer, se existisse
        w90 = _execucoes(api, p["w90"], antes)
        (linha,) = linhas_da_execucao()
        emails = pg.execute("SELECT * FROM emails WHERE controle = %s AND em >= %s ORDER BY id",
                            (TOKEN_INVALIDO, t)).fetchall()
        l = lic(pg, TOKEN_INVALIDO)
        ev = pg.execute("SELECT de::text, para::text, motivo, n8n_execution_id FROM licitacao_eventos"
                        " WHERE controle = %s ORDER BY id", (TOKEN_INVALIDO,)).fetchall()
        propria = pg.execute("SELECT status, erro FROM execucoes_workflow WHERE workflow = 'W20'"
                             " AND n8n_execution_id = %s", (e20["id"],)).fetchone()
        print("\n[W90 uma vez] chamador %s (%s) -> W20 %s (%s, %s) -> W22 %s (%s) · W90 %s · linha %s · e-mail %s"
              % (ech["id"], ech["mode"], e20["id"], e20["mode"], e20["status"], e22["id"], e22["status"],
                 [(x["id"], x["status"]) for x in w90], linha["id"], [(m["id"], m["assunto"]) for m in emails]))
        print("[W90 uma vez] erro: %s · licitação %s tent. %s próxima %s lease %s · linha do W20: %s"
              % (linha["erro"], l["estado"], l["tentativas"], l["proxima_tentativa_em"], l["lease_por"], propria))

        # Produção de verdade: o chamador veio do webhook; o W20 e o W22 morreram (a folha lançou, o W20 herdou).
        assert (ech["mode"], ech["status"]) == ("webhook", "success")
        assert e20["status"] == "error" and e22["status"] == "error"
        # UM W90 e UMA linha de erro na janela — com o id da execução do W20, não o da folha.
        assert len(w90) == 1 and w90[0]["status"] == "success", w90
        # A linha é a que o próprio W20 abriu no "Tomar lease" (workflow 'W20'), FECHADA pelo W90 — não uma
        # segunda linha: antes ela ficava 'em_curso' para sempre e o site mostrava a execução "em curso".
        assert (linha["workflow"], linha["n8n_execution_id"], linha["status"]) == ("W20", e20["id"], "erro")
        assert linha["gatilho"] != "erro" and linha["duracao_s"] is not None and linha["erro"]
        assert not pg.execute("SELECT 1 FROM execucoes_workflow WHERE workflow LIKE %s",
                              ("%" + p["tag"] + "%",)).fetchall(), "o W90 inseriu uma segunda linha"
        assert linha["controle"] == TOKEN_INVALIDO and linha["argumentos"]["ultimo_no"] == "Executar W22 Ler"
        # E-mail de erro saiu do produto (db/038-039): o erro fica na linha acima e no site.
        assert emails == [], "e-mail de erro: %s" % [m["assunto"] for m in emails]
        # Estado coerente: lease devolvido, lendo → erro_leitura pelo W90 (fn_transicao), 1ª tentativa, backoff 15 min.
        assert (l["estado"], l["lease_por"], l["lease_ate"], l["tentativas"]) == ("erro_leitura", None, None, 1)
        assert _backoff_de_15_min(pg, l)
        assert [(x["de"], x["para"]) for x in ev] == [("baixada_ok", "lendo"), ("lendo", "erro_leitura")]
        assert ev[0]["n8n_execution_id"] == e22["id"]
        assert ev[1]["n8n_execution_id"] == e20["id"] and ev[1]["motivo"].startswith("W90: ")
    assert _foto_reais(pg) == foto, "licitação REAL mudou durante o teste"


def test_w20_em_producao_token_invalido_tratado_na_folha_nao_chama_o_w90(instalado, pg):
    """O que acontece HOJE com o token errado: o W22 versionado trata o 403 pela saída de erro do HTTP Request (plano
    §5: nenhum HTTP do núcleo mata o fluxo), devolve {ok:false} e o W20 registra a falha por fn_registrar_falha — o
    W20 não morre, então o W90 NÃO dispara. O aviso de token errado é o status 'disjuntor' do W10 (3 falhas do W20
    em 30 min), não o W90. O motivo fica escrito (evento e linha do W20)."""
    foto = _foto_reais(pg)
    with _producao_com_token_invalido(pg, morre=False) as p:
        api = p["api"]
        antes = _ultimo_id_n8n(api)
        t = pg.execute("SELECT now() AS t").fetchone()["t"]

        assert _disparar(p["caminho"]) == 200

        (e20,) = _esperar(lambda: _terminadas(api, p["w20"], antes), 120, "a cópia do W20 terminar")
        (e22,) = _terminadas(api, p["w22"], antes)
        time.sleep(8)          # se o W90 fosse disparar, teria disparado
        w20 = pg.execute("SELECT id, status, erro FROM execucoes_workflow WHERE workflow = 'W20'"
                         " AND n8n_execution_id = %s", (e20["id"],)).fetchone()
        # A linha 'erro' do W20 alimentaria o disjuntor REAL: sai assim que lida.
        pg.execute("DELETE FROM execucoes_workflow WHERE id = %s", (w20["id"],))
        l = lic(pg, TOKEN_INVALIDO)
        print("\n[token tratado] W20 %s (%s, %s) -> W22 %s (%s) · linha W20 %s: %s · licitação %s tent. %s"
              % (e20["id"], e20["mode"], e20["status"], e22["id"], e22["status"], w20["status"], w20["erro"],
                 l["estado"], l["tentativas"]))
        assert e20["status"] == "success" and e22["status"] == "success"
        assert w20["status"] == "erro" and w20["erro"].startswith("W22: HTTP 403") and "token inválido" in w20["erro"]
        assert (l["estado"], l["lease_por"], l["lease_ate"], l["tentativas"]) == ("erro_leitura", None, None, 1)
        assert _backoff_de_15_min(pg, l)
        assert pg.execute("SELECT count(*) AS n FROM execucoes_workflow WHERE gatilho = 'erro' AND workflow LIKE %s",
                          ("%" + p["tag"] + "%",)).fetchone()["n"] == 0
        assert _execucoes(api, p["w90"], antes) == [], "o W90 disparou sem o W20 morrer"
        assert pg.execute("SELECT count(*) AS n FROM emails WHERE tipo = 'erro' AND em >= %s",
                          (t,)).fetchone()["n"] == 0
    assert _foto_reais(pg) == foto, "licitação REAL mudou durante o teste"


# ------------------------------------------------------------------ plano §11.7: nunca mais de 4 em `extraindo`
# "disparar 6+ processamentos → count(extraindo) ATINGE 4 em algum momento (senão o freio nunca foi exercitado) e
# nunca passa de 4, medido pelo Postgres". O freio não é do n8n nem do W10: o fn_reivindicar pega até 4 - extraindo
# POR RODADA, mas rodadas do W10 coexistem (agenda + W01 + W11) e o que ele reivindica ainda não está em `extraindo`
# — duas rodadas seguidas soltam 8 W20. O ÚNICO freio é o fn_tomar_vaga_extracao (db/019), sob advisory lock, no
# W23. Então a prova na instância é a RAJADA: 8 W20 ao mesmo tempo (um chamador de TESTE com Execute "each", sem
# esperar — o que duas rodadas do W10 fariam) sobre 8 licitações de TESTE em `preparada` com leitura sintética
# (CNPJ zerado, ensaio; o W20 vai direto ao W23), provedor simulado (R$ 0).
#
# Duas variantes:
#   copia_sem_teto — cópia do W23 que lê teto NULL (a do W20 chama esta cópia): o orçamento vigente é a trava de
#     construção de R$ 25/dia e o fn_tomar_vaga_extracao reserva R$ 6,56 por extração em curso, então a 4ª
#     simultânea (4 × 6,56 = 26,24 > 25) é recusada por ORÇAMENTO antes de a vaga faltar: com ele o freio de 4
#     nunca é exercitado. O `orcamento` NÃO é mexido; o que muda é só o que a cópia lê.
#   real_teto_vigente — W20/W23/W24 de verdade, com o orçamento vigente: o teto do dia é o freio que chega antes
#     (hoje: 3 simultâneas; as outras vão a `aguardando_orcamento` com UM e-mail 'orcamento' por dia).
# Evidência do Postgres, não do n8n: `em_curso` gravado pelo próprio fn_tomar_vaga_extracao em cada evento
# preparada→extraindo (quantas havia no instante da vaga, sob o lock), a linha do tempo dos eventos, e uma sonda
# que lê count(extraindo) a cada 50 ms durante a rajada.
RAJADA = ["00000000000000-1-%06d/2026" % n for n in range(941, 949)]   # 8; o 000940 é do teste do token inválido
PIOR_CASO_BRL = 6.56          # db/019 fn_tomar_vaga_extracao: reserva por extração em curso


def _url_pg() -> str:
    return "postgresql://postgres:%s@127.0.0.1:5433/fopa" % cliente.ler_env()["POSTGRES_PASSWORD"]


def _chamador_rajada(nome: str, w20_id: str, controles: list) -> dict:
    """Manual → os controles (fixos no fluxo) → Execute W20 'each' SEM ESPERAR: 8 W20 de uma vez."""
    return {
        "name": nome,
        "nodes": [
            {"parameters": {}, "id": str(uuid.uuid4()), "name": "Manual", "type": "n8n-nodes-base.manualTrigger",
             "typeVersion": 1, "position": [0, 0]},
            {"parameters": {"jsCode": "return %s.map(controle => ({ json: { controle } }));" % json.dumps(controles)},
             "id": str(uuid.uuid4()), "name": "A rajada", "type": "n8n-nodes-base.code", "typeVersion": 2,
             "position": [220, 0]},
            {"parameters": {
                "workflowId": {"__rl": True, "value": w20_id, "mode": "id"},
                "workflowInputs": {"mappingMode": "defineBelow",
                                   "value": {"controle": "={{ $json.controle }}", "forcar": False},
                                   "matchingColumns": [],
                                   "schema": [{"id": k, "displayName": k, "required": False, "defaultMatch": False,
                                               "display": True, "canBeUsedToMatch": True, "type": t}
                                              for k, t in (("controle", "string"), ("forcar", "boolean"))],
                                   "attemptToConvertTypes": False, "convertFieldsToString": False},
                "mode": "each", "options": {"waitForSubWorkflow": False}},
             "id": str(uuid.uuid4()), "name": "W20 (sem esperar)", "type": "n8n-nodes-base.executeWorkflow",
             "typeVersion": 1.2, "position": [440, 0]},
        ],
        "connections": {"Manual": {"main": [[{"node": "A rajada", "type": "main", "index": 0}]]},
                        "A rajada": {"main": [[{"node": "W20 (sem esperar)", "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1", "timezone": "America/Sao_Paulo"},
    }


TETO_DO_ORCAMENTO = "(SELECT o.teto_brl_dia FROM orcamento o WHERE o.vigente) AS teto_brl_dia"


@contextmanager
def _rajada(pg, copia_sem_teto: bool):
    api = cliente.N8n.autenticado()
    tag = uuid.uuid4().hex[:8]
    criados = []
    for c in RAJADA:
        _limpar(pg, c)
    try:
        ids_wf = {importar.codigo(w["name"]): w["id"] for w in api.listar_workflows() if importar.codigo(w["name"])}
        ids_cred = {c["name"]: c["id"] for c in api.listar_credenciais()}
        alvo = ids_wf["W20"]
        if copia_sem_teto:
            w23 = json.loads(json_do_fluxo("W23").read_text(encoding="utf-8"))
            (cfg,) = [n for n in w23["nodes"] if n["name"] == "Configuração e licitação"]
            assert cfg["parameters"]["query"].count(TETO_DO_ORCAMENTO) == 1
            cfg["parameters"]["query"] = cfg["parameters"]["query"].replace(TETO_DO_ORCAMENTO,
                                                                            "NULL::numeric AS teto_brl_dia")
            w23 = importar.resolver(w23, ids_wf, ids_cred, [])
            w23["name"] = "TESTE W23 sem teto %s (apagar)" % tag
            c23 = api.publica("POST", "/workflows", importar.corpo(w23))
            criados.append(c23["id"])
            importar.publicar(api, c23["id"])
            bruto = json.dumps(json.loads(json_do_fluxo("W20").read_text(encoding="utf-8")), ensure_ascii=False)
            assert bruto.count("{{WF:W23}}") == 1
            w20 = importar.resolver(json.loads(bruto.replace("{{WF:W23}}", c23["id"])), ids_wf, ids_cred, [])
            w20["name"] = "TESTE W20 rajada %s (apagar)" % tag
            w20["settings"].pop("errorWorkflow", None)           # a cópia não alarma o W90
            c20 = api.publica("POST", "/workflows", importar.corpo(w20))
            criados.append(c20["id"])
            importar.publicar(api, c20["id"])
            alvo = c20["id"]
        nome = "TESTE chamador da rajada %s (apagar)" % tag
        criados.append(api.publica("POST", "/workflows", _chamador_rajada(nome, alvo, RAJADA))["id"])
        for c in RAJADA:
            _nascer(pg, c, "preparada", "folha de pagamento — TESTE: rajada de extrações (plano §11.7)")
            _leitura_sintetica(pg, c)
        yield {"api": api, "chamador": nome, "w20": alvo, "tag": tag}
    finally:
        for wid in reversed(criados):
            try:
                api.publica("DELETE", "/workflows/" + wid)
            except cliente.ErroN8n as e:
                print("\n[rajada] não apaguei o fluxo %s: %s" % (wid, e))
        for c in RAJADA:          # com eventos, e-mails ('processada', 'orcamento'), linhas W20 e o RELATORIO do /render
            _limpar(pg, c)


def _rodar_rajada(pg, p, ao_atingir=None) -> dict:
    """Dispara os 8 W20 e espera todos fecharem, com a sonda de count(extraindo) rodando em outra conexão.
    `ao_atingir(n)` roda UMA vez, noutra thread, no instante em que a sonda vê 4 da rajada em `extraindo`."""
    import threading
    pico = {"todas": 0, "teste": 0, "amostras": 0}
    parar = threading.Event()
    medida, disparos = {}, []

    def disparar(n):
        medida.update(ao_atingir(n))

    def sonda():
        with psycopg.connect(_url_pg(), autocommit=True) as con:
            while not parar.is_set():
                todas, teste = con.execute(
                    "SELECT count(*) FILTER (WHERE estado = 'extraindo'),"
                    " count(*) FILTER (WHERE estado = 'extraindo' AND controle = ANY(%s)) FROM licitacoes",
                    (RAJADA,)).fetchone()
                pico["todas"], pico["teste"] = max(pico["todas"], todas), max(pico["teste"], teste)
                pico["amostras"] += 1
                if ao_atingir and teste >= 4 and not disparos:
                    disparos.append(threading.Thread(target=disparar, args=(teste,), daemon=True))
                    disparos[0].start()
                time.sleep(0.05)

    t = pg.execute("SELECT now() AS t").fetchone()["t"]
    th = threading.Thread(target=sonda, daemon=True)
    th.start()
    try:
        r = executar.executar(p["chamador"], timeout=120, api=p["api"])
        assert r["status"] == "success", "chamador %s: %s" % (r["id"], r["erro"])
        assert r["nos"]["W20 (sem esperar)"]["itens"] == [len(RAJADA)]

        def fechadas():
            x = pg.execute("SELECT controle, status, contadores FROM execucoes_workflow WHERE workflow = 'W20'"
                           " AND controle = ANY(%s) AND iniciado_em >= %s", (RAJADA, t)).fetchall()
            return x if len(x) == len(RAJADA) and all(y["status"] != "em_curso" for y in x) else None
        w20 = _esperar(fechadas, 600, "os 8 W20 da rajada fecharem", passo=1.0)
    finally:
        parar.set()
        th.join(10)
        for d in disparos:
            d.join(60)
    ev = pg.execute("SELECT id, controle, de::text, para::text, motivo, dados FROM licitacao_eventos"
                    " WHERE controle = ANY(%s) ORDER BY id", (RAJADA,)).fetchall()
    tomadas = [e for e in ev if e["para"] == "extraindo"]
    abertas, linha_do_tempo = set(), 0
    for e in ev:                      # quantas estavam em `extraindo` ao mesmo tempo, na ordem dos eventos
        if e["para"] == "extraindo":
            abertas.add(e["controle"])
        elif e["de"] == "extraindo":
            abertas.discard(e["controle"])
        linha_do_tempo = max(linha_do_tempo, len(abertas))
    return {"chamador": r["id"], "w20": w20, "tomadas": tomadas, "linha_do_tempo": linha_do_tempo, "sonda": pico,
            "em_curso": sorted(int(e["dados"]["em_curso"]) for e in tomadas),
            "estados": {c: lic(pg, c) for c in RAJADA}, "ao_atingir": medida}


def _limite_efetivo(pg) -> tuple[int, object]:
    """O que o fn_tomar_vaga_extracao deixa com o orçamento vigente: min(max_extracoes, (teto - gasto do dia)/6,56)."""
    x = pg.execute(
        "SELECT (SELECT (valor #>> '{}')::int FROM configuracao WHERE chave = 'max_extracoes') AS maximo,"
        " (SELECT teto_brl_dia FROM orcamento WHERE vigente) AS teto,"
        " (SELECT COALESCE(sum(brl), 0) FROM chamadas_modelo WHERE (em AT TIME ZONE 'America/Sao_Paulo')::date"
        "  = (now() AT TIME ZONE 'America/Sao_Paulo')::date) AS gasto").fetchone()
    maximo = x["maximo"] or 4
    if x["teto"] is None:
        return maximo, None
    return min(maximo, int((float(x["teto"]) - float(x["gasto"])) // PIOR_CASO_BRL)), x["teto"]


@pytest.mark.parametrize("variante", ["copia_sem_teto", "real_teto_vigente"])
def test_rajada_de_8_w20_nunca_passa_de_4_em_extraindo(instalado, pg, gratis, variante):
    ja = pg.execute("SELECT count(*) AS n FROM licitacoes WHERE estado = 'extraindo'").fetchone()["n"]
    if ja:
        pytest.skip("%d licitação(ões) em 'extraindo' agora: a medida seria de outra frente" % ja)
    if variante == "copia_sem_teto":
        limite, teto = pg.execute("SELECT (valor #>> '{}')::int AS m FROM configuracao WHERE chave = 'max_extracoes'"
                                  ).fetchone()["m"] or 4, None
    else:
        limite, teto = _limite_efetivo(pg)
        if limite < 1:
            pytest.skip("o orçamento de hoje não deixa extrair nada (teto %s)" % teto)
    foto = _foto_reais(pg)
    email_antes = maximo(pg, "emails")
    with _rajada(pg, copia_sem_teto=(variante == "copia_sem_teto")) as p:
        m = _rodar_rajada(pg, p)
        motivos = [((y["contadores"] or {}).get("passos") or [{}])[-1].get("motivo") for y in m["w20"]]
        est = {c: (x["estado"], x["lease_por"], x["tentativas"]) for c, x in m["estados"].items()}
        orc = pg.execute("SELECT id FROM emails WHERE id > %s AND tipo = 'orcamento' AND controle = ANY(%s)",
                         (email_antes, RAJADA)).fetchall()
        print("\n[rajada · %s] limite esperado %d (teto %s) · chamador n8n %s · em_curso na vaga %s · linha do tempo %d"
              " · sonda %s" % (variante, limite, teto, m["chamador"], m["em_curso"], m["linha_do_tempo"], m["sonda"]))
        print("[rajada · %s] estados %s" % (variante, sorted(x[0] for x in est.values())))
        print("[rajada · %s] motivos do W23: %s · e-mails 'orcamento' %s" % (variante, sorted(set(map(str, motivos))),
                                                                               len(orc)))

        # O freio: ninguém tomou vaga com `limite` já em curso (o banco anotou quantas havia, sob o lock) ...
        assert m["em_curso"] and max(m["em_curso"]) <= limite - 1 <= 3
        # ... e o limite foi ATINGIDO (senão o freio nunca teria sido exercitado), pela anotação e pela linha do tempo.
        assert max(m["em_curso"]) == limite - 1, "a rajada não chegou a %d simultâneas: %s" % (limite, m["em_curso"])
        assert m["linha_do_tempo"] == limite
        assert m["sonda"]["todas"] <= 4 and m["sonda"]["teste"] <= limite
        # Todo W20 fechou 'ok' (vaga ou adiamento não é falha) e devolveu o lease; ninguém gastou tentativa.
        assert all(y["status"] == "ok" for y in m["w20"]), [(y["controle"], y["status"]) for y in m["w20"]]
        assert all(lease is None and tent == 0 for _, lease, tent in est.values()), est
        vencedoras = {e["controle"] for e in m["tomadas"]}
        assert all(est[c][0] == "publicada" for c in vencedoras), est
        perdedoras = [c for c in RAJADA if c not in vencedoras]
        assert perdedoras, "8 W20 e nenhuma ficou sem vaga: a rajada não foi simultânea"
        if variante == "copia_sem_teto":
            # Sem teto, quem chega com 4 em curso volta à fila (preparada, +10 min): 'sem_vaga', nunca orçamento.
            assert all(est[c][0] == "preparada" for c in perdedoras), est
            assert "W23: sem vaga; nova tentativa em 10 min" in motivos and orc == []
        else:
            # Com o teto vigente abaixo de 4 × 6,56, quem chega com `limite` em curso vai esperar orçamento, com UM
            # e-mail no dia (nenhum, se já havia outro 'orcamento' hoje).
            assert all(est[c][0] == ("aguardando_orcamento" if limite < 4 else "preparada") for c in perdedoras), est
            assert len(orc) <= 1
    assert _foto_reais(pg) == foto, "licitação REAL mudou durante o teste"


def test_verificar_responde_em_menos_de_2s_com_4_em_extraindo(instalado, pg, gratis):
    # Plano 11.7: "com 4 em curso, fopa/verificar responde em < 2 s". O W11 responde 202 antes do trabalho e o
    # n8n não enfileira o webhook atrás das execuções pesadas. A rajada (cópia do W23 sem teto) põe 4 licitações
    # de teste em `extraindo`; no instante em que a sonda vê as 4, o "Verificar agora" de verdade é chamado com o
    # token do site. O W01 seco que ele dispara lê o PNCP (grátis) e a linha dele é apagada no fim, com as filhas.
    t = cliente.ler_env().get("FOPA_SITE_TOKEN")
    if not t:
        pytest.skip("FOPA_SITE_TOKEN vazio em docker/.env")
    token = _Oculto(t)
    if pg.execute("SELECT count(*) AS n FROM licitacoes WHERE estado = 'extraindo'").fetchone()["n"]:
        pytest.skip("há licitação em 'extraindo' agora: a medida seria de outra frente")
    foto = _foto_reais(pg)
    quem = "test_nucleo 11.7 " + secrets.token_hex(4)
    inicio = pg.execute("SELECT now() AS t").fetchone()["t"]

    def verificar(n):
        req = urllib.request.Request("%s/webhook/fopa/verificar" % cliente.base(), method="POST",
                                     data=json.dumps({"solicitado_por": quem}).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "X-FOPA-Token": token.valor()})
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=30) as r:
            status, corpo = r.status, json.loads(r.read().decode("utf-8"))
        dur = time.monotonic() - t0
        agora = pg_sonda_extraindo()
        return {"n": n, "depois": agora, "status": status, "dur": dur, "corpo": corpo}

    def pg_sonda_extraindo():
        with psycopg.connect(_url_pg(), autocommit=True) as con:
            return con.execute("SELECT count(*) FROM licitacoes WHERE estado = 'extraindo' AND controle = ANY(%s)",
                               (RAJADA,)).fetchone()[0]

    try:
        with _rajada(pg, copia_sem_teto=True) as p:
            m = _rodar_rajada(pg, p, ao_atingir=verificar)
        v = m["ao_atingir"]
        print("\n[11.7 verificar] com %s em extraindo: HTTP %s em %.3f s (depois: %s em extraindo) · execucao_id %s"
              % (v.get("n"), v.get("status"), v.get("dur", -1), v.get("depois"), (v.get("corpo") or {}).get("execucao_id")))
        assert v, "a sonda nunca viu 4 da rajada em extraindo"
        assert v["n"] >= 4 and v["status"] == 202
        assert v["dur"] < 2.0, "fopa/verificar levou %.2f s com 4 em extraindo" % v["dur"]
        assert isinstance(v["corpo"].get("execucao_id"), int)
    finally:
        # O W01 seco que o "Verificar agora" disparou: espera fechar (lê o PNCP inteiro) e apaga, filhas primeiro.
        def fechadas():
            x = pg.execute("SELECT id, status FROM execucoes_workflow WHERE workflow = 'W01' AND iniciado_em >= %s"
                           " AND argumentos ->> 'solicitado_por' = %s", (inicio, quem)).fetchall()
            return x if x and all(y["status"] != "em_curso" for y in x) else None
        try:
            ids = [y["id"] for y in _esperar(fechadas, 600, "o W01 seco do Verificar agora fechar", passo=3.0)]
        except AssertionError:
            ids = [y["id"] for y in pg.execute("SELECT id FROM execucoes_workflow WHERE workflow = 'W01'"
                                               " AND argumentos ->> 'solicitado_por' = %s", (quem,)).fetchall()]
        if ids:
            with pg.transaction():
                pg.execute("DELETE FROM buscas_paginas WHERE workflow_execucao_id = ANY(%s)", (ids,))
                pg.execute("DELETE FROM buscas WHERE workflow_execucao_id = ANY(%s)", (ids,))
                pg.execute("DELETE FROM execucoes_workflow WHERE id = ANY(%s)", (ids,))
    assert _foto_reais(pg) == foto, "licitação REAL mudou durante o teste"


SEM_PNCP = "00000000000000-1-000930/2026"


def test_reservada_em_preparada_vai_ao_w23_sem_pncp(instalado, pg, gratis):
    # Checklist F7, "Sem PNCP": a demo roda com reservadas em `preparada` (texto já congelado) e o W20 as leva
    # direto ao W23 pelo Switch — nenhum nó do W21 (baixar) nem do W22 (ler) roda, e o dia não depende do PNCP.
    # Licitação de teste com CNPJ zerado: se o W21 rodasse, o PNCP responderia 400 e o W20 falharia.
    foto = _foto_reais(pg)
    _limpar(pg, SEM_PNCP)
    try:
        _nascer(pg, SEM_PNCP, "preparada", "folha de pagamento — TESTE: demo sem PNCP (Checklist F7)")
        _leitura_sintetica(pg, SEM_PNCP)
        pg.execute("UPDATE licitacoes SET reserva_demo = true, ensaio = true WHERE controle = %s", (SEM_PNCP,))
        r = executar.executar("W20", timeout=300, itens=[{"controle": SEM_PNCP, "forcar": True}])
        nos = r["nos"]
        print("\n[sem PNCP] W20 %s %s · nós: %s" % (r["id"], r["status"], sorted(nos)))
        assert r["status"] == "success", r.get("erro")
        assert "Executar W21 Baixar" not in nos and "Executar W22 Ler" not in nos, sorted(nos)
        assert "Executar W23 Extrair" in nos and "Executar W24 Verificar e publicar" in nos, sorted(nos)
        l = lic(pg, SEM_PNCP)
        assert l["estado"] == "publicada" and l["lease_por"] is None, l
        (origem,) = pg.execute("SELECT e.origem FROM verificacoes v JOIN execucoes_modelo e ON e.id = v.execucao_id"
                               " WHERE v.controle = %s AND v.vigente", (SEM_PNCP,)).fetchone().values()
        assert origem == "simulado"
    finally:
        _limpar(pg, SEM_PNCP)
    assert _foto_reais(pg) == foto, "licitação REAL mudou durante o teste"
