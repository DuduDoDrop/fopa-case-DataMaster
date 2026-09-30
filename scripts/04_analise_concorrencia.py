# -*- coding: utf-8 -*-
"""Levanta quem vence licitações de folha no PNCP e por quanto."""
import json, re, io, os, time, urllib.request, urllib.parse, collections

UA = {"User-Agent": "FOPA-POC/0.1 (estudo de viabilidade)", "Accept": "application/json"}
AM = r"C:\Users\Nome\Projetos\projeto-fopa\amostras"
POS = re.compile(r"folha de pagament|cess[aã]o onerosa|cr[ée]ditos salari|processamento da folha|centraliza", re.I)
DESC = re.compile(r"licen[çc]a de uso|software|sistema de gest|empr[ée]stimo pessoal consignado|margem consign|averba|vale[- ]", re.I)


def get(url, timeout=60):
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            if tentativa == 2:
                return None
            time.sleep(1.5)
    return None


# ---------------------------------------------------- 1. descobrir licitações com resultado
achados = {}
for termo in ["cessão onerosa folha de pagamento",
              "folha de pagamento servidores exclusividade",
              "processamento folha de pagamento instituição financeira",
              "centralização créditos folha de pagamento"]:
    for pag in (1, 2, 3):
        q = urllib.parse.urlencode({"q": termo, "tipos_documento": "edital", "ordenacao": "-data",
                                    "pagina": pag, "tam_pagina": 50, "status": "todos"})
        d = get("https://pncp.gov.br/api/search/?" + q)
        if not d:
            break
        itens = d.get("items", [])
        for it in itens:
            achados[it.get("numero_controle_pncp")] = it
        if len(itens) < 50:
            break
        time.sleep(0.5)

alvos = []
for it in achados.values():
    txt = (it.get("title") or "") + " " + (it.get("description") or "")
    if DESC.search(txt) or not POS.search(txt):
        continue
    if it.get("tem_resultado"):
        alvos.append(it)

print("licitacoes de folha encontradas: %d | com resultado: %d" % (len(achados), len(alvos)))

# ---------------------------------------------------- 2. buscar vencedores
vencedores = collections.Counter()
por_uf = collections.defaultdict(collections.Counter)
registros = []
for it in alvos[:60]:
    m = re.match(r"/compras/(\d+)/(\d+)/(\d+)", it.get("item_url") or "")
    if not m:
        continue
    cnpj, ano, seq = m.groups()
    itens = get("https://pncp.gov.br/api/pncp/v1/orgaos/%s/compras/%s/%s/itens" % (cnpj, ano, seq))
    if not itens:
        continue
    if isinstance(itens, dict):
        itens = [itens]
    for item in itens:
        n = item.get("numeroItem")
        if n is None:
            continue
        res = get("https://pncp.gov.br/api/pncp/v1/orgaos/%s/compras/%s/%s/itens/%s/resultados"
                  % (cnpj, ano, seq, n))
        if not res:
            continue
        if isinstance(res, dict):
            res = [res]
        for r in res:
            nome = (r.get("nomeRazaoSocialFornecedor") or "").strip()
            if not nome:
                continue
            valor = r.get("valorTotalHomologado")
            minimo = item.get("valorTotal")
            vencedores[nome] += 1
            por_uf[it.get("uf")][nome] += 1
            registros.append(dict(
                municipio=it.get("municipio_nome"), uf=it.get("uf"),
                modalidade=it.get("modalidade_licitacao_nome"),
                vencedor=nome, cnpj_vencedor=r.get("niFornecedor"),
                natureza=r.get("naturezaJuridicaNome"),
                valor_homologado=valor, valor_minimo=minimo,
                agio=(round(valor / minimo, 3) if (valor and minimo) else None),
                data=r.get("dataResultado"),
                controle=it.get("numero_controle_pncp")))
    time.sleep(0.4)

print("\n=== VENCEDORES (licitacoes de folha com resultado publicado) ===")
tot = sum(vencedores.values())
for nome, n in vencedores.most_common(15):
    print("%5d  %5.1f%%  %s" % (n, 100.0 * n / max(tot, 1), nome[:64]))
print("total de resultados: %d" % tot)

comagio = [r for r in registros if r["agio"] and 0.5 < r["agio"] < 100]
if comagio:
    comagio.sort(key=lambda r: r["agio"])
    print("\n=== AGIO (homologado / valor minimo) ===")
    print("amostra com agio calculavel: %d" % len(comagio))
    ags = [r["agio"] for r in comagio]
    print("minimo %.2fx | mediana %.2fx | maximo %.2fx" %
          (ags[0], ags[len(ags) // 2], ags[-1]))
    print("\nmaiores agios:")
    for r in comagio[-6:][::-1]:
        print("   %-26s %-3s %-22s min R$ %-14s homol R$ %-14s %.2fx" %
              (str(r["municipio"])[:26], r["uf"], str(r["vencedor"])[:22],
               f"{r['valor_minimo']:,.2f}".replace(",", "."), f"{r['valor_homologado']:,.2f}".replace(",", "."), r["agio"]))

io.open(os.path.join(AM, "_concorrencia.json"), "w", encoding="utf-8").write(
    json.dumps(dict(vencedores=dict(vencedores), registros=registros), ensure_ascii=False, indent=1))
print("\nsalvo: amostras/_concorrencia.json")
