# CI da FOPA v3 (plano 11.1 / 11.8). O Makefile só chama o executor único:
# `python ci/rodar.py` faz exatamente o mesmo onde não há `make` (host Windows).
#
#   make ci      camada (a) e, se houver acervo/stack, a (b)
#   make ci-a    só a camada (a): sem acervo, sem stack, sem rede paga (o que o GitHub roda)
#   make ci-b    só a camada (b): 40_fumaca com acervo, n8n/tests, invariantes e guardas da stack

PYTHON ?= python

.PHONY: ci ci-a ci-b

ci:
	$(PYTHON) ci/rodar.py

ci-a:
	$(PYTHON) ci/rodar.py --camada a

ci-b:
	$(PYTHON) ci/rodar.py --camada b
