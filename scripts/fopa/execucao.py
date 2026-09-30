# -*- coding: utf-8 -*-
"""
O registro de execução — quem rodou, quando, o que fez e quanto custou.

POR QUE NÃO É UM ARQUIVO DE LOG
  A pergunta do vault era *"definir para onde vai o log e quem lê"*, e a
  segunda metade é a que importa. Um `>> monitor.log 2>&1` responde só a
  primeira: o arquivo cresce para sempre, ninguém abre, e quando alguém abre é
  porque já deu problema.

  Aqui o registro é **uma linha JSON por execução**, e quem lê é o **painel** —
  a mesma tela que o operador já abre todo dia. Log que precisa de alguém
  lembrar de ler não é auditoria; é arquivo morto com data.

  A saída em texto continua indo para o terminal e pode ser redirecionada. O
  que muda é que o **resumo** de cada execução fica em formato que se consulta.

O QUE CADA LINHA CARREGA
  · quando começou e quanto durou
  · qual script, com quais argumentos
  · o que mudou no mundo (baixadas, extraídas, recusadas, falhas)
  · quanto custou em API de modelo — **sempre**, mesmo quando é zero

  O custo entra mesmo em execução gratuita de propósito. Uma série em que a
  maioria das linhas diz `R$ 0,00` torna óbvio, de relance, quais execuções
  gastam — e é isso que alguém quer saber ao abrir o histórico.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
DESTINO = os.path.join(RAIZ, "saidas", "_execucoes.jsonl")

# Um registro por linha, acrescentado ao fim. Nunca reescreve o arquivo:
# histórico que pode ser reescrito não é histórico.
MAX_LINHAS = 2000


def registrar(script: str, inicio: float, **campos) -> dict:
    """
    Acrescenta uma linha ao histórico de execuções.

        t0 = time.time()
        ...
        execucao.registrar("20_monitor.py", t0,
                           baixadas=3, extraidas=3, custo_brl=12.40)

    Nunca levanta: um registro que quebra a execução que ele deveria registrar
    é pior que registro nenhum.
    """
    reg = {
        "em": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(inicio)),
        "script": script,
        "duracao_s": round(time.time() - inicio, 1),
        "argumentos": " ".join(sys.argv[1:]),
        "custo_brl": 0.0,
    }
    reg.update(campos)
    try:
        os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
        with io.open(DESTINO, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return reg


def ler(limite: int = 30) -> list[dict]:
    """As últimas execuções, da mais recente para a mais antiga."""
    if not os.path.isfile(DESTINO):
        return []
    linhas = []
    try:
        with io.open(DESTINO, encoding="utf-8") as f:
            for l in f:
                l = l.strip()
                if not l:
                    continue
                try:
                    linhas.append(json.loads(l))
                except ValueError:
                    continue       # linha corrompida não derruba a leitura
    except OSError:
        return []
    return list(reversed(linhas[-MAX_LINHAS:]))[:limite]


def resumo(limite: int = 30) -> str:
    """Uma tabela de texto, para quem está no terminal."""
    regs = ler(limite)
    if not regs:
        return "  (sem execuções registradas)"
    fora = ["  %-20s %-24s %8s %9s  %s"
            % ("quando", "script", "duração", "custo", "o que fez")]
    fora.append("  " + "-" * 92)
    for r in regs:
        feito = " · ".join(
            "%s %s" % (v, k) for k, v in sorted(r.items())
            if k not in ("em", "script", "duracao_s", "argumentos", "custo_brl")
            and isinstance(v, (int, float)) and v)
        fora.append("  %-20s %-24s %7.1fs %9s  %s"
                    % (r.get("em", "")[:19].replace("T", " "),
                       r.get("script", "")[:24],
                       r.get("duracao_s", 0),
                       "R$ %.2f" % r.get("custo_brl", 0),
                       feito[:44]))
    return "\n".join(fora)
