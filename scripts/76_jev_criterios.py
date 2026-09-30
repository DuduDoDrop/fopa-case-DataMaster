# -*- coding: utf-8 -*-
"""
Rodada 2 da configuração do Jev (75_): a REDAÇÃO do critério — "a maior alavanca" segundo as auditorias
independentes (70% -> 96%, 83% -> 100% só reescrevendo critérios) — e o que a documentação manda testar.

    python 76_jev_criterios.py [--teto-usd 0.06]

OS BRAÇOS (só o objeto, os mesmos itens; o Jev não tem cache, então A roda DUAS vezes para medir o ruído)
  A1, A2  v3 de produção (string; pergunta + critérios)
  G       v3 SEM critérios — docs/primitives/noul: "try your questions with and without criteria and keep
          whichever gives better answers on your documents"
  H       v3 com critérios ESTRUTURADOS (objeto: o que é / o que inclui) — docs/primitives/advanced
  V4      critério reescrito para os erros que sobraram na 75_ (leitura literal, docs/jaggedness #1): a DIREÇÃO do
          dinheiro (o órgão só PAGA tarifa ao banco = não), envio/retorno de arquivos, "cessão" de SISTEMA de folha
          (licença de software = não), processamento de folha por empresa que não é banco

GABARITOS (os da 75_)
  1. publicadas com leitura (+5 discordâncias) × 19 recusas humanas — o V4 foi escrito OLHANDO os erros daqui
  2. os rótulos humanos (rotulos_escopo) — o conjunto separado: é aqui que o V4 precisa se sustentar

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
V3 = _67.CRITERIO_V3

H_SIM = {
    "meaning": "A bank or financial institution will run the payroll of the public body's servants.",
    "includes": ["processing, managing or paying the payroll credits of the servants",
                 "buying or receiving the exclusive right to do so ('cessão onerosa', 'credenciamento')",
                 "the same contract bundling other banking services such as tax collection, supplier payments or "
                 "payroll-deductible loans"],
}
H_NAO = {
    "meaning": "The contract is something else.",
    "includes": ["a payroll-deductible loan product on its own ('empréstimo consignado')",
                 "payroll software or IT services", "consulting or studies about the payroll",
                 "bank fees or file transfer services paid by the body", "an institutional bank account",
                 "unrelated goods or services"],
}

V4 = {
    "pergunta": (
        "This is the 'objeto' (subject) of a Brazilian public procurement notice, written in Portuguese. Is the public "
        "body contracting, accrediting or selling to a bank or financial institution the service of paying its "
        "servants' salaries — processing, managing, centralizing or crediting the payroll ('folha de pagamento') into "
        "the servants' accounts — or the exclusive right to do so? Judge what is being CONTRACTED, not words that are "
        "merely mentioned."),
    "sim": (
        "yes: a bank or financial institution will process, manage, centralize or pay the payroll credits of the "
        "servants, retirees or pensioners, or buys, receives or is accredited for the right to do so ('cessão "
        "onerosa', 'exclusividade', 'credenciamento') — even when other banking services (tax collection, supplier "
        "payments, payroll-deductible loans) are bundled in"),
    "nao": (
        "no: the contract is something else — the public body only pays bank fees or tariffs ('tarifas bancárias') "
        "or file transmission services ('envio/retorno de arquivos'); payroll software or a payroll system, including "
        "the licensing ('cessão') of a system; payroll calculation, HR outsourcing or consulting by a company that is "
        "not a bank; only the channel for payroll-deductible loans ('consignações'); an institutional bank account or "
        "investments; training, events or unrelated goods and services"),
}

BRACOS = {
    "A1": {"escopo": jev.noul(V3["pergunta"], V3["sim"], V3["nao"])},
    "A2": {"escopo": jev.noul(V3["pergunta"], V3["sim"], V3["nao"])},
    "G": {"escopo": {"type": "noul", "instructions": V3["pergunta"]}},
    "H": {"escopo": {"type": "noul", "instructions": V3["pergunta"], "criteria": {"true": H_SIM, "false": H_NAO}}},
    "V4": {"escopo": jev.noul(V4["pergunta"], V4["sim"], V4["nao"])},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-pos", type=int, default=120)
    ap.add_argument("--semente", type=int, default=24092026)
    ap.add_argument("--teto-usd", type=float, default=0.06)
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
    print("gabarito 1: %d · gabarito 2: %d" % (len(g1), len(g2)))

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
        return r

    with ThreadPoolExecutor(6) as ex:
        r1 = [r for r in ex.map(um, g1) if r]
        r2 = [r for r in ex.map(um, g2) if r]

    def resumo(rs, k):
        return _67._resumo([r[k] for r in rs if r["rotulo"]], [r[k] for r in rs if not r["rotulo"]])

    def acertos(rs, k):
        return sum((r[k] >= 0.5) == bool(r["rotulo"]) for r in rs)

    out = {"gabarito_1": {k: resumo(r1, k) for k in BRACOS}, "gabarito_2": {k: resumo(r2, k) for k in BRACOS},
           "acertos_0.5": {k: {"g1": "%d/%d" % (acertos(r1, k), len(r1)), "g2": "%d/%d" % (acertos(r2, k), len(r2))}
                           for k in BRACOS},
           "ruido_A1_A2": {"media": round(sum(abs(r["A1"] - r["A2"]) for r in r1 + r2) / len(r1 + r2), 4),
                           "max": round(max(abs(r["A1"] - r["A2"]) for r in r1 + r2), 3),
                           "mudou_de_lado": sum((r["A1"] >= 0.5) != (r["A2"] >= 0.5) for r in r1 + r2)},
           "n_1": len(r1), "n_2": len(r2), "usd": round(gasto["usd"], 5), "tokens": gasto["tok"], "modelo": jev.MODELO,
           "v4": V4, "h": {"true": H_SIM, "false": H_NAO}}
    arq = os.path.join(RAIZ, "docs", "medicoes", "jev_criterios_%s.json" % datetime.date.today().isoformat())
    with io.open(arq, "w", encoding="utf-8") as f:
        json.dump({"resumo": out, "gabarito_1": r1, "gabarito_2": r2}, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("acertos_0.5", "ruido_A1_A2", "n_1", "n_2", "usd", "tokens")},
                     ensure_ascii=False, indent=1))
    for g in ("gabarito_1", "gabarito_2"):
        print(g)
        for k in BRACOS:
            s = out[g][k]
            print("  %-3s auc %.3f · folha>=0,5 %.3f · recusa<0,5 %.3f · convictos errados %d/%d" % (
                k, s["auc"], s["pos_>=0.5"], s["neg_<0.5"], s["pos_<=0.25 (falso 'não' convicto)"],
                s["neg_>=0.75 (falso 'sim' convicto)"]))
    print("gravado:", arq)
    return 0


if __name__ == "__main__":
    sys.exit(main())
