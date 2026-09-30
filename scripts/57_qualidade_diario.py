# -*- coding: utf-8 -*-
"""
O texto do diario oficial presta, ou vai precisar de OCR?

    python 57_qualidade_diario.py [--n 12]

NAO CHAMA MODELO. Baixa amostra de diarios do Querido Diario e mede a
densidade de texto extraivel, com o MESMO criterio que o pipeline usa nos
editais do PNCP (RN-19: caracteres por pagina abaixo de 120 -> precisa OCR).

POR QUE IMPORTA
  A fase 2 do roadmap depende de ler diario oficial municipal. Se o diario for
  PDF digitalizado, entra a mesma cadeia de OCR que ja custa 6,4 pontos de
  acuracia nos editais -- e o OCR, medido em 23/09, chega a inventar digito a
  partir de fio de tabela.

O QUE A API OFERECE, E QUE MUDA A PERGUNTA
  Cada diario vem com `url` (o PDF) e `txt_url` (o texto JA EXTRAIDO por eles).
  Se o txt presta, a fase 2 nao paga OCR nenhum: o trabalho ja foi feito na
  origem, uma vez, para todo mundo.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

API = "https://queridodiario.ok.org.br/api/gazettes"
DESTINO = os.path.join(RAIZ, "saidas", "_qualidade_diario.json")
UA = "FOPA/0.1 (estudo de viabilidade; monitoramento de licitacoes de folha)"

# RN-19 do projeto: e o mesmo limiar que decide OCR nos editais do PNCP.
# Usar outro aqui tornaria os dois numeros incomparaveis.
LIMIAR_POR_PAGINA = 120


def _abrir(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
    return gzip.decompress(b) if b[:2] == bytes((0x1F, 0x8B)) else b


def _json(url: str) -> dict:
    return json.loads(_abrir(url).decode("utf-8"))


def _ocr_no_acervo():
    """
    Quantos arquivos do acervo do PNCP precisam de OCR, AGORA.

    O numero estava escrito a mao aqui ("13,5%"), e envelheceu no mesmo dia:
    o acervo dobrou e virou 15,0%. Comparacao com constante congelada nao e
    comparacao -- e duas medicoes de epocas diferentes lado a lado.
    """
    amostras = os.path.join(RAIZ, "amostras")
    if not os.path.isdir(amostras):
        return None
    total = com_ocr = 0
    for pasta in os.listdir(amostras):
        f = os.path.join(amostras, pasta, "_inventario.json")
        if not os.path.isfile(f):
            continue
        try:
            inv = json.load(io.open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for arq in inv.get("arquivos") or []:
            if "requer_ocr" not in arq:
                continue
            total += 1
            com_ocr += 1 if arq["requer_ocr"] else 0
    if not total:
        return None
    return (100.0 * com_ocr / total, com_ocr, total)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--pausa", type=float, default=1.5)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    q = urllib.parse.urlencode({"querystring": "folha de pagamento",
                                "size": a.n})
    try:
        d = _json(API + "?" + q)
    except urllib.error.HTTPError as e:
        # Distinguir 5xx (problema DELES) de 4xx (problema da consulta DAQUI)
        # importa: com 503 nao ha o que corrigir aqui, so voltar depois.
        corpo = e.read()[:120].decode("utf-8", "replace").strip()
        print("Querido Diário respondeu HTTP %d — %s" % (e.code, corpo))
        print("  5xx = fora do ar do lado deles; 4xx = a consulta está errada.")
        return 1
    except Exception as e:                                        # noqa: BLE001
        print("Querido Diário inalcançável (%s)" % type(e).__name__)
        return 1

    diarios = d.get("gazettes") or []
    print("=" * 92)
    print("  QUALIDADE DO TEXTO DO DIÁRIO OFICIAL — amostra de %d" % len(diarios))
    print("  (limiar RN-19: menos de %d caracteres por página → precisa OCR)"
          % LIMIAR_POR_PAGINA)
    print("=" * 92)
    print()

    linhas = []
    com_txt = sem_txt = 0
    for g in diarios:
        nome = "%s/%s" % (g.get("territory_name", "?"), g.get("state_code", "?"))
        txt_url = g.get("txt_url")
        if not txt_url:
            sem_txt += 1
            print("  %-34s sem txt_url — só o PDF" % nome[:34])
            continue
        com_txt += 1
        try:
            bruto = _abrir(txt_url)
        except Exception as e:                                    # noqa: BLE001
            print("  %-34s txt não baixou (%s)" % (nome[:34], type(e).__name__))
            continue
        texto = bruto.decode("utf-8", errors="replace")
        # CONTAR PAGINA DE VERDADE, NO PDF.
        #
        # A primeira versao usava `len(texto) / 2500` quando o txt nao tinha
        # quebra-pagina -- e NENHUM dos doze tinha. Entao a divisao devolvia
        # 2.500 caracteres por pagina em todos, por construcao: o divisor era
        # o proprio resultado. Aritmetica circular que parece medicao, o mesmo
        # defeito que o 55_por_servidor.py teve hoje com o R$ 1,00 simbolico.
        #
        # Agora o PDF e baixado e as paginas contadas nele. Custa uma
        # requisicao a mais, e e a diferenca entre medir e inventar.
        paginas = texto.count(chr(12))  # form feed
        origem_pag = "quebra-pagina no txt"
        if not paginas:
            try:
                import fitz
                pdf = _abrir(g.get("url") or "", timeout=90)
                doc = fitz.open(stream=pdf, filetype="pdf")
                paginas = doc.page_count
                doc.close()
                origem_pag = "contadas no PDF"
            except Exception as e:                                # noqa: BLE001
                print("  %-34s paginas nao contaveis (%s) — fora da conta"
                      % (nome[:34], type(e).__name__))
                continue
        por_pag = len(texto) / max(1, paginas)
        precisa = por_pag < LIMIAR_POR_PAGINA
        linhas.append({"municipio": nome, "caracteres": len(texto),
                       "paginas": paginas, "origem_paginas": origem_pag,
                       "por_pagina": round(por_pag), "precisa_ocr": precisa,
                       "data": g.get("date"), "txt_url": txt_url})
        print("  %-34s %8d car · %4d pág · %5d car/pág  %-12s %s"
              % (nome[:34], len(texto), paginas, round(por_pag),
                 "PRECISA OCR" if precisa else "texto ok", origem_pag))
        time.sleep(a.pausa)

    print()
    if not linhas:
        print("  nenhum diário com texto utilizável na amostra")
        return 1
    precisam = sum(1 for x in linhas if x["precisa_ocr"])
    med = sorted(x["por_pagina"] for x in linhas)[len(linhas) // 2]
    print("  com `txt_url` ............ %d de %d" % (com_txt, len(diarios)))
    print("  texto direto utilizável .. %d de %d (%.0f%%)"
          % (len(linhas) - precisam, len(linhas),
             100.0 * (len(linhas) - precisam) / len(linhas)))
    print("  precisariam de OCR ....... %d" % precisam)
    print("  mediana .................. %d caracteres por página" % med)
    print()
    # A AMOSTRA E ENVIESADA, E ISSO PRECISA APARECER.
    # A busca do Querido Diario devolve varios diarios do MESMO municipio --
    # na medicao de 23/09, 8 dos 12 eram Correntina/BA, alguns com contagem de
    # caracteres separada por 18 unidades (edicao e re-publicacao do mesmo
    # dia). Chamar isso de "amostra de 12" sugere uma variedade que nao existe.
    municipios = sorted({x["municipio"] for x in linhas})
    print("  municípios distintos ..... %d (em %d diários)"
          % (len(municipios), len(linhas)))
    if len(municipios) < len(linhas) / 2:
        print("     AMOSTRA CONCENTRADA: %s" % ", ".join(municipios))
        print("     A busca devolve várias edições do mesmo município. O")
        print("     resultado vale para estes %d, não para o país."
              % len(municipios))
    print()

    print("  COMPARAÇÃO com os editais do PNCP, mesmo critério:")
    pncp_ocr = _ocr_no_acervo()
    if pncp_ocr is None:
        print("     editais que precisam de OCR ..... acervo não medido")
        print("     (rode `41_censo_pdf.py` para preencher o inventário)")
    else:
        print("     editais que precisam de OCR ..... %.1f%% dos arquivos"
              " (%d de %d, medido agora)" % pncp_ocr)
    print("     diários desta amostra ........... %.0f%%"
          % (100.0 * precisam / len(linhas)))

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps(
        {"medido_em": time.strftime("%Y-%m-%d"), "amostra": len(diarios),
         "com_txt": com_txt, "sem_txt": sem_txt,
         "precisam_ocr": precisam, "mediana_por_pagina": med,
         "diarios": linhas}, ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_qualidade_diario.json · custo R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
