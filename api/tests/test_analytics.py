# -*- coding: utf-8 -*-
"""
Analytics do histórico de compra e venda: quem comprou cada folha, por
quanto e quando, e o que foi a deserto e está sendo publicado de novo.

Postgres efêmero com um cenário pequeno escrito à mão:
  · Banco do Brasil compra 2 (uma com dois itens, somados), Caixa compra 1 com duas filiais do mesmo
    CNPJ-raiz (é UM banco), e um resultado cancelado (homologação desfeita) não conta como compra;
  · uma prefeitura publica, vai a deserto, publica de novo (cadastrada em DUPLICIDADE no mesmo dia,
    o caso de Bento Gonçalves — conta como UMA tentativa), vai a deserto e publica a 3ª vez;
  · uma compra fora do escopo (consignado) só entra com escopo=todos.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from api import analytics  # noqa: E402
from tests import pg_efemero  # noqa: E402

BB, CAIXA1, CAIXA2 = "00000000000191", "00360305000104", "00360305123456"
A1, A2, A3 = "11111111000101-1-000001/2026", "11111111000101-1-000002/2026", "22222222000101-1-000010/2026"
CANCELADA = "33333333000101-1-000005/2026"
T1, T2, T2DUP, T3 = ("44444444000101-1-000650/2025", "44444444000101-1-000738/2025",
                     "44444444000101-1-000739/2025", "44444444000101-1-000317/2026")
FORA = "55555555000101-1-000077/2026"
SEMCAB = "66666666000101-1-000042/2026"


def _lic(c, controle, dentro=True):
    c.execute("INSERT INTO licitacoes (controle, orgao, uf, municipio, modalidade, objeto, publicado_em,"
              " escopo_dentro, escopo_motivo, estado, origem)"
              " VALUES (%s, 'órgão', 'RS', 'Cidade', 'Pregão', 'folha', '2026-01-01', %s, 'teste', %s, 'manual')",
              (controle, dentro, "nova" if dentro else "fora_escopo"))


def _compra(c, controle, publicado, valor, municipio="Cidade", uf="RS", situacao="Divulgada no PNCP", orgao=None):
    cnpj = orgao or controle[:14]
    c.execute("INSERT INTO pncp_compras (controle, payload, orgao_cnpj, orgao, uf, municipio, modalidade, objeto,"
              " valor_estimado, situacao, publicado_em) VALUES (%s, %s, %s, %s, %s, %s, 'Pregão', 'folha', %s, %s, %s)",
              (controle, Jsonb({}), cnpj, "Prefeitura de " + municipio, uf, municipio, valor, situacao, publicado))
    c.execute("INSERT INTO pncp_coletas (controle, ok) VALUES (%s, true)", (controle,))


def _item(c, controle, n, situacao, valor=100.0, tem=False):
    c.execute("INSERT INTO pncp_itens (controle, numero_item, payload, situacao, valor_total, tem_resultado)"
              " VALUES (%s, %s, %s, %s, %s, %s)", (controle, n, Jsonb({}), situacao, valor, tem))


def _res(c, controle, n, ni, nome, valor, dia, cancelado=None):
    c.execute("INSERT INTO pncp_resultados (controle, numero_item, sequencial, payload, ni_fornecedor, fornecedor,"
              " natureza_juridica, valor_homologado, data_resultado, cancelado_em)"
              " VALUES (%s, %s, 1, %s, %s, %s, 'Sociedade de Economia Mista', %s, %s, %s)",
              (controle, n, Jsonb({}), ni, nome, valor, dia, cancelado))


@pytest.fixture(scope="module")
def url():
    with pg_efemero.subir() as u:
        pg_efemero.migrar(u)
        with psycopg.connect(u) as c:
            for x in (A1, A2, A3, CANCELADA, T1, T2, T2DUP, T3):
                _lic(c, x)
            _lic(c, FORA, dentro=False)
            # Banco do Brasil: A1 (dois itens, somados) em março, A2 em maio
            _compra(c, A1, "2026-02-10T10:00:00-03:00", 900000)
            _item(c, A1, 1, "Homologado", tem=True)
            _item(c, A1, 2, "Homologado", tem=True)
            _res(c, A1, 1, BB, "BANCO DO BRASIL SA", 600000, date(2026, 3, 5))
            _res(c, A1, 2, BB, "BANCO DO BRASIL S.A.", 400000, date(2026, 3, 5))
            _compra(c, A2, "2026-04-01T10:00:00-03:00", 500000)
            _item(c, A2, 1, "Homologado", tem=True)
            _res(c, A2, 1, BB, "BANCO DO BRASIL SA", 550000, date(2026, 5, 20))
            # Caixa: duas filiais do mesmo CNPJ-raiz = um banco
            _compra(c, A3, "2026-03-01T10:00:00-03:00", 300000, municipio="Outra")
            _item(c, A3, 1, "Homologado", tem=True)
            _res(c, A3, 1, CAIXA1, "CAIXA ECONOMICA FEDERAL", 250000, date(2026, 3, 30))
            c.execute("UPDATE pncp_resultados SET ni_fornecedor = %s WHERE controle = %s", (CAIXA2, A3))
            # homologação desfeita: não é compra
            _compra(c, CANCELADA, "2026-03-15T10:00:00-03:00", 100000, municipio="Triunfo")
            _item(c, CANCELADA, 1, "Homologado", tem=True)
            _res(c, CANCELADA, 1, BB, "BANCO DO BRASIL SA", 100000, date(2026, 4, 1), cancelado="2026-05-10T00:00:00-03:00")
            # a prefeitura que não acha comprador: deserto → (duplicado) deserto → 3ª publicação em aberto
            _compra(c, T1, "2025-11-10T08:00:00-03:00", 8805657.81, municipio="Bento")
            _item(c, T1, 1, "Deserto")
            _compra(c, T2, "2026-01-06T08:00:00-03:00", 8858147.76, municipio="Bento")
            _item(c, T2, 1, "Em andamento")
            _compra(c, T2DUP, "2026-01-06T08:30:00-03:00", 8858147.76, municipio="Bento")
            _item(c, T2DUP, 1, "Deserto")
            _compra(c, T3, "2026-05-13T08:00:00-03:00", 9058141.48, municipio="Bento")
            _item(c, T3, 1, "Em andamento")
            # fora do escopo: consignado comprado pelo Bradesco
            _compra(c, FORA, "2026-06-01T10:00:00-03:00", 50000, municipio="Longe")
            _item(c, FORA, 1, "Homologado", tem=True)
            _res(c, FORA, 1, "60746948000112", "BANCO BRADESCO S.A.", 70000, date(2026, 6, 15))
        yield u


def _dados(url, **kw):
    with psycopg.connect(url) as conn:
        return analytics.montar(conn, **kw)


def test_ranking_de_bancos_por_cnpj_raiz_sem_cancelado(url):
    d = _dados(url)
    bancos = {b["banco"]: b for b in d["bancos"]}
    assert set(bancos) == {"BANCO DO BRASIL SA", "CAIXA ECONOMICA FEDERAL"}
    bb = bancos["BANCO DO BRASIL SA"]
    assert (bb["licitacoes"], bb["valor_total"]) == (2, 1550000.0)          # A1 (2 itens somados) + A2; não a cancelada
    assert bb["ticket_medio"] == pytest.approx(775000.0)
    assert bb["cnpj_raiz"] == "00000000"
    cx = bancos["CAIXA ECONOMICA FEDERAL"]
    assert (cx["licitacoes"], cx["valor_total"]) == (1, 250000.0)            # duas filiais, um banco
    assert d["bancos"][0]["banco"] == "BANCO DO BRASIL SA"                    # ordenado por licitações compradas
    assert sum(b["participacao"] for b in d["bancos"]) == pytest.approx(1.0)


def test_serie_mensal_por_banco(url):
    d = _dados(url)
    meses = d["mensal"]["meses"]
    assert meses == ["2026-03", "2026-04", "2026-05"]                        # do primeiro ao último resultado, sem buraco
    series = {s["banco"]: s for s in d["mensal"]["series"]}
    assert series["BANCO DO BRASIL SA"]["licitacoes"] == [1, 0, 1]
    assert series["BANCO DO BRASIL SA"]["valor"] == [1000000.0, 0.0, 550000.0]
    assert series["CAIXA ECONOMICA FEDERAL"]["licitacoes"] == [1, 0, 0]


def test_republicadas_contam_tentativas_e_juntam_cadastro_duplicado(url):
    d = _dados(url)
    cadeias = d["republicadas"]
    assert len(cadeias) == 1
    k = cadeias[0]
    assert k["municipio"] == "Bento" and k["tentativas"] == 3                # T2 e T2DUP: a mesma tentativa
    assert [t["resultado"] for t in k["historico"]] == ["deserta", "deserta", "aberta"]
    assert k["historico"][1]["controles"] == sorted([T2, T2DUP])
    assert k["situacao_atual"] == "aberta" and k["sem_comprador"] is True
    assert [t["publicacao"] for t in k["historico"]] == [1, 2, 3]


def test_resumo_e_filtros_de_escopo_e_ano(url):
    d = _dados(url)
    r = d["resumo"]
    assert (r["compras"], r["com_vencedor"], r["bancos"]) == (8, 3, 2)
    assert r["valor_homologado"] == pytest.approx(1800000.0)
    assert (r["desertas"], r["republicadas"]) == (2, 1)
    assert d["filtro"] == {"escopo": "dentro", "ano": None, "de": None, "ate": None, "so_fopa_ia": False}

    todos = _dados(url, escopo="todos")
    assert "BANCO BRADESCO S.A." in {b["banco"] for b in todos["bancos"]}
    assert todos["resumo"]["compras"] == 9

    # o ano é o da PUBLICAÇÃO (a régua do gráfico mensal): 738/2025 saiu em 06/01/2026, como em Bento Gonçalves
    so_2025 = _dados(url, ano=2025)
    assert so_2025["resumo"]["compras"] == 1 and so_2025["bancos"] == []


def test_filtro_de_datas_pela_publicacao_com_as_pontas_inclusas(url):
    # O filtro de data da página: a régua é a data de PUBLICAÇÃO (a mesma do
    # ano), no fuso de Brasília, e as duas pontas entram: de 01/02 a 01/03 pega A1 (10/02) e A3 (01/03).
    d = _dados(url, de=date(2026, 2, 1), ate=date(2026, 3, 1))
    assert d["resumo"]["compras"] == 2
    assert d["filtro"] == {"escopo": "dentro", "ano": None, "de": "2026-02-01", "ate": "2026-03-01", "so_fopa_ia": False}
    # só uma das pontas também vale
    assert _dados(url, de=date(2026, 5, 1))["resumo"]["compras"] == 1            # T3 (13/05)
    assert _dados(url, ate=date(2025, 12, 31))["resumo"]["compras"] == 1         # T1 (10/11/2025)


def test_sem_cabecalho_do_pncp_a_licitacao_ainda_conta(url):
    # A API de consulta recusou o cabeçalho (429): a coleta é parcial, mas itens e resultados vieram.
    # Órgão, município e data saem de `licitacoes` (a descoberta); o valor estimado, da soma dos itens.
    with psycopg.connect(url) as conn:
        _lic(conn, SEMCAB)
        _item(conn, SEMCAB, 1, "Homologado", valor=123.0, tem=True)
        _res(conn, SEMCAB, 1, BB, "BANCO DO BRASIL SA", 123.0, date(2026, 5, 2))
        conn.execute("INSERT INTO pncp_coletas (controle, ok, erro) VALUES (%s, true, 'cabeçalho indisponível: 429')", (SEMCAB,))
        d = analytics.montar(conn)
        conn.rollback()
    assert d["resumo"]["compras"] == 9 and d["resumo"]["com_vencedor"] == 4
    assert {b["banco"]: b["licitacoes"] for b in d["bancos"]}["BANCO DO BRASIL SA"] == 3
    assert d["resumo"]["valor_estimado"] == pytest.approx(_dados(url)["resumo"]["valor_estimado"] + 123.0)


def test_data_absurda_do_pncp_nao_estica_o_grafico(url):
    # 24/09 noite: um resultado do PNCP veio com data_resultado no ANO 255 ("0255-02", digitação na origem). O
    # gráfico mensal ia do ano 255 a 2026 — 21.260 meses, 1,7 MB de JSON — e a página ficava em branco. Data fora
    # do plausível (antes de 2020 ou mais de um ano à frente) não vira mês nem "primeira compra"; o total conta.
    with psycopg.connect(url) as conn:
        _res(conn, A1, 9, BB, "BANCO DO BRASIL SA", 1.0, date(255, 2, 10))
        d = analytics.montar(conn)
        conn.rollback()
    assert d["mensal"]["meses"][0] >= "2020-01" and len(d["mensal"]["meses"]) < 120
    bb = next(b for b in d["bancos"] if b["cnpj_raiz"] == BB[:8])
    assert bb["primeira"] >= "2020-01-01"


def test_so_instituicao_financeira_conta_como_banco(url):
    # Com o histórico inteiro, "Bancos que compraram" trazia a PRODESP (processamento de dados) e um tribunal
    # (dado estranho do PNCP). O ranking marca quem é instituição financeira pelo nome (banco, caixa, cooperativa
    # de crédito, sociedade de crédito, instituição de pagamento); o resto continua lá, marcado, e não conta
    # como "banco comprador" nem ganha linha própria no gráfico.
    with psycopg.connect(url) as conn:
        _res(conn, A2, 9, "62577929000135", "COMPANHIA DE PROCESSAMENTO DE DADOS DO ESTADO DE SAO PAULO - PRODESP",
             10.0, date(2026, 4, 20))
        d = analytics.montar(conn)
        conn.rollback()
    por_raiz = {b["cnpj_raiz"]: b for b in d["bancos"]}
    assert por_raiz["62577929"]["financeira"] is False
    assert por_raiz[BB[:8]]["financeira"] is True
    assert d["resumo"]["bancos"] == 2 and d["resumo"]["fornecedores"] == 3
    assert all(s["cnpj_raiz"] != "62577929" for s in d["mensal"]["series"])


@pytest.mark.parametrize("nome,financeira", [
    ("BANCO DO BRASIL SA", True), ("CAIXA ECONOMICA FEDERAL", True), ("ITAU UNIBANCO S.A.", True),
    ("COOPERATIVA DE CREDITO DA REGIAO CENTRAL - SICOOB UNIAO CENTRAL", True),
    ("COOP. DE CREDITO E INVESTIMENTO COM INTERAÇÃO SOLIDÁRIA - VANGUARDA CRESOL VANGUARDA", True),
    ("DELTA GLOBAL SOCIEDADE DE CREDITO DIRETO S A", True), ("MENTORE INSTITUICAO DE PAGAMENTO S/A", True),
    ("TRIBUNAL REGIONAL DO TRABALHO DA 4 REGIAO", False), ("IPM SISTEMAS LTDA", False),
    ("COMPANHIA DE PROCESSAMENTO DE DADOS DO ESTADO DE SAO PAULO - PRODESP", False),
])
def test_quem_e_instituicao_financeira(nome, financeira):
    assert analytics.financeira(nome) is financeira


def test_rotulo_humano_fora_sai_do_escopo_do_analytics(url):
    # O rótulo humano mais recente prevalece também aqui; com "mostrar fora do escopo" a licitação volta.
    with psycopg.connect(url) as conn:
        conn.execute("INSERT INTO rotulos_escopo (controle, veredito, por_que, por) VALUES (%s, 'fora', 't', 't')", (A1,))
        dentro = analytics.montar(conn)
        todos = analytics.montar(conn, escopo="todos")
        conn.rollback()
    assert dentro["resumo"]["compras"] == 7 and todos["resumo"]["compras"] == 9


def test_apenas_fopa_esconde_o_que_a_ia_acha_que_nao_e(url):
    # O filtro "apenas FOPA (a IA confirma)" do analytics: nota da IA < 0,5 sai; sem nota, fica.
    with psycopg.connect(url) as conn:
        conn.execute("INSERT INTO sinais_jev (tipo, controle, criterio_versao, regra, resposta, p_sim, contexto_enviado,"
                     " candidata) VALUES ('escopo', %s, 'escopo-v3', 'dentro', 'nao', 0.3, 'objeto', false)", (A1,))
        todos = analytics.montar(conn)
        fopa = analytics.montar(conn, so_fopa_ia=True)
        conn.rollback()
    assert (todos["resumo"]["compras"], fopa["resumo"]["compras"]) == (8, 7)
    assert fopa["filtro"]["so_fopa_ia"] is True and todos["filtro"]["so_fopa_ia"] is False


def test_compras_por_banco_lista_do_filtro_e_o_que_o_banco_comprou(url):
    # O filtro pesquisável das instituições financeiras e, embaixo, o que a escolhida comprou.
    with psycopg.connect(url) as conn:
        d = analytics.compras_por_banco(conn)
    nomes = {b["banco"] for b in d["bancos"]}
    assert {"BANCO DO BRASIL SA", "CAIXA ECONOMICA FEDERAL"} <= nomes
    assert "BANCO BRADESCO S.A." not in nomes                  # o consignado fora do escopo não entra
    assert d["banco"] is None and d["compras"] == [] and d["total"] == {"licitacoes": 0, "valor": 0.0}

    with psycopg.connect(url) as conn:
        d = analytics.compras_por_banco(conn, banco=BB)
    assert d["banco"] == {"cnpj_raiz": "00000000", "banco": "BANCO DO BRASIL SA"}
    # a mais recente primeiro; os dois itens de A1 somados; a homologação desfeita (Triunfo) não é compra
    assert [(c["controle"], c["valor"], c["comprada_em"], c["rodada"]) for c in d["compras"]] == [
        (A2, 550000.0, "2026-05-20", 1), (A1, 1000000.0, "2026-03-05", 1)]
    assert d["total"] == {"licitacoes": 2, "valor": 1550000.0}
    a1 = d["compras"][1]
    assert (a1["municipio"], a1["uf"], a1["orgao"], a1["contrato"]) == ("Cidade", "RS", "Prefeitura de Cidade", None)

    # o período olha a DATA DA COMPRA, com as duas pontas inclusas
    with psycopg.connect(url) as conn:
        d = analytics.compras_por_banco(conn, banco="00000000", de=date(2026, 3, 5), ate=date(2026, 3, 5))
    assert [c["controle"] for c in d["compras"]] == [A1]


def test_compras_por_banco_diz_a_rodada_da_publicacao_e_o_contrato(url):
    # Bento: deserta (T1), deserta de novo (T2 + o cadastro duplicado T2DUP) e a 3ª publicação (T3) comprada pela
    # Caixa — com o contrato no PNCP (db/049). Tudo numa transação desfeita no fim: o resto do módulo não vê.
    with psycopg.connect(url) as conn:
        _res(conn, T3, 1, CAIXA1, "CAIXA ECONOMICA FEDERAL", 9100000, date(2026, 6, 20))
        conn.execute("INSERT INTO pncp_contratos (controle, controle_compra, payload, ni_fornecedor, valor_global,"
                     " valor_acumulado, assinado_em, vigencia_fim, escopo_dentro) VALUES"
                     " ('44444444000101-2-000001/2026', %s, '{}', %s, 9100000, 9200000, '2026-07-01', '2031-06-30',"
                     " true)", (T3, CAIXA2))
        d = analytics.compras_por_banco(conn, banco=CAIXA1)
        conn.rollback()
    t3 = next(c for c in d["compras"] if c["controle"] == T3)
    assert (t3["rodada"], t3["valor"], t3["comprada_em"], t3["municipio"]) == (3, 9100000.0, "2026-06-20", "Bento")
    assert t3["contrato"] == {"controle": "44444444000101-2-000001/2026", "contratos": 1, "valor": 9200000.0,
                              "assinado_em": "2026-07-01", "vigencia_fim": "2031-06-30"}
    assert next(c for c in d["compras"] if c["controle"] == A3)["rodada"] == 1


def test_compras_por_banco_separa_fopa_do_que_esta_fora_do_escopo(url):
    # O analytics separa FOPA do que está fora do escopo: por
    # padrão só FOPA; com "mostrar fora do escopo" o resto entra, cada linha marcada.
    bradesco = "60746948000112"
    with psycopg.connect(url) as conn:
        assert analytics.compras_por_banco(conn, banco=bradesco, so_fopa_ia=True)["compras"] == []
        d = analytics.compras_por_banco(conn, escopo="todos", banco=bradesco)
        dentro = analytics.compras_por_banco(conn, escopo="todos", banco=BB)
    assert [(c["controle"], c["fopa"]) for c in d["compras"]] == [(FORA, False)]
    assert "BANCO BRADESCO S.A." in {b["banco"] for b in d["bancos"]}
    assert all(c["fopa"] for c in dentro["compras"])
