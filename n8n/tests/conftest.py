# -*- coding: utf-8 -*-
"""
Uma sessão de `n8n/tests` por vez na stack.

Dois pytest ao mesmo tempo (agentes, CI) disputavam o mesmo fopa-n8n e o mesmo
banco: a rodada do W01/W20 de um entrava nas contagens do outro, e a camada (b)
do CI falhou assim em 24/09. A trava é um advisory lock de SESSÃO no Postgres da
stack — vale entre processos diferentes e cai sozinha se o pytest morrer (a
conexão fecha). Quem chega depois espera, com um aviso, até FOPA_TRAVA_N8N_S
segundos (padrão 1800) e então falha dizendo por quê, em vez de rodar por cima.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cliente  # noqa: E402

CHAVE = 0x46_4F_50_41  # "FOPA": a mesma para toda sessão de n8n/tests


@pytest.fixture(scope="session", autouse=True)
def _uma_sessao_de_n8n_tests_por_vez():
    try:
        import psycopg
        env = cliente.ler_env()
        con = psycopg.connect("postgresql://postgres:%s@127.0.0.1:5433/fopa" % env["POSTGRES_PASSWORD"],
                              autocommit=True, connect_timeout=5)
    except Exception:  # noqa: BLE001 — sem stack os próprios testes pulam com o motivo
        yield
        return
    try:
        if not con.execute("SELECT pg_try_advisory_lock(%s)", (CHAVE,)).fetchone()[0]:
            espera = int(os.environ.get("FOPA_TRAVA_N8N_S", "1800"))
            print("\n[n8n/tests] outra sessão está rodando contra a stack; esperando até %d s pela trava" % espera,
                  file=sys.stderr)
            con.execute("SET lock_timeout = %s" % (espera * 1000))
            try:
                con.execute("SELECT pg_advisory_lock(%s)", (CHAVE,))
            except Exception as e:  # noqa: BLE001
                pytest.exit("n8n/tests: outra sessão segurou a trava por mais de %d s (%s)" % (espera, e),
                            returncode=3)
        yield
    finally:
        con.close()   # fecha a sessão: o advisory lock cai junto
