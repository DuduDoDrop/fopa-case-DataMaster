# -*- coding: utf-8 -*-
"""
Best-of-N — o reforço das respostas que falharam (v3.1).

A técnica gera N candidatos e escolhe pelo score. O problema usual é de onde vem o score: quase toda implementação
usa um LLM como juiz e herda a subjetividade dele. Aqui o scorer já existia e não é um modelo — é o Verificador
(ADR-004), determinístico e de custo zero (Fopa-v2/01-Fundamentos/Técnicas avançadas avaliadas.md).

TRÊS REGRAS, com o porquê
  1. Só reamostra o que FALHOU (N=3, só as que falham): resposta REPROVADA na ancoragem, ou "não
     localizado" sem evidência numa pergunta que se aplica à modalidade. O que ancorou não gasta nada; o que "não
     se aplica" (Q1/Q4/Q6 numa dispensa) é ausência esperada, não falha.
  2. Nunca troca um original que ancora, e no empate fica o que veio primeiro — o original. Estável: reamostrar
     não pode piorar o que já estava bom.
  3. Escolhe pelo veredito do próprio verificador: um candidato só vence se ANCORAR melhor. O Best-of-N não aprova
     nada que o verificador não aprovaria; ele só dá à resposta mais chances de mostrar a evidência.

A ordem dos pontos (`pontuar`): 2 = ancorada · 1 = trecho achado noutra página (o verificador corrige a citação e
manda revisar) · 0 = ausência declarada, sem evidência · -1 = reprovada. Empate na ordem desempata pela
similaridade do trecho com a página citada (0 a 1), que mede o quanto a citação chegou perto.

Quem chama: `extrator.extrair(..., melhor_de_n=N)` na v2 e na medição; na v3, o worker (`POST /reforco` decide
o que reamostrar, o `/verificar` escolhe entre as chamadas gravadas) — o modelo continua sendo chamado só pelo n8n.
"""
from __future__ import annotations

from dataclasses import replace

from .extrator import Extracao, Resposta
from .questionario import nao_se_aplica
from .verificador import (APROVADO, REPROVADO, REVISAR, _normalizar, _similar, ausencia_real, modalidade_da,
                          verificar_ancoragem)

N_PADRAO = 3


def falhou(r: Resposta, ext: Extracao, modalidade: str | None) -> bool:
    """A resposta merece outra tentativa? Ver a regra 1 no topo."""
    if ausencia_real(r):
        return not nao_se_aplica(r.id, modalidade_da(ext, modalidade) or "")
    veredito, _ = verificar_ancoragem(replace(r), ext)      # numa cópia: a ancoragem pode corrigir a página
    return veredito == REPROVADO


def falhas(ext: Extracao, modalidade: str | None) -> list[str]:
    """Os ids que falharam, na ordem das respostas."""
    return [r.id for r in ext.respostas if falhou(r, ext, modalidade)]


def _similaridade(r: Resposta, ext: Extracao) -> float:
    """O melhor casamento do trecho com a página citada, de 0 a 1 — a mesma janela deslizante da ancoragem."""
    if not r.trecho_literal or not r.arquivo or not r.pagina:
        return 0.0
    pg = ext.pagina(r.arquivo, r.pagina)
    if pg is None:
        return 0.0
    alvo, fonte = _normalizar(r.trecho_literal), _normalizar(pg.texto)
    if not alvo:
        return 0.0
    if alvo in fonte:
        return 1.0
    n = len(alvo)
    passo = max(1, n // 4)
    return max((_similar(alvo, fonte[i:i + n]) for i in range(0, max(1, len(fonte) - n + 1), passo)),
               default=0.0)


def pontuar(r: Resposta, ext: Extracao) -> tuple[int, float]:
    """(ordem, similaridade) — ver o topo. Nunca altera `r`."""
    if ausencia_real(r):
        return 0, 0.0
    copia = replace(r)
    veredito, _ = verificar_ancoragem(copia, ext)
    ordem = {APROVADO: 2, REVISAR: 1}.get(veredito, -1)
    return ordem, round(_similaridade(copia if ordem == 1 else r, ext), 4)


def escolher(original: Resposta, candidatos: list[Resposta], ext: Extracao) -> tuple[Resposta, dict]:
    """O melhor entre o original e os candidatos; no empate, o primeiro (o original). Devolve (escolhida, registro)."""
    todos = [original] + list(candidatos)
    pontos = [pontuar(r, ext) for r in todos]
    melhor = 0
    for i, p in enumerate(pontos):
        if p > pontos[melhor]:
            melhor = i
    return todos[melhor], {"tentativas": len(todos), "escolhida": melhor,
                           "pontos": [[o, s] for o, s in pontos]}


def aplicar(ext: Extracao, candidatos: dict[str, list[Resposta]],
            tentativas: dict[str, int] | None = None) -> dict[str, dict]:
    """
    Troca, em `ext.respostas`, cada pergunta com candidatos pela escolhida. Devolve o registro por pergunta.

    `tentativas`: quantas vezes cada pergunta FOI ao reforço, contando as chamadas que falharam (truncada, 5xx, ou
    que voltaram sem ela). Sem isso, contam só os candidatos válidos. O registro diz `tentativas` (a original + as
    feitas) e `falhas` (as feitas que não deram candidato) — o reforço que foi tentado e pago nunca some do registro,
    mesmo sem nenhum candidato (revisão da v3.1, 28/09).
    """
    feitas = dict(tentativas or {})
    for pid, lista in candidatos.items():
        feitas[pid] = max(feitas.get(pid, 0), len(lista))
    registro = {}
    for i, r in enumerate(ext.respostas):
        if r.id not in feitas:
            continue
        validos = candidatos.get(r.id, [])
        escolhida, reg = escolher(r, validos, ext)
        reg["tentativas"] = 1 + feitas[r.id]
        reg["falhas"] = feitas[r.id] - len(validos)
        registro[r.id] = reg
        ext.respostas[i] = escolhida
    return registro


__all__ = ["N_PADRAO", "falhou", "falhas", "pontuar", "escolher", "aplicar"]
