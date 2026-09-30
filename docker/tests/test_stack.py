# -*- coding: utf-8 -*-
"""
Contrato da stack `docker/` (plano, seções 4, 6 e 12) — sem subir container.

O que se prova aqui é o que o `docker compose config` RESOLVE e o que o
Dockerfile DECLARA, porque são essas duas coisas que a operação depende e
que ninguém relê depois que a stack "funcionou uma vez":

  - o nome do projeto é `fopa`, e portas/volumes não colidem com a stack n8n
    de outra stack n8n (5678/5432, volumes `n8n_*`) nem com o PG17 nativo;
  - toda porta publicada fica em 127.0.0.1 — nada desta stack aparece na
    rede local por acidente, e o worker não publica porta nenhuma;
  - NENHUM serviço recebe `ANTHROPIC_API_KEY` (plano: a chave existe só na
    Credential do n8n; `/health.anthropic_key_presente` tem de ser false);
  - `fopa-migrate` só existe no profile `migrate`: `up -d` nunca migra sozinho;
  - o Dockerfile pina versão E sha256 de tudo que baixa (leptonica, Tesseract,
    `por.traineddata`) e confere com `sha256sum -c` — o build falha alto,
    nunca instala outra coisa em silêncio;
  - o `.env.exemplo` documenta todas as variáveis da seção 4 sem valor.

Precisa do `docker compose` no PATH (é o que valida o YAML de verdade); sem
ele os testes de compose são pulados com o motivo, nunca aprovados.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
DOCKER = os.path.dirname(AQUI)
RAIZ = os.path.dirname(DOCKER)
COMPOSE = os.path.join(DOCKER, "compose.yml")
DOCKERFILE = os.path.join(DOCKER, "worker.Dockerfile")
ENV_EXEMPLO = os.path.join(DOCKER, ".env.exemplo")
INIT_SQL = os.path.join(DOCKER, "postgres", "init", "01_bancos.sql")

SERVICOS = {"fopa-postgres", "fopa-n8n", "fopa-worker", "fopa-api", "fopa-migrate"}

# Pinos do plano (seção 4/6) e do ledger F0. Se alguém mudar um, o teste cobra
# que a mudança seja consciente.
TESSERACT = "5.4.0"
LEPTONICA = "1.84.1"
TESSDATA_COMMIT = "923915d4ced2a7235221788285785a29c4a42d4a"
TESSDATA_SHA256 = "c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb"
N8N_IMAGEM = "n8nio/n8n:2.37.10"
POSTGRES_IMAGEM = "postgres:16-alpine"

# Seção 4 "Variáveis (nomes)" + as senhas que a migração/compose exigem.
VARIAVEIS_SECAO_4 = [
    "FOPA_ENV", "FOPA_AUTH_MODE", "FOPA_N8N_PUBLIC_URL", "FOPA_SITE_URL",
    "FOPA_WORKER_URL", "FOPA_WORKER_TOKEN", "FOPA_SITE_TOKEN", "DATABASE_URL",
    "N8N_ENCRYPTION_KEY", "N8N_SECURE_COOKIE", "STORAGE_BACKEND", "STORAGE_ROOT",
    "S3_ENDPOINT", "S3_BUCKET", "S3_KEY", "S3_SECRET", "S3_REGION",
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "OAUTH_REDIRECT_URI", "SESSION_SECRET",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM",
    "FOPA_JOBS_CONCORRENCIA", "FOPA_TESSERACT_ESPERADO", "FOPA_TESSDATA_SHA256", "USD_BRL",
    "POSTGRES_PASSWORD", "N8N_DB_PASSWORD",
    "N8N_RW_PASSWORD", "WORKER_RW_PASSWORD", "API_RO_PASSWORD", "API_RW_PASSWORD",
]

# Valores só para o compose resolver `${VAR}` sem avisos: nada disto sobe.
ENV_FALSO = {
    "POSTGRES_PASSWORD": "pg", "N8N_DB_PASSWORD": "n8ndb", "N8N_RW_PASSWORD": "n8n",
    "WORKER_RW_PASSWORD": "worker", "API_RO_PASSWORD": "api", "API_RW_PASSWORD": "apirw",
    "N8N_ENCRYPTION_KEY": "chave", "FOPA_WORKER_TOKEN": "tw", "FOPA_SITE_TOKEN": "ts",
    "SESSION_SECRET": "ss", "FOPA_N8N_PUBLIC_URL": "http://localhost:5679/",
    "FOPA_SITE_URL": "http://localhost:8080",
}


def _compose_config(*extra: str) -> dict:
    if shutil.which("docker") is None:
        pytest.skip("docker não está no PATH")
    env = dict(os.environ, **ENV_FALSO)
    env.pop("ANTHROPIC_API_KEY", None)
    # `--env-file` explícito e vazio: o teste não depende do `.env` real de docker/.
    vazio = os.path.join(AQUI, ".env.vazio")
    with open(vazio, "w", encoding="utf-8") as f:
        f.write("")
    try:
        r = subprocess.run(
            ["docker", "compose", "-f", COMPOSE, "--env-file", vazio, *extra,
             "config", "--format", "json"],
            capture_output=True, text=True, encoding="utf-8", env=env, cwd=DOCKER)
    finally:
        os.remove(vazio)
    assert r.returncode == 0, "docker compose config falhou:\n%s" % r.stderr
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def cfg() -> dict:
    return _compose_config()


@pytest.fixture(scope="module")
def cfg_migrate() -> dict:
    return _compose_config("--profile", "migrate")


# ------------------------------------------------------------------ compose
def test_compose_nome_e_servicos(cfg, cfg_migrate):
    assert cfg["name"] == "fopa"
    assert set(cfg_migrate["services"]) == SERVICOS
    # Sem o profile, a migração não existe: `up -d` não pode migrar sozinho.
    assert "fopa-migrate" not in cfg["services"]
    assert cfg_migrate["services"]["fopa-migrate"]["profiles"] == ["migrate"]


def test_imagens_pinadas(cfg):
    s = cfg["services"]
    assert s["fopa-postgres"]["image"] == POSTGRES_IMAGEM
    assert s["fopa-n8n"]["image"] == N8N_IMAGEM
    # worker, api e migrate: a MESMA imagem, um único build.
    assert s["fopa-worker"]["build"]["dockerfile"].replace("\\", "/").endswith("docker/worker.Dockerfile")
    assert os.path.normcase(os.path.abspath(s["fopa-worker"]["build"]["context"])) == os.path.normcase(RAIZ)
    assert s["fopa-api"]["image"] == s["fopa-worker"]["image"]


def test_portas_so_em_loopback_e_sem_colisao(cfg):
    publicadas = {}
    for nome, svc in cfg["services"].items():
        for p in svc.get("ports", []):
            assert p.get("host_ip") == "127.0.0.1", "%s publica %r fora do loopback" % (nome, p)
            publicadas[nome] = (int(p["published"]), int(p["target"]))
    assert "fopa-worker" not in publicadas, "o worker não publica porta: só o n8n e a api falam com ele"
    assert publicadas["fopa-postgres"] == (5433, 5432)   # 5432 é do PG17 nativo
    assert publicadas["fopa-n8n"] == (5679, 5678)        # 5678 é de outra stack n8n
    assert publicadas["fopa-api"] == (8080, 8080)
    assert {5678, 5432} & {h for h, _ in publicadas.values()} == set()


def test_volumes_proprios(cfg):
    nomes = {v.get("name", k) for k, v in cfg["volumes"].items()}
    assert nomes == {"fopa_postgres_data", "fopa_n8n_data", "fopa_dados"}
    assert not any(n.startswith("n8n_") for n in nomes)


def _env(cfg: dict, servico: str) -> dict:
    return cfg["services"][servico].get("environment", {}) or {}


def test_nenhum_servico_recebe_a_chave_da_anthropic(cfg_migrate):
    for nome, svc in cfg_migrate["services"].items():
        chaves = set(_env(cfg_migrate, nome))
        assert not any("ANTHROPIC" in k or "OPENAI" in k for k in chaves), (nome, chaves)
        assert "env_file" not in svc, "%s: env_file despejaria o .env inteiro no container" % nome


def test_worker(cfg):
    env = _env(cfg, "fopa-worker")
    assert env["DATABASE_URL"].startswith("postgresql://worker_rw:")
    assert env["STORAGE_BACKEND"] == "fs" and env["STORAGE_ROOT"] == "/dados"
    assert env["FOPA_JOBS_CONCORRENCIA"] == "2"
    assert env["FOPA_TESSERACT_ESPERADO"] == TESSERACT
    assert env["FOPA_TESSDATA_SHA256"] == TESSDATA_SHA256
    assert env["FOPA_WORKER_TOKEN"] == ENV_FALSO["FOPA_WORKER_TOKEN"]
    vols = cfg["services"]["fopa-worker"]["volumes"]
    assert any(v["source"] == "fopa_dados" and v["target"] == "/dados" and not v.get("read_only")
               for v in vols)
    # Nunca bind mount de scripts/: o pacote é congelado no build (plano, seção 4).
    assert all(v["type"] == "volume" for v in vols)
    hc = cfg["services"]["fopa-worker"]["healthcheck"]["test"]
    assert "/health" in " ".join(hc) and "urllib" in " ".join(hc)


def test_api(cfg):
    svc = cfg["services"]["fopa-api"]
    env = _env(cfg, "fopa-api")
    assert env["DATABASE_URL"].startswith("postgresql://api_rw:")   # 016
    assert env["FOPA_WORKER_URL"] == "http://fopa-worker:8000"
    for k in ("FOPA_WORKER_TOKEN", "FOPA_SITE_TOKEN", "FOPA_ENV", "FOPA_AUTH_MODE",
              "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "OAUTH_REDIRECT_URI",
              "SESSION_SECRET", "SMTP_HOST"):
        assert k in env, k
    assert "api.site:app" in " ".join(svc["command"])
    assert "8080" in " ".join(svc["command"])
    vols = svc["volumes"]
    assert any(v["source"] == "fopa_dados" and v["target"] == "/dados" and v.get("read_only")
               for v in vols), "a api só lê o storage"


def test_migrate(cfg_migrate):
    svc = cfg_migrate["services"]["fopa-migrate"]
    env = _env(cfg_migrate, "fopa-migrate")
    assert env["DATABASE_URL"].startswith("postgresql://postgres:")   # superusuário: cria papéis
    for k in ("N8N_RW_PASSWORD", "WORKER_RW_PASSWORD", "API_RO_PASSWORD", "API_RW_PASSWORD"):
        assert env[k] == ENV_FALSO[k]
    assert "db/migrar.py" in " ".join(svc["command"])


def test_n8n(cfg):
    svc = cfg["services"]["fopa-n8n"]
    env = _env(cfg, "fopa-n8n")
    esperado = {
        "DB_TYPE": "postgresdb", "DB_POSTGRESDB_HOST": "fopa-postgres",
        "DB_POSTGRESDB_DATABASE": "n8n",
        "GENERIC_TIMEZONE": "America/Sao_Paulo", "TZ": "America/Sao_Paulo",
        "WEBHOOK_URL": ENV_FALSO["FOPA_N8N_PUBLIC_URL"],
        "EXECUTIONS_DATA_SAVE_ON_PROGRESS": "true", "EXECUTIONS_DATA_PRUNE": "true",
        "EXECUTIONS_DATA_MAX_AGE": "720", "N8N_SECURE_COOKIE": "false",
        "N8N_BLOCK_ENV_ACCESS_IN_NODE": "false", "N8N_RUNNERS_ENABLED": "true",
        "N8N_DIAGNOSTICS_ENABLED": "false",
        "FOPA_WORKER_URL": "http://fopa-worker:8000", "FOPA_SITE_URL": "http://fopa-api:8080",
    }
    for k, v in esperado.items():
        assert env.get(k) == v, (k, env.get(k))
    assert env["N8N_ENCRYPTION_KEY"] == ENV_FALSO["N8N_ENCRYPTION_KEY"]
    assert "N8N_EDITOR_BASE_URL" in env
    # O freio de extrações simultâneas é o Postgres, não o n8n (plano, seção 4).
    assert "N8N_CONCURRENCY_PRODUCTION_LIMIT" not in env
    assert svc["depends_on"]["fopa-postgres"]["condition"] == "service_healthy"


def test_postgres(cfg):
    svc = cfg["services"]["fopa-postgres"]
    env = _env(cfg, "fopa-postgres")
    assert env["POSTGRES_DB"] == "fopa"
    assert "pg_isready" in " ".join(svc["healthcheck"]["test"])
    inits = [v for v in svc["volumes"] if v["type"] == "bind"]
    assert any(v["target"] == "/docker-entrypoint-initdb.d" and v.get("read_only") for v in inits)
    with open(INIT_SQL, encoding="utf-8") as f:
        sql = f.read()
    assert re.search(r"CREATE DATABASE n8n\b", sql)


# --------------------------------------------------------------- Dockerfile
@pytest.fixture(scope="module")
def dockerfile() -> str:
    with open(DOCKERFILE, encoding="utf-8") as f:
        return f.read()


def _arg(texto: str, nome: str) -> str:
    m = re.search(r"^ARG %s=(\S+)" % re.escape(nome), texto, re.M)
    assert m, "ARG %s ausente" % nome
    return m.group(1)


def test_dockerfile_multi_stage_e_bases(dockerfile):
    froms = re.findall(r"^FROM\s+(\S+)", dockerfile, re.M)
    assert froms[0].startswith("debian:bookworm-slim")
    assert froms[-1].startswith("python:3.12-slim-bookworm")
    assert "COPY --from=" in dockerfile



def test_dockerfile_versao_do_tesseract_tem_uma_fonte_so(dockerfile):
    # Minor adiado da revisão final da F0: o estágio final repetia "5.4.0" à mão no ENV FOPA_TESSERACT_ESPERADO
    # e no portão de versão — trocar o ARG compilaria uma versão e conferiria outra. A versão é um ARG GLOBAL
    # (antes do primeiro FROM), redeclarado sem valor em cada estágio que o usa.
    globais = dockerfile.split("\nFROM ", 1)[0]
    assert re.search(r"^ARG TESSERACT_VERSAO=%s$" % re.escape(TESSERACT), globais, re.M), "ARG global ausente"
    assert len(re.findall(r"^ARG TESSERACT_VERSAO=", dockerfile, re.M)) == 1, "um valor só"
    final = dockerfile.rsplit("\nFROM ", 1)[1]
    assert re.search(r"^ARG TESSERACT_VERSAO$", final, re.M), "o estágio final não redeclara o ARG"
    assert "FOPA_TESSERACT_ESPERADO=${TESSERACT_VERSAO}" in final
    assert '= "${TESSERACT_VERSAO}"' in final, "o portão de versão do estágio final não usa o ARG"
    assert not re.search(r"\b%s\b" % re.escape(TESSERACT), "\n".join(
        l for l in final.splitlines() if not l.lstrip().startswith("#"))), "versão literal no estágio final"


def test_dockerfile_pina_versoes_e_shas(dockerfile):
    assert _arg(dockerfile, "LEPTONICA_VERSAO") == LEPTONICA
    assert _arg(dockerfile, "TESSERACT_VERSAO") == TESSERACT
    assert _arg(dockerfile, "TESSDATA_COMMIT") == TESSDATA_COMMIT
    assert _arg(dockerfile, "FOPA_TESSDATA_SHA256") == TESSDATA_SHA256
    for nome in ("LEPTONICA_SHA256", "TESSERACT_SHA256"):
        assert re.fullmatch(r"[0-9a-f]{64}", _arg(dockerfile, nome)), nome
    # Três downloads, três conferências: a contagem é o que impede alguém de
    # adicionar um quarto download sem sha.
    assert len(re.findall(r"sha256sum\s+-c", dockerfile)) >= 3
    assert "FOPA_GIT_SHA" in dockerfile


def test_dockerfile_portoes_e_medicao(dockerfile):
    # O portão de versão confere o ARG (a fonte única; test_dockerfile_versao_do_tesseract_tem_uma_fonte_so),
    # não um literal repetido à mão.
    assert re.search(r'test\s+"\$\(tesseract --version[^)]*\)"\s*=\s*"\$\{TESSERACT_VERSAO\}"', dockerfile)
    assert "tesseract --list-langs" in dockerfile and "grep -qx por" in dockerfile
    assert "ocr.checar_ambiente()" in dockerfile
    assert "tests/ocr_baseline/medir.py" in dockerfile
    assert "ocr-equivalencia-imagem.json" in dockerfile
    assert "uvicorn" in dockerfile and "api.worker:app" in dockerfile


def test_dockerfile_env_e_ordem_de_camadas(dockerfile):
    for var in ("TESSDATA_PREFIX", "FOPA_TESSERACT=/usr/local/bin/tesseract",
                "FOPA_TESSDATA=/usr/local/share/tessdata", "FOPA_TESSERACT_ESPERADO",
                "FOPA_TESSDATA_SHA256", "PYTHONUNBUFFERED"):
        assert var in dockerfile, var
    # Nenhuma INSTRUÇÃO menciona a chave (comentário explicando o porquê pode).
    instrucoes = "\n".join(l for l in dockerfile.splitlines() if not l.lstrip().startswith("#"))
    assert "ANTHROPIC" not in instrucoes
    # Compilação e pip antes de qualquer COPY do código: mudar um .py não
    # recompila o Tesseract nem reinstala dependência.
    i_make = dockerfile.index("make ")
    i_pip = dockerfile.index("pip install")
    i_copy_codigo = re.search(r"^COPY\s+scripts/", dockerfile, re.M).start()
    assert i_make < i_pip < i_copy_codigo


# -------------------------------------------------------------- .env.exemplo
def test_env_exemplo_documenta_todas_as_variaveis_sem_valor():
    with open(ENV_EXEMPLO, encoding="utf-8") as f:
        linhas = f.read().splitlines()
    definidas = {}
    for linha in linhas:
        m = re.match(r"^#?\s*([A-Z][A-Z0-9_]*)=(.*)$", linha)
        if m:
            definidas[m.group(1)] = m.group(2).strip()
    faltam = [v for v in VARIAVEIS_SECAO_4 if v not in definidas]
    assert not faltam, "faltam no .env.exemplo: %s" % faltam
    # Sem valor: o exemplo ensina os nomes, nunca carrega segredo nem default escondido.
    com_valor = {k: v for k, v in definidas.items() if v}
    assert not com_valor, com_valor
    assert "ANTHROPIC_API_KEY" not in definidas


# ------------------------------------------------------------------ importar
@pytest.fixture(scope="module")
def cfg_importar() -> dict:
    return _compose_config("--profile", "importar")


def test_importar_so_no_profile_e_com_menor_privilegio(cfg, cfg_importar):
    # A importação do acervo (plano, seção 9) roda DENTRO da stack para os PDFs
    # irem para o volume que a api serve; como worker_rw, nunca superusuário;
    # snapshot e amostras montados só para leitura — ela nunca escreve no v2.
    assert "fopa-importar" not in cfg["services"]
    svc = cfg_importar["services"]["fopa-importar"]
    assert svc["profiles"] == ["importar"]
    assert svc["image"] == cfg["services"]["fopa-worker"]["image"]
    env = svc.get("environment") or {}
    assert env["DATABASE_URL"].startswith("postgresql://worker_rw:")
    assert env["STORAGE_ROOT"] == "/dados"
    assert not any("ANTHROPIC" in k or "OPENAI" in k for k in env)
    assert "migracao.importar" in " ".join(svc["command"])
    alvos = {v["target"]: v for v in svc["volumes"]}
    assert alvos["/dados"]["source"] == "fopa_dados" and not alvos["/dados"].get("read_only")
    assert alvos["/acervo"].get("read_only") and alvos["/amostras"].get("read_only")


def test_imagem_leva_o_pacote_de_migracao():
    texto = open(DOCKERFILE, encoding="utf-8").read()
    assert re.search(r"^COPY migracao/ \./migracao/", texto, re.M)
    ignorado = open(os.path.join(RAIZ, ".dockerignore"), encoding="utf-8").read()
    # o snapshot (~300 MB) nunca entra no contexto do build: vai montado
    assert re.search(r"^acervo/", ignorado, re.M)
