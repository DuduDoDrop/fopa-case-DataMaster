# -*- coding: utf-8 -*-
"""
executar.py — dispara um fluxo do fopa-n8n pelo gatilho Manual e mostra o
resultado nó a nó, sem abrir a UI.

Três comportamentos da REST interna do n8n 2.x, respeitados aqui:

1. A API PÚBLICA NÃO EXECUTA fluxo. Só a REST interna (`POST
   /rest/workflows/{id}/run`, cookie de sessão) dispara execução manual.
2. O disparo precisa de `triggerToStartFrom` com o item já no formato
   ITaskData; sem isso a 2.x responde 400 "specify either a trigger to start
   from or a destination node".
3. A execução volta no formato `flatted` (toda string que é inteiro é um
   ponteiro para outra posição do array): `json.loads` sozinho devolve dados sem sentido.

Execução manual NÃO dispara o Error Trigger (W90) — limitação do n8n (plano,
Apêndice A). Para ensaiar o W90 use o schedule ou um webhook.

Sub-fluxos (W21-W24, W20) não têm gatilho Manual: começam em "When Executed
by Another Workflow". Para ensaiá-los sem um fluxo-pai, o disparo parte desse
gatilho com os itens de entrada dados (`--itens`), exatamente como o Execute
Workflow do pai os entregaria. É a mesma execução manual (sem Error Trigger).

Uso (a partir da raiz):
    python n8n/executar.py "W00 Saúde"
    python n8n/executar.py W00
    python n8n/executar.py W21 --itens '{"controle": "83102434000120-1-000111/2026"}'
    python n8n/executar.py W20 --itens '{"controle": "...", "forcar": false}' --saidas
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import cliente
from cliente import ErroN8n, N8n

TERMINAIS = {"success", "error", "crashed", "canceled"}


def desflatta(texto: str):
    arr = json.loads(texto)
    cache: dict = {}

    def ponteiro(x):
        return isinstance(x, str) and x.lstrip("-").isdigit()

    def pega(i: int):
        if i in cache:
            return cache[i]
        v = arr[i]
        if isinstance(v, list):
            out: list = []
            cache[i] = out
            out.extend(pega(int(x)) if ponteiro(x) else x for x in v)
            return out
        if isinstance(v, dict):
            out_d: dict = {}
            cache[i] = out_d
            for k, x in v.items():
                out_d[k] = pega(int(x)) if ponteiro(x) else x
            return out_d
        cache[i] = v
        return v

    return pega(0)


def achar(api: N8n, alvo: str) -> dict:
    fluxos = api.listar_workflows()
    exato = [w for w in fluxos if w["name"] == alvo or w["id"] == alvo]
    if not exato:
        exato = [w for w in fluxos if w["name"].startswith(alvo)]
    if len(exato) != 1:
        raise ErroN8n("'%s' casa com %d fluxos: %s" % (alvo, len(exato), [w["name"] for w in exato]))
    return exato[0]


def resumo_nos(execucao: dict, com_saidas: bool = False) -> dict:
    """
    Por nó: itens por saída na ÚLTIMA rodada e quantas rodadas houve (laços
    Wait → GET e Loop Over Items rodam o mesmo nó várias vezes). Com
    `com_saidas`, também o JSON que cada nó emitiu na última rodada — é o que
    os testes leem para provar o que o fluxo decidiu, não só que terminou.
    """
    bruto = execucao.get("data")
    dados = desflatta(bruto) if isinstance(bruto, str) else (bruto or {})
    rd = dados.get("resultData") or {}
    nos, saidas_json = {}, {}
    for no, rodadas in (rd.get("runData") or {}).items():
        ultima = rodadas[-1]
        if ultima.get("error"):
            nos[no] = {"erro": str(ultima["error"].get("message"))[:300], "rodadas": len(rodadas)}
        else:
            saidas = (ultima.get("data") or {}).get("main") or []
            nos[no] = {"itens": [len(s or []) for s in saidas], "rodadas": len(rodadas)}
            if com_saidas:
                saidas_json[no] = [[(it or {}).get("json") for it in (s or [])] for s in saidas]
    erro = (rd.get("error") or {}).get("message")
    r = {"nos": nos, "erro": erro, "ultimo_no": rd.get("lastNodeExecuted")}
    if com_saidas:
        r["saidas"] = saidas_json
    return r


TIPOS_GATILHO = ("n8n-nodes-base.manualTrigger", "n8n-nodes-base.executeWorkflowTrigger")


def achar_gatilho(wf: dict, nome: str | None = None, com_itens: bool = False) -> dict:
    """
    O gatilho pedido pelo nome. Sem nome: com itens de entrada, o de sub-fluxo (é ele que lê os itens);
    sem itens, o Manual.

    Por quê: um fluxo com os DOIS gatilhos (W30: Manual = acervo inteiro; sub-fluxo = só os `controles`)
    disparado pelo Manual com itens perde os itens — em 24/09 isso reverificou o acervo publicado inteiro
    num teste que pedia 2 licitações (execução 436, desfeita). Itens pedem o gatilho que os entende.
    """
    if nome:
        g = next((n for n in wf["nodes"] if n["name"] == nome), None)
        if g is None:
            raise ErroN8n("%s não tem nó '%s'" % (wf["name"], nome))
        return g
    for tipo in (reversed(TIPOS_GATILHO) if com_itens else TIPOS_GATILHO):
        g = next((n for n in wf["nodes"] if n["type"] == tipo), None)
        if g is not None:
            return g
    raise ErroN8n("%s não tem gatilho Manual nem 'When Executed by Another Workflow'" % wf["name"])


def executar(alvo: str, timeout: int = 120, api: N8n | None = None, itens: list | None = None,
             gatilho: str | None = None, com_saidas: bool = False) -> dict:
    """
    Dispara `alvo` a partir do gatilho (Manual ou de sub-fluxo) com `itens`
    (lista de dicts; padrão: um item vazio) e espera terminar.
    """
    api = api or N8n.autenticado()
    wid = achar(api, alvo)["id"]
    wf = api.interna("GET", "/rest/workflows/" + wid)
    gatilho = achar_gatilho(wf, gatilho, com_itens=any(bool(i) for i in (itens or [])))
    itens = [{"json": dict(i)} for i in (itens or [{}])]
    corpo = {
        "workflowData": {**wf, "pinData": {}},
        "runData": {},
        "startNodes": [],
        "triggerToStartFrom": {
            "name": gatilho["name"],
            "data": {"startTime": 0, "executionTime": 0, "source": [],
                     "executionStatus": "success", "data": {"main": [itens]}},
        },
    }
    d = api.interna("POST", "/rest/workflows/%s/run" % wid, corpo)
    exec_id = d["executionId"]
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        time.sleep(2)
        e = api.interna("GET", "/rest/executions/%s" % exec_id, ok=(200, 404))
        if isinstance(e, dict) and e.get("status") in TERMINAIS:
            return {"id": str(exec_id), "status": e["status"], **resumo_nos(e, com_saidas)}
    return {"id": str(exec_id), "status": "timeout", "nos": {}, "erro": "não terminou em %d s" % timeout}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("fluxo", help="nome, prefixo (W00) ou id")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--itens", help="JSON: um objeto ou uma lista de objetos de entrada do gatilho")
    ap.add_argument("--gatilho", help="nome do nó gatilho (padrão: Manual ou o de sub-fluxo)")
    ap.add_argument("--saidas", action="store_true", help="mostra o JSON emitido por cada nó")
    a = ap.parse_args()
    itens = None
    if a.itens:
        itens = json.loads(a.itens)
        itens = itens if isinstance(itens, list) else [itens]
    try:
        r = executar(a.fluxo, a.timeout, itens=itens, gatilho=a.gatilho, com_saidas=a.saidas)
    except ErroN8n as e:
        print("ERRO:", e)
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
