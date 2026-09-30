# -*- coding: utf-8 -*-
"""
Qual caixinha do art. 33 o orgao realmente marca para cessao de folha?

    python 53_criterio_julgamento.py [--pausa 0.6]

NAO CHAMA MODELO. Le `criterioJulgamentoNome` do endpoint `/itens`, que e o
campo estruturado onde o proprio orgao declarou como vai julgar.

POR QUE A PERGUNTA IMPORTA
  A ADR-004 registra que a Lei 14.133 NAO tem caixinha para "maior oferta" na
  folha: o art. 33 lista menor preco, maior desconto, melhor tecnica, tecnica
  e preco, maior lance. E "maior lance" so existe atrelado ao LEILAO, que pelo
  art. 6º e para ALIENAR BEM -- e o TCU ja disse que folha nao e alienavel.

  Isso era analise da lei. Esta medicao mostra o que acontece no mundo: com
  caixinha nenhuma servindo, qual eles marcam? A resposta diz se o desalinho e
  teorico ou se produz divergencia real entre os orgaos -- e divergencia entre
  orgaos e ruido que o extrator precisa atravessar.

  E o criterio tambem decide o PRAZO MINIMO do art. 55: maior lance sao 15
  dias uteis, servico comum por menor preco sao 10. Sem saber o criterio, a
  medicao de antecedencia do 8 Orquestrador teve que supor 15 para todos.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
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
DESTINO = os.path.join(RAIZ, "saidas", "_criterio_julgamento.json")

# Art. 55 -- dias uteis minimos entre a divulgacao e a apresentacao, por
# criterio. So os que podem aparecer aqui.
MINIMO_ART_55 = {
    "Maior lance": 15,
    "Menor preço": 10,          # servico comum; bem comum seriam 8
    "Maior desconto": 10,
    "Melhor técnica": 35,
    "Técnica e preço": 35,
    "Maior retorno econômico": 35,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pausa", type=float, default=0.6)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    invs = sorted(glob.glob(os.path.join(AMOSTRAS, "*", "_inventario.json")))
    print("=" * 92)
    print("  CRITÉRIO DE JULGAMENTO DECLARADO — %d licitação(ões)" % len(invs))
    print("=" * 92)

    crit = collections.Counter()
    por_modalidade = collections.defaultdict(collections.Counter)
    registros, erros = [], 0
    for p in invs:
        nome = os.path.basename(os.path.dirname(p))
        inv = inventario.ler(os.path.dirname(p))
        if inv is None:
            erros += 1
            continue
        # apelido resolvido em `fopa/inventario.py` — ver 52_prazo_ao_vivo
        ctrl = inv.get("controle")
        if not ctrl:
            erros += 1
            continue
        try:
            lic = pncp.Licitacao.de_controle(ctrl)
            itens = pncp._get(lic._u("/itens"))
        except Exception:                                         # noqa: BLE001
            erros += 1
            time.sleep(a.pausa)
            continue
        time.sleep(a.pausa)
        nomes = {(i.get("criterioJulgamentoNome") or "?") for i in (itens or [])}
        for c in nomes:
            crit[c] += 1
            por_modalidade[inv.get("modalidade") or "?"][c] += 1
        registros.append({"licitacao": nome, "controle": ctrl,
                          "modalidade": inv.get("modalidade"),
                          "criterios": sorted(nomes),
                          "itens": len(itens or [])})

    consultadas = len(registros)
    print()
    print("  consultadas com sucesso ... %d   (erro: %d)" % (consultadas, erros))
    print()
    if not consultadas:
        print("  nada a reportar")
        return 1
    print("  %-34s %6s %8s  %s" % ("critério declarado", "n", "%", "art. 55"))
    print("  " + "-" * 74)
    for c, n in crit.most_common():
        m = MINIMO_ART_55.get(c)
        print("  %-34s %6d %7.1f%%  %s"
              % (c[:34], n, 100.0 * n / consultadas,
                 ("%d dias úteis" % m) if m else "—"))
    print()

    dominante, n_dom = crit.most_common(1)[0]
    print("  O critério dominante é **%s**, em %.1f%% das licitações."
          % (dominante, 100.0 * n_dom / consultadas))
    if len(crit) > 1:
        print("  E ele NÃO é unânime: %d critério(s) diferente(s) para o mesmo"
              % len(crit))
        print("  objeto de negócio. Órgãos divergem sobre como julgar a mesma coisa,")
        print("  e o extrator atravessa essa divergência em toda extração.")
    print()
    print("  %-30s %s" % ("modalidade", "critérios vistos"))
    print("  " + "-" * 74)
    for mod, cs in sorted(por_modalidade.items(), key=lambda t: -sum(t[1].values())):
        print("  %-30s %s" % (mod[:30],
                              ", ".join("%s (%d)" % (k, v) for k, v in cs.most_common())))

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps({
        "medido_em": dt.date.today().isoformat(),
        "consultadas": consultadas, "erros": erros,
        "criterios": dict(crit),
        "por_modalidade": {k: dict(v) for k, v in por_modalidade.items()},
        "registros": registros,
    }, ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_criterio_julgamento.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
