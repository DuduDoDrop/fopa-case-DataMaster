# -*- coding: utf-8 -*-
"""
Recall da BUSCA contra a varredura completa do mes.

    python 51_recall_busca.py [--mes 2026-08] [--pausa 3.0]

NAO CHAMA MODELO.

A PERGUNTA, E POR QUE ELA E DIFERENTE DAS OUTRAS
  O corpus e montado pelo `api/search`, que casa PALAVRA. Medir a qualidade
  dele contra os proprios resultados e circular: o vocabulario se autoconfirma.
  Esta e a unica medicao do projeto que usa uma fonte INDEPENDENTE -- o
  `consulta/v1`, que devolve TUDO o que foi publicado num intervalo, sem
  termo de busca.

  Varre tudo, aplica o MESMO filtro de escopo em cima, e compara.

O QUE ESTE NUMERO MEDE, E O QUE NAO MEDE
  MEDE   -- recall do VOCABULARIO de busca. Uma licitacao que a varredura
            acha e o corpus nao tem e uma palavra que faltou.
  NAO MEDE -- recall do FILTRO DE ESCOPO. Os dois lados usam `escopo.avaliar`,
            entao uma licitacao de folha que o filtro recusa esta ausente dos
            DOIS lados e nao aparece aqui. Isso precisa ficar dito: e a mesma
            armadilha do censo, contar o que se tem e nao o que falta.

A ARMADILHA QUE QUASE INVALIDOU ESTA MEDICAO
  O `consulta/v1` TRUNCA EM SILENCIO quando o intervalo de datas e largo.
  Medido em 23/09/2026, modalidade 4 (Concorrencia Eletronica):

      24 a 28/08, um dia por vez ....... 1.250 registros
      24 a 28/08, a semana de uma vez ..   170 registros
      licitacoes que somem .............. 1.080  (86%)

  Sem erro, sem aviso, sem campo dizendo que truncou: ele devolve menos e
  para. Sao Lourenco do Sul/RS aparece na consulta do dia 26 e NAO aparece na
  consulta do mes que contem o dia 26.

  Por isso esta varredura vai DIA A DIA e soma. E mais lenta -- 31 dias vezes
  6 modalidades -- e e a unica forma de o denominador ser real.

  A primeira versao deste script varria o mes de uma vez e achou 1 licitacao
  de folha em agosto, contra 31 que a busca por palavra ja tinha. A conclusao
  natural seria "a busca e melhor que a varredura". A conclusao certa e que a
  varredura nao estava varrendo.

A SEGUNDA ARMADILHA, E ELA E PIOR -- medida em 23/09/2026
  Ir dia a dia nao bastou. O `consulta/v1` devolve PAGINA CURTA NO MEIO do
  conjunto, e toda paginacao do mundo para na primeira pagina curta, porque e
  assim que uma API normal diz "acabou". Dispensas de 24/08/2026:

      pag  1 ->  50 itens   (totalRegistros=3008, totalPaginas=61)
      pag  2 ->  20 itens   <- curta, e NAO e o fim
      pag  3 ->  50 itens
      pag 16, 22, 27, 28 -> curtas tambem

  Parando na pagina 2: **70 de 3.008 registros**, 2,3%. Lendo ate a pagina 61:
  **2.878 distintos**, 41 vezes mais. E o numero de paginas entregues variava
  entre execucoes IDENTICAS -- 70 numa, 210 noutra -- porque as curtas caem em
  lugares diferentes. Uma medicao que depende disso nao e reprodutivel.

  O `totalPaginas` estava na resposta o tempo todo. O codigo nunca leu.

  Consequencia direta: o recall de 79,3% medido na manha de 23/09 tinha um
  denominador que era uma fracao da realidade. Um denominador menor INFLA o
  recall. Aquele numero nao vale, e esta marcado como invalido no vault.

POR QUE AGORA SE AMOSTRA DIAS (--dias N)
  Ler um mes inteiro COMPLETO custa ~61 paginas por dia por modalidade: horas.
  A versao anterior "varria o mes" so porque parava cedo. Poucos dias lidos
  ATE O FIM valem mais que trinta pela metade -- o denominador fica menor, e
  fica REAL. A semente e fixa, entao a amostra se repete.
"""
from __future__ import annotations

import argparse
import calendar
import random
import datetime as dt
import io
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import escopo, execucao, pncp                                     # noqa: E402

DESTINO = os.path.join(RAIZ, "saidas", "_recall_busca.json")
CORPUS = os.path.join(RAIZ, "saidas", "_corpus_escopo.json")
MODALIDADES = {
    6: "Pregão - Eletrônico",
    4: "Concorrência - Eletrônica",
    8: "Dispensa",
    12: "Credenciamento",
    7: "Pregão - Presencial",
    5: "Concorrência - Presencial",
}
TAM = 50


def corpus_do_mes(mes: str) -> dict[str, dict]:
    """O que a BUSCA achou, publicado no mes. Chave: numero de controle."""
    if not os.path.isfile(CORPUS):
        return {}
    fora = {}
    for x in json.load(io.open(CORPUS, encoding="utf-8"))["registros"]:
        if x.get("dentro") is False:
            continue
        if str(x.get("publicado_em") or "")[:7] == mes:
            c = x.get("controle")
            if c:
                fora[c] = x
    return fora


def main() -> int:
    _t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", default="2026-08", help="AAAA-MM")
    # A PAUSA NAO E ARBITRARIA: E MEDIDA. Ver `pncp.PAUSA_VARREDURA`: com 0,5s o
    # `consulta/v1` devolve 429 na 10a chamada, com 1,5s na 8a, e com 3,0s
    # aguenta 12 sem falhar. As varreduras anteriores usavam 1,0 a 1,4 e
    # morriam nas paginas 13, 15 e 2.
    ap.add_argument("--pausa", type=float, default=pncp.PAUSA_VARREDURA)
    ap.add_argument("--max-paginas", type=int, default=3000)
    ap.add_argument("--dias", type=int, default=0,
                    help="amostrar N dias do mês, em vez de todos")
    ap.add_argument("--semente", type=int, default=20260823,
                    help="semente da amostra de dias — fixa, para repetir")
    ap.add_argument("--modalidades", default="",
                    help="códigos separados por vírgula; vazio = todas")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    ano, mes = int(a.mes[:4]), int(a.mes[5:7])
    ini = dt.date(ano, mes, 1)
    fim = dt.date(ano, mes, calendar.monthrange(ano, mes)[1])

    print("=" * 92)
    print("  RECALL DA BUSCA — %s (%s a %s)" % (a.mes, ini, fim))
    print("=" * 92)

    achados: dict[str, dict] = {}
    bruto = 0
    truncou = []
    falhas_primeira = 0

    todos = [ini + dt.timedelta(days=k) for k in range((fim - ini).days + 1)]
    if a.dias and a.dias < len(todos):
        # AMOSTRAR DIAS, EM VEZ DE VARRER TODOS PELA METADE.
        # Ler o mes inteiro COMPLETO custa ~61 paginas por dia por modalidade
        # (medido em 24/08/2026), o que da horas. A versao anterior "varria o
        # mes" so porque parava na primeira pagina curta -- lia 2,3% e chamava
        # de mes. Poucos dias lidos ATE O FIM valem mais que trinta pela
        # metade: o denominador fica menor, mas fica REAL.
        rnd = random.Random(a.semente)
        dias = sorted(rnd.sample(todos, a.dias))
    else:
        dias = todos
    # ESCOLHER MODALIDADE E O QUE TORNA A MEDICAO VIAVEL.
    #
    # O custo de um dia varia 80x entre modalidades, medido em 2026-08:
    #   Dispensa .............. ~3.000 registros/dia  (61 paginas)
    #   Pregao - Eletronico ...   ~550 registros/dia  (11 paginas)
    #   Concorrencia - Elet. ..    ~94 registros/dia  ( 2 paginas)
    #   Credenciamento ........    ~36 registros/dia  ( 1 pagina)
    #
    # E a taxa de folha e ~0,12% dos registros. Para o recall ter n suficiente
    # e preciso LER MUITO -- e ler o mes inteiro das tres baratas custa ~22
    # min, contra ~1h35 so da Dispensa. Mes inteiro de tres modalidades da um
    # denominador REAL para a maior parte do mercado; tres dias de todas as
    # seis, como saiu na primeira tentativa, deu n=5 e nao decide nada.
    escolhidas = MODALIDADES
    if a.modalidades:
        pedidos = {int(x) for x in a.modalidades.split(",") if x.strip()}
        escolhidas = {c: n for c, n in MODALIDADES.items() if c in pedidos}
        print("  modalidades: %s" % ", ".join(escolhidas.values()))
        print()
    print("  varrendo %d de %d dia(s) x %d modalidade(s), dia a dia"
          % (len(dias), len(todos), len(escolhidas)))
    if len(dias) < len(todos):
        print("  amostra de dias (semente %d): %s"
              % (a.semente, ", ".join(d.strftime("%d") for d in dias)))
    print("  cada dia e lido ATE `totalPaginas` — pagina curta NAO e fim")
    print()
    incompletas = []
    for cod, nome in escolhidas.items():
        if falhas_primeira >= 2:
            truncou.append("%s (nem tentada — disjuntor)" % nome)
            continue
        nesta, pags, decl, lidos, dias_ok = 0, 0, 0, 0, 0
        for dia in dias:
            di = dia.strftime("%Y%m%d")
            itens, info = pncp.varrer_publicacao(di, di, cod, tamanho=TAM,
                                                 pausa=a.pausa,
                                                 max_paginas=a.max_paginas)
            if info.get("erro"):
                print("   %-24s %s: %s" % (nome, di, str(info["erro"])[:40]))
                truncou.append("%s em %s (%s)" % (nome, di, str(info["erro"])[:30]))
                if not itens:
                    falhas_primeira += 1
            if info.get("completa"):
                dias_ok += 1
            else:
                incompletas.append("%s em %s (%s de %s páginas)"
                                   % (nome, di, info.get("paginas_lidas"),
                                      info.get("total_paginas")))
            pags += info.get("paginas_lidas") or 0
            decl += info.get("total_registros") or 0
            bruto += len(itens)
            lidos += len(itens)
            for it in itens:
                ok, _ = escopo.avaliar(it.get("objetoCompra") or "")
                ctrl = it.get("numeroControlePNCP")
                if ok and ctrl:
                    achados[ctrl] = {
                        "controle": ctrl,
                        "objeto": (it.get("objetoCompra") or "")[:220],
                        "modalidade": nome,
                        "publicado_em": (it.get("dataPublicacaoPncp") or "")[:10],
                        "municipio": ((it.get("unidadeOrgao") or {}).get("municipioNome")),
                        "uf": ((it.get("unidadeOrgao") or {}).get("ufSigla")),
                    }
                    nesta += 1
            time.sleep(a.pausa)
        # `lidos` e DESTA modalidade; `bruto` e o acumulado de todas. Trocar
        # um pelo outro faz a linha dizer "1.789 lidos de 282 declarados",
        # que e impossivel e foi o que ela dizia na primeira versao.
        # COMPLETUDE SE MEDE EM PAGINA, NAO EM REGISTRO.
        # A primeira versao comparava registros lidos com `totalRegistros` e
        # marcava INCOMPLETA a 93%. Nao era: o PNCP repete registro entre
        # paginas, e a deduplicacao por numero de controle come de 4% a 7%
        # (2.878 distintos para 3.008 declarados, num dia conferido a parte).
        # O sinal certo e ter lido todas as paginas que a API declarou.
        print("   %-26s %4d páginas · %6d lidos de %6d declarados"
              " · %d/%d dia(s) completo(s) · %d de folha"
              % (nome, pags, lidos, decl, dias_ok, len(dias), nesta))
        if lidos < decl:
            print("   %-26s (os %d a menos são duplicata entre páginas — %.1f%%)"
                  % ("", decl - lidos, 100.0 * (decl - lidos) / decl))
    truncou.extend(incompletas)

    corpus = corpus_do_mes(a.mes)
    faltando = {k: v for k, v in achados.items() if k not in corpus}
    extras = [k for k in corpus if k not in achados]

    print()
    print("  registros varridos (bruto) ....... %d" % bruto)
    print("  de folha, pela varredura ......... %d" % len(achados))
    print("  de folha, no corpus (busca) ...... %d" % len(corpus))
    print("  a varredura achou e a busca não .. %d" % len(faltando))
    print("  a busca tem e a varredura não .... %d" % len(extras))
    print()

    if truncou:
        print("  ATENÇÃO — a varredura NÃO foi exaustiva:")
        for t in truncou:
            print("   · %s" % t)
        print("  O recall abaixo é TETO, não valor: o denominador está incompleto.")
        print()

    if achados:
        rec = 100.0 * (len(achados) - len(faltando)) / len(achados)
        print("  RECALL DA BUSCA: %d de %d = %.1f%%"
              % (len(achados) - len(faltando), len(achados), rec))
    else:
        rec = None
        print("  varredura não devolveu nenhuma licitação de folha — nada a comparar")
    print()

    if faltando:
        print("  O QUE A BUSCA PERDEU (até 20):")
        for v in list(faltando.values())[:20]:
            print("   %s  %-22s %s" % (v["publicado_em"], (v["municipio"] or "?")[:22],
                                       v["objeto"][:60]))
        print()
        # NAO E VERDADE QUE CADA PERDIDA SEJA UMA PALAVRA QUE FALTA.
    # Esta linha dizia isso, e a varredura de 2026-08 mostrou que nao: das
    # seis perdidas, uma (Joao Pessoa/PB) CONTEM um termo que a busca ja usa
    # inteiro no objeto -- logo o problema ali foi alcance, nao vocabulario.
    # E outra (Ronda Alta/RS) e relogio de ponto: suspeita de falso positivo
    # do FILTRO, nao perda da busca. Conferir antes de tratar como palavra.
    print("  Cada uma destas é candidata a palavra que falta — CONFIRA ANTES:")
    print("     se um termo atual já aparece inteiro no objeto, o problema é")
    print("     alcance (paginação/ranqueamento), não vocabulário; e se o")
    print("     objeto não fala de folha, o suspeito é o filtro de escopo.")

    if extras and not truncou:
        print()
        print("  NO CORPUS E FORA DA VARREDURA: %d" % len(extras))
        print("  Não é erro necessariamente — pode ser publicação em outro mês,")
        print("  modalidade fora das seis, ou registro alterado depois. Vale olhar.")
        for k in extras[:8]:
            x = corpus[k]
            print("   %s  %-22s %s" % (x.get("publicado_em"), (x.get("municipio") or "?")[:22],
                                       (x.get("modalidade") or "")[:24]))
    elif extras:
        # NAO IMPRIMIR A LISTA QUANDO A VARREDURA TRUNCOU.
        #
        # Com a varredura morrendo na pagina 15, "a busca tem 30 e a varredura
        # nao tem nenhuma" descreve a API caindo, nao o corpus. Uma lista de 30
        # municipios sob um titulo de secao parece achado, e a ressalva de duas
        # linhas acima nao compete com uma tabela. Entao a tabela nao sai.
        print()
        print("  As %d do corpus que a varredura não viu NÃO são achado:" % len(extras))
        print("  a varredura parou antes de terminar. A lista fica omitida de")
        print("  propósito — sob um título de seção ela pareceria resultado.")

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps({
        "medido_em": dt.date.today().isoformat(), "mes": a.mes,
        "exaustiva": not truncou, "truncou": truncou,
        "bruto": bruto, "varredura": len(achados), "corpus": len(corpus),
        "perdidas": len(faltando), "recall": rec,
        "faltando": list(faltando.values()),
        "so_no_corpus": extras,
    }, ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_recall_busca.json")
    try:
        execucao.registrar("51_recall_busca.py", _t0, custo_brl=0.0,
                           mes=a.mes, bruto=bruto, de_folha=len(achados),
                           no_corpus=len(corpus), perdidas=len(faltando),
                           exaustiva=not truncou, falhas=len(truncou))
    except Exception:                                             # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
