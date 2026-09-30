# -*- coding: utf-8 -*-
"""
O v3.1 (credenciamento, 77_) também na nota COM O EDITAL? E a média que a tela e a trava usam.

    python 78_jev_credenciamento_edital.py [--teto-usd 0.08]

O 77_ mediu o v3.1 só com o objeto e ele entrou em produção (api/jev.py). A nota com o edital (73_: objeto + páginas
da leitura) ainda pergunta com o v3. Aqui, nos MESMOS itens do gabarito da 73_ (124 folhas publicadas com leitura,
19 recusas humanas), numa rodada só:
  O31  só objeto, v3.1 (o que está no ar)
  R3   objeto + edital, v3 (o que está no ar)
  R31  objeto + edital, v3.1
e as médias O31+R3 (o que a tela mostra hoje) e O31+R31.

Não escreve nada no banco. A medição vai para docs/medicoes/.
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import random
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
_77 = __import__("77_jev_credenciamento")
V3, V31 = _67.CRITERIO_V3, _77.V31
SUFIXO_RAG = _73.PERGUNTA_RAG[len(V3["pergunta"]):]
assert _73.PERGUNTA_RAG == V3["pergunta"] + SUFIXO_RAG

Q_O31 = {"escopo": jev.noul(V31["pergunta"], V31["sim"], V31["nao"])}
Q_R3 = {"escopo": jev.noul(_73.PERGUNTA_RAG, V3["sim"], V3["nao"])}
Q_R31 = {"escopo": jev.noul(V31["pergunta"] + SUFIXO_RAG, V31["sim"], V31["nao"])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-pos", type=int, default=120)
    ap.add_argument("--semente", type=int, default=24092026)
    ap.add_argument("--teto-usd", type=float, default=0.08)
    a = ap.parse_args()
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    segredos.carregar()
    with psycopg.connect(_67._dsn()) as conn:
        conn.read_only = True
        pos = conn.execute("SELECT l.controle, l.objeto, l.leitura_vigente_id FROM licitacoes l WHERE l.estado = 'publicada'"
                           " AND l.leitura_vigente_id IS NOT NULL AND coalesce(l.objeto, '') <> '' ORDER BY l.controle").fetchall()
        neg = conn.execute("SELECT l.controle, l.objeto, l.leitura_vigente_id FROM licitacoes l WHERE l.escopo_versao IS NOT NULL"
                           " AND l.escopo_versao <> 'legado' AND NOT l.escopo_dentro AND l.origem = 'legado'"
                           " AND l.leitura_vigente_id IS NOT NULL AND coalesce(l.objeto, '') <> ''").fetchall()
        disc = conn.execute("SELECT l.controle, l.objeto, l.leitura_vigente_id FROM licitacoes l WHERE l.controle = ANY(%s)"
                            " AND l.leitura_vigente_id IS NOT NULL", (list(_73.DISCORDANCIAS),)).fetchall()
        rnd = random.Random(a.semente)
        amostra = rnd.sample([p for p in pos if p[0] not in _73.DISCORDANCIAS], min(a.n_pos, len(pos)))
        itens = [(c, o, lid, 1) for c, o, lid in disc + amostra] + [(c, o, lid, 0) for c, o, lid in neg]
        paginas = {}
        for c, o, lid, _ in itens:
            paginas[c] = [(r[0], r[1], r[2]) for r in conn.execute(
                "SELECT arquivo_nome, numero, texto FROM paginas WHERE leitura_id = %s ORDER BY arquivo_nome, numero",
                (lid,)).fetchall()]
    print("gabarito: %d folhas · %d recusas" % (sum(1 for i in itens if i[3]), sum(1 for i in itens if not i[3])))

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
        c, o, lid, rot = x
        if gasto["usd"] >= a.teto_usd:
            return None
        trechos = _73.rag(paginas.get(c) or [])
        estado = json.dumps({"objeto": o, "trechos_do_edital": trechos}, ensure_ascii=False)   # como em produção
        r = {"controle": c, "rotulo": rot, "objeto": " ".join((o or "").split())[:160],
             "O31": perguntar(o, Q_O31), "R3": perguntar(estado, Q_R3), "R31": perguntar(estado, Q_R31)}
        if None in (r["O31"], r["R3"], r["R31"]):
            return None
        r["O31+R3"] = (r["O31"] + r["R3"]) / 2
        r["O31+R31"] = (r["O31"] + r["R31"]) / 2
        return r

    with ThreadPoolExecutor(6) as ex:
        res = [r for r in ex.map(um, itens) if r]
    chaves = ("O31", "R3", "R31", "O31+R3", "O31+R31")
    out = {k: _67._resumo([r[k] for r in res if r["rotulo"]], [r[k] for r in res if not r["rotulo"]]) for k in chaves}
    out["acertos_0.5"] = {k: "%d/%d" % (sum((r[k] >= 0.5) == bool(r["rotulo"]) for r in res), len(res)) for k in chaves}
    out.update({"n": len(res), "usd": round(gasto["usd"], 5), "tokens": gasto["tok"], "modelo": jev.MODELO})
    arq = os.path.join(RAIZ, "docs", "medicoes", "jev_credenciamento_edital_%s.json" % datetime.date.today().isoformat())
    with io.open(arq, "w", encoding="utf-8") as f:
        json.dump({"resumo": out, "itens": res}, f, ensure_ascii=False, indent=1)
    print(json.dumps({"acertos_0.5": out["acertos_0.5"], "n": out["n"], "usd": out["usd"]}, ensure_ascii=False, indent=1))
    for k in chaves:
        s = out[k]
        print("  %-8s auc %.3f · folha>=0,5 %.3f · recusa<0,5 %.3f · convictos errados %d/%d" % (
            k, s["auc"], s["pos_>=0.5"], s["neg_<0.5"], s["pos_<=0.25 (falso 'não' convicto)"],
            s["neg_>=0.75 (falso 'sim' convicto)"]))
    print("gravado:", arq)
    return 0


if __name__ == "__main__":
    sys.exit(main())
