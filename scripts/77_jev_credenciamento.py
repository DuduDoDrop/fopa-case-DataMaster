# -*- coding: utf-8 -*-
"""
O ponto cego do CREDENCIAMENTO no escopo só-objeto — um ajuste MÍNIMO do critério v3 (v3.1), medido.

    python 77_jev_credenciamento.py [--teto-usd 0.05]

POR QUÊ (25/09/2026)
  As 5 discordâncias do painel eram todas credenciamento de banco para os créditos da folha (p = 0,27-0,45). No
  histórico, o filtro "apenas FOPA" (nota < 0,5) escondia credenciamentos legítimos com nota só-objeto 0,30-0,49.
  O v3 fala em "contracting" e em "buys the exclusive right"; credenciamento não é nenhum dos dois — o banco é
  CREDENCIADO (em geral sem exclusividade). Leitura literal (docs/jaggedness #1): falta dizer.

O AJUSTE (v3.1): "contracting" -> "contracting or accrediting ('credenciamento')" na pergunta, e "is accredited to do
so ('credenciamento')" no "sim". O "não" não muda. A reescrita grande (V4, 76_) derrubou folha legítima: aqui só
se acrescenta o caso que falta.

OS CONJUNTOS (A = v3 de produção e V31, cada um DUAS vezes — o Jev não tem cache e tem ruído)
  1. o gabarito da 73_ (124 folhas publicadas, 19 recusas humanas)
  2. os rótulos humanos (rotulos_escopo) — a validação separada
  3. os CREDENCIAMENTOS de folha do acervo que a regra aceitou (sem rótulo): quanto sobem, e se os de consignado
     (canal de consignações — recusa humana) sobem junto

Não escreve nada no banco. A medição vai para docs/medicoes/.
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

import psycopg                                                    # noqa: E402

from fopa import jev, segredos                                    # noqa: E402

_67 = __import__("67_jev_escopo_criterio")
_73 = __import__("73_jev_escopo_rag")
V3 = _67.CRITERIO_V3

V31 = {
    "pergunta": V3["pergunta"].replace("Is the public body contracting a bank",
                                       "Is the public body contracting or accrediting ('credenciamento') a bank"),
    "sim": V3["sim"].replace("process, manage or pay the payroll credits of the servants, or buys",
                             "process, manage or pay the payroll credits of the servants, is accredited to do so "
                             "('credenciamento'), or buys"),
    "nao": V3["nao"],
}
assert V31["pergunta"] != V3["pergunta"] and V31["sim"] != V3["sim"], "o texto do v3 mudou: refazer o ajuste"

BRACOS = {
    "A1": {"escopo": jev.noul(V3["pergunta"], V3["sim"], V3["nao"])},
    "A2": {"escopo": jev.noul(V3["pergunta"], V3["sim"], V3["nao"])},
    "C1": {"escopo": jev.noul(V31["pergunta"], V31["sim"], V31["nao"])},
    "C2": {"escopo": jev.noul(V31["pergunta"], V31["sim"], V31["nao"])},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-pos", type=int, default=120)
    ap.add_argument("--semente", type=int, default=24092026)
    ap.add_argument("--teto-usd", type=float, default=0.05)
    a = ap.parse_args()
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    segredos.carregar()
    with psycopg.connect(_67._dsn()) as conn:
        conn.read_only = True
        pos = conn.execute("SELECT l.controle, l.objeto FROM licitacoes l WHERE l.estado = 'publicada'"
                           " AND l.leitura_vigente_id IS NOT NULL AND coalesce(l.objeto, '') <> '' ORDER BY l.controle").fetchall()
        neg = conn.execute("SELECT l.controle, l.objeto FROM licitacoes l WHERE l.escopo_versao IS NOT NULL"
                           " AND l.escopo_versao <> 'legado' AND NOT l.escopo_dentro AND l.origem = 'legado'"
                           " AND l.leitura_vigente_id IS NOT NULL AND coalesce(l.objeto, '') <> ''").fetchall()
        disc = conn.execute("SELECT l.controle, l.objeto FROM licitacoes l WHERE l.controle = ANY(%s)"
                            " AND l.leitura_vigente_id IS NOT NULL", (list(_73.DISCORDANCIAS),)).fetchall()
        rnd = random.Random(a.semente)
        amostra = rnd.sample([p for p in pos if p[0] not in _73.DISCORDANCIAS], min(a.n_pos, len(pos)))
        g1 = [(c, o, 1) for c, o in disc + amostra] + [(c, o, 0) for c, o in neg]
        g2 = [tuple(r) for r in conn.execute(
            "SELECT r.controle, l.objeto, (r.veredito = 'dentro')::int FROM (SELECT DISTINCT ON (controle) controle, veredito"
            " FROM rotulos_escopo ORDER BY controle, em DESC, id DESC) r JOIN licitacoes l USING (controle)"
            " WHERE coalesce(l.objeto, '') <> ''").fetchall()]
        ja = {c for c, _, _ in g1 + g2}
        g3 = [(c, o, None) for c, o in conn.execute(
            "SELECT l.controle, l.objeto FROM licitacoes l WHERE fn_escopo_efetivo(l.controle, l.escopo_dentro)"
            " AND l.objeto ~* 'credenci' ORDER BY l.controle").fetchall() if c not in ja]
    print("gabarito 1: %d · gabarito 2: %d · credenciamentos sem rótulo: %d" % (len(g1), len(g2), len(g3)))

    gasto = {"usd": 0.0, "tok": 0}

    def perguntar(state, q):
        for t in range(3):
            try:
                ans, uso = jev.perguntar(state, q, timeout=120)
                gasto["usd"] += uso["usd"]
                gasto["tok"] += uso["input_tokens"]
                return jev.valor(ans.get("escopo") or {})
            except jev.ErroJev:
                if t == 2:
                    return None
                time.sleep(2)

    def um(x):
        c, o, rot = x
        if gasto["usd"] >= a.teto_usd:
            return None
        r = {"controle": c, "rotulo": rot, "objeto": " ".join((o or "").split())[:200]}
        for k, q in BRACOS.items():
            r[k] = perguntar(o, q)
            if r[k] is None:
                return None
        r["A"] = (r["A1"] + r["A2"]) / 2
        r["C"] = (r["C1"] + r["C2"]) / 2
        return r

    with ThreadPoolExecutor(6) as ex:
        r1 = [r for r in ex.map(um, g1) if r]
        r2 = [r for r in ex.map(um, g2) if r]
        r3 = [r for r in ex.map(um, g3) if r]

    def resumo(rs, k):
        return _67._resumo([r[k] for r in rs if r["rotulo"]], [r[k] for r in rs if not r["rotulo"]])

    def acertos(rs, k):
        return sum((r[k] >= 0.5) == bool(r["rotulo"]) for r in rs)

    consig = [r for r in r3 if "consigna" in r["objeto"].lower()]
    folha3 = [r for r in r3 if "consigna" not in r["objeto"].lower()]
    out = {
        "gabarito_1": {k: resumo(r1, k) for k in ("A1", "A2", "C1", "C2", "A", "C")},
        "gabarito_2": {k: resumo(r2, k) for k in ("A1", "A2", "C1", "C2", "A", "C")},
        "acertos_0.5": {k: {"g1": "%d/%d" % (acertos(r1, k), len(r1)), "g2": "%d/%d" % (acertos(r2, k), len(r2))}
                        for k in ("A1", "A2", "C1", "C2", "A", "C")},
        "credenciamentos": {
            "n_folha": len(folha3), "n_consignado": len(consig),
            "folha_mediana_A": round(statistics.median([r["A"] for r in folha3]), 3) if folha3 else None,
            "folha_mediana_C": round(statistics.median([r["C"] for r in folha3]), 3) if folha3 else None,
            "folha_<0,5_A": sum(r["A"] < 0.5 for r in folha3), "folha_<0,5_C": sum(r["C"] < 0.5 for r in folha3),
            "folha_<=0,25_A": sum(r["A"] <= 0.25 for r in folha3), "folha_<=0,25_C": sum(r["C"] <= 0.25 for r in folha3),
            "consignado_>=0,5_A": sum(r["A"] >= 0.5 for r in consig), "consignado_>=0,5_C": sum(r["C"] >= 0.5 for r in consig)},
        "ruido": {"A1xA2_mudou_de_lado": sum((r["A1"] >= 0.5) != (r["A2"] >= 0.5) for r in r1 + r2 + r3),
                  "C1xC2_mudou_de_lado": sum((r["C1"] >= 0.5) != (r["C2"] >= 0.5) for r in r1 + r2 + r3)},
        "n": [len(r1), len(r2), len(r3)], "usd": round(gasto["usd"], 5), "tokens": gasto["tok"], "modelo": jev.MODELO,
        "v31": V31}
    arq = os.path.join(RAIZ, "docs", "medicoes", "jev_credenciamento_%s.json" % datetime.date.today().isoformat())
    with io.open(arq, "w", encoding="utf-8") as f:
        json.dump({"resumo": out, "gabarito_1": r1, "gabarito_2": r2, "credenciamentos": r3}, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("acertos_0.5", "credenciamentos", "ruido", "n", "usd")}, ensure_ascii=False, indent=1))
    for g in ("gabarito_1", "gabarito_2"):
        print(g)
        for k in ("A1", "A2", "C1", "C2", "A", "C"):
            s = out[g][k]
            print("  %-2s auc %.3f · folha>=0,5 %.3f · recusa<0,5 %.3f · convictos errados %d/%d" % (
                k, s["auc"], s["pos_>=0.5"], s["neg_<0.5"], s["pos_<=0.25 (falso 'não' convicto)"],
                s["neg_>=0.75 (falso 'sim' convicto)"]))
    print("gravado:", arq)
    return 0


if __name__ == "__main__":
    sys.exit(main())
