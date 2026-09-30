# -*- coding: utf-8 -*-
"""
O núcleo do worker contra um Postgres real com o acervo importado:
reverificar (ADR-011/014), render (RELATORIO com link por id) e a publicação
do acervo (plano, seção 9, passo 7).

A régua é FIDELIDADE: o legado da fábrica é produzido pelo verificador REAL,
como o 70_extracao_por_agente fez no acervo; reverificar pela v3 tem de
reproduzir os mesmos vereditos. Nenhuma chamada de modelo.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "migracao" / "tests"))

from api.storage import Storage  # noqa: E402
from migracao import importar, plano as plano_mod  # noqa: E402
from migracao.acervo import Acervo  # noqa: E402
from tests import pg_efemero  # noqa: E402

import fabrica  # noqa: E402
from fabrica import PastaFake  # noqa: E402

C1 = "12345678000101-1-000001/2026"
C2 = "12345678000102-1-000002/2026"
EDITAL = b"%PDF edital"
TOKEN = "token-de-teste"
TAG = "Prompt Injection - Conteúdo Suspeito"


def _paginas_e_respostas():
    rs = fabrica.respostas("01 - Edital.pdf")
    # Trechos longos e ÚNICOS: "trecho Q1" estaria contido em "trecho Q10", e o
    # verificador, com razão, não reloca uma citação ambígua.
    for r in rs:
        if r["trecho_literal"]:
            r["trecho_literal"] = ("Conforme o item %s do edital, a informação pedida consta "
                                   "deste parágrafo." % r["id"])
    # Q2 cita a página 2, mas o trecho está na 1: o verificador corrige e deixa
    # REVISAR com o rastro — o caso de Adrianópolis Q9 e Fruta de Leite Q12.
    rs[1]["pagina"] = 2
    texto1 = "\n".join(r["trecho_literal"] for r in rs if r["trecho_literal"])
    paginas = [("01 - Edital.pdf", 1, texto1), ("01 - Edital.pdf", 2, "anexo sem os trechos")]
    return rs, paginas


def _acervo(tmp_path):
    rs, paginas = _paginas_e_respostas()
    agente = PastaFake(
        nome="Pregão - Eletrônico - Teste-SP", controle=C1, pdfs={"01 - Edital.pdf": EDITAL},
        auditoria=fabrica.auditoria_verificada("Pregão - Eletrônico - Teste-SP", rs, paginas),
        leitura_paginas=paginas, respostas_agente=rs,
        # a leitura viu texto furtivo; a auditoria legada perdeu a condição (o
        # 13_ reescrevia sem ela até 23/09) — é o caso São Simão/Camacho/Coreau
        leitura_condicoes={"arquivos_ocr": [], "paginas_ocr": 0,
                           "furtivos": ["01 - Edital.pdf p.1: texto branco sobre branco"]},
        finalizado=fabrica.finalizado("Pregão - Eletrônico - Teste-SP"))
    api = PastaFake(
        nome="Dispensa - Api-RS", controle=C2, pdfs={"01 - Edital.pdf": b"%PDF api"},
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
def ambiente(pg, tmp_path, monkeypatch):
    with psycopg.connect(pg, autocommit=True) as c:
        c.execute("TRUNCATE licitacoes, importacoes RESTART IDENTITY CASCADE")
    acervo = _acervo(tmp_path)
    storage = Storage(str(tmp_path / "dados"))
    with psycopg.connect(pg) as conn:
        importar.aplicar(conn, plano_mod.montar(acervo, hoje=date(2026, 9, 24)), acervo, storage)
    # o worker entra como worker_rw: os testes provam os grants, não só o SQL
    monkeypatch.setenv("DATABASE_URL", pg_efemero.url_papel(pg, "worker_rw"))
    monkeypatch.setenv("FOPA_WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("STORAGE_BACKEND", "fs")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "dados"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from api import worker
    return {"url": pg, "cliente": TestClient(worker.app), "storage": storage}


def _h():
    return {"Authorization": "Bearer " + TOKEN}


def _um(url, sql, *args):
    with psycopg.connect(url) as c:
        return c.execute(sql, args).fetchone()


# ------------------------------------------------------------------ reverificar
def test_reverificar_exige_token(ambiente):
    assert ambiente["cliente"].post("/reverificar", json={"controle": C1}).status_code == 401


def test_reverificar_reproduz_os_vereditos_do_legado(ambiente):
    r = ambiente["cliente"].post("/reverificar", json={"controle": C1}, headers=_h())
    assert r.status_code == 200, r.text
    d = r.json()
    # Fidelidade ao legado com UMA diferença deliberada: a política da v3 (api/politica.py,
    # decisão de 24/09) manda todo "Não localizado" para REVISAR — Q6 e Q16 da fábrica.
    assert d["diff_vs_anterior"]["vereditos"] == {"Q6": ["APROVADO", "REVISAR"],
                                                  "Q16": ["APROVADO", "REVISAR"]}
    assert not d["versao_regras"].startswith("legado:")
    novos = dict(psycopg.connect(ambiente["url"]).execute(
        "SELECT pergunta_id, veredito FROM verificacao_respostas WHERE verificacao_id = %s",
        (d["verificacao_id"],)).fetchall())
    legado = dict(psycopg.connect(ambiente["url"]).execute(
        "SELECT vr.pergunta_id, vr.veredito FROM verificacao_respostas vr JOIN verificacoes v"
        " ON v.id = vr.verificacao_id WHERE v.controle = %s AND v.vigente", (C1,)).fetchall())
    assert len(novos) == len(legado) == 17
    assert (legado["Q6"], legado["Q16"], novos["Q6"], novos["Q16"]) == ("APROVADO", "APROVADO", "REVISAR", "REVISAR")
    assert {k: v for k, v in novos.items() if k not in ("Q6", "Q16")} == \
        {k: v for k, v in legado.items() if k not in ("Q6", "Q16")}
    # página corrigida continua REVISAR, com o rastro, e nunca vira APROVADO
    assert novos["Q2"] == "REVISAR"
    alertas = _um(ambiente["url"], "SELECT alertas FROM verificacao_respostas WHERE verificacao_id = %s"
                  " AND pergunta_id = 'Q2'", d["verificacao_id"])[0]
    assert any("página corrigida" in a for a in alertas)
    # a nova não vira vigente sozinha: trocar números é decisão (ADR-014)
    assert _um(ambiente["url"], "SELECT vigente FROM verificacoes WHERE id = %s", d["verificacao_id"])[0] is False


def test_reverificar_devolve_a_tag_de_injecao(ambiente):
    antes = _um(ambiente["url"], "SELECT tags FROM verificacoes WHERE controle = %s AND vigente", C1)[0]
    assert TAG not in antes
    d = ambiente["cliente"].post("/reverificar", json={"controle": C1}, headers=_h()).json()
    assert TAG in d["resumo"]["tags"] and d["resumo"]["degradada"] is True


def test_reverificar_sem_paginas_congeladas_e_409(ambiente):
    r = ambiente["cliente"].post("/reverificar", json={"controle": C2}, headers=_h())
    assert r.status_code == 409 and "leitura" in r.json()["detail"]


def test_reverificar_duas_vezes_na_mesma_versao_e_409(ambiente):
    c = ambiente["cliente"]
    assert c.post("/reverificar", json={"controle": C1}, headers=_h()).status_code == 200
    assert c.post("/reverificar", json={"controle": C1}, headers=_h()).status_code == 409


# ------------------------------------------------------------------ render
def test_render_grava_o_relatorio_com_link_por_id(ambiente):
    vid, slug = _um(ambiente["url"], "SELECT v.id, l.slug FROM verificacoes v JOIN licitacoes l"
                    " ON l.controle = v.controle WHERE v.controle = %s AND v.vigente", C1)
    r = ambiente["cliente"].post("/render", json={"verificacao_id": vid}, headers=_h())
    assert r.status_code == 200, r.text
    d = r.json()
    html = ambiente["storage"].get(d["html_uri"]).decode("utf-8")
    arq = _um(ambiente["url"], "SELECT id FROM arquivos WHERE controle = %s AND nome = '01 - Edital.pdf'", C1)[0]
    assert "/api/pdf/%s/%d#page=1" % (slug, arq) in html
    assert "preço não configurado" in html and "R$ 0,00" not in html
    assert TAG not in html        # o render mostra a verificação como ela é, sem reverificar


# ------------------------------------------------------------------ publicação do acervo
def test_publicar_o_acervo_importado(ambiente):
    from migracao import publicar
    with psycopg.connect(ambiente["url"]) as conn:
        r = publicar.publicar(conn, ambiente["storage"])
    assert r["publicadas"] == 2
    estados = dict(psycopg.connect(ambiente["url"]).execute(
        "SELECT controle, estado::text FROM licitacoes").fetchall())
    assert estados == {C1: "publicada", C2: "publicada"}
    with psycopg.connect(ambiente["url"]) as c:
        assert c.execute((RAIZ / "db" / "invariantes.sql").read_text(encoding="utf-8")).fetchall() == []
    with psycopg.connect(ambiente["url"]) as conn:
        assert publicar.publicar(conn, ambiente["storage"])["publicadas"] == 0


# ------------------------------------------------------------------ utilitárias
def test_escopo(ambiente):
    r = ambiente["cliente"].post("/escopo", headers=_h(), json={"objetos": [
        "Cessão onerosa do direito de operacionalizar a folha de pagamento dos servidores",
        "Aquisição de software de gestão de folha de pagamento"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert [x["dentro"] for x in d["resultados"]] == [True, False]
    assert all(x["motivo"] for x in d["resultados"]) and len(d["escopo_versao"]) == 64


def test_questionario(ambiente):
    d = ambiente["cliente"].get("/questionario", headers=_h()).json()
    assert len(d["perguntas"]) == 17 and d["esquema_lote"]["required"] == ["respostas"]
    assert d["sistema"] and len(d["versao_prompt"]) == 64


def test_custo_pelo_preco_da_tabela(ambiente):
    uso = {"input_tokens": 1_000_000, "output_tokens": 0,
           "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    d = ambiente["cliente"].post("/custo", headers=_h(), json={"modelo": "claude-opus-5", "usage": uso}).json()
    assert d["preco_conhecido"] is True and d["usd"] == pytest.approx(5.0)
    # o Opus 5.5 entrou na tabela em 26/09 (US$ 4 por milhão de entrada); modelo fora dela não tem preço
    d = ambiente["cliente"].post("/custo", headers=_h(), json={"modelo": "claude-opus-5-5", "usage": uso}).json()
    assert d["preco_conhecido"] is True and d["usd"] == pytest.approx(4.0)
    d = ambiente["cliente"].post("/custo", headers=_h(), json={"modelo": "modelo-sem-preco", "usage": uso}).json()
    assert d["preco_conhecido"] is False and d["usd"] is None and d["brl"] is None


def test_escopo_acerta_os_23_casos_julgados_a_mao(ambiente):
    # O catálogo é a única fonte independente do filtro (23 casos julgados por
    # leitura humana, versionado como exceção do .gitignore). Pelo HTTP do
    # worker a regra tem de acertar os mesmos 23 que o 23_testa_escopo acerta
    # (plano, seção 11, teste 1: T3/T12/T14/T22).
    import json
    cat = json.load(open(RAIZ / "saidas" / "_catalogo_escopo.json", encoding="utf-8"))["casos"]
    r = ambiente["cliente"].post("/escopo", headers=_h(), json={"objetos": [c["objeto"] for c in cat]})
    assert r.status_code == 200
    obtidos = [x["dentro"] for x in r.json()["resultados"]]
    erros = [(c["orgao"], c["e_folha"]) for c, d in zip(cat, obtidos) if d != c["e_folha"]]
    assert len(cat) == 23 and erros == []
