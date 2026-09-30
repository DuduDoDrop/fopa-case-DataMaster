# -*- coding: utf-8 -*-
import json, re, os, io, urllib.request, hashlib, unicodedata, subprocess, time, datetime

BASE = r"C:\Users\Nome\Projetos\projeto-fopa"
AM = os.path.join(BASE, "amostras")
UA = {"User-Agent": "FOPA-POC/0.1 (estudo de viabilidade)", "Accept": "*/*"}
HOJE = "2026-09-22"


def slug(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9 ._-]", "", s).strip()


def get(url, timeout=90):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


abertos = json.load(io.open(os.path.join(AM, "_editais_abertos.json"), encoding="utf-8"))
# exclui Sao Lourenco (ja no acervo) e fica com os de prazo mais folgado
alvos = [a for a in abertos if "LOURENCO" not in (a["item"].get("orgao_nome") or "").upper()]
print("candidatos abertos:", len(alvos))

resumo = []
for a in alvos:
    it = a["item"]
    m = re.match(r"/compras/(\d+)/(\d+)/(\d+)", it.get("item_url") or "")
    if not m:
        continue
    cnpj, ano, seq = m.groups()
    mun, uf = slug(it.get("municipio_nome")), it.get("uf")
    mod = slug(it.get("modalidade_licitacao_nome"))
    pasta = os.path.join(AM, "ABERTO %s - %s-%s" % (mod, mun, uf))
    try:
        docs = json.loads(get("https://pncp.gov.br/api/pncp/v1/orgaos/%s/compras/%s/%s/arquivos" % (cnpj, ano, seq)))
    except Exception as e:
        print("  !! lista falhou %s/%s: %s" % (mun, uf, e))
        continue
    os.makedirs(pasta, exist_ok=True)
    print("\n### %s/%s  (prazo ate %s)  %d arquivos" % (mun, uf, a["fim"], len(docs)))
    linhas = []
    for d in docs:
        sq, tipo, tit = d.get("sequencialDocumento"), d.get("tipoDocumentoNome"), slug(d.get("titulo"))[:55]
        tit = re.sub(r"\.pdf$", "", tit, flags=re.I)
        dest = os.path.join(pasta, "%02d - %s - %s.pdf" % (sq, slug(tipo), tit))
        try:
            data = get(d.get("url"))
        except Exception as e:
            print("   !! seq=%s: %s" % (sq, e))
            continue
        io.open(dest, "wb").write(data)
        txt = dest[:-4] + ".txt"
        subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", dest, txt], capture_output=True)
        nch = os.path.getsize(txt) if os.path.exists(txt) else 0
        pg = re.search(rb"/Type\s*/Pages.*?/Count\s+(\d+)", data, re.S)
        pg = int(pg.group(1)) if pg else 0
        ocr = nch < 200 or (pg > 0 and nch / pg < 120)
        linhas.append(dict(seq=sq, tipo=tipo, titulo=d.get("titulo"), pag=pg,
                           kb=len(data) // 1024, chars=nch, requer_ocr=ocr,
                           sha=hashlib.sha256(data).hexdigest()[:16],
                           arquivo=os.path.basename(dest)))
        print("   seq=%-3s %-32s %3dp %6dKB txt=%7d %s" %
              (sq, (tipo or "")[:32], pg, len(data) // 1024, nch, "OCR" if ocr else ""))
        time.sleep(0.3)
    reg = dict(modalidade=it.get("modalidade_licitacao_nome"), orgao=it.get("orgao_nome"),
               uf=uf, municipio=it.get("municipio_nome"),
               numero_controle=it.get("numero_controle_pncp"),
               fim_prazo=a["fim"], objeto=re.sub(r"\s+", " ", it.get("description") or "").strip(),
               data_publicacao=(it.get("data_publicacao_pncp") or "")[:10],
               link="https://pncp.gov.br/app/editais/%s/%s/%s" % (cnpj, ano, seq),
               extraido_em=HOJE, arquivos=linhas)
    json.dump(reg, io.open(os.path.join(pasta, "_inventario.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    resumo.append(reg)

json.dump(resumo, io.open(os.path.join(AM, "_abertos_resumo.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n=== RESUMO ===")
print("%-24s %-3s %-26s %-11s %5s %5s" % ("municipio", "uf", "modalidade", "prazo", "arqs", "ocr"))
for r in resumo:
    print("%-24s %-3s %-26s %-11s %5d %5d" % (r["municipio"][:24], r["uf"],
          (r["modalidade"] or "")[:26], r["fim_prazo"], len(r["arquivos"]),
          sum(1 for x in r["arquivos"] if x["requer_ocr"])))
