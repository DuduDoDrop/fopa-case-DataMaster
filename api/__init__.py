# -*- coding: utf-8 -*-
"""
Pacote `api` — worker e API do site da FOPA v3 (FastAPI).

A v3 NÃO reescreve o pipeline: este pacote só expõe por HTTP o que já existe
em `scripts/fopa` (verificador, extrator, ocr, recuperação, página, modelos).
Por isso a primeira coisa que ele faz é tornar `from fopa import ...`
possível, pondo `<raiz>/scripts` no `sys.path` — o pacote `fopa` não é
instalado, vive dentro de `scripts/` e resolve `amostras/` e `saidas/` relativo
ao pai de `scripts/`.

A segunda coisa é uma proteção: `fopa.modelos` chama `segredos.carregar()` no
import, que lê o `.env` do repositório e despejaria `ANTHROPIC_API_KEY` no
ambiente do processo. O worker nunca pode ter essa chave (plano, seção 4: quem
chama o modelo é o n8n, com a Credential; `/health.anthropic_key_presente`
tem de ser `false`). No container não existe `.env`, mas no host de
desenvolvimento existe — então o carregador é marcado como "já rodou", apontando
para um arquivo que não existe, antes de qualquer import do pacote. Quem quiser
a chave em um script continua tendo: isto só vale para processos da `api`.
"""
from __future__ import annotations

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)                       # projeto-fopa/
CAMINHO_SCRIPTS = os.path.join(RAIZ, "scripts")

if CAMINHO_SCRIPTS not in sys.path:
    sys.path.insert(0, CAMINHO_SCRIPTS)

from fopa import segredos as _segredos  # noqa: E402  (precisa do sys.path acima)

# `carregar()` é idempotente: a primeira chamada decide. Com um caminho que não
# existe ela não lê nada e as chamadas seguintes (a de `fopa.modelos`, por
# exemplo) viram no-op. A API pública é usada em vez de alterar `_carregado`.
_segredos.carregar(os.path.join(AQUI, ".env.nunca-lido-pela-api"))

__all__ = ["AQUI", "RAIZ", "CAMINHO_SCRIPTS"]
