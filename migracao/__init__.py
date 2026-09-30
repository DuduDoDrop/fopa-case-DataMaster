# -*- coding: utf-8 -*-
"""
Migração do acervo v2 para o Postgres da v3 (plano, seção 9).

`congelar.py` tira o snapshot; `regras.py` decide, sem banco e sem disco, o que
cada coisa do acervo vira; `acervo.py` lê o snapshot; `importar.py` escreve.

O pacote `fopa` (em `scripts/`) entra no caminho aqui, como em `api/`: as
regras de ausência e de modalidade são as do verificador, nunca uma cópia.
"""
from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
