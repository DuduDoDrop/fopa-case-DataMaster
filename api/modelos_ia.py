# -*- coding: utf-8 -*-
"""
O catálogo do botão "Extrair com IA": provedor -> modelos, cada um com o esforço FIXO (desde 26/09).

POR QUE MEDIUM: a varredura do ADR-009 (Sonnet 5 em Pirapó) deu a mesma acurácia (16/17) e as mesmas críticas (7/7)
em low, medium e high — o esforço mexe só na saída, ~12% da conta; o medium é o padrão da OpenAI ("a configuração
padrão para a maioria dos casos") e o do Opus 5.5. O que rodou Poá e Vale de São Domingos foi o padrão da OpenAI.
Decisão registrada no ADR-020.

O GPT-6 LUNA FOI PARA HIGH E VOLTOU no mesmo dia (28/09): em Bertioga, pelo
botão e contra o gabarito, high deu 13/17 como o medium (14/17 e 13/17), com o dobro do tempo e da saída.

Só entra modelo com preço em `fopa.modelos.PRECOS` — sem preço, o custo sai "preço não configurado" e o teto do dia
não protege nada. O Opus 5.5 entrou em 26/09 pela tabela oficial (US$ 4 / 20); o Opus 5 saiu (o 5.5 é mais novo e
mais barato).

Os níveis que cada modelo aceitaria, das páginas oficiais (lidas em 25-26/09/2026): gpt-5.6-sol, gpt-6-sol e
gpt-6-luna aceitam none..max; o gpt-6-astra não aceita none; Opus 5.5 e Sonnet 5 aceitam low..max; o Haiku 4.5 não
tem esforço. Isso não chega mais à tela: o esforço é o daqui.
"""
from __future__ import annotations

from fopa import modelos

CATALOGO = {
    "openai": {"rotulo": "OpenAI (GPT)", "modelos": [
        {"id": "gpt-5.6-sol", "rotulo": "GPT-5.6 Sol", "esforco": "medium", "nota": "o que extraiu Poá (25/09)"},
        {"id": "gpt-6-sol", "rotulo": "GPT-6 Sol", "esforco": "medium", "nota": "raciocínio forte, metade do preço do 5.6 Sol"},
        {"id": "gpt-6-astra", "rotulo": "GPT-6 Astra", "esforco": "medium", "nota": "o mais capaz da OpenAI; o mais caro"},
        {"id": "gpt-6-luna", "rotulo": "GPT-6 Luna", "esforco": "medium", "nota": "o mais barato e rápido"},
    ]},
    "claude": {"rotulo": "Claude (Anthropic)", "modelos": [
        {"id": "claude-opus-5-5", "rotulo": "Claude Opus 5.5", "esforco": "medium",
         "nota": "o extrator do projeto; mais barato que o Opus 5"},
        {"id": "claude-sonnet-5", "rotulo": "Claude Sonnet 5", "esforco": "medium", "nota": "equilíbrio entre qualidade e custo"},
        {"id": "claude-haiku-4-5", "rotulo": "Claude Haiku 4.5", "esforco": None, "nota": "o mais barato; sem controle de esforço"},
    ]},
}

MAX_TOKENS = {"xhigh": 32000, "max": 64000}
MAX_TOKENS_PADRAO = 16000

# A estimativa parte do edital de Poá (25/09): 118.648 tokens de entrada e 11.726 de saída em high, 3 chamadas. O
# esforço muda a saída (o raciocínio é cobrado como saída); os fatores são aproximados — a medida é a fatura.
ENTRADA_TIPICA = 118_648
SAIDA_EM_HIGH = 11_726
CHAMADAS = 3
FATOR_SAIDA = {"none": 0.3, "low": 0.5, "medium": 0.75, None: 1.0, "high": 1.0, "xhigh": 1.6, "max": 2.5}


def modelo(modelo_id: str) -> dict:
    for prov in CATALOGO.values():
        for m in prov["modelos"]:
            if m["id"] == modelo_id:
                return m
    raise ValueError("O modelo %r não está no catálogo." % modelo_id)


def max_tokens(effort: str | None) -> int:
    return MAX_TOKENS.get(effort or "", MAX_TOKENS_PADRAO)


def resolver(provedor: str, modelo_id: str | None, effort: str | None = None) -> tuple[str, str | None, int]:
    """Valida a escolha da tela e completa com o esforço fixo: (modelo, esforço, teto de saída por chamada)."""
    if provedor not in CATALOGO:
        raise ValueError("Provedor %r inválido: escolha openai ou claude." % provedor)
    ids = [m["id"] for m in CATALOGO[provedor]["modelos"]]
    modelo_id = modelo_id or ids[0]
    if modelo_id not in ids:
        raise ValueError("O modelo %s não é do provedor %s." % (modelo_id, provedor))
    m = modelo(modelo_id)
    if effort is not None and effort != m["esforco"]:
        raise ValueError("O esforço de raciocínio é fixo: o %s usa %s." % (
            m["rotulo"], m["esforco"] or "nenhum (o modelo não tem controle de esforço)"))
    return modelo_id, m["esforco"], max_tokens(m["esforco"])


def estimativa(modelo_id: str) -> dict:
    """US$ estimado para um edital como o de Poá no esforço fixo do modelo, e o máximo (3 chamadas no teto de saída)."""
    effort = modelo(modelo_id)["esforco"]
    p = modelos.PRECOS[modelo_id]
    entrada = ENTRADA_TIPICA * p["entrada"] / 1e6
    saida = SAIDA_EM_HIGH * FATOR_SAIDA.get(effort, 1.0) * p["saida"] / 1e6
    teto = CHAMADAS * max_tokens(effort) * p["saida"] / 1e6
    return {"usd": round(entrada + saida, 3), "usd_max": round(entrada + teto, 2),
            "brl": round((entrada + saida) * modelos.USD_BRL, 2)}


def publico() -> dict:
    """O que a tela recebe (GET /api/modelos-ia): provedores, modelos, o esforço fixo e a estimativa de cada um."""
    provs = []
    for pid, prov in CATALOGO.items():
        ms = [{**m, "estimativa": estimativa(m["id"])} for m in prov["modelos"]]
        provs.append({"id": pid, "rotulo": prov["rotulo"], "modelos": ms})
    return {"provedores": provs, "base": "edital de Poá (25/09): %d mil tokens de entrada, 3 chamadas" % (
        ENTRADA_TIPICA // 1000)}


__all__ = ["CATALOGO", "modelo", "max_tokens", "resolver", "estimativa", "publico"]
