# -*- coding: utf-8 -*-
"""
Recupera a URL de origem dos arquivos baixados pelo monitor.

    python 54_reconciliar_origem.py [--pausa 0.6] [--seco]

NAO CHAMA MODELO.

POR QUE ISTO EXISTE
  O coletor grava, por arquivo, `sha256` completo e `origem` -- a URL do PNCP
  de onde o PDF desceu. O monitor gravava `sha` com 16 caracteres e nenhuma
  origem. Os dois escrevem o MESMO `_inventario.json`.

  Em 23/09/2026 o monitor baixou 53 licitacoes de uma vez e a suite acusou:
  223 arquivos no esquema antigo, contra um teto de 43.

  PROCEDENCIA VERIFICAVEL E O ARGUMENTO CENTRAL DESTE PROJETO. Um PDF com hash
  truncado e sem URL nao prova de onde veio -- e o projeto inteiro se apoia em
  "a resposta cita o trecho, o trecho esta na pagina, a pagina esta no arquivo,
  e o arquivo veio DAQUI".

  A URL nao se inventa: ela vem da API. Este script consulta `/arquivos` de
  cada licitacao e casa pelo `sequencialDocumento`, que e a chave estavel.

O QUE ELE NAO FAZ
  Nao inventa origem quando a API nao devolve o documento -- deixa em branco e
  reporta. Um campo preenchido com suposicao seria pior que o campo vazio: o
  vazio se ve, a suposicao nao.
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

from fopa import inventario, pncp                                             # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pausa", type=float, default=0.6)
    ap.add_argument("--seco", action="store_true", help="so relata, nao grava")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    # Leitura pelo `fopa/inventario`, que resolve os apelidos dos 12 esquemas
    # do acervo. Ler cru aqui obrigava a repetir a regra de apelido logo
    # abaixo -- e regra repetida e regra que uma das copias vai esquecer.
    alvo = []
    for nome, d in inventario.todos(AMOSTRAS):
        faltam = [x for x in d.get("arquivos", [])
                  if x.get("sha256") and not x.get("origem")]
        if faltam:
            alvo.append((os.path.join(AMOSTRAS, nome), d, faltam))

    print("=" * 92)
    print("  ORIGEM DOS ARQUIVOS — %d licitação(ões) com arquivo sem URL" % len(alvo))
    print("=" * 92)
    if not alvo:
        print("  nada a reconciliar")
        return 0

    achou = perdeu = sem_ctrl = 0
    for p, d, faltam in alvo:
        nome = os.path.basename(os.path.dirname(p))
        # apelido resolvido em `fopa/inventario.py`, unico lugar que
        # conhece os 12 esquemas do acervo
        ctrl = d.get("controle")
        if not ctrl:
            sem_ctrl += 1
            print("  %-46s sem número de controle" % nome[:46])
            continue
        try:
            docs = pncp.Licitacao.de_controle(ctrl).arquivos()
        except Exception as e:                                    # noqa: BLE001
            print("  %-46s API: %s" % (nome[:46], type(e).__name__))
            perdeu += len(faltam)
            time.sleep(a.pausa)
            continue
        time.sleep(a.pausa)
        por_seq = {x.get("sequencialDocumento"): x for x in (docs or [])}
        n = 0
        for x in faltam:
            doc = por_seq.get(x.get("seq"))
            url = (doc or {}).get("url") or (doc or {}).get("uri")
            if url:
                x["origem"] = url
                x["origem_recuperada_em"] = "2026-09-23"
                n += 1
            else:
                perdeu += 1
        achou += n
        print("  %-46s %d de %d recuperada(s)" % (nome[:46], n, len(faltam)))
        if n and not a.seco:
            io.open(p, "w", encoding="utf-8").write(
                json.dumps(d, ensure_ascii=False, indent=1))

    print()
    print("  URLs recuperadas ......... %d" % achou)
    print("  não devolvidas pela API .. %d  (ficam em branco, de propósito)" % perdeu)
    if sem_ctrl:
        print("  sem número de controle ... %d  (não há como consultar)" % sem_ctrl)
    if a.seco:
        print("\n  --seco: nada foi gravado")
    print("  custo em API de modelo: R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
