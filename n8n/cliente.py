# -*- coding: utf-8 -*-
"""
Cliente mínimo das duas APIs do n8n da FOPA (fopa-n8n, 127.0.0.1:5679).

Duas regras de propósito:

  - a chave da API pública NUNCA fica no código (o plano, seção 5 "Versionamento
    dos fluxos", proíbe chave fixa): ela vem de `n8n/.segredos/api_key`
    (gitignorado) ou da env N8N_API_KEY;
  - nada daqui imprime segredo. Erros mostram status e um trecho do corpo da
    resposta do n8n, nunca o que foi enviado.

Por que DUAS APIs:
  - a pública (`/api/v1`, header X-N8N-API-KEY) cobre workflows, credenciais e
    publicação — é o caminho estável, documentado no openapi.yml da 2.37.10;
  - a interna (`/rest`, cookie de sessão + header browser-id) é a única que
    cria o owner, cria a própria chave da API pública, executa um fluxo
    manualmente e lê a execução nó a nó. Ela muda entre versões: o cliente usa só o
    que foi conferido na 2.37.10.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
ARQ_ENV = RAIZ / "docker" / ".env"

# Tudo que é segredo gerado aqui mora nesta pasta (gitignorada: n8n/.segredos/).
DIR_SEGREDOS = AQUI / ".segredos"
ARQ_OWNER = DIR_SEGREDOS / "owner.json"
ARQ_API_KEY = DIR_SEGREDOS / "api_key"
ARQ_COOKIE = DIR_SEGREDOS / "cookie"
ARQ_MCP_TOKEN = DIR_SEGREDOS / "mcp_token"
# sha256 do que o bootstrap gravou em cada credencial (o n8n redige o segredo na leitura).
ARQ_IMPRESSOES = DIR_SEGREDOS / "credenciais.sha256.json"

# O n8n amarra o cookie de sessão a este header: tem de ser o mesmo em toda
# chamada da REST interna, senão a sessão é recusada como roubada.
BROWSER_ID = "fopa-n8n-scripts"

# Mesmo padrão do compose (FOPA_TESSDATA_SHA256): o W00 compara contra ele.
TESSDATA_SHA256_PADRAO = "c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb"


class ErroN8n(RuntimeError):
    """Resposta inesperada do n8n. A mensagem nunca carrega o corpo enviado."""


def ler_env(caminho: Path = ARQ_ENV) -> dict:
    """Lê docker/.env sem despejar no ambiente (mesma regra do compose: por nome)."""
    d: dict = {}
    if not caminho.exists():
        return d
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        d[k.strip()] = v
    return d


def base() -> str:
    # Porta do host da stack FOPA. 5678 é de outra stack n8n da máquina: nunca o padrão.
    return os.environ.get("FOPA_N8N_URL", "http://127.0.0.1:5679").rstrip("/")


def _ler(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def gravar_segredo(p: Path, conteudo: str) -> None:
    DIR_SEGREDOS.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo, encoding="utf-8")


def _chamar(url: str, method: str, data, headers: dict, timeout: int = 60):
    corpo = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=corpo, method=method,
                                 headers={"Content-Type": "application/json; charset=utf-8",
                                          "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8")
            return r.status, (json.loads(txt) if txt else {}), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500], e.headers


def no_ar() -> bool:
    try:
        with urllib.request.urlopen(base() + "/healthz/readiness", timeout=5) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _dados(b):
    """A REST interna embrulha em {data: ...}; a pública, às vezes, não."""
    return b.get("data", b) if isinstance(b, dict) else b


class N8n:
    def __init__(self, url_base: str | None = None, api_key: str = "", cookie: str = ""):
        self.base = (url_base or base()).rstrip("/")
        self.api_key = api_key
        self.cookie = cookie

    # --------------------------------------------------------------- sessão
    @classmethod
    def autenticado(cls) -> "N8n":
        """Chave de .segredos (ou N8N_API_KEY) + sessão da REST interna."""
        chave = _ler(ARQ_API_KEY) or os.environ.get("N8N_API_KEY", "")
        if not chave:
            raise ErroN8n("sem chave da API: rode `python n8n/bootstrap.py` antes")
        api = cls(api_key=chave)
        api.login()
        return api

    def sessao_valida(self) -> bool:
        if not self.cookie:
            return False
        s, _, _ = _chamar(self.base + "/rest/login", "GET", None,
                          {"Cookie": self.cookie, "browser-id": BROWSER_ID})
        return s == 200

    def login(self) -> None:
        """Reaproveita o cookie guardado enquanto ele valer.

        O POST /rest/login tem limite de taxa (HTTP 429 depois de poucas
        tentativas por minuto): logar a cada chamada derruba a suíte de testes
        e qualquer script que rode em sequência. O cookie dura dias.
        """
        self.cookie = _ler(ARQ_COOKIE)
        if self.sessao_valida():
            return
        owner = json.loads(_ler(ARQ_OWNER) or "{}")
        if not owner:
            raise ErroN8n("sem %s: rode `python n8n/bootstrap.py` antes" % ARQ_OWNER.name)
        s, b, h = _chamar(self.base + "/rest/login", "POST",
                          {"emailOrLdapLoginId": owner["email"], "password": owner["password"]},
                          {"browser-id": BROWSER_ID})
        if s != 200:
            raise ErroN8n("login recusado: HTTP %s %s" % (s, str(b)[:200]))
        self.cookie = self.cookie_de(h)
        gravar_segredo(ARQ_COOKIE, self.cookie)

    @staticmethod
    def cookie_de(headers) -> str:
        bruto = headers.get_all("Set-Cookie") or []
        ck = next((c.split(";")[0] for c in bruto if c.startswith("n8n-auth")), "")
        if not ck:
            raise ErroN8n("o n8n não devolveu cookie de sessão")
        return ck

    # --------------------------------------------------------------- chamadas
    def publica(self, method: str, path: str, data=None, ok=(200, 201)):
        if not self.api_key:
            raise ErroN8n("chamada à API pública sem chave")
        s, b, _ = _chamar(self.base + "/api/v1" + path, method, data, {"X-N8N-API-KEY": self.api_key})
        if s not in ok:
            raise ErroN8n("%s /api/v1%s -> HTTP %s %s" % (method, path, s, str(b)[:300]))
        return b

    def interna(self, method: str, path: str, data=None, ok=(200, 201), timeout: int = 60):
        if not self.cookie:
            raise ErroN8n("chamada à REST interna sem cookie (faça login)")
        s, b, _ = _chamar(self.base + path, method, data,
                          {"Cookie": self.cookie, "browser-id": BROWSER_ID}, timeout=timeout)
        if s not in ok:
            raise ErroN8n("%s %s -> HTTP %s %s" % (method, path, s, str(b)[:300]))
        return _dados(b)

    # --------------------------------------------------------------- leitura
    def _paginado(self, path: str) -> list:
        itens, cursor = [], None
        while True:
            sep = "&" if "?" in path else "?"
            b = self.publica("GET", path + sep + "limit=250" + ("&cursor=" + cursor if cursor else ""))
            itens.extend(b.get("data", []))
            cursor = b.get("nextCursor")
            if not cursor:
                return itens

    def listar_workflows(self) -> list:
        return self._paginado("/workflows")

    def workflow(self, wid: str) -> dict:
        return self.publica("GET", "/workflows/" + wid)

    def listar_credenciais(self) -> list:
        return self._paginado("/credentials")

    def listar_api_keys(self) -> list:
        d = self.interna("GET", "/rest/api-keys")
        # 2.37.10 devolve {items: [...], count}; versões antigas, a lista crua.
        return d.get("items", []) if isinstance(d, dict) else d
