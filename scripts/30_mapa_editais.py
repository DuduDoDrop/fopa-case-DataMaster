# -*- coding: utf-8 -*-
"""
Gera o mapa das licitações de folha dentro do vault, a partir do corpus.

    python 30_mapa_editais.py            escreve Fopa-v2/09-Editais/
    python 30_mapa_editais.py --seco     mostra o que faria, sem escrever

POR QUE GERADO, E NÃO ESCRITO À MÃO
  São 112 licitações hoje e serão mais amanhã: o corpus cresce a cada coleta, e
  o estado de cada uma muda quando o download em lote roda. Uma tabela mantida à
  mão estaria errada na primeira semana — e errada em silêncio, que é o modo de
  falha que este projeto passou dois dias caçando.

  Rodar de novo é idempotente: reescreve as duas notas a partir da verdade em
  disco (`saidas/_corpus_escopo.json`, `saidas/_catalogo_escopo.json` e as
  auditorias em `saidas/<licitação>/`).

O QUE ENTRA NO MAPA
  Só o que passa em `escopo.avaliar`. O mapa é das licitações **de folha de
  pagamento** — não do corpus inteiro. As 217 que ficam de fora não são ruído a
  documentar: são o que o filtro existe para não processar.

CUSTO
  R$ 0,00. Lê JSON do disco, não chama modelo nem rede.
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import escopo                                          # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")
EDITAIS = os.path.join(RAIZ, "Fopa-v2", "09-Editais")
CORPUS = os.path.join(SAIDAS, "_corpus_escopo.json")

RE_PREFIXO = re.compile(
    r"^(?:munic[íi]pio|prefeitura(?:\s+municipal)?|c[âa]mara(?:\s+municipal)?|"
    r"fundo|instituto|autarquia)\s+(?:municipal\s+)?d[eo]\s+", re.I)


def sem_acento(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def municipio(orgao: str) -> str:
    return RE_PREFIXO.sub("", (orgao or "").strip()).title() or (orgao or "").title()


def controle_do_inventario(pasta: str) -> str | None:
    """
    O `numero_controle_pncp` gravado quando a licitação foi baixada.

    Ele está em `item` nas coletas antigas e na raiz nas novas — as duas formas
    são lidas, porque reescrever inventário antigo só para uniformizar chave
    seria mexer em prova.
    """
    f = os.path.join(AMOSTRAS, pasta, "_inventario.json")
    if not os.path.isfile(f):
        return None
    try:
        d = json.load(io.open(f, encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return (d.get("controle")
            or d.get("numero_controle_pncp")
            or (d.get("item") or {}).get("numero_controle_pncp"))


def pastas_no_disco() -> tuple[dict[str, str], dict[str, str]]:
    """
    (por nome normalizado, por número de controle) -> nome real da pasta.

    CASAR POR NOME É FRÁGIL, E ISSO FOI MEDIDO.
    A pasta se chama pelo MUNICÍPIO; o corpus traz o ÓRGÃO. `Dispensa - Rio
    Branco-AC` é do `TRIBUNAL DE CONTAS DO ESTADO DO ACRE`, e nenhuma derivação
    de nome liga os dois. Por nome, a licitação aparecia como "não baixada"
    tendo sido extraída — errado, e em silêncio.

    O `numero_controle_pncp` é a chave que o próprio PNCP usa, e é a mesma do
    livro-razão do monitor. Nome fica só como reserva, para pasta sem inventário.
    """
    por_nome, por_controle = {}, {}
    for d in os.listdir(AMOSTRAS):
        if not os.path.isdir(os.path.join(AMOSTRAS, d)) or d.startswith("_"):
            continue
        k = sem_acento(d).lower()
        por_nome[k[7:] if k.startswith("aberto ") else k] = d
        ctrl = controle_do_inventario(d)
        if ctrl:
            por_controle[ctrl.strip()] = d
    return por_nome, por_controle


def estado(reg: dict, pastas: tuple[dict[str, str], dict[str, str]]
           ) -> tuple[str, str | None]:
    """(estado legível, nome da pasta) — a verdade vem do DISCO, não do livro."""
    por_nome, por_controle = pastas
    pasta = por_controle.get((reg.get("controle") or "").strip())
    if not pasta:
        chave = sem_acento("%s - %s-%s" % (reg.get("modalidade"),
                                           municipio(reg.get("orgao")),
                                           reg.get("uf"))).lower()
        pasta = por_nome.get(chave)
    if not pasta:
        return "não baixada", None
    if os.path.isfile(os.path.join(SAIDAS, pasta, "auditoria.json")):
        return "extraída", pasta
    if glob.glob(os.path.join(AMOSTRAS, pasta, "*.pdf")):
        return "baixada", pasta
    return "pasta vazia", pasta


def resumo_extracao(pasta: str) -> dict | None:
    f = os.path.join(SAIDAS, pasta, "auditoria.json")
    if not os.path.isfile(f):
        return None
    d = json.load(io.open(f, encoding="utf-8"))
    v = d.get("verificacao", {})
    return dict(
        modelo=d.get("uso", {}).get("modelo", "?"),
        paginas=d.get("paginas", 0), arquivos=len(d.get("arquivos", [])),
        ancorada=round(100 * v.get("taxa_ancorada", 0)),
        naoloc=v.get("nao_localizado", 0), reprov=v.get("reprovadas", 0))


def gerar_mapa(regs: list[dict], pastas) -> str:
    linhas = []
    for r in regs:
        est, pasta = estado(r, pastas)
        linhas.append(dict(r, _estado=est, _pasta=pasta,
                           _mun=municipio(r.get("orgao"))))

    por_estado = Counter(l["_estado"] for l in linhas)
    por_mod = Counter(l.get("modalidade") or "?" for l in linhas)
    por_uf = Counter(l.get("uf") or "?" for l in linhas)
    por_motivo = Counter(escopo.avaliar(l.get("objeto") or "")[1] for l in linhas)

    out = ["""---
tipo: dados
status: verificado
atualizado: 2026-09-23
tags:
  - editais
  - escopo
  - dados
---

# Mapa das licitações de folha

> [!warning] Nota gerada
> Escrita por `scripts/30_mapa_editais.py` a partir de `saidas/_corpus_escopo.json`
> e do que existe em disco. **Não editar à mão** — rode o script de novo.
>
> São %d licitações e o número cresce a cada coleta. Uma tabela mantida à mão
> estaria errada na primeira semana, e errada em silêncio.

Todas passam em `escopo.avaliar`. O corpus tem **%d** registros; as **%d** que
ficam de fora não estão aqui de propósito: são exatamente o que o filtro existe
para não processar. Ver [[MOC Editais]] e `saidas/_catalogo_escopo.json`.

## Onde cada uma está

| estado | quantas | o que significa |
|---|---|---|
""" % (len(linhas), len(linhas) + 217, 217)]

    significado = {
        "extraída": "documentos baixados e as 17 perguntas respondidas e verificadas",
        "baixada": "PDFs em disco, extração ainda não rodada",
        "não baixada": "só os metadados do PNCP; o download em lote ainda não chegou nela",
        "pasta vazia": "pasta existe sem PDF — lote interrompido no meio",
    }
    for est, n in por_estado.most_common():
        out.append("| **%s** | %d | %s |\n" % (est, n, significado.get(est, "")))

    out.append("\n## Por modalidade\n\n| modalidade | quantas |\n|---|---|\n")
    for m, n in por_mod.most_common():
        out.append("| %s | %d |\n" % (m, n))

    out.append("\n## Por UF\n\n")
    ufs = " · ".join("**%s** %d" % (u, n) for u, n in por_uf.most_common())
    out.append(ufs + "\n")

    out.append("""
## Por que cada uma passou no filtro

O filtro decide pelo **verbo**: operar a folha contra conceder crédito ao
servidor. O motivo de cada decisão fica gravado, porque é ele que permite
auditar o filtro sem reler 112 objetos.

| motivo | quantas |
|---|---|
""")
    for mo, n in por_motivo.most_common():
        out.append("| %s | %d |\n" % (mo, n))

    # ------------------------------------------------ a tabela completa
    out.append("""
## As licitações, por UF

`extraída` tem relatório em `amostras/<pasta>/RELATORIO.html`.
O link do PNCP abre a licitação na fonte.

""")
    por_uf_lista = defaultdict(list)
    for l in linhas:
        por_uf_lista[l.get("uf") or "?"].append(l)

    for uf in sorted(por_uf_lista):
        grupo = sorted(por_uf_lista[uf], key=lambda x: x["_mun"])
        out.append("### %s — %d\n\n" % (uf, len(grupo)))
        out.append("| município | modalidade | estado | controle |\n|---|---|---|---|\n")
        for l in grupo:
            ctrl = l.get("controle") or ""
            m = re.match(r"^(\d{14})-\d+-(\d+)/(\d{4})$", ctrl)
            link = ("[%s](https://pncp.gov.br/app/editais/%s/%s/%s)"
                    % (ctrl, m.group(1), m.group(3), int(m.group(2)))) if m else ctrl
            marca = {"extraída": "**extraída**", "baixada": "baixada",
                     "não baixada": "—", "pasta vazia": "⚠ vazia"}[l["_estado"]]
            out.append("| %s | %s | %s | %s |\n"
                       % (l["_mun"], l.get("modalidade") or "?", marca, link))
        out.append("\n")

    out.append("""## Relacionadas

[[MOC Editais]] · [[Resultados medidos]] · [[Pipeline de dados]] · [[Disponibilidade do PNCP]]
""")
    return "".join(out)


def gerar_moc_processados(pastas) -> str:
    """A tabela de processados, a partir das auditorias reais."""
    linhas = []
    for f in sorted(glob.glob(os.path.join(SAIDAS, "*", "auditoria.json"))):
        pasta = os.path.basename(os.path.dirname(f))
        if pasta.startswith("_"):
            continue
        r = resumo_extracao(pasta)
        linhas.append((pasta, r))

    out = ["| Licitação | Modelo | Arquivos | Páginas | Ancoragem | Não loc. | Reprov. |\n",
           "|---|---|---|---|---|---|---|\n"]
    for pasta, r in linhas:
        out.append("| `%s` | %s | %d | %d | %d%% | %d | %d |\n"
                   % (pasta, r["modelo"], r["arquivos"], r["paginas"],
                      r["ancorada"], r["naoloc"], r["reprov"]))
    return "".join(out), len(linhas)


def main() -> int:
    ap = argparse.ArgumentParser(description="Gera o mapa de editais no vault")
    ap.add_argument("--seco", action="store_true", help="não escreve, só mostra")
    a = ap.parse_args()

    corpus = json.load(io.open(CORPUS, encoding="utf-8"))
    regs = [r for r in corpus["registros"]
            if escopo.avaliar(r.get("objeto") or "")[0]]
    pastas = pastas_no_disco()

    texto = gerar_mapa(regs, pastas)
    tabela, n_proc = gerar_moc_processados(pastas)

    print("  corpus ............ %d registros" % len(corpus["registros"]))
    print("  passam no filtro .. %d" % len(regs))
    print("  extraídas ......... %d" % n_proc)

    # Extração que existe e o corpus não conhece não pode sumir do relatório.
    # Capão do Cipó/RS e Quevedos/RS vieram de uma coleta anterior a este corpus;
    # ficar em silêncio sobre elas faria o mapa parecer completo sem ser.
    casadas = {p for p in (estado(r, pastas)[1] for r in regs) if p}
    todas = {os.path.basename(os.path.dirname(f))
             for f in glob.glob(os.path.join(SAIDAS, "*", "auditoria.json"))
             if not os.path.basename(os.path.dirname(f)).startswith("_")}
    orfas = sorted(todas - casadas)
    if orfas:
        print("\n  EXTRAÍDAS FORA DO CORPUS: %d" % len(orfas))
        for o in orfas:
            print("     %s" % o)
        print("     (coleta anterior a este corpus — rode 24_corpus_escopo.py)")
    est = Counter(estado(r, pastas)[0] for r in regs)
    for k, v in est.most_common():
        print("     %-14s %d" % (k, v))

    if a.seco:
        print("\n  (--seco: nada escrito)")
        return 0

    destino = os.path.join(EDITAIS, "Mapa das licitações de folha.md")
    io.open(destino, "w", encoding="utf-8").write(texto)
    print("\n  escrito: %s" % os.path.relpath(destino, RAIZ))

    # substitui a tabela de processados do MOC
    moc = os.path.join(EDITAIS, "MOC Editais.md")
    s = io.open(moc, encoding="utf-8").read()
    marca_ini = "<!-- processados:inicio -->"
    marca_fim = "<!-- processados:fim -->"
    bloco = "%s\n%s%s" % (marca_ini, tabela, marca_fim)
    if marca_ini in s and marca_fim in s:
        s = re.sub(re.escape(marca_ini) + r".*?" + re.escape(marca_fim),
                   bloco.replace("\\", "\\\\"), s, flags=re.S)
        io.open(moc, "w", encoding="utf-8").write(s)
        print("  atualizado: %s (bloco de processados)" % os.path.relpath(moc, RAIZ))
    else:
        print("  AVISO: marcadores de processados não encontrados no MOC Editais.")
        print("  Adicione %s e %s em volta da tabela." % (marca_ini, marca_fim))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
