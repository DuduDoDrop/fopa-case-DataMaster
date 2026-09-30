# -*- coding: utf-8 -*-
"""
O Jev acerta o filtro de escopo? Medido contra o gabarito HUMANO.

    python 63_jev_escopo.py [--criterio v1|v2] [--max N]

CHAMA O JEV (nao o extrator). Custo medido e impresso no fim; a ordem de
grandeza e de centavo de dolar para o catalogo inteiro.

POR QUE CONTRA O GABARITO HUMANO, E NAO CONTRA A REGRA DO PROJETO
  Medir o Jev contra `escopo.avaliar` responderia "o Jev imita a regra?", que
  nao interessa -- se imitasse perfeitamente, seria inutil, e se discordasse
  nao daria para saber quem errou.

  O `_catalogo_escopo.json` tem 23 objetos julgados a LEITURA HUMANA, com o
  motivo escrito. E a unica fonte independente dos dois. Contra ele da para
  perguntar as tres coisas que importam:

      1. o Jev acerta?
      2. a regra do projeto acerta?
      3. quando discordam, quem esta certo?

  A terceira e a que decide se ele entra: um segundo sinal so vale se, nas
  discordancias, ele estiver certo com alguma frequencia util.

O QUE ESTE SCRIPT **NAO** FAZ
  Nao escreve veredito em lugar nenhum. Nao altera o corpus, nao alimenta o
  painel, nao toca em `escopo.avaliar`. A ADR-004 traca a linha: o Jev e um
  adendo de assertividade, nao motivo de decisao. Medir e permitido,
  decidir nao.

A VARIAVEL ESCONDIDA: A DESCRICAO DO CRITERIO
  Auditoria independente mediu o Jev caindo a 16,7% -- abaixo do acaso -- com
  criterio mal descrito. Conferido aqui na primeira chamada: com um criterio
  vago, ele errou Aguas de Chapeco/SC (que diz literalmente "processamento e
  gerenciamento dos creditos provenientes da folha de pagamento") com 71% de
  probabilidade na opcao errada. Reescrito o criterio, acertou com 99%.

  Por isso o criterio e versionado aqui, e trocar de versao e um experimento
  registrado -- nao um ajuste que some no historico.
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
sys.path.insert(0, AQUI)

from fopa import escopo, jev                                      # noqa: E402

CATALOGO = os.path.join(RAIZ, "saidas", "_catalogo_escopo.json")
DESTINO = os.path.join(RAIZ, "saidas", "_jev_escopo.json")

# Criterios versionados. O `v1` e o primeiro escrito, e errou; fica aqui
# de proposito, porque a comparacao entre os dois E o resultado mais util.
CRITERIOS = {
    "v1": {
        "pergunta": ("O órgão está contratando uma instituição financeira para "
                     "OPERAR a folha de pagamento (receber os créditos e pagar "
                     "os servidores)?"),
        "opcoes": {
            "sim": "contrata quem vai operar/processar/pagar a folha",
            "nao": ("consignado, sistema de software, consultoria, ou "
                    "nada a ver com folha"),
        },
    },
    "v2": {
        "pergunta": ("Neste objeto de licitação, o órgão público contrata uma "
                     "instituição financeira ou empresa para OPERAR a folha de "
                     "pagamento dele — isto é, receber os créditos da folha e "
                     "pagar os servidores? Responda sobre o que está sendo "
                     "CONTRATADO, não sobre o que o texto menciona de passagem."),
        "opcoes": {
            "sim": ("o objeto contrata a operação da folha: processamento, "
                    "gerenciamento, pagamento, centralização dos créditos, ou "
                    "cessão onerosa do direito de pagar a folha"),
            "nao": ("o objeto é outra coisa: empréstimo consignado aos "
                    "servidores, licença de software de folha, consultoria ou "
                    "assessoria sobre a folha, ou assunto sem relação"),
        },
    },
    # v3 (24/09/2026, scripts/67_jev_escopo_criterio.py, no acervo da v3): o v2
    # dava p <= 0,25 a 9 folhas reais ("processamento e gerenciamento de
    # créditos provenientes da folha" — Itatiba, Salto, Valinhos, Votorantim).
    # Instrução em inglês (a língua principal do Jev, docs.typesafe.ai) e
    # exemplos dos dois lados: 100 publicadas x 100 recusadas, AUC 0,947 -> 0,968,
    # positivos >= 0,5 de 78,8% -> 98%, negativos iguais (93,3% < 0,5).
    "v3": {
        "pergunta": (
            "This is the 'objeto' (subject) of a Brazilian public procurement notice, written in Portuguese. "
            "Is the public body contracting a bank or financial institution to RUN ITS PAYROLL — that is, to "
            "process, manage and pay the salary credits of its public servants ('processamento e gerenciamento "
            "de créditos provenientes da folha de pagamento', 'pagamento da folha', 'centralização da folha', "
            "'cessão onerosa do direito de processar a folha')? Judge what is being CONTRACTED, not words that "
            "are merely mentioned."),
        "opcoes": {
            "sim": ("yes: a bank or financial institution will process, manage or pay the payroll credits of the "
                    "servants, or buys the exclusive right to do so — even when other banking services (tax "
                    "collection, supplier payments, payroll loans offered as an extra) are bundled in"),
            "nao": ("no: the contract is something else — a payroll loan product on its own (empréstimo "
                    "consignado), payroll software or IT services, consulting or studies about the payroll, bank "
                    "fees or file transfer services paid by the body, an institutional bank account, or "
                    "unrelated goods/services"),
        },
    },
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--criterio", choices=sorted(CRITERIOS), default="v2")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--pausa", type=float, default=0.2)
    ap.add_argument("--fila", action="store_true",
                    help="roda sobre saidas/_fila_rotulagem.json (sem gabarito)")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if a.fila:
        # A FILA NAO TEM GABARITO, E E ESSE O PONTO.
        #
        # O catalogo de 23 casos foi julgado ENQUANTO a regra era construida e
        # corrigida -- a regra acertar 100% nele e, em parte, por construcao.
        # A fila de rotulagem sai das faixas em que a regra e mais FRAGIL
        # (aceita por ausencia de sinal negativo, rejeita falando de folha,
        # rejeita como sistema). E ali que um segundo sinal independente teria
        # onde ganhar -- ou onde ficar provado que nao ganha.
        #
        # Sem gabarito, nao da para dizer quem acertou. Da para dizer ONDE
        # OLHAR PRIMEIRO, que e exatamente o que um "adendo de assertividade"
        # tem direito de fazer.
        f = os.path.join(RAIZ, "saidas", "_fila_rotulagem.json")
        if not os.path.isfile(f):
            print("falta saidas/_fila_rotulagem.json — rode `62_fila_rotulagem.py`.")
            return 1
        casos = [{"orgao": x.get("orgao"), "uf": x.get("uf"),
                  "controle": x.get("controle"), "objeto": x.get("objeto"),
                  "e_folha": None, "faixa": x.get("faixa"),
                  "motivo_humano": x.get("motivo_do_filtro")}
                 for x in json.load(io.open(f, encoding="utf-8"))["casos"]]
    elif not os.path.isfile(CATALOGO):
        print("falta saidas/_catalogo_escopo.json — é o gabarito humano.")
        return 1
    else:
        casos = json.load(io.open(CATALOGO, encoding="utf-8"))["casos"]
    if a.max:
        casos = casos[: a.max]
    crit = CRITERIOS[a.criterio]

    print("=" * 100)
    print("  JEV CONTRA O GABARITO HUMANO — filtro de escopo · critério %s"
          % a.criterio)
    print("  %d casos julgados à leitura humana · Jev NÃO decide nada aqui"
          % len(casos))
    print("=" * 100)
    print()

    linhas, custo, segundos = [], 0.0, 0.0
    falhas = 0
    for c in casos:
        verdade = None if c.get("e_folha") is None else bool(c.get("e_folha"))
        obj = c.get("objeto") or ""
        regra = escopo.avaliar(obj)[0]
        try:
            ans, uso = jev.perguntar(obj, {"escopo": jev.noul(
                crit["pergunta"], crit["opcoes"]["sim"], crit["opcoes"]["nao"])})
        except jev.ErroJev as e:
            falhas += 1
            print("  %-30s FALHOU: %s" % ((c.get("orgao") or "")[:30], e))
            continue
        # NOUL, nao CHOICE. A documentacao do fornecedor e explicita: para
        # "esta condicao vale?" a primitiva e Noul, que devolve a probabilidade
        # de SIM direto, sem campo de confianca separado. `choice` com duas
        # opcoes responde a mesma pergunta por um caminho que o fornecedor nao
        # recomenda -- e os dois deram respostas diferentes no mesmo objeto.
        r = ans.get("escopo") or {}
        p_sim = jev.valor(r)
        jev_diz = (p_sim or 0.0) >= 0.5
        # Num Noul a "confianca" e a distancia de 0,5: 0,98 e 0,02 sao ambos
        # certezas, so que de sinais opostos. Tratar o proprio 0,98 como
        # confianca faria todo "nao" confiante parecer incerto.
        conf = abs((p_sim or 0.5) - 0.5) * 2
        custo += uso["usd"]
        segundos += uso["segundos"]
        linhas.append({
            "orgao": c.get("orgao"), "uf": c.get("uf"),
            "controle": c.get("controle"),
            "verdade_humana": verdade, "motivo_humano": c.get("motivo_humano"),
            "regra": regra, "jev": jev_diz,
            "p_sim": p_sim, "confianca": round(conf, 3),
            "objeto": obj[:200],
        })
        def m(v):
            return "  ?  " if v is None else ("FOLHA" if v else "fora ")
        marca = ""
        if verdade is None:
            if jev_diz != regra:
                marca = "  <- DISCORDAM — olhar primeiro"
        elif jev_diz != verdade:
            marca = "  <- JEV ERROU"
        elif regra != verdade:
            marca = "  <- a REGRA errou, o Jev acertou"
        print("  %-30s humano %s · regra %s · jev %s (%.2f)%s"
              % ((c.get("orgao") or "")[:30], m(verdade), m(regra),
                 m(jev_diz), conf or 0.0, marca))
        time.sleep(a.pausa)

    if not linhas:
        print("\n  nenhuma resposta — nada a concluir.")
        return 1

    n = len(linhas)
    com_gabarito = [x for x in linhas if x["verdade_humana"] is not None]
    acerto_jev = sum(1 for x in com_gabarito if x["jev"] == x["verdade_humana"])
    acerto_regra = sum(1 for x in com_gabarito if x["regra"] == x["verdade_humana"])
    discordam = [x for x in linhas if x["jev"] != x["regra"]]
    jev_certo = [x for x in discordam if x["jev"] == x["verdade_humana"]]

    print()
    print("-" * 100)
    if not com_gabarito:
        # DISCORDAR EXIGE CONVICCAO. Um Noul de 0,44 contra uma regra que diz
        # DENTRO nao e discordancia: e "nao sei", do lado de la do 0,5 por
        # pouco. A auditoria independente mediu a acuracia PLANA entre 0,50 e
        # 0,95 -- entao a distancia do 0,5 nessa faixa nao ordena nada.
        #
        # Sem este corte, a fila saiu com 8 casos e 6 deles eram o Jev
        # indeciso. Chamar isso de "olhar primeiro" gastaria julgamento humano
        # exatamente onde o segundo sinal nao tem o que dizer.
        CONVICCAO = 0.25          # p<=0,25 ou p>=0,75
        disc = [x for x in linhas
                if x["jev"] != x["regra"]
                and ((x["p_sim"] or 0.5) <= CONVICCAO
                     or (x["p_sim"] or 0.5) >= 1 - CONVICCAO)]
        mornos = [x for x in linhas
                  if x["jev"] != x["regra"] and x not in disc]
        print("  SEM GABARITO — não dá para dizer quem acertou, só onde olhar")
        print("     casos .............................. %3d" % n)
        print("     Jev discorda COM CONVICÇÃO em ...... %3d  (%.0f%%)"
              % (len(disc), 100.0 * len(disc) / n))
        print("     Jev do outro lado, mas indeciso .... %3d  (não conta)"
              % len(mornos))
        print()
        print("  As discordâncias, da mais forte para a mais fraca:")
        for x in sorted(disc, key=lambda z: -(z["confianca"] or 0))[:20]:
            print("     %-28s %-30s regra %s · jev %.2f"
                  % ((x["orgao"] or "")[:28], (x.get("faixa") or "")[:30],
                     "DENTRO" if x["regra"] else "fora  ", x["p_sim"] or 0.0))
        print()
        if mornos:
            print()
            print("  Ficaram de fora por indecisão do Jev (0,25 a 0,75):")
            for x in mornos:
                print("     %-28s regra %s · jev %.2f"
                      % ((x["orgao"] or "")[:28],
                         "DENTRO" if x["regra"] else "fora  ", x["p_sim"] or 0.0))
        print()
        print("  Isto é uma ORDEM DE LEITURA, não um veredito. Onde os dois")
        print("  sinais discordam COM CONVICÇÃO, um deles está errado — e é lá")
        print("  que o julgamento humano rende mais por minuto gasto.")
        io.open(DESTINO.replace(".json", "_fila.json"), "w",
                encoding="utf-8").write(json.dumps(
                    {"medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                     "criterio": a.criterio, "casos": n,
                     "discordancias": len(disc), "indecisos": len(mornos),
                     "limiar_conviccao": CONVICCAO, "usd": round(custo, 6),
                     "linhas": linhas}, ensure_ascii=False, indent=1))
        print()
        print("  salvo em saidas/_jev_escopo_fila.json · US$ %.5f" % custo)
        return 0
    n = len(com_gabarito)
    print("  %-46s %s" % ("acertos contra o gabarito humano", "de %d" % n))
    print("     regra determinística (`escopo.avaliar`) ... %2d  (%.0f%%)"
          % (acerto_regra, 100.0 * acerto_regra / n))
    print("     Jev ........................................ %2d  (%.0f%%)"
          % (acerto_jev, 100.0 * acerto_jev / n))
    print()
    print("  ONDE OS DOIS DISCORDAM — é a única parte que decide se ele entra")
    print("     discordâncias .............................. %2d" % len(discordam))
    print("     nelas, o Jev estava certo .................. %2d" % len(jev_certo))
    print("     nelas, a regra estava certa ................ %2d"
          % (len(discordam) - len(jev_certo)))
    if discordam:
        print()
        for x in discordam:
            quem = "JEV certo" if x in jev_certo else "REGRA certa"
            print("     %-28s %-12s conf %.2f · %s"
                  % ((x["orgao"] or "")[:28], quem, x["confianca"] or 0.0,
                     (x["motivo_humano"] or "")[:44]))

    # ---------------------------------------------------------- calibracao
    print()
    print("  CALIBRAÇÃO — quando ele diz %d%%, acerta %d%% das vezes?")
    faixas = [(0.0, 0.6), (0.6, 0.8), (0.8, 0.95), (0.95, 1.01)]
    for lo, hi in faixas:
        dentro = [x for x in linhas if lo <= (x["confianca"] or 0) < hi]
        if not dentro:
            continue
        ok = sum(1 for x in dentro if x["jev"] == x["verdade_humana"])
        media = sum(x["confianca"] or 0 for x in dentro) / len(dentro)
        print("     confiança %.2f–%.2f · n=%2d · diz %.0f%% · acerta %.0f%%"
              % (lo, hi, len(dentro), 100 * media, 100.0 * ok / len(dentro)))
    print()
    print("  > A auditoria independente mediu a acurácia PLANA entre 0,50 e")
    print("  > 0,95 — \"gate at 0.99 or not at all\". Se as faixas acima não")
    print("  > separarem acerto de erro, usar essa confiança para priorizar")
    print("  > seria inventar uma ordem que o número não sustenta.")

    print()
    print("  custo .......... US$ %.5f  (%s)" % (custo, jev.FONTE_PRECO))
    print("  tempo .......... %.1f s em %d chamadas (%.0f ms por objeto)"
          % (segundos, n, 1000.0 * segundos / n))
    if falhas:
        print("  falhas ......... %d chamada(s) não responderam" % falhas)

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps(
        {"medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
         "criterio": a.criterio, "pergunta": crit["pergunta"],
         "opcoes": crit["opcoes"], "modelo": jev.MODELO,
         "casos": n, "acerto_jev": acerto_jev, "acerto_regra": acerto_regra,
         "discordancias": len(discordam), "jev_certo_nas_discordancias": len(jev_certo),
         "usd": round(custo, 6), "preco": jev.FONTE_PRECO,
         "linhas": linhas}, ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_jev_escopo.json")
    print("  NENHUM veredito foi alterado — este script só mede.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
