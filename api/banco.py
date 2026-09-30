# -*- coding: utf-8 -*-
"""Conexão do worker com o Postgres (papel worker_rw no compose)."""
from __future__ import annotations

import psycopg

from . import config


class BancoIndisponivel(RuntimeError):
    """DATABASE_URL ausente: o worker sobe (para /health), mas não trabalha."""


def conectar(cfg: config.Config | None = None) -> psycopg.Connection:
    cfg = cfg or config.carregar()
    if not cfg.database_url:
        raise BancoIndisponivel("DATABASE_URL não definida")
    return psycopg.connect(cfg.database_url)


__all__ = ["conectar", "BancoIndisponivel"]
