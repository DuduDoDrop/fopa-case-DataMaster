# -*- coding: utf-8 -*-
"""
exportar.py — o caminho inverso do importar.py: fopa-n8n -> n8n/workflows/*.json.

Para quem editou um fluxo no canvas e quer versionar a mudança. Todo id que
nasceu na instância volta a ser placeholder, senão o JSON do git só
funcionaria nesta máquina:

    settings.errorWorkflow = <id do W90>        -> {{WF:W90}}
    Execute Workflow -> workflowId = <id>        -> {{WF:Wnn}}
    credentials.<tipo> = {id, name}              -> {id: {{CRED:name}}, name}

A credencial volta pelo NOME, não pelo id: é assim que o sentinela
`ausente:smtp` (credencial ainda não criada, ver importar.py) também volta a
{{CRED:smtp}}. Só fluxos cujo nome começa por Wnn são exportados — o que mais
existir na instância não é da FOPA versionada.

O arquivo sai com as chaves de nó na ordem do molde (parameters, id, name,
type, typeVersion, position, ...) e indentação fixa: o diff no git mostra só o
que mudou no canvas.

Uso (a partir da raiz):
    python n8n/exportar.py                 # sobrescreve n8n/workflows/
    python n8n/exportar.py --destino /tmp/x
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cliente
from cliente import ErroN8n, N8n
from importar import CHAVES_NO, PASTA_WORKFLOWS, codigo

# Configurações que a instância devolve e que fazem parte do fluxo versionado.
CHAVES_SETTINGS = ("executionOrder", "timezone", "errorWorkflow", "saveManualExecutions",
                   "saveDataSuccessExecution", "saveDataErrorExecution", "saveExecutionProgress",
                   "executionTimeout", "callerPolicy", "callerIds", "availableInMCP")


def _placeholder_wf(valor, codigo_por_id: dict):
    if isinstance(valor, str) and valor in codigo_por_id:
        return "{{WF:%s}}" % codigo_por_id[valor]
    return valor


def desresolver(wf: dict, codigo_por_id: dict) -> dict:
    nos = []
    for n in wf["nodes"]:
        novo = {k: n[k] for k in CHAVES_NO if k in n}
        for tipo, ref in (novo.get("credentials") or {}).items():
            novo["credentials"][tipo] = {"id": "{{CRED:%s}}" % ref["name"], "name": ref["name"]}
        p = novo.get("parameters") or {}
        if n["type"].endswith(".executeWorkflow") and "workflowId" in p:
            w = p["workflowId"]
            if isinstance(w, dict):
                w["value"] = _placeholder_wf(w.get("value"), codigo_por_id)
                w.pop("cachedResultUrl", None)   # traz o id real embutido na URL
            else:
                p["workflowId"] = _placeholder_wf(w, codigo_por_id)
        nos.append(novo)
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in CHAVES_SETTINGS}
    if "errorWorkflow" in settings:
        settings["errorWorkflow"] = _placeholder_wf(settings["errorWorkflow"], codigo_por_id)
    return {"name": wf["name"], "nodes": nos, "connections": wf["connections"], "settings": settings}


def exportar(destino: Path | None = None, api: N8n | None = None) -> list:
    destino = Path(destino) if destino else PASTA_WORKFLOWS
    destino.mkdir(parents=True, exist_ok=True)
    api = api or N8n.autenticado()
    fluxos = [w for w in api.listar_workflows() if codigo(w["name"]) and not w.get("isArchived")]
    codigo_por_id = {w["id"]: codigo(w["name"]) for w in fluxos}
    repetidos = {c for c in codigo_por_id.values() if list(codigo_por_id.values()).count(c) > 1}
    if repetidos:
        raise ErroN8n("mais de um fluxo com o mesmo código na instância: %s" % sorted(repetidos))
    escritos = []
    for w in sorted(fluxos, key=lambda w: w["name"]):
        wf = desresolver(api.workflow(w["id"]), codigo_por_id)
        p = destino / ("%s.json" % codigo(w["name"]))
        p.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        escritos.append(p)
    return escritos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--destino", default=str(PASTA_WORKFLOWS))
    a = ap.parse_args()
    try:
        for p in exportar(Path(a.destino)):
            print(p)
    except ErroN8n as e:
        print("ERRO:", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
