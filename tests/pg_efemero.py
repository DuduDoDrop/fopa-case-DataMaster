# -*- coding: utf-8 -*-
"""
Postgres 16 efêmero para testes: um container por sessão, porta sorteada.

Extraído do fixture de `db/tests/test_migracoes.py` para que a migração
(`migracao/tests`) e o worker (`api/tests`) testem contra o MESMO banco real,
com as mesmas migrações, sem mock. `pg_isready` dentro do container responde
antes do restart que o entrypoint faz após o init; por isso a URL só é
liberada depois de uma conexão TCP real pelo host.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parents[1]
MIGRAR = RAIZ / "db" / "migrar.py"
SENHA_ADMIN = "fopa-teste"
SENHAS = {"N8N_RW_PASSWORD": "n8n-teste", "WORKER_RW_PASSWORD": "worker-teste",
          "API_RO_PASSWORD": "api-teste",
          "API_RW_PASSWORD": "api-rw-teste"}


def _docker(*args: str, check: bool = True) -> str:
    r = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("docker %s falhou: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


@contextlib.contextmanager
def subir():
    """Sobe o container, espera aceitar conexão, entrega a URL de superusuário, derruba."""
    cid = _docker("run", "-d", "--rm", "-e", "POSTGRES_PASSWORD=" + SENHA_ADMIN,
                  "-e", "POSTGRES_DB=fopa", "-p", "127.0.0.1:0:5432", "postgres:16-alpine")
    try:
        porta = _docker("port", cid, "5432/tcp").splitlines()[0].rsplit(":", 1)[1]
        url = "postgresql://postgres:%s@127.0.0.1:%s/fopa" % (SENHA_ADMIN, porta)
        limite = time.time() + 90
        while time.time() < limite:
            if subprocess.run(["docker", "exec", cid, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                              capture_output=True).returncode == 0:
                try:
                    with psycopg.connect(url, connect_timeout=3) as c:
                        c.execute("SELECT 1")
                    break
                except psycopg.OperationalError:
                    pass
            time.sleep(1)
        else:
            raise RuntimeError("Postgres efêmero não ficou pronto em 90 s:\n"
                               + _docker("logs", cid, check=False))
        yield url
    finally:
        # `-v`: sem ele o volume anônimo do Postgres (dados do teste) fica órfão a cada rodada (28/09).
        _docker("rm", "-f", "-v", cid, check=False)


def migrar(url: str) -> str:
    """Aplica db/0NN_*.sql com o migrar.py de verdade (o mesmo do compose)."""
    env = dict(os.environ, DATABASE_URL=url, PYTHONIOENCODING="utf-8", **SENHAS)
    env.pop("ANTHROPIC_API_KEY", None)
    r = subprocess.run([sys.executable, str(MIGRAR)], env=env, capture_output=True,
                       text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("migrar.py falhou:\n%s\n%s" % (r.stdout, r.stderr))
    return r.stdout


def url_papel(url: str, papel: str) -> str:
    """A mesma URL com outro papel (n8n_rw, worker_rw, api_ro)."""
    senha = {"n8n_rw": SENHAS["N8N_RW_PASSWORD"], "worker_rw": SENHAS["WORKER_RW_PASSWORD"],
             "api_ro": SENHAS["API_RO_PASSWORD"], "api_rw": SENHAS["API_RW_PASSWORD"]}[papel]
    return url.replace("postgres:" + SENHA_ADMIN, "%s:%s" % (papel, senha))
