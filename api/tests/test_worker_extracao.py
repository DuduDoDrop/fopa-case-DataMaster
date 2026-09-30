# -*- coding: utf-8 -*-
"""
O caminho da extração que o n8n percorre (W23/W24), contra Postgres real:
/prompt, /responder-simulado, /gravado/v1/messages, /verificar e
/importar-respostas. Nenhuma chamada de modelo: o "modelo" aqui é o
ProvedorSimulado ou um cliente falso que só CAPTURA o que o SDK mandaria.

O teste que mais importa é o da equivalência: o corpo que o /prompt monta para
o n8n mandar por HTTP cru tem de ser exatamente o que o `ProvedorClaude` da v2
manda pelo SDK para a mesma leitura (plano, seção 11, item 1). Se divergir, a
v3 mede outra coisa que a v2 mediu.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "migracao" / "tests"))
sys.path.insert(0, str(RAIZ / "scripts"))

from api.storage import Storage  # noqa: E402
from migracao import importar, plano as plano_mod  # noqa: E402
from migracao.acervo import Acervo  # noqa: E402
from tests import pg_efemero  # noqa: E402

import fabrica  # noqa: E402
from fabrica import PastaFake  # noqa: E402

C1 = "12345678000101-1-000001/2026"
C2 = "12345678000102-1-000002/2026"
TOKEN = "token-de-teste"
NOME = "Pregão - Eletrônico - Teste-SP"


def _texto_de_edital():
    # Texto com os termos-sinal das perguntas, para o simulado achar alguma coisa.
    return ("EDITAL DE PREGÃO ELETRÔNICO. Data da sessão pública: 10/10/2026 às 09h00.\n"
            "Objeto: cessão onerosa do direito de operacionalizar a folha de pagamento.\n"
            "Modalidade: pregão eletrônico, critério de julgamento maior oferta.\n"
            "Valor mínimo da oferta: R$ 1.000.000,00. Vigência do contrato: 60 meses.\n"
            "Quantidade de servidores: 1.200 vínculos ativos e inativos.\n")


def _acervo(tmp_path):
    rs = fabrica.respostas("01 - Edital.pdf")
    for r in rs:
        if r["trecho_literal"]:
            r["trecho_literal"] = "Conforme o item %s do edital, a informação consta deste parágrafo." % r["id"]
    texto = _texto_de_edital() + "\n".join(r["trecho_literal"] for r in rs if r["trecho_literal"])
    paginas = [("01 - Edital.pdf", 1, texto), ("02 - Termo.pdf", 1, "Termo de referência: folha de pagamento.")]
    agente = PastaFake(nome=NOME, controle=C1, pdfs={"01 - Edital.pdf": b"%PDF 1", "02 - Termo.pdf": b"%PDF 2"},
                       auditoria=fabrica.auditoria_verificada(NOME, rs, paginas), leitura_paginas=paginas,
                       respostas_agente=rs, finalizado=fabrica.finalizado(NOME))
    api = PastaFake(nome="Dispensa - Api-RS", controle=C2, pdfs={"01 - Edital.pdf": b"%PDF api"},
                    auditoria=fabrica.auditoria_verificada("Dispensa - Api-RS", rs, paginas,
                                                           modelo="claude-opus-5", agente=False))
    snap, vivo = fabrica.criar(str(tmp_path), [agente, api])
    return Acervo(snap, vivo)


@pytest.fixture(scope="module")
def pg():
    with pg_efemero.subir() as url:
        pg_efemero.migrar(url)
        yield url


@pytest.fixture
def amb(pg, tmp_path, monkeypatch):
    with psycopg.connect(pg, autocommit=True) as c:
        c.execute("TRUNCATE licitacoes, importacoes RESTART IDENTITY CASCADE")
    acervo = _acervo(tmp_path)
    with psycopg.connect(pg) as conn:
        importar.aplicar(conn, plano_mod.montar(acervo, hoje=date(2026, 9, 24)), acervo,
                         Storage(str(tmp_path / "dados")))
    monkeypatch.setenv("DATABASE_URL", pg_efemero.url_papel(pg, "worker_rw"))
    monkeypatch.setenv("FOPA_WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "dados"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from api import worker
    with psycopg.connect(pg) as c:
        leitura = c.execute("SELECT leitura_vigente_id FROM licitacoes WHERE controle = %s", (C1,)).fetchone()[0]
    return {"url": pg, "c": TestClient(worker.app), "leitura": leitura}


H = {"Authorization": "Bearer " + TOKEN}


def _prompt(amb, **kw):
    corpo = dict(leitura_id=amb["leitura"], provedor="claude", modelo="claude-opus-5",
                 effort="high", lote=6, k_rag=6, max_tokens=16000)
    corpo.update(kw)
    r = amb["c"].post("/prompt", headers=H, json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ /prompt × SDK
class _Bloco:
    def __init__(self, texto):
        self.type, self.text = "text", texto


class _Msg:
    def __init__(self, texto):
        self.content, self.stop_reason = [_Bloco(texto)], "end_turn"
        self.usage = type("U", (), {"input_tokens": 1, "output_tokens": 1,
                                    "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})()


class _Fluxo:
    def __init__(self, texto):
        self.texto = texto

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return _Msg(self.texto)


class _ClienteFalso:
    """Um cliente Anthropic que só ANOTA o que o SDK mandaria. Sem rede."""

    def __init__(self):
        self.enviados = []
        self.messages = self

    def stream(self, **kw):
        self.enviados.append(kw)
        # os ids do lote pelo mesmo leitor do worker: o content vem em blocos e na ordem nova (v3.1)
        from api import extracao
        ids = extracao.ids_do_usuario(kw["messages"][0]["content"])
        return _Fluxo(json.dumps({"respostas": [{"id": i, "resposta": "Não localizado", "arquivo": None,
                                                 "pagina": None, "trecho_literal": None, "conflito": None,
                                                 "confianca": "baixa"} for i in ids]}))


def _corpos_do_sdk(amb, modo):
    from fopa import extrator
    from fopa import recuperacao as rec
    from fopa.modelos import ProvedorClaude
    with psycopg.connect(amb["url"]) as c:
        pags = [rec.Pagina(a, n, t) for a, n, t in c.execute(
            "SELECT arquivo_nome, numero, texto FROM paginas WHERE leitura_id = %s ORDER BY ordem",
            (amb["leitura"],)).fetchall()]
    prov = ProvedorClaude.__new__(ProvedorClaude)      # sem chave: o cliente é falso
    prov.cliente = _ClienteFalso()
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        pasta = os.path.join(d, NOME)
        os.makedirs(pasta)
        extrator.extrair(pasta, prov, modelo="claude-opus-5", modo=modo, lote=6, k_rag=6,
                         effort="high", paginas_prontas=pags)
    return prov.cliente.enviados


@pytest.mark.parametrize("modo", ["contexto-completo", "rag"])
def test_prompt_e_identico_ao_corpo_do_sdk(amb, modo):
    sdk = _corpos_do_sdk(amb, modo)
    d = _prompt(amb, modo=modo)
    assert d["modo"] == modo and len(d["lotes"]) == len(sdk) == 3
    assert [l["ids"] for l in d["lotes"]] == [["Q%d" % i for i in range(1, 7)],
                                               ["Q%d" % i for i in range(7, 13)],
                                               ["Q%d" % i for i in range(13, 18)]]
    for lote, kw in zip(d["lotes"], sdk):
        # A v2 usa messages.stream(); a v3 manda o mesmo corpo sem stream. É a única diferença.
        assert lote["body"] == kw
        assert "stream" not in lote["body"] and len(lote["request_sha256"]) == 64


def test_prompt_escolhe_o_modo_pelo_tamanho(amb):
    assert _prompt(amb)["modo"] == "contexto-completo"      # texto curto: cabe inteiro


def test_prompt_com_ids_pendentes_so_manda_o_que_falta(amb):
    d = _prompt(amb, ids_pendentes=["Q7", "Q8", "Q16"])
    assert [l["ids"] for l in d["lotes"]] == [["Q7", "Q8", "Q16"]]


# ------------------------------------------------------------------ simulado e gravado
def test_responder_simulado_devolve_o_envelope_da_anthropic(amb):
    lote = _prompt(amb)["lotes"][0]
    r = amb["c"].post("/responder-simulado", headers=H, json={"body": lote["body"]})
    assert r.status_code == 200
    env = r.json()
    assert env["stop_reason"] == "end_turn" and env["usage"]["input_tokens"] == 0
    dados = json.loads("".join(b["text"] for b in env["content"] if b["type"] == "text"))
    assert [x["id"] for x in dados["respostas"]] == lote["ids"]



def _no_esquema(esquema: dict, valor, onde: str = "$") -> list[str]:
    """Validador mínimo para o formato do ESQUEMA_LOTE (type, properties, required,
    additionalProperties=False, items, enum) — o worker não tem jsonschema."""
    tipos = {"object": dict, "array": list, "string": str, "null": type(None), "integer": int}
    aceitos = esquema.get("type")
    aceitos = [aceitos] if isinstance(aceitos, str) else (aceitos or [])
    if aceitos and not any(isinstance(valor, tipos[t]) and not (t == "integer" and isinstance(valor, bool))
                           for t in aceitos):
        return ["%s: %r não é %s" % (onde, valor, "/".join(aceitos))]
    erros = []
    if "enum" in esquema and valor not in esquema["enum"]:
        erros.append("%s: %r fora de %s" % (onde, valor, esquema["enum"]))
    if isinstance(valor, dict):
        props = esquema.get("properties", {})
        erros += ["%s: falta %s" % (onde, k) for k in esquema.get("required", []) if k not in valor]
        if esquema.get("additionalProperties") is False:
            erros += ["%s: sobra %s" % (onde, k) for k in valor if k not in props]
        for k, v in valor.items():
            if k in props:
                erros += _no_esquema(props[k], v, "%s.%s" % (onde, k))
    if isinstance(valor, list) and "items" in esquema:
        for i, v in enumerate(valor):
            erros += _no_esquema(esquema["items"], v, "%s[%d]" % (onde, i))
    return erros


def test_responder_simulado_os_3_lotes_no_esquema_lote(amb):
    # Checklist F3 (11.1): o W23 manda os 3 lotes ao simulado e faz o parse como faria com o
    # modelo. Cada envelope tem de trazer JSON válido no ESQUEMA_LOTE, com os ids do lote.
    from fopa.questionario import ESQUEMA_LOTE
    assert _no_esquema(ESQUEMA_LOTE, {"respostas": [{"id": "Q1"}]}), "o validador sabe falhar"
    lotes = _prompt(amb)["lotes"]
    assert len(lotes) == 3
    vistos = []
    for lote in lotes:
        env = amb["c"].post("/responder-simulado", headers=H, json={"body": lote["body"]}).json()
        dados = json.loads("".join(b["text"] for b in env["content"] if b["type"] == "text"))
        assert _no_esquema(ESQUEMA_LOTE, dados) == [], lote["ids"]
        assert [x["id"] for x in dados["respostas"]] == lote["ids"]
        vistos += lote["ids"]
    assert len(vistos) == len(set(vistos)) == 17


def test_gravado_repete_a_execucao_canonica(amb):
    lote = _prompt(amb)["lotes"][1]
    r = amb["c"].post("/gravado/v1/messages?controle=" + C2, headers=H, json={"body": lote["body"]})
    assert r.status_code == 200, r.text
    dados = json.loads(r.json()["content"][0]["text"])
    assert [x["id"] for x in dados["respostas"]] == lote["ids"]
    assert dados["respostas"][0]["trecho_literal"].startswith("Conforme o item Q7")
    r = amb["c"].post("/gravado/v1/messages?controle=99999999000199-1-000001/2026", headers=H,
                      json={"body": lote["body"]})
    assert r.status_code == 404


# ------------------------------------------------------------------ /verificar
def _execucao_simulada(amb):
    """O que o W23 faz: abre a execução, manda cada lote, grava cada chamada."""
    d = _prompt(amb, provedor="simulado")
    with psycopg.connect(amb["url"]) as c:
        eid = c.execute(
            "INSERT INTO execucoes_modelo (controle, leitura_id, origem, provedor, modelo, modo, effort,"
            " lote, k_rag, status, canonica, versao_prompt) VALUES (%s, %s, 'simulado', 'simulado',"
            " 'simulado', %s, 'high', 6, 6, 'em_curso', false, %s) RETURNING id",
            (C1, amb["leitura"], d["modo"], d["versao_prompt"])).fetchone()[0]
        for lote in d["lotes"]:
            env = amb["c"].post("/responder-simulado", headers=H, json={"body": lote["body"]}).json()
            c.execute("INSERT INTO chamadas_modelo (execucao_id, lote_ids, dados, stop_reason, http_status,"
                      " tentativas, tok_entrada, tok_saida, request_sha256, usd, brl, preco_conhecido)"
                      " VALUES (%s, %s, %s, 'end_turn', 200, 1, 0, 0, %s, 0, 0, true)",
                      (eid, lote["ids"], json.dumps(env), lote["request_sha256"]))
    return eid


def test_verificar_funde_os_lotes_e_fecha_a_execucao(amb):
    eid = _execucao_simulada(amb)
    r = amb["c"].post("/verificar", headers=H, json={"execucao_id": eid})
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["respostas"]) == 17 and d["resumo"]["respondidas"] >= 0
    with psycopg.connect(amb["url"]) as c:
        status, brl, conhecido = c.execute(
            "SELECT status, brl, preco_conhecido FROM execucoes_modelo WHERE id = %s", (eid,)).fetchone()
        assert status == "ok" and conhecido is True and float(brl) == 0.0
        assert c.execute("SELECT count(*) FROM respostas WHERE execucao_id = %s", (eid,)).fetchone()[0] == 17
        vig = c.execute("SELECT vigente FROM verificacoes WHERE id = %s", (d["verificacao_id"],)).fetchone()[0]
        assert vig is False          # simulado nunca vira vigente sozinho (T15); quem decide é o W24
    assert amb["c"].post("/verificar", headers=H, json={"execucao_id": eid}).status_code == 409


def test_verificar_sem_todas_as_chamadas_e_422(amb):
    eid = _execucao_simulada(amb)
    with psycopg.connect(amb["url"]) as c:
        c.execute("DELETE FROM chamadas_modelo WHERE execucao_id = %s AND 'Q13' = ANY(lote_ids)", (eid,))
    r = amb["c"].post("/verificar", headers=H, json={"execucao_id": eid})
    assert r.status_code == 422 and "Q13" in r.json()["detail"]


# ------------------------------------------------------------------ /importar-respostas
def test_importar_respostas_do_agente(amb):
    rs = fabrica.respostas("01 - Edital.pdf")
    r = amb["c"].post("/importar-respostas", headers=H, json={
        "controle": C1, "leitura_id": amb["leitura"], "respostas": rs,
        "procedencia": {"provedor": "claude-code", "modelo": "claude-opus-5-5", "sessao": "teste"}})
    assert r.status_code == 200, r.text
    with psycopg.connect(amb["url"]) as c:
        origem, modo, conhecido = c.execute(
            "SELECT origem, modo, preco_conhecido FROM execucoes_modelo WHERE id = %s",
            (r.json()["execucao_id"],)).fetchone()
    assert (origem, modo, conhecido) == ("agente", "agente", False)



def test_importar_respostas_sem_verificar_so_cria_a_execucao(amb):
    # Para o "Importar respostas do agente" do site (W11): a licitação que ainda não foi extraída segue
    # respondida → W24, e é o W24 que verifica e publica, como depois do W23. Com verificar=false o worker só grava
    # a execução 'agente' e as respostas (em_curso) — sem verificação, para não verificar duas vezes.
    rs = fabrica.respostas("01 - Edital.pdf")
    r = amb["c"].post("/importar-respostas", headers=H, json={
        "controle": C1, "leitura_id": amb["leitura"], "respostas": rs, "verificar": False,
        "procedencia": {"provedor": "claude-code", "modelo": "claude-opus-5-5", "sessao": "teste"}})
    assert r.status_code == 200, r.text
    eid = r.json()["execucao_id"]
    assert r.json().get("verificacao_id") is None and r.json()["verificado"] is False
    with psycopg.connect(amb["url"]) as c:
        st, n_ver = c.execute("SELECT e.status, (SELECT count(*) FROM verificacoes v WHERE v.execucao_id = e.id)"
                              " FROM execucoes_modelo e WHERE e.id = %s", (eid,)).fetchone()
    assert (st, n_ver) == ("em_curso", 0)
    # e o /verificar dessa execução — o que o W24 faz — fecha tudo como no caminho com verificação
    v = amb["c"].post("/verificar", headers=H, json={"execucao_id": eid})
    assert v.status_code == 200, v.text
    assert v.json()["verificacao_id"]


def test_importar_respostas_incompletas_e_422(amb):
    rs = fabrica.respostas("01 - Edital.pdf")[:-1]
    r = amb["c"].post("/importar-respostas", headers=H, json={
        "controle": C1, "leitura_id": amb["leitura"], "respostas": rs,
        "procedencia": {"provedor": "claude-code", "modelo": "claude-opus-5-5"}})
    assert r.status_code == 422 and "Q17" in r.json()["detail"]


def test_rotas_de_extracao_exigem_token(amb):
    for rota in ("/prompt", "/responder-simulado", "/verificar", "/importar-respostas"):
        assert amb["c"].post(rota, json={}).status_code == 401
