# -*- coding: utf-8 -*-
"""
Best-of-N dentro do `extrator.extrair` (v3.1) — o caminho da v2 e da medição antes/depois.

Depois dos lotes, até N-1 rodadas de reforço: em cada uma, só as perguntas que AINDA falham (considerando o melhor
candidato já obtido) voltam ao modelo, com o mesmo contexto do lote normal. Para cedo quando não sobra falha — a
rodada que não precisa não é paga. No fim, `melhor_de_n.aplicar` escolhe pelo verificador.

O provedor aqui é um roteiro: devolve, por pergunta, o que o teste mandou para cada tentativa.
"""
from __future__ import annotations

import os

from api import extracao
from fopa import extrator
from fopa import recuperacao as rec
from fopa.modelos import ErroModelo, Provedor, Uso
from fopa.questionario import NAO_LOCALIZADO

ARQ = "01 - Edital.pdf"
P1 = ("O objeto é a contratação de instituição financeira para gestão da folha de pagamento "
      "dos servidores municipais, com exclusividade.")
P2 = "A sessão pública ocorrerá em 10 de outubro de 2026, às 9 horas, no portal de compras."
PAGINAS = [rec.Pagina(arquivo=ARQ, numero=1, texto=P1), rec.Pagina(arquivo=ARQ, numero=2, texto=P2)]
BOA = {"resposta": "ok", "arquivo": ARQ, "pagina": 1, "confianca": "alta",
       "trecho_literal": "contratação de instituição financeira para gestão da folha"}
Q7_BOA = dict(BOA, pagina=2, trecho_literal="A sessão pública ocorrerá em 10 de outubro de 2026")
Q7_RUIM = dict(BOA, pagina=2, trecho_literal="a sessão será no dia 11 de novembro de 2026")


class Roteiro(Provedor):
    """Devolve BOA para todas as perguntas, menos as do roteiro: a tentativa k de uma pergunta sai da lista dela."""

    nome = "claude"

    def __init__(self, roteiro: dict[str, list[dict]]):
        self.roteiro = roteiro
        self.chamadas: list[list[str]] = []
        self.vistas: dict[str, int] = {}

    def responder_json(self, sistema, usuario, esquema, modelo, max_tokens=16000, effort="high"):
        ids = extracao.ids_do_usuario(usuario)
        self.chamadas.append(ids)
        respostas = []
        for pid in ids:
            k = self.vistas.get(pid, 0)
            self.vistas[pid] = k + 1
            plano = self.roteiro.get(pid)
            r = plano[min(k, len(plano) - 1)] if plano else BOA
            respostas.append(dict(r, id=pid))
        return {"respostas": respostas}, Uso(entrada=100, saida=10, chamadas=1, modelo=modelo)


def _extrair(tmp_path, prov, n):
    pasta = tmp_path / "Pregão Eletrônico 1-2026 - Cidade-RS"
    os.makedirs(pasta, exist_ok=True)
    return extrator.extrair(str(pasta), prov, modelo="claude-opus-5-5", modo="contexto-completo",
                            paginas_prontas=list(PAGINAS), melhor_de_n=n, modalidade="Pregão Eletrônico")


def test_reforco_recupera_a_pergunta_e_para_cedo(tmp_path):
    prov = Roteiro({"Q7": [Q7_RUIM, Q7_BOA]})
    ext = _extrair(tmp_path, prov, 3)
    assert len(prov.chamadas) == 4 and prov.chamadas[-1] == ["Q7"]        # 3 lotes + 1 reforço, só a Q7
    assert ext.por_id("Q7").trecho_literal == Q7_BOA["trecho_literal"]
    assert ext.melhor_de_n["n"] == 3 and ext.melhor_de_n["rodadas"] == 1
    assert ext.melhor_de_n["perguntas"]["Q7"]["escolhida"] == 1
    assert ext.uso.chamadas == 4 and ext.uso.entrada == 400                # o reforço entra no custo


def test_falha_que_nunca_ancora_usa_as_n_tentativas_e_fica_o_original(tmp_path):
    ruim2 = dict(Q7_RUIM, trecho_literal="texto que não existe no edital de jeito nenhum")
    prov = Roteiro({"Q7": [Q7_RUIM, ruim2, ruim2]})
    ext = _extrair(tmp_path, prov, 3)
    assert len(prov.chamadas) == 5                                         # 3 lotes + 2 rodadas
    reg = ext.melhor_de_n["perguntas"]["Q7"]
    assert reg["tentativas"] == 3 and ext.melhor_de_n["rodadas"] == 2
    # Q7_RUIM chega mais perto da página que o texto inventado: a similaridade desempata a favor do original
    assert reg["escolhida"] == 0 and ext.por_id("Q7").trecho_literal == Q7_RUIM["trecho_literal"]


def test_nao_localizado_que_se_aplica_tambem_e_reforcado(tmp_path):
    prov = Roteiro({"Q10": [{"resposta": NAO_LOCALIZADO, "confianca": "baixa"}, dict(BOA, resposta="achou")]})
    ext = _extrair(tmp_path, prov, 3)
    assert prov.chamadas[3] == ["Q10"] and ext.por_id("Q10").resposta == "achou"


def test_n_1_e_a_extracao_de_sempre(tmp_path):
    prov = Roteiro({"Q7": [Q7_RUIM, Q7_BOA]})
    ext = _extrair(tmp_path, prov, 1)
    assert len(prov.chamadas) == 3 and ext.melhor_de_n == {}
    assert ext.por_id("Q7").trecho_literal == Q7_RUIM["trecho_literal"]


class RoteiroQueFalhaNoReforco(Roteiro):
    """Os 3 lotes respondem; toda chamada de reforço levanta ErroModelo (truncada, 5xx, JSON inválido...)."""

    def responder_json(self, sistema, usuario, esquema, modelo, max_tokens=16000, effort="high"):
        if len(self.chamadas) >= 3:
            self.chamadas.append(extracao.ids_do_usuario(usuario))
            raise ErroModelo("resposta truncada pelo provedor (motivo: max_output_tokens)")
        return super().responder_json(sistema, usuario, esquema, modelo, max_tokens, effort)


def test_reforco_que_falha_nao_derruba_a_extracao(tmp_path):
    """Revisão (28/09), item 3: um reforço que falha levantava o erro e jogava fora os 3 lotes pagos (e, na medição,
    o par antes/depois). O reforço é best-effort: a tentativa conta, fica o que já havia."""
    prov = RoteiroQueFalhaNoReforco({"Q7": [Q7_RUIM]})
    ext = _extrair(tmp_path, prov, 3)
    assert len(prov.chamadas) == 5 and ext.uso.chamadas == 3                # 2 rodadas tentadas; só os lotes pagos
    reg = ext.melhor_de_n["perguntas"]["Q7"]
    assert (reg["escolhida"], reg["tentativas"], reg["falhas"]) == (0, 3, 2) and ext.melhor_de_n["rodadas"] == 2
    assert ext.por_id("Q7").trecho_literal == Q7_RUIM["trecho_literal"]


class RoteiroQueOmiteNoReforco(Roteiro):
    """Os 3 lotes respondem; o reforço volta 'bem-sucedido' mas sem nenhuma resposta."""

    def responder_json(self, sistema, usuario, esquema, modelo, max_tokens=16000, effort="high"):
        if len(self.chamadas) >= 3:
            self.chamadas.append(extracao.ids_do_usuario(usuario))
            return {"respostas": []}, Uso(chamadas=1, modelo=modelo)
        return super().responder_json(sistema, usuario, esquema, modelo, max_tokens, effort)


def test_reforco_que_omite_a_pergunta_nao_inventa_nao_localizado_na_v2(tmp_path):
    """Revisão (28/09), item 1, no caminho da medição: o reforço respondeu sem a Q7 — não vira "Não localizado"."""
    ext = _extrair(tmp_path, RoteiroQueOmiteNoReforco({"Q7": [Q7_RUIM]}), 3)
    reg = ext.melhor_de_n["perguntas"]["Q7"]
    assert (reg["escolhida"], reg["falhas"]) == (0, 2)
    assert ext.por_id("Q7").trecho_literal == Q7_RUIM["trecho_literal"]
