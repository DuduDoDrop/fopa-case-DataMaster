# -*- coding: utf-8 -*-
"""
Login Google (OAuth2 + OpenID Connect) do site — plano, seção 8.

FLUXO
  `/auth/google/login` gera `state`, `nonce` e o verificador PKCE, guarda os
  três num cookie assinado de 10 min (só em `/auth`) e redireciona para o
  Google com `scope=openid email profile`. `/auth/google/callback` confere o
  `state` do cookie contra o da query, troca o `code` (com o verificador)
  pelo `id_token` e valida o token AQUI: assinatura pela JWKS do Google,
  `iss`, `aud` = o client_id do FOPA, `exp`, `nonce` e `email_verified`. Só
  então o e-mail é olhado contra a allowlist (`usuarios.ativo`) — isso fica
  em `site.py`, que é quem tem o banco.

POR QUE O ESTADO NUM COOKIE ASSINADO E NÃO NO SessionMiddleware
  O `authorize_redirect` do authlib/starlette exige o SessionMiddleware, que
  poria um segundo cookie de sessão (com outro formato e outra validade) em
  TODAS as rotas. Aqui o estado do login vive só no caminho `/auth`, morre em
  10 min e é apagado no callback.

POR QUE VALIDAR O id_token À MÃO (joserfc) E NÃO CONFIAR NA TROCA
  O token vem do endpoint do Google por TLS, e a especificação até dispensa
  a assinatura nesse caso — mas a `aud` e o `nonce` não são opcionais: sem
  `aud`, um id_token emitido para OUTRO app que usa login Google entraria
  aqui; sem `nonce`, um id_token antigo poderia ser reapresentado. Conferir a
  assinatura também custa pouco (a JWKS é uma chamada) e fecha o caminho de
  um proxy intermediário mal configurado.

POR QUE AS PRIMITIVAS DO authlib E NÃO O `OAuth2Client` DELE
  O cliente httpx do authlib 1.8 usa o pacote `httpx2` quando ele está
  instalado e o `httpx` quando não está: o comportamento (e o transporte que
  ele aceita) mudaria conforme a imagem. A URL de autorização e o desafio
  PKCE saem do authlib (`prepare_grant_uri`, RFC 7636); a troca do código é
  um POST de formulário com o `httpx` que o resto da API já usa.

REDE NOS TESTES
  Tudo que sai para o Google usa o transporte httpx recebido por parâmetro
  (`app.state.transporte_google`): nos testes é um MockTransport que assina o
  id_token com uma chave RSA gerada na hora. Nenhum teste fala com o Google.
"""
from __future__ import annotations

import hmac
import secrets

import httpx
from authlib.oauth2.rfc6749.parameters import prepare_grant_uri
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from itsdangerous import BadSignature, URLSafeTimedSerializer
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from .config import Config

AUTORIZAR_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
# O Google emite com e sem esquema (documentado em "Validating an ID token").
EMISSORES = ("https://accounts.google.com", "accounts.google.com")
ESCOPO = "openid email profile"
COOKIE_ESTADO = "fopa_oauth"
CAMINHO_COOKIE = "/auth"
VALIDADE_ESTADO_S = 600
TIMEOUT_GOOGLE = 15.0
# Relógio do container x relógio do Google: 1 min de folga em exp/iat.
FOLGA_RELOGIO_S = 60


class FalhaOAuth(Exception):
    """Login que não pode seguir. `status` vira o código HTTP da resposta."""

    def __init__(self, mensagem: str, status: int = 400):
        super().__init__(mensagem)
        self.status = status


def _assinador(cfg: Config) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(cfg.session_secret, salt="fopa-oauth-v1")


def _conferir_configuracao(cfg: Config) -> str:
    """Devolve o redirect_uri; falha 503 (é configuração, não erro de quem clicou)."""
    faltando = [n for n, v in (("GOOGLE_CLIENT_ID", cfg.google_client_id),
                               ("GOOGLE_CLIENT_SECRET", cfg.google_client_secret),
                               ("SESSION_SECRET", cfg.session_secret)) if not v]
    redirect = cfg.oauth_redirect_uri or (
        cfg.site_url + "/auth/google/callback" if cfg.site_url else None)
    if not redirect:
        faltando.append("OAUTH_REDIRECT_URI")
    if faltando:
        raise FalhaOAuth("login Google não configurado: falta %s no ambiente do fopa-api"
                         % ", ".join(faltando), status=503)
    return redirect


def iniciar(cfg: Config) -> tuple[str, str]:
    """(URL do Google para redirecionar, valor do cookie de estado)."""
    redirect = _conferir_configuracao(cfg)
    estado, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    verificador = secrets.token_urlsafe(64)      # 86 chars: dentro dos 43-128 do RFC 7636
    url = prepare_grant_uri(
        AUTORIZAR_URL, cfg.google_client_id, "code", redirect_uri=redirect, scope=ESCOPO,
        state=estado, nonce=nonce, code_challenge=create_s256_code_challenge(verificador),
        code_challenge_method="S256",
        # "select_account": quem tem duas contas Google escolhe qual; sem
        # isso o Google entra direto na última usada e o 403 confunde.
        prompt="select_account")
    cookie = _assinador(cfg).dumps({"s": estado, "n": nonce, "v": verificador})
    return url, cookie


def _ler_estado(cfg: Config, valor: str | None) -> dict:
    if not valor:
        raise FalhaOAuth("login sem estado (cookie ausente ou expirado): comece de novo em /login")
    try:
        dados = _assinador(cfg).loads(valor, max_age=VALIDADE_ESTADO_S)
    except BadSignature:
        raise FalhaOAuth("estado do login inválido ou expirado: comece de novo em /login") from None
    if not isinstance(dados, dict) or not all(isinstance(dados.get(k), str) for k in "snv"):
        raise FalhaOAuth("estado do login malformado: comece de novo em /login")
    return dados


def validar_id_token(id_token: str, jwks: dict, client_id: str, nonce: str) -> dict:
    """Claims do id_token se assinatura, iss, aud, exp, nonce e e-mail verificado batem."""
    try:
        token = jwt.decode(id_token, KeySet.import_key_set(jwks), algorithms=["RS256"])
        JWTClaimsRegistry(
            leeway=FOLGA_RELOGIO_S,
            iss={"essential": True, "values": list(EMISSORES)},
            aud={"essential": True, "value": client_id},
            exp={"essential": True},
            nonce={"essential": True, "value": nonce},
            email={"essential": True},
        ).validate(token.claims)
    except (JoseError, ValueError, KeyError, TypeError) as e:
        # A mensagem da joserfc diz QUAL claim falhou ("invalid_claim: aud"),
        # sem carregar o token.
        raise FalhaOAuth("id_token recusado: %s" % e, status=401) from None
    claims = token.claims
    if claims.get("email_verified") is not True:
        raise FalhaOAuth("e-mail da conta Google não verificado", status=403)
    return claims


def concluir(cfg: Config, code: str | None, state: str | None, valor_cookie: str | None,
             transporte: httpx.BaseTransport | None = None) -> dict:
    """Troca o `code` e devolve as claims validadas do id_token (com `email` normalizado)."""
    redirect = _conferir_configuracao(cfg)
    dados = _ler_estado(cfg, valor_cookie)
    # compare_digest: o state é segredo de curta duração, não se compara byte a byte.
    if not state or not hmac.compare_digest(state.encode(), dados["s"].encode()):
        raise FalhaOAuth("state divergente: o login não foi iniciado neste navegador")
    if not code:
        raise FalhaOAuth("o Google não devolveu o código de autorização")
    try:
        with httpx.Client(timeout=TIMEOUT_GOOGLE, transport=transporte) as cliente:
            # client_secret_post: o Google aceita, e o segredo não vai para log de URL.
            r = cliente.post(TOKEN_URL, data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
                "client_id": cfg.google_client_id, "client_secret": cfg.google_client_secret,
                "code_verifier": dados["v"]}, headers={"Accept": "application/json"})
            if r.status_code != 200:
                try:
                    erro = r.json().get("error") or "HTTP %d" % r.status_code
                except ValueError:
                    erro = "HTTP %d" % r.status_code
                # invalid_grant = code expirado/reutilizado ou verificador PKCE errado.
                raise FalhaOAuth("o Google recusou a troca do código: %s" % erro, status=400)
            token = r.json()
            jwks = cliente.get(JWKS_URL).json()
    except httpx.HTTPError as e:
        raise FalhaOAuth("Google inacessível (%s): tente de novo" % type(e).__name__,
                         status=503) from None
    except ValueError:
        raise FalhaOAuth("resposta do Google não é JSON", status=503) from None
    id_token = token.get("id_token") if isinstance(token, dict) else None
    if not id_token:
        raise FalhaOAuth("resposta do Google sem id_token (escopo openid ausente?)", status=401)
    claims = validar_id_token(id_token, jwks, cfg.google_client_id, dados["n"])
    claims = dict(claims)
    claims["email"] = str(claims["email"]).strip().lower()
    return claims


__all__ = ["FalhaOAuth", "iniciar", "concluir", "validar_id_token", "COOKIE_ESTADO",
           "CAMINHO_COOKIE", "VALIDADE_ESTADO_S", "AUTORIZAR_URL", "TOKEN_URL", "JWKS_URL",
           "EMISSORES", "ESCOPO"]
