# -*- coding: utf-8 -*-
"""
Censo dos itens e resultados das licitações do acervo — direto na API do PNCP.

    python 42_censo_itens.py [--max N] [--pausa S]

NÃO CHAMA MODELO. Só a API pública do PNCP, que é gratuita.

POR QUE ISTO EXISTE
  As notas `PNCP - itens` e `PNCP - resultados` carregavam sete perguntas em
  aberto desde que foram escritas, todas da forma *"isto sempre acontece ou foi
  coincidência das 11 licitações observadas?"*:

    · contrato de folha vem sempre como item único, ou há lotes por secretaria?
    · qual a lista COMPLETA de `situacaoCompraItemNome`?
    · o endpoint de resultados devolve objeto ou lista?
    · licitação deserta ou fracassada aparece em resultados, ou só em itens?

  Com 11 licitações nenhuma dessas tinha resposta honesta. Com 170, todas têm —
  e a diferença entre "nas observadas" e "em 170" é exatamente o que separa uma
  observação de uma regra que se pode escrever no código.

  O custo é uma varredura de API pública. A única razão de não ter sido feito
  antes é que o acervo não existia.
"""
from __future__ import annotations

import argparse
import collections
import glob
import io
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")
sys.path.insert(0, AQUI)

from fopa import pncp                                             # noqa: E402

DESTINO = os.path.join(SAIDAS, "_censo_itens.json")


def controles() -> list[tuple[str, str]]:
    """(pasta, numero_controle_pncp) de tudo que tem inventário."""
    out = []
    for f in sorted(glob.glob(os.path.join(AMOSTRAS, "*", "_inventario.json"))):
        pasta = os.path.basename(os.path.dirname(f))
        if pasta.startswith("_"):
            continue
        d = json.load(io.open(f, encoding="utf-8"))
        c = (d.get("controle") or "").strip()
        if c:
            out.append((pasta, c))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0, help="0 = todas")
    ap.add_argument("--pausa", type=float, default=0.4)
    a = ap.parse_args()

    alvos = controles()
    if a.max:
        alvos = alvos[: a.max]
    print("=" * 78)
    print("  CENSO DE ITENS E RESULTADOS — %d licitações" % len(alvos))
    print("=" * 78)

    n_itens = collections.Counter()          # quantos itens por licitação
    situacoes = collections.Counter()
    tipos_resultado = collections.Counter()  # objeto, lista, vazio, erro
    criterios = collections.Counter()
    com_resultado = sem_resultado = 0
    falhas = []
    registros = []

    for i, (pasta, ctrl) in enumerate(alvos, 1):
        try:
            lic = pncp.Licitacao.de_controle(ctrl)
        except Exception as e:                                    # noqa: BLE001
            falhas.append("%s :: controle ilegível: %s" % (pasta[:40], e))
            continue

        try:
            itens = lic.itens()
        except Exception as e:                                    # noqa: BLE001
            falhas.append("%s :: itens: %s" % (pasta[:40], str(e)[:60]))
            continue

        itens = itens if isinstance(itens, list) else [itens]
        n_itens[len(itens)] += 1
        reg = {"pasta": pasta, "controle": ctrl, "n_itens": len(itens), "itens": []}

        for it in itens:
            sit = (it.get("situacaoCompraItemNome") or "(sem situação)").strip()
            situacoes[sit] += 1
            crit = (it.get("criterioJulgamentoNome") or "(sem critério)").strip()
            criterios[crit] += 1
            num = it.get("numeroItem")
            linha = {"numero": num, "situacao": sit, "criterio": crit,
                     "valor_total": it.get("valorTotal"),
                     "valor_unitario": it.get("valorUnitarioEstimado")}

            try:
                # O RETORNO CRU, nao o normalizado. `lic.resultados()` ja
                # converte objeto em lista -- que e o comportamento certo para
                # quem consome, e exatamente o que apaga o dado que esta
                # pergunta quer: QUAL forma a API devolve de fato.
                r = pncp._get(lic._u("/itens/%s/resultados" % num))
                if isinstance(r, list):
                    tipos_resultado["lista de %d" % len(r)] += 1
                    linha["resultado"] = "lista(%d)" % len(r)
                    if r:
                        com_resultado += 1
                    else:
                        sem_resultado += 1
                elif isinstance(r, dict):
                    tipos_resultado["objeto"] += 1
                    linha["resultado"] = "objeto"
                    com_resultado += 1
                else:
                    tipos_resultado["vazio/None"] += 1
                    sem_resultado += 1
            except Exception as e:                                # noqa: BLE001
                msg = str(e)[:40]
                tipos_resultado["erro: %s" % msg[:24]] += 1
                linha["resultado"] = "erro"
                sem_resultado += 1
            time.sleep(a.pausa)

            reg["itens"].append(linha)

        registros.append(reg)
        if i % 20 == 0:
            print("  ... %d/%d" % (i, len(alvos)))
        time.sleep(a.pausa)

    # ------------------------------------------------------------ relatório
    tot_lic = sum(n_itens.values())
    tot_itens = sum(n * c for n, c in n_itens.items())
    print("\n  licitações consultadas ..... %d" % tot_lic)
    print("  itens no total ............. %d" % tot_itens)
    print()
    print("  ITENS POR LICITAÇÃO — a pergunta era 'é sempre item único?'")
    for n, c in sorted(n_itens.items()):
        marca = "  <-- item único" if n == 1 else ""
        print("   %3d licitação(ões) com %2d item(ns)%s" % (c, n, marca))
    if tot_lic:
        um = n_itens.get(1, 0)
        print("   item único: %d de %d (%.0f%%)" % (um, tot_lic, 100.0 * um / tot_lic))

    print("\n  situacaoCompraItemNome — a LISTA COMPLETA observada")
    for s, c in situacoes.most_common():
        print("   %5d  %s" % (c, s))

    print("\n  criterioJulgamentoNome")
    for s, c in criterios.most_common():
        print("   %5d  %s" % (c, s))

    print("\n  forma do retorno de /resultados")
    for s, c in tipos_resultado.most_common(10):
        print("   %5d  %s" % (c, s))
    print("   com resultado: %d · sem: %d" % (com_resultado, sem_resultado))

    if falhas:
        print("\n  %d falha(s):" % len(falhas))
        for f in falhas[:10]:
            print("   · %s" % f)

    json.dump({"medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "licitacoes": tot_lic, "itens": tot_itens,
               "itens_por_licitacao": {str(k): v for k, v in n_itens.items()},
               "situacoes": dict(situacoes), "criterios": dict(criterios),
               "formas_resultado": dict(tipos_resultado),
               "falhas": falhas, "registros": registros},
              io.open(DESTINO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n  salvo: %s" % os.path.relpath(DESTINO, RAIZ))
    print("  custo em API de modelo: R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
