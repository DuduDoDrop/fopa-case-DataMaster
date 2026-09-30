# -*- coding: utf-8 -*-
"""
Versões que o worker declara em `/health` e `/versao` (plano, seção 6).

POR QUE HASHES DE CONTEÚDO, E NÃO NÚMEROS DE VERSÃO
  A ADR-014 diz que defeito conhecido do verificador não é consertado em
  silêncio: vira `versao_regras` nova e reverificação comparável. Um número
  escolhido à mão depende de alguém lembrar de incrementar; o sha256 do código
  muda sozinho quando o código muda. Cada linha de `verificacoes` grava o hash
  vigente na hora, e "mesma `versao_regras`" é o que permite ao `/verificar`
  devolver 409 em vez de duplicar.

O QUE ENTRA EM CADA HASH
  versao_regras  — bytes de verificador.py + questionario.py + distribuicao.py
                   + condicoes.py + api/politica.py + api/injecao.py, nesta
                   ordem. Tudo que decide veredito e tag — as políticas da v3
                   rodam depois do verificador e também decidem.
  versao_prompt  — o que o modelo VÊ: `instrucao_sistema()`, o `ESQUEMA_LOTE`
                   (JSON canônico), a mensagem de usuário montada por
                   `extrator.montar_mensagem` com as 17 perguntas e marcadores
                   no lugar do contexto, e as `PERGUNTAS` serializadas (termos
                   do RAG e flag `critico` incluídos: mudam o que é recuperado).
                   Calculado pelo comportamento, não pelo arquivo, para que
                   refatorar sem mudar o prompt não invalide execuções.
  escopo_versao  — bytes de escopo.py (ADR-003: o portão de regex vem antes
                   de qualquer IA; toda `licitacoes.escopo_motivo` cita esta
                   versão).
  git_sha        — `FOPA_GIT_SHA` gravado no build da imagem; fora dela,
                   `git rev-parse HEAD`; sem nenhum dos dois, "desconhecido"
                   (nunca inventa um sha).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess

from fopa import extrator, questionario   # escopo.py entra pelo caminho, não pelo import

from . import RAIZ

MODULOS_REGRAS = ("verificador", "questionario", "distribuicao", "condicoes")
PASTA_FOPA = os.path.dirname(os.path.abspath(questionario.__file__))
# A política da v3 (todo "Não localizado" vai para REVISAR) roda depois do verificador, e a da
# injeção (api/injecao.py: só trecho com cara de instrução é texto furtivo) decide a tag e a degradação.
POLITICA_V3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "politica.py")
INJECAO_V3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "injecao.py")
# O ajuste do escopo (25/09: os falsos positivos "já no filtro") roda depois da regra e entra na versão dela: mudar
# uma exclusão reavalia o acervo pelo caminho de sempre (/escopo/reavaliar).
ESCOPO_AJUSTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "escopo_ajuste.py")

# Marcadores fixos no lugar do que varia por licitação: assim o hash captura o
# molde da mensagem, não uma licitação em particular.
_MARCA_CONTEXTO = "{{CONTEXTO}}"
_MARCA_LICITACAO = "{{LICITACAO}}"


def _ler(caminho: str) -> bytes:
    """Leitura isolada para os testes trocarem o conteúdo sem tocar no disco."""
    with open(caminho, "rb") as f:
        return f.read()


def _conteudo(caminho: str) -> bytes:
    """
    O conteúdo com fim de linha LF. A imagem nasce do `git archive` com
    core.autocrlf (CRLF) e a árvore do host pode ter LF: o mesmo escopo.py dava
    duas escopo_versao (achado do W01, 24/09/2026). É a mesma normalização que
    o db/migrar.py já faz nas migrações.
    """
    return _ler(caminho).replace(b"\r\n", b"\n")


def _caminho_modulo(nome: str) -> str:
    return os.path.join(PASTA_FOPA, nome + ".py")


def versao_regras() -> str:
    h = hashlib.sha256()
    for nome in MODULOS_REGRAS:
        h.update(_conteudo(_caminho_modulo(nome)))
    h.update(_conteudo(POLITICA_V3))
    h.update(_conteudo(INJECAO_V3))
    return h.hexdigest()


def escopo_versao() -> str:
    return hashlib.sha256(_conteudo(_caminho_modulo("escopo")) + _conteudo(ESCOPO_AJUSTE)).hexdigest()


def _perguntas_serializadas() -> str:
    return json.dumps([dataclasses.asdict(p) for p in questionario.PERGUNTAS],
                      ensure_ascii=False, sort_keys=True)


def versao_prompt() -> str:
    ids = [p.id for p in questionario.PERGUNTAS]
    partes = (
        questionario.instrucao_sistema(),
        json.dumps(questionario.ESQUEMA_LOTE, ensure_ascii=False, sort_keys=True),
        extrator.montar_mensagem(_MARCA_CONTEXTO, ids, _MARCA_LICITACAO),
        _perguntas_serializadas(),
    )
    h = hashlib.sha256()
    for parte in partes:
        h.update(parte.encode("utf-8"))
        h.update(b"\x00")   # separador: evita que a fronteira entre partes seja ambígua
    return h.hexdigest()


def _git_head() -> str | None:
    """Sha do HEAD do repositório, ou None se não há git/repositório (o caso da imagem)."""
    try:
        saida = subprocess.run(["git", "rev-parse", "HEAD"], cwd=RAIZ, capture_output=True,
                               text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = saida.stdout.strip()
    return sha if saida.returncode == 0 and len(sha) == 40 else None


def git_sha() -> str:
    return os.environ.get("FOPA_GIT_SHA", "").strip() or _git_head() or "desconhecido"


def resumo() -> dict:
    """Os três hashes de código, como aparecem em `/health` e `/versao`."""
    return {"versao_regras": versao_regras(), "versao_prompt": versao_prompt(),
            "escopo_versao": escopo_versao()}


__all__ = ["MODULOS_REGRAS", "versao_regras", "versao_prompt", "escopo_versao",
           "git_sha", "resumo"]
