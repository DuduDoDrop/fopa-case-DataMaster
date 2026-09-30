# -*- coding: utf-8 -*-
"""
Gera a baseline de OCR: o PDF de 6 páginas, as 6 PNG a 150 dpi, o texto que o
Tesseract DESTA máquina extrai de cada uma, e o manifest.json.

Só roda na máquina de referência — hoje o host das medições (Tesseract
5.4.0.20240606). Rodar em outra máquina e commitar TROCA a referência, e é
exatamente isso que a decisão "a imagem é a referência" (README.md) prevê
quando chegar a hora: regenerar dentro da imagem.

POR QUE UM PDF DE 6 PÁGINAS E NÃO O DE 44
  O edital digitalizado tem 10,6 MB e está fora do git (`amostras/**/*.pdf`).
  As 6 primeiras páginas copiadas com `insert_pdf` têm 1,1 MB e rasterizam
  pixel a pixel igual ao original (conferido em 24/09/2026); é o que deixa a
  fixture regenerável num clone limpo.

Uso:
  python tests/ocr_baseline/gerar.py            # a partir do PDF versionado
  python tests/ocr_baseline/gerar.py --origem "amostras/.../01 - Edital original (digitalizado, 44p).pdf" --paginas 1 2 3 4 5 6
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import fitz  # noqa: E402
import medir  # noqa: E402
from fopa import ocr  # noqa: E402

PDF_ORIGEM = os.path.join("amostras", "Concorrencia - Eletronica - Sao Lourenco do Sul-RS",
                          "01 - Edital original (digitalizado, 44p).pdf")
PDF_FIXTURE = "sao-lourenco-scan-6p.pdf"
# Páginas 1-6 do original: são as que o BACKLOG.md:427-463 comparou (13.375
# caracteres no 5.4.0 — bate com a soma destas seis, e com nenhuma outra
# sequência natural). Incluem o preâmbulo e as três tabelas da pirâmide
# salarial (Contratos, Inativos, Ativos) — a p2 é a do `|` lido como `1`.
PAGINAS_PADRAO = [1, 2, 3, 4, 5, 6]


def extrair_subconjunto(origem: str, paginas: list[int], destino: str) -> None:
    doc = fitz.open(origem)
    novo = fitz.open()
    try:
        for n in paginas:
            novo.insert_pdf(doc, from_page=n - 1, to_page=n - 1)
        novo.save(destino, garbage=4, deflate=True)
    finally:
        novo.close()
        doc.close()


def procedencia_anterior(fixture: str, manifest: str) -> dict | None:
    """
    A `pdf_origem` do manifest atual, se ele descreve ESTE pdf (mesmo sha256).

    Rodar sem `--origem` é o caso normal (a fixture já está versionada), e antes
    isso gravava `pdf_origem: null` — a baseline perdia de qual edital e de quais
    páginas físicas veio (minor da revisão final da F0). Outro PDF, outro sha:
    a procedência antiga não vale para ele.
    """
    try:
        with open(manifest, encoding="utf-8") as f:
            anterior = json.load(f)
    except (OSError, ValueError):
        return None
    if anterior.get("sha256_pdf") != medir.sha256_arquivo(fixture):
        return None
    return anterior.get("pdf_origem")


def gerar(origem: str | None, paginas: list[int], dpi: int, tesseract: str | None) -> dict:
    binario = medir.resolver_tesseract(tesseract)
    ambiente = ocr.checar_ambiente()  # falha alto se faltar 'por'
    fixture = os.path.join(AQUI, PDF_FIXTURE)

    origem_info = None
    if origem:
        caminho_origem = origem if os.path.isabs(origem) else os.path.join(RAIZ, origem)
        extrair_subconjunto(caminho_origem, paginas, fixture)
        origem_info = {"caminho": os.path.relpath(caminho_origem, RAIZ).replace(os.sep, "/"),
                       "sha256": medir.sha256_arquivo(caminho_origem),
                       "paginas_fisicas": paginas}
    elif not os.path.exists(fixture):
        raise SystemExit("sem --origem e sem %s: nada de onde gerar" % fixture)
    else:
        origem_info = procedencia_anterior(fixture, os.path.join(AQUI, "manifest.json"))

    arquivos = {}
    doc = fitz.open(fixture)
    try:
        if len(doc) != len(paginas):
            raise SystemExit("%s tem %d páginas, --paginas tem %d" % (fixture, len(doc), len(paginas)))
        for i, n in enumerate(paginas):
            png = os.path.join(AQUI, medir.nome_png(n))
            txt = os.path.join(AQUI, medir.nome_txt(n))
            ocr._renderizar(doc, i, dpi).save(png, format="PNG", optimize=True)
            # O texto sai da PNG gravada, não do pixmap: é a PNG que a outra
            # máquina vai ler, então é dela que a referência tem de vir.
            texto = medir.ocr_png(png)
            with open(txt, "w", encoding="utf-8", newline="") as f:
                f.write(texto)
            arquivos[os.path.basename(png)] = medir.sha256_arquivo(png)
            arquivos[os.path.basename(txt)] = medir.sha256_arquivo(txt)
            print("  p%02d  %5d chars" % (n, len(texto)))
    finally:
        doc.close()

    manifest = {
        "pdf": os.path.relpath(fixture, RAIZ).replace(os.sep, "/"),
        "sha256_pdf": medir.sha256_arquivo(fixture),
        "pdf_origem": origem_info,
        "paginas": paginas,
        "dpi": dpi,
        "tesseract_host": ambiente["tesseract"],
        "tesseract_binario": binario,
        "tessdata_sha256": medir.tessdata_sha256(),
        "configuracao_ocr": {"lang": medir.PERFIL["lang"], "psm": medir.PERFIL["psm"],
                             "oem": medir.PERFIL["oem"], "perfil": "fopa.ocr.PERFIL_TEXTO"},
        "arquivos": arquivos,
        "plataforma": {"sistema": platform.platform(), "maquina": platform.machine(),
                       "python": platform.python_version()},
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with open(os.path.join(AQUI, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="regenera a baseline de OCR")
    ap.add_argument("--origem", default=None,
                    help="PDF completo de onde extrair as páginas (padrão: usa o %s já versionado)" % PDF_FIXTURE)
    ap.add_argument("--paginas", type=int, nargs="+", default=PAGINAS_PADRAO,
                    help="números FÍSICOS das páginas no PDF de origem")
    ap.add_argument("--dpi", type=int, default=medir.PERFIL["dpi"])
    ap.add_argument("--tesseract", default=None)
    args = ap.parse_args(argv)
    # O resumo tem acentos; no console do Windows o Python cai em cp1252 e
    # o terminal em UTF-8 mostra lixo. O JSON gravado não passa por aqui.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.origem is None and not os.path.exists(os.path.join(AQUI, PDF_FIXTURE)) \
            and os.path.exists(os.path.join(RAIZ, PDF_ORIGEM)):
        args.origem = PDF_ORIGEM
    m = gerar(args.origem, args.paginas, args.dpi, args.tesseract)
    print("manifest: %s  tesseract %s  tessdata %s"
          % (m["pdf"], m["tesseract_host"], (m["tessdata_sha256"] or "?")[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
