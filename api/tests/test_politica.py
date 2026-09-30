# -*- coding: utf-8 -*-
"""
A política de veredito da v3, aplicada depois do verificador.

Decisão de 24/09/2026: TODO "Não localizado" entra no status de revisão (REVISAR), inclusive
o Q4/Q6 de credenciamento e dispensa (o "não se aplica" da modalidade).

O verificador real é quem produz o ponto de partida: ele aprova a ausência declarada.
Os testes provam o antes (APROVADO) e o depois (REVISAR com o motivo), que REPROVADO
não melhora, que a contagem de ausências não muda e que aplicar duas vezes não dobra
o motivo.
"""
from __future__ import annotations

import api  # noqa: F401  (põe scripts/ no sys.path)
from fopa import recuperacao as rec, verificador
from fopa.extrator import Extracao, Resposta

from api import politica

EDITAL = "01 - Edital.pdf"
TEXTO = "O prazo de vigência do contrato será de 60 (sessenta) meses, prorrogável por igual período."


def _ext(*respostas: Resposta) -> Extracao:
    return Extracao(licitacao="Credenciamento - Teste-SP", respostas=list(respostas),
                    paginas=[rec.Pagina(EDITAL, 1, TEXTO)])


def _nl(pid: str, texto: str = "Não localizado") -> Resposta:
    return Resposta(id=pid, pergunta=pid, resposta=texto, confianca="alta")


def _q9() -> Resposta:
    return Resposta(id="Q9", pergunta="Q9", resposta="60 meses, prorrogável", arquivo=EDITAL, pagina=1,
                    trecho_literal="O prazo de vigência do contrato será de 60 (sessenta) meses",
                    confianca="alta")


def test_todo_nao_localizado_aprovado_vai_para_revisar_com_o_motivo():
    ext = _ext(_q9(), _nl("Q16", "Não localizado. O edital não prevê prova de vida."),
               _nl("Q4", "Não localizado. Credenciamento não tem pregão nem lance."), _nl("Q6"))
    rel = verificador.verificar(ext, None, modalidade="credenciamento")
    # o ponto de partida: o verificador aprova a ausência declarada, inclusive o "não se aplica"
    assert {r.id: r.veredito for r in ext.respostas} == {"Q9": "APROVADO", "Q16": "APROVADO",
                                                          "Q4": "APROVADO", "Q6": "APROVADO"}

    rel = politica.aplicar(ext, rel)

    assert {r.id: r.veredito for r in ext.respostas} == {"Q9": "APROVADO", "Q16": "REVISAR",
                                                          "Q4": "REVISAR", "Q6": "REVISAR"}
    for pid in ("Q16", "Q4", "Q6"):
        assert politica.ALERTA_NAO_LOCALIZADO in ext.por_id(pid).alertas
    assert politica.ALERTA_NAO_LOCALIZADO not in ext.por_id("Q9").alertas
    assert (rel.aprovadas, rel.revisar, rel.reprovadas) == (1, 3, 0)
    # a contagem de ausências mede o DOCUMENTO, não o veredito: não muda
    assert rel.nao_localizado == 3


def test_reprovado_nao_melhora_e_nao_ganha_o_motivo():
    # "Não localizado" com citação que não existe na página: o verificador reprova
    q13 = Resposta(id="Q13", pergunta="Q13", resposta="Não localizado como pirâmide. Efetivos 201.",
                   arquivo=EDITAL, pagina=1, trecho_literal="Efetivos 201 servidores lotados", confianca="alta")
    ext = _ext(q13)
    rel = politica.aplicar(ext, verificador.verificar(ext, None))
    assert q13.veredito == "REPROVADO"
    assert politica.ALERTA_NAO_LOCALIZADO not in q13.alertas
    assert (rel.aprovadas, rel.revisar, rel.reprovadas) == (0, 0, 1)


def test_aplicar_duas_vezes_nao_dobra_o_motivo():
    ext = _ext(_nl("Q16"))
    rel = politica.aplicar(ext, verificador.verificar(ext, None))
    rel = politica.aplicar(ext, rel)
    assert ext.por_id("Q16").alertas.count(politica.ALERTA_NAO_LOCALIZADO) == 1
    assert (rel.aprovadas, rel.revisar) == (0, 1)
