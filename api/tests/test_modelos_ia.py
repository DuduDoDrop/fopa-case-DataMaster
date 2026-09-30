# -*- coding: utf-8 -*-
"""
O catálogo do botão "Extrair com IA" (api/modelos_ia.py): provedor -> modelos, cada um com o esforço FIXO.
Os níveis e padrões vêm das páginas oficiais:
  OpenAI     developers.openai.com/api/docs/models/<modelo> e /guides/reasoning
  Anthropic  platform.claude.com/docs/en/build-with-claude/effort
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from api import modelos_ia  # noqa: E402
from fopa import modelos  # noqa: E402


def test_so_entra_modelo_com_preco_conferido():
    # sem preço, o custo sairia "preço não configurado" e o teto do dia não protegeria nada
    for prov in modelos_ia.CATALOGO.values():
        for m in prov["modelos"]:
            assert m["id"] in modelos.PRECOS, m["id"]


# Desde 26/09 o esforço não se escolhe: é fixo por modelo, no ponto de custo-benefício, e o Claude roda no médio,
# com o Opus 5.5. A varredura do ADR-009 (Sonnet 5 em
# Pirapó) deu a mesma acurácia em low, medium e high; o medium é o padrão da OpenAI e o do Opus 5.5.
# O GPT-6 Luna foi para high e voltou no mesmo dia (28/09): em Bertioga,
# pelo botão, high deu 13/17 como o medium (14/17 e 13/17), com o dobro do tempo.
@pytest.mark.parametrize("modelo,esforco", [
    ("gpt-5.6-sol", "medium"), ("gpt-6-sol", "medium"), ("gpt-6-luna", "medium"), ("gpt-6-astra", "medium"),
    ("claude-opus-5-5", "medium"), ("claude-sonnet-5", "medium"),
    ("claude-haiku-4-5", None),                                            # o Haiku 4.5 não tem esforço
])
def test_cada_modelo_tem_um_esforco_fixo(modelo, esforco):
    m = modelos_ia.modelo(modelo)
    assert m["esforco"] == esforco
    assert "esforcos" not in m and "padrao" not in m                       # não há mais o que escolher


def test_o_claude_e_o_opus_5_5_e_o_opus_5_saiu():
    ids = [m["id"] for m in modelos_ia.CATALOGO["claude"]["modelos"]]
    assert ids == ["claude-opus-5-5", "claude-sonnet-5", "claude-haiku-4-5"]
    assert modelos.PRECOS["claude-opus-5-5"]["entrada"] == 4.00 and modelos.PRECOS["claude-opus-5-5"]["saida"] == 20.00


def test_o_teto_de_saida_sobe_com_o_esforco():
    # o raciocínio conta no limite de saída: com 16 mil, xhigh e max seriam cortados no meio (stop_reason max_tokens)
    assert modelos_ia.max_tokens(None) == modelos_ia.max_tokens("high") == 16000
    assert modelos_ia.max_tokens("xhigh") == 32000 and modelos_ia.max_tokens("max") == 64000


def test_resolver_valida_e_usa_o_esforco_fixo():
    assert modelos_ia.resolver("openai", None, None) == ("gpt-5.6-sol", "medium", 16000)
    assert modelos_ia.resolver("claude", None, None) == ("claude-opus-5-5", "medium", 16000)
    assert modelos_ia.resolver("claude", "claude-sonnet-5", "medium") == ("claude-sonnet-5", "medium", 16000)
    assert modelos_ia.resolver("claude", "claude-haiku-4-5", None) == ("claude-haiku-4-5", None, 16000)
    for ruim in [("openai", "claude-opus-5-5", None), ("claude", "gpt-6-sol", None), ("claude", "claude-opus-5", None),
                 ("claude", "claude-opus-5-5", "max"), ("openai", "gpt-6-astra", "none"), ("claude", "claude-haiku-4-5", "high"),
                 ("openai", "gpt-9", None), ("gemini", None, None)]:
        with pytest.raises(ValueError):
            modelos_ia.resolver(*ruim)


def test_estimativa_pelo_edital_de_poa_no_esforco_fixo():
    # Poá (25/09): 118.648 tokens de entrada e 11.726 de saída em high; em medium a saída é ~75% disso
    e = modelos_ia.estimativa("gpt-5.6-sol")
    assert e["usd"] == pytest.approx(0.650, abs=0.01)
    assert e["usd_max"] > e["usd"]                       # o pior caso: 3 chamadas no teto de saída
    assert modelos_ia.estimativa("claude-opus-5-5")["usd"] == pytest.approx(0.650, abs=0.01)   # US$ 4 / 20, igual ao 5.6 Sol


def test_publico_tem_o_que_a_tela_precisa():
    p = modelos_ia.publico()
    assert [x["id"] for x in p["provedores"]] == ["openai", "claude"]
    m = p["provedores"][1]["modelos"][0]
    assert m["id"] == "claude-opus-5-5" and m["esforco"] == "medium"
    assert {"id", "rotulo", "nota", "esforco", "estimativa"} <= set(m) and "esforcos" not in m


def test_execucao_do_agente_local_nao_tem_preco_de_api_mesmo_com_o_modelo_na_tabela():
    # O agente (Claude Code, sem API) grava provedor 'claude-code' e modelo 'claude-opus-5-5', sem tokens. Com o Opus
    # 5.5 na tabela (26/09), o relatório diria "R$ 0,00" — e R$ 0 nunca é o que se mostra (ADR-012): o agente não
    # passou por API. A chamada de API com o mesmo modelo tem preço.
    from api import reconstrucao
    agente = reconstrucao.uso_da_execucao({"provedor": "claude-code", "modelo": "claude-opus-5-5", "tok_entrada": 0})
    assert agente.preco_conhecido is False
    api = reconstrucao.uso_da_execucao({"provedor": "claude", "modelo": "claude-opus-5-5", "tok_entrada": 1_000_000})
    assert api.preco_conhecido is True and api.usd == pytest.approx(4.0)
