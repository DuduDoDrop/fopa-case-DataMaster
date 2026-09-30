# -*- coding: utf-8 -*-
"""
A fumaça da v2 (`scripts/40_fumaca.py`) como teste do worker — CI camada (a).

Plano, seção 6 e 11.1: a imagem roda SEM acervo (`amostras/`, `saidas/`,
`Fopa-v2/` ficam fora dela), e parte dos testes do 40_ retorna cedo quando o
acervo não está. Por isso este teste NÃO promete 135: ele exige zero falhas e
registra o número real de asserções que rodaram, para que "a fumaça passou"
nunca esconda "a fumaça quase não rodou".

Os invariantes que dependem do texto (verificador sem rede, ancoragem, guarda
numérica, escopo, furtivo, tag de injeção, pirâmide, família de critério, Jev
nunca decide) não dependem do acervo e rodam nos dois lugares.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SCRIPTS = RAIZ / "scripts"
# Com o acervo (host de desenvolvimento) roda tudo; sem ele (imagem), o piso é
# o que não depende de disco. Medido: 135 no host; o piso protege contra um
# 40_ que "passa" porque parou de rodar.
PISO_SEM_ACERVO = 30


def _rodar(script: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("ANTHROPIC_API_KEY", None)
    return subprocess.run([sys.executable, script], cwd=SCRIPTS, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=900)


def _acervo() -> str:
    # `amostras/_fixture` existe sempre (até na imagem): acervo é pasta de licitação, sem "_" na frente.
    base = RAIZ / "amostras"
    n = sum(1 for d in base.glob("*") if d.is_dir() and not d.name.startswith("_")) if base.is_dir() else 0
    return "presente: %d pastas" % n if n else "ausente"


def test_fumaca_da_v2_sem_falha_e_com_o_numero_real():
    r = _rodar("40_fumaca.py")
    ok = re.search(r"asserções ok \.+ (\d+)", r.stdout)
    falhas = re.search(r"falhas \.+ (\d+)", r.stdout)
    assert ok and falhas, "a fumaça não imprimiu o resultado:\n" + r.stdout[-2000:] + r.stderr[-2000:]
    n_ok, n_falhas = int(ok.group(1)), int(falhas.group(1))
    print("\n40_fumaca: %d asserções ok, %d falhas (acervo %s)"
          % (n_ok, n_falhas, _acervo()))
    assert n_falhas == 0 and r.returncode == 0, r.stdout[-3000:]
    assert n_ok >= PISO_SEM_ACERVO


def test_suite_de_escopo_da_v2():
    r = _rodar("23_testa_escopo.py")
    assert r.returncode == 0 and "passaram" in r.stdout, r.stdout[-2000:]
