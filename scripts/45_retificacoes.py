# -*- coding: utf-8 -*-
"""
Quais licitações do acervo já mudaram no PNCP desde que foram baixadas.

    python 45_retificacoes.py [--max N] [--pausa S] [--json]

NÃO CHAMA MODELO. Compara o inventário local com a lista de arquivos da API.

O BURACO QUE ESTE ARQUIVO FECHA
  `ja_baixada()` responde "sim" e o coletor segue em frente. Isso está certo
  para uma licitação que não mudou — e **errado** para uma que foi retificada,
  que é o caso em que o documento novo é justamente o que importa.

  Edital retificado é rotina: muda data de sessão, muda valor mínimo, muda
  anexo. O sistema continuaria respondendo com a versão antiga, com ancoragem
  perfeita contra um documento que o órgão já substituiu. Ancoragem não protege
  contra isso: o trecho está mesmo na página, só que a página é de ontem.

  É o mesmo tipo de cegueira do [[ADR-006]] — lá, escolher o arquivo errado
  entre os do acervo; aqui, não saber que existe arquivo novo.

COMO DECIDE QUE MUDOU
  Três sinais, do mais barato ao mais caro:

    1. a API lista MAIS arquivos ativos do que o inventário registra
    2. existe `sequencialDocumento` na API que não está no inventário
    3. um arquivo que tínhamos foi DESATIVADO (`statusAtivo` virou falso)

  Qualquer um dos três significa "rebaixar". O terceiro é o mais silencioso:
  nada foi adicionado, mas o que lemos deixou de valer.
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

DESTINO = os.path.join(SAIDAS, "_retificacoes.json")


def ativos(arquivos: list[dict]) -> list[dict]:
    """Só os que a API ainda considera válidos."""
    return [a for a in arquivos
            if a.get("statusAtivo") is not False]


def main() -> int:
    _t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0, help="0 = todas")
    ap.add_argument("--pausa", type=float, default=0.35)
    a = ap.parse_args()

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    # LEITURA NORMALIZADA. O acervo tem 12 esquemas de inventario conviven-
    # do, escritos por tres caminhos diferentes ao longo de dias. `fopa/
    # inventario.py` e o unico lugar que conhece os apelidos -- `licitacao`
    # para `orgao`, `numero_controle` para `controle`, `data_publicacao` para
    # `publicado_em`. Ler direto do disco aqui significava cada consumidor
    # resolver isso sozinho, ou nao resolver.
    alvos = []
    for pasta, d in inventario.todos(AMOSTRAS, com_controle=True):
        alvos.append((pasta, (d.get("controle") or "").strip(), d))
    if a.max:
        alvos = alvos[: a.max]

    print("=" * 84)
    print("  RETIFICAÇÕES — %d licitações do acervo contra a API" % len(alvos))
    print("=" * 84)

    mudaram, iguais, erros, incompletas = [], 0, [], []
    for i, (pasta, ctrl, inv) in enumerate(alvos, 1):
        try:
            remoto = ativos(pncp.Licitacao.de_controle(ctrl).arquivos())
        except Exception as e:                                    # noqa: BLE001
            erros.append("%s :: %s" % (pasta[:44], str(e)[:44]))
            continue

        # Os sequenciais do acervo. O inventário guarda `seq` por arquivo, e os
        # extraídos de ZIP herdam o sequencial do container — por isso `set`.
        locais = {a.get("seq") for a in inv.get("arquivos", []) if a.get("seq")}
        locais |= {r.get("seq") for r in inv.get("recusados", []) if r.get("seq")}
        remotos = {r.get("sequencialDocumento") for r in remoto}

        # INVENTÁRIO SEM NENHUM SEQUENCIAL NÃO É RETIFICAÇÃO.
        #
        # Inhácora/RS apareceu na primeira varredura como "+1 novo: [1]", e não
        # era: o único arquivo dela é um `.doc`, o download nunca completou, e o
        # inventário ficou sem `arquivos`. Aí TODO sequencial remoto vira
        # "novo", porque o conjunto local é vazio.
        #
        # Um detector que confunde "nunca baixei" com "mudou" infla a taxa de
        # retificação com os próprios buracos do acervo — e a taxa é o número
        # que decide a frequência de reconferência.
        if not locais:
            incompletas.append(pasta)
            print("  %-46s (inventário sem arquivos — download incompleto)"
                  % pasta[:46])
            time.sleep(a.pausa)
            continue

        novos = sorted(x for x in remotos - locais if x is not None)
        sumiram = sorted(x for x in locais - remotos if x is not None)

        if novos or sumiram:
            mudaram.append({"pasta": pasta, "controle": ctrl,
                            "novos": novos, "desativados": sumiram,
                            "locais": len(locais), "remotos": len(remotos)})
            marca = []
            if novos:
                marca.append("+%d novo(s): %s" % (len(novos), novos[:4]))
            if sumiram:
                marca.append("-%d desativado(s): %s" % (len(sumiram), sumiram[:4]))
            print("  %-46s %s" % (pasta[:46], " · ".join(marca)))
        else:
            iguais += 1

        if i % 25 == 0:
            print("   ... %d/%d" % (i, len(alvos)))
        time.sleep(a.pausa)

    print()
    print("  sem mudança ......... %d" % iguais)
    if incompletas:
        print("  download incompleto . %d  (não entram na taxa)" % len(incompletas))
    print("  COM mudança ......... %d" % len(mudaram))
    print("  erro na consulta .... %d" % len(erros))
    conf = iguais + len(mudaram)
    if conf:
        print("  taxa de retificação . %.1f%%" % (100.0 * len(mudaram) / conf))
    if erros:
        print("\n  não conferidas:")
        for e in erros[:10]:
            print("   · %s" % e)

    if mudaram:
        print("\n  Para rebaixar estas, apague a pasta e rode o coletor —")
        print("  o livro reconhece pelo número de controle, não pelo nome.")

    execucao.registrar("45_retificacoes.py", _t0, conferidas=conf,
                       com_mudanca=len(mudaram), erros=len(erros))
    json.dump({"medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "conferidas": conf, "com_mudanca": len(mudaram),
               "mudaram": mudaram, "erros": erros,
               "incompletas": incompletas},
              io.open(DESTINO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n  salvo: %s" % os.path.relpath(DESTINO, RAIZ))
    print("  custo em API de modelo: R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
