# -*- coding: utf-8 -*-
"""
O Jev de escopo com MAIS CONTEXTO (RAG do edital) acerta melhor? — só objeto × objeto + páginas do edital.

    python 73_jev_escopo_rag.py [--n-pos 120] [--teto-usd 0.10]

O PEDIDO
  Mais contexto para o Jev, com RAG quando preciso (o custo é baixo), e a revisão dos alertas de fora do
  escopo que, na verdade, estão dentro.

O ACHADO QUE MOTIVA
  No Painel, as 5 discordâncias do Jev (critério v3, só o `objeto`) eram todas CREDENCIAMENTO de banco para
  processar os créditos da folha (Recife/TJPE, Ibertioga, Santa Efigênia de Minas, Rafael Jambeiro, Porto
  Nacional): p = 0,27 a 0,45. O v3 foi medido (67_) só com o objeto — os 2.425 sinais do banco são todos
  `contexto_enviado = 'objeto'`.

GABARITO JUSTO (sem chamar o Jev para escolhê-lo)
  Contexto só existe onde há LEITURA (páginas do edital). Comparar positivos com páginas contra negativos sem
  páginas faria do "ter contexto" a pista do rótulo. Então os DOIS lados têm leitura:
    positivos: licitações PUBLICADAS com leitura (as 5 discordâncias sempre entram) — amostra fixa
    negativos: as 19 que a leitura humana RECUSOU (ADR-015), com leitura
  Os mesmos itens vão duas vezes ao Jev: só objeto (o v3 de produção) e objeto + trechos do edital.

O RAG
  Páginas da leitura pontuadas pelos termos da pergunta (folha, créditos, processamento, instituição
  financeira, credenciamento, cessão, exclusividade, contrapartida, consignado, software…) — as melhores até
  ~12 mil caracteres, com arquivo e página. Nada de modelo para escolher.

Não escreve nada no banco. A medição vai para docs/medicoes/.
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import random
import re
import statistics
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

import psycopg                                                    # noqa: E402

from fopa import jev, segredos                                    # noqa: E402

sys.path.insert(0, AQUI)
_67 = __import__("67_jev_escopo_criterio")
CRITERIO = _67.CRITERIO_V3
DISCORDANCIAS = ("18335922000115-1-000001/2025", "18094839000100-1-000024/2025", "18307462000111-1-000029/2026",
                 "13195862000169-1-000016/2026", "45316509000186-1-000123/2025")
TETO_CHARS = 12_000
TERMOS = ("folha de pagamento", "folha", "credito", "creditos", "processamento", "gerenciamento", "salario",
          "instituicao financeira", "instituicao bancaria", "banco", "credenciamento", "credenciada", "cessao",
          "exclusividade", "contrapartida", "servidores", "consignado", "consignacao", "software", "sistema",
          "objeto", "conta salario", "remuneracao")

PERGUNTA_RAG = (CRITERIO["pergunta"] + " Besides `objeto`, `trechos_do_edital` holds pages of the notice itself "
                "(file and page number): use them as evidence of what is being contracted.")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).lower()


def rag(paginas: list[tuple[str, int, str]], teto: int = TETO_CHARS) -> list[dict]:
    """As páginas com mais termos da pergunta, na ordem do documento, até o teto."""
    pont = []
    for arq, n, texto in paginas:
        t = _norm(texto)
        score = sum(t.count(x) for x in TERMOS)
        if score:
            pont.append((score, arq, n, texto))
    escolhidas, total = [], 0
    for score, arq, n, texto in sorted(pont, key=lambda x: -x[0]):
        corte = " ".join((texto or "").split())[:4000]
        if total + len(corte) > teto:
            continue
        escolhidas.append((arq, n, corte))
        total += len(corte)
    escolhidas.sort(key=lambda x: (x[0], x[1]))
    return [{"arquivo": a, "pagina": n, "texto": t} for a, n, t in escolhidas]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-pos", type=int, default=120)
    ap.add_argument("--semente", type=int, default=24092026)
    ap.add_argument("--teto-usd", type=float, default=0.10)
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
                            " AND l.leitura_vigente_id IS NOT NULL", (list(DISCORDANCIAS),)).fetchall()
        rnd = random.Random(a.semente)
        amostra = rnd.sample([p for p in pos if p[0] not in DISCORDANCIAS], min(a.n_pos, len(pos)))
        itens = [(c, o, lid, 1) for c, o, lid in disc + amostra] + [(c, o, lid, 0) for c, o, lid in neg]
        paginas = {}
        for c, o, lid, _ in itens:
            paginas[c] = [(r[0], r[1], r[2]) for r in conn.execute(
                "SELECT arquivo_nome, numero, texto FROM paginas WHERE leitura_id = %s ORDER BY arquivo_nome, numero",
                (lid,)).fetchall()]
    print("positivos %d (5 discordâncias + %d sorteados) · negativos %d" % (len(disc) + len(amostra), len(amostra), len(neg)))

    gasto = {"usd": 0.0, "tok": 0}
    q_obj = {"escopo": jev.noul(CRITERIO["pergunta"], CRITERIO["sim"], CRITERIO["nao"])}
    q_rag = {"escopo": jev.noul(PERGUNTA_RAG, CRITERIO["sim"], CRITERIO["nao"])}

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
        trechos = rag(paginas.get(c) or [])
        p_obj = perguntar(o, q_obj)
        p_rag = perguntar(json.dumps({"objeto": o, "trechos_do_edital": trechos}, ensure_ascii=False), q_rag)
        return {"controle": c, "rotulo": rot, "objeto_so": p_obj, "com_rag": p_rag, "paginas_rag": len(trechos),
                "chars_rag": sum(len(t["texto"]) for t in trechos), "discordancia": c in DISCORDANCIAS,
                "objeto": " ".join((o or "").split())[:160]}

    with ThreadPoolExecutor(6) as ex:
        res = [r for r in ex.map(um, itens) if r and r["objeto_so"] is not None and r["com_rag"] is not None]
    out = {}
    for k in ("objeto_so", "com_rag"):
        out[k] = _67._resumo([r[k] for r in res if r["rotulo"]], [r[k] for r in res if not r["rotulo"]])
    out["discordancias"] = [{"controle": r["controle"], "objeto_so": round(r["objeto_so"], 3), "com_rag": round(r["com_rag"], 3)}
                            for r in res if r["discordancia"]]
    out.update({"n": len(res), "usd": round(gasto["usd"], 5), "tokens": gasto["tok"], "modelo": jev.MODELO,
                "teto_chars": TETO_CHARS, "pergunta_rag": PERGUNTA_RAG})
    out["piores_com_rag"] = sorted([r for r in res if r["rotulo"]], key=lambda r: r["com_rag"])[:5] + \
        sorted([r for r in res if not r["rotulo"]], key=lambda r: -r["com_rag"])[:5]
    os.makedirs(os.path.join(RAIZ, "docs", "medicoes"), exist_ok=True)
    arq = os.path.join(RAIZ, "docs", "medicoes", "jev_escopo_rag_%s.json" % datetime.date.today().isoformat())
    with io.open(arq, "w", encoding="utf-8") as f:
        json.dump({"resumo": out, "itens": res}, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("objeto_so", "com_rag", "discordancias", "n", "usd", "tokens")},
                     ensure_ascii=False, indent=1))
    for r in out["piores_com_rag"]:
        print("  rot=%d obj=%.2f rag=%.2f (%dp)  %s" % (r["rotulo"], r["objeto_so"], r["com_rag"], r["paginas_rag"], r["objeto"][:110]))
    print("gravado:", arq)
    return 0


if __name__ == "__main__":
    sys.exit(main())
