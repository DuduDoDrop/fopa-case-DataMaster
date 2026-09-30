# -*- coding: utf-8 -*-
"""
Os dois experimentos que estavam abertos na ADR-008, medidos.

  1. `--oem 0` com whitelist de digitos nas celulas da tabela
  2. pre-processamento (binarizacao, deskew) antes do OCR

O GABARITO VEM DO PROPRIO DOCUMENTO, e por isso este teste nao precisa de
rotulagem humana: as tabelas de piramide do edital de Sao Lourenco do Sul/RS
trazem a linha `Total N` impressa. Se a soma das linhas bater com o total
impresso, o OCR leu a coluna de quantidade certo. Se nao bater, errou -- e a
diferenca diz quanto.

O GABARITO, conferido a mao: as duas tabelas completas da pagina 2 somam
**674** (Inativos e Pensionistas) e **960** (Ativos).

E a medicao nao compara so o digito. Compara DUAS coisas que se opoem:

  digito   -- a soma da coluna de quantidade bate com o gabarito?
  rotulo   -- as linhas chegam com o prefixo "De R$ X ate R$ Y", que e do
              que a RE_FAIXA do verificador precisa para ligar quantidade
              a faixa?

Um perfil pode ganhar num e perder no outro, e ai nao serve: quantidade sem
faixa nao da ticket medio, nao da concentracao de folha e nao da consignado.
Medir so o digito esconderia exatamente isso.

    python 50_ocr_piramide.py
"""
import io
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz                                            # noqa: E402
import pytesseract                                     # noqa: E402
from PIL import Image, ImageOps                        # noqa: E402
from fopa import ocr                                   # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(RAIZ, "amostras",
                   "Concorrencia - Eletronica - Sao Lourenco do Sul-RS",
                   "01 - Edital original (digitalizado, 44p).pdf")
# indice 0-based -> gabarito conferido a mao da coluna de quantidade.
# p2: tabela "Inativos e Pensionistas" completa, 11 faixas, soma 674.
# p3: tabela "Ativos" completa, 11 faixas, soma 960.
# A sequencia, e nao a soma: soma esconde compensacao de erro, e o parser
# pega sobra da tabela anterior na mesma pagina. Sequencia e inequivoca.
PAGINAS = {
    1: [2, 90, 61, 66, 150, 143, 63, 28, 12, 8, 51],     # Inativos, soma 674
    2: [1, 26, 66, 181, 167, 174, 101, 80, 47, 38, 79],  # Ativos, soma 960
}

# linha de faixa: "De R$ 1.000,01 ate R$ 2.000,00 90 R$ 147.033,67 ..."
# a quantidade e o PRIMEIRO inteiro depois do segundo valor monetario, e nao
# tem virgula -- e o que a distingue do dinheiro que vem logo atras.
RE_LINHA = re.compile(
    r"(?:de|acima\s+de)\s+R\$\s*[\d.]+,\d{2}"
    r"(?:\s*at[ée]\s*R\$\s*[\d.]+,\d{2})?"
    r"[^\d\n]{0,12}(\d{1,5})(?![\d,])", re.I)
# linha SEM rotulo de faixa: so a quantidade e dois valores monetarios. E o
# que sobra quando o psm quebra a tabela em colunas -- o numero certo, orfao.
RE_ORFA = re.compile(
    r"^\s*(\d{1,5})\s+R\$?\s*[\d.]+,\d{2}\s+R\$?\s*[\d.]+,\d{2}\s*$")

def ler(texto: str) -> dict:
    """Separa o que veio ROTULADO do que veio orfao, e soma cada um."""
    rot, orf = [], []
    for l in texto.splitlines():
        m = RE_LINHA.search(l)
        if m:
            rot.append(int(m.group(1)))
            continue
        o = RE_ORFA.match(l)
        if o:
            orf.append(int(o.group(1)))
    return {"rotuladas": rot, "orfas": orf,
            "soma_total": sum(rot) + sum(orf), "soma_rotulada": sum(rot)}


def render(pagina: int, dpi: int) -> Image.Image:
    doc = fitz.open(PDF)
    try:
        pix = doc[pagina].get_pixmap(dpi=dpi)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


def binarizar(img: Image.Image, corte: int = 160) -> Image.Image:
    return ImageOps.grayscale(img).point(lambda p: 255 if p > corte else 0, "L")


def rodar(img: Image.Image, psm: int, oem: int, whitelist: str | None) -> str:
    cfg = "--psm %d --oem %d" % (psm, oem)
    if whitelist:
        cfg += " -c tessedit_char_whitelist=%s" % whitelist
    return pytesseract.image_to_string(img, lang="por", config=cfg)


def main() -> int:
    amb = ocr.checar_ambiente()
    print("=" * 96)
    print("  OCR DA PIRAMIDE — gabarito embutido no proprio documento")
    print("=" * 96)
    print("  tesseract %s | %s" % (amb["tesseract"], os.path.basename(PDF)))
    print()

    # Cache de renderizacao: renderizar a 400 dpi custa segundos, e varios
    # experimentos usam a mesma imagem.
    cache: dict[tuple[int, int], Image.Image] = {}

    def img(pagina: int, dpi: int) -> Image.Image:
        k = (pagina, dpi)
        if k not in cache:
            cache[k] = render(pagina, dpi)
        return cache[k]

    EXPERIMENTOS = [
        ("PERFIL_TABELA atual (400dpi psm4 oem3)", 400, 4, 3, None, False),
        ("oem 0 (legado, sem LSTM)",               400, 4, 0, None, False),
        ("whitelist de digitos (oem 3)",           400, 4, 3,
         "0123456789R$.,-/ ateAcimdoDE", False),
        ("oem 1 (so LSTM)",                        400, 4, 1, None, False),
        ("psm 6 (bloco uniforme)",                 400, 6, 3, None, False),
        ("600 dpi",                                600, 4, 3, None, False),
        ("binarizado (corte 160)",                 400, 4, 3, None, True),
        ("binarizado + 600 dpi",                   600, 4, 3, None, True),
    ]

    linhas = []
    for pg, alvo in PAGINAS.items():
        print("  p%d — %d faixas, soma %d  %s"
              % (pg + 1, len(alvo), sum(alvo), alvo))
    print()
    print("  %-34s %6s   %s"
          % ("experimento", "tempo", "quantidades do gabarito recuperadas"))
    print("  " + "-" * 92)
    for nome, dpi, psm, oem, wl, binar in EXPERIMENTOS:
        t, por_pagina, erro = time.time(), {}, None
        for pg, alvo in PAGINAS.items():
            try:
                im = img(pg, dpi)
                if binar:
                    im = binarizar(im)
                por_pagina[pg] = ler(ocr.limpar_assinatura(rodar(im, psm, oem, wl)))
            except Exception as e:                   # noqa: BLE001
                erro = "%s %s" % (type(e).__name__,
                                  str(e).strip().splitlines()[-1][:40]
                                  if str(e).strip() else "")
                break
        if erro:
            print("  %-34s %6s   ERRO %s" % (nome[:34], "-", erro))
            linhas.append({"experimento": nome, "erro": erro})
            continue
        dt = time.time() - t
        # Quantos valores do gabarito foram recuperados COM rotulo de faixa, e
        # quantos so como numero orfao. Conta por multiconjunto: um 66 que
        # aparece duas vezes no gabarito precisa aparecer duas vezes na leitura.
        from collections import Counter
        r_rot = r_orf = alvo_n = 0
        for pg, alvo in PAGINAS.items():
            alvo_n += len(alvo)
            falta = Counter(alvo)
            for x in por_pagina[pg]["rotuladas"]:
                if falta.get(x):
                    falta[x] -= 1
                    r_rot += 1
            for x in por_pagina[pg]["orfas"]:
                if falta.get(x):
                    falta[x] -= 1
                    r_orf += 1
        perdidos = alvo_n - r_rot - r_orf
        print("  %-34s %5.1fs   %2d/%d com faixa   %2d orfaos   %2d perdidos"
              % (nome[:34], dt, r_rot, alvo_n, r_orf, perdidos))
        linhas.append({"experimento": nome, "dpi": dpi, "psm": psm, "oem": oem,
                       "whitelist": bool(wl), "binarizado": binar,
                       "segundos": round(dt, 1), "de": alvo_n,
                       "com_faixa": r_rot, "orfaos": r_orf, "perdidos": perdidos,
                       "paginas": {str(pg + 1): por_pagina[pg] for pg in PAGINAS}})

    print()
    print()
    print("  LEITURA das tres colunas:")
    print("   com faixa -- o numero veio E veio colado ao `De R$ X ate R$ Y`.")
    print("                E o unico caso que a RE_FAIXA do verificador usa.")
    print("   orfaos    -- o numero veio certo e a faixa se perdeu. Serve para")
    print("                somar e conferir total; NAO serve para ticket medio,")
    print("                concentracao de folha nem estimativa de consignado.")
    print("   perdidos  -- o OCR nao devolveu o numero de jeito nenhum.")
    print()
    print("  Um orfao nao e meio acerto: para o que o banco precisa decidir,")
    print("  quantidade sem faixa salarial vale quase o mesmo que nada.")

    dest = os.path.join(RAIZ, "saidas", "_ocr_piramide.json")
    io.open(dest, "w", encoding="utf-8").write(json.dumps(
        {"medido_em": time.strftime("%Y-%m-%d"), "tesseract": amb["tesseract"],
         "pdf": os.path.basename(PDF),
         "gabarito": {str(k + 1): v for k, v in PAGINAS.items()},
         "experimentos": linhas}, ensure_ascii=False, indent=1))
    print("\n  gravado em saidas/_ocr_piramide.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
