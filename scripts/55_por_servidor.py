# -*- coding: utf-8 -*-
"""
R$ por servidor: o que o banco paga por cabeca.

    python 55_por_servidor.py

NAO CHAMA MODELO. Cruza a Q14 (numero de servidores, lida do edital) com o
`valorTotal` da API do PNCP (valor minimo do lance), ja cacheado em disco.

POR QUE O NUMERO IMPORTA
  Valor minimo sozinho nao compara licitacoes: R$ 3,2 milhoes em Bertioga e
  R$ 346 mil em Capao do Cipo nao dizem qual e o melhor negocio. Por cabeca,
  dizem -- e e assim que a area comercial pensa.

O QUE ELE NAO E
  Nao e o valor da folha nem o retorno esperado. E o PISO que o orgao pediu,
  dividido pela populacao que ele declarou. O agio de cada disputa fica de
  fora, e esta em [[Concorrencia e mercado]].

A RESSALVA QUE O PROPRIO DADO IMPOE
  A Q14 nao mede sempre a mesma coisa. Os editais dizem "servidores",
  "matriculas", "beneficiarios unicos" e "vinculos" -- e Bertioga esclarece
  que 1.896 sao VINCULOS, nao pessoas, porque um servidor pode acumular mais
  de um. Dividir por unidades diferentes e comparar coisas diferentes, e por
  isso a unidade sai impressa em cada linha.
"""
from __future__ import annotations

import glob
import io
import json
import os
import re
import statistics as st
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

SAIDAS = os.path.join(RAIZ, "saidas")
AMOSTRAS = os.path.join(RAIZ, "amostras")

# o primeiro inteiro da resposta, com ou sem separador de milhar
RE_N = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d{2,6})")
# a unidade que o edital usou -- e ela que decide o que o numero conta
UNIDADES = ("vínculo", "vinculo", "matrícula", "matricula",
            "beneficiário", "beneficiario", "servidor", "segurado",
            "pessoa", "colaborador", "funcionário", "funcionario")


def unidade(texto: str, numero: str) -> str:
    """
    A unidade que vem COLADA no numero, nao a que aparece em qualquer lugar.

    A primeira versao procurava as palavras no texto inteiro e devolvia
    "vinculo" para as nove licitacoes -- porque quase toda resposta MENCIONA
    vinculo em algum lugar da explicacao. Uma unidade lida do lugar errado e
    pior que nenhuma: ela parece dado.
    """
    t = (texto or "").lower()
    i = t.find(numero.lower())
    if i < 0:
        return "?"
    janela = t[i + len(numero):i + len(numero) + 40]
    for u in UNIDADES:
        if u in janela:
            return u.rstrip("s")
    return "?"


def valor_da_api(nome: str) -> tuple[float | None, str]:
    """
    O valor MINIMO DO LANCE -- e so quando ele existe.

    `valorTotal` nem sempre e lance. Em Santa Efigenia de Minas/MG, que e
    Credenciamento, o orgao cadastrou `quantidade = 389 SERVIDOR` com
    `valorUnitarioEstimado = 1,0`: o `valorTotal` de R$ 389,00 e a populacao
    multiplicada por um real simbolico. Dividir isso pela populacao devolve
    exatamente R$ 1,00 por cabeca -- um numero que parece medida e e
    aritmetica circular.
    
    O discriminador esta no proprio item: quando `criterioJulgamentoNome` e
    "Nao se aplica" nao ha disputa de preco, e o valor nao e lance.
    """
    p = os.path.join(AMOSTRAS, nome, "_itens_api.json")
    if not os.path.isfile(p):
        return None, "sem cache da API"
    try:
        itens = json.load(io.open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None, "cache ilegivel"
    crits = {(x.get("criterioJulgamentoNome") or "").strip() for x in (itens or [])}
    if crits and crits <= {"Não se aplica", ""}:
        return None, "sem disputa de preço (criterio 'Não se aplica')"
    # e o valor unitario simbolico denuncia o mesmo padrao
    if all((x.get("valorUnitarioEstimado") or 0) <= 1.0 for x in (itens or [])):
        return None, "valor unitário simbólico (R$ 1,00)"
    vals = [float(x.get("valorTotal")) for x in (itens or [])
            if x.get("valorTotal")]
    return (sum(vals) if vals else None), ""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    linhas, sem_valor, sem_n = [], [], []
    for p in sorted(glob.glob(os.path.join(SAIDAS, "*", "auditoria.json"))):
        nome = os.path.basename(os.path.dirname(p))
        if nome.startswith("_"):
            continue
        d = json.load(io.open(p, encoding="utf-8"))
        q14 = next((r for r in d["respostas"] if r["id"] == "Q14"), None)
        if not q14 or not (q14.get("resposta") or "").strip():
            sem_n.append(nome)
            continue
        m = RE_N.search(q14["resposta"])
        val, porque = valor_da_api(nome)
        if not m:
            sem_n.append(nome)
            continue
        if not val:
            sem_valor.append((nome, porque))
            continue
        n = int(m.group(1).replace(".", ""))
        if n < 10:
            sem_n.append(nome)
            continue
        linhas.append((val / n, n, val, unidade(q14["resposta"], m.group(1)), nome))

    print("=" * 96)
    print("  R$ POR SERVIDOR — valor mínimo do lance dividido pela população declarada")
    print("=" * 96)
    if not linhas:
        print("  nenhuma licitação com Q14 e valor da API ao mesmo tempo")
        return 1
    linhas.sort(reverse=True)
    print("  %-40s %8s %14s %11s  %s"
          % ("licitação", "pop.", "mínimo R$", "R$/cabeça", "unidade"))
    print("  " + "-" * 92)
    for r, n, v, u, nome in linhas:
        print("  %-40s %8d %14s %11s  %s"
              % (nome[:40], n, ("%.2f" % v), ("%.2f" % r), u))
    rs = [x[0] for x in linhas]
    print()
    print("  n = %d  |  mediana R$ %.2f  |  mínimo %.2f  |  máximo %.2f"
          % (len(rs), st.median(rs), min(rs), max(rs)))
    print("  amplitude: %.1f× entre o menor e o maior" % (max(rs) / min(rs)))
    print()
    print("  A UNIDADE NÃO É A MESMA em todas as linhas. Onde o edital diz")
    print("  \"vínculo\", o denominador conta CONTRATOS, não pessoas — Bertioga")
    print("  esclarece que um servidor pode acumular mais de um. Comparar uma")
    print("  linha de \"vínculo\" com uma de \"servidor\" sobrestima a segunda.")
    if sem_valor:
        print()
        print("  FORA DA CONTA por não haver lance (%d):" % len(sem_valor))
        for nm, pq in sem_valor:
            print("     %-44s %s" % (nm[:44], pq))
    if sem_n:
        print("  sem número utilizável na Q14 (%d): %s" % (len(sem_n), ", ".join(
            x[:26] for x in sem_n[:4])))

    io.open(os.path.join(SAIDAS, "_por_servidor.json"), "w",
            encoding="utf-8").write(json.dumps({
                "medido_em": "2026-09-23", "n": len(rs),
                "mediana": round(st.median(rs), 2),
                "min": round(min(rs), 2), "max": round(max(rs), 2),
                "linhas": [{"licitacao": nome, "populacao": n, "unidade": u,
                            "valor_minimo": v, "por_cabeca": round(r, 2)}
                           for r, n, v, u, nome in linhas],
            }, ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_por_servidor.json · custo R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
