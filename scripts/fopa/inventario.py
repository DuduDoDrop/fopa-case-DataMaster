# -*- coding: utf-8 -*-
"""
Leitura normalizada do `_inventario.json` — um lugar que conhece os 13 esquemas.

POR QUE ISTO EXISTE
  O acervo tem 713 inventarios escritos por tres caminhos diferentes (coletor
  em lote, monitor, ensaios), ao longo de dias em que o formato mudou. Medido
  em 23/09/2026, sao **13 esquemas distintos**, e os campos se dividem assim:

      controle .................. 713   100%   <- a identidade, em todos
      municipio, situacao ....... 712
      fim_prazo ................. 709
      link ...................... 708
      orgao ..................... 666    93%
      licitacao ................. 651    91%   <- outro nome para orgao
      recusados ................. 592    83%
      numero_controle ...........  58     8%   <- outro nome para controle
      data_publicacao ...........  58     8%   <- outro nome para publicado_em
      arquivos_que_falharam .....  52     7%   <- outro nome para recusados

  Cada consumidor resolvia isso sozinho, ou nao resolvia. Um campo presente em
  PARTE da base e pior que um campo ausente em toda ela: a agregacao responde
  pela parte que tem o campo e apresenta como se fosse do todo. Foi assim que
  o censo devolveu "609 arquivos, 369 paginas" -- so 12 pastas tinham `pag`.

O QUE MUDOU, E O QUE NAO
  A parte que QUEBRAVA ja esta resolvida: `controle` existe em 713 de 713,
  entao nenhuma pasta e invisivel para quem casa por numero de controle
  (`45_retificacoes.py`, `43_cruzar_api.py`, `47_desertas.py`). O plano do
  fluxo funcional ainda registrava isso como risco aberto; nao e mais.

  O que sobra e divergencia de NOME, e este modulo resolve na leitura em vez
  de reescrever 713 arquivos. Reescrever o acervo para arrumar o leitor e
  trocar um problema barato por um irreversivel.
"""
from __future__ import annotations

import io
import json
import os

# nome canonico -> nomes que ja foram usados, em ordem de preferencia
ALIASES = {
    "controle": ("controle", "numero_controle", "numero_controle_pncp"),
    "orgao": ("orgao", "licitacao"),
    "publicado_em": ("publicado_em", "data_publicacao"),
    "recusados": ("recusados", "arquivos_que_falharam"),
    "baixado_em": ("baixado_em", "extraido_em"),
}


def caminho(pasta: str) -> str:
    return os.path.join(pasta, "_inventario.json")


def ler(pasta: str) -> dict | None:
    """
    O inventario de uma pasta, com os nomes canonicos preenchidos.

    Devolve `None` quando nao ha inventario -- e isso e informacao, nao erro:
    pasta sem inventario nao e download, e destroco. Ver `pastas_orfas()` no
    `28_baixar_licitacao.py`.

    Os campos originais ficam onde estavam; o que este leitor faz e GARANTIR
    que o nome canonico exista, copiando do primeiro alias presente. Nada e
    apagado, entao ler por aqui nunca perde informacao de um esquema antigo.
    """
    p = caminho(pasta)
    if not os.path.isfile(p):
        return None
    try:
        inv = json.load(io.open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(inv, dict):
        return None
    for canonico, nomes in ALIASES.items():
        if inv.get(canonico):
            continue
        for n in nomes:
            if inv.get(n):
                inv[canonico] = inv[n]
                break
    inv.setdefault("arquivos", [])
    inv.setdefault("recusados", [])
    return inv


def todos(amostras: str, com_controle: bool = False):
    """
    Percorre o acervo devolvendo `(pasta, inventario)` ja normalizado.

    `com_controle=True` pula quem nao tem identidade -- util para quem vai
    casar com a API, porque casar por NOME DE PASTA foi o que fez a
    `Dispensa - Rio Branco-AC` ser confundida com um orgao de outro estado.
    """
    if not os.path.isdir(amostras):
        return
    for d in sorted(os.listdir(amostras)):
        alvo = os.path.join(amostras, d)
        if not os.path.isdir(alvo) or d.startswith("_"):
            continue
        inv = ler(alvo)
        if inv is None:
            continue
        if com_controle and not inv.get("controle"):
            continue
        yield d, inv


def esquemas(amostras: str) -> dict:
    """
    Quantos formatos distintos convivem no acervo, e em quantas pastas cada um.

    Serve para o teste de fumaca e para saber se a divergencia esta crescendo.
    Um numero que sobe aqui significa que um caminho novo de escrita apareceu
    sem passar por este modulo.
    """
    from collections import Counter
    c: Counter = Counter()
    for _, inv in todos(amostras):
        c[frozenset(inv)] += 1
    return c


__all__ = ["ALIASES", "caminho", "ler", "todos", "esquemas"]
