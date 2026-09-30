# -*- coding: utf-8 -*-
"""
Mede a COBERTURA REAL do Querido Diario contra o mercado do projeto, nao contra o
Brasil.

O numero que circulava na nota era "mais de 350 municipios de 5.570", ~6%. Esse
denominador esta errado para a decisao que a fase 2 precisa tomar: nao
licitamos folha em 5.570 municipios, licitamos onde ha licitacao de folha. A
pergunta util e quantos dos municipios do corpus do PROJETO o Querido Diario cobre.

Sem chave, sem custo. A API publica devolve os 5.570 territorios com um campo
`level` e uma `availability_date` que separam coberto de listado.

    python 48_querido_diario.py
"""
import io
import json
import os
import sys
import time
import gzip
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDAS = os.path.join(RAIZ, "saidas")
API = "https://queridodiario.ok.org.br/api/cities"
# O IBGE usa o MESMO codigo de territorio que o Querido Diario. Cruzar pelo
# codigo evita casar nome, que erra em "Santo Antonio do Pinhal" e amigos.
IBGE = ("https://servicodados.ibge.gov.br/api/v3/agregados/4714/periodos/2022"
        "/variaveis/93?localidades=N6[all]")
# Art. 176 da Lei 14.133/2021: municipio de ate 20 mil habitantes pode
# publicar SO em diario oficial ate 01/04/2027. E esse o furo que a fase 2
# existe para tapar -- entao e essa a faixa que interessa medir.
TETO_ART_176 = 20000
# Instantaneos em disco. O Querido Diario devolveu 503 no meio desta propria
# medicao, minutos depois de responder duas vezes. Uma medicao que so existe
# quando a API de terceiro esta de pe no instante certo nao e reproduzivel --
# e a reprodutibilidade e o ponto do projeto inteiro. Entao o que veio da rede
# fica gravado, e `--rede` e o que forca buscar de novo.
CACHE_QD = "_cache_querido_diario.json"
CACHE_IBGE = "_cache_ibge_populacao.json"


def baixar() -> list[dict]:
    # Tres tentativas com espera crescente. O Querido Diario devolveu 503 no
    # meio desta propria medicao -- um numero de cobertura que depende de a API
    # estar de pe no instante certo nao e um numero, e um sorteio.
    p = os.path.join(SAIDAS, CACHE_QD)
    if not FORCAR_REDE and _cache(CACHE_QD):
        d = json.load(io.open(p, encoding="utf-8"))
        print("  fonte: instantaneo local de %s (use --rede para buscar)"
              % d.get("baixado_em", "?"))
        return d["cities"]
    erro = None
    for tentativa in range(3):
        try:
            d = _json(API)
            d["baixado_em"] = time.strftime("%Y-%m-%d %H:%M")
            io.open(p, "w", encoding="utf-8").write(
                json.dumps(d, ensure_ascii=False))
            print("  fonte: API, instantaneo gravado em saidas/%s" % CACHE_QD)
            return d["cities"]
        except Exception as e:                       # noqa: BLE001
            erro = e
            if tentativa < 2:
                espera = 5 * (tentativa + 1)
                print("  QD indisponivel (%s) — %ds e tento de novo"
                      % (type(e).__name__, espera))
                time.sleep(espera)
    if _cache(CACHE_QD):
        d = json.load(io.open(p, encoding="utf-8"))
        print("  API fora (%s) — usando o instantaneo de %s"
              % (type(erro).__name__, d.get("baixado_em", "?")))
        return d["cities"]
    raise erro


def _cache(nome: str):
    p = os.path.join(SAIDAS, nome)
    return p if os.path.isfile(p) else None


def _json(url: str, timeout: int = 60) -> dict:
    """
    O IBGE devolve gzip MESMO sem `Accept-Encoding: gzip`, e o urllib nao
    descomprime sozinho. A armadilha nao e o erro -- e que `latin-1` decodifica
    bytes comprimidos sem reclamar e devolve bytes que parecem texto. Um fallback
    de encoding "para garantir" transformaria isso numa corrupcao silenciosa.
    Entao: gzip pelo header OU pelo magic number, e utf-8 sem plano B.
    """
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        bruto = r.read()
        gz = (r.headers.get("Content-Encoding") == "gzip")
    if gz or bruto[:2] == bytes((0x1F, 0x8B)):
        bruto = gzip.decompress(bruto)
    return json.loads(bruto.decode("utf-8"))


def populacao() -> dict[str, int]:
    p = os.path.join(SAIDAS, CACHE_IBGE)
    if not FORCAR_REDE and _cache(CACHE_IBGE):
        return json.load(io.open(p, encoding="utf-8"))["pop"]
    d = _json(IBGE, timeout=90)
    fora = {}
    for s_ in d[0]["resultados"][0]["series"]:
        v = (s_.get("serie") or {}).get("2022")
        if v and v.isdigit():
            fora[s_["localidade"]["id"]] = int(v)
    io.open(p, "w", encoding="utf-8").write(json.dumps(
        {"baixado_em": time.strftime("%Y-%m-%d %H:%M"), "pop": fora},
        ensure_ascii=False))
    return fora


def coberto(c: dict) -> bool:
    """Coberto = tem data de disponibilidade. `level` sozinho nao basta."""
    return bool((c.get("availability_date") or "").strip())


def municipios_do_corpus() -> list[tuple[str, str]]:
    p = os.path.join(SAIDAS, "_corpus_escopo.json")
    if not os.path.isfile(p):
        return []
    d = json.load(io.open(p, encoding="utf-8"))
    itens = d.get("registros") or []
    fora = []
    for x in itens:
        # so o que esta DENTRO do escopo: o corpus guarda tambem o que o filtro
        # recusou, e medir cobertura contra o descartado inflaria o denominador.
        if x.get("dentro") is False:
            continue
        m = (x.get("municipio") or "").strip()
        uf = (x.get("uf") or "").strip().upper()
        if m:
            fora.append((m, uf))
    return fora


def normalizar(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().replace("'", "").replace("-", " ").split())


FORCAR_REDE = "--rede" in sys.argv


def main() -> int:
    t = time.time()
    print("=" * 96)
    print("  QUERIDO DIARIO — cobertura contra o NOSSO mercado")
    print("=" * 96)
    cidades = baixar()
    cob = [c for c in cidades if coberto(c)]
    print("  territorios listados na API ..... %d" % len(cidades))
    print("  com diario disponivel ........... %d (%.1f%% do Brasil)"
          % (len(cob), 100.0 * len(cob) / len(cidades)))
    print("  niveis: %s" % dict(Counter(c.get("level") for c in cob)))
    print()

    indice = {}
    for c in cob:
        indice[(normalizar(c["territory_name"]), c["state_code"])] = c

    corpus = municipios_do_corpus()
    if not corpus:
        print("  (sem corpus local — a parte que importa nao pode ser medida)")
        return 0

    unicos = sorted(set(corpus))
    achados, faltando = [], []
    for m, uf in unicos:
        c = indice.get((normalizar(m), uf))
        (achados if c else faltando).append((m, uf, c))

    print("  municipios distintos no corpus .. %d (em %d licitacoes)"
          % (len(unicos), len(corpus)))
    print("  COBERTOS pelo Querido Diario .... %d (%.1f%%)"
          % (len(achados), 100.0 * len(achados) / len(unicos)))
    print("  fora da cobertura ............... %d" % len(faltando))
    print()

    # por UF, porque a cobertura do projeto e desigual por estado
    por_uf = {}
    for m, uf in unicos:
        d = por_uf.setdefault(uf, [0, 0])
        d[1] += 1
        if indice.get((normalizar(m), uf)):
            d[0] += 1
    print("  %-4s %6s %6s  %s" % ("UF", "cob.", "total", "cobertura"))
    print("  " + "-" * 60)
    for uf, (a, b) in sorted(por_uf.items(), key=lambda x: (-x[1][1], x[0])):
        barra = "#" * int(round(20.0 * a / b))
        print("  %-4s %6d %6d  %-20s %.0f%%" % (uf, a, b, barra, 100.0 * a / b))
    print()
    if faltando:
        print("  sem diario no Querido Diario (primeiros 20):")
        for m, uf, _ in faltando[:20]:
            print("     %s/%s" % (m, uf))

    # ---------------------------------------------------------- art. 176
    # A pergunta que decide a fase 2 nao e "quantos municipios o Querido Diario
    # cobre" -- e "quantos dos municipios que a lei DISPENSA de publicar no
    # PNCP ele cobre". Sao coisas muito diferentes, e so a segunda e o furo.
    print()
    print("=" * 96)
    print("  A FAIXA DO ART. 176 — municipios de ate %s habitantes" % f"{TETO_ART_176:,}".replace(",", "."))
    print("=" * 96)
    try:
        pop = populacao()
    except Exception as e:
        print("  IBGE fora do ar (%s) — a parte do art. 176 fica sem medir"
              % type(e).__name__)
        pop = {}
    if pop:
        peq = {k for k, v in pop.items() if v <= TETO_ART_176}
        cob_ids = {c["territory_id"] for c in cob}
        peq_cob = peq & cob_ids
        print("  municipios do Brasil ............ %d" % len(pop))
        print("  na faixa do art. 176 ............ %d (%.1f%% do pais)"
              % (len(peq), 100.0 * len(peq) / len(pop)))
        print("  DESSES, com diario no QD ........ %d (%.1f%% da faixa)"
              % (len(peq_cob), 100.0 * len(peq_cob) / len(peq)))
        gr_cob = cob_ids - peq
        print("  e dos 510 cobertos pelo QD:")
        print("     na faixa do art. 176 ......... %d (%.0f%%)"
              % (len(peq_cob), 100.0 * len(peq_cob) / max(1, len(cob_ids))))
        print("     acima de %s habitantes ..... %d (%.0f%%)"
              % (f"{TETO_ART_176:,}".replace(",", "."), len(gr_cob),
                 100.0 * len(gr_cob) / max(1, len(cob_ids))))
        print()
        print("  LEITURA. O desvio existe mas e moderado: municipio de ate 20 mil")
        print("  e %.1f%% do Brasil e %.0f%% do que o QD cobre. Nao e 'so cidade"
              % (100.0 * len(peq) / len(pop), 100.0 * len(peq_cob) / max(1, len(cob_ids))))
        print("  grande' -- e tambem nao e a faixa que a lei dispensa.")
        print()
        print("  O numero que decide a fase 2 e o outro: dos %d municipios que o"
              % len(peq))
        print("  art. 176 dispensa de publicar no PNCP ate 01/04/2027, o Querido")
        print("  Diario cobre %d. Sao %.1f%%." % (len(peq_cob), 100.0 * len(peq_cob) / len(peq)))
        print("  Esse e o TETO do que a fase 2 pode recuperar do furo legal, e ele")
        print("  vale ate a data em que o furo fecha sozinho.")

    # -------------------------------------------------- ADR-007, item 1
    # "Quantos municipios <= 20 mil ja publicam no PNCP voluntariamente?"
    # Todo municipio do corpus publicou no PNCP -- e assim que o
    # encontramos. Entao basta olhar quantos deles estao na faixa dispensada:
    # cada um e um caso de adesao voluntaria, porque a lei nao os obriga ate
    # 01/04/2027.
    if pop:
        # o Querido Diario serve de indice nome->codigo IBGE, que o corpus
        # nao guarda. Nao e a fonte do dado; e so a ponte entre os dois.
        cod = {(normalizar(c["territory_name"]), c["state_code"]): c["territory_id"]
               for c in cidades}
        peq_n = gr_n = sem_cod = 0
        exemplos = []
        for m, uf in unicos:
            k = cod.get((normalizar(m), uf))
            p_ = pop.get(k) if k else None
            if p_ is None:
                sem_cod += 1
            elif p_ <= TETO_ART_176:
                peq_n += 1
                exemplos.append((p_, m, uf))
            else:
                gr_n += 1
        print()
        print("=" * 96)
        print("  ADESAO VOLUNTARIA — municipios do corpus na faixa dispensada")
        print("=" * 96)
        conhecidos = peq_n + gr_n
        print("  municipios do corpus com populacao conhecida .. %d de %d"
              % (conhecidos, len(unicos)))
        if sem_cod:
            print("  sem casamento de nome com o IBGE ............... %d" % sem_cod)
        if conhecidos:
            print("  na faixa do art. 176 (<= %d hab) ............... %d (%.1f%%)"
                  % (TETO_ART_176, peq_n, 100.0 * peq_n / conhecidos))
            print("  acima do teto ................................. %d" % gr_n)
            print()
            print("  TODOS esses publicaram no PNCP -- e assim que os achamos.")
            print("  Os %d da faixa dispensada nao eram obrigados a isso ate" % peq_n)
            print("  01/04/2027, e publicaram mesmo assim.")
            print()
            print("  CUIDADO COM A INFERENCIA. Esta amostra so contem quem")
            print("  PUBLICOU -- os que usaram a dispensa sao invisiveis aqui,")
            print("  por definicao. O numero NAO diz que a maioria dos pequenos")
            print("  publica; diz que metade do que enxergamos e pequeno, e que")
            print("  o art. 176 nao torna esse municipio invisivel por si so.")
            print("  Quantos ficaram de fora e exatamente o que este metodo nao")
            print("  consegue medir -- a mesma armadilha do 41_censo_pdf.")
            exemplos.sort()
            print()
            print("  os 8 menores que ja publicam no PNCP:")
            for p_, m, uf in exemplos[:8]:
                print("     %-30s %s  %6d hab" % (m[:30], uf, p_))

    dest = os.path.join(SAIDAS, "_querido_diario.json")
    io.open(dest, "w", encoding="utf-8").write(json.dumps({
        "medido_em": time.strftime("%Y-%m-%d %H:%M"),
        "brasil": {"listados": len(cidades), "cobertos": len(cob)},
        "corpus": {"municipios": len(unicos), "licitacoes": len(corpus),
                   "cobertos": len(achados)},
        "por_uf": {k: {"cobertos": v[0], "total": v[1]} for k, v in por_uf.items()},
        "descobertos": [{"municipio": m, "uf": uf} for m, uf, _ in faltando],
        "art_176": ({"teto": TETO_ART_176, "na_faixa": len(peq),
                     "na_faixa_cobertos": len(peq_cob),
                     "cobertos_acima_do_teto": len(gr_cob)} if pop else None),
    }, ensure_ascii=False, indent=1))
    print("  gravado em saidas/_querido_diario.json · %.1fs" % (time.time() - t))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
