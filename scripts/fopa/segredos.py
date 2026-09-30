# -*- coding: utf-8 -*-
"""
Carga de segredos a partir de `projeto-fopa/.env`.

POR QUE ESTE MÓDULO EXISTE, E POR QUE ELE É TÃO CURTO
  Porque a alternativa era pior. Sem ele, cada script precisaria de uma variável
  de ambiente exportada à mão antes de rodar — e a primeira vez que alguém
  esquece, o erro não é "faltou a chave": é uma chamada que falha no meio de um
  lote de 11 licitações, depois de já ter gasto as dez primeiras.

  `python-dotenv` não é usado. São trinta linhas contra uma dependência a mais no
  `requirements.txt`, e este arquivo faz exatamente o que é preciso: lê pares
  `CHAVE=valor`, ignora comentário e linha vazia, e NÃO sobrescreve variável que
  já veio do ambiente — quem exporta na sessão manda mais que o arquivo.

REGRA DE SEGURANÇA
  O `.env` está no `.gitignore` desde a primeira versão (`.env`, `.env.*`,
  `*.key`). Nenhuma chave entra no repositório, e nenhuma função aqui imprime
  valor de segredo: `mascarar()` existe justamente para que log e mensagem de
  erro possam citar a chave sem vazá-la.
"""
from __future__ import annotations

import io
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))          # projeto-fopa/
CAMINHO_ENV = os.path.join(RAIZ, ".env")

_carregado = False


def carregar(caminho: str | None = None, forcar: bool = False) -> int:
    """
    Lê o `.env` para `os.environ`. Devolve quantas chaves foram definidas.

    Idempotente: chamar de novo não relê o arquivo, a menos que `forcar`.
    Variável já presente no ambiente tem precedência e não é sobrescrita.
    """
    global _carregado
    if _carregado and not forcar:
        return 0
    _carregado = True

    alvo = caminho or CAMINHO_ENV
    if not os.path.exists(alvo):
        return 0

    definidas = 0
    with io.open(alvo, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, valor = linha.partition("=")
            chave = chave.strip()
            valor = valor.strip().strip('"').strip("'")
            if chave and valor and chave not in os.environ:
                os.environ[chave] = valor
                definidas += 1
    return definidas


def obter(nome: str, padrao: str | None = None) -> str | None:
    """Valor da variável, carregando o `.env` antes na primeira chamada."""
    carregar()
    return os.environ.get(nome, padrao)


def mascarar(segredo: str | None) -> str:
    """
    'sk-proj-AbCd...WxYz (51 car.)' — o suficiente para conferir QUAL chave está
    em uso sem expor nenhuma que não seja.
    """
    if not segredo:
        return "(ausente)"
    if len(segredo) <= 14:
        return "%s… (%d car.)" % (segredo[:4], len(segredo))
    return "%s…%s (%d car.)" % (segredo[:11], segredo[-4:], len(segredo))


def diagnostico() -> str:
    """Uma linha por provedor: qual chave está visível, sem mostrar nenhuma."""
    carregar()
    linhas = ["  .env:               %s"
              % (CAMINHO_ENV if os.path.exists(CAMINHO_ENV) else "(não existe)")]
    for nome in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        linhas.append("  %-19s %s" % (nome + ":", mascarar(os.environ.get(nome))))
    return "\n".join(linhas)


__all__ = ["carregar", "obter", "mascarar", "diagnostico", "CAMINHO_ENV"]
