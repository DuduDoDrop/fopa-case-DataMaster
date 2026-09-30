# -*- coding: utf-8 -*-
"""
As licitações de folha que morreram — e por isso vão voltar.

    python 47_desertas.py [--max N] [--pausa S]

NÃO CHAMA MODELO. Só o endpoint de itens do PNCP.

POR QUE ISTO É ENTREGÁVEL E NÃO RELATÓRIO DE ERRO
  [[RN-30]]: *"Deserta é oportunidade, não fim."* Município cuja licitação de
  folha ficou deserta **vai relançar** — a folha continua precisando de banco,
  e o processo recomeça, normalmente com o valor mínimo revisto para baixo.

  Quem sabe primeiro chega antes, e chega sabendo **por quanto ninguém quis**.
  Essa é a informação que o concorrente não tem.

  Medido em 23/09/2026: das licitações encerradas do acervo, **um quarto
  morreu** — deserta ou fracassada. Não é cauda: é um em cada quatro.

A DIFERENÇA ENTRE "DESERTA" E "FRACASSADA", QUE MUDA O QUE FAZER
  · **Deserta** — ninguém apareceu. O preço mínimo, o prazo ou as exigências
    afastaram o mercado inteiro. O relançamento tende a vir mais barato.
  · **Fracassada** — apareceram e foram desclassificados. O problema é de
    habilitação, não de preço. O relançamento tende a vir com exigência
    diferente, e quem se habilita hoje tem vantagem.

  Tratar as duas igual perde metade do sinal.
"""
from __future__ import annotations

import argparse
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

from fopa import execucao, inventario, pncp  # noqa: E402

DESTINO = os.path.join(SAIDAS, "_desertas.json")
MORTAS = ("Deserto", "Fracassado")


def brl(v) -> str:
    if v is None:
        return "—"
    return ("R$ %s" % ("{:,.2f}".format(float(v))
                       .replace(",", "@").replace(".", ",").replace("@", ".")))


def main() -> int:
    _t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--pausa", type=float, default=0.3)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    # Ver o comentario em 45_retificacoes.py: leitura pelo `fopa/inventario`,
    # que conhece os 12 esquemas do acervo.
    alvos = [(pasta, d)
             for pasta, d in inventario.todos(AMOSTRAS, com_controle=True)]
    if a.max:
        alvos = alvos[: a.max]

    print("=" * 92)
    print("  OPORTUNIDADES — licitações de folha que morreram e vão voltar")
    print("=" * 92)

    achadas, encerradas, conferidas = [], 0, 0
    for i, (pasta, inv) in enumerate(alvos, 1):
        try:
            itens = pncp.Licitacao.de_controle(inv["controle"]).itens()
        except Exception:
            continue
        conferidas += 1
        for it in itens:
            sit = (it.get("situacaoCompraItemNome") or "").strip()
            if sit in ("Homologado",) + MORTAS:
                encerradas += 1
            if sit not in MORTAS:
                continue
            achadas.append({
                "pasta": pasta, "controle": inv["controle"],
                "orgao": inv.get("orgao") or inv.get("licitacao"),
                "uf": inv.get("uf"), "modalidade": inv.get("modalidade"),
                "situacao": sit,
                "valor_minimo": it.get("valorTotal"),
                "quantidade": it.get("quantidade"),
                "unidade": it.get("unidadeMedida"),
                "objeto": (inv.get("objeto") or "")[:150],
                "link": "https://pncp.gov.br/app/editais/%s/%s/%s" % (
                    inv["controle"][:14], inv["controle"][-4:],
                    str(int(inv["controle"].split("-1-")[1].split("/")[0]))),
            })
        if i % 40 == 0:
            print("   ... %d/%d" % (i, len(alvos)))
        time.sleep(a.pausa)

    por_sit = {}
    for x in achadas:
        por_sit.setdefault(x["situacao"], []).append(x)

    for sit in MORTAS:
        lst = por_sit.get(sit, [])
        if not lst:
            continue
        print()
        print("  %s — %d licitação(ões)" % (sit.upper(), len(lst)))
        print("  " + "-" * 90)
        print("  %-42s %-4s %-16s %s" % ("órgão", "UF", "valor mínimo", "link"))
        for x in sorted(lst, key=lambda y: -(y["valor_minimo"] or 0)):
            print("  %-42s %-4s %-16s %s"
                  % ((x["orgao"] or "")[:42], x["uf"] or "—",
                     brl(x["valor_minimo"]), x["link"]))

    print()
    print("  licitações conferidas ... %d" % conferidas)
    print("  encerradas .............. %d" % encerradas)
    print("  MORTAS .................. %d" % len(achadas))
    if encerradas:
        print("  taxa de mortalidade ..... %.0f%% das encerradas"
              % (100.0 * len(achadas) / encerradas))

    total = sum(x["valor_minimo"] or 0 for x in achadas)
    # DOIS TOTAIS, PORQUE SAO DUAS PERGUNTAS DIFERENTES.
    #
    # Medido em 23/09/2026: 15 orgaos aparecem mais de uma vez na lista --
    # Bento Goncalves e Esteio TRES vezes cada. Somar tudo conta a mesma folha
    # duas e tres vezes, e a diferenca nao e pequena: R$ 229,1 mi contra
    # R$ 173,6 mi, 24%.
    #
    # Os dois numeros estao certos e respondem coisas diferentes:
    #   por evento -> quantas vezes uma folha ficou sem banco
    #   por orgao  -> quanto mercado distinto existe ali
    # Apresentar o primeiro como "mercado" e inflar em 24%.
    por_orgao = {}
    for x in achadas:
        k = (x.get("orgao"), x.get("uf"))
        por_orgao[k] = max(por_orgao.get(k, 0), x["valor_minimo"] or 0)
    unico = sum(por_orgao.values())
    repetidos = len(achadas) - len(por_orgao)
    if total:
        print()
        print("  soma por EVENTO deserto ........ %s" % brl(total))
        print("     (quantas vezes uma folha ficou sem banco)")
        print("  soma por ÓRGÃO distinto ........ %s" % brl(unico))
        print("     (o mercado que existe ali — é este que vai para slide)")
        if repetidos:
            print()
            print("  %d licitação(ões) são RELANÇAMENTO do mesmo órgão." % repetidos)
            print("  Isso não é ruído: é a RN-30 medida. Eles voltam mesmo, e")
            print("  mais de uma vez.")
            for (o, uf), _ in sorted(por_orgao.items()):
                n = sum(1 for x in achadas
                        if (x.get("orgao"), x.get("uf")) == (o, uf))
                if n > 2:
                    print("     %-44s %s  %d vezes" % ((o or "")[:44], uf, n))
        print()
        print("  (é o piso do que esse lote vale quando voltar, não o teto)")

    execucao.registrar("47_desertas.py", _t0, conferidas=conferidas,
                       encerradas=encerradas, mortas=len(achadas),
                       brl_por_evento=round(total, 2),
                       brl_por_orgao=round(unico, 2), relancamentos=repetidos)
    json.dump({"medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "conferidas": conferidas, "encerradas": encerradas,
               "brl_por_evento": round(total, 2), "brl_por_orgao": round(unico, 2),
               "orgaos_distintos": len(por_orgao), "relancamentos": repetidos,
               "mortas": achadas},
              io.open(DESTINO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n  salvo: %s" % os.path.relpath(DESTINO, RAIZ))
    print("  custo em API de modelo: R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
