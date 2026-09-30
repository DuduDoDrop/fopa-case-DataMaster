# -*- coding: utf-8 -*-
"""
POST /escopo/reavaliar: a regra de escopo de HOJE sobre o veredito gravado.

Um cache do resultado de uma regra morre quando a regra muda (40_fumaca,
teste 12). Quando a ADR-015 apertou a regra, 13 licitações que ela passou a
recusar estavam em `preparada`, na fila da extração paga, com o veredito da
regra antiga. Este endpoint é o dono da regra (ADR-003) reaplicando-a; o Jev
não passa por aqui (T25).
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from tests import pg_efemero  # noqa: E402

TOKEN = "t"
H = {"Authorization": "Bearer " + TOKEN}
MACAE = ("Prestação de serviços de concessão de empréstimo pessoal, compra de dívida dos Servidores "
         "Públicos Municipais, mediante desconto em folha de pagamento")
CESSAO = "Cessão onerosa do direito de processamento da folha de pagamento dos servidores municipais"
TARIFAS = "Contratação de instituição bancária para pagamento de tarifas folha de pagamento."


@pytest.fixture(scope="module")
def pg():
    with pg_efemero.subir() as url:
        pg_efemero.migrar(url)
        yield url


@pytest.fixture
def amb(pg, monkeypatch):
    with psycopg.connect(pg, autocommit=True) as c:
        c.execute("TRUNCATE licitacoes, importacoes RESTART IDENTITY CASCADE")
        linhas = [(1, "preparada", True, MACAE), (2, "preparada", True, CESSAO),
                  (3, "publicada", True, TARIFAS), (4, "fora_escopo", False, CESSAO),
                  (5, "preparada", True, None)]
        for n, estado, dentro, objeto in linhas:
            c.execute("INSERT INTO licitacoes (controle, estado, escopo_dentro, escopo_versao, orgao, uf,"
                      " municipio, modalidade, objeto, publicado_em) VALUES (%s, %s, %s, 'legado',"
                      " 'Prefeitura', 'SP', 'Teste', 'Dispensa', %s, '2026-09-01')",
                      ("12345678000101-1-%06d/2026" % n, estado, dentro, objeto))
    monkeypatch.setenv("DATABASE_URL", pg_efemero.url_papel(pg, "worker_rw"))
    monkeypatch.setenv("FOPA_WORKER_TOKEN", TOKEN)
    from api import worker
    return {"url": pg, "c": TestClient(worker.app)}


def _estado(url, n):
    with psycopg.connect(url) as c:
        return c.execute("SELECT estado::text, escopo_dentro, escopo_versao FROM licitacoes WHERE controle = %s",
                         ("12345678000101-1-%06d/2026" % n,)).fetchone()


def test_seco_so_conta_e_nao_muda_nada(amb):
    r = amb["c"].post("/escopo/reavaliar", headers=H, json={"seco": True}).json()
    assert r["seco"] is True and r["avaliadas"] == 5
    assert {m["controle"][-11:] for m in r["mudaram"]} == {"000001/2026", "000003/2026", "000004/2026"}
    assert _estado(amb["url"], 1) == ("preparada", True, "legado")


def test_reaplica_tira_da_fila_devolve_e_marca(amb):
    c, url = amb["c"], amb["url"]
    r = c.post("/escopo/reavaliar", headers=H, json={}).json()
    atual = r["escopo_versao"]
    assert _estado(url, 1) == ("fora_escopo", False, atual)       # consignado sai da fila paga
    assert _estado(url, 2) == ("preparada", True, atual)          # cessão fica, só ganha a versão
    assert _estado(url, 3) == ("publicada", False, atual)         # relatório existe: só a marca
    assert _estado(url, 4) == ("nova", True, atual)               # a regra voltou a aceitar
    assert _estado(url, 5) == ("preparada", True, "legado")       # sem objeto: não se julga o vazio
    assert r["resultado"] == {"fora_escopo": 1, "mesma_decisao": 1, "so_marcada": 1, "nova": 1,
                              "sem_objeto": 1}
    # idempotente: na segunda vez só sobra o que não tem objeto
    r2 = c.post("/escopo/reavaliar", headers=H, json={}).json()
    assert r2["avaliadas"] == 1 and r2["mudaram"] == []


def test_exige_token(amb):
    assert amb["c"].post("/escopo/reavaliar", json={}).status_code == 401
