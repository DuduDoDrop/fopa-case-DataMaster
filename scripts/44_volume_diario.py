# -*- coding: utf-8 -*-
"""
Quantas licitações de folha são publicadas por dia, de verdade.

    python 44_volume_diario.py [--dias 14] [--ate 2026-09-23]

NÃO CHAMA MODELO. Varredura determinística do endpoint de publicação do PNCP.

POR QUE ESTE NÚMERO SUSTENTA TRÊS DECISÕES
  · o custo mensal (R$ 4,38 por licitação × volume)
  · se vale a Batch API, que troca 50% de desconto por latência
  · o dimensionamento da fila de revisão humana

  Sem ele, as três viram estimativa, e uma estimativa que confirma a tese é
  exatamente o que o projeto argumenta que não se deve aceitar.

O NÚMERO QUE ESTE SCRIPT JÁ PRODUZIU ESTÁ CONTAMINADO — 23/09/2026

  Ele pede `dataInicial` e `dataFinal` com 14 dias de distância, numa chamada
  só por modalidade. E o `consulta/v1` TRUNCA EM SILÊNCIO quando o intervalo é
  largo. Medido na modalidade 4:

      24 a 28/08, um dia por vez ....... 1.250 registros
      24 a 28/08, a semana de uma vez ..   170 registros
      somem ............................ 1.080  (86%)

  Sem erro, sem aviso, sem campo de truncamento: `200`, menos itens, paginação
  terminando normalmente.

  Então o "0,1 licitação de folha por dia útil" que este script publicou NÃO
  DEVE SER CITADO. Ele descreve o quanto a API quis devolver, não o mercado.
  CONVERTIDO em 23/09/2026: agora vai dia a dia e lê cada dia ATÉ o
  `totalPaginas` que a própria API declara, via `pncp.varrer_publicacao`.
  Dia incompleto entra no relatório como incompleto, em vez de sumir na média.

  O NÚMERO ANTIGO CONTINUA SEM VALER, porque nunca foi refeito com o código
  novo: converter o script não remede nada. E refazer custa caro — a conta
  honesta é ~14 dias × 6 modalidades × ~60 páginas × 3s = **~5 horas** por
  execução. A conta anterior no `BACKLOG.md` dizia ~25 min, e estava errada
  por um fator de 12, porque supunha ~5 páginas por dia — número que vinha da
  mesma paginação quebrada.

  Quanto rodar, e se vale, está em `BACKLOG.md` como decisão.
  Detalhe em [[PNCP - consulta por publicação]].

A ARMADILHA QUE ESTE ARQUIVO EXISTE PARA NÃO REPETIR
  A primeira tentativa de medir isto parou em 10 páginas por modalidade e
  devolveu "0,2% de folha, 0,3 por dia". O número parecia plausível — folha é
  raro mesmo — e estava errado: a coleta tinha batido no PRÓPRIO teto de paginação, não
  no fim dos dados.

  Um limite de segurança que silenciosamente vira o resultado é pior que não
  ter limite. Aqui o script **avisa** quando para por teto, e o relatório
  distingue "varri tudo" de "parei antes".
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import io
import json
import os
import statistics
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import escopo, pncp                                     # noqa: E402

DESTINO = os.path.join(RAIZ, "saidas", "_volume_diario.json")

# As modalidades em que folha já apareceu, mais as presenciais por segurança.
MODALIDADES = {
    6: "Pregão - Eletrônico",
    4: "Concorrência - Eletrônica",
    8: "Dispensa",
    12: "Credenciamento",
    7: "Pregão - Presencial",
    5: "Concorrência - Presencial",
}
TAM = 50            # o PNCP ignora tamanhoPagina > 50 e devolve 50 assim mesmo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=14)
    ap.add_argument("--ate", default="2026-09-23")
    ap.add_argument("--max-paginas", type=int, default=2000)
    # A PAUSA NAO E ARBITRARIA: E MEDIDA. Ver `pncp.PAUSA_VARREDURA`: com 0,5s o
    # `consulta/v1` devolve 429 na 10a chamada, com 1,5s na 8a, e com 3,0s
    # aguenta 12 sem falhar. As varreduras anteriores usavam 1,0 a 1,4 e
    # morriam nas paginas 13, 15 e 2.
    ap.add_argument("--pausa", type=float, default=pncp.PAUSA_VARREDURA)
    a = ap.parse_args()

    fim = dt.date.fromisoformat(a.ate)
    ini = fim - dt.timedelta(days=a.dias - 1)

    # SAÍDA SEM BUFFER. Uma varredura destas leva horas; com o stdout
    # bufferizado (que é o padrão quando se redireciona para arquivo), o
    # operador vê um arquivo vazio e não sabe se o processo morreu ou está
    # trabalhando. Progresso invisível é indistinguível de travamento.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    print("=" * 78)
    print("  VOLUME DIÁRIO DE LICITAÇÕES DE FOLHA")
    print("  janela: %s a %s (%d dias)" % (ini, fim, a.dias))
    print("=" * 78)

    por_dia = collections.Counter()
    por_mod = collections.Counter()
    bruto_mod = collections.Counter()
    truncou = []
    vistos = set()
    exemplos = []

    # DISJUNTOR. Se a PRIMEIRA página de duas modalidades seguidas falha, o
    # problema não é a modalidade: é o `consulta/v1` inteiro. Varrer as outras
    # quatro só produz mais quatro linhas de erro e gasta o tempo do operador
    # esperando um resultado que já se sabe vazio.
    #
    # SOBRE O MECANISMO: uma versão anterior deste comentário afirmava que o
    # `consulta/v1` "pune por volume acumulado", com janela de castigo longa.
    # A afirmação foi RETRATADA — sondando, o que aparece é `RemoteDisconnected`
    # e `TimeoutError`, nunca um `429` nem `Retry-After`. Não há evidência de
    # rate limit; há evidência de falha em nível de conexão, que tem outras
    # causas possíveis (balanceador, pool de banco, deploy).
    #
    # O que se OBSERVA, e só isso: 23/09/2026, fora por ~5h seguidas em 6
    # tentativas espaçadas; voltou com 200 em 0,6s; e caiu de novo na página 13
    # da primeira modalidade desta mesma varredura. O disjuntor continua certo
    # como comportamento. Descrever a causa não é.
    falhas_na_primeira = 0
    # DIA A DIA E ATE O FIM DAS PAGINAS.
    #
    # Ate 23/09/2026 este script pedia os 14 dias de uma vez e parava na
    # primeira pagina curta. Os dois defeitos somados: o `consulta/v1` entrega
    # menos em intervalo largo, E devolve pagina curta no MEIO do conjunto.
    # Num dia medido (24/08, Dispensa) isso deu 70 de 3.008 registros -- 2,3%.
    # O numero que este script publicou, "0,1 licitacao de folha por dia
    # util", nasceu dai.
    #
    # `pncp.varrer_publicacao` le ate o `totalPaginas` que a API declara, e
    # devolve `info["completa"]`. Um dia incompleto entra no relatorio como
    # incompleto, nao some na media.
    dias = [ini + dt.timedelta(days=k) for k in range((fim - ini).days + 1)]
    for cod, nome in MODALIDADES.items():
        if falhas_na_primeira >= 2:
            truncou.append("%s (nem tentada — disjuntor)" % nome)
            continue
        lidos_mod = 0
        for dia in dias:
            d = dia.strftime("%Y%m%d")
            itens, info = pncp.varrer_publicacao(d, d, cod, tamanho=TAM,
                                                 pausa=a.pausa,
                                                 max_paginas=a.max_paginas)
            if info.get("erro"):
                print("   %-26s %s: %s" % (nome, d, str(info["erro"])[:40]))
                truncou.append("%s em %s (%s)" % (nome, d, str(info["erro"])[:30]))
                if not itens:
                    falhas_na_primeira += 1
            elif not info.get("completa"):
                truncou.append("%s em %s (%s de %s páginas)"
                               % (nome, d, info.get("paginas_lidas"),
                                  info.get("total_paginas")))
            lidos_mod += len(itens)
            bruto_mod[nome] += len(itens)
            for it in itens:
                ok, _ = escopo.avaliar(it.get("objetoCompra") or "")
                ctrl = it.get("numeroControlePNCP")
                if ok and ctrl and ctrl not in vistos:
                    vistos.add(ctrl)
                    por_dia[(it.get("dataPublicacaoPncp") or "")[:10]] += 1
                    por_mod[nome] += 1
                    if len(exemplos) < 12:
                        exemplos.append((it.get("dataPublicacaoPncp") or "")[:10]
                                        + " · " + (it.get("objetoCompra") or "")[:74])
            time.sleep(a.pausa)
        print("   %-26s %6d varridos · %3d de folha"
              % (nome, bruto_mod[nome], por_mod[nome]))
        time.sleep(a.pausa)

    total_bruto = sum(bruto_mod.values())
    n = len(vistos)
    print()
    print("  varridos (bruto) ... %d" % total_bruto)
    print("  de folha ........... %d" % n)
    if total_bruto:
        print("  taxa base .......... %.3f%% (1 em %d)"
              % (100.0 * n / total_bruto, round(total_bruto / n) if n else 0))

    if truncou:
        print()
        print("  ATENÇÃO — a varredura NÃO foi exaustiva:")
        for t in truncou:
            print("   · %s" % t)
        print("  Os números acima são piso, não total.")
        if falhas_na_primeira >= 2:
            print()
            print("  O `consulta/v1` parou de responder no meio da varredura.")
            print("  Falha em nível de CONEXÃO (RemoteDisconnected/TimeoutError),")
            print("  sem 429 e sem Retry-After — não há evidência de rate limit,")
            print("  e este programa não afirma causa. O `pncp/v1` costuma seguir")
            print("  respondendo. Ver [[Disponibilidade do PNCP]].")
    else:
        print("\n  Varredura exaustiva: todas as modalidades chegaram ao fim dos dados.")

    serie = [por_dia.get((ini + dt.timedelta(days=i)).isoformat(), 0)
             for i in range(a.dias)]
    print()
    print("  por dia de publicação:")
    for i, v in enumerate(serie):
        d = ini + dt.timedelta(days=i)
        fds = " (fim de semana)" if d.weekday() >= 5 else ""
        print("   %s  %-24s %2d%s" % (d, "#" * min(v, 24), v, fds))

    uteis = [v for i, v in enumerate(serie)
             if (ini + dt.timedelta(days=i)).weekday() < 5]
    print()
    if serie:
        print("  média por dia corrido .. %.1f" % (sum(serie) / len(serie)))
    if uteis:
        print("  média por dia ÚTIL ..... %.1f" % (sum(uteis) / len(uteis)))
        print("  mediana (dias úteis) ... %.0f" % statistics.median(uteis))
        print("  máximo num dia ......... %d" % max(serie))

    if exemplos:
        print("\n  exemplos do que entrou:")
        for e in exemplos:
            print("   %s" % e)

    json.dump({"medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "janela": [str(ini), str(fim)], "dias": a.dias,
               "bruto": total_bruto, "de_folha": n,
               "por_dia": dict(por_dia), "por_modalidade": dict(por_mod),
               "bruto_por_modalidade": dict(bruto_mod),
               "varredura_truncada": truncou},
              io.open(DESTINO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n  salvo: %s" % os.path.relpath(DESTINO, RAIZ))
    print("  custo em API de modelo: R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
