# -*- coding: utf-8 -*-
"""
O custo da OpenAI, token por token (v3.1; achado da medição antes/depois, 28/09/2026).

A fatura da OpenAI decompõe a entrada em três: nova (US$ 4/M), GRAVADA no cache (US$ 5/M = 1,25×) e LIDA do cache
(US$ 0,40/M = 0,10×) — 321 + 122.407 + 54.376 tokens no gpt-5.6-sol de 23/09 (Fopa-v2/04-Avaliacao/Resultados
medidos.md). O `input_tokens` da Responses API já SOMA as três. Descontar só a leitura deixava a gravação na
entrada E no cache gravado: cobrada duas vezes (1,0× + 1,25×), e a economia da ordem nova do prompt sairia exagerada.
"""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

from api import extracao  # noqa: F401  (põe scripts/ no path)
from fopa import modelos
from fopa.questionario import ESQUEMA_LOTE

NOVA, GRAVADA, LIDA, SAIDA = 321, 122_407, 54_376, 35_310


class _Respostas:
    def create(self, **kw):
        uso = NS(input_tokens=NOVA + GRAVADA + LIDA, output_tokens=SAIDA, total_tokens=0,
                 input_tokens_details=NS(cached_tokens=LIDA, cache_write_tokens=GRAVADA),
                 output_tokens_details=NS(reasoning_tokens=0))
        return NS(status="completed", output_text=json.dumps({"respostas": []}), usage=uso)


def _provedor():
    prov = modelos.ProvedorOpenAI.__new__(modelos.ProvedorOpenAI)          # sem chave: o cliente é falso
    prov.cliente = NS(responses=_Respostas())
    prov._openai = NS(RateLimitError=type("RateLimitError", (Exception,), {}))
    prov.tentativas = 1
    return prov


def test_entrada_nova_nao_carrega_a_gravacao_nem_a_leitura():
    _, uso = _provedor().responder_json("s", "u", ESQUEMA_LOTE, "gpt-5.6-sol")
    assert (uso.entrada, uso.cache_escrita, uso.cache_leitura, uso.saida) == (NOVA, GRAVADA, LIDA, SAIDA)


def test_o_custo_reproduz_a_fatura():
    _, uso = _provedor().responder_json("s", "u", ESQUEMA_LOTE, "gpt-5.6-sol")
    p = modelos.PRECOS["gpt-5.6-sol"]
    fatura = (NOVA * p["entrada"] + GRAVADA * p["entrada"] * modelos.CACHE_ESCRITA
              + LIDA * p["entrada"] * modelos.CACHE_LEITURA + SAIDA * p["saida"]) / 1e6
    assert abs(uso.usd - fatura) < 1e-9
