# -*- coding: utf-8 -*-
"""
bootstrap.py — deixa o fopa-n8n utilizável sem abrir a UI (plano, seção 4).

Owner pela REST, com cookie e chave da API pública; credenciais por nome.
Tudo idempotente: a 2ª execução não cria nada; só confere e, se o docker/.env
mudou, reescreve o VALOR das credenciais no mesmo id (os fluxos apontam para o
id, então trocar a senha do n8n_rw não pode exigir reimportar fluxo).

1. OWNER. Se a instância pede setup, cria o dono com o e-mail do admin do
   projeto e senha aleatória gravada em n8n/.segredos/owner.json. Se já existe,
   só faz login. (Apagar owner.json NÃO recria o owner: ele está no banco `n8n`.)
2. CHAVE DA API PÚBLICA. Criada pela REST interna com todos os escopos e gravada
   em n8n/.segredos/api_key. A chave crua só aparece na criação: se o arquivo
   sumiu, a antiga é apagada e uma nova é criada — nunca fica chave órfã.
3. CREDENCIAIS (por nome; os fluxos as referenciam como {{CRED:nome}}):
     'fopa-postgres (n8n_rw)'  postgres       host fopa-postgres, banco fopa, n8n_rw
     'worker'                  httpHeaderAuth Authorization: Bearer FOPA_WORKER_TOKEN
     'site'                    httpHeaderAuth X-FOPA-Token: FOPA_SITE_TOKEN
     'smtp'                    smtp           SÓ se SMTP_HOST estiver preenchido
     'jev'                     httpHeaderAuth Authorization: Bearer JEV_API_KEY (SÓ se houver)
     'openai'                  httpHeaderAuth Authorization: Bearer OPENAI_API_KEY (SÓ se houver; docker/.env
                               ou, na falta, o .env da raiz) — o botão "Extrair com IA" do site (db/033)
     'anthropic'               anthropicApi   ANTHROPIC_API_KEY (SÓ se houver; docker/.env ou o .env da raiz) —
                               o mesmo botão com o Claude (db/037); o nó "Anthropic /v1/messages" do W23
   Sem SMTP_HOST a credencial não é criada e o relatório diz por quê: o W50
   então falha o envio e marca a linha 'falhou' (seção 5: nunca silêncio).
4. MCP. O servidor MCP é ligado por env no compose (N8N_MCP_MANAGED_BY_ENV);
   aqui só se busca o token do owner para um cliente MCP e ele vai para
   n8n/.segredos/mcp_token (docs/n8n-credenciais.md explica o uso).

Nenhum valor secreto é impresso: o relatório diz criada/existente/atualizada.

Uso (a partir da raiz):
    python n8n/bootstrap.py
"""
from __future__ import annotations

import hashlib
import json
import secrets
import string
import sys

import cliente
from cliente import ErroN8n, N8n

EMAIL_OWNER = "admin@exemplo.com"   # admin do projeto (usuarios, seed 012)
ROTULO_CHAVE = "fopa-scripts"


def _senha_forte() -> str:
    alfa = string.ascii_letters + string.digits + "!@#%^*-_=+"
    while True:
        p = "".join(secrets.choice(alfa) for _ in range(28))
        # o n8n exige 8-64 caracteres, ao menos um número e uma maiúscula
        if any(c.isdigit() for c in p) and any(c.isupper() for c in p):
            return p


def _dados_owner() -> dict:
    if cliente.ARQ_OWNER.exists():
        return json.loads(cliente.ARQ_OWNER.read_text(encoding="utf-8"))
    d = {"email": EMAIL_OWNER, "firstName": "FOPA", "lastName": "Admin", "password": _senha_forte()}
    cliente.gravar_segredo(cliente.ARQ_OWNER, json.dumps(d, indent=2))
    return d


def garantir_owner(api: N8n) -> str:
    s, cfg, _ = cliente._chamar(api.base + "/rest/settings", "GET", None, {})
    if s != 200:
        raise ErroN8n("/rest/settings devolveu HTTP %s" % s)
    owner = _dados_owner()
    if cfg["data"]["userManagement"]["showSetupOnFirstLoad"]:
        s, b, h = cliente._chamar(api.base + "/rest/owner/setup", "POST", owner,
                                  {"browser-id": cliente.BROWSER_ID})
        if s != 200:
            raise ErroN8n("criação do owner recusada: HTTP %s %s" % (s, str(b)[:200]))
        api.cookie = N8n.cookie_de(h)
        cliente.gravar_segredo(cliente.ARQ_COOKIE, api.cookie)
        return "criado"
    api.login()
    return "existente"


def garantir_api_key(api: N8n) -> str:
    chaves = api.listar_api_keys()
    ja = next((k for k in chaves if k.get("label") == ROTULO_CHAVE), None)
    if ja and cliente.ARQ_API_KEY.exists():
        api.api_key = cliente.ARQ_API_KEY.read_text(encoding="utf-8").strip()
        # Confere que a chave do arquivo é a que o n8n conhece (não uma de outro volume).
        api.publica("GET", "/workflows?limit=1")
        return "existente"
    if ja:
        api.interna("DELETE", "/rest/api-keys/" + ja["id"])
    escopos = api.interna("GET", "/rest/api-keys/scopes")
    d = api.interna("POST", "/rest/api-keys", {"label": ROTULO_CHAVE, "expiresAt": None, "scopes": escopos})
    api.api_key = d["rawApiKey"]
    cliente.gravar_segredo(cliente.ARQ_API_KEY, api.api_key)
    return "recriada" if ja else "criada"


def definicoes_credenciais(env: dict) -> dict:
    """nome -> (tipo, dados) ou (None, motivo) quando falta configuração."""
    faltando = [k for k in ("N8N_RW_PASSWORD", "FOPA_WORKER_TOKEN", "FOPA_SITE_TOKEN") if not env.get(k)]
    if faltando:
        raise ErroN8n("docker/.env sem %s" % ", ".join(faltando))
    defs = {
        # Nome do host do compose, nunca localhost: quem conecta é o container do n8n.
        "fopa-postgres (n8n_rw)": ("postgres", {
            "host": "fopa-postgres", "port": 5432, "database": "fopa", "user": "n8n_rw",
            "password": env["N8N_RW_PASSWORD"], "ssl": "disable", "allowUnauthorizedCerts": False,
            "maxConnections": 10, "sshTunnel": False}),
        "worker": ("httpHeaderAuth", {"name": "Authorization", "value": "Bearer " + env["FOPA_WORKER_TOKEN"]}),
        "site": ("httpHeaderAuth", {"name": "X-FOPA-Token", "value": env["FOPA_SITE_TOKEN"]}),
    }
    if env.get("SMTP_HOST"):
        porta = int(env.get("SMTP_PORT") or 587)
        defs["smtp"] = ("smtp", {
            "host": env["SMTP_HOST"], "port": porta, "user": env.get("SMTP_USER", ""),
            "password": env.get("SMTP_PASSWORD", ""),
            # 465 = TLS direto; 587 (Gmail com senha de app) = STARTTLS.
            "secure": porta == 465, "disableStartTls": False})
    else:
        defs["smtp"] = (None, "ausente: SMTP_HOST vazio no docker/.env (o W50 marca 'falhou' com o erro)")
    # O Jev (TypeSafe) é chamado pelo n8n, com credencial dele (o worker só monta
    # o corpo e interpreta a resposta; "Jev na v3"). Sem chave, o W01 pula o
    # score do filtro e diz por quê — o escopo continua sendo a regra (T25).
    if env.get("JEV_API_KEY"):
        defs["jev"] = ("httpHeaderAuth", {"name": "Authorization", "value": "Bearer " + env["JEV_API_KEY"]})
    else:
        defs["jev"] = (None, "ausente: JEV_API_KEY vazio no docker/.env (o W01 não calcula o score do filtro)")
    # A OpenAI do W23 (provedor `openai`): o botão "Extrair com GPT" do site pede para UMA licitação (db/033).
    if env.get("OPENAI_API_KEY"):
        defs["openai"] = ("httpHeaderAuth", {"name": "Authorization", "value": "Bearer " + env["OPENAI_API_KEY"]})
    else:
        defs["openai"] = (None, "ausente: OPENAI_API_KEY vazio (o W23 não extrai com o GPT)")
    # O Claude do W23 (provedor `claude`): o mesmo botão, com a escolha "Claude" (db/037). O nó usa a credencial
    # predefinida do n8n (anthropicApi), que manda x-api-key e a versão da API.
    if env.get("ANTHROPIC_API_KEY"):
        defs["anthropic"] = ("anthropicApi", {"apiKey": env["ANTHROPIC_API_KEY"]})
    else:
        defs["anthropic"] = (None, "ausente: ANTHROPIC_API_KEY vazio (o W23 não extrai com o Claude)")
    return defs


CAMPOS_SECRETOS = {"password", "value", "apiKey"}


def _impressao(dados: dict) -> str:
    """sha256 do que foi gravado: compara segredo sem guardar nem ler o segredo."""
    return hashlib.sha256(json.dumps(dados, sort_keys=True).encode("utf-8")).hexdigest()


def garantir_credenciais(api: N8n, env: dict) -> dict:
    existentes = {c["name"]: c for c in api.listar_credenciais()}
    impressoes = json.loads(cliente.ARQ_IMPRESSOES.read_text(encoding="utf-8")) \
        if cliente.ARQ_IMPRESSOES.exists() else {}
    rel = {}
    for nome, (tipo, dados) in definicoes_credenciais(env).items():
        if tipo is None:
            rel[nome] = dados
            continue
        ja = existentes.get(nome)
        if ja is None:
            api.publica("POST", "/credentials", {"name": nome, "type": tipo, "data": dados})
            impressoes[nome] = _impressao(dados)
            rel[nome] = "criada"
            continue
        if ja["type"] != tipo:
            raise ErroN8n("credencial '%s' existe com tipo %s, esperado %s" % (nome, ja["type"], tipo))
        # A 2.37.10 devolve os campos secretos REDIGIDOS até para o owner, então o
        # segredo não se compara pela instância: compara-se a impressão do que
        # este script gravou (docker/.env mudou -> impressão muda) e os campos
        # não secretos contra a instância (alguém editou o host pela UI).
        atual = api.interna("GET", "/rest/credentials/%s?includeData=true" % ja["id"]).get("data") or {}
        publicos_iguais = all(atual.get(k) == v for k, v in dados.items() if k not in CAMPOS_SECRETOS)
        if publicos_iguais and impressoes.get(nome) == _impressao(dados):
            rel[nome] = "existente"
            continue
        # PATCH no mesmo id: os fluxos apontam para o id, nada a reimportar.
        api.publica("PATCH", "/credentials/" + ja["id"], {"name": nome, "type": tipo, "data": dados})
        impressoes[nome] = _impressao(dados)
        rel[nome] = "atualizada"
    cliente.gravar_segredo(cliente.ARQ_IMPRESSOES, json.dumps(impressoes, indent=2, sort_keys=True))
    return rel


def garantir_mcp(api: N8n) -> str:
    """Busca (ou cria) o token MCP do owner; o acesso MCP em si é ligado por env."""
    try:
        d = api.interna("GET", "/rest/mcp/api-key")
    except ErroN8n as e:
        return "indisponível (%s)" % str(e)[:120]
    token = d.get("apiKey") or d.get("rawApiKey") or ""
    if not token or "*" in token:
        # A instância só mostra a chave inteira na criação; se veio mascarada e
        # o arquivo local existe, o arquivo é a verdade.
        return "existente" if cliente.ARQ_MCP_TOKEN.exists() else "mascarado (gire em Settings > MCP)"
    novo = not cliente.ARQ_MCP_TOKEN.exists() or cliente.ARQ_MCP_TOKEN.read_text(encoding="utf-8").strip() != token
    if novo:
        cliente.gravar_segredo(cliente.ARQ_MCP_TOKEN, token)
    return "gravado" if novo else "existente"


def executar() -> dict:
    env = cliente.ler_env()
    # As chaves dos modelos moram no .env da raiz (o dos scripts); o docker/.env, se tiver, manda.
    raiz = cliente.ler_env(cliente.RAIZ / ".env")
    for chave in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        if not env.get(chave) and raiz.get(chave):
            env[chave] = raiz[chave]
    api = N8n()
    rel = {"owner": garantir_owner(api)}
    rel["api_key"] = garantir_api_key(api)
    rel["credenciais"] = garantir_credenciais(api, env)
    rel["mcp_token"] = garantir_mcp(api)
    return rel


def main() -> int:
    if not cliente.no_ar():
        print("ERRO: fopa-n8n fora do ar em %s (docker compose up -d fopa-n8n)" % cliente.base())
        return 1
    try:
        rel = executar()
    except ErroN8n as e:
        print("ERRO:", e)
        return 1
    print(json.dumps(rel, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
