# -*- coding: utf-8 -*-
"""
Contrato do override de produção `docker/compose.prod.yml` (F8) — sem subir nada.

O que se prova é o que o `docker compose config` RESOLVE com os dois arquivos
juntos (é assim que a VPS sobe, via COMPOSE_FILE):

  - só o Caddy tem porta pública; Postgres e worker não publicam nada; n8n e
    api ficam no loopback;
  - worker e api em FOPA_ENV=prod (cookie Secure), login só Google, storage s3;
  - as URLs públicas vêm dos dois domínios, sem como divergir: redirect do
    OAuth, WEBHOOK_URL do n8n, links dos e-mails;
  - SESSION_SECRET, S3 e a tag da imagem são obrigatórios: sem eles o compose
    recusa, dizendo o NOME da variável;
  - nenhum serviço recebe ANTHROPIC_API_KEY, e não há `env_file:`.

Valores daqui são falsos e só existem para o compose resolver `${VAR}`.
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
CADDYFILE = os.path.join(DOCKER, "Caddyfile.exemplo")

SITE, N8N = "fopa.exemplo.com.br", "n8n.fopa.exemplo.com.br"
ENV_FALSO = {
    "POSTGRES_PASSWORD": "pg", "N8N_DB_PASSWORD": "n8ndb", "N8N_RW_PASSWORD": "n8n",
    "WORKER_RW_PASSWORD": "worker", "API_RO_PASSWORD": "api", "API_RW_PASSWORD": "apirw",
    "N8N_ENCRYPTION_KEY": "chave", "FOPA_WORKER_TOKEN": "tw", "FOPA_SITE_TOKEN": "ts",
    "SESSION_SECRET": "ss", "FOPA_N8N_PUBLIC_URL": "https://%s/" % N8N, "FOPA_SITE_URL": "https://" + SITE,
    "FOPA_DOMINIO_SITE": SITE, "FOPA_DOMINIO_N8N": N8N, "ACME_EMAIL": "ops@exemplo.com.br",
    "CADDY_N8N_USUARIO": "fopa", "CADDY_N8N_HASH": "hash-falso",
    "GOOGLE_CLIENT_ID": "cliente", "GOOGLE_CLIENT_SECRET": "segredo-google",
    "S3_ENDPOINT": "https://conta.r2.cloudflarestorage.com", "S3_BUCKET": "fopa-prod",
    "S3_KEY": "chave-s3", "S3_SECRET": "segredo-s3", "FOPA_IMAGEM_TAG": "abc123def456",
}


def _config(tmp_path, sem: tuple = ()) -> subprocess.CompletedProcess:
    if shutil.which("docker") is None:
        pytest.skip("docker não está no PATH")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("FOPA_", "S3_", "CADDY_", "GOOGLE_", "COMPOSE_")) and "ANTHROPIC" not in k}
    env.update({k: v for k, v in ENV_FALSO.items() if k not in sem})
    vazio = tmp_path / "vazio.env"          # nunca o docker/.env real
    vazio.write_text("", encoding="utf-8")
    return subprocess.run(
        ["docker", "compose", "-f", "compose.yml", "-f", "compose.prod.yml", "--env-file", str(vazio),
         "--profile", "migrate", "--profile", "importar", "config", "--format", "json"],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=DOCKER)


@pytest.fixture(scope="module")
def cfg(tmp_path_factory) -> dict:
    r = _config(tmp_path_factory.mktemp("prod"))
    assert r.returncode == 0, "docker compose config (prod) falhou:\n%s" % r.stderr
    return json.loads(r.stdout)


def _env(cfg, servico) -> dict:
    return cfg["services"][servico].get("environment") or {}


def test_so_o_caddy_tem_porta_publica(cfg):
    s = cfg["services"]
    publicas = {(n, p["published"]) for n, d in s.items() for p in d.get("ports", [])
                if p.get("host_ip") not in ("127.0.0.1",)}
    assert publicas == {("fopa-caddy", "80"), ("fopa-caddy", "443")}
    assert not s["fopa-postgres"].get("ports"), "Postgres não publica porta em produção"
    assert not s["fopa-worker"].get("ports"), "o worker nunca publica porta"
    for n in ("fopa-n8n", "fopa-api"):
        assert all(p["host_ip"] == "127.0.0.1" for p in s[n]["ports"]), n


def test_worker_e_api_em_prod_com_s3_e_login_google(cfg):
    for n in ("fopa-worker", "fopa-api"):
        e = _env(cfg, n)
        assert e["FOPA_ENV"] == "prod" and e["STORAGE_BACKEND"] == "s3", n
        assert {k for k in e if k.startswith("S3_")} == {"S3_ENDPOINT", "S3_BUCKET", "S3_KEY", "S3_SECRET",
                                                          "S3_REGION"}, n
    assert _env(cfg, "fopa-api")["FOPA_AUTH_MODE"] == "google"
    for n in ("fopa-worker", "fopa-api", "fopa-migrate", "fopa-importar"):
        assert cfg["services"][n]["image"] == "fopa/worker:" + ENV_FALSO["FOPA_IMAGEM_TAG"], n


def test_urls_publicas_derivadas_dos_dominios(cfg):
    api, n8n = _env(cfg, "fopa-api"), _env(cfg, "fopa-n8n")
    assert api["FOPA_SITE_URL"] == "https://" + SITE
    assert api["OAUTH_REDIRECT_URI"] == "https://%s/auth/google/callback" % SITE
    assert n8n["WEBHOOK_URL"] == n8n["N8N_EDITOR_BASE_URL"] == "https://%s/" % N8N
    assert n8n["FOPA_SITE_PUBLIC_URL"] == "https://" + SITE
    assert n8n["N8N_SECURE_COOKIE"] == "true"
    # n8n -> worker por HTTPS dentro da rede, e o Caddy é quem atende esse nome
    assert n8n["FOPA_WORKER_URL"] == "https://fopa-worker-tls:8443"
    assert "fopa-worker-tls" in cfg["services"]["fopa-caddy"]["networks"]["default"]["aliases"]
    assert n8n["NODE_EXTRA_CA_CERTS"] in {v["target"] for v in cfg["services"]["fopa-n8n"]["volumes"]}


@pytest.mark.parametrize("falta", ["SESSION_SECRET", "S3_SECRET", "FOPA_IMAGEM_TAG", "FOPA_DOMINIO_SITE",
                                   "CADDY_N8N_HASH", "GOOGLE_CLIENT_SECRET"])
def test_variavel_obrigatoria_ausente_recusa(tmp_path, falta):
    r = _config(tmp_path, sem=(falta,))
    assert r.returncode != 0 and falta in r.stderr


def test_nenhum_servico_recebe_a_chave_da_anthropic_nem_env_file(cfg):
    for n, d in cfg["services"].items():
        assert not any("ANTHROPIC" in k for k in (d.get("environment") or {})), n
        assert "env_file" not in d, n


def test_caddyfile_so_deixa_o_webhook_publico():
    with open(CADDYFILE, encoding="utf-8") as f:
        texto = "\n".join(l for l in f.read().splitlines() if not l.lstrip().startswith("#"))
    bloco_n8n = texto[texto.index("{$FOPA_DOMINIO_N8N}"):texto.index("https://fopa-worker-tls:8443")]
    assert re.search(r"@webhook path /webhook/\*", bloco_n8n)
    # o resto do n8n passa por basic_auth antes do proxy
    resto = bloco_n8n[bloco_n8n.index("handle {"):]
    assert resto.index("basic_auth") < resto.index("reverse_proxy fopa-n8n:5678")
    assert "tls /etc/caddy/interno/worker.crt /etc/caddy/interno/worker.key" in texto
