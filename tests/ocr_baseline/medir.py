# -*- coding: utf-8 -*-
"""
Mede se o Tesseract desta máquina reproduz o OCR do host das medições.

POR QUE MEDIR E NÃO BARRAR
  Todos os números de OCR do projeto saíram do Tesseract 5.4.0.20240606 da
  máquina de desenvolvimento (build MSVC, AVX512). A imagem Docker compila a
  mesma 5.4.0 no Linux, mas mesma minor não garante saída igual: em 23/09 a
  5.3.0 deu 0 de 6 páginas idênticas (BACKLOG.md:427-463), e o `|` de uma
  tabela virou o algarismo `1` na pirâmide salarial. Este script existe para
  que essa diferença seja VISTA e REGISTRADA, nunca descoberta por alguém que
  tentou reproduzir um número. Por isso nunca falha por diferença: se a imagem
  não reproduzir o host, a decisão da ADR-008 passa a ser "a imagem é a
  referência" (ver README.md), e este JSON é a evidência dessa decisão.

O QUE COMPARA
  As 6 PNG versionadas (páginas 1-6 do edital digitalizado de São Lourenço do
  Sul/RS, 150 dpi) passam pelo MESMO perfil que o pipeline usa em texto
  corrido (`fopa.ocr.PERFIL_TEXTO`, RN-20). O texto sai comparado com
  `pNN.host.txt` por igualdade exata e por `difflib.SequenceMatcher.ratio`
  com `autojunk=False` — o autojunk padrão colapsa para ~0,04 em página
  correta acima de 200 caracteres (lição do `03_ocr_benchmark.py`).

Uso:
  python tests/ocr_baseline/medir.py --saida docs/ocr-equivalencia-<sha>.json [--tesseract caminho]

  `<sha>` no nome é trocado pelos 12 primeiros hex do sha256 do binário do
  Tesseract usado (ou por `host` se o binário não puder ser lido).
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import platform
import shutil
import sys
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
# O pacote fopa mora em scripts/ e não é instalado: mesmo truque do 50_ocr_piramide.
sys.path.insert(0, os.path.join(RAIZ, "scripts"))

import pytesseract  # noqa: E402
from PIL import Image  # noqa: E402
from fopa import ocr  # noqa: E402

PERFIL = ocr.PERFIL_TEXTO


# ---------------------------------------------------------------- utilitários
def nome_png(pagina: int) -> str:
    return "p%02d.png" % pagina


def nome_txt(pagina: int) -> str:
    return "p%02d.host.txt" % pagina


def sha256_arquivo(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def resolver_tesseract(caminho: str | None) -> str:
    """
    Decide qual binário roda e aponta o pytesseract para ele.

    Ordem: argumento explícito → o que `fopa.ocr` já resolveu (FOPA_TESSERACT
    ou o padrão do Windows) → o `tesseract` do PATH. O último degrau é o que
    faz o script funcionar dentro da imagem Linux sem variável nenhuma.
    """
    candidatos = [caminho, ocr.TESSERACT_EXE, shutil.which("tesseract")]
    for c in candidatos:
        if c and os.path.exists(c):
            pytesseract.pytesseract.tesseract_cmd = c
            return c
    raise ocr.OcrIndisponivel(
        "tesseract não encontrado (tentei: %s)" % ", ".join(str(c) for c in candidatos))


def caminho_tessdata_por() -> str | None:
    """Onde está o por.traineddata em uso — o de `fopa.ocr` primeiro, depois os lugares usuais do Linux."""
    pastas = [ocr.TESSDATA, os.environ.get("TESSDATA_PREFIX"),
              "/usr/local/share/tessdata", "/usr/share/tesseract-ocr/5/tessdata",
              "/usr/share/tessdata"]
    for pasta in pastas:
        if pasta and os.path.isfile(os.path.join(pasta, "por.traineddata")):
            return os.path.join(pasta, "por.traineddata")
    return None


def tessdata_sha256() -> str | None:
    arquivo = caminho_tessdata_por()
    return sha256_arquivo(arquivo) if arquivo else None


def ocr_png(caminho_png: str) -> str:
    """OCR de uma PNG pelo mesmo caminho de código do pipeline (`ocr._ocr_imagem`)."""
    with Image.open(caminho_png) as img:
        return ocr._ocr_imagem(img.convert("RGB"), PERFIL)


def ler_texto(caminho: str) -> str:
    # newline="" preserva o que está no disco: a comparação é byte a byte.
    with open(caminho, encoding="utf-8", newline="") as f:
        return f.read()


def similaridade(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def versao_tesseract() -> str:
    return str(pytesseract.get_tesseract_version())


# ---------------------------------------------------------------- medição
def medir(tesseract: str | None = None) -> dict:
    binario = resolver_tesseract(tesseract)
    with open(os.path.join(AQUI, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)

    paginas = []
    for n in manifest["paginas"]:
        host = ler_texto(os.path.join(AQUI, nome_txt(n)))
        aqui = ocr_png(os.path.join(AQUI, nome_png(n)))
        paginas.append({
            "pagina": n,
            "identica": aqui == host,
            "similaridade": round(similaridade(host, aqui), 6),
            "chars_host": len(host),
            "chars_aqui": len(aqui),
        })

    return {
        "tesseract": versao_tesseract(),
        "tesseract_binario": binario,
        "tesseract_sha256": sha256_arquivo(binario),
        "tesseract_host": manifest.get("tesseract_host"),
        "tessdata_sha256": tessdata_sha256(),
        "tessdata_sha256_host": manifest.get("tessdata_sha256"),
        "configuracao_ocr": {"lang": PERFIL["lang"], "psm": PERFIL["psm"],
                             "oem": PERFIL["oem"], "dpi": manifest["dpi"]},
        "paginas": paginas,
        "identicas": sum(1 for p in paginas if p["identica"]),
        "similaridade_min": min(p["similaridade"] for p in paginas),
        "plataforma": {"sistema": platform.platform(), "maquina": platform.machine(),
                       "python": platform.python_version()},
        "medido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def resumo(r: dict) -> str:
    tess_igual = r["tessdata_sha256"] == r["tessdata_sha256_host"]
    linhas = ["OCR: %s  (host das medições: %s)" % (r["tesseract"], r["tesseract_host"]),
              "tessdata: %s  %s" % ((r["tessdata_sha256"] or "?")[:12],
                                     "igual ao host" if tess_igual else "DIFERENTE do host")]
    for p in r["paginas"]:
        linhas.append("  p%02d  %s  sim=%.4f  chars %d/%d"
                      % (p["pagina"], "idêntica " if p["identica"] else "DIFERENTE",
                         p["similaridade"], p["chars_host"], p["chars_aqui"]))
    linhas.append("idênticas: %d/%d   similaridade mínima: %.4f"
                  % (r["identicas"], len(r["paginas"]), r["similaridade_min"]))
    if r["identicas"] == len(r["paginas"]):
        linhas.append("esta máquina REPRODUZ o host.")
    else:
        linhas.append("esta máquina NÃO reproduz o host — ver README.md ('a imagem é a referência').")
    return "\n".join(linhas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="mede a equivalência de OCR com o host das medições")
    ap.add_argument("--saida", default="docs/ocr-equivalencia-<sha>.json",
                    help="JSON de saída; `<sha>` vira os 12 primeiros hex do sha256 do binário")
    ap.add_argument("--tesseract", default=None, help="caminho do binário (padrão: FOPA_TESSERACT, "
                    "o padrão do fopa.ocr ou o do PATH)")
    args = ap.parse_args(argv)
    # O resumo tem acentos; no console do Windows o Python cai em cp1252 e
    # o terminal em UTF-8 mostra lixo. O JSON gravado não passa por aqui.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    r = medir(args.tesseract)
    saida = args.saida.replace("<sha>", r["tesseract_sha256"][:12] if r["tesseract_sha256"] else "host")
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(resumo(r))
    print("gravado em %s" % saida)
    return 0  # medição, não portão: diferença é registrada, nunca é erro


if __name__ == "__main__":
    sys.exit(main())
