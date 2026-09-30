# -*- coding: utf-8 -*-
"""
Quais termos de busca valem a profundidade, e quais so trazem ruido.

    python 56_densidade_termos.py [--paginas 10] [--pausa 1.5]

NAO CHAMA MODELO.

POR QUE ESTE SCRIPT EXISTE
  Em 23/09/2026 medi que "a densidade de folha nao cai com a pagina" -- 87%
  ate a pagina 16 -- e usei isso para subir o teto de paginacao de 2 para 10.
  A medicao estava certa e a conclusao, incompleta: ela usou UM termo.

  Na coleta seguinte, com os 7 termos e 10 paginas cada, a taxa despencou:
  61 de 358 objetos eram de folha (17%), contra ~75% antes. O corpus foi de
  509 para 748 registros e a proporcao no escopo caiu para 39%.

  A densidade nao cai com a PAGINA. Cai com o TERMO. E ate agora ninguem tinha
  medido termo a termo -- todos entraram na lista por parecerem razoaveis.

O QUE A MEDICAO DECIDE
  Um termo com densidade baixa nao e inutil: ele pode ser o unico que alcanca
  uma familia de objetos (foi o caso de "instituicao bancaria"). O que a
  medicao permite e escolher a PROFUNDIDADE por termo, em vez de uma so para
  todos -- gastar 10 paginas onde 9 em 10 sao folha, e 2 onde 1 em 10 e.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import escopo, pncp                                     # noqa: E402

DESTINO = os.path.join(RAIZ, "saidas", "_densidade_termos.json")

# os termos que o projeto usa hoje, nos dois programas
TERMOS = [
    "cessão onerosa folha de pagamento",
    "folha de pagamento servidores instituição financeira",
    "gestão de consignações folha de pagamento",
    "administração da folha de pagamento",
    "sistema de folha de pagamento",
    "processamento da folha de pagamento",
    "folha de pagamento instituição bancária",
    # entraram em 23/09 pela varredura de agosto; ainda SEM densidade
    # medida -- e para isso que este script existe
    "créditos da folha de pagamento",
    # ERRO DA RODADA ANTERIOR, PEGO PELA MEDICAO SEGUINTE.
    # Adicionei "creditos da folha de pagamento" achando que cobriria Aguas de
    # Chapeco, Pitanga e Bonito. Nao cobre: os tres escrevem "creditos
    # PROVENIENTES da folha de pagamento", e a busca do PNCP casa a frase --
    # a palavra no meio quebra. A varredura de agosto mostrou os tres ainda
    # perdidos, mais Caninde/CE e Bauru/SP com a mesma redacao.
    #
    # As duas frases convivem porque sao conjuntos distintos, e as duas tem
    # densidade de 100% no corpus: 89 ocorrencias da primeira, 109 da segunda,
    # todas dentro do escopo.
    "créditos provenientes da folha de pagamento",
    # Piedade/SP nao diz "folha" no comeco: "CENTRALIZACAO DOS SERVICOS DE
    # PAGAMENTO DAS REMUNERACOES, SALARIOS E PROVENTOS DOS SERVIDORES". Esta
    # frase NAO tem densidade medida -- nao ha nenhuma ocorrencia no corpus,
    # justamente porque a busca nunca trouxe esses casos. Entra como aposta
    # declarada, e a proxima varredura mede.
    "centralização dos serviços de pagamento",
    "empresa bancária folha de pagamento",
    "folha salarial instituição financeira",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paginas", type=int, default=10)
    ap.add_argument("--pausa", type=float, default=1.5)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("=" * 96)
    print("  DENSIDADE POR TERMO — %d páginas de 50 por termo" % a.paginas)
    print("=" * 96)
    print()

    linhas = []
    vistos_global: set[str] = set()
    for termo in TERMOS:
        vistos, folha, bruto = set(), 0, 0
        por_pagina = []
        exclusivos = 0
        for pag in range(1, a.paginas + 1):
            q = urllib.parse.urlencode({
                "q": termo, "tipos_documento": "edital", "ordenacao": "-data",
                "pagina": pag, "tam_pagina": 50, "status": "todos"})
            try:
                r = pncp._get(pncp.BASE_BUSCA + "?" + q)
            except Exception:                                     # noqa: BLE001
                por_pagina.append(None)
                time.sleep(a.pausa * 2)
                continue
            itens = r.get("items") or []
            if not itens:
                break
            n = 0
            for it in itens:
                bruto += 1
                ctrl = it.get("numero_controle_pncp")
                if escopo.avaliar(it.get("description") or "")[0]:
                    folha += 1
                    n += 1
                    if ctrl:
                        vistos.add(ctrl)
                        if ctrl not in vistos_global:
                            exclusivos += 1
            por_pagina.append(n)
            if len(itens) < 50:
                break
            time.sleep(a.pausa)
        vistos_global |= vistos
        dens = 100.0 * folha / bruto if bruto else 0.0
        linhas.append({"termo": termo, "bruto": bruto, "folha": folha,
                       "densidade": round(dens, 1), "unicas": len(vistos),
                       "exclusivas": exclusivos, "por_pagina": por_pagina})
        print("  %-52s %4d/%4d = %5.1f%%   %3d exclusivas"
              % (termo[:52], folha, bruto, dens, exclusivos))
        print("       por página: %s"
              % " ".join(("--" if x is None else "%2d" % x) for x in por_pagina))

    print()
    linhas.sort(key=lambda x: -x["densidade"])
    print("  %-52s %8s %11s" % ("ranking por densidade", "densid.", "exclusivas"))
    print("  " + "-" * 76)
    for x in linhas:
        print("  %-52s %7.1f%% %11d" % (x["termo"][:52], x["densidade"],
                                        x["exclusivas"]))
    print()
    print("  DENSIDADE alta = o termo acha folha e pouco lixo.")
    print("  EXCLUSIVAS = licitações que SÓ esse termo trouxe. Um termo de")
    print("  densidade baixa e exclusivas altas continua valendo: ele alcança")
    print("  uma família de objetos que os outros não alcançam.")
    print("  Os dois juntos decidem a PROFUNDIDADE de cada termo.")

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps(
        {"medido_em": time.strftime("%Y-%m-%d"), "paginas": a.paginas,
         "termos": linhas, "unicas_no_total": len(vistos_global)},
        ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_densidade_termos.json · custo R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
