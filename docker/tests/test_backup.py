# -*- coding: utf-8 -*-
"""
`docker/backup.py` — a regra que a verificação usa para comparar as contagens restauradas com o manifesto.

  - tabela que só cresce durante o dump: a foto do pg_dump fica entre a contagem de antes e a de depois;
  - `n8n.execution_entity` cresce (o W50 cria uma execução por minuto) e é podada pelo próprio n8n
    (EXECUTIONS_DATA_PRUNE): a foto pode sair do intervalo, no máximo pelas execuções criadas durante o backup.
    Só ela tem folga, e a folga não esconde um dump incompleto.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "docker"))

import backup  # noqa: E402


def test_tabela_que_so_cresce_confere_entre_antes_e_depois():
    assert backup.contagem_confere("fopa", "licitacoes", 6613, 6613, 6613)
    assert backup.contagem_confere("fopa", "execucoes_workflow", 105, 100, 110)
    assert not backup.contagem_confere("fopa", "execucoes_workflow", 111, 100, 110)
    assert not backup.contagem_confere("fopa", "paginas", 155349, 155350, 155350)
    assert not backup.contagem_confere("fopa", "licitacoes", 10, None, 10 + 1)


def test_execucoes_do_n8n_podadas_durante_o_dump_conferem():
    # 29/09/2026 03:42: 10.013 antes, 10.014 na foto do pg_dump, 10.001 depois (o n8n podou no meio do backup).
    assert backup.contagem_confere("n8n", "execution_entity", 10014, 10013, 10001)


def test_a_folga_das_execucoes_nao_esconde_dump_incompleto():
    assert not backup.contagem_confere("n8n", "execution_entity", 9000, 10013, 10001)
    assert not backup.contagem_confere("n8n", "execution_entity", 0, 10013, 10001)
    assert not backup.contagem_confere("n8n", "workflow_entity", 16, 15, 15), "a folga é só da tabela podada"
