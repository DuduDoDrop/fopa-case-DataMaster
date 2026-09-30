# -*- coding: utf-8 -*-
"""
Configuração comum dos testes da API.

Garante que `import api` funcione mesmo quando o pytest é chamado de fora da
raiz do repositório (o `python -m pytest` já põe o cwd no sys.path, mas um
`pytest` direto não). O `api/__init__.py` cuida do resto: põe `scripts/` no
path e impede que o pacote `fopa` leia o `.env` deste host.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
