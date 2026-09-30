# -*- coding: utf-8 -*-
"""
Duelo de provedores na MESMA licitação, com a MESMA configuração.

    python 29_duelo.py "<pasta>"
    python 29_duelo.py "<pasta>" --effort medium
    python 29_duelo.py "<pasta>" --provedores claude openai --simulado

POR QUE UM SCRIPT, E NÃO DUAS EXECUÇÕES NA MÃO
  Porque comparar duas execuções feitas em momentos diferentes é como comparar
  duas medições com réguas diferentes: basta um `--k` distinto, um `--lote`
  distinto ou um `--effort` esquecido para que a diferença medida seja da
  configuração, não do provedor. Aqui a configuração é montada uma vez e usada
  nas duas, e ela é IMPRESSA no cabeçalho — o leitor não precisa confiar.

O QUE O DUELO MEDE, E EM QUE ORDEM
  1. Ancoragem — o trecho citado existe na página citada? É piso de integridade,
     e já se sabe que ele NÃO separa provedores: Opus, Sonnet, Haiku e
     gpt-5.6-sol ficaram todos em 100% nas medições anteriores.
  2. Divergências — em quais perguntas os dois discordam. É o que realmente
     interessa: onde um encontrou e o outro não, e onde ambos encontraram
     coisas diferentes.
  3. Acurácia contra gabarito, se existir. É a única que diz quem acertou;
     sem gabarito, o duelo mostra divergência e não decide quem está certo.

  Essa ordem é proposital. Um duelo que só mostrasse ancoragem concluiria
  "empate" toda vez.

CUSTO
  Uma extração inteira por provedor. Com `--simulado` roda de graça e exercita
  todo o encanamento — útil para conferir o relatório antes de gastar.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import extrator, modelos, saida, verificador               # noqa: E402
from fopa.questionario import NAO_LOCALIZADO, POR_ID                 # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")


def barra(t: str) -> None:
    print("\n" + "=" * 100 + "\n  %s\n" % t + "=" * 100)


def nao_achou(texto: str) -> bool:
    return (texto or "").strip().lower().startswith(NAO_LOCALIZADO.lower())


def rodar(pasta: str, nome_prov: str, effort: str, lote: int, k: int,
          modo: str | None, simulado: bool, destino: str) -> dict | None:
    modelo = modelos.modelo_padrao(nome_prov)
    print("\n  >> %s (%s, effort %s)" % (nome_prov, modelo, effort), flush=True)
    try:
        prov = modelos.obter_provedor(simulado=simulado, provedor=nome_prov)
    except modelos.ErroModelo as e:
        print("     não disponível: %s" % e)
        return None

    t0 = time.time()
    try:
        ext = extrator.extrair(pasta, prov, modelo=modelo, modo=modo,
                               lote=lote, k_rag=k, effort=effort)
    except Exception as e:                                           # noqa: BLE001
        print("     falhou: %s" % e)
        return None

    rel = verificador.verificar(ext)
    os.makedirs(destino, exist_ok=True)
    saida.escrever_json(ext, rel, os.path.join(destino, "auditoria.json"))

    print("     %s" % ext.uso)
    print("     %s" % rel)
    # O rótulo vem do provedor que DE FATO respondeu, não do que foi pedido.
    # Com `--simulado`, pedir "claude" e rotular "claude" faria o placar exibir
    # um duelo entre dois nomes diferentes e o mesmo localizador por regex.
    return dict(provedor=ext.provedor or nome_prov, pedido=nome_prov,
                modelo=ext.uso.modelo, modo=ext.modo,
                effort=effort, ext=ext, rel=rel, segundos=time.time() - t0)


def comparar(resultados: list[dict]) -> None:
    barra("PLACAR")
    print("  %-22s %-9s %-6s %-6s %-6s %-9s %-9s %s"
          % ("provedor", "ancorag.", "aprov", "rever", "reprov", "n/loc",
             "entrada", "saída"))
    print("  " + "-" * 96)
    for r in resultados:
        u, rel = r["ext"].uso, r["rel"]
        print("  %-22s %6.0f%%   %-6d %-6d %-6d %-9d %-9s %s"
              % (r["modelo"][:22], rel.taxa_ancorada * 100, rel.aprovadas,
                 rel.revisar, rel.reprovadas, rel.nao_localizado,
                 f"{u.entrada + u.cache_leitura:,}".replace(",", "."),
                 f"{u.saida:,}".replace(",", ".")))

    if len(resultados) < 2:
        return

    a, b = resultados[0], resultados[1]
    ra = {r.id: r for r in a["ext"].respostas}
    rb = {r.id: r for r in b["ext"].respostas}

    # O NÚMERO QUE IMPORTA: onde um encontrou e o outro não.
    #
    # Ancoragem empata; cobertura não. Foi assim que a diferença entre Opus e
    # gpt-5.6-sol apareceu em Bertioga — ambos 100% ancorados, e um deles com a
    # data da sessão em branco, com a página do comunicado dentro do contexto.
    so_a = [q for q in ra if not nao_achou(ra[q].resposta) and nao_achou(rb[q].resposta)]
    so_b = [q for q in rb if not nao_achou(rb[q].resposta) and nao_achou(ra[q].resposta)]
    ambos_nao = [q for q in ra if nao_achou(ra[q].resposta) and nao_achou(rb[q].resposta)]

    barra("COBERTURA — quem encontrou o que o outro não encontrou")
    print("  só %-18s %d  %s" % (a["provedor"], len(so_a), ", ".join(sorted(so_a)) or "—"))
    print("  só %-18s %d  %s" % (b["provedor"], len(so_b), ", ".join(sorted(so_b)) or "—"))
    print("  nenhum dos dois      %d  %s"
          % (len(ambos_nao), ", ".join(sorted(ambos_nao)) or "—"))

    barra("DIVERGÊNCIAS — mesma pergunta, páginas diferentes")
    houve = False
    for q in sorted(ra, key=lambda x: int(x[1:])):
        x, y = ra[q], rb[q]
        if nao_achou(x.resposta) or nao_achou(y.resposta):
            continue
        if (x.arquivo, x.pagina) == (y.arquivo, y.pagina):
            continue
        houve = True
        print("\n  %-4s %s" % (q, POR_ID[q].texto[:88]))
        print("       %-10s p.%-4s %s" % (a["provedor"], x.pagina, (x.resposta or "")[:64]))
        print("       %-10s p.%-4s %s" % (b["provedor"], y.pagina, (y.resposta or "")[:64]))
    if not houve:
        print("  nenhuma: onde os dois responderam, citaram a mesma página.")

    print("\n  " + "-" * 96)
    print("  Divergência não é erro de ninguém — é onde o Verificador não decide,")
    print("  porque os DOIS podem estar ancorados em páginas diferentes e corretas.")
    print("  Quem decide é o gabarito, e só onde ele existe.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Compara provedores na mesma licitação")
    ap.add_argument("pasta")
    ap.add_argument("--provedores", nargs="+", default=["claude", "openai"])
    ap.add_argument("--effort", choices=["low", "medium", "high"], default="high")
    ap.add_argument("--lote", type=int, default=6)
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--modo", choices=["contexto-completo", "rag"], default=None)
    ap.add_argument("--simulado", action="store_true", help="ensaio, custo zero")
    a = ap.parse_args()

    pasta = a.pasta if os.path.isdir(a.pasta) else os.path.join(AMOSTRAS, a.pasta)
    if not os.path.isdir(pasta):
        print("pasta não encontrada: %s" % pasta)
        return 2
    nome = os.path.basename(pasta.rstrip("\\/"))

    barra("DUELO — %s" % nome)
    print("  MESMA configuração nos dois, e ela está aqui para ser conferida:")
    print("    effort ..... %s" % a.effort)
    print("    lote ....... %d perguntas por requisição" % a.lote)
    print("    k .......... %d páginas por pergunta (só no modo rag)" % a.k)
    print("    modo ....... %s" % (a.modo or "automático (por tamanho)"))
    print("    provedores . %s" % ", ".join(a.provedores))

    base = os.path.join(SAIDAS, "_duelo_%s" % nome)
    resultados = []
    for p in a.provedores:
        r = rodar(pasta, p, a.effort, a.lote, a.k, a.modo, a.simulado,
                  os.path.join(base, p))  # a pasta usa o PEDIDO, para nao colidir
        if r:
            resultados.append(r)

    if not resultados:
        print("\n  nenhum provedor completou.")
        return 1
    comparar(resultados)

    gab = os.path.join(pasta, "_gabarito.json")
    print("\n  " + "-" * 96)
    if os.path.isfile(gab):
        extras = " ".join('--extra "%s"' % os.path.join(base, r["provedor"],
                                                        "auditoria.json")
                          for r in resultados)
        print("  Há gabarito. Para saber quem ACERTOU:")
        print('      python 15_acuracia.py "%s" %s' % (nome, extras))
    else:
        print("  SEM gabarito nesta licitação: o duelo mostra divergência e não")
        print("  decide quem está certo. Construir o gabarito é trabalho humano —")
        print("  usar um modelo como juiz devolveria ao sistema a subjetividade")
        print("  que ele existe para eliminar (ADR-004).")
    print("\n  saídas em %s" % os.path.relpath(base, RAIZ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
