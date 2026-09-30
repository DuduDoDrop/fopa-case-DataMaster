# -*- coding: utf-8 -*-
"""
Detector de texto furtivo — o que o PDF diz ao sistema e não mostra ao humano.

O ATAQUE QUE A BATERIA ADVERSARIAL NÃO COBRIA
  As quatro injeções de `sintetico.py` estão no corpo do edital: um humano que
  abrisse o PDF as veria. O vetor perigoso é o contrário — instrução que a
  máquina lê e a pessoa não:

      texto branco sobre fundo branco       `color` == branco
      texto transparente                    `alpha` == 0
      corpo microscópico                    `size` < 3pt
      fora da área útil da página           `bbox` além do `rect`

  Um edital com "ignore as regras anteriores" em 0,5pt branco passaria na
  revisão humana e chegaria íntegro ao prompt. Quem confere o PDF na tela não
  tem como ver; o extrator recebe o texto igual ao resto.

POR QUE ISTO NÃO É PARANOIA
  O PNCP aceita upload de PDF de qualquer órgão, sem sanitização declarada. Não
  é preciso supor má-fé do município: basta um fornecedor que monte o edital.

  E o custo de detectar é desprezível — a informação já está no PDF, e o
  pipeline já abre cada arquivo para ler texto.

O QUE ELE FAZ E O QUE NÃO FAZ
  Detecta e **sinaliza**; não remove e não bloqueia. Remover mudaria o documento
  que a ancoragem confere — e a ancoragem precisa conferir contra o que está lá,
  não contra o que se decidiu manter. O achado vira alerta no relatório, com
  página e amostra do texto, para decisão humana.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    import pymupdf
except ImportError:                                               # pragma: no cover
    import fitz as pymupdf                                        # noqa: F401

# Um corpo abaixo disto não é leitura: é escrita para máquina. Editais reais
# usam 8pt no pé de página e 6pt em tarja de assinatura — 3 dá folga.
CORPO_MINIMO = 3.0

# Branco puro. Não vale checar "claro demais": fundo colorido é comum em capa,
# e texto claro sobre fundo escuro é legítimo.
BRANCO = 16777215

# Margem de tolerância para o bbox: um glifo que encosta na borda por
# arredondamento não é ataque.
FOLGA_BORDA = 2.0


@dataclass
class Furtivo:
    arquivo: str
    pagina: int
    motivo: str
    amostra: str
    tamanho: float = 0.0

    def __str__(self) -> str:
        return ("%s p.%d — %s: %r"
                % (self.arquivo, self.pagina, self.motivo, self.amostra[:70]))


@dataclass
class Varredura:
    arquivo: str
    paginas: int = 0
    achados: list[Furtivo] = field(default_factory=list)
    erro: str = ""

    @property
    def limpo(self) -> bool:
        return not self.achados and not self.erro


def _motivo(span: dict, rect) -> str | None:
    """Por que este trecho é furtivo — ou None se não for."""
    texto = (span.get("text") or "").strip()
    if len(texto) < 12:
        # Trecho curto não carrega instrução, e marcá-lo encheria o relatório de
        # ruído: numeração de página em 2pt existe em edital de verdade.
        return None

    if (span.get("alpha") if span.get("alpha") is not None else 255) == 0:
        return "texto transparente (alpha 0)"
    if span.get("color") == BRANCO:
        return "texto branco"
    tam = span.get("size") or 0
    if 0 < tam < CORPO_MINIMO:
        return "corpo de %.1fpt — abaixo do legível" % tam

    bb = span.get("bbox")
    if bb and rect is not None:
        x0, y0, x1, y1 = bb
        if (x1 < rect.x0 - FOLGA_BORDA or x0 > rect.x1 + FOLGA_BORDA
                or y1 < rect.y0 - FOLGA_BORDA or y0 > rect.y1 + FOLGA_BORDA):
            return "fora da área visível da página"
    return None


def varrer(caminho: str) -> Varredura:
    """Procura texto furtivo num PDF. Não altera o arquivo."""
    nome = os.path.basename(caminho)
    v = Varredura(arquivo=nome)
    try:
        doc = pymupdf.open(caminho)
    except Exception as e:                                        # noqa: BLE001
        v.erro = str(e)[:160]
        return v

    try:
        v.paginas = doc.page_count
        for n, pagina in enumerate(doc, start=1):
            try:
                blocos = pagina.get_text("dict").get("blocks", [])
            except Exception:                                     # noqa: BLE001
                continue
            rect = pagina.rect
            for b in blocos:
                for linha in b.get("lines", []) or []:
                    for span in linha.get("spans", []) or []:
                        motivo = _motivo(span, rect)
                        if motivo:
                            v.achados.append(Furtivo(
                                arquivo=nome, pagina=n, motivo=motivo,
                                amostra=(span.get("text") or "").strip(),
                                tamanho=span.get("size") or 0.0))
    finally:
        doc.close()
    return v


def varrer_pasta(pasta: str) -> list[Varredura]:
    """Varre todos os PDFs de uma licitação."""
    saida = []
    for nome in sorted(os.listdir(pasta)):
        if nome.lower().endswith(".pdf"):
            saida.append(varrer(os.path.join(pasta, nome)))
    return saida


def resumo(varreduras: list[Varredura]) -> str:
    total = sum(len(v.achados) for v in varreduras)
    if not total:
        return "nenhum texto furtivo em %d arquivo(s)" % len(varreduras)
    arquivos = sum(1 for v in varreduras if v.achados)
    return ("%d trecho(s) furtivo(s) em %d de %d arquivo(s)"
            % (total, arquivos, len(varreduras)))


__all__ = ["varrer", "varrer_pasta", "resumo", "Furtivo", "Varredura",
           "CORPO_MINIMO"]
