# -*- coding: utf-8 -*-
"""
Censo do acervo — abre todo PDF baixado e mede páginas, texto e necessidade de OCR.

    python 41_censo_pdf.py              # mede e grava no inventário
    python 41_censo_pdf.py --so-ler     # só relata, não escreve

POR QUE ISTO EXISTE
  O inventário do coletor grava procedência (sha256, origem, timestamp) mas NÃO
  grava página nem necessidade de OCR — e o esquema antigo gravava. O resultado
  e que qualquer contagem feita a partir dos inventários mistura dois mundos e
  devolve numeros impossiveis: numa medicao de 23/09 deu "609 arquivos, 369
  paginas", porque so as 12 pastas antigas tinham o campo.

  O numero errado nao parecia errado. Parecia so um acervo com PDFs curtinhos.
  Foi a razao entre arquivos e paginas que denunciou — e essa razao so chamou
  atencao porque a medicao anterior existia para comparar.

  Moral: um campo que existe em parte do acervo e pior que um campo que nao
  existe em lugar nenhum, porque a agregacao silenciosamente responde pela
  parte que tem o campo e apresenta o resultado como se fosse do todo.

COMO DECIDE QUE PRECISA DE OCR
  Rasterizar e caro; a heuristica e a mesma do `fopa/ocr.py`: se a pagina
  devolve menos de LIMIAR_CHARS caracteres de texto nativo, ela e imagem.
"""
from __future__ import annotations

import argparse
import collections
import glob
import io
import json
import os
import statistics
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
AMOSTRAS = os.path.join(RAIZ, "amostras")

sys.path.insert(0, AQUI)
from fopa import execucao  # noqa: E402

LIMIAR_CHARS = 100          # por página; abaixo disso é digitalizada


def medir(caminho: str) -> dict | None:
    try:
        import pymupdf
        with pymupdf.open(caminho) as d:
            chars = 0
            pgs_vazias = 0
            for pg in d:
                t = pg.get_text() or ""
                chars += len(t.strip())
                if len(t.strip()) < LIMIAR_CHARS:
                    pgs_vazias += 1
            n = d.page_count
    except Exception as e:                                        # noqa: BLE001
        return {"erro": "%s: %s" % (type(e).__name__, str(e)[:80])}
    return {"pag": n, "chars": chars, "pag_sem_texto": pgs_vazias,
            "requer_ocr": bool(n) and pgs_vazias >= max(1, n // 2)}


def main() -> int:
    _t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--so-ler", action="store_true", help="não grava no inventário")
    a = ap.parse_args()

    invs = [f for f in sorted(glob.glob(os.path.join(AMOSTRAS, "*", "_inventario.json")))
            if not os.path.basename(os.path.dirname(f)).startswith("_")]

    tot_arq = tot_pag = ocr_arq = ocr_pag = 0
    erros = []
    por_lic_arq, por_lic_pag = [], []
    com_ocr = 0
    maiores = []
    tipos = collections.Counter()
    multi_edital = sem_edital = 0

    for f in invs:
        pasta = os.path.dirname(f)
        lic = os.path.basename(pasta)
        d = json.load(io.open(f, encoding="utf-8"))
        lst = d.get("arquivos", [])
        n_ed = 0
        tem_ocr = False
        pag_lic = 0

        for reg in lst:
            tipo = (reg.get("tipo") or "Outros Documentos").strip()
            tipos[tipo] += 1
            if tipo.lower().startswith("edital"):
                n_ed += 1

            nome = reg.get("arquivo") or reg.get("nome") or reg.get("titulo")
            p = os.path.join(pasta, nome) if nome else None
            if not p or not os.path.isfile(p):
                # esquema antigo pode ter o campo sem o arquivo casar pelo nome
                if reg.get("pag") is not None:
                    tot_pag += reg["pag"]; pag_lic += reg["pag"]
                    if reg.get("requer_ocr"):
                        ocr_arq += 1; ocr_pag += reg["pag"]; tem_ocr = True
                    tot_arq += 1
                else:
                    erros.append("%s :: arquivo não encontrado: %s" % (lic[:40], nome))
                continue

            m = medir(p)
            tot_arq += 1
            if "erro" in m:
                erros.append("%s :: %s :: %s" % (lic[:40], (nome or "")[:40], m["erro"]))
                continue
            reg.update(m)
            tot_pag += m["pag"]; pag_lic += m["pag"]
            if m["requer_ocr"]:
                ocr_arq += 1; ocr_pag += m["pag"]; tem_ocr = True
                maiores.append((m["pag"], lic, nome))

        if n_ed > 1:
            multi_edital += 1
        if n_ed == 0:
            sem_edital += 1
        if tem_ocr:
            com_ocr += 1
        por_lic_arq.append(len(lst))
        por_lic_pag.append(pag_lic)

        if not a.so_ler:
            d["censo_em"] = "2026-09-23"
            json.dump(d, io.open(f, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)

    n = len(invs)
    print("=" * 78)
    print("  CENSO DO ACERVO — %d licitações" % n)
    print("=" * 78)
    print("  arquivos ............... %d" % tot_arq)
    print("  páginas ................ %d" % tot_pag)
    print("  páginas por arquivo .... %.1f de média" % (tot_pag / tot_arq if tot_arq else 0))
    print()
    print("  arquivos por licitação . %d a %d · mediana %d · média %.1f"
          % (min(por_lic_arq), max(por_lic_arq),
             statistics.median(por_lic_arq), sum(por_lic_arq) / n))
    print("  só UM arquivo .......... %d (%.0f%%)"
          % (sum(1 for x in por_lic_arq if x == 1),
             100.0 * sum(1 for x in por_lic_arq if x == 1) / n))
    print("  páginas por licitação .. %d a %d · mediana %d"
          % (min(por_lic_pag), max(por_lic_pag), statistics.median(por_lic_pag)))
    print()
    print("  >1 arquivo tipo Edital . %d (%.0f%%)" % (multi_edital, 100.0 * multi_edital / n))
    print("  NENHUM tipo Edital ..... %d (%.0f%%)" % (sem_edital, 100.0 * sem_edital / n))
    print()
    print("  exigem OCR ............. %d arquivos (%.1f%%)"
          % (ocr_arq, 100.0 * ocr_arq / tot_arq if tot_arq else 0))
    print("  páginas sob OCR ........ %d (%.1f%%)"
          % (ocr_pag, 100.0 * ocr_pag / tot_pag if tot_pag else 0))
    print("  licitações com OCR ..... %d (%.0f%%)" % (com_ocr, 100.0 * com_ocr / n))
    print()
    print("  tipos de documento:")
    for t, c in tipos.most_common(10):
        print("   %5d  %s" % (c, t))
    if maiores:
        print("\n  maiores digitalizados:")
        for p, lic, nome in sorted(maiores, reverse=True)[:6]:
            print("   %4d pág  %-44s %s" % (p, lic[:44], (nome or "")[:34]))
    if erros:
        print("\n  %d arquivo(s) não medido(s):" % len(erros))
        for e in erros[:12]:
            print("   · %s" % e)
    if not a.so_ler:
        print("\n  Campos gravados no inventário: pag, chars, pag_sem_texto, requer_ocr")
    execucao.registrar("41_censo_pdf.py", _t0, licitacoes=n,
                       arquivos=tot_arq, paginas=tot_pag,
                       nao_medidos=len(erros))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
