# -*- coding: utf-8 -*-
"""
Quanto o PNCP fica de pe, medido — nao "a API cai".

    python 65_disponibilidade.py [--minutos 10] [--pausa 20]

NAO CHAMA MODELO. Sonda os tres endpoints do PNCP e grava latencia e falha de
cada tentativa.

POR QUE ISTO EXISTE
  O projeto sabe dizer "a `api/pncp/v1` cai" e "a `consulta/v1` e fragil", e
  isso esta em varias notas. O que nao havia era NUMERO: quantas tentativas
  falham, em que proporcao, com que latencia, e se os tres endpoints caem
  juntos ou separados.

  A diferenca importa para o desenho. Se os tres caem juntos, e o portal; se
  so um cai, da para seguir trabalhando pelos outros -- foi exatamente o que
  aconteceu em 23/09, quando o download parou e a busca continuou servindo.

O QUE ESTA SONDA NAO E
  Nao e monitoramento. Ela roda por alguns minutos, grava o que viu e sai. Uma
  serie de verdade precisa de dias, e quem a constroi e o `_execucoes.jsonl`,
  que ja registra toda execucao real. Esta sonda responde uma pergunta menor e
  imediata: **agora, o que esta de pe?**

CUIDADO QUE VALE DIZER
  Sondar e trafego. A pausa padrao de 20s existe para a medicao nao virar
  carga -- em 10 minutos sao 30 requisicoes por endpoint, o que e menos do que
  uma unica pagina de varredura. Medir disponibilidade derrubando o servico
  seria o cumulo.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

DESTINO = os.path.join(RAIZ, "saidas", "_disponibilidade.json")
UA = "FOPA/0.1 (estudo de viabilidade; monitoramento de licitacoes de folha)"

# Um alvo barato por endpoint: o menor resultado possivel, para a sonda medir
# disponibilidade e nao volume.
ALVOS = {
    "api/search": ("https://pncp.gov.br/api/search/"
                   "?q=folha&tipos_documento=edital&pagina=1&tam_pagina=1"),
    "api/pncp/v1": ("https://pncp.gov.br/api/pncp/v1/orgaos/29052875000119"
                    "/compras/2026/25/arquivos"),
    "api/consulta/v1": ("https://pncp.gov.br/api/consulta/v1/contratacoes/"
                        "publicacao?dataInicial=20260824&dataFinal=20260824"
                        "&codigoModalidadeContratacao=8&pagina=1&tamanhoPagina=10"),
}


def sondar(url: str, timeout: int = 25) -> tuple[str, float, str]:
    """(estado, segundos, detalhe). Estado: `ok`, `http`, ou o nome do erro."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(2048)
            return "ok", time.time() - t0, str(r.status)
    except urllib.error.HTTPError as e:
        return "http", time.time() - t0, str(e.code)
    except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError) as e:
        nome = type(e).__name__
        interno = getattr(e, "reason", None)
        if interno is not None:
            nome = type(interno).__name__ if not isinstance(interno, str) else nome
        return nome, time.time() - t0, str(e)[:70]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutos", type=float, default=10.0)
    ap.add_argument("--pausa", type=float, default=20.0)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    fim = time.time() + a.minutos * 60
    registros: list[dict] = []
    print("=" * 96)
    print("  DISPONIBILIDADE DO PNCP — sonda de %.0f min, uma rodada a cada %.0fs"
          % (a.minutos, a.pausa))
    print("  %d endpoints · alvo minimo em cada um, para medir e nao carregar"
          % len(ALVOS))
    print("=" * 96)
    print()
    print("  %-8s %-16s %-16s %-16s" % ("hora", *ALVOS))
    print("  " + "-" * 62)

    while time.time() < fim:
        linha = {"em": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "alvos": {}}
        celulas = []
        for nome, url in ALVOS.items():
            estado, seg, detalhe = sondar(url)
            linha["alvos"][nome] = {"estado": estado, "segundos": round(seg, 2),
                                    "detalhe": detalhe}
            celulas.append("%-16s" % (("%.1fs" % seg) if estado == "ok"
                                      else estado[:15]))
        registros.append(linha)
        print("  %-8s %s" % (time.strftime("%H:%M:%S"), " ".join(celulas)))
        if time.time() < fim:
            time.sleep(a.pausa)

    if not registros:
        print("\n  nenhuma rodada — janela curta demais.")
        return 1

    print()
    print("-" * 96)
    n = len(registros)
    resumo = {}
    for nome in ALVOS:
        estados = [r["alvos"][nome]["estado"] for r in registros]
        oks = [r["alvos"][nome]["segundos"] for r in registros
               if r["alvos"][nome]["estado"] == "ok"]
        from collections import Counter
        c = Counter(e for e in estados if e != "ok")
        pct = 100.0 * len(oks) / n
        resumo[nome] = {"rodadas": n, "ok": len(oks), "pct_ok": round(pct, 1),
                        "latencia_mediana": (round(sorted(oks)[len(oks) // 2], 2)
                                             if oks else None),
                        "falhas": dict(c)}
        print("  %-16s %3d de %3d de pé (%.0f%%)" % (nome, len(oks), n, pct), end="")
        if oks:
            print(" · mediana %.1fs" % sorted(oks)[len(oks) // 2], end="")
        if c:
            print(" · %s" % ", ".join("%s x%d" % (k, v) for k, v in c.most_common()),
                  end="")
        print()

    # CAEM JUNTOS OU SEPARADOS? e o que decide se da para seguir trabalhando.
    print()
    juntos = sum(1 for r in registros
                 if all(v["estado"] != "ok" for v in r["alvos"].values()))
    algum = sum(1 for r in registros
                if any(v["estado"] != "ok" for v in r["alvos"].values()))
    print("  rodadas com ALGUM endpoint fora .... %d de %d" % (algum, n))
    print("  rodadas com TODOS fora ............. %d de %d" % (juntos, n))
    if algum and not juntos:
        print()
        print("  Nenhuma rodada derrubou os três. A queda é POR ENDPOINT, e isso")
        print("  muda o desenho: dá para seguir trabalhando pelos que respondem,")
        print("  como em 23/09, quando o download parou e a busca continuou.")
    elif juntos:
        print()
        print("  Houve rodada com os três fora: aí é o portal, não o endpoint.")

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps(
        {"medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
         "minutos": a.minutos, "pausa": a.pausa, "rodadas": n,
         "resumo": resumo, "rodadas_todos_fora": juntos,
         "rodadas_algum_fora": algum, "registros": registros},
        ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_disponibilidade.json · custo R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
