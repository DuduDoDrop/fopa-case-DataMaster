# -*- coding: utf-8 -*-
"""
Recuperação de páginas — a camada RAG do FOPA.

POR QUE BM25 E NÃO EMBEDDINGS
  O edital é um documento jurídico com vocabulário fechado e altamente específico:
  "cessão onerosa", "margem consignável", "valor mínimo", "prova de vida". A pergunta
  do questionário usa QUASE AS MESMAS PALAVRAS que a resposta no documento. Nesse
  regime, busca léxica é forte e busca semântica não acrescenta o suficiente para
  justificar seu custo: um índice vetorial exigiria serviço de embeddings (custo por
  token, latência, e o documento saindo da máquina) e um banco vetorial para operar.
  BM25 roda local, em milissegundos, sem dependência externa e sem dado saindo daqui.

  Isso é uma DECISÃO COM TRADE-OFF, não uma omissão. Ver ADR-010 no vault e o
  harness de avaliação (11_avaliar.py), que mede contexto-completo × RAG lado a lado.

QUANDO A RECUPERAÇÃO IMPORTA
  Um conjunto como Bertioga (9 arquivos, ~66k tokens) cabe inteiro no contexto de 1M.
  A recuperação passa a valer quando o conjunto cresce — anexos digitalizados após OCR
  chegam fácil a centenas de milhares de tokens — e quando se quer reduzir custo por
  extração. O modo é escolhido por política, não por gosto: ver `escolher_modo`.

Implementação: BM25 Okapi puro, sem dependência externa.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

# stopwords do português + ruído jurídico que aparece em toda página
STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "ou", "em", "no", "na",
    "nos", "nas", "um", "uma", "uns", "umas", "por", "para", "com", "sem", "sob", "sobre",
    "ao", "aos", "à", "às", "que", "se", "ser", "sera", "foi", "seu", "sua", "seus", "suas",
    "este", "esta", "esse", "essa", "aquele", "aquela", "isso", "isto", "pelo", "pela",
    "pelos", "pelas", "como", "mais", "mas", "ate", "apos", "entre", "quando", "onde",
    "qual", "quais", "deve", "devera", "podera", "pode", "nao", "sim", "art", "artigo",
    "inciso", "paragrafo", "alinea", "item", "anexo", "lei", "n", "no",
}

_RE_TOKEN = re.compile(r"[a-z0-9]+")


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return t.lower()


def tokenizar(texto: str) -> list[str]:
    return [t for t in _RE_TOKEN.findall(normalizar(texto))
            if len(t) > 2 and t not in STOPWORDS]


@dataclass
class Pagina:
    arquivo: str
    numero: int          # página FÍSICA, 1-based
    texto: str

    @property
    def marcador(self) -> str:
        return "=== ARQUIVO %s | PÁGINA %d ===" % (self.arquivo, self.numero)

    def __len__(self) -> int:
        return len(self.texto)


class IndiceBM25:
    """BM25 Okapi sobre páginas. k1 e b nos valores clássicos."""

    def __init__(self, paginas: list[Pagina], k1: float = 1.5, b: float = 0.75):
        self.paginas = paginas
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenizar(p.texto)) for p in paginas]
        self.tamanhos = [sum(d.values()) for d in self.docs]
        self.media = (sum(self.tamanhos) / len(self.tamanhos)) if self.tamanhos else 0.0
        n = len(self.docs)
        freq_doc: Counter = Counter()
        for d in self.docs:
            freq_doc.update(d.keys())
        # IDF com piso, para termo presente em quase todo documento não virar negativo
        self.idf = {t: max(0.05, math.log(1 + (n - f + 0.5) / (f + 0.5)))
                    for t, f in freq_doc.items()}

    def pontuar(self, consulta: str) -> list[tuple[int, float]]:
        termos = tokenizar(consulta)
        notas = []
        for i, doc in enumerate(self.docs):
            if not self.tamanhos[i]:
                notas.append((i, 0.0))
                continue
            norm = self.k1 * (1 - self.b + self.b * self.tamanhos[i] / (self.media or 1))
            s = 0.0
            for t in termos:
                f = doc.get(t, 0)
                if f:
                    s += self.idf.get(t, 0.0) * (f * (self.k1 + 1)) / (f + norm)
            notas.append((i, s))
        notas.sort(key=lambda x: -x[1])
        return notas

    def buscar(self, consulta: str, k: int = 6, minimo: float = 0.0) -> list[Pagina]:
        return [self.paginas[i] for i, s in self.pontuar(consulta)[:k] if s > minimo]


def consulta_da_pergunta(p) -> str:
    """Monta a consulta a partir do texto da pergunta mais seus termos-sinal."""
    return p.texto + " " + " ".join(p.termos)


def paginas_para_pergunta(indice: IndiceBM25, p, k: int = 6,
                          sempre: tuple[str, ...] = ()) -> list[Pagina]:
    """
    Páginas relevantes para uma pergunta.

    `sempre` força a inclusão de arquivos inteiros que nunca podem faltar — na prática,
    o aviso de retificação, que é curto e carrega a data vigente (RN-06). Sem isso o
    BM25 pode não trazê-lo, e a Q1 sai errada.
    """
    escolhidas = {(pg.arquivo, pg.numero): pg
                  for pg in indice.buscar(consulta_da_pergunta(p), k=k)}
    for pg in indice.paginas:
        if any(marca.lower() in pg.arquivo.lower() for marca in sempre):
            escolhidas[(pg.arquivo, pg.numero)] = pg
    return sorted(escolhidas.values(), key=lambda x: (x.arquivo, x.numero))


# --------------------------------------------------------------- política de modo
LIMITE_CONTEXTO_COMPLETO = 180_000   # caracteres (~50k tokens) — cabe folgado e custa pouco


def escolher_modo(paginas: list[Pagina], forcado: str | None = None) -> str:
    """
    'contexto-completo' quando o conjunto é pequeno; 'rag' quando cresce.

    A política é explícita de propósito: um modo escolhido por tamanho é auditável,
    um modo escolhido por intuição não é.
    """
    if forcado:
        return forcado
    total = sum(len(p) for p in paginas)
    return "contexto-completo" if total <= LIMITE_CONTEXTO_COMPLETO else "rag"


def montar_contexto(paginas: list[Pagina]) -> str:
    """Texto com os marcadores que o Extrator usa para citar arquivo e página (RN-08)."""
    return "\n\n".join("%s\n%s" % (p.marcador, p.texto) for p in paginas)


__all__ = ["Pagina", "IndiceBM25", "paginas_para_pergunta", "consulta_da_pergunta",
           "escolher_modo", "montar_contexto", "tokenizar", "normalizar",
           "LIMITE_CONTEXTO_COMPLETO"]
