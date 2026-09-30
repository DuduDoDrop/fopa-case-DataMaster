# -*- coding: utf-8 -*-
"""
Guardas da stack viva — camada (b). Plano 11.8: "`docker inspect fopa-worker`
não mostra a chave"; 11.1: "`/health.anthropic_key_presente=false`".

O compose já é conferido sem subir nada (docker/tests/test_stack.py: nenhum
serviço declara a chave). Aqui é o container que ESTÁ rodando: um `docker run
-e ANTHROPIC_API_KEY=...` à mão, ou um compose editado e não commitado, só
aparece no `docker inspect`. Só NOMES de variável saem em mensagem, nunca valor.

Sem docker ou sem o container, o teste é PULADO com o motivo — nunca aprovado.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ci.sem_chave import CHAVES, proibida  # noqa: E402

# fopa-worker e fopa-api são os que o plano nomeia; o n8n também não pode ter
# a chave no Env (ela existe só na Credential dele).
CONTAINERS = ("fopa-worker", "fopa-api", "fopa-n8n")


def proibidas_no_env(env: list[str]) -> list[str]:
    nomes = [e.split("=", 1)[0] for e in env or []]
    return sorted(n for n in nomes if n in CHAVES or proibida(n))


def _docker(*args: str) -> subprocess.CompletedProcess:
    if shutil.which("docker") is None:
        pytest.skip("docker não está no PATH")
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)


def _env_do_container(nome: str) -> list[str]:
    r = _docker("inspect", "--format", "{{json .Config.Env}}", nome)
    if r.returncode != 0:
        pytest.skip("container %s indisponível (stack fora do ar?): %s"
                    % (nome, (r.stderr.strip().splitlines() or ["?"])[0][:160]))
    return json.loads(r.stdout or "[]")


@pytest.mark.parametrize("nome", CONTAINERS)
def test_container_sem_chave_de_modelo_no_env(nome):
    achadas = proibidas_no_env(_env_do_container(nome))
    assert not achadas, "%s tem %s no Env (docker inspect)" % (nome, achadas)


def test_health_do_worker_diz_que_a_chave_nao_esta_presente():
    _env_do_container("fopa-worker")         # pula se o container não existe
    # O worker não publica porta (só a rede do compose fala com ele): pergunta-se
    # de dentro. 503 (OCR fora do contrato) ainda traz o corpo com o campo.
    codigo = ("import json, urllib.request, urllib.error\n"
              "try:\n"
              "    r = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=10); c = r.read()\n"
              "except urllib.error.HTTPError as e:\n"
              "    c = e.read()\n"
              "print(json.dumps(json.loads(c).get('anthropic_key_presente')))\n")
    r = _docker("exec", "fopa-worker", "python", "-c", codigo)
    if r.returncode != 0:
        pytest.skip("não deu para perguntar o /health de dentro do fopa-worker: %s"
                    % (r.stderr.strip().splitlines() or ["?"])[-1][:160])
    assert r.stdout.strip() == "false", "/health.anthropic_key_presente = %s" % r.stdout.strip()


def test_guarda_do_env_sabe_falhar():
    env = ["PATH=/usr/bin", "ANTHROPIC_API_KEY=sk-x", "OPENAI_API_KEY=y", "FOPA_WORKER_TOKEN=t",
           "ANTHROPIC_BASE_URL=z"]
    assert proibidas_no_env(env) == ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "OPENAI_API_KEY"]
    assert proibidas_no_env(["PATH=/usr/bin", "FOPA_ENV=dev"]) == []
