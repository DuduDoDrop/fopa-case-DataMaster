# -*- coding: utf-8 -*-
"""
"A suíte inteira roda com a chave ausente" (plano 11.8) — para scripts.

Tirar ANTHROPIC_API_KEY/OPENAI_API_KEY do ambiente não basta no host de
desenvolvimento: `fopa.modelos` chama `segredos.carregar()` no import, e ele lê
o `.env` da raiz — que TEM chave de modelo — de volta para `os.environ`. Este
invólucro roda um script do pacote com o carregador neutralizado pelo mesmo
mecanismo público que o `api/__init__.py` usa (a primeira chamada decide, e
com um caminho que não existe ela não lê nada), e confere no fim que nenhuma
chave apareceu no ambiente durante a execução. Se apareceu, sai 3.

    python ci/sem_chave.py scripts/40_fumaca.py [args...]

O mesmo módulo serve de plugin do pytest (`-p ci.sem_chave`): tira as chaves
no início da sessão e reprova a sessão se alguma aparecer até o fim.
"""
from __future__ import annotations

import os
import runpy
import sys

# As duas que o plano nomeia, mais o que também é API paga no projeto (o
# teto de US$ 5 por API vale para Anthropic, OpenAI e Jev).
CHAVES = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
PREFIXOS = ("ANTHROPIC_", "OPENAI_")
OUTRAS = ("JEV_API_KEY",)

_ENV_INEXISTENTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.nunca-lido-pelo-ci")


def proibida(nome: str) -> bool:
    return nome.startswith(PREFIXOS) or nome in OUTRAS


def limpar(env: dict) -> list[str]:
    """Remove do dicionário (ou de os.environ) toda variável de API paga. Devolve os NOMES removidos."""
    fora = sorted(k for k in env if proibida(k))
    for k in fora:
        del env[k]
    return fora


def presentes() -> list[str]:
    return sorted(k for k in os.environ if proibida(k))


def neutralizar_env_do_repositorio(pasta_scripts: str) -> bool:
    """Faz `fopa.segredos` nunca ler o `.env`. Devolve False se o pacote não existe ali."""
    if not os.path.isdir(os.path.join(pasta_scripts, "fopa")):
        return False
    if pasta_scripts not in sys.path:
        sys.path.insert(0, pasta_scripts)
    from fopa import segredos  # noqa: PLC0415
    segredos.carregar(_ENV_INEXISTENTE)
    return True


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("uso: python ci/sem_chave.py <script.py> [args...]", file=sys.stderr)
        return 2
    script = os.path.abspath(argv[1])
    limpar(os.environ)
    neutralizar_env_do_repositorio(os.path.dirname(script))
    sys.argv = [script, *argv[2:]]
    sys.path.insert(0, os.path.dirname(script))
    codigo = 0
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit as e:
        codigo = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    sys.stdout.flush()
    vazou = presentes()
    if vazou:
        print("\n[sem_chave] REPROVADO: %s apareceram no ambiente durante %s"
              % (", ".join(vazou), os.path.basename(script)))
        return 3
    print("\n[sem_chave] nenhuma chave de API paga no ambiente do início ao fim de %s"
          % os.path.basename(script))
    return codigo


# ------------------------------------------------------------------ plugin do pytest
def pytest_configure(config):  # noqa: ARG001
    limpar(os.environ)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    vazou = presentes()
    if vazou:
        print("\n[sem_chave] REPROVADO: %s apareceram no ambiente durante a sessão" % ", ".join(vazou))
        session.exitstatus = 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
