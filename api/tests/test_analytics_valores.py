# -*- coding: utf-8 -*-
"""
O dado do PNCP que não fechava no analytics (BACKLOG 4.4, resolvido em 28/09/2026):

  · HOMOLOGADO SIMBÓLICO: o banco homologa R$ 0,60 e assina um contrato de R$ 75 mi (Bradesco, 01468760…).
    Com contrato dele, vale o contrato; sem, fica o simbólico, marcado; o contrato de OUTRO banco não conta.
  · COMPRA CADASTRADA DUAS VEZES: mesmo órgão, mesmo banco, mesmo valor, e publicação a até 7 dias ou
    homologação no mesmo dia — conta uma vez. Mesmo valor com dois meses e homologações diferentes, ou valor
    diferente na mesma semana, são duas compras.

Postgres efêmero próprio: o cenário do `test_analytics.py` fica intacto.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from api import analytics  # noqa: E402
from api.tests.test_analytics import _compra, _item, _lic, _res  # noqa: E402
from tests import pg_efemero  # noqa: E402

BRADESCO, ITAU, CAIXA = "60746948000112", "60701190000104", "00360305000104"
SIMB_CONTRATO = "01468760000190-1-000010/2025"        # R$ 0,60 homologado, contrato de R$ 75 mi
SIMB_SEM = "83831719000100-1-000020/2026"             # R$ 0,01 e nenhum contrato
SIMB_OUTRO = "50290931000140-1-000010/2025"           # R$ 0,60; o contrato é de outro banco
DUP_A, DUP_B = "45781176000166-1-001092/2025", "45781176000166-1-001096/2025"    # mesmo dia
LONGE_A, LONGE_B = "46634440000100-1-000397/2025", "46634440000100-1-000003/2026"  # 2 meses, mesma homologação
REPETE_A, REPETE_B = "17702515000136-1-000137/2025", "17702515000136-1-000153/2025"  # 2 meses, homologações ≠
SEMANA_A, SEMANA_B = "88414552000197-1-000101/2024", "88414552000197-1-000102/2024"  # mesma semana, valor ≠
TODAS = (SIMB_CONTRATO, SIMB_SEM, SIMB_OUTRO, DUP_A, DUP_B, LONGE_A, LONGE_B, REPETE_A, REPETE_B, SEMANA_A, SEMANA_B)


def _contrato(c, controle, compra, ni, valor):
    c.execute("INSERT INTO pncp_contratos (controle, controle_compra, payload, ni_fornecedor, valor_global,"
              " assinado_em, escopo_dentro) VALUES (%s, %s, '{}', %s, %s, '2026-01-10', true)",
              (controle, compra, ni, valor))


def _comprada(c, controle, publicado, ni, nome, valor, dia):
    _compra(c, controle, publicado, valor or 1000)
    _item(c, controle, 1, "Homologado", tem=True)
    _res(c, controle, 1, ni, nome, valor, dia)


@pytest.fixture(scope="module")
def url():
    with pg_efemero.subir() as u:
        pg_efemero.migrar(u)
        with psycopg.connect(u) as c:
            for x in TODAS:
                _lic(c, x)
            _comprada(c, SIMB_CONTRATO, "2025-03-01T10:00:00-03:00", BRADESCO, "BANCO BRADESCO S.A.", 0.60,
                      date(2025, 4, 1))
            _contrato(c, "01468760000190-2-000001/2025", SIMB_CONTRATO, "60746948000199", 75_000_000)  # outra filial
            _comprada(c, SIMB_SEM, "2026-02-01T10:00:00-03:00", CAIXA, "CAIXA ECONOMICA FEDERAL", 0.01,
                      date(2026, 3, 1))
            _comprada(c, SIMB_OUTRO, "2025-05-01T10:00:00-03:00", BRADESCO, "BANCO BRADESCO S.A.", 0.60,
                      date(2025, 6, 1))
            _contrato(c, "50290931000140-2-000001/2025", SIMB_OUTRO, ITAU, 9_000_000)
            _comprada(c, DUP_A, "2025-10-15T09:00:00-03:00", CAIXA, "CAIXA ECONOMICA FEDERAL", 14_800_000,
                      date(2025, 11, 3))
            _comprada(c, DUP_B, "2025-10-15T15:00:00-03:00", CAIXA, "CAIXA ECONOMICA FEDERAL", 14_800_000,
                      date(2025, 10, 30))
            _comprada(c, LONGE_A, "2026-01-15T10:00:00-03:00", CAIXA, "CAIXA ECONOMICA FEDERAL", 10_658_739.83,
                      date(2026, 2, 25))
            _comprada(c, LONGE_B, "2026-03-16T10:00:00-03:00", CAIXA, "CAIXA ECONOMICA FEDERAL", 10_658_739.83,
                      date(2026, 2, 25))
            _comprada(c, REPETE_A, "2025-09-07T10:00:00-03:00", ITAU, "ITAU UNIBANCO S.A.", 20_000,
                      date(2025, 9, 27))
            _comprada(c, REPETE_B, "2025-11-07T10:00:00-03:00", ITAU, "ITAU UNIBANCO S.A.", 20_000,
                      date(2025, 11, 27))
            _comprada(c, SEMANA_A, "2024-02-09T10:00:00-03:00", ITAU, "ITAU UNIBANCO S.A.", 1_700_000,
                      date(2024, 3, 5))
            _comprada(c, SEMANA_B, "2024-02-12T10:00:00-03:00", ITAU, "ITAU UNIBANCO S.A.", 1_900_000,
                      date(2024, 3, 6))
        yield u


def _montar(url):
    with psycopg.connect(url) as conn:
        return analytics.montar(conn)


def _compras(url, banco):
    with psycopg.connect(url) as conn:
        return {c["controle"]: c for c in analytics.compras_por_banco(conn, banco=banco)["compras"]}


def test_homologado_simbolico_vale_o_contrato_do_mesmo_banco(url):
    compras = _compras(url, BRADESCO)
    assert (compras[SIMB_CONTRATO]["valor"], compras[SIMB_CONTRATO]["fonte_valor"]) == (75_000_000.0, "contrato")
    # o contrato de R$ 9 mi é do Itaú: o R$ 0,60 do Bradesco fica, marcado como simbólico
    assert (compras[SIMB_OUTRO]["valor"], compras[SIMB_OUTRO]["fonte_valor"]) == (0.6, "simbolico")
    bancos = {b["cnpj_raiz"]: b for b in _montar(url)["bancos"]}
    assert bancos["60746948"]["valor_total"] == 75_000_000.6


def test_simbolico_sem_contrato_fica_marcado_e_o_resumo_conta(url):
    assert _compras(url, CAIXA)[SIMB_SEM]["fonte_valor"] == "simbolico"
    r = _montar(url)["resumo"]
    assert (r["pelo_contrato"], r["simbolicas"]) == (1, 2)


def test_compra_cadastrada_duas_vezes_conta_uma(url):
    caixa = _compras(url, CAIXA)
    assert DUP_A in caixa and DUP_B not in caixa                  # mesmo dia: fica a publicada primeiro
    assert LONGE_A in caixa and LONGE_B not in caixa              # 2 meses, mas a mesma homologação
    bancos = {b["cnpj_raiz"]: b for b in _montar(url)["bancos"]}
    assert bancos["00360305"]["licitacoes"] == 3                  # DUP_A, LONGE_A e o simbólico
    assert bancos["00360305"]["valor_total"] == round(14_800_000 + 10_658_739.83 + 0.01, 2)


def test_o_que_nao_e_duplicata_continua_duas_compras(url):
    itau = _compras(url, ITAU)
    assert {REPETE_A, REPETE_B, SEMANA_A, SEMANA_B} <= set(itau)  # 2 meses e homologações ≠; valor ≠ na semana
    r = _montar(url)["resumo"]
    assert r["duplicadas"] == 2
    assert r["compras"] == len(TODAS) - 2
