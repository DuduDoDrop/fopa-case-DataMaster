# -*- coding: utf-8 -*-
"""
importar.py — sobe n8n/workflows/*.json para o fopa-n8n (plano, seção 5,
"Versionamento dos fluxos").

Upsert POR NOME pela API pública (`/api/v1/workflows`, X-N8N-API-KEY de
n8n/.segredos/api_key — nunca fixa no código). Os JSON versionados não carregam
id nenhum da instância; carregam placeholders que este script resolve:

    {{WF:W90}}        -> id do fluxo cujo nome começa por "W90 "
    {{CRED:nome}}     -> id da credencial com esse nome (n8n/bootstrap.py cria)

Por que placeholder e não id: o id nasce na instância. Outra máquina, um
volume recriado ou a nuvem (F8) geram ids novos, e um JSON com id fixo
apontaria o Error Workflow ou a credencial para o nada — em silêncio.

ORDEM: das folhas para a raiz. O n8n 2.x recusa publicar um fluxo que
referencia sub-workflow não publicado, e o
id de um fluxo só existe depois de criado. A ordem sai das próprias
referências {{WF:...}} (W90 antes de W00/W50; depois W21-W24 → W20 → W10 → W01/W11).

IDEMPOTENTE: se o que está na instância já é igual ao JSON resolvido, nada é
enviado ("inalterado") — a 2ª execução não cria versão nova nem republica.

Credencial ausente (hoje: 'smtp', porque SMTP_HOST está vazio) NÃO bloqueia:
o nó recebe o id sentinela `ausente:<nome>`. A 2.37.10 recusa publicar nó com
credencial de id VAZIO ("Credential not configured", n8n-workflow
node-validation.js:32) mas não confere se o id existe; em execução o nó falha
com "Credential with ID "ausente:smtp" does not exist" e o W50 grava esse
motivo na linha do e-mail — o que o plano pede: falha visível, nunca silêncio.
O sentinela é legível no canvas e o exportar.py o devolve a {{CRED:nome}}.

PUBLICAR (28/09/2026, v3.1): o padrão é publicar todos (a produção). Na stack LOCAL religada para desenvolver,
publicar um fluxo com agenda faria dois n8n coletarem e mandarem e-mail em dobro: `--publicar nenhum` carrega sem
ativar, e `--publicar W20,W21,W22,W23,W24` publica só os subfluxos sem agenda (o n8n só chama subfluxo publicado).

Uso (a partir da raiz):
    python n8n/importar.py
    python n8n/importar.py --pasta caminho/para/jsons
    python n8n/importar.py --publicar W20,W21,W22,W23,W24     # stack local
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import cliente
from cliente import ErroN8n, N8n

PASTA_WORKFLOWS = cliente.AQUI / "workflows"
RE_WF = re.compile(r"\{\{WF:(W\d{2})\}\}")
RE_CRED = re.compile(r"\{\{CRED:([^}]+)\}\}")
SENTINELA = "ausente:"

# Chaves de nó que a FOPA controla pelo JSON. O resto (ex.: webhookId gerado)
# é da instância e não entra na comparação.
CHAVES_NO = ("parameters", "id", "name", "type", "typeVersion", "position", "credentials",
             "onError", "alwaysOutputData", "executeOnce", "disabled", "notes", "retryOnFail",
             "maxTries", "waitBetweenTries")


def codigo(nome: str) -> str | None:
    m = re.match(r"^(W\d{2})\b", nome or "")
    return m.group(1) if m else None


def carregar(pasta: Path) -> dict:
    fluxos = {}
    for p in sorted(Path(pasta).glob("*.json")):
        wf = json.loads(p.read_text(encoding="utf-8"))
        c = codigo(wf.get("name", ""))
        if not c:
            raise ErroN8n("%s: nome '%s' não começa por Wnn" % (p.name, wf.get("name")))
        if c in fluxos:
            raise ErroN8n("dois arquivos com o fluxo %s" % c)
        fluxos[c] = wf
    return fluxos


def ordem_folhas_para_raiz(fluxos: dict) -> list:
    deps = {c: set(RE_WF.findall(json.dumps(wf))) - {c} for c, wf in fluxos.items()}
    ordem, feitos = [], set()
    while len(ordem) < len(fluxos):
        prontos = sorted(c for c in fluxos if c not in feitos and deps[c] <= feitos | (deps[c] - set(fluxos)))
        if not prontos:
            raise ErroN8n("referência circular entre fluxos: %s" % sorted(set(fluxos) - feitos))
        ordem.extend(prontos)
        feitos.update(prontos)
    return ordem


def resolver(wf: dict, ids_wf: dict, ids_cred: dict, avisos: list) -> dict:
    """Troca placeholders por ids reais. Fluxo ausente é erro; credencial ausente, aviso."""
    def troca_wf(m):
        c = m.group(1)
        if c not in ids_wf:
            raise ErroN8n("%s referencia {{WF:%s}}, que não existe na instância nem na pasta"
                          % (wf["name"], c))
        return ids_wf[c]

    def troca_cred(m):
        nome = m.group(1)
        if nome not in ids_cred:
            avisos.append("credencial '%s' não existe: o nó publica com o id sentinela %s%s e "
                          "falha na execução com o motivo (rode n8n/bootstrap.py quando configurar)"
                          % (nome, SENTINELA, nome))
            return SENTINELA + nome
        return ids_cred[nome]

    bruto = json.dumps(wf, ensure_ascii=False)
    return json.loads(RE_CRED.sub(troca_cred, RE_WF.sub(troca_wf, bruto)))


def normalizar(wf: dict, chaves_settings) -> dict:
    nos = sorted(({k: n[k] for k in CHAVES_NO if k in n} for n in wf.get("nodes", [])),
                 key=lambda n: n["name"])
    settings = wf.get("settings") or {}
    return {"name": wf["name"], "nodes": nos, "connections": wf.get("connections", {}),
            "settings": {k: settings.get(k) for k in chaves_settings}}


def corpo(wf: dict) -> dict:
    return {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": wf.get("settings", {})}


def publicar_fluxo(api: N8n, wid: str) -> bool:
    atual = api.workflow(wid)
    if atual.get("active") and atual.get("activeVersionId") == atual.get("versionId"):
        return False
    api.publica("POST", "/workflows/%s/publish" % wid, {"versionId": atual["versionId"]})
    return True


# o nome antigo continua valendo para os testes que publicam um fluxo por vez (test_nucleo, test_w01, test_w10_w11)
publicar = publicar_fluxo


def ler_publicar(texto: str):
    """`todos` | `nenhum` | lista de códigos separados por vírgula (`W20,W23`)."""
    t = (texto or "").strip().lower()
    if t in ("todos", "nenhum"):
        return t
    codigos = {c.strip().upper() for c in t.split(",") if c.strip()}
    invalidos = sorted(c for c in codigos if not re.fullmatch(r"W\d{2}", c))
    if invalidos or not codigos:
        raise ValueError("--publicar: use todos, nenhum ou códigos como W20,W23 (inválido: %s)"
                         % (", ".join(invalidos) or texto))
    return codigos


def _deve_publicar(publicar, nome: str) -> bool:
    if publicar == "todos":
        return True
    if publicar == "nenhum":
        return False
    return codigo(nome) in publicar


def importar(pasta: Path | None = None, api: N8n | None = None, publicar="todos") -> dict:
    pasta = Path(pasta) if pasta else PASTA_WORKFLOWS
    api = api or N8n.autenticado()
    fluxos = carregar(pasta)
    na_instancia = {w["name"]: w for w in api.listar_workflows()}
    ids_wf = {codigo(n): w["id"] for n, w in na_instancia.items() if codigo(n)}
    ids_cred = {c["name"]: c["id"] for c in api.listar_credenciais()}

    rel = {}
    for c in ordem_folhas_para_raiz(fluxos):
        avisos: list = []
        wf = resolver(fluxos[c], ids_wf, ids_cred, avisos)
        existente = na_instancia.get(wf["name"])
        if existente is None:
            criado = api.publica("POST", "/workflows", corpo(wf))
            wid, acao = criado["id"], "criado"
            ids_wf[c] = wid
        else:
            wid = existente["id"]
            chaves = list((wf.get("settings") or {}).keys())
            if normalizar(api.workflow(wid), chaves) == normalizar(wf, chaves):
                acao = "inalterado"
            else:
                api.publica("PUT", "/workflows/" + wid, corpo(wf))
                acao = "atualizado"
        if not _deve_publicar(publicar, wf["name"]):
            rel[wf["name"]] = {"id": wid, "acao": acao, "publicado": bool(api.workflow(wid).get("active")),
                               "avisos": sorted(set(avisos))}
            continue
        try:
            republicado = publicar_fluxo(api, wid)
        except ErroN8n as e:
            # Recusa de publicação é informação, não exceção muda: vai no relatório.
            rel[wf["name"]] = {"id": wid, "acao": acao, "publicado": False, "erro": str(e)[:300],
                               "avisos": sorted(set(avisos))}
            continue
        if republicado and acao == "inalterado":
            acao = "publicado"
        rel[wf["name"]] = {"id": wid, "acao": acao, "publicado": bool(api.workflow(wid).get("active")),
                           "avisos": sorted(set(avisos))}
    return rel


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--pasta", default=str(PASTA_WORKFLOWS))
    ap.add_argument("--publicar", default="todos", help="todos (padrão) | nenhum | W20,W21,... (stack local)")
    a = ap.parse_args()
    try:
        publicar = ler_publicar(a.publicar)
        rel = importar(Path(a.pasta), publicar=publicar)
    except (ErroN8n, ValueError) as e:
        print("ERRO:", e)
        return 1
    print(json.dumps(rel, ensure_ascii=False, indent=2))
    return 0 if all(r["publicado"] for n, r in rel.items() if _deve_publicar(publicar, n)) else 1


if __name__ == "__main__":
    sys.exit(main())
