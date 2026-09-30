# -*- coding: utf-8 -*-
"""
O nome de pasta de uma licitação, num lugar só.

POR QUE ISTO É UM MÓDULO E NÃO UMA FUNÇÃO SOLTA EM CADA COLETOR
  Dois programas escrevem em `amostras/`: o `28_baixar_licitacao.py`, que baixa
  um lote a partir do corpus, e o `20_monitor.py`, que roda sozinho todo dia e
  baixa o que apareceu.

  Até 23/09/2026 cada um montava o nome do seu jeito. Para a mesma licitação de
  São Lourenço do Sul/RS o coletor produzia

      Concorrência - Eletrônica - Sao Lourenco Do Sul-RS

  e o monitor, a partir do texto cru do PNCP, produzia

      CONCORRENCIA ELETRONICA - MUNICIPIO DE SAO LOURENCO DO SULRS

  — o `/` de `SUL/RS` some na sanitização e cola as duas partes. Duas pastas,
  uma licitação, e o de-dup de cada um cego para o outro.

  É a [[ADR-013]] por outra porta: nome de pasta é ENDEREÇO, e dois programas
  que geram endereços diferentes para a mesma identidade produzem duplicata
  silenciosa. A defesa não é "sanitizar igual"; é **não ter duas funções**.

  O `numero_controle_pncp` continua sendo a identidade. Isto aqui só garante
  que o endereço também seja único e previsível.
"""
from __future__ import annotations

import re
import unicodedata

# "MUNICIPIO DE", "PREFEITURA MUNICIPAL DE" e afins não distinguem nada: toda
# licitação municipal começa assim. O que distingue é o que vem depois.
# "MUNICIPIO DE", "PREFEITURA MUNICIPAL DE", "INSTITUTO DE PREVIDENCIA DE" e
# afins não distinguem nada: quase toda licitação municipal começa assim. O que
# distingue é o que vem depois.
#
# ESTA REGEX VEIO DO `28_baixar_licitacao.py`, COPIADA, NÃO REESCRITA.
# Na primeira tentativa, uma equivalente foi escrita de memória e deixou de
# remover `Instituto de`, `Câmara de Vereadores do` e `Município do` — cinco
# das 165 pastas passaram a calcular um nome diferente do que está em disco.
# Um módulo que unifica duas implementações e inventa uma terceira não unifica
# nada; cria mais uma.
RE_PREFIXO = re.compile(
    r"^(?:munic[íi]pio|prefeitura(?:\s+municipal)?|c[âa]mara(?:\s+municipal)?|"
    r"fundo|instituto|autarquia)\s+(?:municipal\s+)?d[eo]\s+", re.I)

# O Windows recusa estes caracteres em nome de arquivo ou pasta.
RE_PROIBIDOS = re.compile(r'[<>:"/\\|?*]')
RE_CONTROLE = re.compile(r"[\x00-\x1f]")


def limpar(texto: str) -> str:
    """
    Texto do PNCP virando pedaço de nome de pasta seguro no Windows.

    NÃO TIRA ACENTO, e isso é decisão, não esquecimento.

    As 170 pastas já em disco se chamam `Pregão - Eletrônico - Bertioga-SP`,
    com acento — foi assim que o coletor as criou. Normalizar aqui produziria
    `Pregao - Eletronico - Bertioga-SP` para a MESMA licitação, que é
    exatamente a divergência de endereço que este módulo existe para eliminar.

    Acento é assunto de `chave()`, a função de COMPARAÇÃO. Endereço preserva o
    texto; comparação normaliza. Misturar os dois papéis numa função só foi o
    que produziu o bug original do de-dup.
    """
    t = RE_PROIBIDOS.sub(" ", texto or "")   # ESPAÇO, não vazio: "SUL/RS" -> "SUL RS"
    t = RE_CONTROLE.sub("", t)
    t = re.sub(r"\s+", " ", t).strip(" .")   # o Windows também recusa ponto final
    return t or "sem-nome"


def nome_pasta(*, orgao: str = "", modalidade: str = "", uf: str = "") -> str:
    """
    `<modalidade> - <município>-<UF>` — a forma que 170 pastas já usam.

    Recebe por palavra-chave de propósito: os dois chamadores leem os campos de
    fontes diferentes (`orgao`/`orgao_nome`, `modalidade`/`modalidade_licitacao_nome`)
    e trocar a ordem dos posicionais seria um erro mudo.
    """
    orgao = (orgao or "").strip()
    municipio = RE_PREFIXO.sub("", orgao).title() or orgao.title()
    modalidade = (modalidade or "Licitacao").strip()
    return limpar("%s - %s-%s" % (modalidade, municipio, (uf or "").strip()))


def chave(nome: str) -> str:
    """
    Chave de comparação de pasta: sem acento, sem caixa, sem o prefixo antigo.

    A comparação ingênua listou Pirapó, Adrianópolis e mais três como se não
    tivessem sido baixadas — porque o corpus escreve "Concorrência - Eletrônica"
    e a pasta no disco se chama "Concorrencia - Eletronica". O de-dup falhava
    para TODA licitação cuja modalidade tem acento, que são quase todas.
    """
    n = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    n = n.lower().strip()
    return n[7:] if n.startswith("aberto ") else n
