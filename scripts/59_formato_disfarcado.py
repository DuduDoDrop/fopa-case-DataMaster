# -*- coding: utf-8 -*-
"""
Quantos arquivos do acervo terminam em .pdf e NAO sao PDF -- e quanto custa.

    python 59_formato_disfarcado.py              # so censo
    python 59_formato_disfarcado.py --reparar    # extrai os ZIP que ficaram fechados

NAO CHAMA MODELO. NAO CHAMA REDE (o reparo trabalha em cima do que ja esta
em disco).

O QUE ISTO DESCOBRIU
  O censo do acervo (41_censo_pdf.py) dizia "12 arquivos nao medidos:
  FileDataError". Erro de leitura de PDF, facil de ler como corrupcao. Nao e
  corrupcao: o arquivo nao e PDF. O PNCP entrega o nome com extensao .pdf
  porque o campo de metadado diz PDF, e o conteudo e outra coisa.

  Medido em 23/09/2026, sobre os arquivos com extensao .pdf do acervo:

      PDF de verdade ......... 2.185
      ZIP / OOXML ............    65
      RAR ....................     1
      formato nao identificado     2

  Os 65 se dividem em duas historias MUITO diferentes:

  1. ZIP com PDF dentro que nunca foi aberto. O `28_baixar_licitacao.py`
     sabe desempacotar desde que a funcao `desempacotar()` existe -- mas ele
     e idempotente pela PASTA existir, entao nunca voltou nas licitacoes
     baixadas antes disso. Quatro licitacoes ficaram com o edital trancado
     dentro do proprio arquivo. E isto que o `--reparar` conserta.

  2. DOCX/XLSX renomeado para .pdf. A assinatura e a mesma de um ZIP, porque
     OOXML E um ZIP -- so que com `[Content_Types].xml` e `word/` dentro, em
     vez de PDF. O pipeline nao le, e NAO da para consertar aqui: ver a
     secao final.

POR QUE O NUMERO QUE IMPORTA E POR LICITACAO, NAO POR ARQUIVO
  67 de 2.252 arquivos e 3,0% e parece pouco. Mas um anexo ilegivel nao
  custa nada se o edital estiver do lado. O que custa e a licitacao que fica
  SEM NENHUM documento legivel -- e essa conta e a que o relatorio fecha.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import sys
import time
import zipfile
from collections import Counter

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
AMOSTRAS = os.path.join(RAIZ, "amostras")
sys.path.insert(0, AQUI)

DESTINO = os.path.join(RAIZ, "saidas", "_formato_disfarcado.json")


def _baixador():
    """Importa o 28, cujo nome comeca com digito e nao entra num import normal."""
    p = os.path.join(AQUI, "28_baixar_licitacao.py")
    spec = importlib.util.spec_from_file_location("baixador", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def assinatura(caminho: str) -> str:
    """O que o arquivo E, pelos primeiros bytes -- nao pelo nome."""
    try:
        with io.open(caminho, "rb") as f:
            cab = f.read(8)
    except OSError:
        return "ilegivel"
    if cab.startswith(b"%PDF"):
        return "PDF"
    if cab.startswith(b"Rar!"):
        return "RAR"
    if cab.startswith(b"\xd0\xcf\x11\xe0"):
        return "DOC/XLS antigo"
    if not cab.startswith(b"PK\x03\x04"):
        return "desconhecido"
    # A partir daqui e um container ZIP. O que ha DENTRO e que separa
    # "pacote com o edital" de "documento do Word com outro nome".
    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
    except Exception:                                             # noqa: BLE001
        return "ZIP corrompido"
    if any(n.lower().endswith(".pdf") for n in nomes):
        return "ZIP com PDF"
    if "[Content_Types].xml" in nomes or any(n.startswith("word/") for n in nomes):
        return "OOXML (Word/Excel)"
    if any(n.lower().endswith(".zip") for n in nomes):
        return "ZIP dentro de ZIP"
    return "ZIP sem PDF"


def varrer() -> tuple[dict, list]:
    """Assinatura de todo .pdf do acervo, agrupada por licitacao."""
    por_pasta = {}
    for pasta in sorted(os.listdir(AMOSTRAS)):
        d = os.path.join(AMOSTRAS, pasta)
        if not os.path.isdir(d):
            continue
        arqs = [a for a in os.listdir(d) if a.lower().endswith(".pdf")]
        if not arqs:
            continue
        por_pasta[pasta] = {a: assinatura(os.path.join(d, a)) for a in arqs}
    disfarcados = [(p, a, t) for p, m in por_pasta.items()
                   for a, t in m.items() if t != "PDF"]
    return por_pasta, disfarcados


def reparar(pastas: list) -> int:
    """Abre os ZIP que tem PDF dentro e ficaram fechados. Atualiza o inventario."""
    mod = _baixador()
    consertadas = 0
    for pasta in pastas:
        d = os.path.join(AMOSTRAS, pasta)
        alvos = [a for a in sorted(os.listdir(d))
                 if a.lower().endswith(".pdf")
                 and assinatura(os.path.join(d, a)) in ("ZIP com PDF",
                                                        "ZIP dentro de ZIP")]
        if not alvos:
            continue
        inv_p = os.path.join(d, "_inventario.json")
        inv = (json.load(io.open(inv_p, encoding="utf-8"))
               if os.path.isfile(inv_p) else {"arquivos": []})
        antigos = inv.get("arquivos") or []
        ja = {x.get("arquivo") for x in antigos}
        print("  %s" % pasta)
        novos = 0
        for a in alvos:
            caminho = os.path.join(d, a)
            # o `doc` so alimenta os metadados do ArquivoBaixado; pegamos o
            # que o inventario ja sabe sobre ESTE arquivo, para nao inventar
            # CASE-INSENSITIVE de proposito. O Windows lista o arquivo como
            # `...editais_1789562401.zip.pdf` e o inventario gravou
            # `...EDITAIS_1789562401.ZIP.pdf` -- o mesmo arquivo, duas grafias.
            # Comparar exato fez o Sao Joao do Tigre perder a `origem` do pai e
            # quebrou a assercao de procedencia do 40_fumaca.py.
            meta = next((x for x in antigos
                         if (x.get("arquivo") or "").lower() == a.lower()), {})
            doc = {"sequencialDocumento": meta.get("seq"),
                   "tipoDocumentoNome": meta.get("tipo") or "Edital",
                   "url": meta.get("origem")}
            saiu = mod.desempacotar(caminho, doc)
            if not saiu:
                print("     %-58s nada extraido" % a[:58])
                continue
            for b in saiu:
                base = os.path.basename(b.caminho)
                if base in ja:
                    continue
                inv.setdefault("arquivos", []).append(
                    dict(seq=b.seq, tipo=b.tipo, titulo=b.titulo, arquivo=base,
                         bytes=b.bytes, sha256=b.sha256, origem=b.origem))
                ja.add(base)
                novos += 1
                print("     %-58s -> %s" % (a[:58], base[:52]))
        if novos:
            inv["reparado_em"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            inv["reparo"] = ("ZIP que ficaram fechados porque o download e"
                             " idempotente pela pasta, nao pelo conteudo")
            json.dump(inv, io.open(inv_p, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            consertadas += 1
    return consertadas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reparar", action="store_true")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    por_pasta, disfarcados = varrer()
    total = sum(len(m) for m in por_pasta.values())
    print("=" * 96)
    print("  FORMATO DISFARÇADO — %d arquivos .pdf em %d licitações"
          % (total, len(por_pasta)))
    print("=" * 96)
    print()
    c = Counter(t for _, _, t in disfarcados)
    print("  o que os %d não-PDF realmente são:" % len(disfarcados))
    for t, n in c.most_common():
        print("     %-22s %4d" % (t, n))
    print()

    # a conta que importa: licitação sem NENHUM documento legível
    sem_nada = []
    for pasta, m in por_pasta.items():
        if not any(t == "PDF" for t in m.values()):
            sem_nada.append((pasta, sorted(set(m.values()))))
    print("  licitações SEM NENHUM PDF legível ... %d de %d (%.1f%%)"
          % (len(sem_nada), len(por_pasta),
             100.0 * len(sem_nada) / max(1, len(por_pasta))))
    reparaveis, perdidas = [], []
    for par in sem_nada:
        (reparaveis if any(t in ("ZIP com PDF", "ZIP dentro de ZIP")
                           for t in par[1]) else perdidas).append(par)
    print("     destas, recuperáveis agora ....... %d (ZIP fechado)" % len(reparaveis))
    print("     destas, fora do alcance do código  %d (Word/RAR)" % len(perdidas))
    print()
    recup = {p for p, _ in reparaveis}
    for pasta, tipos in sem_nada:
        marca = "REPARÁVEL" if pasta in recup else "—"
        print("     %-10s %-56s %s" % (marca, pasta[:56], ", ".join(tipos)))
    print()

    if a.reparar and reparaveis:
        print("-" * 96)
        print("  REPARO — abrindo os ZIP que ficaram fechados")
        print("-" * 96)
        n = reparar(sorted(recup))
        print("\n  %d licitação(ões) reparada(s)." % n)
        print("  Rode `41_censo_pdf.py` de novo para o acervo refletir isso.")
    elif reparaveis:
        print("  Rode com --reparar para abrir os %d ZIP fechados."
              % len(reparaveis))

    print()
    print("-" * 96)
    print("  O QUE O CÓDIGO NÃO RESOLVE SOZINHO")
    print("-" * 96)
    print("  Os arquivos OOXML são editais escritos no Word e publicados com")
    print("  extensão .pdf. O texto está lá — `word/document.xml`, sem OCR,")
    print("  sem imagem, mais fácil de ler que qualquer PDF do acervo.")
    print()
    print("  Mas o Verificador ancora cada resposta em PÁGINA de PDF (RN-05).")
    print("  Um .docx não tem página: a paginação nasce na hora de imprimir e")
    print("  depende da fonte instalada. Converter geraria número de página que")
    print("  não corresponde a documento nenhum — pior que não ter âncora,")
    print("  porque parece ter. Decisão pendente, registrada no BACKLOG.md.")

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps(
        {"medido_em": time.strftime("%Y-%m-%d"), "arquivos": total,
         "licitacoes": len(por_pasta), "disfarcados": len(disfarcados),
         "por_tipo": dict(c),
         "sem_pdf_legivel": [{"pasta": p, "tipos": t} for p, t in sem_nada],
         "reparaveis": sorted(recup),
         "fora_de_alcance": [p for p, _ in perdidas]},
        ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_formato_disfarcado.json · custo R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
