# -*- coding: utf-8 -*-
"""
OCR de editais — implementa a ADR-008 do vault.

Regras que este módulo faz cumprir (ver vault/01-Case/Regras de negócio.md):
  RN-19  gatilho: chars/páginas < 120 → roda OCR
  RN-20  dois perfis: texto corrido (150dpi psm3) e tabela (400dpi psm4)
  RN-21  pirâmide vinda de OCR nunca entra sozinha — sempre marcada
  RN-22  preferir sempre o documento digital quando existir
  RN-23  limpar a camada de assinatura digital antes de parsear tabela

Armadilha herdada de um projeto anterior e confirmada no ambiente de desenvolvimento:
  TESSDATA_PREFIX SUBSTITUI o tessdata do Tesseract, não soma. O tessdata
  padrão tem apenas eng e osd — sem português. Apontar errado faz o OCR
  falhar em SILÊNCIO, devolvendo página vazia.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

# ---------------------------------------------------------------- configuração
TESSERACT_EXE = os.environ.get(
    "FOPA_TESSERACT", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
# O TESSDATA MORA DENTRO DO PROJETO, e isto foi um conserto, não um capricho.
#
# O padrão anterior apontava para o tessdata de OUTRO projeto da máquina de
# desenvolvimento. Funcionava ali e falhava em qualquer outra: o
# `TESSDATA_PREFIX` SUBSTITUI o tessdata do Tesseract em vez de somar, então o
# projeto nunca usou o tessdata do instalador, e o instalador padrão não traz
# português.
#
# Ninguém tinha percebido porque o Docker define o caminho dele e instala
# `tesseract-ocr-por`: o caminho TESTADO estava certo e o caminho USADO no dia
# a dia estava emprestado. "Roda local" era verdade numa máquina só.
#
# `setup.ps1` baixa o `por.traineddata` (~2 MB) para cá. O arquivo fica fora do
# git — é binário, é baixável, e versioná-lo trocaria uma dívida por outra.
_RAIZ_PROJETO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
TESSDATA = os.environ.get(
    "FOPA_TESSDATA", os.path.join(_RAIZ_PROJETO, "tessdata"))

# RN-20 — os dois perfis, com os números medidos em 22/09/2026
PERFIL_TEXTO = dict(lang="por", dpi=150, psm=3, oem=3)   # 92,97% similaridade de palavra
PERFIL_TABELA = dict(lang="por", dpi=400, psm=4, oem=3)  # zero valores errados

LIMIAR_OCR = 120  # RN-19 — caracteres por página

# RN-23 — a tarja de assinatura digital entra no meio da tabela
RUIDO_ASSINATURA = re.compile(
    r"assinado por \d+ pessoas?:.*"
    r"|para verificar a autenticidade.*"
    r"|c[oó]digo para verifica[çc][ãa]o:.*"
    r"|este documento foi assinado digitalmente.*"
    r"|esta vers[ãa]o de verifica[çc][ãa]o foi gerada.*",
    re.I)

RE_MOEDA = re.compile(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b")


class OcrIndisponivel(RuntimeError):
    pass


def _configurar() -> None:
    """
    Aponta o pytesseract e o TESSDATA_PREFIX já no IMPORT do módulo.

    Antes isto vivia só dentro de checar_ambiente(), e quem chamasse ler_documento()
    direto quebrava com "tesseract is not installed". Configuração de ambiente não
    pode depender de alguém lembrar de validar antes.
    """
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
    if os.path.isdir(TESSDATA):
        os.environ["TESSDATA_PREFIX"] = TESSDATA


_configurar()


def checar_ambiente() -> dict:
    """Falha ALTO, nunca em silêncio. Rodar antes de qualquer pipeline que dependa de OCR."""
    if not os.path.exists(TESSERACT_EXE):
        raise OcrIndisponivel("tesseract não encontrado em %s" % TESSERACT_EXE)
    if not os.path.isdir(TESSDATA):
        raise OcrIndisponivel("tessdata não encontrado em %s" % TESSDATA)

    _configurar()

    versao = str(pytesseract.get_tesseract_version())
    idiomas = pytesseract.get_languages(config="")
    if "por" not in idiomas:
        raise OcrIndisponivel(
            "o tessdata em %s não tem 'por' (tem: %s). "
            "O OCR rodaria em inglês e perderia ~6,4 pontos de acurácia, sem avisar."
            % (TESSDATA, ", ".join(idiomas)))
    return {"tesseract": versao, "tessdata": TESSDATA, "idiomas": idiomas}


# ---------------------------------------------------------------- diagnóstico
@dataclass
class Diagnostico:
    arquivo: str
    paginas: int
    chars_nativos: int
    chars_por_pagina: float
    fontes_embutidas: int
    imagens: int
    requer_ocr: bool

    def __str__(self) -> str:
        return ("%-52s %3dp  %7d chars  %6.0f/pág  fontes=%d  imgs=%d  %s"
                % (os.path.basename(self.arquivo)[:52], self.paginas,
                   self.chars_nativos, self.chars_por_pagina,
                   self.fontes_embutidas, self.imagens,
                   "REQUER OCR" if self.requer_ocr else ""))


def diagnosticar(pdf: str) -> Diagnostico:
    """RN-19 — decide se o documento precisa de OCR, sem adivinhar."""
    doc = fitz.open(pdf)
    try:
        paginas = len(doc)
        chars = sum(len(doc[i].get_text().strip()) for i in range(paginas))
        fontes = sum(len(doc[i].get_fonts()) for i in range(paginas))
        imagens = sum(len(doc[i].get_images()) for i in range(paginas))
    finally:
        doc.close()
    por_pagina = chars / paginas if paginas else 0.0
    return Diagnostico(pdf, paginas, chars, por_pagina, fontes, imagens,
                       requer_ocr=(por_pagina < LIMIAR_OCR))


# ---------------------------------------------------------------- OCR
def _ocr_imagem(img: Image.Image, perfil: dict) -> str:
    cfg = "--psm %d --oem %d" % (perfil["psm"], perfil["oem"])
    return pytesseract.image_to_string(img, lang=perfil["lang"], config=cfg)


def _renderizar(doc, indice: int, dpi: int) -> Image.Image:
    pix = doc[indice].get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def limpar_assinatura(texto: str) -> str:
    """RN-23 — remove a tarja de assinatura antes de qualquer parsing de tabela."""
    return "\n".join(l for l in texto.splitlines() if not RUIDO_ASSINATURA.search(l))


def ler_pagina(pdf: str, indice: int, tabela: bool = False, forcar_ocr: bool = False) -> str:
    """
    Devolve o texto de uma página.

    RN-22: usa o texto nativo quando existe. Só cai para OCR quando precisa.
    """
    doc = fitz.open(pdf)
    try:
        nativo = doc[indice].get_text()
        if not forcar_ocr and len(nativo.strip()) >= LIMIAR_OCR:
            return nativo
        perfil = PERFIL_TABELA if tabela else PERFIL_TEXTO
        return _ocr_imagem(_renderizar(doc, indice, perfil["dpi"]), perfil)
    finally:
        doc.close()


def ler_documento(pdf: str, tabela: bool = False, forcar_ocr: bool = False,
                  progresso=None) -> list[str]:
    """Texto página a página. O índice da lista + 1 é a PÁGINA FÍSICA (RN-08)."""
    doc = fitz.open(pdf)
    try:
        perfil = PERFIL_TABELA if tabela else PERFIL_TEXTO
        paginas = []
        for i in range(len(doc)):
            nativo = doc[i].get_text()
            if not forcar_ocr and len(nativo.strip()) >= LIMIAR_OCR:
                paginas.append(nativo)
            else:
                paginas.append(_ocr_imagem(_renderizar(doc, i, perfil["dpi"]), perfil))
            if progresso:
                progresso(i + 1, len(doc), len(paginas[-1].strip()))
        return paginas
    finally:
        doc.close()


def marcar_paginas(paginas: list[str], arquivo: str) -> str:
    """Formato que o Extrator consome — o marcador carrega arquivo e página física."""
    nome = os.path.basename(arquivo)
    return "\n".join("=== ARQUIVO %s | PÁGINA %d ===\n%s" % (nome, i + 1, t)
                     for i, t in enumerate(paginas))


# ---------------------------------------------------------------- sanidade
@dataclass
class Alerta:
    regra: str
    pagina: int
    detalhe: str

    def __str__(self) -> str:
        return "⚠ [%s] p.%d — %s" % (self.regra, self.pagina, self.detalhe)


def _moeda(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def checar_faixas(paginas: list[str]) -> list[Alerta]:
    """
    RN-21 e a verificação nº 7 da ADR-008.

    Limites de faixa salarial são contínuos: o topo de uma faixa + 0,01 é a base
    da seguinte. `1.000,07` seguido de `2.000,00` quebra a regra — foi exatamente
    o erro que o perfil de 150dpi cometeu (leu 7 onde era 1).
    """
    alertas = []
    padrao = re.compile(
        r"de\s+R\$\s*([\d.]+,\d{2})\s+at[ée]\s+R\$\s*([\d.]+,\d{2})", re.I)
    for n, texto in enumerate(paginas, start=1):
        faixas = []
        for m in padrao.finditer(limpar_assinatura(texto)):
            try:
                faixas.append((_moeda(m.group(1)), _moeda(m.group(2)), m.group(0)))
            except ValueError:
                continue
        for i in range(1, len(faixas)):
            topo_anterior = faixas[i - 1][1]
            base_atual = faixas[i][0]
            if abs(base_atual - (topo_anterior + 0.01)) > 0.005:
                alertas.append(Alerta(
                    "RN-21", n,
                    "faixa descontínua: anterior termina em %.2f, esta começa em %.2f (%s)"
                    % (topo_anterior, base_atual, faixas[i][2])))
    return alertas


def checar_total_deslocado(paginas: list[str]) -> list[Alerta]:
    """
    RN-10 — um valor numa linha de faixa igual ao total da tabela é suspeita
    de total deslocado. Foi o que aconteceu com o `287` que caiu na linha
    "Acima de R$ 10.000,00" em São Lourenço do Sul.
    """
    alertas = []
    linha_faixa = re.compile(
        r"(?:de\s+R\$[\d.,\s]+at[ée]\s+R\$[\d.,\s]+|acima\s+de\s+R\$[\d.,\s]+)\s+(\d{1,5})\b", re.I)
    linha_total = re.compile(r"\btotal\b[^\d]{0,40}(\d{1,5})\b", re.I)
    for n, texto in enumerate(paginas, start=1):
        limpo = limpar_assinatura(texto)
        quantidades = [int(m.group(1)) for m in linha_faixa.finditer(limpo)]
        totais = [int(m.group(1)) for m in linha_total.finditer(limpo)]
        soma = sum(quantidades)
        for q in quantidades:
            if q and (q in totais or (soma and q == soma - q)):
                alertas.append(Alerta(
                    "RN-10", n,
                    "quantidade %d numa linha de faixa é igual a um total da tabela "
                    "— possível total deslocado" % q))
                break
    return alertas


def auditar(paginas: list[str], veio_de_ocr: bool) -> list[Alerta]:
    """Todas as checagens de sanidade de uma vez."""
    alertas = checar_faixas(paginas) + checar_total_deslocado(paginas)
    if veio_de_ocr and any("R$" in p for p in paginas):
        alertas.append(Alerta(
            "RN-21", 0,
            "pirâmide extraída por OCR — recall medido de 78,8%. "
            "NÃO entra na planilha sem revisão humana."))
    return alertas


__all__ = ["checar_ambiente", "diagnosticar", "ler_pagina", "ler_documento",
           "marcar_paginas", "limpar_assinatura", "auditar", "checar_faixas",
           "checar_total_deslocado", "Diagnostico", "Alerta", "OcrIndisponivel",
           "PERFIL_TEXTO", "PERFIL_TABELA", "LIMIAR_OCR"]
