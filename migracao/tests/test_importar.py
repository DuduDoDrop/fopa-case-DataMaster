# -*- coding: utf-8 -*-
"""
A importação escrevendo de verdade: Postgres 16 efêmero + migrações reais +
storage em disco temporário + snapshot sintético.

O que se prova aqui é o que a seção 9 do plano promete: tudo entra por
controle, os PDFs vão para o storage com o sha conferido contra o manifesto,
o texto congelado entra página a página, a procedência sobrevive, e rodar duas
vezes não muda nada.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from api.storage import Storage  # noqa: E402
from migracao import importar, plano as plano_mod  # noqa: E402
from migracao.acervo import Acervo, DivergenciaManifesto  # noqa: E402
from tests import pg_efemero  # noqa: E402

import fabrica  # noqa: E402
from fabrica import PastaFake  # noqa: E402
from test_plano import C1, C2, C3, EDITAL, TR, _pasta_agente  # noqa: E402

HOJE = date(2026, 9, 24)


@pytest.fixture(scope="module")
def pg():
    with pg_efemero.subir() as url:
        pg_efemero.migrar(url)
        yield url


@pytest.fixture
def banco(pg):
    """Banco limpo a cada teste: as tabelas de dado são esvaziadas, o seed fica."""
    with psycopg.connect(pg, autocommit=True) as c:
        c.execute("TRUNCATE licitacoes, pastas_legado, arquivos, leituras, paginas, execucoes_modelo,"
                  " chamadas_modelo, respostas, verificacoes, verificacao_respostas, publicacoes,"
                  " gabaritos, itens_api, execucoes_workflow, licitacao_eventos, importacoes"
                  " RESTART IDENTITY CASCADE")
    return pg


def _acervo(tmp_path):
    rs = fabrica.respostas("01 - Edital.pdf")
    api = PastaFake(nome="ABERTO Pregao - Api-RS", controle=C2, pdfs={"01 - Edital.pdf": TR},
                    auditoria=fabrica.auditoria("ABERTO Pregao - Api-RS", rs, provedor="",
                                                modelo="claude-opus-5", chamadas=3, brl=4.83,
                                                modo="contexto-completo", agente=False))
    contaminada = _pasta_agente("Castro-PR", C3, pdfs={"01 - Edital.pdf": EDITAL, "PE 133.pdf": b"%PDF outra"},
                                lidos=["01 - Edital.pdf", "PE 133.pdf"], em="2026-09-23T23:57:59-0300")
    contaminada.inventario_arquivos = [{"seq": 1, "arquivo": "01 - Edital.pdf", "sha256": fabrica.sha(EDITAL)}]
    limpa = _pasta_agente("Castro-PR - 557-2026", C3, pdfs={"01 - Edital.pdf": EDITAL},
                          em="2026-09-23T23:58:00-0300")
    corpus = [{"controle": "12345678000109-1-000009/2026", "orgao": "X", "uf": "RS", "municipio": "X",
               "modalidade": "Pregão", "fim_prazo": "2026-12-01T09:00", "publicado_em": "2026-09-01",
               "situacao": "x", "dentro": False, "motivo": "consignado", "objeto": "consignado"}]
    snap, vivo = fabrica.criar(str(tmp_path), [_pasta_agente("Pregão - Teste-SP", C1), api,
                                               contaminada, limpa], corpus=corpus,
                               execucoes=[{"em": "2026-09-23T12:54:41-0300", "script": "28.py",
                                           "duracao_s": 0.1, "custo_brl": 0.0}])
    return Acervo(snap, vivo), vivo


def _conta(url, sql, *args):
    with psycopg.connect(url) as c:
        return c.execute(sql, args).fetchone()[0]


def test_importa_o_acervo(banco, tmp_path):
    acervo, _ = _acervo(tmp_path)
    storage = Storage(str(tmp_path / "dados"))
    plano = plano_mod.montar(acervo, hoje=HOJE)
    with psycopg.connect(banco) as conn:
        r = importar.aplicar(conn, plano, acervo, storage)
    assert r["licitacoes"] == 4 and r["execucoes"] == 4

    estados = dict(psycopg.connect(banco).execute("SELECT controle, estado::text FROM licitacoes").fetchall())
    assert estados[C1] == estados[C2] == estados[C3] == "verificada"
    assert estados["12345678000109-1-000009/2026"] == "fora_escopo"
    # nascimento: um evento por licitação, de NULL para o estado importado
    assert _conta(banco, "SELECT count(*) FROM licitacao_eventos WHERE de IS NULL") == 4

    # PDFs no storage, com a chave content-addressed do plano
    for chave, sha in psycopg.connect(banco).execute(
            "SELECT storage_key, sha256 FROM arquivos WHERE status = 'ok'").fetchall():
        assert storage.existe(chave) and chave.endswith(sha + ".pdf")
    assert _conta(banco, "SELECT count(*) FROM arquivos WHERE status = 'procedencia_incerta'") == 1

    # texto congelado página a página, a leitura vigente é a da pasta canônica
    assert _conta(banco, "SELECT count(*) FROM leituras") == 3
    assert _conta(banco, "SELECT count(*) FROM leituras WHERE vigente") == 2
    vig = _conta(banco, "SELECT leitura_vigente_id FROM licitacoes WHERE controle = %s", C3)
    assert _conta(banco, "SELECT count(*) FROM paginas WHERE leitura_id = %s", vig) == 1
    assert _conta(banco, "SELECT count(*) FROM paginas WHERE arquivo_id IS NULL") == 0

    # procedência: agente sem preço, API com custo legado, nunca 0
    with psycopg.connect(banco) as c:
        rows = dict(c.execute("SELECT origem || ':' || canonica, count(*) FROM execucoes_modelo GROUP BY 1").fetchall())
        assert rows == {"agente:true": 2, "agente:false": 1, "api:true": 1}
        brl, legado, completa = c.execute(
            "SELECT brl, brl_legado, procedencia_completa FROM execucoes_modelo WHERE origem = 'api'").fetchone()
        assert brl is None and float(legado) == 4.83 and completa is False
        assert c.execute("SELECT count(*) FROM respostas").fetchone()[0] == 4 * 17
        # verificação vigente por controle, e o link de cada resposta resolve para um arquivo
        assert c.execute("SELECT count(*) FROM verificacoes WHERE vigente").fetchone()[0] == 3
        assert c.execute("SELECT count(*) FROM verificacao_respostas vr JOIN verificacoes v"
                         " ON v.id = vr.verificacao_id WHERE v.vigente AND vr.ausencia IS NULL"
                         " AND vr.arquivo_id IS NULL").fetchone()[0] == 0
        # invariantes do plano: nada violado
        viol = c.execute((RAIZ / "db" / "invariantes.sql").read_text(encoding="utf-8")).fetchall()
        assert viol == []
        assert c.execute("SELECT count(*) FROM execucoes_workflow WHERE script_legado = '28.py'").fetchone()[0] == 1
        (imp,) = c.execute("SELECT snapshot FROM importacoes").fetchone()
        assert imp == "2026-09-24_0150"


def test_segunda_importacao_nao_muda_nada(banco, tmp_path):
    acervo, _ = _acervo(tmp_path)
    storage = Storage(str(tmp_path / "dados"))
    plano = plano_mod.montar(acervo, hoje=HOJE)
    with psycopg.connect(banco) as conn:
        importar.aplicar(conn, plano, acervo, storage)
    tabelas = ("licitacoes", "arquivos", "leituras", "paginas", "execucoes_modelo", "respostas",
               "verificacoes", "verificacao_respostas", "licitacao_eventos", "pastas_legado",
               "execucoes_workflow")
    antes = {t: _conta(banco, "SELECT count(*) FROM %s" % t) for t in tabelas}
    with psycopg.connect(banco) as conn:
        r = importar.aplicar(conn, plano, acervo, storage)
    depois = {t: _conta(banco, "SELECT count(*) FROM %s" % t) for t in tabelas}
    assert antes == depois
    assert r["licitacoes"] == 0 and r["execucoes"] == 0 and r["paginas"] == 0


def test_pdf_que_mudou_depois_do_snapshot_aborta_tudo(banco, tmp_path):
    acervo, vivo = _acervo(tmp_path)
    with open(os.path.join(vivo, "Pregão - Teste-SP", "01 - Edital.pdf"), "ab") as f:
        f.write(b" alterado depois do congelamento")
    plano = plano_mod.montar(acervo, hoje=HOJE)
    with pytest.raises(DivergenciaManifesto):
        with psycopg.connect(banco) as conn:
            importar.aplicar(conn, plano, acervo, Storage(str(tmp_path / "dados")))
    assert _conta(banco, "SELECT count(*) FROM licitacoes") == 0


def test_importacao_incremental_promove_a_preparada(banco, tmp_path):
    # O acervo cresce enquanto o agente trabalha (seção 9): a licitação entra
    # `preparada` num snapshot e ganha extração no seguinte.
    preparada = PastaFake(nome="Pregão - Teste-SP", controle=C1, pdfs={"01 - Edital.pdf": EDITAL},
                          leitura_paginas=[("01 - Edital.pdf", 1, "texto de 01 - Edital.pdf")])
    snap1, vivo1 = fabrica.criar(str(tmp_path / "s1"), [preparada])
    storage = Storage(str(tmp_path / "dados"))
    a1 = Acervo(snap1, vivo1)
    with psycopg.connect(banco) as conn:
        importar.aplicar(conn, plano_mod.montar(a1, hoje=HOJE), a1, storage)
    assert _conta(banco, "SELECT estado::text FROM licitacoes WHERE controle = %s", C1) == "preparada"

    snap2, vivo2 = fabrica.criar(str(tmp_path / "s2"), [_pasta_agente("Pregão - Teste-SP", C1)])
    a2 = Acervo(snap2, vivo2)
    with psycopg.connect(banco) as conn:
        r = importar.aplicar(conn, plano_mod.montar(a2, hoje=HOJE), a2, storage)
    assert r["promovidas"] == 1 and r["licitacoes"] == 0
    assert _conta(banco, "SELECT estado::text FROM licitacoes WHERE controle = %s", C1) == "verificada"
    # o caminho fica na linha do tempo, com o motivo
    assert _conta(banco, "SELECT count(*) FROM licitacao_eventos WHERE controle = %s"
                  " AND motivo LIKE 'importação incremental%%'", C1) == 3
    assert _conta(banco, "SELECT count(*) FROM verificacoes WHERE controle = %s AND vigente", C1) == 1


def test_mesmo_texto_com_nomes_diferentes_sao_duas_leituras(banco, tmp_path):
    # Capep: duas pastas do mesmo controle, o mesmo texto, nomes de arquivo
    # diferentes. Uma leitura só faria a execução canônica citar arquivos que
    # não existem no texto congelado dela.
    def pasta(nome, arquivo, de=None):
        rs = fabrica.respostas(arquivo)
        texto = "\n".join("trecho %s" % r["id"] for r in rs)
        return PastaFake(nome=nome, controle=C1, pdfs={arquivo: EDITAL},
                         auditoria=fabrica.auditoria(nome, rs), leitura_paginas=[(arquivo, 1, texto)],
                         respostas_agente=rs, finalizado=fabrica.finalizado(nome, de=de))
    snap, vivo = fabrica.criar(str(tmp_path), [pasta("Capep", "03 - Edital__A.pdf"),
                                               pasta("Capep-Saude", "03 - Edital__AGOSTO.pdf", de="Capep")])
    acervo = Acervo(snap, vivo)
    with psycopg.connect(banco) as conn:
        importar.aplicar(conn, plano_mod.montar(acervo, hoje=HOJE), acervo, Storage(str(tmp_path / "d")))
    assert _conta(banco, "SELECT count(*) FROM leituras WHERE controle = %s", C1) == 2
    with psycopg.connect(banco) as c:
        viol = c.execute((RAIZ / "db" / "invariantes.sql").read_text(encoding="utf-8")).fetchall()
    assert viol == []
