# -*- coding: utf-8 -*-
"""
Custo REAL cobrado pela OpenAI, e o preço efetivo por modelo.

    python 32_custo_real.py                 relatório dos últimos 7 dias
    python 32_custo_real.py --dias 30
    python 32_custo_real.py --calibrar      resolve o preço unitário (gasta centavos)

POR QUE ISTO EXISTE
  Porque "quanto custou" tinha duas respostas no projeto e nenhuma era medida:
  a tabela de preço do fornecedor (que não tínhamos) e a estimativa do próprio
  pipeline (que depende dela). Este script traz a terceira, que é a única que
  vale: **o que foi cobrado**.

  Com ela o sistema passa a conferir a própria estimativa contra a fatura —
  a mesma ideia da ancoragem, aplicada a dinheiro. Ver [[ADR-004 Evidência
  obrigatória]]: uma afirmação sem evidência não entra, e isso vale para custo.

A CHAVE É OUTRA, DE PROPÓSITO
  `OPENAI_ADMIN_KEY`, escopo `api.usage.read`. A chave de projeto não alcança
  faturamento (403, `Missing scopes`) — e é bom que não alcance. A admin lê
  dados da organização inteira, então só este script a usa.

O QUE A API DE USO REVELOU, E QUE O PIPELINE NÃO VIA
  O input se decompõe em TRÊS e não em dois:

      input_uncached_tokens       nunca vistos
      input_cache_write_tokens    gravados no cache  (custam MAIS que o normal)
      input_cached_tokens         lidos do cache     (custam MUITO menos)

  O pipeline tratava quase tudo como entrada simples. Na primeira medição real,
  **122.407 dos 177.104 tokens de entrada eram cache WRITE** e apenas 321 eram
  não-cacheados — ou seja, a parcela chamada de "entrada" era, quase toda,
  a mais cara das três.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import modelos, segredos                                # noqa: E402

BASE = "https://api.openai.com/v1/organization"
DESTINO = os.path.join(RAIZ, "saidas", "_custo_openai.json")


def barra(t: str) -> None:
    print("\n" + "=" * 92 + "\n  %s\n" % t + "=" * 92)


def _pegar(url: str, chave: str, timeout: int = 40) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": "Bearer %s" % chave})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def custos(chave: str, dias: int) -> tuple[float, list[dict]]:
    ini = int(time.time()) - 86400 * dias
    d = _pegar("%s/costs?start_time=%d&limit=31" % (BASE, ini), chave)
    total, linhas = 0.0, []
    for b in d.get("data", []):
        for r in b.get("results", []):
            v = (r.get("amount") or {}).get("value") or 0.0
            total += v
            linhas.append(dict(dia=b.get("start_time_iso", "")[:10], usd=v,
                               item=r.get("line_item")))
    return total, linhas


def uso(chave: str, dias: int) -> dict[str, dict]:
    ini = int(time.time()) - 86400 * dias
    d = _pegar("%s/usage/completions?start_time=%d&bucket_width=1d"
               "&group_by=model&limit=31" % (BASE, ini), chave)
    por_modelo: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for b in d.get("data", []):
        for r in b.get("results", []):
            m = r.get("model") or "?"
            for campo in ("num_model_requests", "input_tokens", "output_tokens",
                          "input_cached_tokens", "input_cache_write_tokens",
                          "input_uncached_tokens"):
                por_modelo[m][campo] += r.get(campo) or 0
    return {k: dict(v) for k, v in por_modelo.items()}


def n(x: int) -> str:
    return f"{x:,}".replace(",", ".")


def relatorio(chave: str, dias: int) -> dict:
    total, linhas = custos(chave, dias)
    por_modelo = uso(chave, dias)

    barra("CUSTO REAL — últimos %d dias" % dias)
    print("  fonte: /v1/organization/costs — o que foi COBRADO, não estimado\n")
    for l in sorted(linhas, key=lambda x: x["dia"]):
        print("  %s   US$ %8.4f   %s" % (l["dia"], l["usd"], l["item"] or ""))
    print("\n  TOTAL       US$ %8.4f   (R$ %.2f a %.2f/USD)"
          % (total, total * modelos.USD_BRL, modelos.USD_BRL))

    barra("USO POR MODELO")
    for m, u in sorted(por_modelo.items()):
        ent = u.get("input_tokens", 0)
        print("  %s" % m)
        print("    requisições ....... %d" % u.get("num_model_requests", 0))
        print("    entrada total ..... %s" % n(ent))
        for campo, rotulo in (("input_uncached_tokens", "não cacheada"),
                              ("input_cache_write_tokens", "gravação de cache"),
                              ("input_cached_tokens", "leitura de cache")):
            v = u.get(campo, 0)
            pct = (100.0 * v / ent) if ent else 0
            print("       %-20s %12s  (%4.1f%%)" % (rotulo, n(v), pct))
        print("    saída ............. %s" % n(u.get("output_tokens", 0)))

    # ------------------------------------------------ preço efetivo
    barra("PREÇO EFETIVO — o que dá para afirmar, e o que não dá")
    if len(por_modelo) == 1 and total > 0:
        m, u = next(iter(por_modelo.items()))
        reqs = u.get("num_model_requests", 0) or 1
        tot_tok = u.get("input_tokens", 0) + u.get("output_tokens", 0)
        print("  Um só modelo no período, então o custo é todo dele.\n")
        print("    US$ %.4f por requisição" % (total / reqs))
        print("    US$ %.4f por milhão de tokens (entrada+saída misturadas)"
              % (total / tot_tok * 1_000_000 if tot_tok else 0))
        print("""
  > Este é um preço MISTURADO, não o preço unitário. Ele depende da proporção
  > entre entrada, saída e cache desta amostra — troque a proporção e ele muda.
  > Serve para orçar execuções PARECIDAS com estas, e não para preencher
  > FOPA_PRECO_OPENAI_ENTRADA/SAIDA, que são preços unitários.
  >
  > Para resolver os unitários: `python 32_custo_real.py --calibrar`""")
    else:
        print("  %d modelos no período — e o custo SEPARA entre eles." % len(por_modelo))
        print("  (`group_by=line_item`: o line_item é \"<modelo>, <tipo de token>\")\n")
        porm = custo_por_modelo(dias, chave)
        if porm:
            print("  %-24s %10s   %s" % ("modelo", "total", "decomposição"))
            print("  " + "-" * 84)
            for m, tipos in sorted(porm.items(), key=lambda x: -sum(x[1].values())):
                tot_m = sum(tipos.values())
                dec = " · ".join("%s %.4f" % (k, v)
                                 for k, v in sorted(tipos.items(), key=lambda x: -x[1])
                                 if v > 0)
                print("  %-24s US$ %7.4f   %s" % (m[:24], tot_m, dec[:48]))
            print("  " + "-" * 84)
            print("  %-24s US$ %7.4f"
                  % ("TOTAL", sum(sum(t.values()) for t in porm.values())))

    saida = {"gerado_em": time.strftime("%Y-%m-%d %H:%M"), "dias": dias,
             "total_usd": total, "por_dia": linhas, "por_modelo": por_modelo,
             "custo_por_modelo": custo_por_modelo(dias, chave)}
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    json.dump(saida, io.open(DESTINO, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n  gravado: %s" % os.path.relpath(DESTINO, RAIZ))
    return saida


def calibrar(chave_admin: str, modelo: str) -> int:
    """
    Resolve o preço unitário por um experimento controlado.

    DUAS INCÓGNITAS, DUAS EQUAÇÕES.
    O custo de uma chamada é `entrada·X + saída·Y`. Uma única execução não
    separa X de Y — qualquer par (X, Y) que dê o mesmo total serve. Então
    fazemos DUAS chamadas com proporções opostas:

        A   entrada grande, saída mínima   -> o total é quase só X
        B   entrada mínima, saída grande   -> o total é quase só Y

    e lemos o custo de cada uma na própria API de faturamento. É o mesmo
    princípio de qualquer calibração: variar um fator de cada vez.

    CUSTO: centavos. E ele é medido, não estimado — é o ponto do exercício.
    """
    import openai

    cliente = openai.OpenAI(api_key=segredos.obter("OPENAI_API_KEY"), max_retries=0)

    def custo_agora() -> float:
        t, _ = custos(chave_admin, 1)
        return t

    def medir(rotulo: str, entrada: str, teto: int, effort: str) -> dict:
        antes = custo_agora()
        r = cliente.responses.create(model=modelo, input=entrada,
                                     max_output_tokens=teto,
                                     reasoning={"effort": effort})
        u = r.usage
        det_in = getattr(u, "input_tokens_details", None)
        time.sleep(20)                      # a contabilidade não é instantânea
        depois = custo_agora()
        d = dict(rotulo=rotulo,
                 entrada=getattr(u, "input_tokens", 0),
                 cache=getattr(det_in, "cached_tokens", 0) or 0,
                 saida=getattr(u, "output_tokens", 0),
                 delta=depois - antes)
        print("  %-28s entrada %7s  saída %7s  ΔUS$ %.6f"
              % (rotulo, n(d["entrada"]), n(d["saida"]), d["delta"]))
        return d

    barra("CALIBRAÇÃO — %s" % modelo)
    print("  Duas chamadas com proporções opostas, e o custo lido na fatura.")
    print("  Custo do experimento: centavos.\n")

    # texto longo e SEM sentido repetido, para não ser cacheado de execução
    # anterior — cache barateia a entrada e estragaria a medição de X.
    import random
    palavras = ["folha", "cessão", "onerosa", "servidores", "município",
                "instituição", "financeira", "edital", "pregão", "contrato"]
    longo = " ".join(random.choice(palavras) for _ in range(8000))

    a = medir("A entrada grande", longo + "\n\nResponda apenas: ok", 16, "low")
    b = medir("B saída grande", "Escreva um texto longo sobre licitações.", 3000, "low")

    # entrada·X + saída·Y = delta, para cada uma
    import itertools
    m11, m12, r1 = a["entrada"], a["saida"], a["delta"]
    m21, m22, r2 = b["entrada"], b["saida"], b["delta"]
    det = m11 * m22 - m12 * m21
    print()
    if abs(det) < 1e-9 or r1 <= 0 or r2 <= 0:
        print("  Não deu para resolver: alguma medição voltou zero.")
        print("  A contabilidade da OpenAI pode levar minutos — tente de novo.")
        return 1
    X = (r1 * m22 - m12 * r2) / det * 1_000_000
    Y = (m11 * r2 - r1 * m21) / det * 1_000_000
    print("  RESOLVIDO:")
    print("    entrada  US$ %.2f por milhão de tokens" % X)
    print("    saída    US$ %.2f por milhão de tokens" % Y)
    if X <= 0 or Y <= 0:
        print("\n  Valor negativo = ruído maior que o sinal. Repita com")
        print("  chamadas maiores, ou confirme na tabela oficial.")
        return 1
    print("\n  Para gravar, ponha no .env:")
    print("      FOPA_PRECO_OPENAI_ENTRADA=%.2f" % X)
    print("      FOPA_PRECO_OPENAI_SAIDA=%.2f" % Y)
    return 0


def custo_por_modelo(dias: int, chave: str) -> dict:
    """
    O que foi COBRADO, separado por modelo.

    A CHAVE ESTÁ NO `group_by=line_item`, e isso levou tempo para aparecer.
      Este script dizia, quando via mais de um modelo no período:

        "N modelos no período — o custo agregado não separa entre eles.
         Rode com --dias menor, num período de um modelo só."

      Era falso, e por isso o item "custo de quatro dos seis ainda não isolado
      na fatura" ficou meses em aberto esperando um período limpo que nunca ia
      existir, porque os benchmarks rodam os modelos em sequência no mesmo dia.

      O endpoint `/v1/organization/costs` recusa `group_by=model` com HTTP 400
      e recusa `bucket_width=1h` com HTTP 400 — daí a conclusão de que não
      dava. Mas aceita `group_by=line_item`, e o `line_item` vem no formato
      **`"<modelo>, <tipo de token>"`**:

          gpt-5.6-sol, cache writes      US$ 1.0195
          gpt-5.6-sol, output            US$ 0.9464
          gpt-6-astra, cache writes      US$ 1.1859

      Basta cortar na vírgula. A informação sempre esteve lá, num campo cujo
      nome não prometia conter o modelo.

    Lição: um `400` em `group_by=model` não significa "a API não separa por
    modelo". Significa que esse parâmetro não existe. São coisas diferentes, e
    confundi-las custou uma pendência que parecia depender de dado externo.
    """
    import collections
    ini = int(time.time()) - dias * 86400
    d = _pegar("%s/costs?start_time=%d&bucket_width=1d&group_by=line_item&limit=31"
               % (BASE, ini), chave)
    por = collections.defaultdict(lambda: collections.defaultdict(float))
    for b in (d.get("data") or []):
        for x in (b.get("results") or []):
            li = str(x.get("line_item") or "")
            modelo, _, tipo = li.partition(",")
            valor = (x.get("amount") or {}).get("value", 0) or 0
            por[modelo.strip()][tipo.strip() or "(sem tipo)"] += valor
    return {m: dict(t) for m, t in por.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Custo real cobrado pela OpenAI")
    ap.add_argument("--dias", type=int, default=7)
    ap.add_argument("--calibrar", action="store_true",
                    help="experimento controlado para o preço unitário (centavos)")
    a = ap.parse_args()

    chave = segredos.obter("OPENAI_ADMIN_KEY")
    if not chave:
        print("OPENAI_ADMIN_KEY não definida em projeto-fopa/.env")
        print("A chave de projeto NÃO serve: faturamento exige escopo api.usage.read.")
        return 3

    try:
        if a.calibrar:
            return calibrar(chave, modelos.MODELO_OPENAI)
        relatorio(chave, a.dias)
    except urllib.error.HTTPError as e:
        print("falha: %s | %s" % (e, e.read().decode()[:200]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
