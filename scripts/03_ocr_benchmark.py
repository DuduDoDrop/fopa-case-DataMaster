# -*- coding: utf-8 -*-
"""
Benchmark de OCR para editais — FOPA. Versao 2.

CORRECAO v2: a v1 usava difflib.SequenceMatcher com autojunk ligado (padrao).
Em sequencias acima de 200 elementos o autojunk trata como ruido todo elemento
que aparece em mais de 1% da sequencia — o que, em texto, sao as letras comuns.
Resultado: similaridade colapsava para ~0,04 em paginas cujo OCR estava correto.
Sintoma: bimodalidade (0,87 / 0,04) sem causa fisica. Corrigido com
autojunk=False e medicao em nivel de PALAVRA, que e a unidade que interessa.
"""
import os, io, time, json, difflib, re, unicodedata
import fitz
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Users\Nome\tessdata"

AM = r"C:\Users\Nome\Projetos\projeto-fopa\amostras"
PASTA = os.path.join(AM, "Concorrencia - Eletronica - Sao Lourenco do Sul-RS")
PDF_DIGITAL = os.path.join(PASTA, "05 - Edital correto (VIGENTE).pdf")
PDF_SCAN = os.path.join(PASTA, "01 - Edital original (digitalizado, 44p).pdf")
OUT = os.path.join(AM, "_ocr_benchmark")
os.makedirs(OUT, exist_ok=True)

RUIDO = re.compile(r"assinado por \d+ pessoas?:.*|para verificar a autenticidade.*|"
                   r"c[oó]digo para verifica[çc][ãa]o:.*|este documento foi assinado.*", re.I)


def limpa(s):
    s = RUIDO.sub(" ", s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def palavras(s):
    return re.findall(r"[a-z0-9][a-z0-9/.,:%-]*", limpa(s))


def sim_palavra(a, b):
    pa, pb = palavras(a), palavras(b)
    if not pa and not pb:
        return 1.0
    m = difflib.SequenceMatcher(None, pa, pb, autojunk=False)
    return m.ratio()


def sim_char(a, b):
    m = difflib.SequenceMatcher(None, limpa(a), limpa(b), autojunk=False)
    return m.ratio()


def render(pdf, i, dpi):
    doc = fitz.open(pdf)
    pix = doc[i].get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img


def ocr(img, lang, psm):
    return pytesseract.image_to_string(img, lang=lang, config="--psm %d --oem 3" % psm)


doc = fitz.open(PDF_DIGITAL)
N = len(doc)
GT = [doc[i].get_text() for i in range(N)]
doc.close()

AMOSTRA = [0, 4, 8, 12, 16, 20]
GRID = [("por", 150, 3), ("por", 200, 3), ("por", 300, 3), ("por", 400, 3),
        ("por", 300, 6), ("por", 300, 4), ("eng", 300, 3)]

print("=" * 82)
print("EXPERIMENTO A - grid de configuracao (6 paginas, gabarito conhecido)")
print("=" * 82)
print("%-5s %5s %4s | %11s | %11s | %8s" % ("lang", "dpi", "psm", "sim.palavra", "sim.caract", "seg/pag"))
print("-" * 82)
res = []
cache = {}
for lang, dpi, psm in GRID:
    t0 = time.time()
    sp, sc = [], []
    for p in AMOSTRA:
        if (p, dpi) not in cache:
            cache[(p, dpi)] = render(PDF_DIGITAL, p, dpi)
        t = ocr(cache[(p, dpi)], lang, psm)
        sp.append(sim_palavra(t, GT[p]))
        sc.append(sim_char(t, GT[p]))
    dt = (time.time() - t0) / len(AMOSTRA)
    mp, mc = sum(sp) / len(sp), sum(sc) / len(sc)
    res.append(dict(lang=lang, dpi=dpi, psm=psm, palavra=mp, caract=mc, seg=dt,
                    por_pagina=[round(x, 4) for x in sp]))
    print("%-5s %5d %4d | %10.2f%% | %10.2f%% | %7.1fs" % (lang, dpi, psm, mp * 100, mc * 100, dt))

melhor = max(res, key=lambda r: (r["palavra"], -r["seg"]))
print("\nESCOLHIDA: lang=%s dpi=%d psm=%d  (%.2f%% palavra, %.1fs/pag)" %
      (melhor["lang"], melhor["dpi"], melhor["psm"], melhor["palavra"] * 100, melhor["seg"]))
print("por pagina: %s" % melhor["por_pagina"])

# ---------------------------------------------------------- documento inteiro
lang, dpi, psm = melhor["lang"], melhor["dpi"], melhor["psm"]
print("\n" + "=" * 82)
print("EXPERIMENTO B - documento inteiro (%d paginas) na config escolhida" % N)
print("=" * 82)
t0 = time.time()
ocr_paginas = []
for i in range(N):
    ocr_paginas.append(ocr(render(PDF_DIGITAL, i, dpi), lang, psm))
dt_full = time.time() - t0
sp_full = [sim_palavra(ocr_paginas[i], GT[i]) for i in range(N)]
media = sum(sp_full) / N
pior = min(range(N), key=lambda i: sp_full[i])
print("similaridade de palavra, media das %d paginas: %.2f%%" % (N, media * 100))
print("melhor pagina: p.%02d (%.2f%%)   pior pagina: p.%02d (%.2f%%)" %
      (max(range(N), key=lambda i: sp_full[i]) + 1, max(sp_full) * 100, pior + 1, sp_full[pior] * 100))
print("paginas abaixo de 90%%: %s" % [i + 1 for i in range(N) if sp_full[i] < 0.90])
print("tempo total: %.1fs (%.2f s/pagina)" % (dt_full, dt_full / N))

TXT_OCR = "\n".join(ocr_paginas)
TXT_GT = "\n".join(GT)

# ---------------------------------------------------------- campos criticos
print("\n" + "=" * 82)
print("EXPERIMENTO C - os campos do questionario sobrevivem ao OCR?")
print("=" * 82)
ALVOS = [
    ("Q5  valor 1.900.000,00", r"1\.900\.000,00"),
    ("Q5  rotulo 'valor minimo'", r"valor\s+minimo"),
    ("Q3  modalidade 'concorrencia'", r"concorrencia"),
    ("Q4  criterio 'maior'", r"maior\s+(lance|oferta)"),
    ("Q9  '60' proximo de 'meses'", r"60\s*\(?\s*\w*\s*\)?\s*meses"),
    ("datas DD/MM/AAAA", r"\d{2}/\d{2}/\d{4}"),
    ("CNPJ 87.893.111/0001-52", r"87\.893\.111/0001-52"),
    ("percentuais", r"\d+(?:,\d+)?\s*%"),
    ("referencias a 'lei 14.133'", r"lei\s*(federal\s*)?n?o?\s*14\.133"),
]
print("%-32s | %9s | %6s | %s" % ("campo", "gabarito", "ocr", "veredito"))
print("-" * 82)
campos = []
for nome, pat in ALVOS:
    a = len(re.findall(pat, limpa(TXT_GT)))
    b = len(re.findall(pat, limpa(TXT_OCR)))
    vd = ("ausente no gabarito" if a == 0 else
          ("OK" if b >= a else "PERDA %d de %d" % (a - b, a)))
    campos.append(dict(campo=nome, gabarito=a, ocr=b, veredito=vd))
    print("%-32s | %9d | %6d | %s" % (nome, a, b, vd))

# ---------------------------------------------------------- scan real completo
print("\n" + "=" * 82)
print("EXPERIMENTO D - o PDF realmente digitalizado, 44 paginas, completo")
print("=" * 82)
doc = fitz.open(PDF_SCAN)
NS = len(doc)
doc.close()
t0 = time.time()
scan_paginas = []
for i in range(NS):
    scan_paginas.append(ocr(render(PDF_SCAN, i, dpi), lang, psm))
dt_scan = time.time() - t0
TXT_SCAN = "\n".join(scan_paginas)
chars = [len(t.strip()) for t in scan_paginas]
vazias = [i + 1 for i, c in enumerate(chars) if c < 120]
print("antes do OCR: 44 chars no documento inteiro")
print("depois do OCR: %s chars, media de %d por pagina" % (f"{len(TXT_SCAN.strip()):,}".replace(",", "."), sum(chars) // NS))
print("paginas ainda vazias apos OCR: %s" % (vazias if vazias else "nenhuma"))
print("tempo: %.1fs para %d paginas (%.2f s/pagina)" % (dt_scan, NS, dt_scan / NS))
print("\ncampos criticos recuperados do SCAN:")
for nome, pat in ALVOS:
    b = len(re.findall(pat, limpa(TXT_SCAN)))
    print("   %-32s -> %d ocorrencia(s)" % (nome, b))

io.open(os.path.join(OUT, "ocr_scan_44p.txt"), "w", encoding="utf-8").write(TXT_SCAN)
io.open(os.path.join(OUT, "ocr_digital_27p.txt"), "w", encoding="utf-8").write(TXT_OCR)
json.dump(dict(grid=res, escolhida=melhor, doc_inteiro=dict(
    paginas=N, media_palavra=media, por_pagina=[round(x, 4) for x in sp_full],
    seg_por_pagina=dt_full / N), campos=campos,
    scan=dict(paginas=NS, chars=len(TXT_SCAN.strip()), seg_por_pagina=dt_scan / NS,
              vazias=vazias)),
    io.open(os.path.join(OUT, "resultado_v2.json"), "w", encoding="utf-8"),
    ensure_ascii=False, indent=1)
print("\nsalvo em %s" % OUT)
