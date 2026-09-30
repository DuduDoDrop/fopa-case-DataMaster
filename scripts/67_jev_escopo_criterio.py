# -*- coding: utf-8 -*-
"""
Qual critério do Jev acerta o escopo no acervo REAL da v3? — v2 (medido em 63_) × v3.

    python 67_jev_escopo_criterio.py [--n-neg 80] [--teto-usd 0.02]

O ACHADO QUE MOTIVA
  Ao pontuar as 1.162 licitações do recorte com o critério v2 (66_), 54
  "candidatas" em que a regra diz DENTRO e o Jev diz NÃO eram, quase todas,
  compra de folha de livro-texto ("Contratação de instituição bancária para
  operar os serviços de processamento e gerenciamento de créditos provenientes
  da folha de pagamento dos servidores") — Itatiba, Salto, Valinhos,
  Votorantim, São José dos Campos. O Jev dava 0,10-0,25. Como está, o site
  pintaria de âmbar oportunidade verdadeira.

GABARITO (sem chamar o Jev para escolhê-lo)
  positivos: as licitações PUBLICADAS (extraídas e revisadas como folha)
  negativos: as 20 que a leitura humana recusou (ADR-015) + N do corpus
             fora do escopo, sorteadas com semente fixa
  O v2 já está gravado em sinais_jev; só o v3 é chamado aqui.

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

REJEITADAS_HUMANAS = ("fora_escopo",)
CRITERIO_V3 = {
    "pergunta": (
        "This is the 'objeto' (subject) of a Brazilian public procurement notice, written in Portuguese. "
        "Is the public body contracting a bank or financial institution to RUN ITS PAYROLL — that is, to "
        "process, manage and pay the salary credits of its public servants ('processamento e gerenciamento "
        "de créditos provenientes da folha de pagamento', 'pagamento da folha', 'centralização da folha', "
        "'cessão onerosa do direito de processar a folha')? Judge what is being CONTRACTED, not words that "
        "are merely mentioned."),
    "sim": ("yes: a bank or financial institution will process, manage or pay the payroll credits of the "
            "servants, or buys the exclusive right to do so — even when other banking services (tax "
            "collection, supplier payments, payroll loans offered as an extra) are bundled in"),
    "nao": ("no: the contract is something else — a payroll loan product on its own (empréstimo consignado), "
            "payroll software or IT services, consulting or studies about the payroll, bank fees or file "
            "transfer services paid by the body, an institutional bank account, or unrelated goods/services"),
}


def _dsn() -> str:
    env = {}
    with io.open(os.path.join(RAIZ, "docker", ".env"), encoding="utf-8") as f:
        for l in f:
            if "=" in l and not l.lstrip().startswith("#"):
                k, _, v = l.strip().partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    return "postgresql://api_ro:%s@127.0.0.1:5433/fopa" % env["API_RO_PASSWORD"]


def _auc(pos, neg):
    pares = [(a, b) for a in pos for b in neg]
    return sum(1.0 if a > b else 0.5 if a == b else 0.0 for a, b in pares) / len(pares) if pares else None


def _resumo(pos, neg):
    return {"n_pos": len(pos), "n_neg": len(neg), "auc": round(_auc(pos, neg), 3),
            "pos_>=0.5": round(sum(p >= 0.5 for p in pos) / len(pos), 3),
            "neg_<0.5": round(sum(p < 0.5 for p in neg) / len(neg), 3),
            "pos_<=0.25 (falso 'não' convicto)": sum(p <= 0.25 for p in pos),
            "neg_>=0.75 (falso 'sim' convicto)": sum(p >= 0.75 for p in neg),
            "p_pos_mediana": round(statistics.median(pos), 3), "p_neg_mediana": round(statistics.median(neg), 3)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-neg", type=int, default=80)
    ap.add_argument("--semente", type=int, default=24092026)
    ap.add_argument("--teto-usd", type=float, default=0.02)
    a = ap.parse_args()
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    segredos.carregar()
    with psycopg.connect(_dsn()) as conn:
        conn.read_only = True
        v2 = "(SELECT s.p_sim FROM sinais_jev s WHERE s.controle = l.controle AND s.tipo = 'escopo' ORDER BY s.em DESC LIMIT 1)"
        pos = conn.execute("SELECT l.controle, l.objeto, %s FROM licitacoes l WHERE l.estado = 'publicada'"
                           " AND coalesce(l.objeto, '') <> ''" % v2).fetchall()
        humanas = conn.execute(
            "SELECT l.controle, l.objeto, %s FROM licitacoes l WHERE l.escopo_versao IS NOT NULL"
            " AND l.escopo_versao <> 'legado' AND NOT l.escopo_dentro AND l.origem = 'legado'"
            " AND coalesce(l.objeto, '') <> ''" % v2).fetchall()
        corpus = conn.execute(
            "SELECT l.controle, l.objeto, %s FROM licitacoes l WHERE l.estado = 'fora_escopo' AND l.origem = 'corpus'"
            " AND fn_no_recorte(l.fim_prazo, l.publicado_em) AND coalesce(l.objeto, '') <> ''"
            " ORDER BY l.controle" % v2).fetchall()
    rnd = random.Random(a.semente)
    neg = humanas + rnd.sample(corpus, min(a.n_neg, len(corpus)))
    itens = [(c, o, p2, 1) for c, o, p2 in pos] + [(c, o, p2, 0) for c, o, p2 in neg]
    print("positivos %d · negativos %d (humanas %d + corpus %d)" % (len(pos), len(neg), len(humanas), len(neg) - len(humanas)))

    gasto = {"usd": 0.0}
    q = {"escopo": jev.noul(CRITERIO_V3["pergunta"], CRITERIO_V3["sim"], CRITERIO_V3["nao"])}

    def um(x):
        c, o, p2, rot = x
        if gasto["usd"] >= a.teto_usd:
            return None
        for t in range(3):
            try:
                ans, uso = jev.perguntar(o, q)
                break
            except jev.ErroJev:
                if t == 2:
                    return None
                time.sleep(2)
        gasto["usd"] += uso["usd"]
        return {"controle": c, "rotulo": rot, "v2": float(p2) if p2 is not None else None,
                "v3": jev.valor(ans.get("escopo") or {}),
                "objeto": " ".join((o or "").split())[:200]}

    with ThreadPoolExecutor(6) as ex:
        res = [r for r in ex.map(um, itens) if r and r["v3"] is not None]
    comp = [r for r in res if r["v2"] is not None]
    out = {"v2": _resumo([r["v2"] for r in comp if r["rotulo"]], [r["v2"] for r in comp if not r["rotulo"]]),
           "v3": _resumo([r["v3"] for r in comp if r["rotulo"]], [r["v3"] for r in comp if not r["rotulo"]]),
           "n_comparados": len(comp), "usd": round(gasto["usd"], 5), "modelo": jev.MODELO, "criterio_v3": CRITERIO_V3}
    piores = sorted([r for r in res if r["rotulo"]], key=lambda r: r["v3"])[:5] + \
        sorted([r for r in res if not r["rotulo"]], key=lambda r: -r["v3"])[:5]
    out["piores_v3"] = piores
    os.makedirs(os.path.join(RAIZ, "docs", "medicoes"), exist_ok=True)
    arq = os.path.join(RAIZ, "docs", "medicoes", "jev_escopo_criterio_%s.json" % datetime.date.today().isoformat())
    with io.open(arq, "w", encoding="utf-8") as f:
        json.dump({"resumo": out, "itens": res}, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("v2", "v3", "n_comparados", "usd")}, ensure_ascii=False, indent=1))
    for r in piores:
        print("  rot=%d v2=%s v3=%.2f  %s" % (r["rotulo"], r["v2"], r["v3"], r["objeto"][:120]))
    print("gravado:", arq)
    return 0


if __name__ == "__main__":
    sys.exit(main())
