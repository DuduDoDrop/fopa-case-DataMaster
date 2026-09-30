# -*- coding: utf-8 -*-
"""
O escopo do Jev COM O EDITAL nas licitações já lidas — a segunda nota que a tela junta à do só-objeto.

    python 74_jev_escopo_edital_acervo.py [--abertas] [--max-lic N] [--teto-usd 0.30] [--seco]

POR QUÊ
  Mais contexto para o Jev, com RAG (24/09), e a revisão dos alertas de fora do escopo que estavam dentro.
  Medido em 73_: a média do
  só-objeto com o objeto+edital derruba o alarme falso na folha de 4% para 0,8% (os credenciamentos) e pega
  as mesmas recusas humanas. A média é da tela (api/consultas.py:JEV_ESCOPO); aqui só se grava a nota crua.

COMO — O MESMO CAMINHO DE PRODUÇÃO (como o 68_)
  O app do worker roda em processo (TestClient) contra o Postgres da stack (papel worker_rw):
    POST /jev/escopo/edital/corpos   objeto + páginas da leitura vigente escolhidas por termo (73_:rag)
    (este script chama o Jev)
    POST /jev/escopo/interpretar     grava em sinais_jev com contexto_enviado "edital RAG Np"
  Nada daqui muda escopo (T25). Idempotente: `so_faltando`.
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
    ap.add_argument("--abertas", action="store_true", help="só licitações com prazo aberto")
    ap.add_argument("--max-lic", type=int, default=0)
    ap.add_argument("--teto-usd", type=float, default=0.30)
    ap.add_argument("--fios", type=int, default=6)
    ap.add_argument("--seco", action="store_true")
    a = ap.parse_args()
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    stack = _env(os.path.join(RAIZ, "docker", ".env"))
    os.environ["JEV_API_KEY"] = _env(os.path.join(RAIZ, ".env"))["JEV_API_KEY"]
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
        controles = [r[0] for r in conn.execute(
            "SELECT l.controle FROM licitacoes l WHERE l.escopo_dentro AND l.leitura_vigente_id IS NOT NULL"
            + (" AND l.fim_prazo > now()" if a.abertas else "") +
            " AND NOT EXISTS (SELECT 1 FROM sinais_jev s WHERE s.tipo = 'escopo' AND s.controle = l.controle"
            "                 AND s.criterio_versao = %s)"
            " ORDER BY l.fim_prazo DESC NULLS LAST, l.controle", ("escopo-" + jev_api.CRITERIO_ESCOPO_EDITAL,)).fetchall()]
    if a.max_lic:
        controles = controles[:a.max_lic]
    print("licitações a avaliar: %d" % len(controles))
    if a.seco or not controles:
        return 0

    c = TestClient(worker.app)
    H = {"Authorization": "Bearer " + token}
    gasto = {"usd": 0.0, "tok": 0}

    def um(req):
        if gasto["usd"] >= a.teto_usd:
            return None
        b = req["body"]
        for t in range(3):
            try:
                ans, uso = cliente.perguntar(b["state"], b["questions"], modelo=b["model"], timeout=120)
                break
            except cliente.ErroJev as e:
                if t == 2:
                    return {"erro": str(e)[:120]}
                time.sleep(3 * (t + 1))
        gasto["usd"] += uso["usd"]
        gasto["tok"] += uso["input_tokens"]
        r = c.post("/jev/escopo/interpretar", headers=H, json={
            "controle": req["controle"], "regra_dentro": req["regra_dentro"], "contexto_enviado": req["contexto_enviado"],
            "resposta": {"answers": ans, "usage": {"input_tokens": uso["input_tokens"]}, "model": uso["modelo"]}})
        return r.json() if r.status_code == 200 else {"erro": r.text[:120]}

    res, t0 = [], time.time()
    for i in range(0, len(controles), 20):
        lote = controles[i:i + 20]
        d = c.post("/jev/escopo/edital/corpos", headers=H, json={"controles": lote, "so_faltando": True})
        if d.status_code != 200:
            res.append({"erro": "corpos %s: %s" % (d.status_code, d.text[:100])})
            continue
        with ThreadPoolExecutor(a.fios) as ex:
            res += [r for r in ex.map(um, d.json()["requisicoes"]) if r]
        print("  %4d/%d  US$ %.4f  (%d tok)" % (min(i + 20, len(controles)), len(controles), gasto["usd"], gasto["tok"]),
              flush=True)
        if gasto["usd"] >= a.teto_usd:
            print("  teto de US$ %.2f atingido; o resto fica para a próxima rodada (idempotente)" % a.teto_usd)
            break
    ok = [r for r in res if "erro" not in r and r.get("p_sim") is not None]
    ps = [r["p_sim"] for r in ok]
    print({"avaliadas": len(ok), "erros": len([r for r in res if "erro" in r]),
           "p_sim_mediana": round(statistics.median(ps), 3) if ps else None, "p_sim_<0.5": sum(p < 0.5 for p in ps),
           "candidatas_so_desta_nota": sum(bool(r.get("candidata")) for r in ok),
           "usd": round(gasto["usd"], 4), "tokens": gasto["tok"], "segundos": round(time.time() - t0, 1)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
