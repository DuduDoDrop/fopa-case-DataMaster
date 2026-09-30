# -*- coding: utf-8 -*-
"""
Analytics do histórico de compra e venda da folha.

Visão geral das instituições financeiras que compram folha: valores homologados, número de licitações
compradas, a série mensal de compras por instituição e, na mesma página, os editais sem comprador que
voltaram a ser publicados.

Tudo sai das tabelas que o coletor enche a partir da API do PNCP (db/027, api/historico_pncp.py) —
nenhum edital, nenhum modelo. Aqui, diferente das telas de licitações, o que está fora do escopo de
folha VALE (`escopo=todos`, a caixa "mostrar fora do escopo" da página).

Regras que moram aqui, com o porquê:
  · BANCO é o CNPJ-raiz (8 primeiros dígitos): as filiais de um banco são o mesmo comprador; o nome
    mostrado é o mais frequente entre os resultados dele.
  · Resultado com `cancelado_em` (homologação desfeita — Triunfo Potiguar/RN) não é compra.
  · REPUBLICAÇÃO não tem campo no PNCP (PNCP - resultados.md): é heurística. Mesmo órgão, publicações
    em ordem; a tentativa seguinte continua a cadeia se a anterior NÃO terminou comprada e veio em até
    540 dias. Cadastro duplicado (mesmo dia, valor a menos de 1% — Bento Gonçalves) é UMA tentativa.
  · HOMOLOGADO SIMBÓLICO: o PNCP traz compras de folha homologadas por R$ 0,00 a R$ 1,00 com
    contrato de milhões (Bradesco R$ 0,60 / R$ 75 mi; Patrocínio/MG R$ 0,01 / R$ 5,5 mi). Quando a soma que o
    banco homologou na compra é ≤ R$ 1 e o contrato dele com o órgão (db/049) diz mais, vale o contrato;
    sem contrato, fica o simbólico, marcado. `fonte_valor` diz qual: homologado | contrato | simbolico.
  · COMPRA CADASTRADA DUAS VEZES: mesmo órgão, mesmo banco vencedor, mesmo valor (±1%) e
    publicação a até 7 dias OU homologação no mesmo dia é a mesma compra — a soma do banco contava duas
    vezes (R$ 14,8 mi no mesmo dia; R$ 10,66 mi com dois meses entre os cadastros e o mesmo dia de
    homologação). Fica a publicação mais antiga; a outra sai de todas as contas.
"""
from __future__ import annotations

import collections
import re
import unicodedata
from datetime import date, timedelta

from psycopg.rows import dict_row

ESCOPOS = ("dentro", "todos")
JANELA_REPUBLICACAO = timedelta(days=540)
MAX_SERIES = 6
ORDEM_RESULTADO = {"comprada": 4, "deserta": 3, "fracassada": 3, "revogada": 2, "anulada": 2, "aberta": 1}
SIMBOLICO = 1.0                             # homologado até R$ 1,00 não é preço de folha
JANELA_DUPLICADA = timedelta(days=7)


def _f(v) -> float:
    return float(v) if v is not None else 0.0


def _raiz(ni: str | None) -> str:
    ni = "".join(ch for ch in (ni or "") if ch.isdigit())
    return ni[:8] if len(ni) == 14 else ni


def _meses(primeiro: date, ultimo: date) -> list[str]:
    out, a, m = [], primeiro.year, primeiro.month
    while (a, m) <= (ultimo.year, ultimo.month):
        out.append("%04d-%02d" % (a, m))
        m += 1
        if m > 12:
            a, m = a + 1, 1
    return out


def _resultado_da_compra(situacao_compra: str | None, itens: list[str], comprada: bool) -> str:
    if comprada or "Homologado" in itens:
        return "comprada"
    if "Deserto" in itens:
        return "deserta"
    if "Fracassado" in itens:
        return "fracassada"
    s = (situacao_compra or "").lower()
    if "revogad" in s:
        return "revogada"
    if "anulad" in s:
        return "anulada"
    return "aberta"


# O PNCP tem data digitada errada: um resultado veio no ANO 255 ("0255-02") e esticou o gráfico mensal a 21.260
# meses (24/09 noite — a página ficava em branco). Data fora disto não vira mês nem "primeira/última compra";
# o resultado continua contando nos totais.
DATA_MINIMA = date(2020, 1, 1)


def _plausivel(d) -> bool:
    return bool(d) and DATA_MINIMA <= d <= date.today() + timedelta(days=366)


# Quem é instituição financeira, pelo NOME (a natureza jurídica não separa: Caixa e PRODESP são "Empresa
# Pública"). Com o histórico inteiro, "Bancos que compraram" trazia a PRODESP e um tribunal (24/09 noite): quem não
# é banco continua no ranking, marcado, mas não conta como banco comprador nem ganha linha própria no gráfico.
RE_FINANCEIRA = re.compile(
    r"\b(BANCO|BANK|CAIXA ECONOMICA|COOPERATIVA DE CREDITO|COOP\.? DE CREDITO|SOCIEDADE DE CREDITO"
    r"|INSTITUICAO DE PAGAMENTO|CREDITO FINANCIAMENTO|SICOOB|SICREDI|CRESOL|UNICRED|AILOS|BANRISUL|BANESTES|BANPARA"
    r"|BANESE|ITAU|BRADESCO|SANTANDER|NUBANK|BRB)\b")


def financeira(nome: str | None) -> bool:
    n = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode("ascii").upper()
    return bool(RE_FINANCEIRA.search(n))


def _bancos(resultados: list[dict]) -> tuple[list[dict], dict]:
    grupos: dict[str, dict] = {}
    for r in resultados:
        g = grupos.setdefault(_raiz(r["ni_fornecedor"]), {"nomes": collections.Counter(), "naturezas": collections.Counter(),
                                                           "controles": set(), "valor": 0.0, "datas": []})
        g["nomes"][r["fornecedor"] or "(sem nome)"] += 1
        g["naturezas"][r["natureza_juridica"] or ""] += 1
        g["controles"].add(r["controle"])
        g["valor"] += r["valor"]
        if _plausivel(r["data_resultado"]):
            g["datas"].append(r["data_resultado"])
    total = sum(len(g["controles"]) for g in grupos.values()) or 1
    nomes = {raiz: sorted(g["nomes"].items(), key=lambda x: (-x[1], x[0]))[0][0] for raiz, g in grupos.items()}
    bancos = [{"banco": nomes[raiz], "cnpj_raiz": raiz, "financeira": financeira(nomes[raiz]),
               "natureza_juridica": sorted(g["naturezas"].items(), key=lambda x: (-x[1], x[0]))[0][0] or None,
               "licitacoes": len(g["controles"]), "valor_total": round(g["valor"], 2),
               "ticket_medio": round(g["valor"] / len(g["controles"]), 2),
               "participacao": len(g["controles"]) / total,
               "primeira": min(g["datas"]).isoformat() if g["datas"] else None,
               "ultima": max(g["datas"]).isoformat() if g["datas"] else None}
              for raiz, g in grupos.items()]
    bancos.sort(key=lambda b: (-b["licitacoes"], -b["valor_total"], b["banco"]))
    return bancos, nomes


def _mensal(resultados: list[dict], bancos: list[dict], nomes: dict) -> dict:
    # uma compra conta no mês do (primeiro) resultado daquele banco nela
    por_compra: dict[tuple, dict] = {}
    for r in resultados:
        if not _plausivel(r["data_resultado"]):
            continue
        k = (_raiz(r["ni_fornecedor"]), r["controle"])
        x = por_compra.setdefault(k, {"dia": r["data_resultado"], "valor": 0.0})
        x["dia"] = min(x["dia"], r["data_resultado"])
        x["valor"] += r["valor"]
    if not por_compra:
        return {"meses": [], "series": []}
    dias = [x["dia"] for x in por_compra.values()]
    meses = _meses(min(dias), max(dias))
    idx = {m: i for i, m in enumerate(meses)}
    topo = [b["cnpj_raiz"] for b in bancos if b["financeira"]][:MAX_SERIES]
    series: dict[str, dict] = {}
    for (raiz, _), x in por_compra.items():
        chave = raiz if raiz in topo else "outros"
        s = series.setdefault(chave, {"banco": nomes.get(raiz) if chave != "outros" else "Outros",
                                      "cnpj_raiz": raiz if chave != "outros" else None,
                                      "licitacoes": [0] * len(meses), "valor": [0.0] * len(meses)})
        i = idx["%04d-%02d" % (x["dia"].year, x["dia"].month)]
        s["licitacoes"][i] += 1
        s["valor"][i] = round(s["valor"][i] + x["valor"], 2)
    ordem = {r: i for i, r in enumerate(topo)}
    return {"meses": meses, "series": sorted(series.values(), key=lambda s: ordem.get(s["cnpj_raiz"], len(ordem)))}


def _tentativas(compras: list[dict]) -> list[dict]:
    """Compras de UM órgão, em ordem, com o cadastro duplicado do mesmo dia juntado numa tentativa."""
    out: list[dict] = []
    for c in compras:
        u = out[-1] if out else None
        mesmo_dia = u and c["publicado_em"] and u["publicado_em"] and c["publicado_em"].date() == u["publicado_em"].date()
        valor_igual = u and abs(_f(c["valor_estimado"]) - _f(u["valor_estimado"])) <= 0.01 * max(_f(u["valor_estimado"]), 1.0)
        if mesmo_dia and valor_igual:
            u["controles"].append(c["controle"])
            if ORDEM_RESULTADO[c["resultado"]] > ORDEM_RESULTADO[u["resultado"]]:
                u["resultado"] = c["resultado"]
            continue
        out.append({"controles": [c["controle"]], "publicado_em": c["publicado_em"], "resultado": c["resultado"],
                    "valor_estimado": _f(c["valor_estimado"]) or None})
    return out


def _cadeias(compras: list[dict]) -> list[tuple[str, list[dict]]]:
    """
    As cadeias de publicação de cada órgão (a heurística do topo): em ordem, a tentativa seguinte continua a cadeia se
    a anterior NÃO terminou comprada e veio em até JANELA_REPUBLICACAO. Cadeia de uma tentativa só é a 1ª publicação.
    """
    por_orgao: dict[str, list] = collections.defaultdict(list)
    for c in compras:
        if c["publicado_em"]:
            por_orgao[c["orgao_cnpj"] or c["controle"][:14]].append(c)
    cadeias = []
    for cnpj, lista in por_orgao.items():
        lista.sort(key=lambda c: (c["publicado_em"], c["controle"]))
        atual: list[dict] = []
        for t in _tentativas(lista):
            if atual and (atual[-1]["resultado"] == "comprada"
                          or t["publicado_em"] - atual[-1]["publicado_em"] > JANELA_REPUBLICACAO):
                cadeias.append((cnpj, atual))
                atual = []
            atual.append(t)
        if atual:
            cadeias.append((cnpj, atual))
    return cadeias


def _rodadas(compras: list[dict]) -> dict[str, int]:
    """A publicação (1ª, 2ª, 3ª...) de cada licitação na cadeia do órgão — a mesma conta das republicadas."""
    return {controle: i for _, tentativas in _cadeias(compras)
            for i, t in enumerate(tentativas, start=1) for controle in t["controles"]}


def _republicadas(compras: list[dict]) -> list[dict]:
    out = []
    ref = {c["controle"]: c for c in compras}
    for cnpj, tentativas in _cadeias(compras):
        if len(tentativas) < 2:
            continue
        primeira = ref[tentativas[-1]["controles"][0]]
        historico = [{"publicacao": i, "controles": sorted(t["controles"]), "publicado_em": t["publicado_em"].isoformat(),
                      "resultado": t["resultado"], "valor_estimado": t["valor_estimado"]}
                     for i, t in enumerate(tentativas, start=1)]
        out.append({"orgao_cnpj": cnpj, "orgao": primeira["orgao"], "municipio": primeira["municipio"],
                    "uf": primeira["uf"], "tentativas": len(tentativas), "historico": historico,
                    "situacao_atual": tentativas[-1]["resultado"],
                    "sem_comprador": tentativas[-1]["resultado"] != "comprada",
                    "ultima_publicacao": tentativas[-1]["publicado_em"].isoformat()})
    out.sort(key=lambda k: (-k["tentativas"], k["ultima_publicacao"]), reverse=False)
    out.sort(key=lambda k: -k["tentativas"])
    return out


def montar(conn, escopo: str = "dentro", ano: int | None = None, de: date | None = None,
           ate: date | None = None, so_fopa_ia: bool = False) -> dict:
    cur = conn.cursor(row_factory=dict_row)
    compras, resultados, ajustes = _carregar(cur, escopo=escopo, ano=ano, de=de, ate=ate, so_fopa_ia=so_fopa_ia)
    compradas = {r["controle"] for r in resultados}
    bancos, nomes = _bancos(resultados)
    republicadas = _republicadas(compras)
    desertas = sum(1 for k in _republicadas_todas_tentativas(compras) if k in ("deserta", "fracassada"))
    return {
        "filtro": {"escopo": escopo, "ano": int(ano) if ano else None,
                   "de": de.isoformat() if de else None, "ate": ate.isoformat() if ate else None,
                   "so_fopa_ia": bool(so_fopa_ia)},
        "resumo": {"compras": len(compras), "com_vencedor": len(compradas),
                   "bancos": sum(1 for b in bancos if b["financeira"]), "fornecedores": len(bancos),
                   "valor_homologado": round(sum(r["valor"] for r in resultados), 2),
                   "valor_estimado": round(sum(_f(c["valor_estimado"]) for c in compras), 2),
                   "desertas": desertas, "republicadas": len(republicadas),
                   **ajustes,
                   "coletadas_em": _ultima_coleta(cur)},
        "bancos": bancos,
        "mensal": _mensal(resultados, bancos, nomes),
        "republicadas": republicadas,
    }


def _carregar(cur, escopo: str = "dentro", ano: int | None = None, de: date | None = None, ate: date | None = None,
              so_fopa_ia: bool = False) -> tuple[list[dict], list[dict]]:
    """As compras coletadas do escopo (com o `resultado` de cada uma) e os resultados não cancelados delas."""
    # A base é a licitação COLETADA (pncp_coletas ok). O cabeçalho do PNCP é opcional — a API de consulta
    # recusa (429) com facilidade —, então órgão, município, data e situação caem para o que a descoberta
    # gravou em `licitacoes`, e o valor estimado para a soma dos itens.
    publicado = "COALESCE(c.publicado_em, l.publicado_em::timestamp AT TIME ZONE 'America/Sao_Paulo')"
    # o escopo efetivo (db/031): o rótulo humano mais recente prevalece sobre a regra
    where, args = ["true" if escopo == "todos" else "fn_escopo_efetivo(l.controle, l.escopo_dentro)"], []
    if ano:
        where.append("extract(year FROM %s AT TIME ZONE 'America/Sao_Paulo') = %%s" % publicado)
        args.append(int(ano))
    # O filtro de datas: a mesma régua do ano — a data de publicação em Brasília —,
    # com as duas pontas inclusas.
    if so_fopa_ia:
        # "apenas FOPA (a IA confirma)" (db/034): sai o que a IA estima que não é folha (nota < 0,5)
        where.append("NOT fn_ia_nao_fopa(l.controle, 0.5)")
    if de:
        where.append("(%s AT TIME ZONE 'America/Sao_Paulo')::date >= %%s" % publicado)
        args.append(de)
    if ate:
        where.append("(%s AT TIME ZONE 'America/Sao_Paulo')::date <= %%s" % publicado)
        args.append(ate)
    compras = cur.execute(
        "SELECT l.controle, COALESCE(c.orgao_cnpj, substr(l.controle, 1, 14)) AS orgao_cnpj,"
        " COALESCE(c.orgao, l.orgao) AS orgao, COALESCE(c.uf, l.uf) AS uf,"
        " COALESCE(c.municipio, l.municipio) AS municipio,"
        " COALESCE(c.modalidade, l.modalidade) AS modalidade, COALESCE(c.objeto, l.objeto) AS objeto,"
        " c.payload ->> 'numeroCompra' AS numero_compra,"
        " COALESCE(c.valor_estimado, (SELECT sum(i.valor_total) FROM pncp_itens i WHERE i.controle = l.controle))"
        "   AS valor_estimado,"
        " COALESCE(c.situacao, l.situacao) AS situacao, " + publicado + " AS publicado_em"
        " FROM licitacoes l JOIN pncp_coletas k ON k.controle = l.controle AND k.ok"
        " LEFT JOIN pncp_compras c ON c.controle = l.controle WHERE " + " AND ".join(where),
        args).fetchall()
    controles = [c["controle"] for c in compras]
    itens = collections.defaultdict(list)
    for i in cur.execute("SELECT controle, situacao FROM pncp_itens WHERE controle = ANY(%s)", (controles,)).fetchall():
        itens[i["controle"]].append(i["situacao"])
    resultados = cur.execute(
        "SELECT controle, numero_item, ni_fornecedor, fornecedor, natureza_juridica, valor_homologado, data_resultado"
        " FROM pncp_resultados WHERE controle = ANY(%s) AND cancelado_em IS NULL", (controles,)).fetchall()
    duplicadas = _duplicadas(compras, resultados)
    compras = [c for c in compras if c["controle"] not in duplicadas]
    resultados = [r for r in resultados if r["controle"] not in duplicadas]
    fontes = _valor_efetivo(cur, resultados)
    compradas = {r["controle"] for r in resultados}
    for c in compras:
        c["resultado"] = _resultado_da_compra(c["situacao"], itens.get(c["controle"], []), c["controle"] in compradas)
    ajustes = {"duplicadas": len(duplicadas), "pelo_contrato": fontes["contrato"], "simbolicas": fontes["simbolico"]}
    return compras, resultados, ajustes


def _por_compra_e_banco(resultados: list[dict]) -> dict[tuple, list[dict]]:
    grupos: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in resultados:
        grupos[(r["controle"], _raiz(r["ni_fornecedor"]))].append(r)
    return grupos


def _duplicadas(compras: list[dict], resultados: list[dict]) -> set[str]:
    """
    As compras que são o MESMO cadastro de outra (ver "COMPRA CADASTRADA DUAS VEZES" no topo): mesmo órgão,
    mesmo banco vencedor, mesmo valor homologado (±1%), e publicação a até 7 dias ou homologação no mesmo dia.
    Devolve as que saem; de cada grupo fica a publicada primeiro.
    """
    ref = {c["controle"]: c for c in compras}
    candidatos: dict[tuple, list[dict]] = collections.defaultdict(list)
    for (controle, raiz), linhas in _por_compra_e_banco(resultados).items():
        c = ref.get(controle)
        if c is None or c["publicado_em"] is None:
            continue
        dias = [r["data_resultado"] for r in linhas if _plausivel(r["data_resultado"])]
        candidatos[(c["orgao_cnpj"] or controle[:14], raiz)].append(
            {"controle": controle, "pub": c["publicado_em"], "valor": sum(_f(r["valor_homologado"]) for r in linhas),
             "dia": min(dias) if dias else None})
    fica: dict[str, str] = {}

    def raiz_de(controle: str) -> str:
        while fica.get(controle, controle) != controle:
            controle = fica[controle]
        return controle

    for lista in candidatos.values():
        lista.sort(key=lambda x: (x["pub"], x["controle"]))
        for i, a in enumerate(lista):
            for b in lista[i + 1:]:
                if abs(a["valor"] - b["valor"]) > 0.01 * max(a["valor"], b["valor"], 1.0):
                    continue
                perto = b["pub"] - a["pub"] <= JANELA_DUPLICADA
                if perto or (a["dia"] is not None and a["dia"] == b["dia"]):
                    ra, rb = raiz_de(a["controle"]), raiz_de(b["controle"])
                    if ra != rb:
                        primeiro, segundo = sorted((ra, rb), key=lambda k: (ref[k]["publicado_em"], k))
                        fica[segundo] = primeiro
    return {k for k in fica if raiz_de(k) != k}


def _valor_efetivo(cur, resultados: list[dict]) -> dict[str, int]:
    """
    Grava em cada resultado `valor` (o que entra nas somas) e `fonte_valor` (ver "HOMOLOGADO SIMBÓLICO" no
    topo). No grupo (compra, banco) que vai pelo contrato, a primeira linha leva o valor do contrato e as outras
    zero: as somas por compra e por banco ficam certas sem mudar quem as faz. Devolve quantos grupos de cada.
    """
    grupos = _por_compra_e_banco(resultados)
    for r in resultados:
        r["valor"], r["fonte_valor"] = _f(r["valor_homologado"]), "homologado"
    simbolicos = [k for k, linhas in grupos.items() if sum(r["valor"] for r in linhas) <= SIMBOLICO]
    contratos: dict[tuple, float] = collections.defaultdict(float)
    if simbolicos:
        for k in cur.execute(
                "SELECT controle_compra, ni_fornecedor, COALESCE(valor_acumulado, valor_global) AS valor"
                " FROM pncp_contratos WHERE controle_compra = ANY(%s)",
                (sorted({c for c, _ in simbolicos}),)).fetchall():
            contratos[(k["controle_compra"], _raiz(k["ni_fornecedor"]))] += _f(k["valor"])
    n = {"contrato": 0, "simbolico": 0}
    for k in simbolicos:
        linhas, contrato = grupos[k], contratos.get(k, 0.0)
        fonte = "contrato" if contrato > SIMBOLICO else "simbolico"
        n[fonte] += 1
        for i, r in enumerate(linhas):
            r["fonte_valor"] = fonte
            if fonte == "contrato":
                r["valor"] = contrato if i == 0 else 0.0
    return n


def _contratos(cur, controles: list[str], raiz: str) -> dict[str, dict]:
    """Os contratos (db/049) de cada licitação com o banco `raiz`: valor (acumulado, com os aditivos) e vigência."""
    out: dict[str, dict] = {}
    for k in cur.execute(
            "SELECT controle, controle_compra, ni_fornecedor, COALESCE(valor_acumulado, valor_global) AS valor,"
            " assinado_em, vigencia_fim FROM pncp_contratos WHERE controle_compra = ANY(%s)"
            " ORDER BY assinado_em NULLS LAST, controle", (controles,)).fetchall():
        if _raiz(k["ni_fornecedor"]) != raiz:
            continue
        x = out.setdefault(k["controle_compra"], {"controle": k["controle"], "contratos": 0, "valor": 0.0,
                                                  "assinado_em": None, "vigencia_fim": None})
        x["contratos"] += 1
        x["valor"] = round(x["valor"] + _f(k["valor"]), 2)
        if k["assinado_em"] and x["assinado_em"] is None:
            x["assinado_em"] = k["assinado_em"].isoformat()
        if k["vigencia_fim"] and (x["vigencia_fim"] is None or k["vigencia_fim"].isoformat() > x["vigencia_fim"]):
            x["vigencia_fim"] = k["vigencia_fim"].isoformat()
    return out


def compras_por_banco(conn, escopo: str = "dentro", so_fopa_ia: bool = False, banco: str | None = None,
                      de: date | None = None, ate: date | None = None) -> dict:
    """
    O que cada instituição financeira comprou.

    `bancos` é a lista do filtro: as instituições financeiras com compra no escopo, no histórico inteiro. Com
    `banco` (CNPJ ou CNPJ-raiz), as compras dele: o PREÇO é a soma do que ele homologou na licitação; a DATA, o
    resultado mais antigo dele nela; a RODADA sai das cadeias do histórico INTEIRO (a 2ª publicação continua a
    2ª com qualquer período). O período olha a data da compra, com as duas pontas inclusas. O contrato
    (db/049) vem quando o PNCP o publicou.
    """
    cur = conn.cursor(row_factory=dict_row)
    compras, resultados, _ = _carregar(cur, escopo=escopo, so_fopa_ia=so_fopa_ia)
    bancos, nomes = _bancos(resultados)
    raiz = _raiz(banco) if banco else None
    out = {"filtro": {"escopo": escopo, "so_fopa_ia": bool(so_fopa_ia), "banco": raiz,
                      "de": de.isoformat() if de else None, "ate": ate.isoformat() if ate else None},
           "bancos": [{k: b[k] for k in ("cnpj_raiz", "banco", "licitacoes", "valor_total")}
                      for b in bancos if b["financeira"]],
           "banco": {"cnpj_raiz": raiz, "banco": nomes.get(raiz)} if raiz else None,
           "compras": [], "total": {"licitacoes": 0, "valor": 0.0}, "coletadas_em": _ultima_coleta(cur)}
    if not raiz:
        return out
    por_compra: dict[str, dict] = {}
    for r in resultados:
        if _raiz(r["ni_fornecedor"]) != raiz:
            continue
        x = por_compra.setdefault(r["controle"], {"valor": 0.0, "dia": None, "fonte_valor": r["fonte_valor"]})
        x["valor"] += r["valor"]
        if _plausivel(r["data_resultado"]) and (x["dia"] is None or r["data_resultado"] < x["dia"]):
            x["dia"] = r["data_resultado"]
    no_periodo = {c: x for c, x in por_compra.items()
                  if (not de or (x["dia"] and x["dia"] >= de)) and (not ate or (x["dia"] and x["dia"] <= ate))}
    rodada, ref = _rodadas(compras), {c["controle"]: c for c in compras}
    contratos = _contratos(cur, list(no_periodo), raiz)
    # FOPA = o que a tela mostra por padrão: escopo efetivo de folha e a IA não diz que não é. Só das compras do
    # banco: as duas funções custam uma consulta por licitação, e o acervo inteiro tem milhares.
    fopa = {r["controle"]: r["fopa"] for r in cur.execute(
        "SELECT controle, (fn_escopo_efetivo(controle, escopo_dentro) AND NOT fn_ia_nao_fopa(controle, 0.5)) AS fopa"
        " FROM licitacoes WHERE controle = ANY(%s)", (list(no_periodo),)).fetchall()}
    linhas = []
    for controle, x in no_periodo.items():
        c = ref[controle]
        linhas.append({"controle": controle, "fopa": bool(fopa.get(controle)), "municipio": c["municipio"], "uf": c["uf"],
                       "orgao": c["orgao"],
                       "modalidade": c["modalidade"], "numero_compra": c["numero_compra"], "objeto": c["objeto"],
                       "publicado_em": c["publicado_em"].isoformat() if c["publicado_em"] else None,
                       "rodada": rodada.get(controle, 1), "valor": round(x["valor"], 2),
                       "fonte_valor": x["fonte_valor"],
                       "comprada_em": x["dia"].isoformat() if x["dia"] else None,
                       "contrato": contratos.get(controle)})
    # a compra mais recente primeiro; sem data (o PNCP não disse quando), no fim
    linhas.sort(key=lambda l: (l["comprada_em"] or "", l["controle"]), reverse=True)
    out["compras"] = linhas
    out["total"] = {"licitacoes": len(linhas), "valor": round(sum(l["valor"] for l in linhas), 2)}
    return out


def _republicadas_todas_tentativas(compras: list[dict]) -> list[str]:
    """O resultado de cada TENTATIVA (duplicadas juntas), de todos os órgãos: é o que conta como deserta."""
    por_orgao: dict[str, list] = collections.defaultdict(list)
    for c in compras:
        por_orgao[c["orgao_cnpj"] or c["controle"][:14]].append(c)
    out = []
    for lista in por_orgao.values():
        lista.sort(key=lambda c: (c["publicado_em"] is None, c["publicado_em"] or date.min, c["controle"]))
        out += [t["resultado"] for t in _tentativas([c for c in lista if c["publicado_em"]])]
        out += [c["resultado"] for c in lista if not c["publicado_em"]]
    return out


def _ultima_coleta(cur) -> str | None:
    r = cur.execute("SELECT max(em) AS em FROM pncp_coletas WHERE ok").fetchone()
    return r["em"].isoformat() if r and r["em"] else None


__all__ = ["montar", "compras_por_banco", "financeira", "ESCOPOS"]
