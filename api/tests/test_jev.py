# -*- coding: utf-8 -*-
"""
O Jev na v3: segundo sinal, nunca decisão. Sem chamada real ao Jev — as
respostas são montadas no formato que a API devolve (conferido ao vivo em
23/09/2026, fopa/jev.py). O n8n é quem chama o Jev, com a credencial dele; o
worker monta o corpo com o critério medido e interpreta com o corte medido.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "migracao" / "tests"))

from api import jev as jev_mod  # noqa: E402
from api.storage import Storage  # noqa: E402
from migracao import importar, plano as plano_mod  # noqa: E402
from migracao.acervo import Acervo  # noqa: E402
from tests import pg_efemero  # noqa: E402

import fabrica  # noqa: E402
from fabrica import PastaFake  # noqa: E402

C1 = "12345678000101-1-000001/2026"
TOKEN = "t"
H = {"Authorization": "Bearer " + TOKEN}


def _noul(p):
    return {"escopo": {"type": "noul", "noul": p}}


# ------------------------------------------------------------------ puras
def test_corpo_de_escopo_usa_o_criterio_v31_medido():
    # v3 (24/09/2026, scripts/67_jev_escopo_criterio.py): o v2 dava p <= 0,25 a
    # 9 folhas reais do acervo ("processamento e gerenciamento de créditos
    # provenientes da folha" — Itatiba, Salto, Valinhos, Votorantim); o v3,
    # com a instrução em inglês e exemplos dos dois lados, zera esses erros
    # sem piorar os negativos (AUC 0,947 -> 0,968).
    # v3.1 (25/09/2026, scripts/77_jev_credenciamento.py): o v3 falava em "contracting" e em "buys the exclusive
    # right", e credenciamento não é nenhum dos dois — o ponto cego medido (as 5 discordâncias do painel). Só
    # acrescentar o caso: folhas reconhecidas 96,8% -> 100%, credenciamentos de folha < 0,5 de 23 para 6 em 137,
    # as mesmas recusas pegas, e zero troca de lado entre duas chamadas iguais (o v3 trocou 10).
    corpo = jev_mod.corpo_escopo("Credenciamento de instituição financeira para gerenciamento dos créditos da folha")
    q = corpo["questions"]["escopo"]
    assert q["type"] == "noul" and "RUN ITS PAYROLL" in q["instructions"]
    assert "contracting or accrediting ('credenciamento') a bank" in q["instructions"]
    assert "is accredited to do so ('credenciamento')" in q["criteria"]["true"]
    assert "payroll loan product" in q["criteria"]["false"]
    assert corpo["state"].startswith("Credenciamento de instituição financeira") and corpo["model"]
    assert jev_mod.CRITERIO_ESCOPO == "v3.1"


@pytest.mark.parametrize("regra,p,candidata", [
    (False, 0.85, True),     # São Mateus do Maranhão: a regra recusou, o Jev diz 0,85
    (True, 0.17, True),      # Diorama: a regra aceitou, o Jev diz 0,17
    (True, 0.44, False),     # do outro lado por pouco: indecisão, não discordância
    (False, 0.60, False),
    (True, 0.95, False),     # concorda: nada a olhar
])
def test_escopo_so_e_candidata_com_conviccao(regra, p, candidata):
    s = jev_mod.interpretar_escopo(regra, _noul(p), {"input_tokens": 300})
    assert s["candidata"] is candidata and s["p_sim"] == p
    assert s["usd"] == pytest.approx(300 * 0.042 / 1_000_000)


def test_janela_cresce_em_volta_da_pagina_citada_e_respeita_o_teto():
    paginas = ["pagina %d " % i + "x" * 1000 for i in range(1, 11)]
    texto, como = jev_mod.janela(paginas, alvo=5, teto=3200)
    assert como == "janela 3p (de 10)"
    assert "pagina 5 " in texto and "pagina 4 " in texto and "pagina 6 " in texto
    assert "pagina 1 " not in texto
    texto, como = jev_mod.janela(paginas[:2], alvo=1, teto=10_000)
    assert como == "documento"


# ------------------------------------------------------------------ com banco
@pytest.fixture(scope="module")
def pg():
    with pg_efemero.subir() as url:
        pg_efemero.migrar(url)
        yield url


@pytest.fixture
def amb(pg, tmp_path, monkeypatch):
    with psycopg.connect(pg, autocommit=True) as c:
        c.execute("TRUNCATE licitacoes, importacoes RESTART IDENTITY CASCADE")
    rs = fabrica.respostas("01 - Edital.pdf")
    for r in rs:
        if r["trecho_literal"]:
            r["trecho_literal"] = "Conforme o item %s do edital, a informação consta deste parágrafo." % r["id"]
    paginas = [("01 - Edital.pdf", 1, "\n".join(r["trecho_literal"] for r in rs if r["trecho_literal"]))]
    nome = "Pregão - Eletrônico - Teste-SP"
    pasta = PastaFake(nome=nome, controle=C1, pdfs={"01 - Edital.pdf": b"%PDF"},
                      auditoria=fabrica.auditoria_verificada(nome, rs, paginas), leitura_paginas=paginas,
                      respostas_agente=rs, finalizado=fabrica.finalizado(nome))
    snap, vivo = fabrica.criar(str(tmp_path), [pasta])
    acervo = Acervo(snap, vivo)
    with psycopg.connect(pg) as conn:
        importar.aplicar(conn, plano_mod.montar(acervo, hoje=date(2026, 9, 24)), acervo,
                         Storage(str(tmp_path / "d")))
    monkeypatch.setenv("DATABASE_URL", pg_efemero.url_papel(pg, "worker_rw"))
    monkeypatch.setenv("FOPA_WORKER_TOKEN", TOKEN)
    from api import worker
    vid = psycopg.connect(pg).execute("SELECT id FROM verificacoes WHERE vigente").fetchone()[0]
    return {"url": pg, "c": TestClient(worker.app), "vid": vid}


def test_rota_de_escopo_monta_e_interpreta_e_grava_o_sinal(amb):
    c = amb["c"]
    corpos = c.post("/jev/escopo/corpos", headers=H, json={"itens": [
        {"controle": C1, "objeto": "Cessão onerosa da folha de pagamento dos servidores"}]}).json()
    (req,) = corpos["requisicoes"]
    assert req["controle"] == C1 and req["regra_dentro"] is True and corpos["url"].startswith("https://")
    r = c.post("/jev/escopo/interpretar", headers=H, json={
        "controle": C1, "regra_dentro": True, "resposta": {"answers": _noul(0.10), "usage": {"input_tokens": 250},
                                                          "model": "jev-1.13.0"}})
    assert r.status_code == 200 and r.json()["candidata"] is True
    with psycopg.connect(amb["url"]) as db:
        tipo, cand, modelo = db.execute("SELECT tipo, candidata, modelo_jev FROM sinais_jev").fetchone()
        assert (tipo, cand, modelo) == ("escopo", True, "jev-1.13.0")
        # a regra continua mandando: o Jev não reclassifica
        assert db.execute("SELECT escopo_dentro FROM licitacoes WHERE controle = %s", (C1,)).fetchone()[0] is True


def test_rota_de_sustenta_aprovada_contradita_vira_revisao(amb):
    c = amb["c"]
    d = c.post("/jev/sustenta/corpos", headers=H, json={"verificacao_id": amb["vid"]}).json()
    ids = [r["pergunta_id"] for r in d["requisicoes"]]
    assert ids and all(i not in ("Q6", "Q16") for i in ids)          # sem trecho, nada a sustentar
    estado = json.loads(d["requisicoes"][0]["body"]["state"])
    assert estado["trecho_citado"] and estado["afirmacao"] and "contexto_enviado" in d["requisicoes"][0]
    r = c.post("/jev/sustenta/interpretar", headers=H, json={
        "verificacao_id": amb["vid"], "pergunta_id": ids[0], "contexto_enviado": "documento",
        "resposta": {"answers": {"relacao": {"type": "choice", "choice": "contradiz", "confidence": 0.99,
                                             "probabilities": {"contradiz": 0.99}}},
                     "usage": {"input_tokens": 700}, "model": "jev-1.13.0"}})
    assert r.status_code == 200 and r.json()["candidata"] is True
    with psycopg.connect(amb["url"]) as db:
        assert db.execute("SELECT count(*) FROM revisoes_humanas WHERE status = 'aberta'"
                          " AND motivo LIKE 'jev:%%'").fetchone()[0] == 1
        # o veredito não muda: o Jev nunca aprova nem reprova
        assert db.execute("SELECT veredito FROM verificacao_respostas WHERE verificacao_id = %s"
                          " AND pergunta_id = %s", (amb["vid"], ids[0])).fetchone()[0] == "APROVADO"


def _contradiz():
    return {"answers": {"relacao": {"type": "choice", "choice": "contradiz", "confidence": 0.99,
                                    "probabilities": {"contradiz": 0.99, "sustenta": 0.01}}},
            "usage": {"input_tokens": 700}, "model": "jev-1.13.0"}


def test_sustenta_em_toda_resposta_com_trecho_e_so_a_aprovada_abre_revisao(amb):
    # Cada pergunta e resposta ganha a métrica do Jev: o quanto a passagem sustenta a resposta. Não só a
    # APROVADA: toda resposta que cita trecho ganha o score.
    c = amb["c"]
    with psycopg.connect(amb["url"], autocommit=True) as db:
        db.execute("UPDATE verificacao_respostas SET veredito = 'REVISAR' WHERE verificacao_id = %s"
                   " AND pergunta_id = 'Q2'", (amb["vid"],))
    d = c.post("/jev/sustenta/corpos", headers=H, json={"verificacao_id": amb["vid"]}).json()
    por_q = {r["pergunta_id"]: r for r in d["requisicoes"]}
    assert por_q["Q2"]["veredito"] == "REVISAR" and por_q["Q1"]["veredito"] == "APROVADO"
    r = c.post("/jev/sustenta/interpretar", headers=H, json={
        "verificacao_id": amb["vid"], "pergunta_id": "Q2", "contexto_enviado": "documento",
        "resposta": _contradiz()})
    assert r.status_code == 200 and r.json()["candidata"] is True and r.json()["p_sustenta"] == 0.01
    with psycopg.connect(amb["url"]) as db:
        assert db.execute("SELECT regra FROM sinais_jev WHERE tipo = 'sustenta' AND pergunta_id = 'Q2'"
                          ).fetchone()[0] == "REVISAR"
        # a REVISAR já está na mão de gente: o score vai para a tela, sem abrir outra revisão
        assert db.execute("SELECT count(*) FROM revisoes_humanas WHERE motivo LIKE 'jev:%%'").fetchone()[0] == 0
    # rodar de novo só pergunta o que falta: Q2 já tem o sinal do critério atual
    d2 = c.post("/jev/sustenta/corpos", headers=H, json={"verificacao_id": amb["vid"], "so_faltando": True}).json()
    ids2 = [r["pergunta_id"] for r in d2["requisicoes"]]
    assert "Q2" not in ids2 and "Q1" in ids2


def test_escopo_com_edital_monta_rag_da_leitura_e_grava_o_contexto(amb):
    # Mais contexto para o Jev, com RAG (24/09). Medido em 73_: o
    # só-objeto dava alarme falso em 4% da folha (os credenciamentos); com o edital, em 0,8%.
    c = amb["c"]
    with psycopg.connect(amb["url"], autocommit=True) as db:
        db.execute("UPDATE paginas SET texto = texto || ' Credenciamento de instituição financeira para processar"
                   " os créditos da folha de pagamento dos servidores.'")
    d = c.post("/jev/escopo/edital/corpos", headers=H, json={"controles": [C1, "00000000000000-1-000009/2026"]}).json()
    (req,) = d["requisicoes"]                       # a que não existe (ou não tem leitura) não vem
    assert req["controle"] == C1 and req["regra_dentro"] is True and d["criterio_versao"] == "v3+edital"
    estado = json.loads(req["body"]["state"])
    assert estado["objeto"] and estado["trechos_do_edital"] and estado["trechos_do_edital"][0]["pagina"] == 1
    assert req["contexto_enviado"].startswith("edital RAG 1p")
    assert "trechos_do_edital" in req["body"]["questions"]["escopo"]["instructions"]
    r = c.post("/jev/escopo/interpretar", headers=H, json={
        "controle": C1, "regra_dentro": True, "contexto_enviado": req["contexto_enviado"],
        "resposta": {"answers": _noul(0.90), "usage": {"input_tokens": 3000}, "model": "jev-1.13.0"}})
    assert r.status_code == 200
    with psycopg.connect(amb["url"]) as db:
        ctx, crit = db.execute("SELECT contexto_enviado, criterio_versao FROM sinais_jev ORDER BY id DESC LIMIT 1").fetchone()
    assert ctx.startswith("edital RAG") and crit == "escopo-v3+edital"
    # rodar de novo só pergunta o que falta
    assert c.post("/jev/escopo/edital/corpos", headers=H,
                  json={"controles": [C1], "so_faltando": True}).json()["requisicoes"] == []


def test_a_rodada_do_w24_leva_tambem_o_escopo_com_o_edital_uma_vez(amb):
    # A W24 já chama o Jev para o "sustenta?" de cada resposta; a mesma rodada leva a nota de escopo com o edital
    # (73_), UMA vez por licitação lida — sem ela, a licitação extraída daqui em diante ficaria só com a nota do
    # objeto e o alarme falso dos credenciamentos voltaria. Sem pergunta = o escopo da licitação.
    c = amb["c"]
    with psycopg.connect(amb["url"], autocommit=True) as db:
        db.execute("UPDATE paginas SET texto = texto || ' Processamento dos créditos da folha de pagamento.'")
    d = c.post("/jev/sustenta/corpos", headers=H, json={"verificacao_id": amb["vid"]}).json()
    escopo = [r for r in d["requisicoes"] if r["pergunta_id"] is None]
    assert len(escopo) == 1 and escopo[0]["tipo"] == "escopo" and escopo[0]["contexto_enviado"].startswith("edital")
    assert d["requisicoes"][0]["pergunta_id"] is not None           # as de sustenta vêm primeiro, como antes
    r = c.post("/jev/sustenta/interpretar", headers=H, json={
        "verificacao_id": amb["vid"], "pergunta_id": None, "contexto_enviado": escopo[0]["contexto_enviado"],
        "resposta": {"answers": _noul(0.95), "usage": {"input_tokens": 3000}, "model": "jev-1.13.0"}})
    assert r.status_code == 200 and r.json()["candidata"] is False
    with psycopg.connect(amb["url"]) as db:
        tipo, crit, regra = db.execute("SELECT tipo, criterio_versao, regra FROM sinais_jev ORDER BY id DESC LIMIT 1").fetchone()
        assert (tipo, crit, regra) == ("escopo", "escopo-v3+edital", "dentro")
        assert db.execute("SELECT count(*) FROM revisoes_humanas WHERE motivo LIKE 'jev:%%'").fetchone()[0] == 0
    # já tem a nota com o edital: a próxima rodada não pergunta de novo
    d2 = c.post("/jev/sustenta/corpos", headers=H, json={"verificacao_id": amb["vid"]}).json()
    assert [r for r in d2["requisicoes"] if r["pergunta_id"] is None] == []


# ------------------------------------------------------------------ T25
def test_t25_nada_do_jev_escreve_em_veredito_confianca_ou_escopo():
    # A linha que não pode ser cruzada (ADR-004, "Jev na v3"): nenhum código
    # que lida com o Jev atribui a veredito, confianca ou escopo_dentro.
    # Filtrar por veredito (WHERE vr.veredito = 'APROVADO') é permitido; ATRIBUIR não.
    decisao = r"(veredito|confianca|escopo_dentro)\s*=(?!=)"
    set_sql = re.compile(r"\bSET\b(.*?)(\bWHERE\b|;|\"|$)", re.I | re.S)
    atribuicao_py = re.compile(r"^\s*[\w.\[\]\"']+\.(veredito|confianca|escopo_dentro)\s*=(?!=)", re.M)
    insert_decisao = re.compile(r"INSERT\s+INTO\s+(verificacao_respostas|respostas)\b", re.I)
    fontes = [RAIZ / "api" / "jev.py", RAIZ / "api" / "rotas_jev.py"]
    fontes += sorted((RAIZ / "n8n" / "workflows").glob("*.json")) if (RAIZ / "n8n" / "workflows").is_dir() else []
    for f in fontes:
        texto = f.read_text(encoding="utf-8")
        if f.suffix == ".json" and "typesafe" not in texto.lower() and "jev" not in texto.lower():
            continue
        sets = [m.group(1) for m in set_sql.finditer(texto)]
        assert not any(re.search(r"\b" + decisao, s, re.I) for s in sets), "%s: UPDATE de decisão" % f.name
        assert not atribuicao_py.search(texto), "%s: atribui decisão em Python" % f.name
        assert not insert_decisao.search(texto), "%s: grava resposta/veredito" % f.name


def test_t25_pega_quem_cruza_a_linha(tmp_path):
    # O guarda precisa saber falhar: estes três trechos são exatamente o proibido.
    decisao = r"(veredito|confianca|escopo_dentro)\s*=(?!=)"
    set_sql = re.compile(r"\bSET\b(.*?)(\bWHERE\b|;|\"|$)", re.I | re.S)
    atribuicao_py = re.compile(r"^\s*[\w.\[\]\"']+\.(veredito|confianca|escopo_dentro)\s*=(?!=)", re.M)
    assert any(re.search(r"\b" + decisao, s.group(1), re.I) for s in set_sql.finditer(
        "UPDATE licitacoes SET escopo_dentro = %s WHERE controle = %s"))
    assert atribuicao_py.search("    r.veredito = 'APROVADO'\n")
    assert not any(re.search(r"\b" + decisao, s.group(1), re.I) for s in set_sql.finditer(
        "SELECT 1 FROM verificacao_respostas vr WHERE vr.veredito = 'APROVADO'"))


# ------------------------------------------------------------------ os scores
@pytest.mark.parametrize("regra,p,filtro_ok", [(True, 0.9, 0.9), (False, 0.9, 0.1), (False, 0.05, 0.95)])
def test_score_do_filtro_e_a_probabilidade_da_regra_ter_acertado(regra, p, filtro_ok):
    # A probabilidade de o filtro ter acertado: se a regra disse DENTRO, é P(folha);
    # se disse FORA, é 1 - P(folha). É o número que mede o ruído da busca do PNCP.
    s = jev_mod.interpretar_escopo(regra, _noul(p), None)
    assert s["p_filtro_ok"] == pytest.approx(filtro_ok)


def test_score_da_resposta_e_a_probabilidade_de_sustentar():
    s = jev_mod.interpretar_sustenta({"relacao": {"type": "choice", "choice": "sustenta", "confidence": 0.9,
                                                  "probabilities": {"sustenta": 0.93, "contradiz": 0.02,
                                                                    "nada_diz": 0.05}}}, None)
    assert s["p_sustenta"] == pytest.approx(0.93) and s["candidata"] is False
