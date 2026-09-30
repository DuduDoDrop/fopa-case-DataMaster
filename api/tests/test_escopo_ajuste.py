# -*- coding: utf-8 -*-
"""
A camada de ajuste do escopo (api/escopo_ajuste.py) com os textos REAIS do acervo medidos em
scripts/80_escopo_ajuste.py (25/09/2026): o que tem de sair, o que NUNCA pode sair e a versão que muda com ela.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from api import escopo_ajuste as ajuste, versao  # noqa: E402


# Folha de verdade (publicadas no acervo ou folha pelo texto) que tocam palavras das exclusões. A 1ª versão da camada
# tiraria as quatro primeiras: "estagiários" no meio dos servidores, "sem cobrança de tarifa", "cessão onerosa" sem
# citar banco, "centralização" de serviços bancários.
FOLHA = [
    "Cessão onerosa do direito de efetuar, com exclusividade, o pagamento da folha dos servidores públicos (estagiários, "
    "cargos em comissão, efetivos)",
    "Contratação de Instituição Financeira, para centralizar e processar, sem a incidência de cobrança de tarifa bancária "
    "pelo respectivo serviço, os créditos da folha de pagamento",
    "[Portal de Compras Públicas] - CESSÃO ONEROSA DO DIREITO DE REALIZAR, COM EXCLUSIVIDADE, O PAGAMENTO DA FOLHA DOS "
    "SERVIDORES PÚBLICOS",
    "CONTRATAÇÃO DE INSTITUIÇÃO FINANCEIRA AUTORIZADA PELO BANCO CENTRAL DO BRASIL PARA A PRESTAÇÃO DE SERVIÇOS DE "
    "CENTRALIZAÇÃO E PROCESSAMENTO DOS CRÉDITOS PROVENIENTES DA FOLHA DE PAGAMENTO",
    "OBJETO: contratação de instituição financeira, pública ou privada, para processamento e gerenciamento de créditos "
    "provenientes da folha de pagamento dos servidores",
    "Credenciamento do Banco Bradesco S.A. para: a) atuar como consignatária facultativa, via descontos em folha de "
    "pagamento (ITEM 1); e/ou b) prestar serviço de pagamento de salários",
    "Contratação e formalização de Convênio com a Caixa Econômica Federal, sem custo para a Câmara Municipal da Lapa, "
    "cujo objeto é o gerenciamento e disponibilização de sistema de folha de pagamento dos servidores.",
    "Contratação de serviços bancários, através de convênios de pagamento de folha dos servidores do SAAE",
    "Prestação de serviço de pagamento de folha salarial dos servidores ativos, inativos, pensionistas e estagiários",
]

# Fora, com o nome da exclusão que tem de valer (textos do acervo; rótulo humano "fora" ou Jev <= 0,25).
FORA = [
    ("DESPESAS COM TARIFAS BANCÁRIAS PELO RECEBIMENTO DE GUIAS, MANUTENÇÃO DE CONTAS E EXECUÇÃO DE FOLHA DE PAGAMENTO "
     "DE SERVIDORES", "tarifa paga pelo órgão"),
    ("[Portal de Compras Públicas] - Despesas com tarifas bancárias de janeiro a dezembro de 2025, junto ao Banco do "
     "Brasil, referente à manutenção da Conta", "tarifa paga pelo órgão"),
    ("Contratação de instituição financeira pública para valores em disponibilidade e demais serviços, exceto folha de "
     "pagamento", "exceto folha"),
    ("Firmar Parceria, por meio de Termo de Fomento (art. 2º, VII c/c art. 17 da Lei 13.019/2014) com a Associação de "
     "Pais e Amigos dos Excepcionais, objetivando pagamento da folha mensal", "termo de fomento ou parceria"),
    ("Locação de imóvel, localizado na Rua Antônio Rosa e Silva, 159, destinado ao funcionamento da secretaria, "
     "centralização das folhas de pagamento", "locação de imóvel"),
    ("Contratação de uma entidade sem fins lucrativos, especializada em formação técnico profissional sistemática, para "
     "fornecer serviços de recrutamento, seleção, contratação, pagamento da folha de pagamento e acompanhamento de "
     "jovens", "recrutamento ou temporários"),
    ("“CONTRATAÇÃO DE SERVIÇOS DE RECUPERAÇÃO DE IMPOSTO DEVIDO POR INSTITUIÇÃO FINANCEIRA E PRESTADORES DE SERVIÇOS",
     "recuperação de imposto"),
    ("Contratação de serviços especializados de Estudo Técnico de Viabilidade Econômico-financeira, para estimar o "
     "melhor valor a ser pago pelos serviços relativos à folha por instituição financeira", "estudo técnico sobre a folha"),
    ("LICENCIAMENTO DE USO E MANUTENÇÃO E SUPORTE DOS SISTEMAS DE PROCESSAMENTO DE FOLHA DE PAGAMENTO",
     "sistema ou TI de folha"),
    ("CONTRATAÇÃO DOS SERVIÇOS DE LOCAÇÃO E MANUTENÇÃO DE SISTEMA DE FOLHA DE PAGAMENTO E GERAÇÃO DA RAIZ E GFIP",
     "sistema ou TI de folha"),
    ("Contratação de empresa especializada para prestação de serviços de processamento da folha de pagamentos da "
     "Companhia Docas de São Sebastião", "serviço de RH ou contábil"),
    ("CONTRATAÇÃO DE SERVIÇOS TÉCNICOS ESPECIALIZADOS NO PROCESSAMENTO DA FOLHA DE PAGAMENTO, ELABORAÇÃO DA GFIP, GPS, "
     "DIRF, RAIS, ACOMPANHAMENTO NOS PARCELAMENTOS, CERTIDÕES FEDERAIS E CAIXA ECONÔMICA", "serviço de RH ou contábil"),
    ("Credenciamento de pessoas jurídicas para a concessão onerosa do canal de consignações em folha de pagamento dos "
     "servidores públicos municipais", "só o canal de consignações"),
    ("3 Inscrições para participação no Encontro Nacional de Gestão de Folha de Pagamento para RPPS",
     "evento ou curso sobre folha"),
    ("Aquisicao de telefone para uso na Folha de Pagamento devido a recente separacao da folha", "compra de bens"),
    ("EMPENHO PARA PAGAMENTO DE MANUTENÇÃO DE TELHADO COM TROCA DE FOLHAS DE BRASILIT", "obra ou manutenção predial"),
]


@pytest.mark.parametrize("texto", FOLHA)
def test_folha_nunca_sai(texto):
    assert ajuste.excluir(texto) is None, texto
    assert ajuste.ajustar(texto, True, "regra: folha") == (True, "regra: folha")


@pytest.mark.parametrize("texto,nome", FORA)
def test_sai_com_o_nome_da_exclusao(texto, nome):
    assert ajuste.excluir(texto) == nome
    dentro, motivo = ajuste.ajustar(texto, True, "regra: folha")
    assert dentro is False and nome in motivo and ajuste.VERSAO in motivo and "regra: folha" in motivo


def test_so_tira_nunca_poe():
    texto = FORA[0][0]
    assert ajuste.ajustar(texto, False, "regra: fora") == (False, "regra: fora")
    assert ajuste.ajustar("Cessão onerosa da folha de pagamento", False, "regra: fora") == (False, "regra: fora")


def test_avaliar_e_a_regra_mais_o_ajuste():
    # o que os quatro lugares da regra chamam (worker /escopo, reavaliação, descoberta histórica, Jev)
    assert ajuste.avaliar(FORA[8][0])[0] is False
    assert ajuste.avaliar("Cessão onerosa do direito de processar a folha de pagamento dos servidores")[0] is True


def test_a_versao_do_escopo_muda_com_a_camada(monkeypatch):
    antes = versao.escopo_versao()
    original = versao._ler

    def lido(caminho):
        conteudo = original(caminho)
        return conteudo + b"\n# mudou" if caminho.endswith("escopo_ajuste.py") else conteudo

    monkeypatch.setattr(versao, "_ler", lido)
    assert versao.escopo_versao() != antes
