# -*- coding: utf-8 -*-
"""
A descoberta HISTÓRICA no PNCP (db/030, api/descoberta_historica.py), de 24/09/2026: o Analytics
com todo o histórico possível, sempre dentro do escopo de licitação.

O W01 ignora o que está fora do recorte de 2026 (ADR-015). Aqui se prova que a busca ano a ano registra esse
passado SÓ como histórico (fora_janela no escopo, fora_escopo se a regra recusou; origem 'historico'), que o que
já está no banco não é tocado (nem carimbo, nem retificação), que dentro do recorte o caminho é o mesmo do W01, e
que a busca pagina até a página curta, ano a ano.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from api import descoberta_historica as dh  # noqa: E402
from tests import pg_efemero  # noqa: E402

HOJE = date(2026, 9, 24)


def _item(controle, descricao="Cessão onerosa da folha de pagamento dos servidores municipais",
          publicado="2023-03-10T09:00:00", fim="2023-04-01T09:00:00", **extra):
    cnpj, _, resto = controle.partition("-1-")
    seq, _, ano = resto.partition("/")
    d = {"numero_controle_pncp": controle, "orgao_cnpj": cnpj, "ano": ano, "numero_sequencial": str(int(seq)),
         "orgao_nome": "MUNICIPIO DE TESTE", "uf": "RS", "municipio_nome": "Teste",
         "modalidade_licitacao_nome": "Pregão - Eletrônico", "description": descricao, "title": "Edital nº 1",
         "situacao_nome": "Divulgada no PNCP", "data_publicacao_pncp": publicado, "data_fim_vigencia": fim,
         "data_atualizacao_pncp": publicado}
    d.update(extra)
    return d


@pytest.fixture(scope="module")
def url():
    with pg_efemero.subir() as u:
        pg_efemero.migrar(u)
        yield u


@pytest.fixture
def conn(url):
    with psycopg.connect(url, row_factory=dict_row) as c:
        yield c
        c.rollback()


def test_normalizar_segue_o_w01():
    n = dh.normalizar(_item("11111111000101-1-000007/2023"))
    p = n["payload"]
    assert n["controle"] == "11111111000101-1-000007/2023"
    assert (p["ano"], p["seq"], p["uf"], p["municipio"]) == (2023, 7, "RS", "Teste")
    assert p["objeto"].startswith("Cessão onerosa") and p["fim_prazo"] == "2023-04-01T09:00:00"
    assert p["link"] == "https://pncp.gov.br/app/editais/11111111000101/2023/7"
    assert "Cessão onerosa" in n["texto_escopo"] and "Edital nº 1" in n["texto_escopo"]
    assert dh.normalizar({"numero_controle_pncp": "lixo"}) is None


def test_passado_entra_so_como_historico(conn):
    dentro = dh.normalizar(_item("11111111000101-1-000007/2023"))
    fora = dh.normalizar(_item("11111111000101-1-000008/2023", descricao="Curso de capacitação em folha de pagamento"))
    acoes = dh.registrar(conn, [dentro, fora], hoje=HOJE)
    assert acoes == {"historico": 1, "historico_fora_escopo": 1}
    linhas = {r["controle"]: r for r in conn.execute(
        "SELECT controle, estado::text, origem, escopo_dentro, escopo_versao, publicado_em FROM licitacoes"
        " WHERE controle LIKE '11111111000101-%%'").fetchall()}
    a, b = linhas[dentro["controle"]], linhas[fora["controle"]]
    assert (a["estado"], a["origem"], a["escopo_dentro"]) == ("fora_janela", "historico", True)
    assert (b["estado"], b["origem"], b["escopo_dentro"]) == ("fora_escopo", "historico", False)
    assert a["escopo_versao"] and a["publicado_em"] == date(2023, 3, 10)


def test_o_que_ja_existe_nao_e_tocado(conn):
    c = "22222222000101-1-000001/2024"
    conn.execute("INSERT INTO licitacoes (controle, orgao, uf, municipio, modalidade, objeto, publicado_em,"
                 " escopo_dentro, escopo_motivo, estado, origem, visto_em, atualizado_pncp) VALUES"
                 " (%s, 'o', 'RS', 'T', 'Pregão', 'folha', '2024-01-10', true, 'm', 'publicada', 'legado',"
                 " '2024-02-01', '2024-01-10 09:00')", (c,))
    antes = conn.execute("SELECT * FROM licitacoes WHERE controle = %s", (c,)).fetchone()
    # carimbo NOVO no PNCP: o W01 retificaria; a descoberta histórica não mexe
    novo = dh.normalizar(_item(c, publicado="2024-01-10T09:00:00", data_atualizacao_pncp="2026-09-20T10:00:00"))
    assert dh.registrar(conn, [novo], hoje=HOJE) == {"conhecida": 1}
    assert conn.execute("SELECT * FROM licitacoes WHERE controle = %s", (c,)).fetchone() == antes


def test_dentro_do_recorte_e_o_caminho_do_w01(conn):
    aberta = dh.normalizar(_item("33333333000101-1-000009/2026", publicado="2026-09-01T09:00:00",
                                 fim="2026-10-30T09:00:00"))
    assert dh.registrar(conn, [aberta], hoje=HOJE) == {"inserir_nova": 1}
    estado, origem = conn.execute("SELECT estado::text, origem FROM licitacoes WHERE controle = %s",
                                  (aberta["controle"],)).fetchone().values()
    assert (estado, origem) == ("nova", "n8n")


def test_so_dentro_descarta_o_que_a_regra_recusa(conn):
    # O termo amplo ("folha de pagamento") traz software, curso, consignado: dele só entra o que a regra aceita.
    fora = dh.normalizar(_item("44444444000101-1-000002/2022", descricao="Sistema informatizado de folha de pagamento"))
    assert dh.registrar(conn, [fora], hoje=HOJE, so_dentro=True) == {"descartada_pela_regra": 1}
    assert conn.execute("SELECT count(*) AS n FROM licitacoes WHERE controle = %s",
                        (fora["controle"],)).fetchone()["n"] == 0


def test_busca_ano_a_ano_ate_a_pagina_curta():
    pedidos = []

    def get(url, timeout=None):
        pedidos.append(url)
        pagina = int(url.split("pagina=")[1].split("&")[0])
        n = dh.TAMANHO if pagina == 1 else 3
        return {"total": dh.TAMANHO + 3, "items": [_item("55555555000101-1-%06d/2023" % (pagina * 100 + i))
                                                    for i in range(n)]}

    itens, info = dh.buscar("cessão onerosa folha de pagamento", 2023, get=get)
    assert len(itens) == dh.TAMANHO + 3 and len(pedidos) == 2
    assert all("anos=2023" in u and "status=todos" in u and "tipos_documento=edital" in u for u in pedidos)
    assert (info["total_declarado"], info["lidos"], info["paginas"]) == (dh.TAMANHO + 3, dh.TAMANHO + 3, 2)


def test_pagina_que_falha_insiste_e_se_desistir_leva_o_que_ja_leu():
    # 24/09 noite: 22 consultas (termo, ano) caíram numa página funda e o que já tinha sido lido ia junto.
    from fopa import pncp
    falhas = {"n": 0}

    def get(url, timeout=None):
        pagina = int(url.split("pagina=")[1].split("&")[0])
        if pagina == 2 and falhas["n"] < 2:
            falhas["n"] += 1
            raise pncp.ErroPNCP("falhou após 3 tentativas: timeout")
        n = dh.TAMANHO if pagina == 1 else 3
        return {"total": dh.TAMANHO + 3, "items": [_item("77777777000101-1-%06d/2024" % (pagina * 100 + i))
                                                    for i in range(n)]}

    itens, info = dh.buscar("folha", 2024, get=get, espera=0)
    assert len(itens) == dh.TAMANHO + 3 and falhas["n"] == 2          # insistiu na página 2 e passou

    def get_sempre_cai(url, timeout=None):
        if "pagina=2" in url:
            raise pncp.ErroPNCP("falhou após 3 tentativas: timeout")
        return get(url)

    with pytest.raises(pncp.ErroPNCP) as e:
        dh.buscar("folha", 2024, get=get_sempre_cai, espera=0)
    assert len(e.value.itens) == dh.TAMANHO and e.value.pagina == 2      # o que já leu vai junto


def test_pares_restringe_a_rodada():
    assert dh.pares("folha de pagamento@2024; créditos da folha de pagamento@2021") == {
        ("folha de pagamento", 2024), ("créditos da folha de pagamento", 2021)}
