# -*- coding: utf-8 -*-
"""
API do site da FOPA v3 — FastAPI, `127.0.0.1:8080` (plano, seções 4 e 8).

O QUE ESTE PROCESSO FAZ
  - login Google (`oauth.py`) ou, só na demo sem rede, o modo local;
  - sessão em cookie assinado + tabela `sessoes` (`sessao.py`);
  - leitura do Postgres como `api_rw` (SQL em `consultas.py`) — o site LÊ
    tudo, mas só ESCREVE as tabelas dele: usuarios, sessoes,
    revisoes_humanas, rotulos_escopo, orcamento, termos, configuracao e a
    reserva de demo (GRANTs da 016). Respostas, verificações, escopo e estado
    são do worker e do n8n; o Jev (017) é sinal mostrado ao lado, nunca decide;
  - serve os PDFs e o RELATORIO.html do storage atrás do login;
  - repassa as ações ("verificar", "processar", "reverificar") aos webhooks do
    n8n pelo hostname interno do compose — o site nunca processa nada sozinho;
  - serve o build do React (mesma origem: sem CORS, e o cookie vai junto).

PAPÉIS
  leitor lê; operador também dispara ações, vê a fila de revisão, decide
  revisões e rotula escopo; admin tudo.
  Toda `/api/*` exige sessão, exceto `/api/saude`. O PDF devolve 401 SEMPRE
  sem sessão, antes de olhar se o arquivo existe (LGPD: edital traz nome e
  salário de servidor, e nem a existência de um id deve vazar).

ERROS
  Dependência fora do ar (Postgres, n8n, worker) é 503 com a mensagem de
  QUAL peça caiu, nunca 500: a tela de ação e a de saúde mostram a mensagem
  como veio, e "Internal Server Error" não diz nada a quem está usando o site.
  Banco sem a migração que a rota lê (função/tabela inexistente) também é
  503, com o nome do objeto. Resposta do worker que não é JSON é 502.

Rodar local: `uvicorn api.site:app --port 8080` a partir da raiz do repositório.
"""
from __future__ import annotations

import hmac
import concurrent.futures
import html
import mimetypes
import os
import re
from datetime import date
from typing import Any, Literal
from urllib.parse import quote, unquote, urlsplit

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator

from . import analytics, config, consultas, modelos_ia, oauth, sessao, storage as storage_mod

TIMEOUT_WORKER = 5.0
TIMEOUT_POSTGRES = 5
# O W11 responde imediatamente (Respond to Webhook antes do trabalho): 15 s
# é folga para o n8n acordar, não para esperar processamento.
TIMEOUT_N8N = 15.0
# /healthz do n8n na saúde: 2 s. O healthcheck do compose desiste em 5 s e soma
# worker + Postgres + n8n; o n8n lento não pode custar o "healthy" do site.
TIMEOUT_N8N_SAUDE = 2.0
# O timeout do httpx não cobre o DNS (getaddrinfo bloqueia fora dele: ~2,7 s
# para `fopa-n8n` fora do compose, medido no Windows). O limite de verdade é
# do relógio: a sonda roda aqui e a resposta não a espera além do prazo.
_SONDA_N8N = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="sonda-n8n")

# O RELATORIO é HTML montado de texto de edital (conteúdo de terceiros), servido
# na MESMA origem do site e atrás do login. `sandbox` sem allow-scripts dá a ele
# origem opaca: mesmo que um trecho escapasse do escape do pagina.py, não roda
# script nem usa a sessão de quem abriu contra a API. A política é a do que ele
# USA (test_relatorio_real_renderiza_sob_a_csp): só <style> e style="" inline;
# fonte por nome (IBM Plex instalada ou system-ui, sem @font-face); nenhum
# script, imagem, formulário ou recurso externo. Links (PDF #page, PNCP,
# voltar) são navegação, que a CSP não bloqueia; nenhum abre outra aba.
CSP_RELATORIO = ("sandbox; default-src 'none'; style-src 'unsafe-inline'; base-uri 'none';"
                 " form-action 'none'; frame-ancestors 'self'")

RE_CONTROLE = re.compile(r"^\d{14}-\d+-\d+/\d{4}$")
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NIVEL = {"leitor": 1, "operador": 2, "admin": 3}
PROVEDORES = ("simulado", "gravado", "claude", "openai")
PROVEDORES_PAGOS = ("claude", "openai")
MAX_CONTROLES_POR_ACAO = 20        # o Code do W11 recusa mais que isso (plano, seção 5)
AVISO_CUSTO = "~R$ 3-4 por edital (custo medido)"

app = FastAPI(title="fopa-api", docs_url=None, redoc_url=None, openapi_url=None)
# Transportes injetáveis (httpx.MockTransport nos testes); None = rede de verdade.
app.state.transporte_worker = None
app.state.transporte_n8n = None
app.state.transporte_google = None


# ====================================================================== saúde
def checar_worker(url_base: str | None, transporte: httpx.BaseTransport | None = None) -> dict:
    if not url_base:
        return {"ok": False, "erro": "FOPA_WORKER_URL não definido"}
    try:
        with httpx.Client(timeout=TIMEOUT_WORKER, transport=transporte) as cliente:
            resposta = cliente.get(url_base.rstrip("/") + "/health")
    except httpx.HTTPError as e:
        # `str(e)` de erro de conexão é curto e não carrega segredo; a URL do
        # worker é interna ao compose.
        return {"ok": False, "erro": "%s: %s" % (type(e).__name__, e)}
    try:
        corpo = resposta.json()
    except ValueError:
        corpo = None
    ok = resposta.status_code == 200 and isinstance(corpo, dict) and corpo.get("ok") is True
    return {"ok": ok, "status": resposta.status_code, "health": corpo}


def _sem_segredo_de_url(texto: str, url: str) -> str:
    """Tira da mensagem a URL configurada e qualquer `usuario:senha@` (a URL pode levar credencial)."""
    texto = texto.replace(url.rstrip("/"), "<FOPA_N8N_URL>")
    partes = urlsplit(url)
    for segredo in (partes.password, partes.password and unquote(partes.password)):
        if segredo:
            texto = texto.replace(segredo, "***")
    return re.sub(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@]+@", r"\1***@", texto)


def _healthz_n8n(url_base: str, transporte: httpx.BaseTransport | None) -> dict:
    try:
        with httpx.Client(timeout=TIMEOUT_N8N_SAUDE, transport=transporte) as cliente:
            resposta = cliente.get(url_base.rstrip("/") + "/healthz")
    except Exception as e:  # noqa: BLE001 — URL inválida, DNS, recusa, timeout: tudo é "fora"
        return {"ok": False, "erro": _sem_segredo_de_url("%s: %s" % (type(e).__name__, e), url_base)}
    if resposta.status_code != 200:
        return {"ok": False, "status": resposta.status_code,
                "erro": "/healthz respondeu HTTP %d" % resposta.status_code}
    return {"ok": True, "status": 200}


def checar_n8n(url_base: str | None, transporte: httpx.BaseTransport | None = None) -> dict:
    """
    `GET {FOPA_N8N_URL}/healthz` em no máximo 2 s de relógio → `{ok, status?,
    erro?}`. Qualquer falha vira ok=false com a mensagem (sem a URL), nunca
    exceção: é sonda.
    """
    if not url_base:
        return {"ok": None, "erro": "FOPA_N8N_URL não definido"}
    futuro = _SONDA_N8N.submit(_healthz_n8n, url_base, transporte)
    try:
        return futuro.result(timeout=TIMEOUT_N8N_SAUDE + 0.25)
    except concurrent.futures.TimeoutError:
        return {"ok": False, "erro": "o n8n não respondeu /healthz em %g s (DNS ou rede)" % TIMEOUT_N8N_SAUDE}


def _sondar_postgres(database_url: str | None, ler=None) -> tuple[dict, Any]:
    """
    Uma conexão só: confere `select 1` e, se pedido, lê com `ler(conexao)`
    (dict_row). Devolve `(estado, lido)`; lido é None quando algo falhou.
    """
    if not database_url:
        return {"ok": None, "erro": "DATABASE_URL não definido"}, None
    # Import tardio: o site tem de subir (e responder /api/saude) mesmo que o
    # driver esteja quebrado na imagem — aí a resposta diz isso, em vez de o
    # processo nem iniciar.
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as e:
        return {"ok": False, "erro": "psycopg indisponível: %s" % e}, None
    try:
        with psycopg.connect(database_url, connect_timeout=TIMEOUT_POSTGRES, row_factory=dict_row) as conexao:
            conexao.execute("select 1").fetchone()
            try:
                lido = ler(conexao) if ler else None
            except Exception as e:
                # Conecta mas não lê o que o site lê (GRANT, migração): o site
                # está tão quebrado quanto com o banco fora.
                return {"ok": False, "erro": "conecta, mas a leitura falhou: %s: %s"
                        % (type(e).__name__, str(e).strip().splitlines()[0] if str(e).strip() else "")}, None
    except Exception as e:
        # Só o tipo e a mensagem do driver: a URL (com senha) nunca entra aqui.
        return {"ok": False, "erro": "%s: %s" % (type(e).__name__, str(e).strip())}, None
    return {"ok": True}, lido


def checar_postgres(database_url: str | None) -> dict:
    return _sondar_postgres(database_url)[0]


def _marcos(conexao) -> dict:
    return {"ultima_coleta": consultas.ultima_coleta(conexao),
            "ultimo_alerta": consultas.ultimo_alerta(conexao)}


@app.get("/api/saude")
def saude(request: Request):
    """
    Sem sessão: é o que o healthcheck do compose e o W00 consultam.

    503 quando o Postgres ou o worker não respondem, com `caiu` dizendo quem.
    Antes era 200 sempre, e o compose marcava "healthy" um site que não
    conseguia ler nada (achado da revisão da F0). O corpo continua trazendo o
    detalhe de cada peça: o código diz "está ruim", o corpo diz "o quê".

    O n8n NÃO entra em `caiu`: o site lê tudo do Postgres e só precisa do n8n
    para disparar ações (que já respondem 503 com a mensagem certa). Se o n8n
    fora derrubasse o healthcheck, o compose reiniciaria um site sadio e a
    leitura se perderia junto. Ele vai para `avisos` (nomes, como
    `caiu`; o detalhe fica em `n8n`), e `ok` continua dizendo só do site.

    `ultima_coleta` é a mesma do `/api/resumo` (última rodada do W01 ou do
    monitor v2); `ultimo_alerta` é `{em, workflow, mensagem}` da última falha
    registrada — W90 (`execucoes_workflow` status 'erro') ou W00 (`saude` com
    o worker fora do contrato); ver `consultas.ultimo_alerta`. Os dois saem
    null quando o Postgres não responde.
    """
    cfg = config.carregar()
    worker = checar_worker(cfg.worker_url, request.app.state.transporte_worker)
    postgres, marcos = _sondar_postgres(cfg.database_url, _marcos)
    n8n = checar_n8n(cfg.n8n_url, request.app.state.transporte_n8n)
    caiu = [nome for nome, d in (("postgres", postgres), ("worker", worker)) if d.get("ok") is not True]
    avisos = [] if n8n.get("ok") is True else ["n8n"]
    marcos = marcos or {}
    corpo = {"ok": not caiu, "api_ok": True, "ambiente": cfg.ambiente, "auth_mode": cfg.auth_mode,
             "caiu": caiu, "avisos": avisos, "worker": worker, "postgres": postgres, "n8n": n8n,
             "ultima_coleta": marcos.get("ultima_coleta"), "ultimo_alerta": marcos.get("ultimo_alerta")}
    if cfg.ambiente == "prod" and not _tem_sessao(request, cfg):
        # Em produção a rota é pública (healthcheck), mas mensagem de erro
        # interna, última coleta e versões são para quem entrou.
        corpo = {"ok": corpo["ok"], "caiu": caiu, "avisos": avisos}
    return JSONResponse(jsonable_encoder(corpo), status_code=503 if caiu else 200)


def _tem_sessao(request: Request, cfg) -> bool:
    """Sessão válida, sem levantar nada: qualquer falha (sem cookie, forjado, banco fora) é "não"."""
    valor = request.cookies.get(sessao.NOME_COOKIE)
    if not valor or not cfg.session_secret or not sessao.assinatura_valida(valor, cfg.session_secret):
        return False
    db = Banco(cfg.database_url)
    try:
        return sessao.ler(db.conn, valor, cfg.session_secret) is not None
    except Exception:
        return False
    finally:
        db.fechar()


# ====================================================================== banco
class Banco:
    """
    Conexão aberta só no primeiro uso. Assim uma rota que recusa por falta de
    cookie (401) nem toca no Postgres — e o 401 do PDF sai igual com o banco
    no ar ou fora dele.
    """

    def __init__(self, url: str | None):
        self.url = url
        self._conn = None

    @property
    def conn(self):
        if self._conn is None:
            if not self.url:
                raise HTTPException(503, "Configuração incompleta: DATABASE_URL não está definida no serviço do site (fopa-api).")
            import psycopg
            from psycopg.rows import dict_row
            try:
                self._conn = psycopg.connect(self.url, row_factory=dict_row,
                                             connect_timeout=TIMEOUT_POSTGRES)
            except psycopg.OperationalError as e:
                # Nunca a mensagem inteira: psycopg repete host e usuário.
                raise HTTPException(503, "Banco de dados (Postgres) indisponível (%s). Tente novamente em instantes."
                                    % type(e).__name__) from None
        return self._conn

    def commit(self):
        self.conn.commit()

    def fechar(self):
        if self._conn is not None:
            try:
                self._conn.close()          # sem commit: escrita sem commit explícito é descartada
            finally:
                self._conn = None


def banco():
    db = Banco(config.carregar().database_url)
    try:
        yield db
    finally:
        db.fechar()


@app.exception_handler(config.ConfigInvalida)
async def _config_invalida(request: Request, exc: config.ConfigInvalida):
    # Variável inválida (FOPA_ENV, STORAGE_BACKEND...) caía no handler genérico como "erro interno:
    # ConfigInvalida" (500). É 503 dizendo qual e o que ela aceita — escolhas e números, nunca segredo.
    return JSONResponse({"detail": "Configuração inválida: %s" % exc}, status_code=503)


@app.exception_handler(Exception)
async def _erro_de_banco(request: Request, exc: Exception):
    # Postgres que cai NO MEIO da requisição (depois de conectar) também é
    # 503 com mensagem, não 500. Qualquer outra exceção segue como 500, só com
    # o tipo — o traceback fica no log do uvicorn, não na resposta.
    try:
        import psycopg
        if isinstance(exc, psycopg.OperationalError):
            return JSONResponse({"detail": "Banco de dados (Postgres) indisponível (%s). Tente novamente em instantes." % type(exc).__name__},
                                status_code=503)
        if isinstance(exc, (psycopg.errors.UndefinedFunction, psycopg.errors.UndefinedTable,
                            psycopg.errors.UndefinedColumn)):
            # Código novo com banco velho (ex.: recorte/Jev antes das migrações
            # 017/018): diz o objeto que falta e o remédio. A 1ª linha da
            # mensagem do Postgres só nomeia o objeto — nada de host ou senha.
            texto = str(exc).strip()
            return JSONResponse({"detail": "O banco de dados não tem o objeto que esta rota consulta (%s). Aplique as "
                                           "migrações pendentes (docker compose run --rm fopa-migrate)."
                                           % (texto.splitlines()[0] if texto else type(exc).__name__)},
                                status_code=503)
    except ImportError:
        pass
    return JSONResponse({"detail": "Erro interno (%s). Tente novamente em instantes." % type(exc).__name__}, status_code=500)


# ====================================================================== sessão e papéis
def _seguro(cfg) -> bool:
    return cfg.ambiente == "prod"


def usuario_atual(request: Request, db: Banco = Depends(banco)) -> dict:
    cfg = config.carregar()
    valor = request.cookies.get(sessao.NOME_COOKIE)
    if not valor:
        raise HTTPException(401, "Sessão não encontrada. Faça login para continuar.")
    if not cfg.session_secret:
        raise HTTPException(503, "Configuração incompleta: SESSION_SECRET não está definido no serviço do site (fopa-api).")
    # A assinatura é conferida ANTES do banco: cookie forjado não vira consulta.
    if not sessao.assinatura_valida(valor, cfg.session_secret):
        raise HTTPException(401, "Sessão inválida ou expirada. Faça login novamente.")
    usuario = sessao.ler(db.conn, valor, cfg.session_secret)
    if usuario is None:
        raise HTTPException(401, "Sessão encerrada ou expirada. Faça login novamente.")
    return usuario


def exigir(papel: str):
    def _dep(usuario: dict = Depends(usuario_atual)) -> dict:
        if NIVEL.get(usuario["papel"], 0) < NIVEL[papel]:
            raise HTTPException(403, "Esta ação requer o perfil %s. Seu perfil atual é %s." % (papel, usuario["papel"]))
        return usuario
    return _dep


leitor = exigir("leitor")
# Quem revisa RESPOSTAS (a fila e a decisão): até 26/09 era o operador; desde 27/09 é qualquer usuário logado
# (ADR-021, emenda de 27/09). A revisão de ESCOPO (os rótulos) é só do admin. O papel operador continua no banco,
# mas hoje não abre nada a mais que o usuário.
revisor = leitor
admin = exigir("admin")


def so_supremo(usuario: dict = Depends(admin)) -> dict:
    """O admin supremo (db/046): o único que dá e tira acesso — o admin normal só vê a lista."""
    if not usuario.get("supremo"):
        raise HTTPException(403, "Somente o administrador supremo altera usuários e perfis.")
    return usuario


def _pagina(status: int, titulo: str, texto: str) -> HTMLResponse:
    """Página mínima para as respostas de NAVEGAÇÃO (login, callback): o navegador mostra HTML."""
    corpo = ("<!doctype html><html lang=pt-BR><meta charset=utf-8><title>FOPA · %s</title>"
             "<body style='font-family:system-ui;max-width:36rem;margin:4rem auto;padding:0 1rem'>"
             "<h1 style='font-size:1.3rem'>%s</h1><p>%s</p><p><a href='/login'>Voltar ao login</a></p>"
             % (html.escape(titulo), html.escape(titulo), html.escape(texto)))
    return HTMLResponse(corpo, status_code=status)


def _entrar(db: Banco, email: str, cfg) -> RedirectResponse:
    valor = sessao.emitir(db.conn, email, cfg.session_secret)
    db.commit()
    resposta = RedirectResponse("/", status_code=303)
    sessao.gravar_cookie(resposta, valor, _seguro(cfg))
    return resposta


# ====================================================================== login
@app.get("/login")
def login(db: Banco = Depends(banco)):
    cfg = config.carregar()
    if cfg.auth_mode == "local":
        # O modo local libera o admin sem Google. Fora da demo (Wi-Fi
        # desligado na demonstração) isso seria um site aberto: recusa alto.
        if cfg.ambiente != "demo":
            return _pagina(403, "Login local recusado",
                           "FOPA_AUTH_MODE=local só é aceito com FOPA_ENV=demo (ambiente atual: %s). "
                           "Use FOPA_AUTH_MODE=google." % cfg.ambiente)
        if not cfg.session_secret:
            return _pagina(503, "Login indisponível", "SESSION_SECRET não configurado no fopa-api.")
        linha = db.conn.execute("SELECT email FROM usuarios WHERE papel = 'admin' AND ativo"
                                " ORDER BY email LIMIT 1").fetchone()
        if linha is None:
            return _pagina(503, "Login indisponível", "Nenhum admin ativo semeado em usuarios (012_seed).")
        return _entrar(db, linha["email"], cfg)
    return RedirectResponse("/auth/google/login", status_code=307)


@app.get("/auth/google/login")
def google_login(request: Request):
    cfg = config.carregar()
    try:
        url, estado = oauth.iniciar(cfg)
    except oauth.FalhaOAuth as e:
        return _pagina(e.status, "Login Google indisponível", str(e))
    resposta = RedirectResponse(url, status_code=302)
    resposta.set_cookie(oauth.COOKIE_ESTADO, estado, max_age=oauth.VALIDADE_ESTADO_S,
                        path=oauth.CAMINHO_COOKIE, httponly=True, samesite="lax", secure=_seguro(cfg))
    return resposta


@app.get("/auth/google/callback")
def google_callback(request: Request, code: str | None = None, state: str | None = None,
                    error: str | None = None, db: Banco = Depends(banco)):
    cfg = config.carregar()

    def falha(status, titulo, texto):
        r = _pagina(status, titulo, texto)
        r.delete_cookie(oauth.COOKIE_ESTADO, path=oauth.CAMINHO_COOKIE)
        return r

    if error:
        return falha(400, "Login cancelado", "O Google devolveu: %s." % error)
    try:
        claims = oauth.concluir(cfg, code, state, request.cookies.get(oauth.COOKIE_ESTADO),
                                request.app.state.transporte_google)
    except oauth.FalhaOAuth as e:
        return falha(e.status, "Login recusado", str(e))
    email = claims["email"]
    linha = db.conn.execute("SELECT email, ativo FROM usuarios WHERE lower(email) = %s", (email,)).fetchone()
    if linha is None:
        # Conta nova vira usuário — o papel de menor acesso. Dar mais é com o admin supremo, no Admin.
        db.conn.execute("INSERT INTO usuarios (email, nome, papel, ativo) VALUES (%s, %s, 'leitor', true)"
                        " ON CONFLICT (email) DO NOTHING", (email, (claims.get("name") or None)))
        db.commit()
        linha = db.conn.execute("SELECT email, ativo FROM usuarios WHERE lower(email) = %s", (email,)).fetchone()
    if not linha["ativo"]:
        # Desativado pelo admin: a conta Google é válida, mas o acesso foi tirado.
        return falha(403, "Acesso não liberado",
                     "A conta %s está sem acesso ao FOPA. Peça acesso ao administrador." % email)
    resposta = _entrar(db, linha["email"], cfg)
    resposta.delete_cookie(oauth.COOKIE_ESTADO, path=oauth.CAMINHO_COOKIE)
    return resposta


@app.post("/auth/sair")
def sair(request: Request, db: Banco = Depends(banco)):
    cfg = config.carregar()
    valor = request.cookies.get(sessao.NOME_COOKIE)
    if valor and cfg.session_secret:
        sessao.encerrar(db.conn, valor, cfg.session_secret)
        db.commit()
    resposta = JSONResponse({"ok": True})
    sessao.apagar_cookie(resposta, _seguro(cfg))
    return resposta


@app.get("/api/me")
def me(usuario: dict = Depends(leitor)):
    return {"email": usuario["email"], "papel": usuario["papel"], "nome": usuario["nome"],
            "supremo": bool(usuario.get("supremo"))}


# ====================================================================== leitura
Filtro = Literal[tuple(consultas.FILTROS)]  # type: ignore[valid-type]
Estado = Literal[consultas.ESTADOS]          # type: ignore[valid-type]
# ADR-015: por padrão só o recorte (fn_no_recorte da 018); `todos` mostra tudo.
Recorte = Literal[consultas.RECORTES]        # type: ignore[valid-type]
Situacao = Literal[consultas.SITUACOES]      # type: ignore[valid-type]


def _datas(de: date | None, ate: date | None) -> None:
    if de and ate and de > ate:
        raise HTTPException(422, "A data inicial (%s) é posterior à data final (%s)." % (de, ate))


@app.get("/api/resumo")
def resumo(usuario: dict = Depends(leitor), db: Banco = Depends(banco), recorte: Recorte = "ano_minimo",
           situacao: Situacao = "todas", de: date | None = None, ate: date | None = None,
           so_fopa_ia: bool = False):
    _datas(de, ate)
    return consultas.resumo(db.conn, recorte=recorte, situacao=situacao, de=de, ate=ate, so_fopa_ia=so_fopa_ia)


@app.get("/api/licitacoes")
def licitacoes(usuario: dict = Depends(leitor), db: Banco = Depends(banco),
               q: str | None = Query(None, max_length=200), estado: Estado | None = None,
               uf: str | None = Query(None, max_length=2), modalidade: str | None = Query(None, max_length=120),
               filtro: list[Filtro] = Query(["todas"]), vence_em: int | None = None,
               recorte: Recorte = "ano_minimo",
               situacao: Situacao = "todas", de: date | None = None, ate: date | None = None,
               so_fopa_ia: bool = False,
               page: int = Query(1, ge=1), por_pagina: int = Query(50, ge=1, le=200)):
    _datas(de, ate)
    if vence_em is not None and vence_em not in consultas.VENCIMENTOS:
        raise HTTPException(422, "O vencimento deve ser de 7, 15, 30, 45 ou 60 dias.")
    return consultas.listar_licitacoes(db.conn, q=q, estado=estado, uf=uf, modalidade=modalidade,
                                       filtro=filtro, vence_em=vence_em, recorte=recorte, situacao=situacao,
                                       page=page, por_pagina=por_pagina, de=de, ate=ate, so_fopa_ia=so_fopa_ia)


@app.get("/api/analytics")
def analytics_(usuario: dict = Depends(leitor), db: Banco = Depends(banco),
               escopo: Literal[analytics.ESCOPOS] = "dentro",   # type: ignore[valid-type]
               ano: int | None = Query(None, ge=2000, le=2100), de: date | None = None,
               ate: date | None = None, so_fopa_ia: bool = False):
    """
    Histórico de compra e venda da folha, pela API do PNCP (db/027): ranking de bancos, compras por
    mês e quem comprou, editais sem comprador publicados de novo. Aqui, e só aqui, o que está fora
    do escopo de folha pode entrar (`escopo=todos`, a caixa "mostrar fora do escopo").
    """
    _datas(de, ate)
    return analytics.montar(db.conn, escopo=escopo, ano=ano, de=de, ate=ate, so_fopa_ia=so_fopa_ia)


@app.get("/api/analytics/compras")
def analytics_compras(usuario: dict = Depends(leitor), db: Banco = Depends(banco),
                      escopo: Literal[analytics.ESCOPOS] = "dentro",   # type: ignore[valid-type]
                      banco_cnpj: str | None = Query(None, alias="banco", pattern=r"^\d{8}(\d{6})?$"),
                      de: date | None = None, ate: date | None = None, so_fopa_ia: bool = False):
    """
    O que cada instituição financeira comprou: a lista do filtro pesquisável e, com `banco`
    (CNPJ-raiz ou CNPJ), as compras dele — licitação, rodada de publicação, preço, data da compra e o contrato. O
    período olha a data da compra; FOPA e fora do escopo como no resto do analytics.
    """
    _datas(de, ate)
    return analytics.compras_por_banco(db.conn, escopo=escopo, so_fopa_ia=so_fopa_ia, banco=banco_cnpj, de=de, ate=ate)


@app.get("/api/licitacoes/{slug}")
def licitacao(slug: str, usuario: dict = Depends(leitor), db: Banco = Depends(banco)):
    d = consultas.detalhe(db.conn, slug)
    if d is None:
        raise HTTPException(404, "Licitação %s não encontrada." % slug)
    return d


def _chave_do_uri(uri: str) -> str:
    """`html_uri` gravado pelo W24: a chave do storage, com ou sem prefixo de esquema."""
    for prefixo in ("fs://", "storage://", "s3://"):
        if uri.startswith(prefixo):
            uri = uri[len(prefixo):]
            break
    return uri.lstrip("/")


def _storage(request: Request):
    """Backend do STORAGE_BACKEND; no s3, com o transporte injetável (MockTransport nos testes)."""
    return storage_mod.abrir(config.carregar(), getattr(request.app.state, "transporte_s3", None))


@app.get("/api/licitacoes/{slug}/relatorio")
def relatorio(request: Request, slug: str, usuario: dict = Depends(leitor), db: Banco = Depends(banco)):
    # Mesmo no s3 o HTML passa pela API, nunca por redirect: a CSP sandbox
    # abaixo só vale servida desta origem, e os links `/api/pdf/...#page=N` do
    # RELATORIO são relativos — no host do bucket apontariam para o nada.
    pub = consultas.publicacao_vigente(db.conn, slug)
    if pub is None:
        raise HTTPException(404, "Licitação %s não encontrada." % slug)
    if not pub["html_uri"]:
        raise HTTPException(404, "O relatório desta licitação ainda não foi publicado: a verificação "
                                 "vigente ainda não tem publicação.")
    st = _storage(request)
    try:
        conteudo = st.get(_chave_do_uri(pub["html_uri"]))
    except (storage_mod.ObjetoInexistente, storage_mod.ChaveInvalida):
        raise HTTPException(404, "Publicação registrada, mas o relatório não está no armazenamento (storage).") from None
    except storage_mod.StorageIndisponivel as e:
        raise HTTPException(503, str(e)) from None
    return Response(conteudo, media_type="text/html; charset=utf-8",
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-cache",
                             "Content-Security-Policy": CSP_RELATORIO})


def _disposicao_inline(nome: str) -> str:
    """`inline` com o nome original, na mesma forma do FileResponse (RFC 6266/5987 se não for ASCII puro)."""
    citado = quote(nome)
    if citado != nome:
        return "inline; filename*=utf-8''%s" % citado
    return 'inline; filename="%s"' % nome


@app.get("/api/pdf/{slug}/{arquivo_id}")
def pdf(request: Request, slug: str, arquivo_id: int, usuario: dict = Depends(leitor),
        db: Banco = Depends(banco)):
    # `leitor` resolve ANTES do corpo: sem sessão é 401 sem tocar no banco nem no storage.
    arq = consultas.arquivo_do_slug(db.conn, slug, arquivo_id)
    if arq is None:
        raise HTTPException(404, "O arquivo %d não pertence à licitação %s." % (arquivo_id, slug))
    if not arq["storage_key"]:
        raise HTTPException(404, "Arquivo sem PDF no armazenamento (storage), com status %s." % arq["status"])
    st = _storage(request)
    if st.backend == "s3":
        # 302 para URL assinada de 10 min (plano, seção 8): os bytes vão do
        # bucket direto ao navegador, sem passar pela API. O `#page=N` nunca
        # chega ao servidor; como o Location não tem fragmento, o navegador
        # reaplica o da URL original ao destino (RFC 9110, 10.2.2) e o leitor
        # de PDF abre na página citada. `response-content-*` fazem o bucket
        # responder `application/pdf` + `inline`, o que abre em vez de baixar.
        try:
            if not st.existe(arq["storage_key"]):
                raise HTTPException(404, "PDF registrado, mas ausente do armazenamento (bucket). Verifique a "
                                         "sincronização do volume fopa_dados.")
            url = st.presign(arq["storage_key"], expira=storage_mod.PRESIGN_PADRAO_S,
                             tipo="application/pdf", disposicao=_disposicao_inline(arq["nome"]))
        except storage_mod.ChaveInvalida:
            raise HTTPException(404, "Chave de armazenamento inválida no banco (storage_key).") from None
        except storage_mod.StorageIndisponivel as e:
            raise HTTPException(503, str(e)) from None
        # no-store: a URL assinada expira em 10 min, e um redirect guardado
        # levaria a um 403 do bucket. no-referrer: o bucket não recebe a URL
        # da página do site.
        return RedirectResponse(url, status_code=302,
                                headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"})
    try:
        caminho = st.caminho(arq["storage_key"])
    except storage_mod.ChaveInvalida:
        raise HTTPException(404, "Chave de armazenamento inválida no banco (storage_key).") from None
    if not os.path.isfile(caminho):
        raise HTTPException(404, "PDF registrado, mas ausente do armazenamento (storage). Verifique se o volume fopa_dados está montado.")
    # inline: o navegador abre no leitor e o `#page=N` da citação funciona;
    # o nome original volta no Content-Disposition para quem salvar. O
    # FileResponse do Starlette já responde Range (206) e Accept-Ranges.
    return FileResponse(caminho, media_type="application/pdf", filename=arq["nome"],
                        content_disposition_type="inline",
                        headers={"Cache-Control": "private, max-age=3600",
                                 "X-Content-Type-Options": "nosniff"})


# Execuções, E-mails e o custo por execução: só o admin.
@app.get("/api/execucoes")
def execucoes(usuario: dict = Depends(admin), db: Banco = Depends(banco),
              workflow: str | None = Query(None, max_length=60), page: int = Query(1, ge=1),
              por_pagina: int = Query(50, ge=1, le=200)):
    return consultas.listar_execucoes(db.conn, workflow=workflow, page=page, por_pagina=por_pagina)


@app.get("/api/execucoes/{wid}")
def execucao(wid: int, usuario: dict = Depends(admin), db: Banco = Depends(banco)):
    d = consultas.execucao(db.conn, wid)
    if d is None:
        raise HTTPException(404, "Execução %d não encontrada." % wid)
    return d


@app.get("/api/custo")
def custo(usuario: dict = Depends(admin), db: Banco = Depends(banco)):
    return consultas.custo(db.conn)


@app.get("/api/gastos-ia")
def gastos_ia(usuario: dict = Depends(leitor), db: Banco = Depends(banco)):
    return consultas.gastos_ia(db.conn)


@app.get("/api/emails")
def emails(usuario: dict = Depends(admin), db: Banco = Depends(banco),
           tipo: str | None = Query(None, max_length=30), status: str | None = Query(None, max_length=20),
           page: int = Query(1, ge=1), por_pagina: int = Query(50, ge=1, le=200)):
    return consultas.listar_emails(db.conn, tipo=tipo, status=status, page=page, por_pagina=por_pagina)


# ====================================================================== revisão humana
@app.get("/api/fila-revisao/licitacoes")
def fila_revisao_licitacoes(usuario: dict = Depends(revisor), db: Banco = Depends(banco),
                            q: str | None = Query(None, max_length=200)):
    # A lista leve: os totais sempre e, com a busca, as licitações
    # com revisão aberta — o clique abre os campos pelo `?controle=` da rota abaixo.
    return consultas.licitacoes_em_revisao(db.conn, q=q)


@app.get("/api/fila-revisao")
def fila_revisao(usuario: dict = Depends(revisor), db: Banco = Depends(banco),
                 q: str | None = Query(None, max_length=200),
                 controle: str | None = Query(None, max_length=40)):
    # Operador: a fila é trabalho de quem decide (a página /revisao é dele);
    # o leitor vê a pendência no card (`revisao_pendente`) e no detalhe.
    # `controle`: os campos de UMA licitação (o clique na lista leve); `q`: a busca, a mesma do painel.
    return {"itens": consultas.fila_revisao(db.conn, q=q, controle=controle)}


class RevisaoIn(BaseModel):
    verificacao_id: int
    pergunta_id: str = Field(pattern=r"^Q\d+$")
    decisao: Literal["aceita", "corrigida", "rejeitada"]
    resposta_corrigida: str | None = Field(None, max_length=20000)
    nota: str | None = Field(None, max_length=5000)

    @model_validator(mode="after")
    def _corrigida_tem_resposta(self):
        if self.decisao == "corrigida" and not (self.resposta_corrigida or "").strip():
            raise ValueError("decisão 'corrigida' exige resposta_corrigida")
        return self


@app.post("/api/revisoes")
def decidir_revisao(corpo: RevisaoIn, usuario: dict = Depends(revisor), db: Banco = Depends(banco)):
    """
    Camada própria (T25): grava em `revisoes_humanas` e NADA MAIS. A resposta
    do modelo e o veredito do verificador ficam como estavam — o humano
    corrige por cima, com nome e data, e o histórico continua auditável.
    """
    conn = db.conn
    v = conn.execute("SELECT controle FROM verificacoes WHERE id = %s", (corpo.verificacao_id,)).fetchone()
    if v is None:
        raise HTTPException(404, "Verificação %d não encontrada." % corpo.verificacao_id)
    if conn.execute("SELECT 1 FROM perguntas WHERE id = %s", (corpo.pergunta_id,)).fetchone() is None:
        raise HTTPException(404, "A pergunta %s não existe." % corpo.pergunta_id)
    campos = (corpo.decisao, corpo.resposta_corrigida, corpo.nota, usuario["email"])
    linha = conn.execute(
        "UPDATE revisoes_humanas SET status = %s, resposta_corrigida = %s, nota = COALESCE(%s, nota),"
        " decidido_por = %s, decidido_em = now()"
        " WHERE id = (SELECT id FROM revisoes_humanas WHERE verificacao_id = %s AND pergunta_id = %s"
        "             AND status = 'aberta' ORDER BY id LIMIT 1) RETURNING *",
        campos + (corpo.verificacao_id, corpo.pergunta_id)).fetchone()
    if linha is None:
        # Sem pendência aberta: a decisão entra como revisão nova, já decidida.
        linha = conn.execute(
            "INSERT INTO revisoes_humanas (controle, verificacao_id, pergunta_id, motivo, status,"
            " resposta_corrigida, nota, decidido_por, decidido_em)"
            " VALUES (%s, %s, %s, 'revisão por iniciativa do operador', %s, %s, %s, %s, now())"
            " RETURNING *",
            (v["controle"], corpo.verificacao_id, corpo.pergunta_id) + campos).fetchone()
    db.commit()
    return linha


# ====================================================================== revisão: aba "escopo"
@app.get("/api/rotulos-escopo")
def rotulos_escopo(usuario: dict = Depends(admin), db: Banco = Depends(banco)):   # só admin (ADR-021, emenda 27/09)
    """Candidatas do Jev sem rótulo, depois as rotuladas (ver `consultas.rotulos_escopo`)."""
    return consultas.rotulos_escopo(db.conn)


class RotuloEscopoIn(BaseModel):
    controle: str
    dentro: StrictBool                     # "sim"/"1" não viram rótulo por coerção
    motivo: str | None = Field(None, max_length=2000)

    @field_validator("controle")
    @classmethod
    def valida_controle(cls, v: str) -> str:
        return _controle(v)

    @field_validator("motivo")
    @classmethod
    def _limpo(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


@app.post("/api/rotulos-escopo", status_code=201)
def rotular_escopo(corpo: RotuloEscopoIn, usuario: dict = Depends(admin), db: Banco = Depends(banco)):
    """
    T25: grava em `rotulos_escopo` (quem, quando, por quê) e NADA MAIS.
    `licitacoes.escopo_dentro` é da regra (ADR-003) e só o worker a reaplica
    (fn_aplicar_escopo, 019): o rótulo humano é o gabarito que MEDE a regra e
    o Jev, não um override. Rotular de novo acrescenta; vale o mais recente.
    """
    conn = db.conn
    if conn.execute("SELECT 1 FROM licitacoes WHERE controle = %s", (corpo.controle,)).fetchone() is None:
        raise HTTPException(404, "Licitação %s não encontrada." % corpo.controle)
    linha = conn.execute(
        "INSERT INTO rotulos_escopo (controle, veredito, por_que, por) VALUES (%s, %s, %s, %s)"
        " RETURNING id, controle, veredito, por_que, por, em",
        (corpo.controle, "dentro" if corpo.dentro else "fora", corpo.motivo, usuario["email"])).fetchone()
    if corpo.dentro:
        # O que a regra mandou para fora_escopo volta à fila (db/032); o "fora" basta estar gravado: a fila e a
        # tela olham o escopo efetivo (db/031).
        conn.execute("SELECT fn_rotulo_dentro_volta_a_fila(%s)", (corpo.controle,))
    db.commit()
    return {"id": linha["id"], "controle": linha["controle"], "dentro": linha["veredito"] == "dentro",
            "motivo": linha["por_que"], "por": linha["por"], "em": linha["em"]}


# ====================================================================== admin
@app.get("/api/admin/configuracao")
def config_ler(usuario: dict = Depends(admin), db: Banco = Depends(banco)):
    itens = db.conn.execute("SELECT chave, valor, descricao, alterado_por, em FROM configuracao"
                            " ORDER BY chave").fetchall()
    return {"itens": itens, "provedores": PROVEDORES, "aviso_custo": AVISO_CUSTO}


class ConfigIn(BaseModel):
    chave: str = Field(max_length=60)
    valor: Any
    confirmar: bool = False


_INTEIROS = ("lote", "k_rag", "max_tokens", "max_extracoes")
_TEXTOS = ("modelo", "modelo_openai", "effort")


def _validar_config(chave: str, valor: Any) -> None:
    if chave == "provedor" and valor not in PROVEDORES:
        raise HTTPException(422, "Provedor inválido. Opções: %s." % " | ".join(PROVEDORES))
    if chave in _INTEIROS and (not isinstance(valor, int) or isinstance(valor, bool) or valor < 1):
        raise HTTPException(422, "%s deve ser um número inteiro maior ou igual a 1." % chave)
    if chave in _TEXTOS and (not isinstance(valor, str) or not valor.strip()):
        raise HTTPException(422, "%s deve ser um texto não vazio." % chave)
    # fn_ano_minimo() (018) faz `::int` do valor em TODA leitura da lista: texto
    # ali derrubaria o site inteiro, e ano absurdo esvaziaria o recorte.
    if chave == "ano_minimo" and (not isinstance(valor, int) or isinstance(valor, bool)
                                  or not 2000 <= valor <= 2100):
        raise HTTPException(422, "ano_minimo deve ser um ano entre 2000 e 2100.")


@app.put("/api/admin/configuracao")
def config_gravar(corpo: ConfigIn, usuario: dict = Depends(admin), db: Banco = Depends(banco)):
    from psycopg.types.json import Jsonb
    conn = db.conn
    if conn.execute("SELECT 1 FROM configuracao WHERE chave = %s", (corpo.chave,)).fetchone() is None:
        raise HTTPException(404, "A chave de configuração %r não existe." % corpo.chave)
    _validar_config(corpo.chave, corpo.valor)
    # "API só em produção": trocar para um provedor que cobra é decisão
    # explícita, não um clique perdido. O front mostra o aviso e reenvia com
    # confirmar=true; quem mudou fica em `alterado_por`.
    if corpo.chave == "provedor" and corpo.valor in PROVEDORES_PAGOS and not corpo.confirmar:
        raise HTTPException(409, "A troca do provedor para '%s' gera custo real (%s). Para prosseguir, "
                                 "reenvie com confirmar=true." % (corpo.valor, AVISO_CUSTO))
    linha = conn.execute("UPDATE configuracao SET valor = %s, alterado_por = %s WHERE chave = %s"
                         " RETURNING chave, valor, descricao, alterado_por, em",
                         (Jsonb(corpo.valor), usuario["email"], corpo.chave)).fetchone()
    db.commit()
    return linha


@app.get("/api/admin/orcamento")
def orcamento_ler(usuario: dict = Depends(admin), db: Banco = Depends(banco)):
    historico = db.conn.execute("SELECT id, teto_brl_dia, max_por_execucao, auto_processar, vigente,"
                                " alterado_por, em FROM orcamento ORDER BY em DESC, id DESC LIMIT 50").fetchall()
    return {"vigente": consultas.orcamento_vigente(db.conn), "historico": historico,
            "aviso_custo": AVISO_CUSTO}


class OrcamentoIn(BaseModel):
    # NULL = sem teto (produção automática, sem teto).
    teto_brl_dia: float | None = Field(None, ge=0)
    max_por_execucao: int | None = Field(None, ge=1)
    auto_processar: bool = True


@app.put("/api/admin/orcamento")
def orcamento_gravar(corpo: OrcamentoIn, usuario: dict = Depends(admin), db: Banco = Depends(banco)):
    # Histórico, não UPDATE: a linha antiga deixa de ser vigente e continua
    # dizendo quanto era o teto em cada dia (o W23 lê a vigente).
    conn = db.conn
    conn.execute("UPDATE orcamento SET vigente = false WHERE vigente")
    conn.execute("INSERT INTO orcamento (teto_brl_dia, max_por_execucao, auto_processar, vigente,"
                 " alterado_por) VALUES (%s, %s, %s, true, %s)",
                 (corpo.teto_brl_dia, corpo.max_por_execucao, corpo.auto_processar, usuario["email"]))
    db.commit()
    return consultas.orcamento_vigente(conn)


@app.get("/api/admin/termos")
def termos_ler(usuario: dict = Depends(admin), db: Banco = Depends(banco)):
    return {"itens": db.conn.execute("SELECT termo, paginas, ativo, prioridade, densidade_pct, medido_em"
                                     " FROM termos ORDER BY prioridade, termo").fetchall()}


class TermoNovo(BaseModel):
    termo: str = Field(min_length=3, max_length=200)
    paginas: int = Field(10, ge=1, le=50)
    ativo: bool = True
    prioridade: int = Field(0, ge=0, le=1000)

    @field_validator("termo")
    @classmethod
    def _limpo(cls, v: str) -> str:
        return " ".join(v.split())


class TermoAlterar(BaseModel):
    termo: str = Field(min_length=1, max_length=200)
    paginas: int | None = Field(None, ge=1, le=50)
    ativo: bool | None = None
    prioridade: int | None = Field(None, ge=0, le=1000)


@app.post("/api/admin/termos", status_code=201)
def termo_criar(corpo: TermoNovo, usuario: dict = Depends(admin), db: Banco = Depends(banco)):
    linha = db.conn.execute(
        "INSERT INTO termos (termo, paginas, ativo, prioridade) VALUES (%s, %s, %s, %s)"
        " ON CONFLICT (termo) DO NOTHING RETURNING termo, paginas, ativo, prioridade",
        (corpo.termo, corpo.paginas, corpo.ativo, corpo.prioridade)).fetchone()
    if linha is None:
        raise HTTPException(409, "Este termo já existe. Para alterá-lo, use a edição (PUT).")
    db.commit()
    return linha


def _update_parcial(conn, tabela: str, chave: str, valor_chave, campos: dict):
    """UPDATE só dos campos enviados. Nomes de coluna vêm do modelo pydantic, nunca do cliente."""
    sets = ", ".join("%s = %%s" % c for c in campos)
    return conn.execute("UPDATE %s SET %s WHERE %s = %%s RETURNING *" % (tabela, sets, chave),
                        list(campos.values()) + [valor_chave]).fetchone()


@app.put("/api/admin/termos")
def termo_alterar(corpo: TermoAlterar, usuario: dict = Depends(admin), db: Banco = Depends(banco)):
    campos = {k: getattr(corpo, k) for k in corpo.model_fields_set if k != "termo"}
    if not campos:
        raise HTTPException(422, "Nenhuma alteração informada (páginas, ativo ou prioridade).")
    linha = _update_parcial(db.conn, "termos", "termo", corpo.termo, campos)
    if linha is None:
        raise HTTPException(404, "O termo %r não existe." % corpo.termo)
    db.commit()
    return linha


@app.get("/api/admin/usuarios")
def usuarios_ler(usuario: dict = Depends(admin), db: Banco = Depends(banco)):
    return {"itens": db.conn.execute("SELECT email, nome, papel, ativo, supremo FROM usuarios"
                                     " ORDER BY supremo DESC, email").fetchall()}


def _email(v: str) -> str:
    v = v.strip().lower()
    if not RE_EMAIL.match(v):
        raise ValueError("e-mail inválido")
    return v


class UsuarioNovo(BaseModel):
    email: str = Field(max_length=254)
    nome: str | None = Field(None, max_length=120)
    papel: Literal["leitor", "operador", "admin"] = "leitor"
    ativo: bool = True

    @field_validator("email")
    @classmethod
    def valida_email(cls, v: str) -> str:
        return _email(v)


class UsuarioAlterar(BaseModel):
    email: str = Field(max_length=254)
    nome: str | None = Field(None, max_length=120)
    papel: Literal["leitor", "operador", "admin"] | None = None
    ativo: bool | None = None

    @field_validator("email")
    @classmethod
    def valida_email(cls, v: str) -> str:
        return _email(v)


@app.post("/api/admin/usuarios", status_code=201)
def usuario_criar(corpo: UsuarioNovo, usuario: dict = Depends(so_supremo), db: Banco = Depends(banco)):
    linha = db.conn.execute(
        "INSERT INTO usuarios (email, nome, papel, ativo) VALUES (%s, %s, %s, %s)"
        " ON CONFLICT (email) DO NOTHING RETURNING email, nome, papel, ativo, supremo",
        (corpo.email, corpo.nome, corpo.papel, corpo.ativo)).fetchone()
    if linha is None:
        raise HTTPException(409, "Este usuário já existe. Para alterá-lo, use a edição (PUT).")
    db.commit()
    return linha


@app.put("/api/admin/usuarios")
def usuario_alterar(corpo: UsuarioAlterar, usuario: dict = Depends(so_supremo), db: Banco = Depends(banco)):
    conn = db.conn
    campos = {k: getattr(corpo, k) for k in corpo.model_fields_set if k != "email"}
    if not campos:
        raise HTTPException(422, "Nenhuma alteração informada (nome, perfil ou ativo).")
    atual = conn.execute("SELECT papel, ativo, supremo FROM usuarios WHERE email = %s FOR UPDATE",
                         (corpo.email,)).fetchone()
    if atual is None:
        raise HTTPException(404, "O usuário %s não existe." % corpo.email)
    if atual["supremo"]:
        # Ninguém altera o supremo pelo site — nem ele mesmo, por engano: ficaria sem quem dá acesso
        raise HTTPException(403, "O administrador supremo não pode ser alterado pelo site.")
    perde_admin = atual["papel"] == "admin" and atual["ativo"] and (
        campos.get("papel", "admin") != "admin" or campos.get("ativo", True) is False)
    if perde_admin:
        outros = conn.execute("SELECT count(*) AS n FROM usuarios WHERE papel = 'admin' AND ativo"
                              " AND email <> %s", (corpo.email,)).fetchone()["n"]
        if outros == 0:
            # Sem outro admin ativo ninguém mais edita usuários pelo site.
            raise HTTPException(409, "Este é o último administrador ativo. Promova outro usuário antes.")
    linha = _update_parcial(conn, "usuarios", "email", corpo.email, campos)
    db.commit()
    return {k: linha[k] for k in ("email", "nome", "papel", "ativo", "supremo")}


class UsuarioRemover(BaseModel):
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def valida_email(cls, v: str) -> str:
        return _email(v)


@app.delete("/api/admin/usuarios", status_code=204)
def usuario_remover(corpo: UsuarioRemover, usuario: dict = Depends(so_supremo), db: Banco = Depends(banco)):
    """Apaga o cadastro e derruba a sessão aberta (db/048). Quem entrar de novo com o Google volta como
    usuário; para barrar a volta existe o bloquear (PUT ativo=false)."""
    conn = db.conn
    atual = conn.execute("SELECT supremo FROM usuarios WHERE email = %s FOR UPDATE", (corpo.email,)).fetchone()
    if atual is None:
        raise HTTPException(404, "O usuário %s não existe." % corpo.email)
    if atual["supremo"]:
        raise HTTPException(403, "O administrador supremo não pode ser alterado pelo site.")
    conn.execute("DELETE FROM sessoes WHERE email = %s", (corpo.email,))
    conn.execute("DELETE FROM usuarios WHERE email = %s", (corpo.email,))
    db.commit()
    return Response(status_code=204)


class ReservaIn(BaseModel):
    controles: list[str] = Field(min_length=1, max_length=50)
    dias: int = Field(ge=1, le=60)

    @field_validator("controles")
    @classmethod
    def _formato(cls, v: list[str]) -> list[str]:
        ruins = [c for c in v if not RE_CONTROLE.match(c)]
        if ruins:
            raise ValueError("controle fora do formato do PNCP: %s" % ", ".join(ruins[:5]))
        return list(dict.fromkeys(v))


@app.post("/api/admin/reservar-demo")
def reservar_demo(corpo: ReservaIn, usuario: dict = Depends(admin), db: Banco = Depends(banco)):
    """
    Substitui o `api/demo_reservar.py` do plano: marca `reserva_demo` e empurra
    `fim_prazo` para `now() + dias`, para que as licitações escolhidas
    continuem "abertas" no dia da demonstração sem ninguém editar o banco à mão.
    """
    linhas = db.conn.execute(
        "UPDATE licitacoes SET reserva_demo = true, fim_prazo = now() + make_interval(days => %s)"
        " WHERE controle = ANY(%s) RETURNING controle, fim_prazo", (corpo.dias, corpo.controles)).fetchall()
    db.commit()
    feitas = {l["controle"]: l["fim_prazo"] for l in linhas}
    return {"reservadas": [c for c in corpo.controles if c in feitas],
            "nao_encontradas": [c for c in corpo.controles if c not in feitas],
            "fim_prazo": next(iter(feitas.values()), None)}


# ====================================================================== ações → n8n (W11)
def _chamar_n8n(request: Request, acao: str, corpo: dict) -> JSONResponse:
    cfg = config.carregar()
    if not cfg.site_token:
        raise HTTPException(503, "Configuração incompleta: FOPA_SITE_TOKEN não está definido; o site não consegue acionar o processamento (n8n).")
    url = "%s/webhook/fopa/%s" % (cfg.n8n_url, acao)
    try:
        with httpx.Client(timeout=TIMEOUT_N8N, transport=request.app.state.transporte_n8n) as cliente:
            r = cliente.post(url, json=corpo, headers={"X-FOPA-Token": cfg.site_token})
    except httpx.HTTPError as e:
        raise HTTPException(503, "Processamento (n8n) indisponível (%s): a ação '%s' não foi enviada. "
                                 "Verifique o serviço fopa-n8n." % (type(e).__name__, acao)) from None
    if r.status_code == 404:
        raise HTTPException(503, "O processamento (n8n) respondeu, mas o webhook fopa/%s não está registrado. "
                                 "Verifique se o fluxo W11 está ativo." % acao)
    if r.status_code in (401, 403):
        raise HTTPException(503, "O processamento (n8n) recusou o X-FOPA-Token: a credencial 'site' do W11 "
                                 "difere de FOPA_SITE_TOKEN.")
    try:
        dados = r.json()
    except ValueError:
        dados = {"resposta": r.text[:500]}
    if r.status_code >= 500:
        return JSONResponse({"detail": "o n8n falhou ao aceitar a ação '%s' (HTTP %d)" % (acao, r.status_code),
                             "n8n": dados}, status_code=502)
    # 2xx e 4xx de validação do W11 (ex.: controle recusado) voltam como vieram.
    return JSONResponse(dados, status_code=r.status_code)


def _controle(v: str) -> str:
    if not RE_CONTROLE.match(v):
        raise ValueError("controle fora do formato do PNCP (00000000000000-1-000000/2026)")
    return v


class VerificarIn(BaseModel):
    pass


class ProcessarIn(BaseModel):
    controles: list[str] = Field(min_length=1, max_length=MAX_CONTROLES_POR_ACAO)
    forcar: bool = False

    @field_validator("controles")
    @classmethod
    def _formato(cls, v):
        return [_controle(c) for c in v]


class ReverificarIn(BaseModel):
    controle: str

    @field_validator("controle")
    @classmethod
    def valida_controle(cls, v: str) -> str:
        return _controle(v)


class ImportarRespostasIn(BaseModel):
    """As 17 respostas que um agente (Claude Code, custo zero, ADR-014) produziu sobre a leitura congelada."""
    controle: str
    respostas: list[dict] = Field(min_length=17, max_length=17)
    modelo: str | None = Field(None, max_length=80)
    sessao: str | None = Field(None, max_length=200)

    @field_validator("controle")
    @classmethod
    def valida_controle(cls, v: str) -> str:
        return _controle(v)


@app.post("/api/acoes/verificar")
def acao_verificar(request: Request, corpo: VerificarIn | None = None, usuario: dict = Depends(admin)):
    # W11 → W01 seco: busca no PNCP, custo R$ 0; responde 202 {execucao_id}.
    return _chamar_n8n(request, "verificar", {"solicitado_por": usuario["email"]})


@app.post("/api/acoes/processar")
def acao_processar(request: Request, corpo: ProcessarIn, usuario: dict = Depends(admin)):
    return _chamar_n8n(request, "processar", {"controles": corpo.controles, "forcar": corpo.forcar,
                                              "solicitado_por": usuario["email"]})


# Onde não há texto para ler (db/002: o W21 e o W22 param aqui): um pedido de extração nunca seria usado.
ESTADOS_SEM_TEXTO = ("formato_nao_suportado", "sem_pdf_legivel")


class ExtrairIaIn(BaseModel):
    controle: str
    provedor: Literal["openai", "claude"] = "openai"
    # O modelo, filtrado pelo provedor; vazio = o primeiro. O esforço é FIXO por modelo desde 26/09
    # (ADR-020): a tela não manda; se um cliente velho mandar um diferente do fixo, 422.
    modelo: str | None = None
    effort: str | None = None

    @field_validator("controle")
    @classmethod
    def valida_controle(cls, v: str) -> str:
        return _controle(v)


@app.get("/api/modelos-ia")
def modelos_ia_disponiveis(usuario: dict = Depends(leitor)):
    """O catálogo do botão "Extrair com IA": provedores, modelos, esforços, o padrão de cada empresa e a estimativa
    (api/modelos_ia.py; níveis e padrões das páginas oficiais da OpenAI e da Anthropic)."""
    return modelos_ia.publico()


@app.post("/api/acoes/extrair-ia")
def acao_extrair_ia(request: Request, corpo: ExtrairIaIn, usuario: dict = Depends(admin),
                    db: Banco = Depends(banco)):
    """
    O botão "Extrair com GPT": grava o pedido (db/033) — o provedor global NÃO muda, e a fila
    das 6h segue só baixando e lendo o resto — e pede o processamento desta licitação ao W11, como o "Processar"
    com `forcar` (a publicada recomeça; a preparada vai direto à extração). O W23 gasta o pedido ao abrir a
    execução: se falhar, é outro clique.
    """
    conn = db.conn
    lic = conn.execute("SELECT controle, estado::text AS estado FROM licitacoes"
                       " WHERE controle = %s AND fn_escopo_efetivo(controle, escopo_dentro)", (corpo.controle,)).fetchone()
    if lic is None:
        raise HTTPException(404, "Licitação %s não encontrada no escopo de folha." % corpo.controle)
    if lic["estado"] in ESTADOS_SEM_TEXTO:
        # Vale de São Domingos (25/09): o edital era RTF com nome .pdf; o pedido ficaria pendente para sempre e o
        # clique pareceria não fazer nada. Aqui se diz o porquê, sem gravar pedido nem chamar o n8n.
        motivos = [r["motivo"] for r in conn.execute(
            "SELECT DISTINCT motivo FROM arquivos WHERE controle = %s AND status = %s AND motivo IS NOT NULL",
            (corpo.controle, lic["estado"])).fetchall()]
        raise HTTPException(409, "O edital desta licitação não está em PDF legível (%s); sem texto, não há o que extrair, "
                                 "e nada seria cobrado. O sistema processa apenas PDF: solicite o PDF ao órgão ou anexe "
                                 "a versão em PDF." % ("; ".join(motivos) or lic["estado"]))
    try:
        modelo, effort, max_tokens = modelos_ia.resolver(corpo.provedor, corpo.modelo, corpo.effort)
    except ValueError as e:
        raise HTTPException(422, str(e))
    conn.execute("INSERT INTO pedidos_extracao (controle, provedor, pedido_por, modelo, effort, max_tokens)"
                 " VALUES (%s, %s, %s, %s, %s, %s)",
                 (corpo.controle, corpo.provedor, usuario["email"], modelo, effort, max_tokens))
    db.commit()
    return _chamar_n8n(request, "processar", {"controles": [corpo.controle], "forcar": True,
                                              "solicitado_por": usuario["email"]})


@app.post("/api/acoes/reverificar")
def acao_reverificar(request: Request, corpo: ReverificarIn, usuario: dict = Depends(admin)):
    return _chamar_n8n(request, "reverificar", {"controle": corpo.controle,
                                                "solicitado_por": usuario["email"]})


@app.post("/api/acoes/importar-respostas")
def acao_importar_respostas(request: Request, corpo: ImportarRespostasIn, usuario: dict = Depends(admin)):
    # Plano §8 (admin): "Importar respostas do agente". O site confere o que é dele (controle, 17 respostas); a
    # validação de cada resposta é do worker e o caminho (preparada → respondida → W24, ou republicar se já
    # publicada) é do W11. O 202/409/422 do W11 volta como veio.
    return _chamar_n8n(request, "importar-respostas", {
        "controle": corpo.controle, "respostas": corpo.respostas, "solicitado_por": usuario["email"],
        "procedencia": {"provedor": "claude-code", "modelo": corpo.modelo, "sessao": corpo.sessao}})


@app.post("/api/interno/invalidar", status_code=204)
def interno_invalidar(request: Request):
    """
    O W24 avisa depois de publicar (plano §5, W24 passo 9; Never Error no n8n).
    O site não guarda cache no servidor — o React Query do navegador revalida
    sozinho —, então aqui só se autentica o n8n (X-FOPA-Token, o mesmo segredo
    das ações) e se confirma. Sem a rota, cada publicação recebia 405.
    """
    cfg = config.carregar()
    if not cfg.site_token:
        raise HTTPException(503, "Configuração incompleta: FOPA_SITE_TOKEN não está definido no serviço do site (fopa-api).")
    recebido = request.headers.get("X-FOPA-Token") or ""
    if not hmac.compare_digest(recebido.encode(), cfg.site_token.encode()):
        raise HTTPException(401, "Token do processamento (n8n) ausente ou inválido.")
    return Response(status_code=204)


# ====================================================================== questionário (worker)
@app.get("/api/questionario")
def questionario(request: Request, usuario: dict = Depends(leitor)):
    cfg = config.carregar()
    if not cfg.worker_url or not cfg.worker_token:
        raise HTTPException(503, "Configuração incompleta: FOPA_WORKER_URL/FOPA_WORKER_TOKEN não estão definidos no serviço do site (fopa-api).")
    try:
        with httpx.Client(timeout=TIMEOUT_WORKER, transport=request.app.state.transporte_worker) as cliente:
            r = cliente.get(cfg.worker_url + "/questionario",
                            headers={"Authorization": "Bearer " + cfg.worker_token})
    except httpx.HTTPError as e:
        raise HTTPException(503, "Serviço de leitura e extração (worker) indisponível (%s)." % type(e).__name__) from None
    if r.status_code in (404, 405):
        raise HTTPException(503, "O serviço de leitura e extração (worker) ainda não disponibiliza /questionario.")
    if r.status_code != 200:
        raise HTTPException(502, "O serviço de leitura e extração (worker) respondeu HTTP %d em /questionario." % r.status_code)
    try:
        dados = r.json()
    except ValueError:
        # Proxy no meio ou worker antigo devolvendo HTML: foi um intermediário que respondeu errado.
        raise HTTPException(502, "O serviço de leitura e extração (worker) respondeu /questionario com um conteúdo que não é JSON.") from None
    return JSONResponse(dados)


# ====================================================================== privacidade
# Pública e renderizada no servidor: é o link que a tela de consentimento do Google pede para publicar o app
# (o login não pode depender do modo "Testando" do Google). O texto segue o que o código faz:
# oauth.py lê só `openid email profile`; ADR-016 (os dois e-mails); ADR-021 (bloquear e remover).
PRIVACIDADE = """<!doctype html><html lang=pt-BR><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>FOPA · Privacidade</title>
<body style="font-family:system-ui;max-width:40rem;margin:3rem auto;padding:0 1rem;line-height:1.55">
<h1 style="font-size:1.4rem">Política de privacidade do FOPA</h1>
<p>O FOPA é um estudo de viabilidade que lê editais públicos de licitação de folha de pagamento publicados no
Portal Nacional de Contratações Públicas (PNCP). Os editais e os dados das compras são públicos; esta página trata
só dos dados de quem entra no site.</p>
<h2 style="font-size:1.1rem">O que coletamos</h2>
<p>No login com o Google, o site recebe apenas o seu <b>nome</b> e o seu <b>e-mail</b> (escopos <code>openid</code>,
<code>email</code> e <code>profile</code>). Não lemos contatos, arquivos, agenda nem nenhum outro dado da conta.
Guardamos também a sessão de login (um cookie que expira em 12 horas) e o registro das ações feitas no site,
como pedir uma extração.</p>
<h2 style="font-size:1.1rem">Para que usamos</h2>
<ul>
<li>Identificar você e decidir o que você pode ver e fazer no site.</li>
<li>Enviar e-mail aos administradores quando surge uma licitação nova de folha de pagamento.</li>
<li>Enviar, a quem pediu uma extração pelo site, o resultado dessa extração.</li>
</ul>
<p>Não enviamos outros e-mails, não vendemos nem compartilhamos seus dados, e não usamos dados da conta Google para
treinar modelos de IA ou para publicidade. Os e-mails saem por um provedor de envio contratado só para isso.</p>
<h2 style="font-size:1.1rem">Onde ficam e por quanto tempo</h2>
<p>Em servidores na região de São Paulo (AWS sa-east-1). O cadastro fica enquanto o acesso existir; o administrador
pode removê-lo a qualquer momento, e a remoção apaga o cadastro e as sessões.</p>
<h2 style="font-size:1.1rem">Seus direitos</h2>
<p>Pela LGPD, você pode pedir acesso, correção ou exclusão dos seus dados pelo e-mail
<a href="mailto:contato@exemplo.com">contato@exemplo.com</a>.</p>
<p style="color:#666;font-size:.9rem">Atualizada em 28/09/2026. · <a href="/">Voltar ao FOPA</a></p>
"""


@app.get("/privacidade", include_in_schema=False)
def privacidade():
    return HTMLResponse(PRIVACIDADE)


# ====================================================================== front (build do React)
# Tipos fixos para os estáticos do Vite: o `mimetypes` do Windows lê o
# registro e pode servir .js como text/plain, que o navegador recusa em módulo.
_TIPOS = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
          ".html": "text/html; charset=utf-8", ".json": "application/json", ".svg": "image/svg+xml",
          ".woff2": "font/woff2", ".woff": "font/woff", ".wasm": "application/wasm",
          ".map": "application/json", ".ico": "image/x-icon", ".png": "image/png", ".txt": "text/plain"}


@app.get("/{caminho:path}", include_in_schema=False)
def front(caminho: str):
    """
    SPA: arquivo que existe no build sai como está; o resto cai no index.html
    para o React Router resolver (/licitacao/:slug, /admin...). `/api`, `/auth`
    e `/login` nunca caem aqui como página: rota inexistente nelas é 404 de
    verdade, senão o front receberia HTML onde espera JSON.
    """
    primeiro = caminho.split("/", 1)[0]
    if primeiro in ("api", "auth", "login"):
        raise HTTPException(404, "Rota inexistente: /%s." % caminho)
    dist = config.carregar().web_dist
    if not os.path.isdir(dist):
        raise HTTPException(404, "Build do site ausente (FOPA_WEB_DIST=%s)." % dist)
    raiz = os.path.realpath(dist)
    alvo = os.path.realpath(os.path.join(raiz, caminho))
    # realpath + commonpath: `..`, `%2e%2e` decodificado e symlink não saem da pasta do build.
    if caminho and os.path.commonpath([raiz, alvo]) == raiz and os.path.isfile(alvo):
        tipo = _TIPOS.get(os.path.splitext(alvo)[1].lower()) or mimetypes.guess_type(alvo)[0]
        return FileResponse(alvo, media_type=tipo)
    indice = os.path.join(raiz, "index.html")
    if not os.path.isfile(indice):
        raise HTTPException(404, "index.html ausente em FOPA_WEB_DIST.")
    # index sem cache: é ele que aponta para os assets com hash do build novo.
    return FileResponse(indice, media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})


__all__ = ["app", "checar_worker", "checar_postgres", "checar_n8n", "CSP_RELATORIO"]
