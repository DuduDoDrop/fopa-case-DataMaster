# -*- coding: utf-8 -*-
"""
Configuração da `api` a partir do ambiente (plano, seção 4 "Variáveis (nomes)").

Lida a cada chamada de `carregar()`, nunca em constante de módulo: o worker e o
site rodam em containers configurados por env, e ler no import faria a ordem de
import decidir a configuração (foi assim que o `TESSDATA_PREFIX` errado passou
despercebido por semanas em `fopa/ocr.py`). Ler por chamada também é o que
permite testar cada variável com `monkeypatch`.

Este módulo NUNCA lê ANTHROPIC_API_KEY. A chave existe só na Credential do n8n;
o worker apenas informa em `/health` se ela está presente no ambiente, para que
a ausência possa ser verificada de fora.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

AMBIENTES = ("dev", "demo", "prod")
BACKENDS = ("fs", "s3")
MODOS_AUTH = ("google", "local")

# Hostname interno do compose: o site fala com o n8n pela rede do compose,
# nunca pela URL pública (plano, seção 4 "fopa-api").
N8N_URL_PADRAO = "http://fopa-n8n:5678"
# Onde a imagem copia o build do React (fopa-web); ausente = site só com /api.
WEB_DIST_PADRAO = "/app/web/dist"

# 5.4.0 é a versão das medições de OCR (ADR-008); o build da imagem compila
# exatamente ela, e o /health recusa qualquer outra.
TESSERACT_ESPERADO_PADRAO = "5.4.0"
JOBS_CONCORRENCIA_PADRAO = 2
# R2 chama a região de `auto` (e aceita `us-east-1` como apelido); MinIO e AWS
# assinam com a região do bucket, que então tem de vir em S3_REGION.
S3_REGIAO_PADRAO = "auto"


class ConfigInvalida(ValueError):
    """Variável de ambiente fora do domínio aceito. Falha alto, no arranque."""


@dataclass(frozen=True)
class Config:
    ambiente: str = "dev"                       # FOPA_ENV
    worker_token: str | None = field(default=None, repr=False)   # FOPA_WORKER_TOKEN
    worker_url: str | None = None               # FOPA_WORKER_URL (usado pelo site)
    database_url: str | None = field(default=None, repr=False)   # DATABASE_URL (tem senha)
    storage_backend: str = "fs"                 # STORAGE_BACKEND
    storage_root: str = "/dados"                # STORAGE_ROOT
    # --- storage s3 (F8; R2/MinIO). Validados no uso (StorageS3), não aqui:
    # o /health tem de responder dizendo o que falta, não cair no arranque.
    s3_endpoint: str | None = None              # S3_ENDPOINT (https://<conta>.r2.cloudflarestorage.com)
    s3_bucket: str | None = None                # S3_BUCKET
    s3_key: str | None = field(default=None, repr=False)      # S3_KEY (access key id)
    s3_secret: str | None = field(default=None, repr=False)   # S3_SECRET
    s3_region: str = S3_REGIAO_PADRAO           # S3_REGION (R2: auto; MinIO/AWS: a do bucket)
    tesseract_esperado: str = TESSERACT_ESPERADO_PADRAO   # FOPA_TESSERACT_ESPERADO
    tessdata_sha256: str | None = None          # FOPA_TESSDATA_SHA256
    jobs_concorrencia: int = JOBS_CONCORRENCIA_PADRAO     # FOPA_JOBS_CONCORRENCIA
    usd_brl: float | None = None                # USD_BRL
    git_sha: str | None = None                  # FOPA_GIT_SHA (gravado no build)
    # --- site (F2) ---------------------------------------------------------
    auth_mode: str = "google"                   # FOPA_AUTH_MODE (local só vale com FOPA_ENV=demo)
    site_token: str | None = field(default=None, repr=False)     # FOPA_SITE_TOKEN (X-FOPA-Token do n8n)
    session_secret: str | None = field(default=None, repr=False) # SESSION_SECRET (assina o cookie)
    n8n_url: str = N8N_URL_PADRAO               # FOPA_N8N_URL (base; o site soma /webhook/fopa/<ação>)
    site_url: str | None = None                 # FOPA_SITE_URL
    google_client_id: str | None = None         # GOOGLE_CLIENT_ID
    google_client_secret: str | None = field(default=None, repr=False)  # GOOGLE_CLIENT_SECRET
    oauth_redirect_uri: str | None = None       # OAUTH_REDIRECT_URI
    web_dist: str = WEB_DIST_PADRAO             # FOPA_WEB_DIST


def _opcional(env: Mapping[str, str], nome: str) -> str | None:
    valor = env.get(nome, "").strip()
    return valor or None


def _escolha(env: Mapping[str, str], nome: str, aceitos: tuple[str, ...], padrao: str) -> str:
    valor = (env.get(nome) or padrao).strip().lower()
    if valor not in aceitos:
        raise ConfigInvalida("%s=%r; aceito: %s" % (nome, valor, "|".join(aceitos)))
    return valor


def _inteiro(env: Mapping[str, str], nome: str, padrao: int, minimo: int = 1) -> int:
    bruto = env.get(nome, "").strip()
    if not bruto:
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        raise ConfigInvalida("%s=%r não é inteiro" % (nome, bruto)) from None
    if valor < minimo:
        raise ConfigInvalida("%s=%d; mínimo %d" % (nome, valor, minimo))
    return valor


def _decimal(env: Mapping[str, str], nome: str) -> float | None:
    bruto = env.get(nome, "").strip()
    if not bruto:
        return None
    try:
        valor = float(bruto.replace(",", "."))
    except ValueError:
        raise ConfigInvalida("%s=%r não é número" % (nome, bruto)) from None
    if valor <= 0:
        raise ConfigInvalida("%s=%r; a cotação tem de ser positiva" % (nome, bruto))
    return valor


def carregar(env: Mapping[str, str] | None = None) -> Config:
    """Monta a `Config` do ambiente dado (padrão: `os.environ`)."""
    env = os.environ if env is None else env
    return Config(
        ambiente=_escolha(env, "FOPA_ENV", AMBIENTES, "dev"),
        worker_token=_opcional(env, "FOPA_WORKER_TOKEN"),
        worker_url=(_opcional(env, "FOPA_WORKER_URL") or "").rstrip("/") or None,
        database_url=_opcional(env, "DATABASE_URL"),
        storage_backend=_escolha(env, "STORAGE_BACKEND", BACKENDS, "fs"),
        storage_root=_opcional(env, "STORAGE_ROOT") or "/dados",
        s3_endpoint=(_opcional(env, "S3_ENDPOINT") or "").rstrip("/") or None,
        s3_bucket=_opcional(env, "S3_BUCKET"),
        s3_key=_opcional(env, "S3_KEY"),
        s3_secret=_opcional(env, "S3_SECRET"),
        s3_region=_opcional(env, "S3_REGION") or S3_REGIAO_PADRAO,
        tesseract_esperado=_opcional(env, "FOPA_TESSERACT_ESPERADO") or TESSERACT_ESPERADO_PADRAO,
        tessdata_sha256=(_opcional(env, "FOPA_TESSDATA_SHA256") or "").lower() or None,
        jobs_concorrencia=_inteiro(env, "FOPA_JOBS_CONCORRENCIA", JOBS_CONCORRENCIA_PADRAO),
        usd_brl=_decimal(env, "USD_BRL"),
        git_sha=_opcional(env, "FOPA_GIT_SHA"),
        auth_mode=_escolha(env, "FOPA_AUTH_MODE", MODOS_AUTH, "google"),
        site_token=_opcional(env, "FOPA_SITE_TOKEN"),
        session_secret=_opcional(env, "SESSION_SECRET"),
        n8n_url=(_opcional(env, "FOPA_N8N_URL") or N8N_URL_PADRAO).rstrip("/"),
        site_url=(_opcional(env, "FOPA_SITE_URL") or "").rstrip("/") or None,
        google_client_id=_opcional(env, "GOOGLE_CLIENT_ID"),
        google_client_secret=_opcional(env, "GOOGLE_CLIENT_SECRET"),
        oauth_redirect_uri=_opcional(env, "OAUTH_REDIRECT_URI"),
        web_dist=_opcional(env, "FOPA_WEB_DIST") or WEB_DIST_PADRAO,
    )


__all__ = ["Config", "ConfigInvalida", "carregar", "AMBIENTES", "BACKENDS", "MODOS_AUTH",
           "TESSERACT_ESPERADO_PADRAO", "JOBS_CONCORRENCIA_PADRAO", "N8N_URL_PADRAO",
           "WEB_DIST_PADRAO", "S3_REGIAO_PADRAO"]
