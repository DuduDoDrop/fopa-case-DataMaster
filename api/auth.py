# -*- coding: utf-8 -*-
"""
Autenticação do worker: `Authorization: Bearer ${FOPA_WORKER_TOKEN}` em tudo,
exceto `GET /health` (plano, seção 6).

POR QUE UM TOKEN ÚNICO E NÃO USUÁRIOS
  Quem fala com o worker é o n8n (Credential "worker") e o `fopa-api` — dois
  processos, nenhuma pessoa. O worker não é publicado fora da rede do compose;
  o Bearer existe para que "não publicado" não seja a única defesa, e para que
  o mesmo código sirva atrás de HTTPS na nuvem (F8).

CÓDIGOS
  401 — sem credencial (ou esquema que não é Bearer): o cliente não se apresentou.
  403 — credencial apresentada, mas errada.
  503 — `FOPA_WORKER_TOKEN` não configurado. Recusar tudo é o único
        comportamento seguro: "sem token = aberto" seria um container
        exposto por um `.env` esquecido.
"""
from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config

_esquema = HTTPBearer(auto_error=False)


def exigir_token(credencial: HTTPAuthorizationCredentials | None = Depends(_esquema)) -> None:
    esperado = config.carregar().worker_token
    if not esperado:
        raise HTTPException(503, "FOPA_WORKER_TOKEN não configurado no worker")
    if credencial is None or credencial.scheme.lower() != "bearer":
        raise HTTPException(401, "credencial Bearer ausente",
                            headers={"WWW-Authenticate": "Bearer"})
    # compare_digest: tempo constante, para o token não vazar byte a byte por timing.
    if not hmac.compare_digest(credencial.credentials.encode(), esperado.encode()):
        raise HTTPException(403, "token inválido")


__all__ = ["exigir_token"]
