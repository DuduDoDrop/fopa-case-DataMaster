# -*- coding: utf-8 -*-
"""
O score do filtro para o acervo que já está no banco da v3 — uma vez.

    python 66_jev_escopo_acervo.py [--max N] [--teto-usd 0.10] [--seco]

POR QUÊ
  Para cada resultado da consulta ao PNCP, a PROBABILIDADE de o
  filtro de escopo ter acertado (a API traz muito ruído além da folha).
  O W01 faz isso para o que ENTRA de novo; as 1.8xx
  licitações que o importador trouxe da v2 nunca foram avaliadas, e o site não
  mostra "filtro X%" em nenhuma.

COMO — O MESMO CAMINHO DE PRODUÇÃO
  O app do worker roda em processo (FastAPI TestClient) contra o Postgres da
  stack, com o papel worker_rw:
    POST /jev/escopo/corpos      o corpo com o critério medido (63_ v2) e a regra de HOJE
    (este script chama o Jev, como o n8n faria com a credencial dele)
    POST /jev/escopo/interpretar grava o sinal em sinais_jev (p_filtro_ok, candidata)
  Nada daqui escreve escopo_dentro (T25): o Jev é sinal, a regra decide.
  Idempotente: pula quem já tem sinal de escopo.
"""
from __future__ import annotations

import argparse
import io
import os
import secrets
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)


def _env(caminho: str) -> dict:
    d = {}
    with io.open(caminho, encoding="utf-8") as f:
        for l in f:
            if "=" in l and not l.lstrip().startswith("#"):
                k, _, v = l.strip().partition("=")
                d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--teto-usd", type=float, default=0.10)
    ap.add_argument("--fios", type=int, default=6)
    ap.add_argument("--seco", action="store_true", help="só conta quantas seriam avaliadas")
    ap.add_argument("--historico", action="store_true",
                    help="também o que é de antes do recorte, no escopo de folha (a descoberta histórica, db/030)")
    a = ap.parse_args()
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    stack = _env(os.path.join(RAIZ, "docker", ".env"))
    raiz = _env(os.path.join(RAIZ, ".env"))
    # O app do worker nunca lê o .env (api/__init__.py); a chave do Jev entra
    # só neste processo, como entraria na credencial do n8n.
    os.environ["JEV_API_KEY"] = raiz["JEV_API_KEY"]
    os.environ["DATABASE_URL"] = "postgresql://worker_rw:%s@127.0.0.1:5433/fopa" % stack["WORKER_RW_PASSWORD"]
    token = secrets.token_hex(16)
    os.environ["FOPA_WORKER_TOKEN"] = token
    os.environ.pop("ANTHROPIC_API_KEY", None)
    sys.path.insert(0, RAIZ)
    sys.path.insert(0, AQUI)

    import psycopg
    from fastapi.testclient import TestClient

    from api import jev as jev_api
    from api import worker
    from fopa import jev as cliente

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        linhas = conn.execute(
            "SELECT l.controle, l.objeto FROM licitacoes l"
            # --historico (25/09): o passado de folha que a descoberta trouxe também ganha nota — é ela que o filtro
            # "apenas FOPA (a IA confirma)" do histórico e do analytics usa
            " WHERE " + ("fn_escopo_efetivo(l.controle, l.escopo_dentro)" if a.historico
                         else "fn_no_recorte(l.fim_prazo, l.publicado_em)") + " AND coalesce(l.objeto, '') <> ''"
            "   AND NOT EXISTS (SELECT 1 FROM sinais_jev s WHERE s.controle = l.controle AND s.tipo = 'escopo'"
            "                   AND s.criterio_versao = %s"
            "                   AND s.regra = CASE WHEN l.escopo_dentro THEN 'dentro' ELSE 'fora' END)"
            " ORDER BY l.controle", ("escopo-" + jev_api.CRITERIO_ESCOPO,)).fetchall()
    if a.max:
        linhas = linhas[:a.max]
    print("a avaliar: %d (no recorte, com objeto, sem sinal de escopo)" % len(linhas))
    if a.seco or not linhas:
        return 0

    c = TestClient(worker.app)
    H = {"Authorization": "Bearer " + token}
    gasto = {"usd": 0.0}
    res = []

    def um(req):
        if gasto["usd"] >= a.teto_usd:
            return None
        b = req["body"]
        for tentativa in range(3):
            try:
                ans, uso = cliente.perguntar(b["state"], b["questions"], modelo=b["model"])
                break
            except cliente.ErroJev as e:
                if tentativa == 2:
                    return {"controle": req["controle"], "erro": str(e)[:120]}
                time.sleep(2 * (tentativa + 1))
        gasto["usd"] += uso["usd"]
        r = c.post("/jev/escopo/interpretar", headers=H, json={
            "controle": req["controle"], "regra_dentro": req["regra_dentro"],
            "resposta": {"answers": ans, "usage": {"input_tokens": uso["input_tokens"]}, "model": uso["modelo"]}})
        return r.json() if r.status_code == 200 else {"controle": req["controle"], "erro": r.text[:120]}

    t0 = time.time()
    for i in range(0, len(linhas), 50):
        lote = [{"controle": x[0], "objeto": x[1]} for x in linhas[i:i + 50]]
        corpos = c.post("/jev/escopo/corpos", headers=H, json={"itens": lote})
        corpos.raise_for_status()
        with ThreadPoolExecutor(a.fios) as ex:
            res += [r for r in ex.map(um, corpos.json()["requisicoes"]) if r]
        print("  %4d/%d  US$ %.4f" % (min(i + 50, len(linhas)), len(linhas), gasto["usd"]), flush=True)
        if gasto["usd"] >= a.teto_usd:
            print("  teto de US$ %.2f atingido; o resto fica para a próxima rodada (idempotente)" % a.teto_usd)
            break

    ok = [r for r in res if "erro" not in r and r.get("p_sim") is not None]
    erros = [r for r in res if "erro" in r]
    pf = [r["p_filtro_ok"] for r in ok]
    print({"avaliadas": len(ok), "erros": len(erros), "discordancias": sum(r["discorda"] for r in ok),
           "candidatas": sum(r["candidata"] for r in ok),
           "p_filtro_ok_medio": round(statistics.mean(pf), 4) if pf else None,
           "p_filtro_ok_<0.5": sum(p < 0.5 for p in pf), "usd": round(gasto["usd"], 5),
           "segundos": round(time.time() - t0, 1)})
    for e in erros[:5]:
        print("  erro:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
