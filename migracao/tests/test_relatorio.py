# -*- coding: utf-8 -*-
"""
Passo 8 da seção 9 do plano: o relatório de reconciliação.

A importação já era idempotente e já conferia as invariantes; o que faltava era
o documento que diz ao humano o que ele precisa decidir ou saber: controles com
duas pastas, arquivos de procedência incerta, extraídas fora do escopo,
procedência inferida, gêmeas, empates sem critério. Aqui se prova que cada caso
do acervo sintético aparece na seção certa — e que a ausência é dita, não omitida.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from api.storage import Storage  # noqa: E402
from migracao import importar, plano as plano_mod, relatorio  # noqa: E402
from tests import pg_efemero  # noqa: E402

from test_importar import HOJE, _acervo  # noqa: E402
from test_plano import C1, C2, C3  # noqa: E402


@pytest.fixture(scope="module")
def pg():
    with pg_efemero.subir() as url:
        pg_efemero.migrar(url)
        yield url


@pytest.fixture
def importado(pg, tmp_path):
    with psycopg.connect(pg, autocommit=True) as c:
        c.execute("TRUNCATE licitacoes, pastas_legado, arquivos, leituras, paginas, execucoes_modelo,"
                  " chamadas_modelo, respostas, verificacoes, verificacao_respostas, publicacoes,"
                  " gabaritos, itens_api, execucoes_workflow, licitacao_eventos, importacoes"
                  " RESTART IDENTITY CASCADE")
    acervo, _ = _acervo(tmp_path)
    plano = plano_mod.montar(acervo, hoje=HOJE)
    with psycopg.connect(pg) as conn:
        importar.aplicar(conn, plano, acervo, Storage(str(tmp_path / "dados")))
    return pg


def _secao(md: str, titulo: str) -> str:
    """O texto de uma seção `## titulo` até a próxima `## `."""
    ini = md.index("## " + titulo)
    fim = md.find("\n## ", ini + 1)
    return md[ini:] if fim < 0 else md[ini:fim]


def test_cada_caso_do_acervo_aparece_na_secao_certa(importado):
    with psycopg.connect(importado) as conn:
        md = relatorio.montar(conn, hoje=HOJE)

    assert md.startswith("# Reconciliação da migração")
    # a importação e o snapshot de onde veio
    assert "2026-09-24_0150" in _secao(md, "Importações")

    dup = _secao(md, "Controles com mais de uma pasta")
    assert C3 in dup and "Castro-PR - 557-2026" in dup and "Castro-PR" in dup
    assert C1 not in dup and C2 not in dup

    incerta = _secao(md, "Procedência incerta")
    assert C3 in incerta and "PE 133.pdf" in incerta

    inferida = _secao(md, "Procedência inferida")
    assert C2 in inferida and "api" in inferida and C1 not in inferida

    # o edital de Castro-PR tem os mesmos bytes do de C1: gêmeas, não duplicata
    gemeas = _secao(md, "Gêmeas")
    assert C3 in gemeas and C1 in gemeas

    # o que não existe no acervo é dito, não omitido
    assert "nenhum" in _secao(md, "Extraídas fora do escopo").lower()
    assert "nenhuma" in _secao(md, "Decisões pendentes").lower()

    contagens = _secao(md, "Contagens")
    assert "| licitações | 4 |" in contagens


def test_extraida_fora_do_escopo_e_canonicas_de_pastas_diferentes_viram_achado(importado):
    with psycopg.connect(importado, autocommit=True) as c:
        # a regra de escopo mudou depois da extração: o dado existe, o escopo diz "fora"
        c.execute("UPDATE licitacoes SET escopo_dentro = false, escopo_motivo = 'consignado'"
                  " WHERE controle = %s", (C1,))
        # duas execuções canônicas vindas de pastas diferentes do mesmo controle
        c.execute("UPDATE execucoes_modelo SET canonica = true WHERE controle = %s", (C3,))
    with psycopg.connect(importado) as conn:
        md = relatorio.montar(conn, hoje=HOJE)

    fora = _secao(md, "Extraídas fora do escopo")
    assert C1 in fora and "consignado" in fora

    canon = _secao(md, "Mais de uma execução canônica")
    assert C3 in canon and "Castro-PR - 557-2026" in canon


def test_main_grava_o_arquivo_e_exige_o_banco(importado, tmp_path, monkeypatch, capsys):
    saida = tmp_path / "relatorio-2026-09-24.md"
    assert relatorio.main(["--database-url", importado, "--saida", str(saida),
                           "--hoje", HOJE.isoformat()]) == 0
    texto = saida.read_text(encoding="utf-8")
    assert texto.startswith("# Reconciliação da migração") and C3 in texto

    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert relatorio.main(["--saida", str(saida)]) == 2
    assert "DATABASE_URL" in capsys.readouterr().err
