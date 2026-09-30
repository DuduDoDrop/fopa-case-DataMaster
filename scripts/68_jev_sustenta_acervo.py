# -*- coding: utf-8 -*-
"""
"Sustenta?" do Jev em TODA resposta com trecho das verificações vigentes — o score da resposta.

    python 68_jev_sustenta_acervo.py [--abertas] [--max-lic N] [--teto-usd 0.30] [--seco]

  24/09 noite: cada pergunta e resposta com a métrica do Jev — não só as
  APROVADAS. O sinal vale para a EXECUÇÃO (re-verificar não muda resposta nem trecho), e rodar de novo
  só pergunta o que falta (`so_faltando`). `--abertas`: só as licitações com prazo aberto.

POR QUÊ
  O segundo uso do Jev: a PROBABILIDADE de cada resposta estar
  certa. A ancoragem garante que o trecho EXISTE na página citada; não garante
  que ele SUSTENTA a afirmação (64_jev_ancoragem.py: o ponto cego). O site mostra
  "sustenta X%" ao lado de cada APROVADA — e hoje não há sinal nenhum.

COMO — O MESMO CAMINHO DE PRODUÇÃO (o W24 fará igual, com a credencial do n8n)
  O app do worker roda em processo (TestClient) contra o Postgres da stack
  (papel worker_rw):
    POST /jev/sustenta/corpos       por verificação: um corpo por APROVADA com trecho
                                    (documento inteiro ou janela em volta da página)
    (este script chama o Jev)
    POST /jev/sustenta/interpretar  grava em sinais_jev; "contradiz"/"nada_diz" com
                                    convicção vira revisão humana ABERTA
  Nada daqui muda veredito nem confiança (T25). Idempotente: pula a verificação
  que já tem sinal "sustenta" do critério atual.
"""
from __future__ import annotations

import argparse
import io
import os
import secrets
import statistics
import sys
import time
from collections import Counter
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
    ap.add_argument("--max-lic", type=int, default=0)
    ap.add_argument("--abertas", action="store_true", help="só licitações com prazo aberto (fim_prazo no futuro)")
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
        # Verificação vigente com ALGUMA resposta citando trecho e ainda sem o sinal do critério atual
        # na mesma execução (o mesmo filtro de `so_faltando` em api/rotas_jev.py).
        vids = [r[0] for r in conn.execute(
            "SELECT v.id FROM verificacoes v JOIN licitacoes l ON l.controle = v.controle"
            " WHERE v.vigente AND v.leitura_id IS NOT NULL AND NOT l.ensaio AND l.escopo_dentro"
            + ("   AND l.fim_prazo > now()" if a.abertas else "") +
            "   AND EXISTS (SELECT 1 FROM verificacao_respostas vr JOIN respostas r"
            "        ON r.execucao_id = v.execucao_id AND r.pergunta_id = vr.pergunta_id"
            "        WHERE vr.verificacao_id = v.id AND vr.ausencia IS NULL AND vr.arquivo_canonico IS NOT NULL"
            "          AND coalesce(r.trecho_literal, '') <> ''"
            "          AND NOT EXISTS (SELECT 1 FROM sinais_jev s JOIN verificacoes vs ON vs.id = s.verificacao_id"
            "               WHERE s.tipo = 'sustenta' AND vs.execucao_id = v.execucao_id"
            "                 AND s.pergunta_id = vr.pergunta_id AND s.criterio_versao = %s))"
            " ORDER BY l.fim_prazo NULLS LAST, v.controle", (jev_api.CRITERIO_SUSTENTA,)).fetchall()]
    if a.max_lic:
        vids = vids[:a.max_lic]
    print("verificações a avaliar: %d" % len(vids))
    if a.seco or not vids:
        return 0

    c = TestClient(worker.app)
    H = {"Authorization": "Bearer " + token}
    gasto = {"usd": 0.0, "tok": 0}
    res = []

    def um(args):
        vid, req = args
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
        r = c.post("/jev/sustenta/interpretar", headers=H, json={
            "verificacao_id": vid, "pergunta_id": req["pergunta_id"], "contexto_enviado": req["contexto_enviado"],
            "resposta": {"answers": ans, "usage": {"input_tokens": uso["input_tokens"]}, "model": uso["modelo"]}})
        out = r.json() if r.status_code == 200 else {"erro": r.text[:120]}
        out["pergunta_id"] = req["pergunta_id"]
        out["contexto"] = req["contexto_enviado"]
        return out

    t0 = time.time()
    for i, vid in enumerate(vids, 1):
        d = c.post("/jev/sustenta/corpos", headers=H, json={"verificacao_id": vid, "so_faltando": True})
        if d.status_code != 200:
            res.append({"erro": "corpos %s: %s" % (d.status_code, d.text[:100])})
            continue
        with ThreadPoolExecutor(a.fios) as ex:
            res += [r for r in ex.map(um, [(vid, q) for q in d.json()["requisicoes"]]) if r]
        print("  %3d/%d  %s  US$ %.4f  (%d tok)" % (i, len(vids), d.json().get("controle"), gasto["usd"], gasto["tok"]),
              flush=True)
        if gasto["usd"] >= a.teto_usd:
            print("  teto de US$ %.2f atingido; o resto fica para a próxima rodada (idempotente)" % a.teto_usd)
            break

    ok = [r for r in res if "erro" not in r and r.get("resposta")]
    ps = [r["p_sustenta"] for r in ok if r.get("p_sustenta") is not None]
    print({"respostas": len(ok), "erros": len([r for r in res if "erro" in r]),
           "escolhas": dict(Counter(r["resposta"] for r in ok)),
           "candidatas_revisao": sum(bool(r.get("candidata")) for r in ok),
           "p_sustenta_mediana": round(statistics.median(ps), 3) if ps else None,
           "p_sustenta_<0.5": sum(p < 0.5 for p in ps),
           "contextos": dict(Counter(("janela" if str(r["contexto"]).startswith("janela") else r["contexto"]) for r in ok)),
           "usd": round(gasto["usd"], 4), "tokens": gasto["tok"], "segundos": round(time.time() - t0, 1)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
