# -*- coding: utf-8 -*-
"""
A progressão de retentativa que o item 11.7 do plano pede: 15 min → 2 h → 12 h, e a 4ª falha
vira `erro_definitivo` sem próxima tentativa (db/021, `fn_registrar_falha` + `fn_backoff`).

Até aqui só o 1º degrau (15 min) tinha prova — `n8n/tests/test_w10_w11.py` e o ramo de erro do
W20 em `test_nucleo.py`. Os outros três existiam só no SQL, e é deles que depende a fila não
martelar o PNCP nem desistir cedo demais de uma licitação que só pegou uma rede ruim.

Postgres efêmero migrado; cada teste roda numa transação que volta atrás. Dentro dela `now()` é
o instante da transação, então `proxima_tentativa_em - now()` é o próprio backoff, sem folga.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from tests import pg_efemero  # noqa: E402

C = "00000000000000-1-000901/2026"


@pytest.fixture(scope="module")
def url():
    with pg_efemero.subir() as u:
        pg_efemero.migrar(u)
        yield u


@pytest.fixture
def cur(url):
    with psycopg.connect(url, row_factory=dict_row) as conn:
        conn.execute(
            "INSERT INTO licitacoes (controle, orgao, uf, municipio, modalidade, objeto, publicado_em,"
            " escopo_dentro, escopo_motivo, estado, ensaio, origem)"
            " VALUES (%s, 'TESTE backoff', 'SC', 'Teste', 'Pregão', 'folha de pagamento', '2026-09-01',"
            " true, 'teste', 'nova', true, 'manual')", (C,))
        yield conn
        conn.rollback()


def _tentar_e_falhar(cur, cega: bool = False) -> tuple[str, dict]:
    """Uma volta da fila: o W21 pega (→ baixando, com lease) e a rede falha."""
    cur.execute("SELECT fn_transicao(%s, 'baixando', 'teste: nova tentativa')", (C,))
    cur.execute("UPDATE licitacoes SET lease_por = 'W20:teste', lease_ate = now() + interval '2 hours'"
                " WHERE controle = %s", (C,))
    r = cur.execute("SELECT fn_registrar_falha(%s, 'falha_rede', 'teste: rede caiu', %s) AS r",
                    (C, cega)).fetchone()["r"]
    lic = cur.execute("SELECT estado::text AS estado, tentativas, lease_por, lease_ate,"
                      " proxima_tentativa_em - now() AS atraso FROM licitacoes WHERE controle = %s",
                      (C,)).fetchone()
    return r, lic


def test_progressao_15min_2h_12h_e_a_quarta_falha_e_definitiva(cur):
    esperado = [timedelta(minutes=15), timedelta(hours=2), timedelta(hours=12)]
    for n, atraso in enumerate(esperado, start=1):
        r, lic = _tentar_e_falhar(cur)
        assert r == "falha_rede", (n, r)
        assert (lic["estado"], lic["tentativas"]) == ("falha_rede", n)
        assert lic["atraso"] == atraso, "falha %d: backoff %s, esperado %s" % (n, lic["atraso"], atraso)
        assert lic["lease_por"] is None and lic["lease_ate"] is None, "o lease volta em toda falha"

    r, lic = _tentar_e_falhar(cur)
    assert r == "erro_definitivo"
    assert (lic["estado"], lic["tentativas"], lic["atraso"]) == ("erro_definitivo", 4, None)
    eventos = [e["para"] for e in cur.execute(
        "SELECT para::text AS para FROM licitacao_eventos WHERE controle = %s ORDER BY id", (C,)).fetchall()]
    assert eventos[-2:] == ["falha_rede", "erro_definitivo"], eventos


def test_falha_cega_nao_gasta_tentativa_mas_espera(cur):
    """PNCP fora (execução cega) não é culpa da licitação: não conta, mas também não martela."""
    r, lic = _tentar_e_falhar(cur, cega=True)
    assert r == "falha_rede"
    assert (lic["tentativas"], lic["atraso"], lic["lease_por"]) == (0, timedelta(minutes=15), None)
