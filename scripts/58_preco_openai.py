# -*- coding: utf-8 -*-
"""
Quanto custa mil tokens do OpenAI -- derivado da FATURA, nao da tabela.

    python 58_preco_openai.py

NAO CHAMA MODELO. NAO CHAMA REDE. Le `saidas/_custo_openai.json`, que o
32_custo_real.py ja gravou a partir de dois endpoints DIFERENTES da conta:

    /v1/organization/costs           -> dolares COBRADOS, por line_item
    /v1/organization/usage/*         -> tokens CONSUMIDOS, por modelo

O preco por milhao sai da divisao de um pelo outro. Como numerador e
denominador vem de fontes independentes, a divisao e medicao -- e nao a
aritmetica circular que derrubou o 55 (R$ 1,00 por servidor) e o 57
(2.500 caracteres por pagina) hoje mais cedo.

POR QUE ISSO ESTAVA EM ABERTO
  O catalogo em `fopa/modelos.py` tinha os tres modelos da Claude com preco
  de tabela conferido e NENHUM do OpenAI -- por regra explicita do projeto:
  nao escrever valor sem fonte. Havia tokens medidos e nenhum R$. Agora ha
  fonte, e ela e melhor que a tabela: e o que a conta pagou.
"""
from __future__ import annotations

import io
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

FONTE = os.path.join(RAIZ, "saidas", "_custo_openai.json")
DESTINO = os.path.join(RAIZ, "saidas", "_preco_openai.json")

# Tabela oficial, consultada em 23/09/2026 em
# https://developers.openai.com/api/docs/pricing (standard processing).
# Esta aqui SO para conferencia: o numero que o projeto usa e o derivado da
# fatura. Se os dois divergirem, quem manda e a fatura -- e a divergencia
# vira aviso, porque significa desconto, promocao ou tabela desatualizada.
TABELA = {
    "gpt-6-sol":   {"entrada":  2.00, "cache_leitura": 0.20, "saida": 10.00},
    "gpt-6-astra": {"entrada": 10.00, "cache_leitura": 1.00, "saida": 50.00},
    "gpt-6-luna":  {"entrada":  0.10, "cache_leitura": 0.01, "saida":  0.50},
    "gpt-5.6-sol": {"entrada":  4.00, "cache_leitura": 0.40, "saida": 20.00},
}

# nome do balde na fatura -> nome do contador de tokens no uso
BALDES = [
    ("input",        "input_uncached_tokens",   "entrada"),
    ("cache writes", "input_cache_write_tokens", "cache_escrita"),
    ("cached input", "input_cached_tokens",     "cache_leitura"),
    ("output",       "output_tokens",           "saida"),
]

MIN_TOKENS = 1000     # abaixo disso o arredondamento da fatura domina


def main() -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if not os.path.exists(FONTE):
        print("falta saidas/_custo_openai.json — rode antes:")
        print("    python 32_custo_real.py --openai")
        return 1
    d = json.load(io.open(FONTE, encoding="utf-8"))
    uso, custo = d.get("por_modelo") or {}, d.get("custo_por_modelo") or {}

    print("=" * 96)
    print("  PREÇO POR MILHÃO DE TOKENS — derivado da fatura de %s" % d.get("gerado_em"))
    print("  fatura US$ %.4f em %d dias · fonte: /v1/organization/costs"
          % (d.get("total_usd") or 0.0, d.get("dias") or 0))
    print("=" * 96)
    print()

    derivado, avisos = {}, []
    for modelo in sorted(uso):
        u, c = uso[modelo], custo.get(modelo) or {}
        print("  %s" % modelo)
        linha = {}
        for balde, campo_tok, nome in BALDES:
            tok, usd = u.get(campo_tok) or 0, c.get(balde) or 0.0
            if tok < MIN_TOKENS or usd <= 0:
                print("     %-14s %10d tok · US$ %9.6f   (amostra pequena demais)"
                      % (nome, tok, usd))
                continue
            p = usd / tok * 1_000_000
            linha[nome] = round(p, 4)
            of = (TABELA.get(modelo) or {}).get(nome)
            marca = ""
            if of is not None:
                dif = abs(p - of) / of * 100.0
                marca = ("confere com a tabela" if dif < 1.0
                         else "DIVERGE da tabela (US$ %.2f)" % of)
                if dif >= 1.0:
                    avisos.append("%s/%s: fatura US$ %.2f, tabela US$ %.2f"
                                  % (modelo, nome, p, of))
            print("     %-14s %10d tok · US$ %9.6f = US$ %8.4f /M  %s"
                  % (nome, tok, usd, p, marca))
        # A RAZAO QUE A TABELA NAO PUBLICA.
        # A tabela oficial lista entrada, cache de LEITURA e saida. O preco da
        # ESCRITA no cache nao esta la -- so aparece na fatura. Como o balde de
        # entrada nao-cacheada e pequeno demais em todos os quatro modelos
        # (18 a 330 tokens, onde o arredondamento da fatura domina), a base da
        # razao e o preco de entrada DA TABELA. Continua sendo duas fontes:
        # numerador da fatura, denominador da tabela.
        base = linha.get("entrada")
        de_onde = "fatura"
        if base is None:
            base = (TABELA.get(modelo) or {}).get("entrada")
            de_onde = "tabela"
        if base and "cache_escrita" in linha:
            r = linha["cache_escrita"] / base
            linha["cache_escrita_sobre_entrada"] = round(r, 4)
            print("     escrever no cache custa %.2f× a entrada"
                  "  (entrada de US$ %.2f, da %s)" % (r, base, de_onde))
        derivado[modelo] = linha
        print()

    # ----------------------------------------------------- economia do cache
    esc = sum((uso[m].get("input_cache_write_tokens") or 0) for m in uso)
    lei = sum((uso[m].get("input_cached_tokens") or 0) for m in uso)
    usd_esc = sum((custo.get(m) or {}).get("cache writes", 0.0) for m in uso)
    usd_lei = sum((custo.get(m) or {}).get("cached input", 0.0) for m in uso)
    print("-" * 96)
    print("  O CACHE ESTÁ PAGANDO OU CUSTANDO?")
    print("     escrito no cache ..... %9d tokens · US$ %.4f" % (esc, usd_esc))
    print("     lido do cache ........ %9d tokens · US$ %.4f" % (lei, usd_lei))
    if esc:
        print("     reaproveitamento ..... %.1f%% do que foi escrito"
              % (100.0 * lei / esc))
        # escrever custa 1,25x; ler custa 0,10x. O extra da escrita e 0,25 por
        # token escrito; cada token lido economiza 0,90. Empata em 27,8%.
        print("     ponto de equilíbrio .. 27,8%  (escrita custa +0,25×,"
              " leitura economiza 0,90×)")
        if lei < 0.278 * esc:
            # em dolares, modelo a modelo -- 0,25x extra por token escrito,
            # 0,90x economizado por token lido, no preco de entrada de cada um
            perda_usd = 0.0
            for m in uso:
                pe = ((derivado.get(m) or {}).get("entrada")
                      or (TABELA.get(m) or {}).get("entrada") or 0.0)
                perda_usd += (0.25 * (uso[m].get("input_cache_write_tokens") or 0)
                              - 0.90 * (uso[m].get("input_cached_tokens") or 0)
                              ) * pe / 1_000_000
            print()
            print("     ABAIXO DO EQUILÍBRIO: o cache ENCARECEU a conta.")
            print("     Custou US$ %.4f a mais do que economizou — %.1f%% da fatura."
                  % (perda_usd, 100.0 * perda_usd / (d.get("total_usd") or 1)))
            print("     Causa provável: cada pergunta abre um prompt novo, e o")
            print("     edital é escrito no cache sem nunca ser relido antes de")
            print("     a janela de 5 minutos expirar.")
    print("-" * 96)
    print()
    if avisos:
        print("  DIVERGÊNCIAS entre fatura e tabela oficial:")
        for a in avisos:
            print("     %s" % a)
    else:
        print("  Todos os preços derivados conferem com a tabela oficial de")
        print("  23/09/2026 (developers.openai.com/api/docs/pricing), dentro de 1%.")
        print("  Duas fontes independentes dando o mesmo número — é isso que")
        print("  separa medição de coincidência.")

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps(
        {"derivado_de": os.path.basename(FONTE), "fatura_em": d.get("gerado_em"),
         "fonte_dolares": "/v1/organization/costs (group_by=line_item)",
         "fonte_tokens": "/v1/organization/usage/completions (group_by=model)",
         "tabela_oficial": "https://developers.openai.com/api/docs/pricing"
                           " consultada em 2026-09-23",
         "usd_por_milhao": derivado, "tabela": TABELA,
         "cache": {"escritos": esc, "lidos": lei,
                   "usd_escrita": round(usd_esc, 6),
                   "usd_leitura": round(usd_lei, 6),
                   "reaproveitamento": round(100.0 * lei / esc, 1) if esc else None},
         "divergencias": avisos}, ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_preco_openai.json · custo R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
