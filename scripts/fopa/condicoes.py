# -*- coding: utf-8 -*-
"""
Condições de operação de uma execução — o que o sistema sabe sobre si mesmo.

O RELATÓRIO RESPONDE "O QUE O EDITAL DIZ". ISTO RESPONDE "SOB QUE CONDIÇÕES A LEITURA FOI FEITA".

POR QUE ISTO EXISTE
  Porque o campo `confianca` vem do MODELO dizendo o quanto confia em si — que é
  exatamente o tipo de auto-avaliação que este projeto rejeita em toda parte.
  Um modelo confiante e errado é indistinguível de um modelo confiante e certo.

  Aqui a incerteza é derivada de FATOS que o sistema observou sobre a própria
  execução: documento que o inventário prometia e não veio, anexo que precisou
  de OCR, provedor secundário no lugar do principal, corpus velho, pergunta
  sobre a qual se absteve.

  É a inversão da ADR-004 aplicada à incerteza. Lá: quem gera a resposta não
  pode ser quem a verifica. Aqui: quem gera a resposta não pode ser quem declara
  o quanto ela é confiável.

O QUE ISTO NÃO FAZ
  Não bloqueia entrega e não substitui `confianca`. Os dois convivem — e a
  DIVERGÊNCIA entre eles é informação: modelo confiante sob condição degradada
  é precisamente o caso que merece olho humano antes do lance.

CUSTO
  Zero. São fatos que o pipeline já tinha em mãos e jogava fora.
"""
from __future__ import annotations

import io
import json
import os
import time
from dataclasses import dataclass, field

# Uma condição é DEGRADADA quando aumenta a chance de leitura incompleta. A
# lista é curta de propósito: marcar tudo como degradado é o mesmo que não
# marcar nada.
DEGRADA = ("documentos_faltando", "ocr", "provedor_secundario",
           "corpus_velho", "texto_furtivo")

# TAGS — rotulos que acompanham a licitacao pelo resto do fluxo.
#
# Descrever nao basta. Um motivo escrito em prosa dentro do relatorio serve a
# quem esta lendo AQUELE relatorio; uma tag serve a quem precisa FILTRAR: achar
# todas as licitacoes suspeitas sem abrir uma por uma, no painel, na planilha e
# nos metadados.
#
# A tag e a mesma string em todo lugar, de proposito: busca textual tem que
# encontrar as tres ocorrencias.
TAG_INJECAO = "Prompt Injection - Conteúdo Suspeito"


@dataclass
class Condicoes:
    """O que se observou durante uma execução."""

    # documentos
    esperados: int = 0                 # o que o _inventario.json prometia
    obtidos: int = 0                   # o que de fato foi lido
    faltando: list[str] = field(default_factory=list)

    # leitura
    arquivos_ocr: list[str] = field(default_factory=list)
    paginas_ocr: int = 0

    # modelo
    provedor: str = ""
    modelo: str = ""
    effort: str = ""
    secundario: bool = False           # rodou no plano B

    # frescor
    corpus_horas: float | None = None  # idade da última coleta

    # ambiente hostil
    # Texto que o PDF diz a MAQUINA e nao mostra ao humano: branco sobre branco,
    # corpo de 1pt, transparente. Ver `furtivo.py`. Nao e hipotese academica --
    # o PNCP aceita upload de qualquer orgao, sem sanitizacao declarada.
    furtivos: list[str] = field(default_factory=list)

    # resultado
    abstencoes: list[str] = field(default_factory=list)

    # ------------------------------------------------------------- leitura
    @property
    def documentos_faltando(self) -> bool:
        return bool(self.faltando)

    @property
    def ocr(self) -> bool:
        return bool(self.arquivos_ocr)

    @property
    def provedor_secundario(self) -> bool:
        return self.secundario

    @property
    def texto_furtivo(self) -> bool:
        return bool(self.furtivos)

    @property
    def corpus_velho(self) -> bool:
        """48h é o limiar porque licitação abre e fecha em dias, não em horas."""
        return self.corpus_horas is not None and self.corpus_horas > 48

    @property
    def degradada(self) -> bool:
        return any(getattr(self, c) for c in DEGRADA)

    def motivos(self) -> list[str]:
        """Por que esta execução é degradada — em português, não em flags."""
        fora = []
        if self.documentos_faltando:
            fora.append("%d documento(s) do inventário não foram lidos: %s"
                        % (len(self.faltando), ", ".join(self.faltando[:3])))
        if self.ocr:
            fora.append("%d arquivo(s) exigiram OCR (%d páginas) — texto "
                        "reconhecido, não extraído"
                        % (len(self.arquivos_ocr), self.paginas_ocr))
        if self.provedor_secundario:
            fora.append("rodou no provedor secundário (%s), não no principal"
                        % self.modelo)
        if self.corpus_velho:
            fora.append("o corpus foi coletado há %.0f horas; pode haver "
                        "licitação nova não vista" % self.corpus_horas)
        if self.texto_furtivo:
            # Primeiro da lista quando aparece: os outros sao degradacao de
            # qualidade; este e tentativa de manipulacao, e muda o que se faz
            # com o documento, nao so a confianca na leitura.
            fora.insert(0, "ATENÇÃO: %d trecho(s) de texto FURTIVO — visível "
                           "para a máquina e não para quem lê o PDF: %s"
                        % (len(self.furtivos), "; ".join(self.furtivos[:2])))
        return fora

    def tags(self) -> list[str]:
        """
        Rótulos que a licitação carrega dali em diante.

        Hoje há uma só, e ela é a que muda o QUE SE FAZ com o documento: as
        demais condições degradam a confiança na leitura; texto furtivo é
        tentativa de manipulação e pede decisão humana antes do lance.
        """
        fora = []
        if self.texto_furtivo:
            fora.append(TAG_INJECAO)
        return fora

    def para_dict(self) -> dict:
        return {
            "tags": self.tags(),
            "degradada": self.degradada,
            "motivos": self.motivos(),
            "documentos": {"esperados": self.esperados, "obtidos": self.obtidos,
                           "faltando": self.faltando},
            "ocr": {"arquivos": self.arquivos_ocr, "paginas": self.paginas_ocr},
            "modelo": {"provedor": self.provedor, "modelo": self.modelo,
                       "effort": self.effort, "secundario": self.secundario},
            "texto_furtivo": self.furtivos,
            "corpus_horas": (round(self.corpus_horas, 1)
                             if self.corpus_horas is not None else None),
            "abstencoes": self.abstencoes,
        }

    def __str__(self) -> str:
        if not self.degradada and not self.abstencoes:
            return "condições normais: nada degradou esta execução"
        partes = self.motivos()
        if self.abstencoes:
            partes.append("abstenção em %d pergunta(s): %s"
                          % (len(self.abstencoes), ", ".join(self.abstencoes)))
        return " · ".join(partes)


# ------------------------------------------------------------------ coleta
def documentos_esperados(pasta: str) -> list[str]:
    """
    O que o `_inventario.json` prometia, se houver um.

    Sem inventário não há promessa a cobrar, e ausência de inventário NÃO é
    condição degradada: as seis licitações mais antigas da amostra vieram de
    uma coleta anterior à convenção.
    """
    f = os.path.join(pasta, "_inventario.json")
    if not os.path.isfile(f):
        return []
    try:
        d = json.load(io.open(f, encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return [a.get("arquivo") for a in (d.get("arquivos") or []) if a.get("arquivo")]


def nao_lidos(esperados: list[str], lidos: set[str] | list[str]) -> list[str]:
    """
    O que o inventário prometia e não foi lido — sem falso alarme de grafia.

    Duas formas de o MESMO documento parecer ausente, as duas vistas no acervo:

      · maiúsculas: o inventário grava "CAPA-LICITACAO.pdf" e o disco tem
        "Capa-Licitacao.pdf" — o mesmo arquivo para o Windows;
      · ZIP entregue como ".ZIP.pdf": o download extrai o conteúdo como
        "<nome do zip> -- <arquivo interno>.pdf", e é ESSE que se lê.

    Comparar por nome exato marcava a leitura como degradada nos dois casos, e
    um aviso que dispara sem motivo ensina o leitor a ignorá-lo.
    """
    baixos = {n.casefold() for n in lidos}

    def lido(nome: str) -> bool:
        b = nome.casefold()
        if b in baixos:
            return True
        if ".zip" in b:
            raiz = b[:b.index(".zip")] + " -- "
            return any(n.startswith(raiz) for n in baixos)
        return False

    return sorted(f for f in esperados if not lido(f))


def idade_do_corpus(raiz: str) -> float | None:
    """Horas desde a última coleta — None se nunca houve coleta."""
    f = os.path.join(raiz, "saidas", "_corpus_escopo.json")
    if not os.path.isfile(f):
        return None
    try:
        d = json.load(io.open(f, encoding="utf-8"))
        quando = d.get("coletado_em")
        if not quando:
            return None
        t = time.mktime(time.strptime(quando[:16], "%Y-%m-%d %H:%M"))
        return (time.time() - t) / 3600.0
    except (ValueError, OSError, OverflowError):
        return None


__all__ = ["Condicoes", "documentos_esperados", "nao_lidos", "idade_do_corpus",
           "DEGRADA", "TAG_INJECAO"]
