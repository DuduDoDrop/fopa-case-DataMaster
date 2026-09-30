# -*- coding: utf-8 -*-
"""
Cliente do Jev (TypeSafe AI) — decisao tipada com probabilidade.

O QUE ELE E, NO LUGAR CERTO DA ARQUITETURA
  Jev NAO decide nada neste projeto. Ele e um SEGUNDO SINAL, independente do
  filtro de regras do projeto, e serve para dizer onde vale olhar -- nunca para
  aprovar ou reprovar. A linha esta na ADR-004: o Jev nao e motivo de
  decisao, e um adendo de assertividade.

  Concretamente, o que isto NAO pode fazer:
    · aprovar resposta        -> quem aprova e o Verificador, por ancoragem
    · substituir `escopo.avaliar` -> a regra continua sendo o veredito
    · virar `confianca` da resposta -> esse campo ja tem dono

  E o que pode:
    · discordar do filtro, e a discordancia virar fila de revisao humana
    · dar uma segunda estimativa ao lado da regra, as duas visiveis

A FORMA DA API, conferida ao vivo em 23/09/2026
  POST https://api.typesafe.ai/v1/systemone
  Authorization: Bearer <chave>      Content-Type: application/json

      {"state": "<o texto>", "model": "jev-latest",
       "questions": {"<id>": {"type": "choice",
                              "instructions": "<a pergunta>",
                              "criteria": {"<opcao>": "<quando vale>"}}}}

  Resposta:

      {"model": "jev-1.13.0",
       "answers": {"<id>": {"type": "choice", "choice": "<opcao>",
                            "confidence": 0.42,
                            "probabilities": {"<opcao>": 0.71, ...}}},
       "usage": {"input_tokens": 457, "output_tokens": 42}}

  NAO HA campo de trecho, citacao, offset ou substring da entrada. Isso esta
  conferido contra a API real, nao contra o anuncio -- e e o que impede usar
  Jev na extracao ancorada: sem span nao ha o que o Verificador confira.

O QUE A AUDITORIA DE TERCEIRO DIZ, E QUE MUDA COMO SE USA
  · a acuracia e PLANA entre confianca 0,50 e 0,95 -- "gate at 0.99 or not at
    all". Entao confianca intermediaria nao ordena nada, e usa-la para
    priorizar seria inventar ordem.
  · fora de distribuicao, o ECE vai a 0,325: 44,7% de acerto com probabilidade
    media 0,74. Licitacao brasileira e, muito provavelmente, fora da
    distribuicao de treino.
  · com criterio mal descrito, caiu a 16,7% -- abaixo do acaso de 25%. A
    descricao do criterio E a variavel.

  Por isso este modulo nao expoe nada que pareca "o Jev disse que sim".
  Ele devolve a resposta crua, com probabilidades e custo, e quem chama
  precisa decidir o que fazer com uma opiniao nao calibrada.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from . import segredos

URL = "https://api.typesafe.ai/v1/systemone"
# Fixado na versão em que os cortes 0,25/0,75 foram medidos (63_ e 64_, 23/09/2026):
# o alias "jev-latest" troca de modelo quando sai versão nova (docs.typesafe.ai).
MODELO = os.environ.get("FOPA_MODELO_JEV", "jev-1.13.0")

# Preco e limites de https://docs.typesafe.ai/models.md (jev-1.13/latest),
# lidos em 23/09/2026. Ainda NAO conferidos contra fatura -- a origem fica
# declarada, como manda a regra de nao escrever valor sem fonte.
#
#     entrada ......... US$ 0,042 por milhao de tokens
#     saida ........... "Output tokens are free" -- documentado, nao suposto
#     contexto ........ 64k por request; 32k para `state` + a maior pergunta
#     taxa ............ 250 mil tokens/s, 1.200 requisicoes/min
#
# O teto que pega na pratica e o de `state`, porque e la que o documento vai:
# com uma pergunta de algumas centenas de tokens, metade do request fica
# inutilizavel. A pagina avisa que os limites de taxa mudam sem aviso.
PRECO_ENTRADA_ANUNCIADO = 0.042
PRECO_SAIDA_ANUNCIADO = 0.0      # documentado como gratuito
FONTE_PRECO = "docs.typesafe.ai/models (23/09/2026); NAO conferido contra fatura"
MAX_TOKENS_STATE = 32_768
RPM_DOCUMENTADO = 1_200


class ErroJev(RuntimeError):
    """Falha ao falar com o Jev. Carrega o corpo da resposta quando ha."""

    def __init__(self, *args, status: int = 0, corpo: str = ""):
        super().__init__(*args)
        self.status = status
        self.corpo = corpo


def chave() -> str:
    segredos.carregar()
    k = (os.environ.get("JEV_API_KEY") or "").strip()
    if not k:
        raise ErroJev("JEV_API_KEY ausente — veja o .env")
    return k


def escolha(pergunta: str, criterios: dict) -> dict:
    """
    Pergunta `choice` — escolhe UMA opcao de um conjunto definido.

    Use quando as opcoes competem entre si e a distribuicao entre elas
    interessa. Para "esta condicao vale?", a primitiva certa e `noul`.
    """
    return {"type": "choice", "instructions": pergunta, "criteria": criterios}


def noul(pergunta: str, quando_sim: str, quando_nao: str) -> dict:
    """
    Pergunta `noul` — probabilidade de SIM, de 0 a 1.

    E a primitiva para "esta condicao vale?", e nao `choice` com duas opcoes:
    a documentacao do fornecedor e explicita em que Noul devolve probabilidade
    de sim, sem campo de confianca separado. Um Noul perto de 0,5 significa
    "sim e nao com probabilidade parecida", NAO "intensidade media".

    Tambem e a primitiva do cookbook de reranking: pontuar cada par
    (consulta, candidato) de forma independente e ordenar pelo valor.
    """
    return {"type": "noul", "instructions": pergunta,
            "criteria": {"true": quando_sim, "false": quando_nao}}


def valor(resposta: dict):
    """
    O numero que interessa de uma resposta, seja ela `noul` ou `choice`.

    `noul` -> a probabilidade de sim, no campo `noul`.
    `choice` -> a opcao escolhida, em `choice`, com `confidence` ao lado.

    Ler o campo errado e silencioso: um `choice` nao tem `noul` e devolveria
    `None`, que num `if` vira "nao" sem avisar.
    """
    if not isinstance(resposta, dict):
        return None
    if resposta.get("type") == "noul" or "noul" in resposta:
        return resposta.get("noul")
    return resposta.get("choice")


def perguntar(estado: str, perguntas: dict, modelo: str | None = None,
              timeout: int = 60) -> tuple[dict, dict]:
    """
    Manda o estado e as perguntas; devolve `(answers, uso)`.

    `uso` traz `input_tokens`, `output_tokens`, `segundos`, `usd` e `modelo` --
    o `usd` com o preco ANUNCIADO, porque ainda nao ha fatura para conferir.
    """
    corpo = {"state": estado, "model": modelo or MODELO, "questions": perguntas}
    req = urllib.request.Request(
        URL, data=json.dumps(corpo).encode("utf-8"),
        headers={"Authorization": "Bearer " + chave(),
                 "Content-Type": "application/json"},
        method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        texto = e.read()[:400].decode("utf-8", "replace")
        raise ErroJev("HTTP %d do Jev" % e.code, status=e.code,
                      corpo=texto) from e
    except Exception as e:                                        # noqa: BLE001
        raise ErroJev("falha ao chamar o Jev: %s" % e) from e

    u = dados.get("usage") or {}
    ent, sai = u.get("input_tokens") or 0, u.get("output_tokens") or 0
    uso = {"input_tokens": ent, "output_tokens": sai,
           "segundos": round(time.time() - t0, 3),
           "modelo": dados.get("model"),
           "usd": (ent * PRECO_ENTRADA_ANUNCIADO
                   + sai * PRECO_SAIDA_ANUNCIADO) / 1_000_000,
           "preco": FONTE_PRECO}
    return dados.get("answers") or {}, uso


__all__ = ["ErroJev", "URL", "MODELO", "escolha", "noul", "valor",
           "MAX_TOKENS_STATE", "RPM_DOCUMENTADO",
           "perguntar", "chave",
           "PRECO_ENTRADA_ANUNCIADO", "FONTE_PRECO"]
