# -*- coding: utf-8 -*-
"""
db/026: o RAG de produção passa a levar 12 páginas por pergunta.

ADR-010: k=12 teve 100% de recall em todas as medições; k=6 só chegou a 100% depois dos termos
novos de 23/09, numa amostra única. A página que o RAG perde vira "Não localizado" — que desde a
política da v3 vai para REVISAR. A migração troca só a semente: valor editado pelo admin fica.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from tests import pg_efemero  # noqa: E402

MIGRACAO = RAIZ / "db" / "026_k_rag_12.sql"


@pytest.fixture(scope="module")
def url():
    with pg_efemero.subir() as u:
        pg_efemero.migrar(u)
        yield u


def _k_rag(conn):
    return conn.execute("SELECT valor, alterado_por FROM configuracao WHERE chave = 'k_rag'").fetchone()


def test_banco_migrado_leva_12_paginas_por_pergunta(url):
    with psycopg.connect(url) as conn:
        valor, por = _k_rag(conn)
    assert valor == 12
    assert "026" in por


def test_valor_editado_a_mao_nao_e_atropelado(url):
    with psycopg.connect(url) as conn:
        conn.execute("UPDATE configuracao SET valor = '8', alterado_por = 'admin@teste' WHERE chave = 'k_rag'")
        conn.execute(MIGRACAO.read_text(encoding="utf-8"))
        assert _k_rag(conn) == (8, "admin@teste")
        conn.rollback()
