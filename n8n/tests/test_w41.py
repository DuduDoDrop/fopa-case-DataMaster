# -*- coding: utf-8 -*-
"""
W41 (histórico do PNCP, todo dia 04:30) — o JSON versionado segue as convenções dos fluxos agendados (as do
test_w40_w70.py) e o laço dos jobs longos do W21. Estático: não precisa da instância.

O trabalho é do worker (api/historico_pncp.py: rodada_diaria, testado em api/tests); aqui se prova que o fluxo o
dispara, espera o job do jeito certo e deixa o rastro em `execucoes_workflow` — com os números do job ou o motivo.

    python -m pytest n8n/tests/test_w41.py -v
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import importar  # noqa: E402

ARQ = importar.PASTA_WORKFLOWS / "W41.json"


def _wf() -> dict:
    return json.loads(ARQ.read_text(encoding="utf-8"))


def _no(wf: dict, nome: str) -> dict:
    return next(n for n in wf["nodes"] if n["name"] == nome)


def _destinos(wf: dict, origem: str) -> list[list[str]]:
    return [[c["node"] for c in saida] for saida in wf["connections"][origem]["main"]]


def test_w41_versionado_segue_as_convencoes_dos_agendados():
    wf = _wf()
    assert wf["name"] == "W41 Histórico do PNCP" and importar.codigo(wf["name"]) == "W41"
    gatilho = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.scheduleTrigger")
    assert gatilho["parameters"]["rule"]["interval"][0]["expression"] == "30 4 * * *", "todo dia 04:30"
    s = wf["settings"]
    assert (s["errorWorkflow"], s["timezone"], s["executionOrder"]) == ("{{WF:W90}}", "America/Sao_Paulo", "v1")
    assert any(n["type"] == "n8n-nodes-base.manualTrigger" for n in wf["nodes"])
    notas = [n["parameters"]["content"] for n in wf["nodes"] if n["type"] == "n8n-nodes-base.stickyNote"]
    assert any("—" in c and ".py:" in c for c in notas)
    for n in wf["nodes"]:
        if n["type"] == "n8n-nodes-base.postgres":
            assert n["typeVersion"] == 2.6 and n.get("executeOnce") is True
            assert n["credentials"]["postgres"]["id"] == "{{CRED:fopa-postgres (n8n_rw)}}"
            # só mexe na linha da própria rodada
            sql = re.sub(r"--[^\n]*", "", n["parameters"]["query"])
            assert re.findall(r"\b(?:INSERT INTO|UPDATE)\s+(\w+)", sql) == ["execucoes_workflow"], n["name"]
    assert "'W41'" in _no(wf, "Abrir execução")["parameters"]["query"]
    ids = [n["id"] for n in wf["nodes"]]
    assert len(ids) == len(set(ids))


def test_w41_dispara_o_job_do_worker_e_espera_como_o_w21():
    wf = _wf()
    https = {n["name"]: n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"}
    assert set(https) == {"POST /jobs/historico", "GET /jobs/{id}"}
    for n in https.values():
        p = n["parameters"]
        assert p["url"].startswith("={{ $env.FOPA_WORKER_URL }}/jobs/")
        assert n["credentials"]["httpHeaderAuth"]["id"] == "{{CRED:worker}}"
        assert p["options"]["timeout"] == 30000
        assert p["options"]["response"]["response"] == {"fullResponse": True, "neverError": True}
        assert n["onError"] == "continueErrorOutput"
    assert https["POST /jobs/historico"]["parameters"]["method"] == "POST"
    # o laço: aceito (202 + job_id) → espera 30 s → GET → status → volta enquanto queued/running
    assert _destinos(wf, "POST /jobs/historico") == [["Job aceito?"], ["Job aceito?"]]
    assert _destinos(wf, "Job aceito?") == [["Esperar 30 s"], ["Motivo da falha"]]
    assert _no(wf, "Esperar 30 s")["parameters"] == {"amount": 30, "unit": "seconds"}
    assert _destinos(wf, "Esperar 30 s") == [["GET /jobs/{id}"]]
    assert _destinos(wf, "GET /jobs/{id}") == [["Status do job"], ["Status do job"]]
    assert _destinos(wf, "Ainda na fila ou rodando?") == [["Esperar 30 s"], ["Job concluído?"]]
    assert _destinos(wf, "Job concluído?") == [["Fechar execução"], ["Motivo da falha"]]
    assert _destinos(wf, "Motivo da falha") == [["Fechar com erro"]]
    status = _no(wf, "Status do job")["parameters"]["jsCode"]
    for trecho in ("const MAX = 150;", "status === 'queued' || status === 'running'", "status === 'done'",
                   "$('POST /jobs/historico')"):
        assert trecho in status, trecho
    # sucesso grava os números do job; falha grava o motivo — nunca silêncio
    assert "$json.result" in _no(wf, "Fechar execução")["parameters"]["options"]["queryReplacement"]
    assert "cego = " in _no(wf, "Fechar execução")["parameters"]["query"]      # busca caída fica visível
    assert "status = 'erro'" in _no(wf, "Fechar com erro")["parameters"]["query"]
