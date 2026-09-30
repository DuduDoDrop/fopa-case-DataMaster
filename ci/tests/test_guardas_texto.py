# -*- coding: utf-8 -*-
"""
Guardas de texto do CI — camada (a): sem acervo, sem stack, sem rede.

Plano 11.8 ("API só em produção") e checklist F3 ("nenhuma chave de modelo em
lugar nenhum"):

  1. `api.anthropic.com` só aparece nos fluxos do n8n dentro do ramo `claude`
     do Switch do W23 — em nenhum outro nó, de nenhum outro fluxo; e nunca no
     código do worker/site (`api/`, `web/src/`). Notas adesivas (stickyNote)
     são documentação, não chamada: ficam de fora e são contadas.
  2. Nenhum arquivo versionado — nem os não versionados que o .gitignore
     deixaria entrar no próximo commit — tem cara de segredo (sk-..., JWT
     eyJ..., n8n_api_..., chave privada, segredo OAuth do Google...), nem o
     VALOR de um segredo dos `.env` locais e de `n8n/.segredos/`.

A lista do que é versionado vem de `git ls-files` (único comando git aqui).
Nenhum segredo é impresso: a mensagem diz arquivo, linha e o nome do padrão ou
da variável, com no máximo 6 caracteres do achado.

Cada guarda tem um teste que prova que ela sabe falhar.
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOWS = RAIZ / "n8n" / "workflows"
HOST = "api.anthropic.com"
NOTA = "n8n-nodes-base.stickyNote"
SWITCH = "n8n-nodes-base.switch"


# ================================================================== 1. api.anthropic.com
def _alcancaveis(conexoes: dict, inicio, barreira: str = "") -> set[str]:
    """Nós alcançáveis a partir de `inicio` sem atravessar `barreira` (o próprio Switch):
    um laço de retentativa que volta ao Switch passa de novo pela decisão dele."""
    vistos: set[str] = set()
    pilha = list(inicio)
    while pilha:
        n = pilha.pop()
        if n in vistos or n == barreira:
            continue
        vistos.add(n)
        for saidas in (conexoes.get(n) or {}).values():
            for lista in saidas or []:
                for alvo in lista or []:
                    pilha.append(alvo["node"])
    return vistos


def _saidas_claude(no: dict) -> set[int]:
    """Índices de saída do Switch cujo ramo é o provedor `claude`."""
    regras = (no.get("parameters") or {}).get("rules") or {}
    lista = regras.get("values") or regras.get("rules") or []          # Switch v3 / v1-v2
    idx = set()
    for i, r in enumerate(lista):
        chave = str(r.get("outputKey") or "").strip().lower()
        saida = int(r["output"]) if str(r.get("output", "")).isdigit() else i
        # sem outputKey: a regra compara com 'claude' (rightValue ou dentro da expressão)
        if chave == "claude" or (not chave and re.search(r"[\"']claude\\?[\"']", json.dumps(r).lower())):
            idx.add(saida)
    return idx


def _ramo_claude(wf: dict) -> set[str]:
    """Nós alcançáveis SÓ pela saída `claude` de um Switch (não por outra saída dele)."""
    conexoes = wf.get("connections") or {}
    ramo: set[str] = set()
    for no in wf.get("nodes") or []:
        if no.get("type") != SWITCH:
            continue
        claude = _saidas_claude(no)
        if not claude:
            continue
        saidas = (conexoes.get(no["name"]) or {}).get("main") or []
        de_claude, de_outras = [], []
        for i, lista in enumerate(saidas):
            (de_claude if i in claude else de_outras).extend(a["node"] for a in lista or [])
        ramo |= (_alcancaveis(conexoes, de_claude, no["name"])
                 - _alcancaveis(conexoes, de_outras, no["name"]))
    return ramo


def _eh_w23(wf: dict, nome_arquivo: str) -> bool:
    return nome_arquivo.upper().startswith("W23") or str(wf.get("name") or "").strip().upper().startswith("W23")


def analisar_fluxo(wf: dict, nome_arquivo: str) -> dict:
    """{'violacoes': [...], 'permitidos': [...], 'notas': n} para um fluxo exportado."""
    r = {"violacoes": [], "permitidos": [], "notas": 0}
    fora_de_no = {k: v for k, v in wf.items() if k != "nodes"}
    if HOST in json.dumps(fora_de_no, ensure_ascii=False).lower():
        r["violacoes"].append("%s: %s fora de qualquer nó (pinData/settings/...)" % (nome_arquivo, HOST))
    ramo = _ramo_claude(wf) if _eh_w23(wf, nome_arquivo) else set()
    for no in wf.get("nodes") or []:
        if HOST not in json.dumps(no, ensure_ascii=False).lower():
            continue
        if no.get("type") == NOTA:
            r["notas"] += 1
        elif no.get("name") in ramo:
            r["permitidos"].append("%s: nó %r (ramo claude)" % (nome_arquivo, no.get("name")))
        else:
            r["violacoes"].append("%s: nó %r (%s) fala com %s fora do ramo `claude` do Switch do W23"
                                  % (nome_arquivo, no.get("name"), no.get("type"), HOST))
    return r


def _fluxos() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.json")) if WORKFLOWS.is_dir() else []


def test_api_anthropic_so_no_ramo_claude_do_switch_do_w23():
    fluxos = _fluxos()
    assert fluxos, "n8n/workflows/ sem nenhum fluxo exportado: nada para olhar"
    violacoes, permitidos, notas, w23 = [], [], 0, []
    for f in fluxos:
        wf = json.loads(f.read_text(encoding="utf-8"))
        if _eh_w23(wf, f.name):
            w23.append(f.name)
        r = analisar_fluxo(wf, f.name)
        violacoes += r["violacoes"]
        permitidos += r["permitidos"]
        notas += r["notas"]
    assert not violacoes, "\n".join(violacoes)
    if not w23:
        warnings.warn("não havia W23 para olhar em n8n/workflows/ (fluxos: %s); os demais não citam %s"
                      % (", ".join(f.stem for f in fluxos), HOST), UserWarning)
    elif not permitidos:
        warnings.warn("W23 olhado (%s): não cita %s em nó nenhum" % (", ".join(w23), HOST), UserWarning)
    else:
        warnings.warn("W23 olhado: %s só em %s" % (HOST, "; ".join(permitidos)), UserWarning)
    if notas:
        warnings.warn("%d nota(s) adesiva(s) citam %s (documentação, ignoradas)" % (notas, HOST), UserWarning)


def test_worker_e_site_nunca_falam_com_a_anthropic():
    # Checklist F3: o worker monta o corpo (/prompt) mas quem chama é o n8n.
    fontes = [p for p in (RAIZ / "api").rglob("*.py") if "tests" not in p.relative_to(RAIZ).parts]
    web = RAIZ / "web" / "src"
    if web.is_dir():
        fontes += [p for p in web.rglob("*") if p.suffix in (".ts", ".tsx", ".js", ".jsx")]
    assert fontes
    achados = [str(p.relative_to(RAIZ)) for p in fontes
               if HOST in p.read_text(encoding="utf-8", errors="replace").lower()]
    assert not achados, "%s citado em código do worker/site: %s" % (HOST, achados)


# -- o guarda sabe falhar ------------------------------------------------------
URL = "https://" + HOST + "/v1/messages"


def _no(nome, tipo="n8n-nodes-base.httpRequest", **params):
    return {"name": nome, "type": tipo, "parameters": params}


def _liga(*pares):
    """_liga(("A", 0, "B"), ...) -> connections do n8n (saída i de A vai para B)."""
    c: dict = {}
    for de, i, para in pares:
        saidas = c.setdefault(de, {}).setdefault("main", [])
        while len(saidas) <= i:
            saidas.append([])
        saidas[i].append({"node": para, "type": "main", "index": 0})
    return c


def _switch(*chaves):
    return _no("Provedor", SWITCH, rules={"values": [
        {"conditions": {"conditions": [{"rightValue": k}]}, "renameOutput": True, "outputKey": k}
        for k in chaves]})


def _w23(ligacoes):
    return {"name": "W23 Extrair", "nodes": [
        _no("Gatilho", "n8n-nodes-base.executeWorkflowTrigger"), _switch("claude", "simulado", "openai"),
        _no("Chamar Claude", url=URL), _no("Responder simulado", url="http://fopa-worker:8000/responder-simulado"),
        _no("Gravar chamada", "n8n-nodes-base.postgres"),
        _no("Sobre o W23", NOTA, content="só o ramo claude chama " + URL)],
        "connections": _liga(("Gatilho", 0, "Provedor"), *ligacoes)}


def test_guarda_anthropic_aceita_o_ramo_claude_e_ignora_a_nota():
    wf = _w23([("Provedor", 0, "Chamar Claude"), ("Provedor", 1, "Responder simulado"),
               ("Chamar Claude", 0, "Gravar chamada"), ("Responder simulado", 0, "Gravar chamada")])
    r = analisar_fluxo(wf, "W23.json")
    assert r["violacoes"] == [] and len(r["permitidos"]) == 1 and r["notas"] == 1


def test_guarda_anthropic_aceita_o_laco_de_retentativa_que_volta_ao_switch():
    # O W23 real: toda resposta (de qualquer provedor) cai em "Retentar?", que
    # volta a "Preparar chamada" -> Switch. Voltar ao Switch não é estar no ramo.
    wf = _w23([("Provedor", 0, "Chamar Claude"), ("Provedor", 1, "Responder simulado"),
               ("Chamar Claude", 0, "Gravar chamada"), ("Responder simulado", 0, "Gravar chamada"),
               ("Gravar chamada", 0, "Preparar chamada"), ("Preparar chamada", 0, "Provedor")])
    wf["nodes"].append(_no("Preparar chamada", "n8n-nodes-base.code"))
    r = analisar_fluxo(wf, "W23.json")
    assert r["violacoes"] == [] and len(r["permitidos"]) == 1


def test_guarda_anthropic_pega_a_chamada_no_ramo_errado():
    wf = _w23([("Provedor", 1, "Chamar Claude")])            # pendurada na saída `simulado`
    assert analisar_fluxo(wf, "W23.json")["violacoes"]


def test_guarda_anthropic_pega_a_chamada_alcancavel_por_dois_ramos():
    wf = _w23([("Provedor", 0, "Chamar Claude"), ("Provedor", 1, "Chamar Claude")])
    assert analisar_fluxo(wf, "W23.json")["violacoes"]


def test_guarda_anthropic_pega_outro_fluxo_e_fora_de_no():
    w50 = {"name": "W50 Envio de e-mails", "nodes": [_no("Resumo por IA", url=URL)], "connections": {}}
    assert analisar_fluxo(w50, "W50.json")["violacoes"]
    # o mesmo Switch fora do W23 não autoriza nada
    w20 = _w23([("Provedor", 0, "Chamar Claude")])
    w20["name"] = "W20 Processar"
    assert analisar_fluxo(w20, "W20.json")["violacoes"]
    pin = {"name": "W00 Saúde", "nodes": [], "connections": {}, "pinData": {"x": [{"json": {"u": URL}}]}}
    assert analisar_fluxo(pin, "W00.json")["violacoes"]


def test_switch_v2_com_saida_explicita():
    no = _no("Provedor", SWITCH, rules={"rules": [{"value2": "simulado", "output": 1},
                                                   {"value2": "claude", "output": 0}]})
    assert _saidas_claude(no) == {0}


def test_switch_sem_rotulo_com_a_comparacao_na_expressao():
    cond = "={{ $json.provedor === '%s' }}"
    no = _no("Provedor", SWITCH, rules={"values": [
        {"conditions": {"conditions": [{"leftValue": cond % "simulado"}]}},
        {"conditions": {"conditions": [{"leftValue": cond % "claude"}]}},
        {"conditions": {"conditions": [{"leftValue": cond % "claude-code"}]}}]})
    assert _saidas_claude(no) == {1}


# ================================================================== 2. segredos
def _achado(nome, rotulo, texto, m, linha):
    return "%s:%d: %s (%s…)" % (nome, linha, rotulo, texto[m.start():m.start() + 6])


def _variado(s: str) -> bool:
    """Maiúscula, minúscula e dígito: a cara de um segredo gerado, não de um nome inventado."""
    return bool(re.search(r"[A-Z]", s) and re.search(r"[a-z]", s) and re.search(r"\d", s))


# (rótulo, regex, exige variedade de caracteres)
PADROES = [
    ("chave sk- (Anthropic/OpenAI)", re.compile(r"(?<![A-Za-z0-9])sk-(?:ant-|proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}"), True),
    ("JWT (eyJ...)", re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), False),
    ("chave da API do n8n (n8n_api_...)", re.compile(r"n8n_api_[A-Za-z0-9]{20,}"), False),
    ("chave privada PEM", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"), False),
    ("segredo OAuth do Google (GOCSPX-)", re.compile(r"GOCSPX-[A-Za-z0-9_\-]{20,}"), False),
    ("chave de API do Google (AIza...)", re.compile(r"AIza[0-9A-Za-z_\-]{35}"), False),
    ("token do GitHub", re.compile(r"(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}"), False),
    ("chave de acesso AWS", re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])"), False),
    ("token do Slack", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), False),
]


def achar_segredos(texto: str, nome: str = "<texto>") -> list[str]:
    achados = []
    for rotulo, rx, variado in PADROES:
        for m in rx.finditer(texto):
            if variado and not _variado(m.group(0)):
                continue
            achados.append(_achado(nome, rotulo, texto, m, texto.count("\n", 0, m.start()) + 1))
    return achados


def vazamentos_de_valor(texto: str, segredos: dict, nome: str = "<texto>") -> list[str]:
    return ["%s: contém o valor de %s" % (nome, var) for var, valor in segredos.items() if valor in texto]


BINARIOS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".zip", ".gz", ".xlsx", ".docx",
            ".traineddata", ".woff", ".woff2", ".ttf", ".otf", ".pyc", ".db", ".sqlite", ".tif", ".tiff"}


def _git_ls_files(*extra: str) -> list[str]:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git não está no PATH: sem `git ls-files` não há a lista do que é versionado")
    r = subprocess.run([git, "ls-files", "-z", *extra], cwd=str(RAIZ), capture_output=True)
    if r.returncode != 0:
        pytest.skip("`git ls-files` falhou (não é um checkout git?): %s"
                    % r.stderr.decode("utf-8", "replace").strip()[:200])
    return [n for n in r.stdout.decode("utf-8", "replace").split("\0") if n]


@pytest.fixture(scope="module")
def candidatos() -> list[tuple[str, str]]:
    """(caminho relativo, texto) dos versionados + dos não ignorados que entrariam no próximo commit."""
    nomes = sorted(set(_git_ls_files()) | set(_git_ls_files("--others", "--exclude-standard")))
    saida = []
    for nome in nomes:
        p = RAIZ / nome
        if p.suffix.lower() in BINARIOS or not p.is_file():
            continue
        dados = p.read_bytes()
        if b"\0" in dados[:8192]:
            continue
        saida.append((nome, dados.decode("utf-8", "replace")))
    assert saida, "nenhum arquivo de texto listado pelo git ls-files"
    return saida


def test_nenhum_arquivo_versionado_tem_cara_de_segredo(candidatos):
    achados = [a for nome, texto in candidatos for a in achar_segredos(texto, nome)]
    assert not achados, "segredo com cara de segredo em arquivo versionado:\n" + "\n".join(achados)


def _segredos_locais() -> dict:
    """{'arquivo:VAR': valor} dos segredos que existem NESTE host (nunca impressos)."""
    def ler_env(caminho: Path) -> dict:
        d = {}
        for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                v = v.strip().strip('"').strip("'")
                d[k.strip()] = v
        return d

    segredos = {}
    for rel in (".env", "docker/.env"):
        p = RAIZ / rel
        if p.is_file():
            for k, v in ler_env(p).items():
                if re.search(r"PASSWORD|SECRET|TOKEN|KEY|SENHA", k) and len(v) >= 12:
                    segredos["%s:%s" % (rel, k)] = v
    pasta = RAIZ / "n8n" / ".segredos"
    for nome in ("api_key", "mcp_token", "cookie"):
        p = pasta / nome
        if p.is_file() and len(p.read_text(encoding="utf-8", errors="replace").strip()) >= 12:
            segredos["n8n/.segredos/" + nome] = p.read_text(encoding="utf-8", errors="replace").strip()
    p = pasta / "owner.json"
    if p.is_file():
        try:
            senha = json.loads(p.read_text(encoding="utf-8")).get("password") or ""
        except ValueError:
            senha = ""
        if len(senha) >= 8:
            segredos["n8n/.segredos/owner.json:password"] = senha
    return segredos


def test_nenhum_arquivo_versionado_carrega_o_valor_de_um_segredo_local(candidatos):
    segredos = _segredos_locais()
    if not segredos:
        pytest.skip("nenhum .env/.segredos neste host (ex.: runner de CI): não há valor local para procurar")
    achados = [a for nome, texto in candidatos for a in vazamentos_de_valor(texto, segredos, nome)]
    assert not achados, "\n".join(achados)


# -- o guarda sabe falhar ------------------------------------------------------
def _b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


FALSOS = {
    "sk anthropic": "sk-ant-api03-" + "Qx7vB2mN" * 11 + "AA",
    "sk openai": "sk-proj-" + "Zt4kP9wR" * 6,
    "jwt do n8n": _b64({"alg": "HS256", "typ": "JWT"}) + "." + _b64({"sub": "ab12", "iss": "n8n"}) + "." + "Sg9xK2pLq7" * 3,
    "n8n_api": "n8n_api_" + "a1B2c3D4e5" * 3,
    "pem": "-----BEGIN " + "PRIVATE KEY-----",
    "google oauth": "GOCSPX-" + "q1W2e3R4t5Y6" * 2,
}
INOCENTES = [
    "sk-ant-segredo-que-nao-pode-vazar",          # o valor falso do test_health: sem cara de gerado
    "o disk-cleanup-do-worker-roda-a-cada-hora",
    "eyJ sozinho não é JWT", "n8n_api_curta", "-----BEGIN PUBLIC KEY-----",
]


@pytest.mark.parametrize("rotulo", list(FALSOS))
def test_guarda_de_segredo_pega_cada_formato(rotulo):
    achados = achar_segredos("config = '%s'\n" % FALSOS[rotulo], "falso.py")
    assert achados and all(FALSOS[rotulo] not in a for a in achados), "o achado não pode imprimir o segredo"


def test_guarda_de_segredo_nao_acusa_o_que_so_parece():
    assert [a for s in INOCENTES for a in achar_segredos(s)] == []


def test_guarda_de_valor_pega_o_valor_e_nao_o_imprime():
    achados = vazamentos_de_valor("url = postgres://u:Senh4-Muito-Longa@h/db", {"docker/.env:X_PASSWORD": "Senh4-Muito-Longa"})
    assert achados == ["<texto>: contém o valor de docker/.env:X_PASSWORD"]


# ------------------------------------------------------------------ Python sem SyntaxWarning
PASTAS_PYTHON = ("api", "migracao", "scripts/fopa", "tests", "db", "n8n", "ci", "docker")


def _avisos_de_sintaxe(arquivos) -> list:
    achados = []
    for p in arquivos:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
        achados += ["%s:%s %s" % (p.relative_to(RAIZ) if p.is_relative_to(RAIZ) else p, x.lineno, x.message)
                    for x in w if issubclass(x.category, SyntaxWarning)]
    return achados


def test_python_do_projeto_sem_syntaxwarning(tmp_path):
    # 24/09: um "C:" + barra invertida + "dados" numa docstring (escape inválido) só apareceu no log do build da
    # imagem — os testes não tratam SyntaxWarning como falha, e numa versão futura do Python ela vira SyntaxError.
    arquivos = [p for d in PASTAS_PYTHON for p in (RAIZ / d).rglob("*.py")
                if "node_modules" not in p.parts and "rascunho" not in p.parts]
    assert len(arquivos) > 50
    assert _avisos_de_sintaxe(arquivos) == []
    ruim = tmp_path / "ruim.py"                       # o guarda sabe falhar
    ruim.write_text('X = "C:' + chr(92) + 'dados"' + chr(10), encoding="utf-8")
    assert len(_avisos_de_sintaxe([ruim])) == 1
