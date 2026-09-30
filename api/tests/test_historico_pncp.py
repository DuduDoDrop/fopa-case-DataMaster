# -*- coding: utf-8 -*-
"""
O coletor do histórico de compra e venda (db/027, api/historico_pncp.py) contra um Postgres efêmero,
com o PNCP FALSO (dicionário de URL → resposta): nenhuma rede, nenhum custo.

Prova: o payload inteiro de cada resposta é guardado; as colunas do analytics saem certas (valores,
datas em horário de Brasília, situação do item, vencedor); a lista de itens é paginada; resultado que
vem como objeto solto é normalizado; item sem resultado não gera chamada; compra que o PNCP não acha
fica registrada como falha (sem apagar a coleta anterior); e rodar duas vezes não duplica nada.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from api import historico_pncp as hp  # noqa: E402
from fopa import pncp  # noqa: E402
from tests import pg_efemero  # noqa: E402

C = "04035135000143-1-000015/2026"
DESERTA = "12345678000199-1-000650/2025"
SUMIU = "12345678000199-1-000999/2026"

CONSULTA = pncp.BASE_CONSULTA + "/orgaos/%s/compras/%s/%s"
ITENS = hp.BASE_ITENS + "/orgaos/%s/compras/%s/%s/itens?pagina=%d&tamanhoPagina=" + str(hp.TAMANHO_PAGINA)
RESULTADOS = hp.BASE_ITENS + "/orgaos/%s/compras/%s/%s/itens/%s/resultados"


def _compra(**extra):
    base = {"valorTotalEstimado": 1250000.0, "valorTotalHomologado": 1250000.0, "situacaoCompraNome": "Divulgada no PNCP",
            "dataPublicacaoPncp": "2026-09-16T10:09:17", "dataAberturaProposta": None,
            "dataEncerramentoProposta": "2026-09-30T09:00:00", "modalidadeNome": "Dispensa", "existeResultado": True,
            "objetoCompra": "folha de pagamento", "dataAtualizacaoGlobal": "2026-09-16T10:12:18",
            "orgaoEntidade": {"cnpj": "04035135000143", "razaoSocial": "TRIBUNAL DE CONTAS DO ESTADO DO ACRE"},
            "unidadeOrgao": {"ufSigla": "AC", "municipioNome": "Rio Branco"}}
    base.update(extra)
    return base


def _item(n, situacao="Homologado", tem=True, valor=1250000.0):
    return {"numeroItem": n, "descricao": "gestão da folha", "situacaoCompraItemNome": situacao, "temResultado": tem,
            "valorTotal": valor, "criterioJulgamentoNome": "Maior oferta", "campoQueNinguemUsa": "guardado"}


def _pncp_falso():
    chamadas = []
    respostas = {
        CONSULTA % ("04035135000143", 2026, 15): _compra(),
        ITENS % ("04035135000143", 2026, 15, 1): [_item(1)] + [_item(n, tem=False) for n in range(2, hp.TAMANHO_PAGINA + 1)],
        ITENS % ("04035135000143", 2026, 15, 2): [_item(hp.TAMANHO_PAGINA + 1, tem=False)],
        # o PNCP às vezes devolve o resultado como OBJETO, não lista
        RESULTADOS % ("04035135000143", 2026, 15, 1): {
            "sequencialResultado": 1, "niFornecedor": "00000000000191", "nomeRazaoSocialFornecedor": "BANCO DO BRASIL SA",
            "valorTotalHomologado": 1250000.0, "dataResultado": "2026-09-16", "naturezaJuridicaNome": "Sociedade de Economia Mista",
            "porteFornecedorNome": "Demais", "situacaoCompraItemResultadoNome": "Informado", "dataCancelamento": None},
        CONSULTA % ("12345678000199", 2025, 650): _compra(valorTotalHomologado=None, existeResultado=False,
                                                           dataPublicacaoPncp="2025-11-10T08:00:00"),
        ITENS % ("12345678000199", 2025, 650, 1): [_item(1, situacao="Deserto", tem=False, valor=8805657.81)],
    }

    def get(url, timeout=None):
        chamadas.append(url)
        if url not in respostas:
            raise pncp.ErroPNCP("falhou após 3 tentativas: %s — HTTP Error 404" % url)
        return respostas[url]
    return get, chamadas


@pytest.fixture(scope="module")
def url():
    with pg_efemero.subir() as u:
        pg_efemero.migrar(u)
        yield u


@pytest.fixture
def conn(url):
    with psycopg.connect(url, row_factory=dict_row) as c:
        c.execute("TRUNCATE pncp_compras, pncp_itens, pncp_resultados, pncp_coletas")
        c.commit()
        yield c


def test_uma_compra_inteira_payload_colunas_paginacao_e_vencedor(conn):
    get, chamadas = _pncp_falso()
    r = hp.coletar_um(conn, C, get=get)
    assert r == {"controle": C, "ok": True, "itens": hp.TAMANHO_PAGINA + 1, "resultados": 1,
                 "chamadas": 4, "erro": None, "cabecalho": True}
    # item sem resultado não gera chamada de resultado
    assert sum(1 for u in chamadas if u.endswith("/resultados")) == 1

    compra = conn.execute("SELECT * FROM pncp_compras WHERE controle = %s", (C,)).fetchone()
    assert (compra["uf"], compra["municipio"], compra["orgao_cnpj"]) == ("AC", "Rio Branco", "04035135000143")
    assert (float(compra["valor_estimado"]), float(compra["valor_homologado"])) == (1250000.0, 1250000.0)
    assert compra["existe_resultado"] is True and compra["abertura_em"] is None
    # horário do PNCP é o de Brasília
    assert compra["publicado_em"].isoformat() == "2026-09-16T13:09:17+00:00"
    assert compra["payload"]["orgaoEntidade"]["razaoSocial"].startswith("TRIBUNAL DE CONTAS")

    assert conn.execute("SELECT count(*) AS n FROM pncp_itens WHERE controle = %s", (C,)).fetchone()["n"] == hp.TAMANHO_PAGINA + 1
    item1 = conn.execute("SELECT * FROM pncp_itens WHERE controle = %s AND numero_item = 1", (C,)).fetchone()
    assert (item1["situacao"], item1["tem_resultado"], item1["criterio"]) == ("Homologado", True, "Maior oferta")
    assert item1["payload"]["campoQueNinguemUsa"] == "guardado"        # "todos os itens que a API disponibiliza"

    res = conn.execute("SELECT * FROM pncp_resultados WHERE controle = %s", (C,)).fetchone()
    assert (res["ni_fornecedor"], res["fornecedor"], res["porte"]) == ("00000000000191", "BANCO DO BRASIL SA", "Demais")
    assert (float(res["valor_homologado"]), res["data_resultado"].isoformat(), res["cancelado_em"]) == (1250000.0, "2026-09-16", None)
    assert conn.execute("SELECT ok, chamadas FROM pncp_coletas WHERE controle = %s", (C,)).fetchone() == {"ok": True, "chamadas": 4}


def test_deserta_sem_resultado_e_compra_que_o_pncp_nao_acha(conn):
    get, _ = _pncp_falso()
    assert hp.coletar_um(conn, DESERTA, get=get)["ok"] is True
    item = conn.execute("SELECT situacao, valor_total FROM pncp_itens WHERE controle = %s", (DESERTA,)).fetchone()
    assert (item["situacao"], float(item["valor_total"])) == ("Deserto", 8805657.81)
    assert conn.execute("SELECT count(*) AS n FROM pncp_resultados WHERE controle = %s", (DESERTA,)).fetchone()["n"] == 0

    r = hp.coletar_um(conn, SUMIU, get=get)
    assert r["ok"] is False and "404" in r["erro"]
    col = conn.execute("SELECT ok, erro FROM pncp_coletas WHERE controle = %s", (SUMIU,)).fetchone()
    assert col["ok"] is False and "404" in col["erro"]
    assert conn.execute("SELECT count(*) AS n FROM pncp_compras WHERE controle = %s", (SUMIU,)).fetchone()["n"] == 0


def test_rodar_duas_vezes_nao_duplica_e_falha_nao_apaga_a_coleta_boa(conn):
    get, _ = _pncp_falso()
    hp.coletar_um(conn, C, get=get)
    antes = [conn.execute("SELECT count(*) AS n FROM %s" % t).fetchone()["n"]
             for t in ("pncp_compras", "pncp_itens", "pncp_resultados")]
    hp.coletar_um(conn, C, get=get)
    depois = [conn.execute("SELECT count(*) AS n FROM %s" % t).fetchone()["n"]
              for t in ("pncp_compras", "pncp_itens", "pncp_resultados")]
    assert antes == depois

    def pncp_fora(url, timeout=None):
        raise pncp.ErroPNCP("falhou após 3 tentativas: %s — HTTP Error 503" % url)
    r = hp.coletar_um(conn, C, get=pncp_fora)
    assert r["ok"] is False
    # a coleta boa anterior continua lá: a falha só marca a tentativa
    assert conn.execute("SELECT count(*) AS n FROM pncp_resultados WHERE controle = %s", (C,)).fetchone()["n"] == 1


def test_controle_fora_do_formato_nao_chama_o_pncp(conn):
    get, chamadas = _pncp_falso()
    r = hp.coletar_um(conn, "lixo", get=get)
    assert r["ok"] is False and chamadas == []


def test_cabecalho_passa_pelo_limitador_de_ritmo_da_api_de_consulta(conn):
    # A API de consulta (cabeçalho) devolve 429 com 3 threads; o gateway de itens/resultados não.
    # Medido em 24/09: sem ritmo, 90 s de espera por compra; com, 0,3 s. Uma espera por controle.
    esperas = []

    class Limitador:
        def esperar(self):
            esperas.append(1)

    get, chamadas = _pncp_falso()
    hp.buscar(C, get=get, limitador=Limitador())
    assert esperas == [1]
    assert sum(1 for u in chamadas if "/api/consulta/" in u) == 1


def test_limitador_espaca_as_chamadas():
    import time as _t
    lim = hp.Limitador(por_segundo=20)
    t = _t.perf_counter()          # o monotonic do Windows tem degrau de 15,6 ms: media 187,5 ms num intervalo de 200
    for _ in range(5):
        lim.esperar()
    assert _t.perf_counter() - t >= 4 / 20


def test_cabecalho_recusado_nao_segura_itens_e_resultados(conn):
    # 429 na API de consulta (cabeçalho) custava 90 s de espera por compra. Agora: grava o que o
    # gateway rápido deu (itens e resultados), marca a coleta como parcial, e o cabeçalho vem depois.
    get, _ = _pncp_falso()

    def get_sem_consulta(url, timeout=None):
        if "/api/consulta/" in url:
            raise pncp.ErroPNCP("HTTP Error 429: Too Many Requests")
        return get(url)

    r = hp.coletar_um(conn, C, get=get_sem_consulta)
    assert r["ok"] is True and r["cabecalho"] is False and r["resultados"] == 1
    col = conn.execute("SELECT ok, erro FROM pncp_coletas WHERE controle = %s", (C,)).fetchone()
    assert col["ok"] is True and "cabeçalho" in col["erro"]
    assert conn.execute("SELECT count(*) AS n FROM pncp_compras WHERE controle = %s", (C,)).fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM pncp_resultados WHERE controle = %s", (C,)).fetchone()["n"] == 1
    # a passada de cabeçalhos completa depois, sem refazer itens
    assert hp.coletar_cabecalho(conn, C, get=get) is True
    assert conn.execute("SELECT count(*) AS n FROM pncp_compras WHERE controle = %s", (C,)).fetchone()["n"] == 1
    assert conn.execute("SELECT erro FROM pncp_coletas WHERE controle = %s", (C,)).fetchone()["erro"] is None


def test_pncp_fora_do_ar_nao_desfaz_a_coleta_boa(conn):
    # 30/09: a releitura diária rodou com o PNCP fora do ar e marcava ok=false em quem já tinha sido coletado;
    # o analytics, que só conta `ok`, ficou vazio com os dados intactos.
    get, _ = _pncp_falso()
    assert hp.coletar_um(conn, C, get=get)["ok"] is True

    def fora_do_ar(url, timeout=None):
        raise pncp.ErroPNCP("falhou após 3 tentativas: " + url)

    r = hp.coletar_um(conn, C, get=fora_do_ar)
    assert r["ok"] is False
    col = conn.execute("SELECT ok, erro, chamadas FROM pncp_coletas WHERE controle = %s", (C,)).fetchone()
    assert col["ok"] is True and "falhou" in col["erro"] and col["chamadas"] == 4
    assert conn.execute("SELECT count(*) AS n FROM pncp_resultados WHERE controle = %s", (C,)).fetchone()["n"] == 1
    # e a próxima que der certo limpa o erro
    assert hp.coletar_um(conn, C, get=get)["ok"] is True
    assert conn.execute("SELECT erro FROM pncp_coletas WHERE controle = %s", (C,)).fetchone()["erro"] is None


def test_sem_cabecalho_adia_sem_nem_chamar_a_api_de_consulta(conn):
    # 24/09 21h: a API de consulta passou a TRAVAR (30 s de timeout por compra) enquanto o gateway dava
    # itens em 0,1 s. A passada rápida pode nem tentar o cabeçalho: grava itens e resultados e deixa o
    # cabeçalho para a passada lenta (--so-cabecalhos).
    get, chamadas = _pncp_falso()
    r = hp.coletar_um(conn, C, get=get, get_cabecalho=hp.adiar_cabecalho)
    assert r["ok"] is True and r["cabecalho"] is False and r["resultados"] == 1
    assert not [u for u in chamadas if "/api/consulta/" in u]
    col = conn.execute("SELECT ok, erro FROM pncp_coletas WHERE controle = %s", (C,)).fetchone()
    assert col["ok"] is True and "adiado" in col["erro"]
    assert hp.coletar_cabecalho(conn, C, get=get) is True


def test_faltando_so_dentro_coleta_primeiro_o_escopo(conn):
    # Depois da descoberta histórica (db/030) o acervo tem milhares de licitações, a maioria fora do escopo
    # (o que a regra recusou fica registrado). O ritmo do gateway é de minutos por centena: o analytics abre no
    # escopo de folha, então `--so-dentro` coleta primeiro só o que ele mostra.
    import argparse
    for controle, dentro in (("66666666000101-1-000001/2023", True), ("66666666000101-1-000002/2023", False)):
        conn.execute("INSERT INTO licitacoes (controle, orgao, uf, municipio, modalidade, objeto, publicado_em,"
                     " escopo_dentro, escopo_motivo, estado, origem) VALUES (%s, 'o', 'RS', 'T', 'Pregão', 'x',"
                     " '2023-01-01', %s, 'm', 'fora_janela', 'manual')", (controle, dentro))
    a = argparse.Namespace(so_cabecalhos=False, controles=None, faltando=True, so_dentro=True, limite=0)
    alvos = hp._alvos(conn, a)
    assert "66666666000101-1-000001/2023" in alvos and "66666666000101-1-000002/2023" not in alvos
    a.so_dentro = False
    assert "66666666000101-1-000002/2023" in hp._alvos(conn, a)


def test_passada_rapida_nao_marca_sem_cabecalho_quem_ja_tem(conn):
    # A rodada diária relê itens e resultados do acervo inteiro SEM o cabeçalho: quem já tem cabeçalho de uma coleta
    # anterior não pode virar "cabeçalho indisponível" todo dia.
    get, _ = _pncp_falso()
    hp.coletar_um(conn, C, get=get)
    r = hp.coletar_um(conn, C, get=get, get_cabecalho=hp.adiar_cabecalho)
    assert r["ok"] is True and r["cabecalho"] is False
    assert conn.execute("SELECT erro FROM pncp_coletas WHERE controle = %s", (C,)).fetchone()["erro"] is None


def _licitacao(conn, controle, dentro=True):
    conn.execute("INSERT INTO licitacoes (controle, orgao, uf, municipio, modalidade, objeto, publicado_em,"
                 " escopo_dentro, escopo_motivo, estado, origem) VALUES (%s, 'o', 'AC', 'Rio Branco', 'Dispensa',"
                 " 'folha', '2026-09-16', %s, 'm', 'fora_janela', 'manual') ON CONFLICT (controle) DO NOTHING",
                 (controle, dentro))


def test_rodada_diaria_novas_acervo_cabecalhos_e_contratos(conn, url):
    # Os dados do analytics sempre atualizados: o W41 roda isto todo dia.
    # C já foi coletada antes do vencedor sair (coleta boa, sem cabeçalho nem resultado); DESERTA nunca foi.
    for controle in (C, DESERTA):
        _licitacao(conn, controle)
    conn.execute("INSERT INTO pncp_coletas (controle, ok, erro, chamadas) VALUES (%s, true, 'cabeçalho adiado', 2)",
                 (C,))
    conn.commit()
    get_compras, chamadas = _pncp_falso()

    def get(u, timeout=None, vazio_ok=False):
        if u.startswith(pncp.BASE_BUSCA):                # a busca de contratos: nada nesta rodada
            chamadas.append(u)
            return {"total": 0, "items": []}
        return get_compras(u)

    etapas = []
    r = hp.rodada_diaria(url, get=get, get_cabecalho=get, forcar_contratos=False, paralelo=2,
                         progresso=lambda **p: etapas.append(p["etapa"]))
    # outras licitações do módulo (sem resposta no PNCP falso) só entram como falha
    assert r["novas_coletadas"] == 1 and r["falhas"] == r["novas"] - 1
    assert (r["acervo"], r["acervo_atualizado"]) == (1, 1)
    assert r["vencedores_novos"] == 1                   # o vencedor de C, que saiu depois da 1ª coleta
    assert (r["cabecalhos"], r["cabecalhos_pendentes"]) == (1, 0)
    assert (r["contratos_achados"], r["cego"], r["contratos_forcados"]) == (0, False, False)
    assert {"novas", "acervo", "cabeçalhos", "contratos"} <= set(etapas)
    col = conn.execute("SELECT ok, erro FROM pncp_coletas WHERE controle = %s", (C,)).fetchone()
    assert col == {"ok": True, "erro": None}
    assert conn.execute("SELECT count(*) AS n FROM pncp_compras WHERE controle IN (%s, %s)",
                        (C, DESERTA)).fetchone()["n"] == 2
    # o acervo vai sem cabeçalho (gateway), a nova com ele
    assert sum(1 for u in chamadas if u == CONSULTA % ("12345678000199", 2025, 650)) == 1


def test_rodada_diaria_da_ao_cabecalho_um_tempo_e_nao_segura_a_rodada(conn, url, monkeypatch):
    # 27/09: a API de consulta foi a 5 cabeçalhos por minuto. Estourado o tempo, o cabeçalho fica para amanhã.
    _licitacao(conn, C)
    conn.execute("INSERT INTO pncp_coletas (controle, ok, erro, chamadas) VALUES (%s, true, 'cabeçalho adiado', 2)"
                 " ON CONFLICT (controle) DO UPDATE SET ok = true", (C,))
    conn.commit()
    get_compras, chamadas = _pncp_falso()

    def get(u, timeout=None, vazio_ok=False):
        return {"total": 0, "items": []} if u.startswith(pncp.BASE_BUSCA) else get_compras(u)

    monkeypatch.setattr(hp, "TEMPO_CABECALHOS_S", -1)
    r = hp.rodada_diaria(url, get=get, get_cabecalho=get, forcar_contratos=False, paralelo=2)
    assert r["cabecalhos_tentados"] == 0 and r["cabecalhos_pendentes"] >= 1
    assert not [u for u in chamadas if "/api/consulta/" in u and "000015" in u]
