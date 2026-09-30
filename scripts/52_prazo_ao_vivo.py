# -*- coding: utf-8 -*-
"""
O prazo gravado no disco ainda e o prazo que o PNCP publica?

    python 52_prazo_ao_vivo.py [--so ABERTO] [--pausa 0.6]

NAO CHAMA MODELO. Usa o `api/search`, que e o endpoint estavel.

POR QUE ISTO EXISTE
  O criterio do [[5 Monitor de resultados]] diz "nenhuma sessao perdida por
  data desatualizada". Era criterio sem teste: o pipeline le o prazo uma vez,
  na coleta, e o grava no inventario. Se o orgao move a sessao depois -- o que
  o art. 55, § 1º da Lei 14.133 nao so permite como OBRIGA quando a retificacao
  afeta a proposta -- o disco fica com a data velha e o painel alerta errado.

  Errar para MAIS (a sessao foi adiada e avisamos cedo) e inofensivo.
  Errar para MENOS (a sessao foi antecipada, ou ja passou) e perder a licitacao.

  Esta medicao pergunta o prazo de novo, ao vivo, e compara.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import io
import json
import os
import sys
import time
import urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import inventario, pncp                                             # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
DESTINO = os.path.join(RAIZ, "saidas", "_prazo_ao_vivo.json")


def data(s) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def ao_vivo(controle: str) -> tuple[dt.date | None, str]:
    """
    Prazo e criterio de julgamento, ao vivo, pelo `api/search`.

    Nao da para usar `pncp/v1/orgaos/.../compras/{ano}/{seq}`: esse recurso
    devolve **301** (testado em 23/09/2026; `/arquivos` e `/itens` respondem
    normalmente, so o cabecalho da compra nao). A busca por numero de controle
    devolve um unico resultado e traz `data_fim_vigencia`, que e o prazo.
    """
    q = urllib.parse.urlencode({"q": controle, "tipos_documento": "edital",
                                "pagina": 1, "tam_pagina": 5, "status": "todos"})
    d = pncp._get(pncp.BASE_BUSCA + "?" + q)
    for it in (d.get("items") or []):
        if it.get("numero_controle_pncp") == controle:
            return data(it.get("data_fim_vigencia")), str(it.get("situacao_nome") or "")
    return None, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", default="", help="prefixo do nome da pasta")
    ap.add_argument("--pausa", type=float, default=0.6)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    invs = sorted(glob.glob(os.path.join(AMOSTRAS, "*", "_inventario.json")))
    if a.so:
        invs = [p for p in invs if os.path.basename(os.path.dirname(p)).startswith(a.so)]
    hoje = dt.date.today()

    print("=" * 96)
    print("  PRAZO NO DISCO vs. PRAZO AO VIVO — %d licitação(ões)" % len(invs))
    print("=" * 96)

    iguais = adiadas = antecipadas = sem_local = sem_remoto = erro = 0
    casos, falhas = [], []
    for p in invs:
        nome = os.path.basename(os.path.dirname(p))
        inv = inventario.ler(os.path.dirname(p))
        if inv is None:
            erro += 1
            continue
        # O apelido do numero de controle e resolvido em
        # `fopa/inventario.py`, que e o unico lugar que conhece os 12
        # esquemas do acervo. Resolver inline aqui era a mesma regra
        # escrita pela terceira vez -- e a terceira copia e a que
        # esquece o apelido novo.
        ctrl = inv.get("controle")
        local = data(inv.get("fim_prazo"))
        if not ctrl:
            erro += 1
            continue
        if not local:
            sem_local += 1
            continue
        try:
            remoto, criterio = ao_vivo(ctrl)
        except Exception as e:                                    # noqa: BLE001
            falhas.append("%s: %s" % (nome[:40], str(e)[:40]))
            erro += 1
            time.sleep(a.pausa)
            continue
        time.sleep(a.pausa)
        if remoto is None:
            sem_remoto += 1
            continue
        d = (remoto - local).days
        if d == 0:
            iguais += 1
            continue
        reg = {"licitacao": nome, "controle": ctrl, "disco": local.isoformat(),
               "ao_vivo": remoto.isoformat(), "dias": d, "situacao": criterio,
               "ja_passou_no_disco": local < hoje, "ainda_aberta": remoto >= hoje}
        casos.append(reg)
        if d > 0:
            adiadas += 1
        else:
            antecipadas += 1

    print()
    print("  prazo idêntico ao do disco ..... %d" % iguais)
    print("  ADIADA (ao vivo é depois) ...... %d" % adiadas)
    print("  ANTECIPADA (ao vivo é antes) ... %d   <- é este que perde licitação" % antecipadas)
    print("  sem prazo no disco ............. %d" % sem_local)
    print("  sem prazo na resposta .......... %d" % sem_remoto)
    print("  erro de consulta ............... %d" % erro)
    for f in falhas[:5]:
        print("     · %s" % f)
    print()

    perigosas = [c for c in casos if c["dias"] < 0 and c["ainda_aberta"]]
    revividas = [c for c in casos if c["ja_passou_no_disco"] and c["ainda_aberta"]]
    if casos:
        print("  %-42s %-11s %-11s %s" % ("licitação", "disco", "ao vivo", "dias"))
        print("  " + "-" * 88)
        for c in sorted(casos, key=lambda x: x["dias"])[:25]:
            marca = " <<<" if c in perigosas else ""
            print("  %-42s %-11s %-11s %+4d%s"
                  % (c["licitacao"][:42], c["disco"], c["ao_vivo"], c["dias"], marca))
    else:
        print("  nenhuma divergência.")

    if revividas:
        print()
        print("  %d licitação(ões) que o DISCO dá por encerrada e o PNCP dá por ABERTA:"
              % len(revividas))
        for c in revividas:
            print("     %-42s disco %s · ao vivo %s"
                  % (c["licitacao"][:42], c["disco"], c["ao_vivo"]))
        print("  Essas somem do painel de urgência sem terem acabado.")

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps({
        "medido_em": hoje.isoformat(), "consultadas": len(invs),
        "iguais": iguais, "adiadas": adiadas, "antecipadas": antecipadas,
        "sem_prazo_local": sem_local, "sem_prazo_remoto": sem_remoto, "erro": erro,
        "divergencias": casos, "revividas": revividas,
    }, ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_prazo_ao_vivo.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
