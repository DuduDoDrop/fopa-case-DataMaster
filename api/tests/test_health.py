# -*- coding: utf-8 -*-
"""
Testes do worker (`GET /health`, `GET /versao`), do módulo de versões e do
`GET /api/saude` do site.

Tudo roda sem rede paga e com `ANTHROPIC_API_KEY` ausente: o único binário
externo tocado é o Tesseract do host, e onde ele não é essencial o
`checar_ambiente` é substituído por monkeypatch para o teste ser determinístico.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

import api
from api import config, versao
from fopa import ocr, questionario

HEX64 = re.compile(r"^[0-9a-f]{64}$")
TOKEN = "token-de-teste-123"

AMBIENTE_OK = {"tesseract": "5.4.0.20240606", "tessdata": ocr.TESSDATA, "idiomas": ["por"]}


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Ambiente mínimo do worker; sem chave da Anthropic, por definição."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("FOPA_ENV", "dev")
    monkeypatch.setenv("FOPA_WORKER_TOKEN", TOKEN)
    monkeypatch.setenv("STORAGE_BACKEND", "fs")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("FOPA_TESSERACT_ESPERADO", "5.4.0")
    monkeypatch.setenv("FOPA_GIT_SHA", "abc123")
    # n8n numa porta fechada local: recusa na hora (o padrão fopa-n8n leva ~2,7 s de DNS no Windows).
    monkeypatch.setenv("FOPA_N8N_URL", "http://127.0.0.1:9")
    return monkeypatch


@pytest.fixture
def cliente(env):
    from api import worker
    return TestClient(worker.app)


@pytest.fixture
def ambiente_falso(env):
    """Tesseract simulado: o /health não pode depender do binário do host nos testes de contrato."""
    env.setattr(ocr, "checar_ambiente", lambda: dict(AMBIENTE_OK))
    return env


# ------------------------------------------------------------------ /health
def test_health_responde_sem_auth_e_com_os_campos(cliente, ambiente_falso):
    r = cliente.get("/health")
    assert r.status_code == 200, r.text
    corpo = r.json()
    for campo in ("ok", "git_sha", "tesseract", "tessdata_sha256", "idiomas",
                  "versao_regras", "versao_prompt", "escopo_versao", "storage",
                  "anthropic_key_presente"):
        assert campo in corpo, campo
    assert corpo["ok"] is True
    assert corpo["git_sha"] == "abc123"
    assert corpo["tesseract"] == "5.4.0.20240606"
    assert "por" in corpo["idiomas"]
    assert corpo["storage"]["backend"] == "fs"
    for h in ("versao_regras", "versao_prompt", "escopo_versao"):
        assert HEX64.match(corpo[h]), (h, corpo[h])



def test_health_config_invalida_e_503_com_o_motivo(cliente, ambiente_falso):
    # Achado da revisão final da F0 (adiado até 24/09): uma variável inválida (STORAGE_BACKEND=xpto) derrubava o
    # /health num 500 opaco — o healthcheck caía sem dizer por quê. Agora é 503, no formato do /health, com a
    # variável e os valores aceitos (são escolhas e números, nunca segredo).
    ambiente_falso.setenv("STORAGE_BACKEND", "xpto")
    r = cliente.get("/health")
    assert r.status_code == 503, r.text
    corpo = r.json()
    assert corpo["ok"] is False
    assert "STORAGE_BACKEND" in corpo["erro"] and "fs|s3" in corpo["erro"], corpo["erro"]
    assert corpo["git_sha"] == "abc123"


def test_rota_do_worker_com_config_invalida_e_503(cliente, ambiente_falso):
    # O mesmo nas outras rotas: a config é lida por requisição, e config errada não é "erro interno".
    ambiente_falso.setenv("FOPA_ENV", "producao")
    r = cliente.post("/render", json={"verificacao_id": 1}, headers={"Authorization": "Bearer " + TOKEN})
    assert r.status_code == 503, r.text
    assert "FOPA_ENV" in r.json()["detail"]


def test_health_tessdata_sha256_e_o_do_arquivo_apontado(cliente, ambiente_falso):
    esperado = None
    caminho = os.path.join(ocr.TESSDATA, "por.traineddata")
    if os.path.exists(caminho):
        with open(caminho, "rb") as f:
            esperado = hashlib.sha256(f.read()).hexdigest()
    assert cliente.get("/health").json()["tessdata_sha256"] == esperado


def test_health_anthropic_key_presente_false_sem_env(cliente, ambiente_falso):
    assert cliente.get("/health").json()["anthropic_key_presente"] is False


def test_health_anthropic_key_presente_true_com_env_e_nunca_expoe_o_valor(cliente, ambiente_falso):
    ambiente_falso.setenv("ANTHROPIC_API_KEY", "sk-ant-segredo-que-nao-pode-vazar")
    r = cliente.get("/health")
    assert r.json()["anthropic_key_presente"] is True
    assert "segredo-que-nao-pode-vazar" not in r.text
    assert TOKEN not in r.text


def test_health_503_quando_tesseract_diverge_do_esperado(cliente, ambiente_falso):
    ambiente_falso.setattr(ocr, "checar_ambiente",
                           lambda: dict(AMBIENTE_OK, tesseract="5.3.0"))
    r = cliente.get("/health")
    assert r.status_code == 503
    assert r.json()["ok"] is False
    assert "5.3.0" in r.json()["erro"] and "5.4.0" in r.json()["erro"]


def test_health_503_quando_esperado_da_env_nao_bate(cliente, ambiente_falso):
    ambiente_falso.setenv("FOPA_TESSERACT_ESPERADO", "9.9.9")
    assert cliente.get("/health").status_code == 503


def test_health_aceita_build_com_sufixo_de_data(cliente, ambiente_falso):
    # O host das medições reporta '5.4.0.20240606'; a ADR-008 fixa '5.4.0'.
    # O sufixo é data de build, não versão: tem de bater.
    ambiente_falso.setattr(ocr, "checar_ambiente",
                           lambda: dict(AMBIENTE_OK, tesseract="5.4.0.20240606"))
    assert cliente.get("/health").status_code == 200


def test_health_503_quando_ocr_indisponivel(cliente, ambiente_falso):
    def falha():
        raise ocr.OcrIndisponivel("tesseract não encontrado em /nada")
    ambiente_falso.setattr(ocr, "checar_ambiente", falha)
    r = cliente.get("/health")
    assert r.status_code == 503
    assert r.json()["ok"] is False
    assert r.json()["tesseract"] is None
    assert "não encontrado" in r.json()["erro"]


def test_health_503_quando_falta_por(cliente, ambiente_falso):
    ambiente_falso.setattr(ocr, "checar_ambiente",
                           lambda: dict(AMBIENTE_OK, idiomas=["eng", "osd"]))
    assert cliente.get("/health").status_code == 503


def test_health_real_contra_o_tesseract_do_host(cliente):
    """Sem monkeypatch: o que o host devolve de verdade. Pula se não há Tesseract."""
    try:
        amb = ocr.checar_ambiente()
    except ocr.OcrIndisponivel as e:
        pytest.skip("OCR indisponível neste host: %s" % e)
    r = cliente.get("/health")
    assert r.json()["tesseract"] == amb["tesseract"]
    assert r.json()["idiomas"] == amb["idiomas"]


# ------------------------------------------------------------------ /versao
def _rotas_abertas(app, cliente_app) -> list:
    """(método, rota, status) de toda rota da app que NÃO responde 401 sem token — fora a /health."""
    from fastapi.routing import APIRoute
    abertas = []
    for r in app.routes:
        if not isinstance(r, APIRoute) or r.path == "/health":
            continue
        caminho = re.sub(r"\{[^}]+\}", "1", r.path)
        for metodo in sorted(r.methods - {"HEAD", "OPTIONS"}):
            resp = cliente_app.request(metodo, caminho, json={} if metodo in ("POST", "PUT", "PATCH") else None)
            if resp.status_code != 401:
                abertas.append((metodo, r.path, resp.status_code))
    return abertas


def test_toda_rota_do_worker_exige_token_menos_a_health(cliente):
    # Plano §6: "Bearer em tudo exceto GET /health". Hoje cada router declara o token; uma rota nova sem ele
    # passaria despercebida — este guarda percorre TODAS as rotas da app (auditoria de 24/09).
    from api import worker
    assert _rotas_abertas(worker.app, cliente) == []
    # o guarda sabe falhar: uma app com uma rota aberta é pega
    from fastapi import FastAPI
    aberta = FastAPI()
    aberta.get("/aberta")(lambda: {"ok": True})
    assert _rotas_abertas(aberta, TestClient(aberta)) == [("GET", "/aberta", 200)]


def test_versao_sem_token_401(cliente):
    assert cliente.get("/versao").status_code == 401


def test_versao_token_errado_403(cliente):
    r = cliente.get("/versao", headers={"Authorization": "Bearer outro-token"})
    assert r.status_code == 403


def test_versao_esquema_errado_401(cliente):
    r = cliente.get("/versao", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401


def test_versao_token_certo_200_com_quatro_hashes(cliente, ambiente_falso):
    r = cliente.get("/versao", headers={"Authorization": "Bearer " + TOKEN})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert set(corpo) == {"versao_regras", "versao_prompt", "escopo_versao", "versao_ocr"}
    for h in ("versao_regras", "versao_prompt", "escopo_versao"):
        assert HEX64.match(corpo[h]), (h, corpo[h])
    assert corpo["versao_ocr"] == "5.4.0.20240606"


def test_versao_sem_token_configurado_e_503_nao_200(cliente, env):
    # Sem FOPA_WORKER_TOKEN o worker recusa tudo: aceitar "qualquer token" seria pior.
    env.delenv("FOPA_WORKER_TOKEN")
    r = cliente.get("/versao", headers={"Authorization": "Bearer " + TOKEN})
    assert r.status_code == 503


# ------------------------------------------------------------- módulo versao
def test_versao_regras_e_sha256_dos_quatro_modulos_e_da_politica_v3():
    h = hashlib.sha256()
    caminhos = [os.path.join(api.CAMINHO_SCRIPTS, "fopa", nome + ".py")
                for nome in ("verificador", "questionario", "distribuicao", "condicoes")]
    # as políticas da v3 (api/politica.py: veredito; api/injecao.py: tag e degradação) rodam depois
    # do verificador e decidem: são regra
    caminhos.append(os.path.join(api.AQUI, "politica.py"))
    caminhos.append(os.path.join(api.AQUI, "injecao.py"))
    for caminho in caminhos:
        with open(caminho, "rb") as f:
            h.update(f.read().replace(b"\r\n", b"\n"))
    assert versao.versao_regras() == h.hexdigest()


@pytest.mark.parametrize("arquivo", ["politica.py", "injecao.py"])
def test_versao_regras_muda_se_uma_politica_v3_mudar(monkeypatch, arquivo):
    antes = versao.versao_regras()
    original = versao._ler
    monkeypatch.setattr(versao, "_ler", lambda c: original(c) + (
        b"\n# politica nova\n" if os.path.basename(c) == arquivo else b""))
    assert versao.versao_regras() != antes


def test_versao_nao_depende_do_fim_de_linha(monkeypatch):
    # Achado do W01 (24/09): a imagem nasce do `git archive` com autocrlf e
    # leva o escopo.py em CRLF; a árvore do host tem LF. O conteúdo era o
    # mesmo e a escopo_versao saía diferente (95664043 x c9f8dffc) — o
    # /escopo/reavaliar do worker e as ferramentas do host discordavam.
    original = versao._ler
    lf = (versao.versao_regras(), versao.escopo_versao())
    monkeypatch.setattr(versao, "_ler",
                        lambda c: original(c).replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert (versao.versao_regras(), versao.escopo_versao()) == lf


def test_versao_regras_muda_se_um_modulo_mudar(monkeypatch):
    antes = versao.versao_regras()
    original = versao._ler

    def ler_alterado(caminho):
        conteudo = original(caminho)
        if os.path.basename(caminho) == "distribuicao.py":
            conteudo += b"\n# regra nova\n"
        return conteudo

    monkeypatch.setattr(versao, "_ler", ler_alterado)
    depois = versao.versao_regras()
    assert HEX64.match(depois)
    assert depois != antes


def test_versao_regras_nao_muda_se_so_o_escopo_mudar(monkeypatch):
    antes = versao.versao_regras()
    original = versao._ler
    monkeypatch.setattr(versao, "_ler", lambda c: original(c) + (
        b"\n#x\n" if os.path.basename(c) == "escopo.py" else b""))
    assert versao.versao_regras() == antes
    assert HEX64.match(versao.escopo_versao())


def test_versao_prompt_estavel_e_sensivel_ao_sistema(monkeypatch):
    a = versao.versao_prompt()
    assert a == versao.versao_prompt()
    assert HEX64.match(a)
    monkeypatch.setattr(questionario, "instrucao_sistema", lambda: "outro prompt")
    assert versao.versao_prompt() != a


def test_versao_prompt_sensivel_as_perguntas(monkeypatch):
    a = versao.versao_prompt()
    monkeypatch.setattr(questionario, "PERGUNTAS", questionario.PERGUNTAS[:-1])
    assert versao.versao_prompt() != a


def test_git_sha_prefere_env_e_cai_em_desconhecido(monkeypatch):
    monkeypatch.setenv("FOPA_GIT_SHA", "deadbeef")
    assert versao.git_sha() == "deadbeef"
    monkeypatch.delenv("FOPA_GIT_SHA")
    monkeypatch.setattr(versao, "_git_head", lambda: None)
    assert versao.git_sha() == "desconhecido"


def test_git_sha_do_host_e_o_head_do_repositorio(monkeypatch):
    # Minor da revisão final da F0: o teste antigo aceitava "desconhecido" OU qualquer sha, e passava com o
    # _git_head quebrado. Onde há git e repositório, o sha tem de ser o HEAD de verdade; onde não há (a
    # imagem, a cópia sem .git da camada a do CI), pula dizendo por quê.
    monkeypatch.delenv("FOPA_GIT_SHA", raising=False)
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=versao.RAIZ, capture_output=True, text=True, timeout=10)
    except OSError:
        pytest.skip("git ausente neste ambiente")
    if r.returncode != 0:
        pytest.skip("sem repositório git em %s (imagem ou cópia do CI)" % versao.RAIZ)
    assert versao.git_sha() == r.stdout.strip()


def test_git_head_sem_git_no_path_e_none(monkeypatch):
    # Sem o binário do git (o caso da imagem), _git_head não levanta: devolve None e o git_sha cai no env ou
    # em "desconhecido".
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("FOPA_GIT_SHA", raising=False)
    assert versao._git_head() is None
    assert versao.git_sha() == "desconhecido"


# ------------------------------------------------------------------- config
def test_config_le_env_com_defaults(monkeypatch):
    for k in ("FOPA_ENV", "STORAGE_BACKEND", "FOPA_JOBS_CONCORRENCIA", "USD_BRL",
              "FOPA_TESSERACT_ESPERADO", "DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    cfg = config.carregar()
    assert cfg.ambiente == "dev"
    assert cfg.storage_backend == "fs"
    assert cfg.jobs_concorrencia == 2
    assert cfg.tesseract_esperado == "5.4.0"
    assert cfg.usd_brl is None
    assert cfg.database_url is None


def test_config_rejeita_valores_fora_do_dominio(monkeypatch):
    monkeypatch.setenv("FOPA_ENV", "staging")
    with pytest.raises(config.ConfigInvalida):
        config.carregar()
    monkeypatch.setenv("FOPA_ENV", "prod")
    monkeypatch.setenv("STORAGE_BACKEND", "gcs")
    with pytest.raises(config.ConfigInvalida):
        config.carregar()
    monkeypatch.setenv("STORAGE_BACKEND", "fs")
    monkeypatch.setenv("FOPA_JOBS_CONCORRENCIA", "zero")
    with pytest.raises(config.ConfigInvalida):
        config.carregar()


def test_config_nunca_le_a_chave_da_anthropic(monkeypatch):
    import inspect
    fonte = inspect.getsource(config)
    assert "ANTHROPIC" not in fonte.replace("NUNCA lê ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    cfg = config.carregar()
    assert "sk-x" not in repr(cfg)


def test_importar_api_nao_carrega_o_env_do_projeto():
    """
    `fopa.modelos` chama `segredos.carregar()` no import, que leria o `.env` do
    repositório. O worker nunca pode herdar a chave por esse caminho (plano,
    seção 4). Roda num subprocesso limpo para o teste não depender do estado
    deste interpretador.
    """
    ambiente = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    codigo = ("import os, api, api.worker, fopa.modelos; "
              "print('ANTHROPIC_API_KEY' in os.environ)")
    saida = subprocess.run([sys.executable, "-c", codigo], cwd=api.RAIZ, env=ambiente,
                           capture_output=True, text=True, timeout=120)
    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.strip().splitlines()[-1] == "False"


# ---------------------------------------------------------------- site /api/saude
@pytest.fixture
def site(env):
    from api import site as mod
    mod.app.state.transporte_worker = None
    return mod


def test_saude_sem_worker_url_nem_banco(site, env):
    env.delenv("FOPA_WORKER_URL", raising=False)
    env.delenv("DATABASE_URL", raising=False)
    r = TestClient(site.app).get("/api/saude")
    assert r.status_code == 503      # plano §8: dependência fora = 503, com o detalhe no corpo
    corpo = r.json()
    assert corpo["api_ok"] is True
    assert corpo["worker"]["ok"] is False and "FOPA_WORKER_URL" in corpo["worker"]["erro"]
    assert corpo["postgres"]["ok"] is None and "DATABASE_URL" in corpo["postgres"]["erro"]


def test_saude_worker_fora_do_ar_e_falha_tratada(site, env):
    # Porta 9 (discard) sem nada escutando: conexão recusada, nunca exceção 500.
    env.setenv("FOPA_WORKER_URL", "http://127.0.0.1:9")
    env.delenv("DATABASE_URL", raising=False)
    r = TestClient(site.app).get("/api/saude")
    assert r.status_code == 503
    assert r.json()["worker"]["ok"] is False
    assert r.json()["worker"]["erro"]


def test_saude_worker_no_ar_repassa_o_health(site, env):
    env.setenv("FOPA_WORKER_URL", "http://worker.interno:8000")
    env.delenv("DATABASE_URL", raising=False)
    visto = {}

    def responder(req: httpx.Request):
        visto["url"] = str(req.url)
        return httpx.Response(200, json={"ok": True, "tesseract": "5.4.0"})

    site.app.state.transporte_worker = httpx.MockTransport(responder)
    r = TestClient(site.app).get("/api/saude")
    assert visto["url"] == "http://worker.interno:8000/health"
    assert r.json()["worker"] == {"ok": True, "status": 200,
                                   "health": {"ok": True, "tesseract": "5.4.0"}}


def test_saude_postgres_inacessivel_e_falha_tratada(site, env):
    env.delenv("FOPA_WORKER_URL", raising=False)
    env.setenv("DATABASE_URL", "postgresql://fopa:x@127.0.0.1:9/fopa?connect_timeout=2")
    r = TestClient(site.app).get("/api/saude")
    assert r.status_code == 503
    assert r.json()["postgres"]["ok"] is False
    assert r.json()["postgres"]["erro"]
    assert "fopa:x@" not in json.dumps(r.json())   # a URL com senha nunca sai na resposta
