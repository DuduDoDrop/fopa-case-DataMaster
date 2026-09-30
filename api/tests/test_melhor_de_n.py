# -*- coding: utf-8 -*-
"""
Best-of-N (v3.1; N=3, só as que falham).

O scorer não é um modelo: é o próprio Verificador (ADR-004), determinístico e de custo zero
(Fopa-v2/01-Fundamentos/Técnicas avançadas avaliadas.md). Estes testes fixam as três regras que mantêm o
Best-of-N honesto: só reamostra o que FALHOU; nunca troca um original que já ancora; e escolhe pelo veredito do
verificador — um candidato só vence se ancorar melhor.
"""
from __future__ import annotations

from dataclasses import replace

from api import extracao  # noqa: F401  (põe scripts/ no path)
from fopa import melhor_de_n as bon
from fopa import recuperacao as rec
from fopa.extrator import Extracao, Resposta
from fopa.questionario import NAO_LOCALIZADO

ARQ = "01 - Edital.pdf"
P1 = ("O objeto é a contratação de instituição financeira para gestão da folha de pagamento "
      "dos servidores municipais, com exclusividade.")
P2 = "A sessão pública ocorrerá em 10 de outubro de 2026, às 9 horas, no portal de compras."


def _ext(*respostas: Resposta) -> Extracao:
    paginas = [rec.Pagina(arquivo=ARQ, numero=1, texto=P1), rec.Pagina(arquivo=ARQ, numero=2, texto=P2)]
    return Extracao(licitacao="Pregão Eletrônico 1-2026 - Cidade-RS", respostas=list(respostas), paginas=paginas)


def _r(pid, trecho=None, pagina=None, resposta="valor", arquivo=ARQ):
    return Resposta(id=pid, pergunta="?", resposta=resposta, arquivo=arquivo if trecho else None,
                    pagina=pagina, trecho_literal=trecho)


ANCORADA = _r("Q2", "contratação de instituição financeira para gestão da folha", 1)
INVENTADA = _r("Q7", "a sessão será no dia 11 de novembro de 2026", 2)
AUSENTE = _r("Q10", resposta=NAO_LOCALIZADO)


def test_reprovada_e_falha_ancorada_nao_e():
    ext = _ext(ANCORADA, INVENTADA)
    assert not bon.falhou(ANCORADA, ext, None)
    assert bon.falhou(INVENTADA, ext, None)


def test_nao_localizado_que_se_aplica_e_falha_o_que_nao_se_aplica_nao_e():
    q1 = _r("Q1", resposta=NAO_LOCALIZADO)                # Q1 não se aplica a dispensa
    ext = _ext(AUSENTE, q1)
    assert bon.falhou(AUSENTE, ext, "Dispensa de Licitação")
    assert not bon.falhou(q1, ext, "Dispensa de Licitação")
    assert bon.falhou(q1, ext, "Pregão Eletrônico")       # num pregão, a Q1 se aplica
    assert bon.falhas(_ext(ANCORADA, INVENTADA, AUSENTE, q1), "Dispensa") == ["Q7", "Q10"]


def test_escolhe_o_candidato_que_ancora():
    boa = _r("Q7", "A sessão pública ocorrerá em 10 de outubro de 2026", 2, resposta="10/10/2026 às 9h")
    ext = _ext(INVENTADA)
    escolhida, reg = bon.escolher(INVENTADA, [replace(INVENTADA), boa], ext)
    assert escolhida is boa
    assert reg["tentativas"] == 3 and reg["escolhida"] == 2
    assert [p[0] for p in reg["pontos"]] == [-1, -1, 2]


def test_original_ancorado_nunca_e_trocado_e_no_empate_fica_o_original():
    outra_ancorada = _r("Q2", "gestão da folha de pagamento dos servidores municipais", 1, resposta="outra")
    escolhida, reg = bon.escolher(ANCORADA, [outra_ancorada], _ext(ANCORADA))
    assert escolhida is ANCORADA and reg["escolhida"] == 0
    # empate exato (o candidato é a mesma resposta de novo): fica o primeiro, o original — não o último
    escolhida, reg = bon.escolher(INVENTADA, [replace(INVENTADA), replace(INVENTADA)], _ext(INVENTADA))
    assert escolhida is INVENTADA and reg["escolhida"] == 0 and reg["tentativas"] == 3


def test_pagina_corrigida_vale_mais_que_ausencia_e_menos_que_ancorada():
    pagina_errada = _r("Q7", "A sessão pública ocorrerá em 10 de outubro de 2026", 1)   # o trecho está na p.2
    ext = _ext(AUSENTE, pagina_errada)
    assert bon.pontuar(pagina_errada, ext)[0] == 1
    assert bon.pontuar(AUSENTE, ext)[0] == 0
    assert bon.pontuar(ANCORADA, _ext(ANCORADA))[0] == 2
    assert bon.pontuar(INVENTADA, _ext(INVENTADA))[0] == -1


def test_pontuar_nao_altera_a_resposta():
    pagina_errada = _r("Q7", "A sessão pública ocorrerá em 10 de outubro de 2026", 1)
    antes = replace(pagina_errada)
    bon.pontuar(pagina_errada, _ext(pagina_errada))
    assert pagina_errada == antes                          # o verificador corrige a página numa CÓPIA


def test_similaridade_desempata_entre_reprovadas():
    quase = _r("Q7", "A sessão pública ocorrerá em 10 de outubro de 2027", 2)   # um dígito trocado: reprova
    longe = _r("Q7", "prazo de vigência do contrato de sessenta meses", 2)
    ext = _ext(quase)
    assert bon.pontuar(quase, ext)[0] == -1 and bon.pontuar(longe, ext)[0] == -1
    assert bon.pontuar(quase, ext)[1] > bon.pontuar(longe, ext)[1]


def test_aplicar_troca_so_as_perguntas_com_candidatos_e_devolve_o_registro():
    boa = _r("Q7", "A sessão pública ocorrerá em 10 de outubro de 2026", 2, resposta="10/10/2026")
    ext = _ext(ANCORADA, INVENTADA, AUSENTE)
    reg = bon.aplicar(ext, {"Q7": [boa], "Q10": [replace(AUSENTE)]})
    assert ext.por_id("Q7") is boa and ext.por_id("Q2") is ANCORADA and ext.por_id("Q10") is AUSENTE
    assert [r.id for r in ext.respostas] == ["Q2", "Q7", "Q10"]              # a ordem não muda
    assert reg["Q7"]["escolhida"] == 1 and reg["Q10"]["escolhida"] == 0 and set(reg) == {"Q7", "Q10"}
    assert bon.N_PADRAO == 3


def test_aplicar_registra_tentativas_que_falharam():
    """Revisão (28/09), item 2: a pergunta que foi ao reforço entra no registro mesmo sem candidato válido."""
    boa = _r("Q7", "A sessão pública ocorrerá em 10 de outubro de 2026", 2, resposta="10/10/2026")
    ext = _ext(ANCORADA, INVENTADA, AUSENTE)
    reg = bon.aplicar(ext, {"Q7": [boa]}, {"Q7": 2, "Q10": 2})
    assert (reg["Q7"]["escolhida"], reg["Q7"]["tentativas"], reg["Q7"]["falhas"]) == (1, 3, 1)
    assert (reg["Q10"]["escolhida"], reg["Q10"]["tentativas"], reg["Q10"]["falhas"]) == (0, 3, 2)
    assert ext.por_id("Q10") is AUSENTE
