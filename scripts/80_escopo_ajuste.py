# -*- coding: utf-8 -*-
"""
Mede a camada de ajuste do escopo (api/escopo_ajuste.py) no acervo — sem custo, sem escrever nada.

    python 80_escopo_ajuste.py [--listar 40]

O QUE TEM DE VALER
  1. NUNCA tirar o que é folha comprovada: licitação extraída/publicada, rótulo humano "dentro", as 5 discordâncias
     do painel (credenciamentos). Qualquer uma aqui é defeito da camada.
  2. Pegar os casos conhecidos: os rótulos humanos "fora" em que a regra dizia dentro, e os que o Jev (v3.1) recusa
     com convicção.
  3. O resto que ela tira, por exclusão, com a nota do Jev ao lado — nota alta no que sai é sinal de erro.
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import os
import statistics
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

from api import escopo_ajuste                                     # noqa: E402

_67 = __import__("67_jev_escopo_criterio")
_73 = __import__("73_jev_escopo_rag")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listar", type=int, default=40)
    a = ap.parse_args()
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    with psycopg.connect(_67._dsn(), row_factory=dict_row) as conn:
        conn.read_only = True
        linhas = conn.execute(
            "SELECT l.controle, l.objeto, l.estado::text AS estado, l.escopo_motivo,"
            " (SELECT r.veredito FROM rotulos_escopo r WHERE r.controle = l.controle ORDER BY r.em DESC, r.id DESC LIMIT 1)"
            "   AS rotulo,"
            " fn_ia_p_folha(l.controle) AS p,"
            " EXISTS (SELECT 1 FROM execucoes_modelo e WHERE e.controle = l.controle) AS extraida"
            " FROM licitacoes l WHERE l.escopo_dentro AND coalesce(l.objeto, '') <> ''").fetchall()
    print("a regra aceita %d licitações com objeto" % len(linhas))
    saem = []
    for x in linhas:
        dentro, motivo = escopo_ajuste.ajustar(x["objeto"], True, x["escopo_motivo"] or "")
        if not dentro:
            x["exclusao"] = escopo_ajuste.excluir(x["objeto"])
            saem.append(x)
    protegidas = [x for x in saem if x["extraida"] or x["rotulo"] == "dentro" or x["controle"] in _73.DISCORDANCIAS
                  or x["estado"] in ("publicada", "verificada", "respondida")]
    fora_humano = [x for x in linhas if x["rotulo"] == "fora"]
    jev_nao = [x for x in linhas if x["rotulo"] is None and x["p"] is not None and float(x["p"]) <= 0.25]
    ids_saem = {x["controle"] for x in saem}
    por = collections.Counter(x["exclusao"] for x in saem)
    ps = [float(x["p"]) for x in saem if x["p"] is not None]
    altas = sorted([x for x in saem if x["p"] is not None and float(x["p"]) >= 0.5], key=lambda x: -float(x["p"]))
    out = {
        "aceitas_pela_regra": len(linhas), "saem": len(saem),
        "DEFEITO_folha_comprovada_que_sairia": [(x["controle"], x["estado"], x["exclusao"], x["objeto"][:120]) for x in protegidas],
        "rotulos_fora_pegos": "%d/%d" % (sum(x["controle"] in ids_saem for x in fora_humano), len(fora_humano)),
        "jev_convicto_pegos": "%d/%d" % (sum(x["controle"] in ids_saem for x in jev_nao), len(jev_nao)),
        "por_exclusao": dict(por.most_common()),
        "jev_nas_que_saem": {"com_nota": len(ps), "mediana": round(statistics.median(ps), 3) if ps else None,
                             ">=0,5": len(altas)},
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("== as que saem com nota do Jev >= 0,5 (revisar):")
    for x in altas[:a.listar]:
        print("  %.2f %-28s %-22s | %s" % (float(x["p"]), x["exclusao"], x["estado"], " ".join(x["objeto"].split())[:130]))
    print("== rótulos 'fora' que a camada NÃO pega:")
    for x in fora_humano:
        if x["controle"] not in ids_saem:
            print("  %s | %s" % (x["controle"], " ".join(x["objeto"].split())[:130]))
    print("== Jev convicto que a camada NÃO pega:")
    for x in jev_nao:
        if x["controle"] not in ids_saem:
            print("  %.2f | %s" % (float(x["p"]), " ".join(x["objeto"].split())[:130]))
    return 1 if protegidas else 0


if __name__ == "__main__":
    sys.exit(main())
