# -*- coding: utf-8 -*-
"""
Política de veredito da v3, aplicada DEPOIS do verificador.

O verificador (`scripts/fopa/verificador.py`, módulo mantido à parte) aprova a
ausência declarada: um "Não localizado" sem trecho ancora como APROVADO, e o
"não se aplica" da modalidade (Q4/Q6 de credenciamento e dispensa) nem conta
como lacuna. Para quem usa o produto isso escondia exatamente o que precisa de
olho humano — a pergunta que o edital não respondeu.

Decisão de produto (24/09/2026): toda resposta "Não localizado" entra no status
de revisão (REVISAR), inclusive o Q4/Q6 de credenciamento e dispensa.

A regra só REBAIXA: APROVADO → REVISAR, com o motivo escrito na resposta.
REPROVADO continua REPROVADO (o pior veredito vence) e o que já estava em
REVISAR não ganha um segundo motivo. `nao_localizado` do relatório não muda:
continua contando ausências do DOCUMENTO, não vereditos.

Mora aqui, e não no verificador, para o verificador ficar intocado. E
entra no hash de `versao_regras` (`api/versao.py`): mudar esta política é regra
nova, e o W30 reverifica o acervo a custo zero em vez de o número mudar calado.
"""
from __future__ import annotations

from fopa.verificador import APROVADO, REVISAR, nao_encontrou

ALERTA_NAO_LOCALIZADO = ("não localizado: a resposta não está nos documentos — conferir antes de usar "
                         "(política v3: todo não localizado vai para revisão)")


def aplicar(ext, rel):
    """Aplica a política às respostas de `ext` e recompõe as contagens de `rel`."""
    for r in ext.respostas:
        if r.veredito == APROVADO and nao_encontrou(r.resposta or ""):
            r.veredito = REVISAR
            r.alertas.append(ALERTA_NAO_LOCALIZADO)
    rel.aprovadas = sum(1 for r in ext.respostas if r.veredito == APROVADO)
    rel.revisar = sum(1 for r in ext.respostas if r.veredito == REVISAR)
    rel.reprovadas = sum(1 for r in ext.respostas if r.veredito not in (APROVADO, REVISAR))
    return rel


__all__ = ["aplicar", "ALERTA_NAO_LOCALIZADO"]
