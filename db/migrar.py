# -*- coding: utf-8 -*-
"""
Aplica as migrações db/0NN_*.sql em ordem alfabética num único banco (fopa).

    DATABASE_URL=postgresql://... python db/migrar.py [--pasta db]

Registra cada arquivo em `schema_migracoes(nome, sha256, em)`. Arquivo já
aplicado é pulado; arquivo já aplicado cujo sha256 mudou ABORTA — migração é
histórico, não configuração: quem precisa mudar o esquema escreve o 0NN
seguinte. Cada arquivo roda numa transação própria; se falhar no meio, nada
daquele arquivo fica e o registro não é gravado.

Senhas dos papéis (n8n_rw, worker_rw, api_ro) NUNCA ficam no SQL: vêm de
N8N_RW_PASSWORD / WORKER_RW_PASSWORD / API_RO_PASSWORD e só são aplicadas
(ALTER ROLE ... PASSWORD) quando a variável existe. Assim o mesmo migrar.py
serve ao teste efêmero, ao compose local e à nuvem.

Saída: uma linha por arquivo e, por último, `aplicadas=N puladas=M`, que é o
que o teste e o `docker compose run fopa-migrate` conferem.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

import psycopg
from psycopg import sql

PADRAO = re.compile(r"^\d{3}_.*\.sql$")

PAPEIS_SENHA = (
    ("n8n_rw", "N8N_RW_PASSWORD"),
    ("worker_rw", "WORKER_RW_PASSWORD"),
    ("api_ro", "API_RO_PASSWORD"),
    ("api_rw", "API_RW_PASSWORD"),   # 016: o site escreve as tabelas dele
)


class ShaDivergente(RuntimeError):
    """Um arquivo já aplicado foi editado depois de aplicado."""


def listar(pasta: Path) -> list[Path]:
    return sorted(p for p in pasta.iterdir() if PADRAO.match(p.name))


def sha256(caminho: Path) -> str:
    # Normaliza CRLF -> LF antes do hash. O repositório roda com
    # core.autocrlf=true: o mesmo arquivo sai LF num clone Linux e CRLF no
    # próximo checkout no Windows, e o sha dos bytes crus mudava sem ninguém
    # ter editado a migração -- o que faria este script ABORTAR contra um banco
    # íntegro. Arquivo LF mantém o sha de sempre; editar o conteúdo continua
    # mudando o sha. Ver db/tests/test_sha_fim_de_linha.py.
    return hashlib.sha256(caminho.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _garantir_registro(conn: psycopg.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migracoes ("
        " nome text PRIMARY KEY, sha256 char(64) NOT NULL,"
        " em timestamptz NOT NULL DEFAULT now())")
    conn.commit()


def aplicar(url: str, pasta: Path, saida=sys.stdout) -> tuple[list[str], list[str]]:
    """Aplica o que falta. Devolve (aplicadas, puladas)."""
    aplicadas: list[str] = []
    puladas: list[str] = []
    with psycopg.connect(url) as conn:
        _garantir_registro(conn)
        gravadas = {n: s for n, s in conn.execute("SELECT nome, sha256 FROM schema_migracoes")}
        for arq in listar(pasta):
            sha = sha256(arq)
            if arq.name in gravadas:
                if gravadas[arq.name] != sha:
                    raise ShaDivergente(
                        "%s já foi aplicada com sha256 %s e o arquivo em disco tem %s; "
                        "migração aplicada não se edita, escreva a próxima"
                        % (arq.name, gravadas[arq.name], sha))
                puladas.append(arq.name)
                print("  pulada   %s" % arq.name, file=saida)
                continue
            # Sem parâmetros o psycopg 3 manda o arquivo inteiro pelo protocolo
            # simples: vários comandos, DO $$ ... $$ e funções passam de uma vez.
            conn.execute(arq.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migracoes (nome, sha256) VALUES (%s, %s)",
                         (arq.name, sha))
            conn.commit()
            aplicadas.append(arq.name)
            print("  aplicada %s" % arq.name, file=saida)
        _senhas(conn, saida)
    return aplicadas, puladas


def _senhas(conn: psycopg.Connection, saida) -> None:
    """ALTER ROLE ... PASSWORD só para os papéis cuja env existe."""
    for papel, var in PAPEIS_SENHA:
        senha = os.environ.get(var)
        if not senha:
            continue
        existe = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (papel,)).fetchone()
        if not existe:
            print("  aviso: papel %s não existe, %s ignorada" % (papel, var), file=saida)
            continue
        conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
            sql.Identifier(papel), sql.Literal(senha)))
        conn.commit()
        print("  senha    %s (de %s)" % (papel, var), file=saida)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pasta", default=str(Path(__file__).resolve().parent),
                    help="pasta com os 0NN_*.sql (padrão: a deste script)")
    ap.add_argument("--url", default=os.environ.get("DATABASE_URL"),
                    help="URL do Postgres (padrão: DATABASE_URL)")
    a = ap.parse_args(argv)
    if not a.url:
        print("DATABASE_URL não definida", file=sys.stderr)
        return 2
    try:
        aplicadas, puladas = aplicar(a.url, Path(a.pasta))
    except ShaDivergente as e:
        print("ERRO sha256: %s" % e, file=sys.stderr)
        return 3
    except psycopg.Error as e:
        print("ERRO Postgres: %s" % e, file=sys.stderr)
        return 1
    print("aplicadas=%d puladas=%d" % (len(aplicadas), len(puladas)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
