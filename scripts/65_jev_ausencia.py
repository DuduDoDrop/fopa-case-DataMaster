# -*- coding: utf-8 -*-
"""
"Não localizado" com página que responde? — o R1 de "Jev — casos de uso avaliados".

    python 65_jev_ausencia.py --prova [--n 140]        o Jev sabe dizer sim E não?
    python 65_jev_ausencia.py --ausencias [--max-lic N] as "Não localizado" do acervo
    python 65_jev_ausencia.py --controle <c> --perguntas Q7,Q10   uma licitação, ranking

CHAMA O JEV (centavos; teto --teto-usd). Lê o Postgres da v3 (papel api_ro, só
leitura) — as verificações VIGENTES e as páginas CONGELADAS delas. Não escreve
no banco, não muda veredito, não apaga "Não localizado" (T25). Grava a medição
em docs/medicoes/.

O PONTO CEGO
  "Não localizado" ancora por construção: sem citação, o verificador não tem o
  que conferir. Se a página certa ficou fora do top-k do BM25 (ADR-010:
  "começar a executar" × "iniciar", Bertioga Q10), o modelo diz "Não
  localizado" e ninguém percebe. 274 respostas vigentes estão nesse estado e
  nenhuma foi conferida.

O QUE SE PERGUNTA AO JEV
  Um Noul por pergunta "Não localizado" da licitação, todas no mesmo request,
  sobre UMA página por vez ({arquivo, pagina, texto}): "esta página traz a
  informação que responde à pergunta?". Página é a unidade de citação
  (ADR-005) e estado pequeno é onde o Jev acerta mais.

ANTES DE CONFIAR: --prova
  Para N respostas APROVADAS (a página citada TEM a resposta — o verificador
  conferiu), Noul na página citada (tem de dar alto) e em até 5 páginas
  sorteadas do mesmo arquivo, longe da citada (têm de dar baixo). Sem isso,
  um sinal nas ausências não quer dizer nada.
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
import threading
import time
from concurrent.futures import ThreadPoolExecutor

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

from fopa import jev, questionario, segredos                      # noqa: E402

DESTINO = os.path.join(RAIZ, "docs", "medicoes")
CORTE = 0.75                       # o corte de convicção medido na 1.13 (Jev na v3)
MAX_TEXTO = 60_000                 # 32k tokens de state (MAX_CHARS_STATE do worker: 63.000)
POR_ID = {p.id: p for p in questionario.PERGUNTAS}


def _dsn() -> str:
    if os.environ.get("FOPA_DSN_LEITURA"):
        return os.environ["FOPA_DSN_LEITURA"]
    env = {}
    with io.open(os.path.join(RAIZ, "docker", ".env"), encoding="utf-8") as f:
        for l in f:
            if "=" in l and not l.lstrip().startswith("#"):
                k, _, v = l.strip().partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    return "postgresql://api_ro:%s@127.0.0.1:5433/fopa" % env["API_RO_PASSWORD"]


def _noul(pid: str) -> dict:
    p = POR_ID[pid]
    instr = ("Esta página de um edital de licitação pública traz a informação que responde à "
             "pergunta abaixo? Julgue só esta página; a informação pode estar escrita com outras "
             "palavras. Pergunta: %s O que conta como resposta: %s" % (p.texto, p.orienta or "a informação pedida"))
    return jev.noul(instr,
                    "a página traz a informação pedida pela pergunta, o bastante para respondê-la "
                    "(inclusive quando diz expressamente que não há ou que não se exige)",
                    "a página não trata do assunto, ou só o menciona de passagem sem dar a "
                    "informação pedida")


class Gasto:
    def __init__(self, teto: float):
        self.teto, self.usd, self.chamadas, self._t = teto, 0.0, 0, threading.Lock()

    def perguntar(self, estado: dict, pids: list[str]) -> dict:
        with self._t:
            if self.usd >= self.teto:
                raise RuntimeError("teto de US$ %.2f atingido" % self.teto)
        for tentativa in range(3):
            try:
                ans, uso = jev.perguntar(json.dumps(estado, ensure_ascii=False),
                                         {pid: _noul(pid) for pid in pids})
                break
            except jev.ErroJev as e:
                if tentativa == 2 or getattr(e, "status", None) not in (429, 500, 502, 503, 529, None):
                    raise
                time.sleep(3 * (tentativa + 1))
        with self._t:
            self.usd += uso["usd"]
            self.chamadas += 1
        return {pid: jev.valor(ans.get(pid) or {}) for pid in pids}


def _estado(arquivo: str, numero: int, texto: str) -> dict:
    return {"arquivo": arquivo, "pagina": numero, "texto": (texto or "")[:MAX_TEXTO]}


# ------------------------------------------------------------------ prova
def prova(conn, gasto: Gasto, n: int, semente: int, fios: int) -> dict:
    linhas = conn.execute(
        "SELECT v.controle, v.leitura_id, vr.pergunta_id, vr.arquivo_canonico, vr.pagina_final"
        "  FROM verificacao_respostas vr JOIN verificacoes v ON v.id = vr.verificacao_id AND v.vigente"
        " WHERE vr.veredito = 'APROVADO' AND vr.ausencia IS NULL AND vr.pagina_final IS NOT NULL"
        "   AND v.leitura_id IS NOT NULL ORDER BY v.controle, vr.pergunta_id").fetchall()
    rnd = random.Random(semente)
    rnd.shuffle(linhas)
    tarefas = []
    for x in linhas:
        if len(tarefas) >= n:
            break
        pags = conn.execute("SELECT numero, texto FROM paginas WHERE leitura_id = %s AND arquivo_nome = %s"
                            " ORDER BY numero", (x["leitura_id"], x["arquivo_canonico"])).fetchall()
        por_num = {p["numero"]: p["texto"] for p in pags}
        if x["pagina_final"] not in por_num:
            continue
        longe = [k for k in por_num if abs(k - x["pagina_final"]) > 1]
        negs = rnd.sample(longe, min(5, len(longe)))
        tarefas.append((x, por_num, negs))

    def uma(t):
        x, por_num, negs = t
        pid = x["pergunta_id"]
        pos = gasto.perguntar(_estado(x["arquivo_canonico"], x["pagina_final"], por_num[x["pagina_final"]]), [pid])[pid]
        neg = [gasto.perguntar(_estado(x["arquivo_canonico"], k, por_num[k]), [pid])[pid] for k in negs]
        return {"controle": x["controle"], "pergunta": pid, "arquivo": x["arquivo_canonico"],
                "pagina": x["pagina_final"], "p_citada": pos, "negativas": dict(zip(negs, neg))}

    with ThreadPoolExecutor(fios) as ex:
        casos = list(ex.map(uma, tarefas))
    pos = [c["p_citada"] for c in casos if c["p_citada"] is not None]
    neg = [p for c in casos for p in c["negativas"].values() if p is not None]
    pares = [(c["p_citada"], p) for c in casos for p in c["negativas"].values()
             if c["p_citada"] is not None and p is not None]
    auc = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a, b in pares) / len(pares) if pares else None
    return {"casos": casos, "resumo": {
        "respostas": len(casos), "paginas_negativas": len(neg),
        "p_citada_media": round(statistics.mean(pos), 3) if pos else None,
        "p_negativa_media": round(statistics.mean(neg), 3) if neg else None,
        "citada_>=corte": round(sum(p >= CORTE for p in pos) / len(pos), 3) if pos else None,
        "citada_<=0.25": round(sum(p <= 0.25 for p in pos) / len(pos), 3) if pos else None,
        "negativa_>=corte (alarme falso)": round(sum(p >= CORTE for p in neg) / len(neg), 3) if neg else None,
        "auc_pareada": round(auc, 3) if auc is not None else None}}


# ------------------------------------------------------------------ ausências
def ausencias(conn, gasto: Gasto, max_lic: int, fios: int, controle: str | None = None,
              perguntas: list[str] | None = None) -> dict:
    sql = ("SELECT v.controle, v.leitura_id, array_agg(vr.pergunta_id ORDER BY vr.pergunta_id) AS pids"
           "  FROM verificacao_respostas vr JOIN verificacoes v ON v.id = vr.verificacao_id AND v.vigente"
           "  JOIN respostas r ON r.execucao_id = v.execucao_id AND r.pergunta_id = vr.pergunta_id"
           " WHERE v.leitura_id IS NOT NULL AND r.resposta ILIKE 'não localizad%%'")
    params: list = []
    if controle:
        sql = ("SELECT v.controle, v.leitura_id, %s::text[] AS pids FROM verificacoes v"
               " WHERE v.vigente AND v.leitura_id IS NOT NULL AND v.controle = %s")
        params = [perguntas, controle]
    else:
        sql += " GROUP BY v.controle, v.leitura_id ORDER BY v.controle"
    grupos = conn.execute(sql, params).fetchall()
    if max_lic:
        grupos = grupos[:max_lic]
    saida = []
    for g in grupos:
        pags = conn.execute("SELECT arquivo_nome, numero, texto FROM paginas WHERE leitura_id = %s"
                            " ORDER BY ordem, numero", (g["leitura_id"],)).fetchall()

        def uma(p, pids=g["pids"]):
            return (p["arquivo_nome"], p["numero"], gasto.perguntar(_estado(p["arquivo_nome"], p["numero"], p["texto"]), pids))

        with ThreadPoolExecutor(fios) as ex:
            res = list(ex.map(uma, pags))
        por_pergunta = {}
        for pid in g["pids"]:
            ranking = sorted(((ps.get(pid) or 0.0, arq, num) for arq, num, ps in res), reverse=True)
            por_pergunta[pid] = {"candidatas": [{"arquivo": a, "pagina": n, "p": round(p, 3)}
                                                for p, a, n in ranking if p >= CORTE][:5],
                                 "top3": [{"arquivo": a, "pagina": n, "p": round(p, 3)} for p, a, n in ranking[:3]]}
        saida.append({"controle": g["controle"], "paginas": len(pags), "perguntas": por_pergunta})
        print("  %s  %3d págs  %s  US$ %.4f" % (g["controle"], len(pags),
              " ".join("%s:%d" % (k, len(v["candidatas"])) for k, v in por_pergunta.items()), gasto.usd), flush=True)
    pares = [(s["controle"], pid, v) for s in saida for pid, v in s["perguntas"].items()]
    com = [x for x in pares if x[2]["candidatas"]]
    por_q = {}
    for _, pid, v in pares:
        d = por_q.setdefault(pid, {"nl": 0, "com_candidata": 0})
        d["nl"] += 1
        d["com_candidata"] += bool(v["candidatas"])
    return {"licitacoes": saida, "resumo": {
        "licitacoes": len(saida), "nao_localizadas": len(pares), "com_pagina_candidata": len(com),
        "revisoes_extras_por_licitacao": round(len(com) / len(saida), 2) if saida else None,
        "por_pergunta": por_q}}


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--prova", action="store_true")
    g.add_argument("--ausencias", action="store_true")
    g.add_argument("--controle")
    ap.add_argument("--perguntas", default="", help="com --controle: Q7,Q10")
    ap.add_argument("--n", type=int, default=140)
    ap.add_argument("--max-lic", type=int, default=0)
    ap.add_argument("--semente", type=int, default=24092026)
    ap.add_argument("--fios", type=int, default=4)
    ap.add_argument("--teto-usd", type=float, default=0.40)
    a = ap.parse_args()
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    # Uma vez, na thread principal: segredos.carregar() marca-se carregado ANTES de
    # ler o arquivo, e uma thread concorrente veria a chave ausente.
    segredos.carregar()
    gasto = Gasto(a.teto_usd)
    t0 = time.time()
    with psycopg.connect(_dsn(), row_factory=dict_row) as conn:
        conn.read_only = True
        if a.prova:
            modo, r = "prova", prova(conn, gasto, a.n, a.semente, a.fios)
        elif a.ausencias:
            modo, r = "ausencias", ausencias(conn, gasto, a.max_lic, a.fios)
        else:
            modo, r = "controle", ausencias(conn, gasto, 0, a.fios, a.controle,
                                            [x.strip() for x in a.perguntas.split(",") if x.strip()])
    r["medicao"] = {"modo": modo, "modelo": jev.MODELO, "corte": CORTE, "chamadas": gasto.chamadas,
                    "usd_anunciado": round(gasto.usd, 5), "segundos": round(time.time() - t0, 1),
                    "em": datetime.datetime.now().isoformat(timespec="seconds")}
    os.makedirs(DESTINO, exist_ok=True)
    arq = os.path.join(DESTINO, "jev_ausencia_%s_%s.json" % (modo, datetime.date.today().isoformat()))
    with io.open(arq, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    print(json.dumps({"resumo": r.get("resumo"), "medicao": r["medicao"]}, ensure_ascii=False, indent=1))
    print("gravado:", arq)
    return 0


if __name__ == "__main__":
    sys.exit(main())
