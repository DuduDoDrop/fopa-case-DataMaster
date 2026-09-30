# -*- coding: utf-8 -*-
"""
Lê a distribuição de servidores que a Q13 devolve em prosa e a estrutura.

O extrator responde a Q13 em texto corrido porque é assim que o edital escreve.
Isso é correto para a resposta e ruim para o leitor: a distribuição — que é o
insumo mais importante para precificar a folha — fica enterrada numa frase de
quinze linhas, e quem confere precisa somar de cabeça.

Este módulo não pergunta nada ao modelo. Reconhece, por padrão de texto, as duas
formas em que a distribuição aparece:

    faixa salarial   "Até R$ 2.000,00: 32"                <- o que se pede
    vínculo          "Servidores Efetivos: 201 (R$ ...)"  <- o que às vezes vem

A diferença não é cosmética. Sem faixa salarial não dá para estimar ticket médio,
potencial de consignado nem concentração da folha — um edital pode trazer 504
servidores perfeitamente contados sem dizer **quanto cada um ganha**.

E UMA SOMA SÓ É PUBLICADA QUANDO É UMA SOMA
São Lourenço do Sul tem três tabelas, e a resposta diz, com todas as letras, que
uma aparece "apenas parcialmente" e outra "não está disponível". As 17 linhas
legíveis somam 676 — um número que não é o total de nada. Apresentá-lo como
total seria repetir, no visualizador, o erro que a RN-09 cometeu no verificador:
tratar leitura parcial como leitura completa. Por isso a parcialidade é detectada
e carregada junto, e quem exibe decide como rotular a soma.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# "R$ 2.000,01 a R$ 3.000,00: 93" · "Até R$ 2.000,00 - 32" · "Acima de R$ 10.000,01: 3"
RE_FAIXA = re.compile(
    r"(?P<rotulo>"
    r"(?:de\s+|at[ée]\s+|acima\s+de\s+|mais\s+de\s+|a\s+partir\s+de\s+)?R?\$?\s*[\d.]+,\d{2}"
    r"(?:\s*(?:a|at[ée]|-|–|>)\s*R?\$?\s*[\d.]+,\d{2})?"
    r")\s*[:\-–]\s*(?P<qtd>\d{1,6})\b",
    re.I)

# "I – Servidores Efetivos: 201 (folha bruta mensal R$ 527.400,00)"
RE_VINCULO = re.compile(
    r"(?:^|[;.]\s*|\d\s*[–-]\s*|[IVX]{1,4}\s*[–-]\s*)"
    r"(?P<rotulo>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ /,()'’-]{3,70}?)"
    r"\s*[:]\s*(?P<qtd>\d{1,6})\b"
    r"(?:[^)\d]{0,40}R\$\s*(?P<valor>[\d.]+,\d{2}))?")

RE_TOTAL = re.compile(
    r"total(?:\s+geral|\s+impresso)?\s*[:\-–(]?\s*(?P<qtd>\d{1,3}(?:\.\d{3})*|\d{1,6})", re.I)

# Abre um grupo: 'Tabela "Contratos"', 'Tabela 1 — Prefeitura Municipal'.
# O número da tabela é descartado em favor do nome que vem depois do travessão:
# "Tabela 1" não diz nada a quem lê, "Prefeitura Municipal" diz tudo.
RE_GRUPO = re.compile(
    r"Tabela\s*(?:\d{1,2}|[IVX]{1,4})?\s*(?:[—–-]\s*)?[\"“]?(?P<nome>[^\"”;.:()]{2,60})",
    re.I)

# A palavra "Tabela" também aparece no meio de frase ("a tabela de faixas
# salariais repete..."). O que vem depois dela então é prosa, não um rótulo.
INICIO_PROSA = ("de ", "do ", "da ", "dos ", "das ", "que ", "com ", "em ",
                "no ", "na ", "e ", "é ", "nao ", "não ", "unica", "única",
                "aparece", "consta", "traz", "vem ", "acima", "abaixo")

# A própria resposta avisando que não leu tudo. Reconhecer isso é o ponto.
RE_PARCIAL = re.compile(
    r"parcialmente|n[ãa]o\s+constam|n[ãa]o\s+est[áa]\s+dispon[íi]vel|"
    r"n[ãa]o\s+consta\b|truncad|incomplet|apenas\s+parte|"
    r"demais\s+faixas.{0,30}n[ãa]o", re.I)

# Rótulos que casam com o padrão sem serem linha de distribuição.
RUIDO = ("total", "soma", "pagina", "página", "item", "clausula", "cláusula",
         "anexo", "artigo", "inciso", "lei", "decreto", "processo", "edital",
         "pregao", "pregão", "telefone", "cnpj", "conta", "agencia", "agência",
         "tabela", "populacao", "população")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def _num(s: str) -> float | None:
    try:
        return float(s.replace(".", "").replace(",", "."))
    except (AttributeError, ValueError):
        return None


def _limpar(rotulo: str) -> str:
    r = (rotulo or "").strip(" -–—:;,.")
    return re.sub(r"^(?:[IVX]{1,4}|\d{1,2})\s*[–-]\s*", "", r).strip()


@dataclass
class Linha:
    rotulo: str
    quantidade: int
    valor: float | None = None


@dataclass
class Grupo:
    nome: str
    linhas: list[Linha] = field(default_factory=list)
    total_declarado: int | None = None

    @property
    def soma(self) -> int:
        return sum(l.quantidade for l in self.linhas)

    @property
    def confere(self) -> bool | None:
        if self.total_declarado is None or not self.linhas:
            return None
        return self.soma == self.total_declarado


@dataclass
class Distribuicao:
    tipo: str = "ausente"            # "faixa salarial" | "vínculo" | "ausente"
    grupos: list[Grupo] = field(default_factory=list)
    parcial: bool = False            # a própria resposta declara que falta dado

    @property
    def linhas(self) -> list[Linha]:
        return [l for g in self.grupos for l in g.linhas]

    @property
    def soma(self) -> int:
        return sum(g.soma for g in self.grupos)

    @property
    def total_declarado(self) -> int | None:
        if len(self.grupos) == 1:
            return self.grupos[0].total_declarado
        return None

    @property
    def confere(self) -> bool | None:
        """None quando não há com o que comparar, ou quando a leitura é parcial.

        Numa leitura parcial a soma não representa população nenhuma, então
        "confere" não tem resposta — nem sim, nem não.
        """
        if self.parcial or self.total_declarado is None or not self.linhas:
            return None
        return self.soma == self.total_declarado

    @property
    def por_faixa(self) -> bool:
        return self.tipo == "faixa salarial"

    @property
    def completa(self) -> bool:
        """Todo grupo fecha com o próprio total impresso.

        Vale mais que o sinal de texto: em Fruta de Leite a resposta avisa que a
        pirâmide salarial não existe — e avisa certo —, mas a tabela por vínculo
        que ela traz fecha 504 contra 504. O dado exibido está completo; o que
        falta é outra coisa, e é o `tipo` que diz isso.
        """
        return bool(self.grupos) and all(g.confere is True for g in self.grupos)

    @property
    def rotulo_soma(self) -> str:
        """Como a soma deve ser chamada. Parcial não é total."""
        if self.completa:
            return "total, conferido linha a linha"
        if self.parcial:
            return "soma das linhas legíveis — leitura incompleta"
        return "soma das linhas"


def _nome_valido(nome: str) -> bool:
    n = _norm(nome)
    return bool(n) and not n.startswith(INICIO_PROSA)


def _fatiar(texto: str) -> list[tuple[str, str]]:
    """Divide em (nome do grupo, trecho). Sem marcador, um grupo só."""
    marcas = [m for m in RE_GRUPO.finditer(texto)
              if _nome_valido(m.group("nome"))]
    if not marcas:
        return [("", texto)]
    fatias = []
    if marcas[0].start() > 0:
        cabeca = texto[:marcas[0].start()]
        if RE_FAIXA.search(cabeca) or RE_VINCULO.search(cabeca):
            fatias.append(("", cabeca))
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        fatias.append((_limpar(m.group("nome")), texto[m.start():fim]))
    return fatias


def _faixas(trecho: str) -> list[Linha]:
    return [Linha(_limpar(m.group("rotulo")), int(m.group("qtd")))
            for m in RE_FAIXA.finditer(trecho)]


def _vinculos(trecho: str) -> list[Linha]:
    saida = []
    for m in RE_VINCULO.finditer(trecho):
        rot = _limpar(m.group("rotulo"))
        if not rot or any(r in _norm(rot) for r in RUIDO):
            continue
        saida.append(Linha(rot, int(m.group("qtd")), _num(m.group("valor"))))
    return saida


def ler(texto: str) -> Distribuicao:
    """Reconhece a distribuição no texto da resposta. Nunca chama modelo."""
    d = Distribuicao()
    if not texto:
        return d
    d.parcial = bool(RE_PARCIAL.search(texto))

    fatias = _fatiar(texto)

    # Duas linhas é o mínimo para chamar de distribuição; uma é menção solta.
    grupos_faixa = []
    for nome, trecho in fatias:
        linhas = _faixas(trecho)
        if len(linhas) >= 2:
            g = Grupo(nome, linhas)
            m = RE_TOTAL.search(trecho)
            if m:
                try:
                    g.total_declarado = int(m.group("qtd").replace(".", ""))
                except ValueError:
                    pass
            grupos_faixa.append(g)

    if grupos_faixa:
        d.tipo, d.grupos = "faixa salarial", grupos_faixa
        return d

    grupos_vinc = []
    for nome, trecho in fatias:
        linhas = _vinculos(trecho)
        if len(linhas) >= 2:
            g = Grupo(nome, linhas)
            m = RE_TOTAL.search(trecho)
            if m:
                try:
                    g.total_declarado = int(m.group("qtd").replace(".", ""))
                except ValueError:
                    pass
            grupos_vinc.append(g)

    if grupos_vinc:
        d.tipo, d.grupos = "vínculo", grupos_vinc
    return d
