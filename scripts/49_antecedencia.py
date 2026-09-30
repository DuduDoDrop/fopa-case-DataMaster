# -*- coding: utf-8 -*-
"""
Mede a ANTECEDENCIA REAL entre o que se sabe e a sessao.

A promessa "avisamos com X dias" e a unica coisa que o produto entrega antes
de qualquer extracao, e ate agora o X nunca foi medido -- estava marcado como
`{{A PREENCHER}}` no 8 Orquestrador.

O art. 55 da Lei 14.133/2021 da o MINIMO LEGAL por criterio de julgamento:
maior lance e 15 dias uteis. Mas minimo legal nao e o que o sistema recebe.
O que o sistema recebe e a diferenca entre `publicado_em` (quando o registro
apareceu NO PNCP) e `fim_prazo` (quando fecha a proposta).

ESSAS DUAS COISAS SAO DIFERENTES, e a diferenca e o ponto desta medicao: o
edital pode ter sido divulgado semanas antes no diario oficial e so entrar no
PNCP na vespera. Para a lei, o prazo correu. Para o monitoramento, nao existiu.

    python 49_antecedencia.py
"""
import datetime as dt
import io
import json
import os
import statistics as st
import sys

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDAS = os.path.join(RAIZ, "saidas")

# Art. 55, VI: maior lance -> 15 dias uteis. E o criterio da cessao de folha,
# que e leilao de maior oferta. NAO e o unico possivel: edital que se enquadra
# como servico comum por menor preco cai no inciso II (10 dias uteis). O corpus
# nao guarda o criterio de julgamento, entao 15 e referencia, nao veredito.
MINIMO_MAIOR_LANCE = 15


def dia(s: str):
    if not s:
        return None
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def dias_uteis(a: dt.date, b: dt.date) -> int:
    n, c = 0, a
    while c < b:
        c += dt.timedelta(days=1)
        if c.weekday() < 5:
            n += 1
    return n


def main() -> int:
    p = os.path.join(SAIDAS, "_corpus_escopo.json")
    if not os.path.isfile(p):
        print("sem corpus -- rode 24_corpus_escopo.py antes")
        return 1
    reg = [x for x in json.load(io.open(p, encoding="utf-8"))["registros"]
           if x.get("dentro") is not False]

    pares = []
    sem_data = 0
    for x in reg:
        pub, fim = dia(x.get("publicado_em")), dia(x.get("fim_prazo"))
        if pub and fim and fim >= pub:
            pares.append((dias_uteis(pub, fim), x))
        else:
            sem_data += 1
    if not pares:
        print("nenhum registro com as duas datas")
        return 1
    pares.sort(key=lambda t: t[0])
    v = [t[0] for t in pares]

    print("=" * 96)
    print("  ANTECEDENCIA REAL — do registro no PNCP ate o fim do prazo")
    print("=" * 96)
    print("  no escopo ................. %d" % len(reg))
    print("  com as duas datas ......... %d" % len(pares))
    print("  sem uma das datas ......... %d  (nao entram na conta)" % sem_data)
    print()
    print("  dias UTEIS    min %d | p25 %d | mediana %d | p75 %d | max %d"
          % (v[0], v[len(v) // 4], st.median(v), v[3 * len(v) // 4], v[-1]))
    print()

    # A distribuicao acumulada e o que a promessa precisa: "em X% dos casos
    # ha ao menos N dias".
    print("  se prometermos N dias uteis de antecedencia, cobrimos:")
    for n in (1, 3, 5, 10, 15, 20):
        ok = sum(1 for x in v if x >= n)
        barra = "#" * int(round(40.0 * ok / len(v)))
        print("   >= %2d du  %-40s %5.1f%%  (%d de %d)"
              % (n, barra, 100.0 * ok / len(v), ok, len(v)))
    print()

    zero = [t for t in pares if t[0] == 0]
    abaixo = [t for t in pares if 0 < t[0] < MINIMO_MAIOR_LANCE]
    print("  ABAIXO dos %d dias uteis do art. 55, VI: %d de %d (%.1f%%)"
          % (MINIMO_MAIOR_LANCE, len(zero) + len(abaixo), len(v),
             100.0 * (len(zero) + len(abaixo)) / len(v)))
    print("     desses, com ZERO dias uteis: %d" % len(zero))
    for n, x in zero:
        print("       %-26s %s  %s  publicado==prazo em %s"
              % ((x.get("municipio") or "?")[:26], x.get("uf"),
                 (x.get("modalidade") or "")[:20], str(x.get("fim_prazo"))[:10]))
    print()
    print("  NAO CONCLUA ILEGALIDADE DISSO. `publicado_em` e a data do registro")
    print("  no PNCP, nao a data da divulgacao do edital. Zero dias uteis quase")
    print("  certamente significa CADASTRO TARDIO: o edital saiu no diario")
    print("  semanas antes e o registro entrou no PNCP no dia da sessao.")
    print("  Para a lei, o prazo correu. Para nos, nao existiu -- e e por isso")
    print("  que o numero importa mesmo sem dizer nada sobre legalidade.")
    print()

    por = {}
    for n, x in pares:
        por.setdefault((x.get("modalidade") or "?")[:28], []).append(n)
    print("  %-30s %5s %8s %5s" % ("modalidade", "n", "mediana", "min"))
    print("  " + "-" * 56)
    for k, vs in sorted(por.items(), key=lambda t: -len(t[1])):
        print("  %-30s %5d %8.0f %5d" % (k, len(vs), st.median(vs), min(vs)))

    dest = os.path.join(SAIDAS, "_antecedencia.json")
    io.open(dest, "w", encoding="utf-8").write(json.dumps({
        "medido_em": dt.date.today().isoformat(),
        "n": len(pares), "sem_data": sem_data,
        "dias_uteis": {"min": v[0], "p25": v[len(v) // 4],
                       "mediana": st.median(v), "p75": v[3 * len(v) // 4],
                       "max": v[-1]},
        "cobertura": {str(n): sum(1 for x in v if x >= n)
                      for n in (1, 3, 5, 10, 15, 20)},
        "zero_dias": [{"municipio": x.get("municipio"), "uf": x.get("uf"),
                       "controle": x.get("controle")} for _, x in zero],
    }, ensure_ascii=False, indent=1))
    print("\n  gravado em saidas/_antecedencia.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
