# -*- coding: utf-8 -*-
"""
`importar.py --publicar` (28/09/2026, v3.1): na stack LOCAL religada para desenvolver, publicar um fluxo com agenda
(W01 descoberta, W41 histórico, W50 e-mails...) faria dois n8n coletarem e mandarem e-mail em dobro. O padrão
continua "todos" (a produção); "nenhum" carrega os fluxos sem ativar; uma lista publica só os códigos dados — os
subfluxos sem agenda (W20-W24), que o n8n só chama publicados.

Sem stack: uma API falsa que registra o que o importar pediu.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

import importar  # noqa: E402


class ApiFalsa:
    def __init__(self):
        self.fluxos: dict[str, dict] = {}
        self.publicados: list[str] = []

    def listar_workflows(self):
        return list(self.fluxos.values())

    def listar_credenciais(self):
        return []

    def workflow(self, wid):
        return self.fluxos[wid]

    def publica(self, metodo, caminho, corpo=None):
        if metodo == "POST" and caminho == "/workflows":
            wid = "id-%d" % (len(self.fluxos) + 1)
            self.fluxos[wid] = dict(corpo, id=wid, versionId="v-" + wid, active=False, activeVersionId=None)
            return self.fluxos[wid]
        if caminho.endswith("/publish"):
            wid = caminho.split("/")[2]
            self.publicados.append(self.fluxos[wid]["name"])
            self.fluxos[wid].update(active=True, activeVersionId=self.fluxos[wid]["versionId"])
            return {}
        raise AssertionError("chamada inesperada: %s %s" % (metodo, caminho))


def _pasta(tmp_path, nomes):
    for codigo, nome in nomes:
        (tmp_path / ("%s.json" % codigo)).write_text(json.dumps(
            {"name": nome, "nodes": [], "connections": {}, "settings": {}}), encoding="utf-8")
    return tmp_path


NOMES = [("W01", "W01 Descoberta"), ("W20", "W20 Processar uma licitação"), ("W23", "W23 Extrair")]


def test_padrao_publica_todos_como_na_producao(tmp_path):
    api = ApiFalsa()
    rel = importar.importar(_pasta(tmp_path, NOMES), api=api)
    assert sorted(api.publicados) == sorted(n for _, n in NOMES)
    assert all(r["publicado"] for r in rel.values())


def test_nenhum_carrega_sem_ativar(tmp_path):
    api = ApiFalsa()
    rel = importar.importar(_pasta(tmp_path, NOMES), api=api, publicar="nenhum")
    assert api.publicados == []
    assert {r["acao"] for r in rel.values()} == {"criado"}
    assert not any(r["publicado"] for r in rel.values())


def test_lista_publica_so_os_codigos_dados(tmp_path):
    api = ApiFalsa()
    importar.importar(_pasta(tmp_path, NOMES), api=api, publicar={"W20", "W23"})
    assert sorted(api.publicados) == ["W20 Processar uma licitação", "W23 Extrair"]


def test_cli_le_a_lista(monkeypatch):
    assert importar.ler_publicar("todos") == "todos"
    assert importar.ler_publicar("nenhum") == "nenhum"
    assert importar.ler_publicar("W20,W23 ,w24") == {"W20", "W23", "W24"}
    with pytest.raises(ValueError):
        importar.ler_publicar("W2O")
