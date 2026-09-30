# -*- coding: utf-8 -*-
"""
O Jev está bem configurado? — o que a documentação da TypeSafe e as auditorias independentes mandam, medido.

    python 75_jev_configuracao.py [--teto-usd 0.15]

O PEDIDO: revisar a configuração do Jev contra o paper, as skills e os plugins dele — depois de a capa do edital
(1ª página) não mudar nada.

O QUE A DOCUMENTAÇÃO DIZ E O PROJETO NÃO FAZIA (docs.typesafe.ai, lidos em 25/09)
  1. `state` estruturado é um OBJETO JSON ("Use an object for most requests"; a pergunta aponta os campos por
     caminho entre crases). O objeto+edital e o "sustenta?" mandavam `json.dumps(...)` — uma STRING com JSON
     dentro, aspas escapadas e quebras de linha como texto.
  2. "Large state full of irrelevant detail": acurácia cai com contexto que não é da pergunta ("context rot").
     O RAG manda ~12 mil caracteres de páginas escolhidas por termo.
  3. "Decompose the questions ... probably the most important concept in this guide": perguntas atômicas,
     combinadas no código. O v3 junta numa pergunta só: é banco? é pagar salário? não é consignado? não é
     software? (auditoria de phishing da comunidade: 62,6% numa pergunta, 95,0% em cinco).

OS BRAÇOS (os mesmos itens em todos)
  A  produção, só objeto (string, v3)          D  objeto+edital OBJETO com metade do teto (6 mil)
  B  produção, objeto+edital STRING            E  só objeto como OBJETO {"objeto": ...} (v3)
  C  objeto+edital como OBJETO (mesmas págs)   F  DECOMPOSTO: 5 Nouls atômicos numa chamada; regra no código

GABARITOS
  1. o da 73_ (mesma semente): publicadas com leitura (+ as 5 discordâncias) × as 19 recusas humanas (ADR-015)
  2. os rótulos humanos de escopo (rotulos_escopo): só objeto — A, E e F

Não escreve nada no banco. A medição vai para docs/medicoes/.
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import math
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

PERGUNTA_E = ("`objeto` is the subject of a Brazilian public procurement notice, written in Portuguese. "
              + V3["pergunta"].split("written in Portuguese. ", 1)[1])

# F — uma condição por pergunta, "sim" = valor alto, o campo citado por caminho (docs: primitives/noul, jaggedness).
DECOMPOSTO = {
    "banco": jev.noul(
        "Is the party being contracted, accredited or chosen in `objeto` a bank or other financial institution?",
        "A bank, a financial institution, or an institution authorized by the Central Bank of Brazil is the party "
        "being contracted, accredited or chosen.",
        "The party is a software company, a consultancy, an HR or payroll-calculation company, an event organizer, a "
        "nonprofit or another non-bank provider, or `objeto` does not say who provides the service."),
    "paga_salarios": jev.noul(
        "Does the service in `objeto` include paying or crediting the salaries of the public body's servants into "
        "their bank accounts?",
        "Paying, crediting, centralizing or managing the payroll credits of servants, retirees or pensioners "
        "('créditos da folha de pagamento', 'pagamento da folha', 'centralização da folha').",
        "The payroll is only mentioned: calculating or preparing the payroll, payroll software, payroll-deductible "
        "loans, training or events about the payroll, or a service that does not pay salaries."),
    "direito_folha": jev.noul(
        "Does `objeto` sell, grant or accredit the right to process, centralize or manage the payroll of the public "
        "body's servants?",
        "Sale or grant of the right to process the payroll ('cessão onerosa', 'exclusividade', 'credenciamento', "
        "'concessão' of the payroll or of the salary credits).",
        "No right over the payroll is granted, or the right is only over payroll-deductible loans ('canal de "
        "consignações')."),
    "consignado": jev.noul(
        "Is `objeto` about payroll-deductible loans ('empréstimo consignado', 'consignações em folha')?",
        "The contract offers, manages or grants the channel for payroll-deductible loans to servants.",
        "The contract is about paying salaries, or about something other than payroll-deductible loans."),
    "sistema_rh": jev.noul(
        "Is `objeto` about payroll software, an HR or payroll-calculation service, consulting, training or an event "
        "about the payroll?",
        "Software or systems, calculation or preparation of the payroll, HR outsourcing, consultancy, courses or "
        "event registrations.",
        "A banking service, or goods and services unrelated to the payroll."),
}
EXCLUSAO = ("consignado", "sistema_rh")


def combina(p: dict) -> float:
    """A regra no código: banco E (paga salários OU direito sobre a folha), e NÃO consignado/sistema."""
    positivo = min(p["banco"], max(p["paga_salarios"], p["direito_folha"]))
    return positivo * (1 - max(p["consignado"], p["sistema_rh"]))


def _logit(p):
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


def _lr_loo(x, y, l2=1.0, it=300, lr=0.1):
    """Regressão logística com L2, previsões leave-one-out (só para medir; nada de produção)."""
    n, k = len(x), len(x[0])

    def treino(xs, ys):
        w = [0.0] * (k + 1)
        for _ in range(it):
            g = [0.0] * (k + 1)
            for xi, yi in zip(xs, ys):
                z = w[0] + sum(a * b for a, b in zip(w[1:], xi))
                e = 1 / (1 + math.exp(-z)) - yi
                g[0] += e
                for j in range(k):
                    g[j + 1] += e * xi[j]
            for j in range(k + 1):
                w[j] -= lr * (g[j] / len(xs) + (l2 * w[j] / len(xs) if j else 0))
        return w
    out = []
    for i in range(n):
        w = treino(x[:i] + x[i + 1:], y[:i] + y[i + 1:])
        z = w[0] + sum(a * b for a, b in zip(w[1:], x[i]))
        out.append(1 / (1 + math.exp(-z)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-pos", type=int, default=120)
    ap.add_argument("--semente", type=int, default=24092026)
    ap.add_argument("--teto-usd", type=float, default=0.15)
    a = ap.parse_args()
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    segredos.carregar()
    with psycopg.connect(_67._dsn()) as conn:
        conn.read_only = True
        # o MESMO sorteio da 73_
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
        humanos = conn.execute(
            "SELECT r.controle, l.objeto, (r.veredito = 'dentro')::int FROM (SELECT DISTINCT ON (controle) controle, veredito"
            " FROM rotulos_escopo ORDER BY controle, em DESC, id DESC) r JOIN licitacoes l USING (controle)"
            " WHERE coalesce(l.objeto, '') <> ''").fetchall()
    print("gabarito 1: %d positivos · %d negativos | gabarito 2 (rótulos humanos): %d" % (
        sum(1 for i in itens if i[3]), sum(1 for i in itens if not i[3]), len(humanos)))

    gasto = {"usd": 0.0, "tok": 0}
    q_v3 = {"escopo": jev.noul(V3["pergunta"], V3["sim"], V3["nao"])}
    q_e = {"escopo": jev.noul(PERGUNTA_E, V3["sim"], V3["nao"])}
    q_rag = {"escopo": jev.noul(_73.PERGUNTA_RAG, V3["sim"], V3["nao"])}

    def perguntar(state, q):
        for t in range(3):
            try:
                ans, uso = jev.perguntar(state, q, timeout=120)
                gasto["usd"] += uso["usd"]
                gasto["tok"] += uso["input_tokens"]
                vals = {k: jev.valor(ans.get(k) or {}) for k in q}
                return None if any(v is None for v in vals.values()) else vals
            except jev.ErroJev:
                if t == 2:
                    return None
                time.sleep(2)

    def um(x):
        c, o, lid, rot = x
        if gasto["usd"] >= a.teto_usd:
            return None
        pgs = paginas.get(c) or []
        t12 = _73.rag(pgs)
        t06 = _73.rag(pgs, teto=6000)
        r = {"controle": c, "rotulo": rot, "objeto": " ".join((o or "").split())[:160],
             "chars_12k": sum(len(t["texto"]) for t in t12), "chars_6k": sum(len(t["texto"]) for t in t06)}
        ra = perguntar(o, q_v3)
        rb = perguntar(json.dumps({"objeto": o, "trechos_do_edital": t12}, ensure_ascii=False), q_rag)
        rc = perguntar({"objeto": o, "trechos_do_edital": t12}, q_rag)
        rd = perguntar({"objeto": o, "trechos_do_edital": t06}, q_rag)
        re_ = perguntar({"objeto": o}, q_e)
        rf = perguntar({"objeto": o}, DECOMPOSTO)
        if None in (ra, rb, rc, rd, re_, rf):
            return None
        r.update({"A": ra["escopo"], "B": rb["escopo"], "C": rc["escopo"], "D": rd["escopo"], "E": re_["escopo"],
                  "F_q": rf, "F": combina(rf)})
        return r

    def um_humano(x):
        c, o, rot = x
        if gasto["usd"] >= a.teto_usd:
            return None
        ra = perguntar(o, q_v3)
        re_ = perguntar({"objeto": o}, q_e)
        rf = perguntar({"objeto": o}, DECOMPOSTO)
        if None in (ra, re_, rf):
            return None
        return {"controle": c, "rotulo": rot, "objeto": " ".join((o or "").split())[:160],
                "A": ra["escopo"], "E": re_["escopo"], "F_q": rf, "F": combina(rf)}

    with ThreadPoolExecutor(6) as ex:
        res = [r for r in ex.map(um, itens) if r]
        hum = [r for r in ex.map(um_humano, humanos) if r]

    def resumo(rs, k):
        return _67._resumo([r[k] for r in rs if r["rotulo"]], [r[k] for r in rs if not r["rotulo"]])

    for r in res:
        r["A+B"] = (r["A"] + r["B"]) / 2
        r["A+C"] = (r["A"] + r["C"]) / 2
        r["E+C"] = (r["E"] + r["C"]) / 2
        r["A+D"] = (r["A"] + r["D"]) / 2
    out = {"gabarito_1": {k: resumo(res, k) for k in ("A", "B", "C", "D", "E", "F", "A+B", "A+C", "E+C", "A+D")}}

    def lado(r, q):
        return (1 - r["F_q"][q]) if q in EXCLUSAO else r["F_q"][q]
    out["gabarito_1"]["F_por_pergunta_auc"] = {
        q: round(_67._auc([lado(r, q) for r in res if r["rotulo"]], [lado(r, q) for r in res if not r["rotulo"]]), 3)
        for q in DECOMPOSTO}
    todos = res + hum
    loo = _lr_loo([[_logit(r["F_q"][q]) for q in DECOMPOSTO] for r in todos], [r["rotulo"] for r in todos])
    for r, p in zip(todos, loo):
        r["F_lr_loo"] = p
    classes = {r["rotulo"] for r in hum}
    out["gabarito_2"] = {k: (resumo(hum, k) if len(classes) > 1 else None) for k in ("A", "E", "F")}
    out["gabarito_2_acertos_0.5"] = {k: sum((r[k] >= 0.5) == bool(r["rotulo"]) for r in hum) for k in ("A", "E", "F")}
    out["F_regressao_loo_todos"] = _67._resumo([r["F_lr_loo"] for r in todos if r["rotulo"]],
                                               [r["F_lr_loo"] for r in todos if not r["rotulo"]])
    out.update({"n_1": len(res), "n_2": len(hum), "usd": round(gasto["usd"], 5), "tokens": gasto["tok"],
                "modelo": jev.MODELO, "decomposto": DECOMPOSTO, "pergunta_e": PERGUNTA_E})
    os.makedirs(os.path.join(RAIZ, "docs", "medicoes"), exist_ok=True)
    arq = os.path.join(RAIZ, "docs", "medicoes", "jev_configuracao_%s.json" % datetime.date.today().isoformat())
    with io.open(arq, "w", encoding="utf-8") as f:
        json.dump({"resumo": out, "itens": res, "humanos": hum}, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("gabarito_1", "gabarito_2", "gabarito_2_acertos_0.5", "F_regressao_loo_todos",
                                          "n_1", "n_2", "usd", "tokens")}, ensure_ascii=False, indent=1))
    print("gravado:", arq)
    return 0


if __name__ == "__main__":
    sys.exit(main())
