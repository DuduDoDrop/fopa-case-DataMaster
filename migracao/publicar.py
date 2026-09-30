# -*- coding: utf-8 -*-
"""
Passo 7 da migração (plano, seção 9): publicar o acervo importado.

Para cada licitação `verificada` com verificação vigente e sem publicação,
gera o RELATORIO pelo worker (`api.render`), grava `publicacoes` e leva a
licitação a `publicada` pela máquina de estados (a 013 exige verificação
vigente para isso). Uma licitação por transação: se o render de uma falhar,
ela fica `verificada` e as outras seguem — é o mesmo contrato do W24 ("render
falho não desfaz a verificação").

    python -m migracao.publicar            # DATABASE_URL e STORAGE_ROOT do ambiente
"""
from __future__ import annotations

import json
import os
import sys
import time

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from api import render  # noqa: E402
from api.storage import Storage  # noqa: E402


def publicar(conn: psycopg.Connection, storage) -> dict:
    conn.row_factory = dict_row
    alvos = conn.execute(
        "SELECT l.controle, v.id AS verificacao_id FROM licitacoes l"
        " JOIN verificacoes v ON v.controle = l.controle AND v.vigente"
        " WHERE l.estado = 'verificada'"
        "   AND NOT EXISTS (SELECT 1 FROM publicacoes p WHERE p.verificacao_id = v.id)"
        " ORDER BY l.controle").fetchall()
    conn.commit()
    feitas, falhas = 0, []
    for a in alvos:
        try:
            with conn.transaction():
                r = render.renderizar(conn, storage, a["verificacao_id"])
                conn.execute("INSERT INTO publicacoes (controle, verificacao_id, html_uri)"
                             " VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                             (a["controle"], a["verificacao_id"], r["html_uri"]))
                conn.execute("SELECT fn_transicao(%s, 'publicada', %s, %s)",
                             (a["controle"], "importação: RELATORIO publicado (passo 7)",
                              Jsonb({"html_uri": r["html_uri"], "sha256": r["sha256"]})))
            feitas += 1
        except Exception as e:                                        # noqa: BLE001
            falhas.append({"controle": a["controle"], "erro": "%s: %s" % (type(e).__name__, e)})
    return {"publicadas": feitas, "falhas": falhas}


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    url, raiz = os.environ.get("DATABASE_URL"), os.environ.get("STORAGE_ROOT")
    if not url or not raiz:
        print("faltam DATABASE_URL e STORAGE_ROOT", file=sys.stderr)
        return 2
    t0 = time.time()
    with psycopg.connect(url) as conn:
        r = publicar(conn, Storage(raiz))
    print("publicado em %.1fs: %s" % (time.time() - t0, json.dumps(r, ensure_ascii=False)[:2000]))
    return 1 if r["falhas"] else 0


if __name__ == "__main__":
    sys.exit(main())
