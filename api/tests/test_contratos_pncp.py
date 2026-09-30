# -*- coding: utf-8 -*-
"""
Os contratos da folha (db/049, api/contratos_pncp.py) contra um Postgres efêmero, com o PNCP FALSO (URL → resposta):
nenhuma rede, nenhum custo.

Prova: a busca pagina até a página curta e deduplica entre termos; o detalhe vira as colunas do analytics (valores,
parcelas, assinatura, vigência, compra de origem, banco) com o payload inteiro guardado; os aditivos gravam e o 204
dos /termos é "nenhum"; o escopo sai da mesma regra das licitações (o banco da folha dentro, o sistema de RH fora); a
segunda rodada só desce no que mudou (e `forcar` em todos); e a falha de um contrato não derruba a rodada.
"""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from api import contratos_pncp as cp  # noqa: E402
from fopa import pncp  # noqa: E402
from tests import pg_efemero  # noqa: E402

FOLHA = "04092706000181-2-000127/2025"       # Vilhena/RO × CAIXA, R$ 4,7 mi até 11/06/2030 (o contrato real)
SISTEMA = "31692289000180-2-000002/2023"     # o sistema de RH que a busca por "folha de pagamento" também traz
SUMIU = "12345678000199-2-000009/2026"
TERMO = "folha de pagamento instituição bancária"

OBJ_FOLHA = ("Contratação de INSTITUIÇÃO FINANCEIRA pública ou privada, autorizada pelo Banco Central, para prestação "
             "de serviço de operacionalização de pagamento da folha de salário dos servidores ativos do Município de "
             "Vilhena-RO")
OBJ_SISTEMA = ("Contratação de empresa para cessão de licença de uso de software e prestação de serviços técnicos de "
               "manutenção e suporte técnico do sistema integrado de gestão da folha pagamento do FUMPREV.")


def _contrato(controle, objeto=OBJ_FOLHA, **extra):
    cnpj, _, _ = cp.partes(controle)
    d = {"numeroControlePNCP": controle, "numeroControlePncpCompra": "%s-1-000339/2024" % cnpj,
         "orgaoEntidade": {"cnpj": cnpj, "razaoSocial": "MUNICIPIO DE VILHENA"},
         "unidadeOrgao": {"ufSigla": "RO", "municipioNome": "Vilhena"},
         "niFornecedor": "00360305182547", "nomeRazaoSocialFornecedor": "CAIXA ECONOMICA FEDERAL",
         "objetoContrato": objeto, "tipoContrato": {"id": 1, "nome": "Contrato (termo inicial)"},
         "valorInicial": 4700000.0, "valorGlobal": 4700000.0, "valorAcumulado": 4700000.0,
         "valorParcela": 4700000.0, "numeroParcelas": 1, "receita": False, "dataAssinatura": "2025-06-12",
         "dataVigenciaInicio": "2025-06-12", "dataVigenciaFim": "2030-06-11",
         "dataPublicacaoPncp": "2025-07-07T09:09:53", "dataAtualizacao": "2025-07-07T09:10:15",
         "dataAtualizacaoGlobal": "2025-07-07T09:10:15", "campoQueNinguemUsa": "guardado"}
    d.update(extra)
    return d


def _achado(controle, carimbo="2025-07-07T09:10:15.035098042"):
    return {"numero_controle_pncp": controle, "data_atualizacao_pncp": carimbo}


ADITIVO = {"sequencialTermoContrato": 1, "tipoTermoContratoNome": "Termo Aditivo", "valorAcrescido": 70.39,
           "valorGlobal": 22890.5999, "prazoAditadoDias": 365, "dataAssinatura": "2024-06-19",
           "dataVigenciaFim": "2025-06-29", "objetoTermoContrato": "Prorrogação de prazo + reajuste de 3,69% (IPCA)"}


class PncpFalso:
    """A busca por (termo, página); detalhe e /termos por URL. `None` nos /termos é o 204 do PNCP."""

    def __init__(self, paginas, contratos, aditivos):
        self.paginas, self.contratos, self.aditivos, self.chamadas = paginas, contratos, aditivos, []

    def __call__(self, url, timeout=None, vazio_ok=False):
        self.chamadas.append(url)
        if url.startswith(pncp.BASE_BUSCA):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            assert q["tipos_documento"] == ["contrato"]
            r = self.paginas.get((q["q"][0], int(q["pagina"][0])), {"total": 0, "items": []})
            if isinstance(r, Exception):
                raise r
            return r
        for c, d in self.contratos.items():
            if url == cp.url_contrato(c):
                return d
            if url == cp.url_contrato(c) + "/termos":
                r = self.aditivos.get(c)
                if r is None and not vazio_ok:
                    raise pncp.ErroPNCP("204 sem vazio_ok: %s" % url)
                return r
        raise pncp.ErroPNCP("falhou após 3 tentativas: %s — HTTP Error 404" % url)

    def detalhes(self):
        return [u for u in self.chamadas if "/contratos/" in u and not u.endswith("/termos")]


@pytest.fixture(scope="module")
def url():
    with pg_efemero.subir() as u:
        pg_efemero.migrar(u)
        yield u


@pytest.fixture
def conn(url):
    with psycopg.connect(url, row_factory=dict_row) as c:
        c.execute("TRUNCATE pncp_contrato_termos, pncp_contratos")
        c.execute("UPDATE termos SET ativo = false")
        c.execute("INSERT INTO termos (termo, ativo) VALUES (%s, true) ON CONFLICT (termo) DO UPDATE SET ativo = true",
                  (TERMO,))
        c.commit()
        yield c


def test_busca_pagina_ate_a_pagina_curta_e_deduplica_entre_termos(monkeypatch):
    monkeypatch.setattr(cp, "TAMANHO_BUSCA", 2)
    x, y, z = FOLHA, SISTEMA, SUMIU
    get = PncpFalso({("a", 1): {"total": 3, "items": [_achado(x), _achado(y)]},
                     ("a", 2): {"total": 3, "items": [_achado(z)]},
                     ("b", 1): {"total": 1, "items": [_achado(x), {"numero_controle_pncp": "lixo"}]}}, {}, {})
    achados, por_termo = cp.buscar(["a", "b"], get=get)
    assert set(achados) == {x, y, z}
    assert achados[x]["termo"] == "a"                                   # quem achou primeiro
    assert achados[x]["carimbo"].isoformat() == "2025-07-07T09:10:15-03:00"   # nanossegundos fora, hora de Brasília
    assert por_termo == {"a": {"total": 3, "lidos": 3}, "b": {"total": 1, "lidos": 2}}
    assert not any("pagina=3" in u for u in get.chamadas)              # página curta encerra o termo


def test_contrato_vira_colunas_com_payload_aditivos_e_escopo(conn, url):
    get = PncpFalso({(TERMO, 1): {"total": 2, "items": [_achado(FOLHA), _achado(SISTEMA)]}},
                    {FOLHA: _contrato(FOLHA), SISTEMA: _contrato(SISTEMA, OBJ_SISTEMA)},
                    {FOLHA: None, SISTEMA: [ADITIVO, dict(ADITIVO, sequencialTermoContrato=2, valorAcrescido=0)]})
    r = cp.coletar(url, get=get)
    assert (r["contratos_achados"], r["contratos_lidos"], r["contratos_novos"], r["contratos_falhas"]) == (2, 2, 2, 0)
    assert r["aditivos_lidos"] == 2 and r["busca"] == {TERMO: {"total": 2, "lidos": 2}}

    c = conn.execute("SELECT * FROM pncp_contratos WHERE controle = %s", (FOLHA,)).fetchone()
    assert c["controle_compra"] == "04092706000181-1-000339/2024"
    assert (c["orgao_cnpj"], c["uf"], c["municipio"]) == ("04092706000181", "RO", "Vilhena")
    assert (c["ni_fornecedor"], c["fornecedor"], c["tipo"]) == ("00360305182547", "CAIXA ECONOMICA FEDERAL",
                                                                "Contrato (termo inicial)")
    assert [float(c[k]) for k in ("valor_inicial", "valor_global", "valor_acumulado", "valor_parcela")] == [4700000.0] * 4
    assert (c["parcelas"], c["receita"]) == (1, False)
    assert [c[k].isoformat() for k in ("assinado_em", "vigencia_inicio", "vigencia_fim")] == [
        "2025-06-12", "2025-06-12", "2030-06-11"]
    assert c["atualizado_pncp"].isoformat() == "2025-07-07T12:10:15+00:00"   # 09:10:15 em Brasília
    assert c["payload"]["campoQueNinguemUsa"] == "guardado" and c["termo_busca"] == TERMO
    # a mesma regra das licitações: o banco da folha dentro, o sistema de RH fora
    assert c["escopo_dentro"] is True
    s = conn.execute("SELECT escopo_dentro, escopo_motivo FROM pncp_contratos WHERE controle = %s", (SISTEMA,)).fetchone()
    assert s["escopo_dentro"] is False and "sistema" in s["escopo_motivo"]

    assert conn.execute("SELECT count(*) AS n FROM pncp_contrato_termos WHERE controle_contrato = %s",
                        (FOLHA,)).fetchone()["n"] == 0                      # 204 = nenhum aditivo
    t = conn.execute("SELECT * FROM pncp_contrato_termos WHERE controle_contrato = %s AND sequencial = 1",
                     (SISTEMA,)).fetchone()
    assert (t["tipo"], float(t["valor_acrescido"]), t["prazo_aditado_dias"]) == ("Termo Aditivo", 70.39, 365)
    assert (t["assinado_em"].isoformat(), t["vigencia_fim"].isoformat()) == ("2024-06-19", "2025-06-29")


def test_segunda_rodada_so_desce_no_que_mudou_e_forcar_rele_todos(conn, url):
    contratos = {FOLHA: _contrato(FOLHA), SISTEMA: _contrato(SISTEMA, OBJ_SISTEMA)}
    busca = {(TERMO, 1): {"total": 2, "items": [_achado(FOLHA), _achado(SISTEMA)]}}
    cp.coletar(url, get=PncpFalso(busca, contratos, {}))

    mesma = PncpFalso(busca, contratos, {})
    r = cp.coletar(url, get=mesma)
    assert (r["contratos_achados"], r["contratos_lidos"], r["contratos_novos"]) == (2, 0, 0)
    assert mesma.detalhes() == []                                      # carimbo igual: nem pede o detalhe

    # o PNCP mexeu no contrato de Vilhena (aditivo novo): só ele desce
    contratos[FOLHA] = _contrato(FOLHA, valorAcumulado=5000000.0, dataAtualizacaoGlobal="2026-09-20T10:00:00")
    mudou = PncpFalso({(TERMO, 1): {"total": 2, "items": [_achado(FOLHA, "2026-09-20T10:00:00.5"),
                                                          _achado(SISTEMA)]}}, contratos, {})
    r = cp.coletar(url, get=mudou)
    assert r["contratos_lidos"] == 1 and mudou.detalhes() == [cp.url_contrato(FOLHA)]
    assert float(conn.execute("SELECT valor_acumulado FROM pncp_contratos WHERE controle = %s",
                              (FOLHA,)).fetchone()["valor_acumulado"]) == 5000000.0

    todos = PncpFalso(busca, contratos, {})
    assert cp.coletar(url, get=todos, forcar=True)["contratos_lidos"] == 2 and len(todos.detalhes()) == 2


def test_falha_num_contrato_nao_derruba_a_rodada(conn, url):
    get = PncpFalso({(TERMO, 1): {"total": 2, "items": [_achado(SUMIU), _achado(FOLHA)]}},
                    {FOLHA: _contrato(FOLHA)}, {})
    r = cp.coletar(url, get=get)
    assert (r["contratos_lidos"], r["contratos_falhas"]) == (1, 1)
    assert SUMIU in r["erros_contratos"][0] and "404" in r["erros_contratos"][0]
    assert [x["controle"] for x in conn.execute("SELECT controle FROM pncp_contratos").fetchall()] == [FOLHA]


def test_busca_que_cai_no_meio_segue_com_o_que_leu_e_a_rodada_fica_cega(conn, url, monkeypatch):
    monkeypatch.setattr(cp, "TAMANHO_BUSCA", 1)
    # página 1 responde, a 2 cai (o PNCP derruba a conexão): o contrato da página 1 é lido mesmo assim
    get = PncpFalso({(TERMO, 1): {"total": 5, "items": [_achado(FOLHA)]},
                     (TERMO, 2): pncp.ErroPNCP("falhou após 3 tentativas: RemoteDisconnected")},
                    {FOLHA: _contrato(FOLHA)}, {})
    r = cp.coletar(url, get=get)
    assert r["contratos_lidos"] == 1 and r["cego"] is True
    assert r["busca"][TERMO]["lidos"] == 1 and "página 2" in r["busca"][TERMO]["erro"]


def test_controle_de_contrato_fora_do_formato():
    with pytest.raises(ValueError):
        cp.partes("04092706000181-1-000339/2024")                      # isto é compra (-1-), não contrato (-2-)
    assert cp.url_contrato(FOLHA) == pncp.BASE_PNCP + "/orgaos/04092706000181/contratos/2025/127"
