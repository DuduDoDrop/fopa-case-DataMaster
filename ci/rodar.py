#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Executor único do CI da FOPA v3 — plano, seções 11.1 e 11.8. Windows e Linux.

    python ci/rodar.py                # camada (a) e, se houver acervo/stack, a (b)
    python ci/rodar.py --camada a     # só a (a) — é o que o GitHub Actions roda
    python ci/rodar.py --camada b     # só a (b)
    make ci                           # o mesmo que o primeiro

CAMADA (a) — sem acervo, sem stack, sem rede paga
  Roda numa CÓPIA do repositório montada como a imagem do worker a enxerga
  (.dockerignore): código, testes, `amostras/_fixture` e o catálogo de escopo
  versionado — sem `amostras/` real, `saidas/`, `Fopa-v2/`, `acervo/` e sem
  NENHUM `.env`. É por isso que a fumaça reporta aqui o número REAL de
  asserções sem acervo, e não os ~135 do host (checklist transversal: "não
  prometer 135 no CI da imagem"). Passos: guardas de texto (ci/tests),
  db/tests, migracao/tests, api/tests, docker/tests, web (vitest + build, como
  o stage `web` do worker.Dockerfile), `23_testa_escopo.py` e
  `api/tests/test_fumaca.py`. O Postgres de teste é efêmero (tests/pg_efemero.py,
  container com porta sorteada): nunca o 5433 da stack. O web roda com o npm
  do host se ele for Node 22 (o GitHub instala), senão em `node:22-alpine`.

CAMADA (b) — com acervo e stack, opcional, detectada
  `40_fumaca.py` sobre o acervo do host (~135), `23_testa_escopo.py` com os
  objetos reais das auditorias, `n8n/tests` se o fopa-n8n
  responder em 127.0.0.1:5679, `db/invariantes.sql` no Postgres da stack
  (127.0.0.1:5433, papel só-leitura api_ro) e as guardas da stack
  (`docker inspect` sem chave de modelo no Env).

REGRAS
  - Sai 0 só se tudo que RODOU passou. O que foi pulado não conta como passou:
    sai listado com o motivo, e um passo cujos testes foram todos pulados é
    "pulado", nunca "passou".
  - ANTHROPIC_*, OPENAI_* e JEV_API_KEY saem do ambiente de todo processo
    filho (11.8: "a suíte inteira roda com a chave ausente"); scripts do pacote
    rodam por `ci/sem_chave.py`, que impede o `.env` da raiz de devolver a
    chave e reprova se ela aparecer; o pytest carrega o mesmo módulo como
    plugin. Nenhum segredo é impresso.
  - Nenhum comando git além de `git ls-files` (as guardas listam o que é
    versionado com ele).
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from ci import sem_chave  # noqa: E402

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# ------------------------------------------------------------------ o que a camada (a) copia
# Espelha o .dockerignore (o que a imagem leva) mais o código de teste. Nunca
# `.env` de pasta nenhuma, nunca `n8n/.segredos`.
COPIAR_PASTAS = ("scripts", "api", "db", "migracao", "tests", "docker", "n8n", "ci", "web", "amostras/_fixture")
# `saidas/_catalogo_escopo.json` é versionado (exceção do .gitignore): são os 23
# casos julgados a mão que o `/escopo` tem de acertar (11.1 a). `tessdata/` não
# é acervo: é o `por.traineddata` que o setup do host baixa (gitignorado).
COPIAR_ARQUIVOS = ("saidas/_catalogo_escopo.json", ".dockerignore", ".gitignore", "requirements.txt")
COPIAR_SE_EXISTIR = ("tessdata",)
NUNCA = {"__pycache__", ".pytest_cache", "node_modules", ".segredos", "build.log"}

# Testes de api/tests que precisam da stack viva (5433/5679/8080). Hoje nenhum:
# todos sobem o próprio Postgres efêmero. Quem precisar entra aqui, com o motivo.
PRECISAM_DA_STACK: dict[str, str] = {}

# Testes que precisam de Tesseract 5.4.0 + `por` (ADR-008). Num host sem ele
# (o runner do GitHub) são desmarcados e listados como PULADOS com o motivo; o
# portão de OCR é o build da imagem do worker, que compila a 5.4.0.
PRECISAM_DE_OCR = (
    "api/tests/test_jobs.py::test_paginas_le_digital_e_digitalizado_e_congela",
    # /jobs/paginas confere o OCR ANTES de ler (api/leitura.py: "falha alto"),
    # mesmo quando a licitação não tem PDF nenhum.
    "api/tests/test_jobs.py::test_paginas_sem_pdf_nao_cria_leitura",
    # OCR forçado por arquivo e rotação (2376d3a, db/043): leem a página pela imagem.
    # Entraram sem esta lista e deixaram o CI do GitHub vermelho de 26/09 a 28/09.
    "api/tests/test_jobs.py::test_paginas_com_ocr_forcado_gera_leitura_nova_e_a_marcacao_fica",
    "api/tests/test_jobs.py::test_paginas_conta_so_o_texto_escondido_com_cara_de_instrucao",
    "api/tests/test_leitura_forcada.py::test_camada_de_texto_cortada_e_lida_pela_imagem",
    "api/tests/test_leitura_forcada.py::test_pagina_de_cabeca_para_baixo_se_le_girando_180",
)

TIMEOUT_PASSO = 30 * 60


# ------------------------------------------------------------------ registro
@dataclass
class Passo:
    camada: str
    nome: str
    status: str = "pulado"          # passou | falhou | pulado
    segundos: float = 0.0
    resumo: str = ""
    motivo: str = ""
    pulados: list[str] = field(default_factory=list)    # dentro do passo (pytest skip / desmarcados)
    saida: str = ""                                      # tudo que o passo imprimiu (fica no log)


PASSOS: list[Passo] = []
TEMPO_CAMADA: dict[str, float] = {}


def titulo(texto: str) -> None:
    print("\n" + "=" * 78 + "\n  " + texto + "\n" + "=" * 78, flush=True)


def ambiente(extra: dict | None = None) -> dict:
    env = dict(os.environ)
    sem_chave.limpar(env)
    env.update(PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    env.update(extra or {})
    return env


def executar(cmd: list[str], cwd: Path, env: dict, log: Path, mostrar: bool = True) -> tuple[int, str]:
    """Roda, ecoa ao vivo (se `mostrar`), grava o log inteiro e devolve (código, saída)."""
    linhas = []
    with open(log, "w", encoding="utf-8") as f:
        f.write("$ %s\n(cwd %s)\n\n" % (" ".join(cmd), cwd))
        try:
            p = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        except OSError as e:
            f.write("não executou: %s\n" % e)
            return 127, "não executou: %s" % e
        inicio = time.time()
        assert p.stdout is not None
        for linha in p.stdout:
            linhas.append(linha)
            f.write(linha)
            if mostrar:
                print("  │ " + linha.rstrip("\n"), flush=True)
            if time.time() - inicio > TIMEOUT_PASSO:
                p.kill()
                linhas.append("\n[rodar] TIMEOUT de %d s\n" % TIMEOUT_PASSO)
                break
        codigo = p.wait()
    return codigo, "".join(linhas)


# ------------------------------------------------------------------ pytest
def _junit(caminho: Path) -> dict:
    r = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "pulados": []}
    if not caminho.exists():
        return r
    raiz = ET.parse(caminho).getroot()
    suites = [raiz] if raiz.tag == "testsuite" else raiz.findall("testsuite")
    for s in suites:
        for k in ("tests", "failures", "errors", "skipped"):
            r[k] += int(s.get(k, 0))
        for tc in s.iter("testcase"):
            sk = tc.find("skipped")
            if sk is not None:
                msg = (sk.get("message") or "").replace("\n", " ").strip()
                if msg.startswith("Skipped: "):
                    msg = msg[len("Skipped: "):]
                r["pulados"].append("%s::%s — %s" % (tc.get("classname", "").replace(".", "/"),
                                                     tc.get("name", ""), msg[:200]))
    return r


def _slug(nome: str) -> str:
    import unicodedata
    ascii_ = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:60]


def passo_pytest(camada: str, nome: str, alvos: list[str], cwd: Path, logs: Path,
                 extra: list[str] | None = None, desmarcar: dict[str, str] | None = None,
                 env_extra: dict | None = None) -> Passo:
    titulo("[%s] %s" % (camada, nome))
    p = Passo(camada, nome)
    slug = _slug(nome)
    junit = logs / ("%s-%s.xml" % (camada, slug))
    cmd = [sys.executable, "-m", "pytest", *alvos, "-q", "-rfEs", "--tb=short",
           "-p", "no:cacheprovider", "-p", "ci.sem_chave",
           "--junitxml", str(junit), "-o", "junit_family=xunit2", *(extra or [])]
    for nodeid, motivo in (desmarcar or {}).items():
        cmd += ["--deselect", nodeid]
        p.pulados.append("%s — desmarcado: %s" % (nodeid, motivo))
    t0 = time.time()
    codigo, saida = executar(cmd, cwd, ambiente(env_extra), logs / ("%s-%s.log" % (camada, slug)))
    p.segundos, p.saida = time.time() - t0, saida
    j = _junit(junit)
    p.pulados += j["pulados"]
    rodaram = j["tests"] - j["skipped"]
    ruins = j["failures"] + j["errors"]
    p.resumo = "%d passaram, %d falharam, %d pulados" % (rodaram - ruins, ruins, j["skipped"])
    if desmarcar:
        p.resumo += ", %d desmarcados" % len(desmarcar)
    if codigo not in (0, 5) or ruins:
        p.status = "falhou"
        p.motivo = "pytest saiu %d" % codigo if not ruins else ""
        if codigo == 3 and "[sem_chave] REPROVADO" in saida:
            p.motivo = "chave de API paga apareceu no ambiente"
    elif rodaram == 0:
        p.status = "pulado"
        p.motivo = "nenhum teste rodou (%s)" % ("nada coletado" if j["tests"] == 0 else "todos pulados")
    else:
        p.status = "passou"
    PASSOS.append(p)
    return p


def passo_script(camada: str, nome: str, script: Path, cwd: Path, logs: Path,
                 interpretar) -> Passo:
    """Um script do pacote pelo `ci/sem_chave.py`. `interpretar(saida)` -> (ok, resumo)."""
    titulo("[%s] %s" % (camada, nome))
    p = Passo(camada, nome)
    slug = _slug(nome)
    sem = cwd.parent / "ci" / "sem_chave.py" if (cwd.parent / "ci").is_dir() else RAIZ / "ci" / "sem_chave.py"
    t0 = time.time()
    codigo, saida = executar([sys.executable, str(sem), str(script)], cwd, ambiente(),
                             logs / ("%s-%s.log" % (camada, slug)), mostrar=False)
    p.segundos, p.saida = time.time() - t0, saida
    # Os scripts falam muito; o log inteiro fica em disco. Aqui: falhas e o fecho.
    for linha in saida.splitlines():
        if re.search(r"\bFALHA\b|\bERRO\b|Traceback|explodiu", linha):
            print("  │ " + linha)
    for linha in saida.splitlines()[-12:]:
        print("  │ " + linha)
    ok, p.resumo = interpretar(saida)
    if codigo == 3 and "[sem_chave] REPROVADO" in saida:
        p.status, p.motivo = "falhou", "chave de API paga apareceu no ambiente"
    elif codigo != 0 or not ok:
        p.status, p.motivo = "falhou", "saiu %d" % codigo
    else:
        p.status = "passou"
    PASSOS.append(p)
    return p


def pular(camada: str, nome: str, motivo: str) -> Passo:
    titulo("[%s] %s" % (camada, nome))
    print("  PULADO: " + motivo, flush=True)
    p = Passo(camada, nome, status="pulado", motivo=motivo)
    PASSOS.append(p)
    return p


# ------------------------------------------------------------------ interpretação dos scripts
def _interpretar_23(saida: str) -> tuple[bool, str]:
    m = re.search(r"todos os (\d+) casos passaram", saida)
    if m:
        return True, "%s casos passaram" % m.group(1)
    m = re.search(r"(\d+) FALHA\(S\)", saida)
    return False, ("%s falha(s)" % m.group(1)) if m else "o script não imprimiu o resultado"


def _interpretar_40(saida: str) -> tuple[bool, str]:
    ok = re.search(r"asserções ok \.+ (\d+)", saida)
    falhas = re.search(r"falhas \.+ (\d+)", saida)
    if not (ok and falhas):
        return False, "a fumaça não imprimiu o resultado"
    n_ok, n_f = int(ok.group(1)), int(falhas.group(1))
    lista = re.findall(r"^\s+· (.+)$", saida, re.M)
    resumo = "%d asserções ok, %d falhas" % (n_ok, n_f)
    if lista:
        resumo += " (" + "; ".join(lista[:3]) + ")"
    return n_f == 0, resumo


# ------------------------------------------------------------------ camada (a)
def _ignorar(pasta: str, nomes: list[str]) -> set[str]:
    fora = set()
    for n in nomes:
        if n in NUNCA or n.endswith((".pyc", ".pyo")):
            fora.add(n)
        elif (n == ".env" or n.startswith(".env.")) and n != ".env.exemplo":
            fora.add(n)                         # nunca copiar segredo, de pasta nenhuma
        elif n == "rascunho" and os.path.basename(pasta) == "n8n":
            fora.add(n)                         # rascunhos de fluxo: gitignorados
        elif n == "dist" and os.path.basename(pasta) == "web":
            fora.add(n)                         # build do site: o passo web refaz
    return fora


def montar_copia_sem_acervo() -> Path:
    destino = Path(tempfile.mkdtemp(prefix="fopa-ci-a-"))
    for rel in COPIAR_PASTAS:
        origem = RAIZ / rel
        if origem.is_dir():
            shutil.copytree(origem, destino / rel, ignore=_ignorar)
    for rel in COPIAR_ARQUIVOS:
        origem = RAIZ / rel
        if origem.is_file():
            (destino / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, destino / rel)
    for rel in COPIAR_SE_EXISTIR:
        origem = RAIZ / rel
        if origem.is_dir():
            shutil.copytree(origem, destino / rel, ignore=_ignorar)
    # Nenhum segredo atravessou: conferido, não suposto.
    vazados = [str(p.relative_to(destino)) for p in destino.rglob(".env*") if p.name != ".env.exemplo"]
    assert not vazados, "a cópia da camada (a) levou .env: %s" % vazados
    return destino


def ocr_disponivel(raiz: Path) -> tuple[bool, str]:
    codigo = ("import sys; sys.path.insert(0, 'scripts'); from fopa import ocr; "
              "a = ocr.checar_ambiente(); print('OCR=' + a['tesseract'] + '|' + ','.join(a['idiomas']))")
    try:
        r = subprocess.run([sys.executable, "-c", codigo], cwd=str(raiz), env=ambiente(),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    m = re.search(r"OCR=([^|\s]+)\|(\S*)", r.stdout)
    if not m:
        erro = (r.stderr.strip().splitlines() or ["sem saída"])[-1]
        return False, erro[:200]
    versao, idiomas = m.group(1), m.group(2).split(",")
    if not versao.startswith("5.4.0") or "por" not in idiomas:
        return False, "Tesseract %s com %s (exigido 5.4.0 + por)" % (versao, idiomas)
    return True, "Tesseract %s + por" % versao


def _node_22() -> str | None:
    """Caminho do npm se o host tem Node 22 (a versão da imagem); senão None."""
    npm, node = shutil.which("npm"), shutil.which("node")
    if not (npm and node):
        return None
    try:
        v = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return npm if v.startswith("v22.") else None


def _interpretar_vitest(saida: str) -> tuple[bool, str]:
    limpa = re.sub(r"\x1b\[[0-9;]*m", "", saida)
    arquivos = re.search(r"Test Files\s+(.+?)\s*$", limpa, re.M)
    testes = re.search(r"^\s*Tests\s+(.+?)\s*$", limpa, re.M)
    if not testes:
        return False, "o vitest não imprimiu o resultado"
    resumo = "vitest: testes %s" % testes.group(1)
    if arquivos:
        resumo += ", arquivos %s" % arquivos.group(1)
    return "failed" not in testes.group(1), resumo


def passo_web(camada: str, copia: Path, logs: Path) -> Passo:
    """`npm ci && npm test && npm run build` — o mesmo portão do stage `web` do worker.Dockerfile."""
    nome = "web (npm ci, vitest, build)"
    web = copia / "web"
    if not (web / "package.json").is_file() or not (web / "package-lock.json").is_file():
        return pular(camada, nome, "web/package.json ou package-lock.json ausente")
    npm = _node_22()
    cmds = "npm ci --no-audit --no-fund && npm test && npm run build"
    if npm:
        onde = "npm do host (Node 22)"
        seq = [[npm, "ci", "--no-audit", "--no-fund"], [npm, "test"], [npm, "run", "build"]]
    elif shutil.which("docker"):
        onde = "container node:22-alpine"
        # node_modules e dist em volumes anônimos (somem com --rm), como o README do web.
        seq = [["docker", "run", "--rm", "-e", "CI=1", "-e", "NO_COLOR=1",
                "--mount", "type=bind,source=%s,target=/web" % web,
                "--mount", "type=volume,target=/web/node_modules",
                "--mount", "type=volume,target=/web/dist",
                "-w", "/web", "node:22-alpine", "sh", "-c", cmds]]
    else:
        return pular(camada, nome, "sem Node 22 nem docker neste host")
    titulo("[%s] %s — %s" % (camada, nome, onde))
    p = Passo(camada, nome)
    t0 = time.time()
    saida, codigo = "", 0
    env = ambiente({"CI": "1", "NO_COLOR": "1"})
    for i, cmd in enumerate(seq):
        codigo, s = executar(cmd, web, env, logs / ("%s-web-%d.log" % (camada, i)), mostrar=False)
        saida += s
        if codigo != 0:
            break
    p.segundos, p.saida = time.time() - t0, saida
    limpa = re.sub(r"\x1b\[[0-9;]*m", "", saida)
    for linha in limpa.splitlines():
        if re.search(r"\bFAIL\b|✗|×|error TS\d+|npm ERR!|npm error", linha):
            print("  │ " + linha)
    for linha in [l for l in limpa.splitlines() if re.search(r"Test Files|^\s*Tests\s|built in|✓ built", l)]:
        print("  │ " + linha.strip())
    ok, p.resumo = _interpretar_vitest(saida)
    if codigo != 0 or not ok:
        p.status, p.motivo = "falhou", "saiu %d (%s)" % (codigo, onde)
    else:
        p.status = "passou"
        p.resumo += " · build ok · %s" % onde
    PASSOS.append(p)
    return p


def camada_a(logs: Path, manter: bool) -> None:
    t0 = time.time()
    titulo("CAMADA (a) — sem acervo, sem stack, sem rede paga")
    copia = montar_copia_sem_acervo()
    print("  cópia sem acervo: %s" % copia)
    print("  (espelha o .dockerignore: sem amostras/ real, saidas/, Fopa-v2/, acervo/ e sem .env)")
    tem_ocr, ocr_msg = ocr_disponivel(copia)
    if not tem_ocr and (copia / "tessdata").is_dir():
        # tessdata sem o binário é um ambiente que não existe em lugar nenhum
        # (nem no runner, nem na imagem): a cópia fica coerente com "sem OCR".
        shutil.rmtree(copia / "tessdata")
        ocr_msg += "; tessdata do host retirado da cópia"
    print("  OCR: %s" % ("disponível — " + ocr_msg if tem_ocr else "INDISPONÍVEL — " + ocr_msg))
    try:
        # Guardas de texto: rodam na árvore real (precisam do `git ls-files`), não na cópia.
        g = passo_pytest("a", "guardas de texto (ci/tests)", ["ci/tests/test_guardas_texto.py"], RAIZ, logs)
        m = re.search(r"(?:não havia W23 para olhar|W23 olhado)[^\n]*", g.saida)
        if m:
            g.resumo += " · " + m.group(0).strip()
        passo_pytest("a", "db/tests", ["db/tests"], copia, logs)
        passo_pytest("a", "migracao/tests", ["migracao/tests"], copia, logs)
        desmarcar = dict(PRECISAM_DA_STACK)
        if not tem_ocr:
            desmarcar.update({n: "precisa de Tesseract 5.4.0 + por (%s); o portão de OCR é o build "
                                 "da imagem do worker" % ocr_msg for n in PRECISAM_DE_OCR})
        passo_pytest("a", "api/tests (sem a fumaça)", ["api/tests"], copia, logs,
                     extra=["--ignore", "api/tests/test_fumaca.py"], desmarcar=desmarcar)
        passo_pytest("a", "docker/tests", ["docker/tests"], copia, logs)
        passo_web("a", copia, logs)
        passo_script("a", "scripts/23_testa_escopo.py", copia / "scripts" / "23_testa_escopo.py",
                     copia / "scripts", logs, _interpretar_23)
        p = passo_pytest("a", "api/tests/test_fumaca.py (número real, sem acervo)",
                         ["api/tests/test_fumaca.py"], copia, logs, extra=["-s"])
        m = re.search(r"40_fumaca: (\d+) asserções ok, (\d+) falhas", p.saida)
        if m:
            p.resumo += " · 40_fumaca sem acervo: %s asserções ok, %s falhas" % (m.group(1), m.group(2))
        elif p.status == "passou":
            p.status, p.motivo = "falhou", "test_fumaca.py não imprimiu o número de asserções"
    finally:
        if manter:
            print("\n  cópia mantida em %s" % copia)
        else:
            shutil.rmtree(copia, ignore_errors=True)
    TEMPO_CAMADA["a"] = time.time() - t0


# ------------------------------------------------------------------ camada (b)
def _acervo_presente() -> tuple[bool, str]:
    amostras, saidas = RAIZ / "amostras", RAIZ / "saidas"
    invs = [p for p in amostras.glob("*/_inventario.json") if not p.parent.name.startswith("_")] \
        if amostras.is_dir() else []
    auds = list(saidas.glob("*/auditoria.json")) if saidas.is_dir() else []
    if not invs or not auds:
        return False, "acervo v2 ausente (%d inventários em amostras/, %d auditorias em saidas/)" % (
            len(invs), len(auds))
    return True, "%d inventários, %d auditorias" % (len(invs), len(auds))


def _responde(url: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status == 200, "HTTP %d" % r.status
    except Exception as e:                                             # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, str(e)[:120])


def _ler_env_docker() -> dict:
    """docker/.env por nome, sem despejar no ambiente (mesma regra do n8n/cliente.py)."""
    caminho = RAIZ / "docker" / ".env"
    d = {}
    if caminho.is_file():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                d[k.strip()] = v
    return d


def invariantes_na_stack(logs: Path) -> Passo:
    nome = "db/invariantes.sql no Postgres da stack (127.0.0.1:5433, api_ro)"
    try:
        import psycopg
    except ImportError:
        return pular("b", nome, "psycopg não instalado")
    senha = _ler_env_docker().get("API_RO_PASSWORD")
    if not senha:
        return pular("b", nome, "docker/.env ausente ou sem API_RO_PASSWORD")
    titulo("[b] " + nome)
    p = Passo("b", nome)
    t0 = time.time()
    try:
        with psycopg.connect(host="127.0.0.1", port=5433, dbname="fopa", user="api_ro",
                             password=senha, connect_timeout=5) as c:
            c.execute("SET default_transaction_read_only = on")
            ctx = c.execute(
                "SELECT (SELECT count(*) FROM licitacoes),"
                "       (SELECT count(*) FROM licitacoes WHERE estado = 'publicada'),"
                "       (SELECT count(*) FROM verificacoes WHERE vigente),"
                "       (SELECT count(*) FROM verificacao_respostas),"
                "       (SELECT count(*) FROM execucoes_modelo),"
                "       (SELECT count(*) FROM arquivos WHERE status = 'ok')").fetchone()
            linhas = c.execute((RAIZ / "db" / "invariantes.sql").read_text(encoding="utf-8")).fetchall()
    except psycopg.OperationalError as e:
        PASSOS.append(p)
        p.status, p.motivo = "pulado", "Postgres da stack não respondeu (%s)" % str(e).splitlines()[0][:120]
        print("  PULADO: " + p.motivo)
        return p
    p.segundos = time.time() - t0
    lic, pub, vig, vr, ex, arq = ctx
    contexto = ("%d licitações, %d publicadas, %d verificações vigentes, %d vereditos, "
                "%d execuções, %d arquivos ok" % ctx)
    print("  olhou: " + contexto)
    with open(logs / "b-invariantes-stack.log", "w", encoding="utf-8") as f:
        f.write(contexto + "\n")
        for l in linhas:
            f.write("%s | %s | %s\n" % tuple(l))
    if lic == 0:
        p.status, p.motivo = "pulado", "banco da stack vazio: zero linhas não provaria nada"
    elif linhas:
        p.status = "falhou"
        por_tipo: dict[str, int] = {}
        for inv, ref, det in linhas:
            por_tipo[inv] = por_tipo.get(inv, 0) + 1
        p.resumo = "%d violação(ões): %s" % (len(linhas), ", ".join("%s=%d" % kv for kv in sorted(por_tipo.items())))
        for l in linhas[:30]:
            print("  VIOLAÇÃO %s | %s | %s" % tuple(l))
        if len(linhas) > 30:
            print("  ... e mais %d (log: b-invariantes-stack.log)" % (len(linhas) - 30))
    else:
        p.status = "passou"
        p.resumo = "zero linhas sobre " + contexto
    print("  " + (p.resumo or p.motivo))
    PASSOS.append(p)
    return p


def camada_b(logs: Path) -> None:
    t0 = time.time()
    titulo("CAMADA (b) — com acervo e stack (opcional, detectada)")
    tem_acervo, msg_acervo = _acervo_presente()
    print("  acervo: %s" % msg_acervo)
    n8n_ok, msg_n8n = _responde("http://127.0.0.1:5679/healthz")
    print("  fopa-n8n (127.0.0.1:5679): %s" % msg_n8n)

    if tem_acervo:
        passo_script("b", "scripts/40_fumaca.py (com acervo)", RAIZ / "scripts" / "40_fumaca.py",
                     RAIZ / "scripts", logs, _interpretar_40)
        # Com acervo, os objetos reais das auditorias entram na suíte de escopo.
        passo_script("b", "scripts/23_testa_escopo.py (com acervo)", RAIZ / "scripts" / "23_testa_escopo.py",
                     RAIZ / "scripts", logs, _interpretar_23)
    else:
        pular("b", "scripts/40_fumaca.py (com acervo)", msg_acervo)
        pular("b", "scripts/23_testa_escopo.py (com acervo)", msg_acervo)

    if n8n_ok:
        passo_pytest("b", "n8n/tests (instância fopa-n8n)", ["n8n/tests"], RAIZ, logs)
    else:
        pular("b", "n8n/tests (instância fopa-n8n)", "fopa-n8n não respondeu em 127.0.0.1:5679 (%s)" % msg_n8n)

    invariantes_na_stack(logs)
    passo_pytest("b", "guardas da stack (docker inspect)", ["ci/tests/test_guardas_stack.py"], RAIZ, logs)
    TEMPO_CAMADA["b"] = time.time() - t0


# ------------------------------------------------------------------ resumo
def resumo(logs: Path) -> int:
    titulo("RESUMO")
    larg = max(len(p.nome) for p in PASSOS) if PASSOS else 10
    for p in PASSOS:
        print("  (%s) %-*s  %-6s %7.1f s  %s" % (p.camada, larg, p.nome, p.status.upper(), p.segundos,
                                               p.resumo or p.motivo))
    pulados = [p for p in PASSOS if p.status == "pulado"]
    internos = [(p, x) for p in PASSOS for x in p.pulados]
    print("\n  PULADO (não rodou — não conta como passou):")
    if not pulados and not internos:
        print("    nada")
    for p in pulados:
        print("    - passo (%s) %s: %s" % (p.camada, p.nome, p.motivo))
    for p, x in internos:
        print("    - teste em (%s) %s: %s" % (p.camada, p.nome, x))
    falhos = [p for p in PASSOS if p.status == "falhou"]
    print("\n  TEMPO POR CAMADA:")
    for c in sorted(TEMPO_CAMADA):
        print("    camada (%s): %.1f s" % (c, TEMPO_CAMADA[c]))
    print("\n  logs completos: %s" % logs)
    if falhos:
        print("\n  REPROVADO: %d passo(s) falharam: %s" % (len(falhos), ", ".join(
            "(%s) %s" % (p.camada, p.nome) for p in falhos)))
        return 1
    rodaram = [p for p in PASSOS if p.status == "passou"]
    if not rodaram:
        print("\n  REPROVADO: nenhum passo rodou")
        return 1
    print("\n  APROVADO: %d passo(s) passaram; não rodaram %d passo(s) e %d teste(s) (listados acima)"
          % (len(rodaram), len(pulados), len(internos)))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--camada", choices=("a", "b", "ab"), default="ab")
    ap.add_argument("--manter-copia", action="store_true", help="não apaga a cópia sem acervo da camada (a)")
    args = ap.parse_args(argv)

    removidas = sem_chave.limpar(os.environ)
    logs = Path(tempfile.mkdtemp(prefix="fopa-ci-logs-"))
    titulo("FOPA v3 — CI (plano 11.1 / 11.8)")
    print("  python %s · %s · raiz %s" % (platform.python_version(), platform.platform(), RAIZ))
    print("  camadas: %s" % ", ".join("(%s)" % c for c in args.camada))
    print("  chaves de API paga removidas do ambiente: %s" % (", ".join(removidas) or "nenhuma estava definida"))
    print("  logs: %s" % logs)

    if "a" in args.camada:
        camada_a(logs, args.manter_copia)
    if "b" in args.camada:
        camada_b(logs)
    return resumo(logs)


if __name__ == "__main__":
    raise SystemExit(main())
