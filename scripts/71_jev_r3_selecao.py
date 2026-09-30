# -*- coding: utf-8 -*-
"""
R3 com o Jev — segundo extrator POR SELEÇÃO para a Q1 (data) e a Q5 (valor).

    python 71_jev_r3_selecao.py --seco                 monta tudo, conta caracteres, NÃO chama
    python 71_jev_r3_selecao.py [--max N] --teto-usd 0.07 [--livro caixa.json --teto-livro 0.10]
    python 71_jev_r3_selecao.py --rejulgar             relê o JSON salvo + o julgamento à mão (US$ 0)

CHAMA O JEV (centavos; teto DURO --teto-usd, e opcionalmente um teto somado entre
execuções via --livro). Lê o Postgres da v3 (papel api_ro, só leitura). Não escreve
no banco, não muda veredito, não mexe em confiança (T25). Grava a medição em
docs/medicoes/r3_jev_selecao_<data>.json.

O DESENHO (fim da nota R3 em "Jev — casos de uso avaliados"; passo zero no 69_)
  População: as respostas APROVADAS de Q1 e Q5 com página congelada e valor-alvo —
  as mesmas 70 + 63 do 69_recall_candidatos.py.
  Candidatos: a LEITURA INTEIRA, com as regex do 69_ (camada completa) e a poda por
  código do 69_ (Q1: ano >= ano da compra; Q5: "R$" colado antes). A página que o
  Claude citou NÃO é usada para montar candidatos: o segundo extrator tem de ser
  independente do primeiro.
  Um Noul por valor DISTINTO. O estado leva ±200 caracteres de entorno de CADA
  ocorrência, com as janelas da mesma página unidas (é a conta de caracteres do
  69_) e cada ocorrência marcada no texto com o id do candidato ("[c07]02/10/2026").
  Mais um Noul "nenhum dos marcados é". Escolha = maior p entre os candidatos e o
  "nenhum". Candidatos demais (Q5 chega a 539 valores distintos) vão em lotes de
  até MAX_NOULS; o "nenhum" final é o MENOR dos lotes (basta um lote ter o valor).

O QUE SE MEDE
  concordância da escolha com o valor aprovado (Q1: só a DATA; a hora é informação),
  p do escolhido, margem para o 2º, e as discordâncias — as 10 piores (maior p no
  escolhido errado) julgadas à mão, em JULGAMENTO, com o trecho de cada lado.

A LINHA
  O valor do Jev nunca vira resposta nem confiança: aqui ele só é comparado.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import io
import json
import os
import re
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

from fopa import jev, segredos                                    # noqa: E402


def _carregar(nome: str, arquivo: str):
    spec = importlib.util.spec_from_file_location(nome, os.path.join(AQUI, arquivo))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R69 = _carregar("recall69", "69_recall_candidatos.py")        # regex, poda, alvo, _dsn — sem copiar

DESTINO = os.path.join(RAIZ, "docs", "medicoes")
PERGUNTAS = ("Q1", "Q5")
ENTORNO = 200                     # ± caracteres por ocorrência (o do 69_)
MAX_NOULS = 100                   # candidatos por request (+1 "nenhum"); quem manda é o state
MAX_ESTADO = 55_000               # caracteres de state serializado (o teto sondado é 63.750)
CORTE = 0.75                      # convicção medida na 1.13 (Jev na v3)
# Sondado em 23/09 (64_): 63.750 caracteres -> 32.179 tokens, ~1,98 caractere por token.
# A reserva usa 1,5: a estimativa fica ACIMA do real e o teto nunca é furado.
CHARS_POR_TOKEN_RESERVA = 1.5


# ============================================================ caixa (teto duro)
class TetoAtingido(RuntimeError):
    pass


class Caixa:
    """
    Teto DURO de gasto. Antes de cada request reserva o custo estimado (por cima);
    se gasto + reservado + estimativa passar do limite, não chama. Com --livro, o
    limite também desconta o que execuções anteriores (deste e de outros scripts)
    já gastaram, e o livro é regravado a cada chamada — um erro no meio não perde
    a conta.
    """

    def __init__(self, teto: float, livro: str | None, teto_livro: float | None, rotulo: str):
        self.livro, self.rotulo = livro, rotulo
        self.id = "%s@%s" % (rotulo, datetime.datetime.now().isoformat(timespec="seconds"))
        self.dados = {"teto_usd": teto_livro, "usd": 0.0, "execucoes": {}}
        if livro and os.path.exists(livro):
            self.dados = json.load(io.open(livro, encoding="utf-8"))
        self.anterior = float(self.dados.get("usd") or 0.0)
        self.limite = teto if teto_livro is None else min(teto, teto_livro - self.anterior)
        self.usd = self.reservado = 0.0
        self.chamadas = self.tokens = self.falhas = 0
        self.chars_enviados = 0
        self._t = threading.Lock()

    def _gravar(self) -> None:
        if not self.livro:
            return
        self.dados["execucoes"][self.id] = {"usd": round(self.usd, 6), "chamadas": self.chamadas,
                                            "tokens": self.tokens}
        self.dados["usd"] = round(sum(e["usd"] for e in self.dados["execucoes"].values()), 6)
        io.open(self.livro, "w", encoding="utf-8").write(json.dumps(self.dados, indent=1))

    def perguntar(self, estado: str, perguntas: dict) -> tuple[dict, dict]:
        chars = len(estado) + len(json.dumps(perguntas, ensure_ascii=False))
        est = chars / CHARS_POR_TOKEN_RESERVA * jev.PRECO_ENTRADA_ANUNCIADO / 1_000_000
        with self._t:
            if self.usd + self.reservado + est > self.limite:
                raise TetoAtingido("teto: gasto %.5f + reservado %.5f + este %.5f > limite %.5f"
                                   % (self.usd, self.reservado, est, self.limite))
            self.reservado += est
        try:
            for tentativa in range(4):
                try:
                    ans, uso = jev.perguntar(estado, perguntas)
                    break
                except jev.ErroJev as e:
                    if tentativa == 3 or e.status not in (0, 429, 500, 502, 503, 529):
                        with self._t:
                            self.falhas += 1
                        raise
                    time.sleep(2 * 2 ** tentativa)
        finally:
            with self._t:
                self.reservado -= est
        with self._t:
            self.usd += uso["usd"]
            self.chamadas += 1
            self.tokens += uso["input_tokens"]
            self.chars_enviados += chars
            self._gravar()
        if uso["usd"] > est:
            print("  ! estimativa abaixo do real (%.6f > %.6f)" % (uso["usd"], est), flush=True)
        return ans, uso


# ================================================================= candidatos
MES_RE = {1: "janeiro", 2: "fevereiro", 3: "mar[çc]o", 4: "abril", 5: "maio", 6: "junho",
          7: "julho", 8: "agosto", 9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"}


def _dig(n: int) -> str:
    """Dígitos de n, tolerando o espaço que o OCR mete entre eles e o zero à esquerda."""
    s = str(n)
    p = r"\s?".join(s)
    return (r"(?:0\s?)?" + p) if len(s) == 1 else p


def re_data_bruta(valor: str):
    """
    As grafias de uma data (dd/mm/aaaa) no texto CRU da página.

    O 69_ acha as datas no texto normalizado (ascii, minúsculo, extenso já convertido),
    onde as posições não batem com o texto original. Para o Jev ler o entorno com
    acento e maiúscula, cada valor distinto é procurado de novo no texto cru.
    """
    d, m, a = (int(x) for x in valor.split("/"))
    ano = r"\s?".join(str(a))
    num = r"(?<![\d/.])%s\s*[/.\-]\s*%s\s*[/.\-]\s*%s(?![\d/])" % (_dig(d), _dig(m), ano)
    ext = r"(?<!\d)%s\s*(?:º|°|ª|o)?\s+de\s+%s\s+de\s+%s(?!\d)" % (_dig(d), MES_RE[m], ano)
    return re.compile(num + "|" + ext, re.I)


def ocorrencias_da_pagina(pid: str, controle: str, texto: str) -> list:
    """
    [(valor, fonte, ini, fim)] das ocorrências que passam na poda, numa página.
    fonte = "bruto" (posição no texto cru) ou "norm" (só a Q1, quando a grafia
    não foi reencontrada no cru — o entorno então vai normalizado, e isso é contado).
    """
    c = R69.CANDIDATOS[pid](texto)
    occ = [o for o in c["ocorrencias"] if R69.passa_poda(pid, controle, c["norm"], o)]
    if pid == "Q5":                              # as posições do 69_ já são do texto cru
        return [(v, "bruto", i, f) for v, i, f in occ]
    saida = []
    for v in sorted({o[0] for o in occ}):
        cru = [(m.start(), m.end()) for m in re_data_bruta(v).finditer(texto or "")]
        if cru:
            saida += [(v, "bruto", i, f) for i, f in cru]
        else:
            saida += [(v, "norm", i, f) for vv, i, f in occ if vv == v]
    return saida


def rotulo(pid: str, v) -> str:
    return v if pid == "Q1" else "R$ " + R69.fmt_reais(v)


def _limpar(s: str) -> str:
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def janelas(texto: str, marcas: list, entorno: int) -> list[str]:
    """
    Janelas de ±entorno em volta de cada ocorrência, unidas quando se tocam, com o
    id do candidato inserido antes de cada ocorrência: "... abertura: [c03]02/10/2026 ...".
    `marcas` = [(cid, ini, fim)].
    """
    if not marcas:
        return []
    marcas = sorted(marcas, key=lambda x: x[1])
    blocos, atual = [], None
    for cid, i, f in marcas:
        a, b = max(0, i - entorno), min(len(texto), f + entorno)
        if atual and a <= atual[1]:
            atual[1] = max(atual[1], b)
            atual[2].append((cid, i))
        else:
            atual = [a, b, [(cid, i)]]
            blocos.append(atual)
    saida = []
    for a, b, ms in blocos:
        partes, cur = [], a
        for cid, i in ms:
            partes.append(texto[cur:i])
            partes.append("[%s]" % cid)
            cur = i
        partes.append(texto[cur:b])
        s = _limpar("".join(partes))
        saida.append(("… " if a > 0 else "") + s + (" …" if b < len(texto) else ""))
    return saida


# ================================================================== perguntas
# A definição vai UMA vez no state (`tarefa`); cada Noul só aponta o candidato. Na
# primeira montagem (definição dentro de cada Noul) as perguntas eram 70% dos
# caracteres: 2.400 Nouls x ~880 caracteres. O Jev lê o state uma vez e avalia todas
# as perguntas contra ele (docs.typesafe.ai/models), e o texto da pergunta é cobrado.
TAREFA = {
    "Q1": ("Find the date of the PUBLIC SESSION of this Brazilian public procurement: the day the "
           "'sessão pública' opens or the bidding dispute ('disputa de lances') starts — including a "
           "new session date set by a rectification or postponement notice. NOT the session date: "
           "publication dates, deadlines for clarification or challenge, proposal submission on a "
           "different day, contract, validity or signature dates, dates of laws, decrees or "
           "ordinances. Candidate dates are marked in the excerpts as [c01], [c02], ..."),
    "Q5": ("Find the MINIMUM VALUE of this contract for a municipality's payroll banking services "
           "(folha de pagamento): the overall amount the bank must at least offer or pay for the "
           "right to process the payroll. Documents label it 'valor mínimo', 'lance mínimo', 'valor "
           "estimado', 'valor de referência', 'valor global' or 'valor da outorga'. NOT it: unit or "
           "per-employee prices, monthly or partial installments, payroll totals or salaries, "
           "guarantees, fines, capital or equity requirements, fees, values of something else. "
           "Candidate amounts are marked in the excerpts as [c01], [c02], ..."),
}


def noul_candidato(pid: str, cid: str, rot: str) -> dict:
    return jev.noul("Is the candidate marked [%s] (%s) the value that `tarefa` asks for?" % (cid, rot),
                    "yes: the excerpts present [%s] as that value" % cid,
                    "no: [%s] is something else" % cid)


def noul_nenhum(pid: str, ids: list[str]) -> dict:
    return jev.noul("Is it true that NONE of the marked candidates ([%s] to [%s]) is the value that "
                    "`tarefa` asks for?" % (ids[0], ids[-1]),
                    "none of them is: the right value is missing from the excerpts or unmarked",
                    "at least one marked candidate is it")


# ================================================================== montagem
def carregar_casos(conn, maximo: int) -> list[dict]:
    """A população do 69_: APROVADAS de Q1/Q5, página citada congelada, valor-alvo."""
    linhas = conn.execute(
        "SELECT v.controle, v.leitura_id, vr.pergunta_id, vr.arquivo_canonico, vr.pagina_final,"
        "       r.resposta, r.trecho_literal"
        "  FROM verificacao_respostas vr"
        "  JOIN verificacoes v ON v.id = vr.verificacao_id AND v.vigente"
        "  JOIN respostas r ON r.execucao_id = v.execucao_id AND r.pergunta_id = vr.pergunta_id"
        " WHERE vr.veredito = 'APROVADO' AND vr.pergunta_id = ANY(%s) AND v.leitura_id IS NOT NULL"
        " ORDER BY vr.pergunta_id, v.controle", (list(PERGUNTAS),)).fetchall()
    cache, casos, conta = {}, [], {p: 0 for p in PERGUNTAS}
    for x in linhas:
        pid = x["pergunta_id"]
        if maximo and conta[pid] >= maximo:
            continue
        if x["pagina_final"] is None or not x["arquivo_canonico"]:
            continue
        lid = x["leitura_id"]
        if lid not in cache:
            cache.clear()
            cache[lid] = conn.execute(
                "SELECT arquivo_nome, numero, texto FROM paginas WHERE leitura_id = %s"
                " ORDER BY ordem, arquivo_nome, numero", (lid,)).fetchall()
        paginas = cache[lid]
        if not any(p["arquivo_nome"] == x["arquivo_canonico"] and p["numero"] == x["pagina_final"]
                   for p in paginas):
            continue
        valor, hora = R69.alvo(pid, x["resposta"])
        if valor is None:
            continue
        conta[pid] += 1
        casos.append({"x": x, "pid": pid, "alvo": valor, "hora": hora,
                      "paginas": [(p["arquivo_nome"], p["numero"], p["texto"] or "") for p in paginas]})
    return casos


def _trechos(caso: dict, marcas: dict) -> list[dict]:
    """marcas = {(pagina_idx, fonte): [(cid, ini, fim)]} -> [{arquivo, paginas: [{pagina, texto}]}]"""
    por_arq: dict = {}
    for (k, fonte), ms in sorted(marcas.items()):
        arq, num, texto = caso["paginas"][k]
        base = texto if fonte == "bruto" else R69._norm_texto(texto)
        pag = {"pagina": num, "texto": "\n…\n".join(janelas(base, ms, ENTORNO))}
        if fonte == "norm":
            pag["texto_normalizado"] = True
        por_arq.setdefault(arq, []).append(pag)
    return [{"arquivo": a, "paginas": ps} for a, ps in por_arq.items()]


def _estado(pid: str, caso: dict, marcas: dict) -> str:
    return json.dumps({"tarefa": TAREFA[pid], "trechos": _trechos(caso, marcas)}, ensure_ascii=False)


def montar(caso: dict) -> dict:
    """Candidatos distintos da leitura inteira (com poda) e os lotes de requests."""
    pid, controle = caso["pid"], caso["x"]["controle"]
    ordem, occ = [], {}                    # valor -> [(pagina_idx, fonte, i, f)]
    for k, (arq, num, texto) in enumerate(caso["paginas"]):
        for v, fonte, i, f in sorted(ocorrencias_da_pagina(pid, controle, texto), key=lambda o: o[2]):
            if v not in occ:
                occ[v] = []
                ordem.append(v)
            occ[v].append((k, fonte, i, f))
    larg = 2 if len(ordem) < 100 else 3
    ids = {v: "c%0*d" % (larg, n + 1) for n, v in enumerate(ordem)}

    def marcas_de(vs, lim=None):
        mm: dict = {}
        for v in vs:
            for k, fonte, i, f in (occ[v] if lim is None or v not in lim else occ[v][:lim[v]]):
                mm.setdefault((k, fonte), []).append((ids[v], i, f))
        return mm

    # tamanho REAL do state de cada candidato sozinho (janelas unidas); a soma é o
    # limite superior de um lote, porque candidatos vizinhos ainda dividem janela
    base = len(_estado(pid, caso, {}))
    tam, cortes = {}, {}
    for v in ordem:
        t = len(_estado(pid, caso, marcas_de([v]))) - base
        if t + base > MAX_ESTADO:          # um valor sozinho estoura: fica com as 1ªs ocorrências
            n = len(occ[v])
            while n > 1 and len(_estado(pid, caso, marcas_de([v], {v: n}))) > MAX_ESTADO:
                n = max(1, int(n * 0.8))
            cortes[v] = len(occ[v]) - n
            occ[v] = occ[v][:n]
            t = len(_estado(pid, caso, marcas_de([v]))) - base
        tam[v] = t
    lotes, atual, soma = [], [], base
    for v in ordem:
        if atual and (len(atual) >= MAX_NOULS or soma + tam[v] > MAX_ESTADO):
            lotes.append(atual)
            atual, soma = [], base
        atual.append(v)
        soma += tam[v]
    if atual:
        lotes.append(atual)

    requests = []
    for lote in lotes:
        estado = _estado(pid, caso, marcas_de(lote))
        lids = [ids[v] for v in lote]
        perguntas = {ids[v]: noul_candidato(pid, ids[v], rotulo(pid, v)) for v in lote}
        perguntas["nenhum"] = noul_nenhum(pid, lids)
        requests.append({"estado": estado, "perguntas": perguntas, "ids": lids})
    return {"ordem": ordem, "ids": ids, "occ": occ, "requests": requests, "cortes": cortes,
            "norm": sum(1 for v in ordem for o in occ[v] if o[1] == "norm")}


def trecho_de(caso: dict, occ: list, raio: int = 220) -> dict | None:
    if not occ:
        return None
    k, fonte, i, f = occ[0]
    arq, num, texto = caso["paginas"][k]
    base = texto if fonte == "bruto" else R69._norm_texto(texto)
    return {"arquivo": arq, "pagina": num,
            "trecho": _limpar(base[max(0, i - raio):f + raio])}


# ==================================================================== rodada
def rodar(casos: list[dict], caixa: Caixa, fios: int, parou: list) -> list[dict]:
    montados = [montar(c) for c in casos]

    def um(par):
        caso, m = par
        p, nenhum, falhas, usd, tok = {}, [], [], 0.0, 0
        for rq in m["requests"]:
            try:
                ans, uso = caixa.perguntar(rq["estado"], rq["perguntas"])
            except TetoAtingido as e:        # resposta incompleta não entra na medição
                parou.append(str(e))
                return None
            except jev.ErroJev as e:
                falhas.append("%s %s" % (e, (e.corpo or "")[:120]))
                continue
            usd += uso["usd"]
            tok += uso["input_tokens"]
            for cid in rq["ids"]:
                p[cid] = jev.valor(ans.get(cid) or {})
            nenhum.append(jev.valor(ans.get("nenhum") or {}))
        return avaliar(caso, m, p, [x for x in nenhum if x is not None], falhas, usd, tok)

    with ThreadPoolExecutor(fios) as ex:
        return [r for r in ex.map(um, zip(casos, montados)) if r is not None]


def avaliar(caso, m, p, nenhum, falhas, usd, tok) -> dict:
    pid, x = caso["pid"], caso["x"]
    inv = {cid: v for v, cid in m["ids"].items()}
    opcoes = [(cid, pp) for cid, pp in p.items() if pp is not None]
    p_nenhum = min(nenhum) if nenhum else None
    if p_nenhum is not None:
        opcoes.append(("nenhum", p_nenhum))
    opcoes.sort(key=lambda t: -t[1])
    alvo = caso["alvo"]
    cid_alvo = m["ids"].get(alvo)
    r = {"controle": x["controle"], "pergunta": pid,
         "citada": "%s p.%s" % (x["arquivo_canonico"], x["pagina_final"]),
         "alvo": rotulo(pid, alvo), "resposta": (x["resposta"] or "")[:220],
         "n_candidatos": len(m["ordem"]), "n_ocorrencias": sum(len(o) for o in m["occ"].values()),
         "ocorrencias_normalizadas": m["norm"], "ocorrencias_cortadas": sum(m["cortes"].values()),
         "requests": len(m["requests"]), "usd": round(usd, 6), "tokens": tok, "falhas": falhas,
         "alvo_entre_candidatos": cid_alvo is not None,
         "p_nenhum": p_nenhum,
         "candidatos": [{"id": m["ids"][v], "valor": rotulo(pid, v), "p": p.get(m["ids"][v]),
                         "ocorrencias": len(m["occ"][v])} for v in m["ordem"]]}
    if pid == "Q1":
        r["hora_da_resposta"] = caso["hora"]
    if not opcoes:
        r["escolhido"] = None
        return r
    esc, pe = opcoes[0]
    seg, ps = opcoes[1] if len(opcoes) > 1 else (None, 0.0)
    r.update({"escolhido": inv.get(esc, "nenhum") if esc != "nenhum" else "nenhum",
              "escolhido_id": esc, "p_escolhido": pe,
              "segundo": (inv.get(seg, "nenhum") if seg != "nenhum" else "nenhum") if seg else None,
              "p_segundo": ps, "margem": round(pe - ps, 4),
              "p_alvo": p.get(cid_alvo) if cid_alvo else None,
              "posicao_alvo": next((n + 1 for n, (c, _) in enumerate(opcoes) if c == cid_alvo), None)})
    r["escolhido"] = rotulo(pid, r["escolhido"]) if r["escolhido"] != "nenhum" else "nenhum"
    r["segundo"] = rotulo(pid, r["segundo"]) if r["segundo"] not in (None, "nenhum") else r["segundo"]
    r["concorda"] = esc == cid_alvo
    # A regra de código que a nota deixa para depois ("qual das datas vale é código"):
    # entre as datas convictas (p >= CORTE), a MAIS TARDIA — retificação adia. Custa zero:
    # é só outra leitura das mesmas probabilidades.
    if pid == "Q1":
        conv = [inv[c] for c, pp in opcoes if c != "nenhum" and pp >= CORTE]
        if conv:
            regra = max(conv, key=lambda d: (d[6:], d[3:5], d[:2]))
            r["regra_codigo"] = regra
            r["concorda_regra"] = regra == alvo
        else:
            r["regra_codigo"] = r["escolhido"]
            r["concorda_regra"] = r["concorda"]
        r["convictos"] = conv
    if not r["concorda"]:
        r["trecho_escolhido"] = trecho_de(caso, m["occ"].get(inv.get(esc))) if esc != "nenhum" else None
        r["trecho_alvo"] = trecho_de(caso, m["occ"].get(alvo)) if cid_alvo else None
        r["trecho_aprovado"] = (x["trecho_literal"] or "")[:300]
    return r


# =================================================================== julgamento
# Preenchido À MÃO depois da rodada de 24/09/2026, lendo o trecho de cada lado
# (--rejulgar reaplica, sem chamar). Foram 5 discordâncias em 133 — as "10 piores" são
# todas. Classes: "aprovada errada" (defeito real) · "jev errou" (a aprovada está certa)
# · "duas sessões" (as duas datas são sessão; qual vale é precedência, código)
# · "sem sessão" (a aprovada não afirma sessão) · "candidato ausente" (a poda tirou o valor)
JULGAMENTO: dict = {
    ("Q1", "18307496000106-1-000041/2026"): (
        "sem sessão",
        "Sardoá/MG, credenciamento: a própria aprovada diz 'não há sessão pública de disputa' e põe à "
        "frente a data de início do recebimento (14/07/2026, até 14/07/2027). O 'nenhum' do Jev (0,87) "
        "está certo; foi o alvo() do 69_ que leu a data inicial como sessão."),
    ("Q1", "75392019000120-1-000050/2026"): (
        "duas sessões",
        "Credenciamento 04/2026: 'Abertura 01ª chamada: 08/09/2026' (edital) e 'Abertura 02ª chamada: "
        "28/09/2026' (aviso posterior). As duas são sessão; a aprovada (2ª) está certa pela precedência "
        "do aviso. Jev 0,84 na 1ª e 0,51 na 2ª: é o 'qual vale é código' da nota."),
    ("Q1", "23444680000138-1-000020/2026"): (
        "jev errou",
        "Quadro-resumo com OCR ruim: 'CADASTRAMENTO DE PROPOSTAS INÍCIO 18/09/2026 TÉRMINO 09/10/2026' e "
        "'ABERTURA 09/10/2026 08:00H / DISPUTA 09:00H'. O Jev ficou com o início do cadastramento (0,74) "
        "contra 0,66 na abertura — sem convicção, não abre revisão no corte 0,75."),
    ("Q5", "07598618000144-1-000096/2026"): (
        "jev errou",
        "Coreaú/CE: 'VALOR TOTAL ESTIMADO R$ 598.911,81' no preâmbulo é o que a Q5 pede (o rótulo é "
        "transcrito). Jev 0,48 nele e 0,59 no 'nenhum' — sem convicção."),
    ("Q5", "09074592000160-1-000032/2026"): (
        "candidato ausente",
        "O valor está numa tabela sem 'R$' ('60.000,00 | 60.000,00', TR 2.5); a poda do 69_ o tira e o "
        "Jev diz 'nenhum' com 0,84 — certo sobre o que recebeu. É o 1 de 63 que o passo zero previa."),
}


# ===================================================================== resumo
def _est(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return {"n": 0}
    q = lambda f: xs[min(len(xs) - 1, int(round(f * (len(xs) - 1))))]   # noqa: E731
    return {"n": len(xs), "media": round(statistics.mean(xs), 3), "p10": q(0.1),
            "mediana": round(statistics.median(xs), 3), "p90": q(0.9)}


CORTES = ((0.0, 0.0), (0.5, 0.0), (0.75, 0.0), (0.75, 0.25), (0.9, 0.0), (0.9, 0.5))


def resumir(res: list[dict]) -> dict:
    out = {}
    for pid in PERGUNTAS:
        rs = [r for r in res if r["pergunta"] == pid and r.get("escolhido") is not None]
        n = len(rs)
        if not n:
            continue
        conc = sum(r["concorda"] for r in rs)
        lic = len({r["controle"] for r in rs})
        faixas = {}
        for a, b in ((0, 0.5), (0.5, 0.75), (0.75, 0.9), (0.9, 1.01)):
            g = [r for r in rs if a <= r["p_escolhido"] < b]
            faixas["%.2f-%.2f" % (a, min(b, 1))] = {"n": len(g), "concordam": sum(r["concorda"] for r in g)}
        cortes = []
        for pmin, mmin in CORTES:
            disp = [r for r in rs if r["p_escolhido"] >= pmin and r["margem"] >= mmin]
            rev = [r for r in disp if not r["concorda"]]
            jul = [JULGAMENTO.get((pid, r["controle"]), ("", ""))[0] for r in rev]
            cortes.append({"p_min": pmin, "margem_min": mmin, "disparam": len(disp),
                           "revisoes": len(rev), "revisoes_por_licitacao": round(len(rev) / lic, 3),
                           "silencio_concordante": len(disp) - len(rev),
                           "sem_sinal": n - len(disp),
                           "revisoes_defeito_real": sum(j == "aprovada errada" for j in jul),
                           "revisoes_julgadas": sum(bool(j) for j in jul),
                           # "nenhum" convicto diz "a regex não achou" ou "não há sessão", não
                           # "a aprovada está errada": sem ele, o que sobra é valor contra valor
                           "revisoes_sem_nenhum": sum(r["escolhido"] != "nenhum" for r in rev)})
        d = {"medidas": n, "licitacoes": lic, "concordam": conc, "pct": round(100.0 * conc / n, 1),
             "escolheu_nenhum": sum(r["escolhido"] == "nenhum" for r in rs),
             "alvo_fora_dos_candidatos": sum(not r["alvo_entre_candidatos"] for r in rs),
             "p_escolhido": _est([r["p_escolhido"] for r in rs]),
             "margem": _est([r["margem"] for r in rs]),
             "p_alvo": _est([r["p_alvo"] for r in rs]),
             "alvo_convicto": sum((r["p_alvo"] or 0) >= CORTE for r in rs),
             "candidatos_por_resposta": _est([r["n_candidatos"] for r in rs]),
             "requests": sum(r["requests"] for r in rs),
             "concordancia_por_faixa_de_p": faixas, "cortes": cortes,
             "falhas": sum(bool(r["falhas"]) for r in rs)}
        if pid == "Q1":
            d["regra_codigo_mais_tardia_entre_convictas"] = {
                "concordam": sum(r["concorda_regra"] for r in rs),
                "pct": round(100.0 * sum(r["concorda_regra"] for r in rs) / n, 1),
                "com_2_ou_mais_convictas": sum(len(r["convictos"]) >= 2 for r in rs)}
            # A mesma regra com corte 0,5 — ESCOLHIDA DEPOIS de ver as discordâncias (as duas
            # de Q1 com duas datas acima de 0,5). Custa zero, mas é ajuste: precisa de remedição
            # antes de valer (o sintético de "data retificada" é o teste natural).
            ok = 0
            for r in rs:
                acima = [c["valor"] for c in r["candidatos"] if (c["p"] or 0) >= 0.5]
                esc = max(acima, key=lambda x: (x[6:], x[3:5], x[:2])) if acima else r["escolhido"]
                ok += esc == r["alvo"]
            d["regra_codigo_mais_tardia_acima_de_0_5_pos_hoc"] = {"concordam": ok,
                                                                  "pct": round(100.0 * ok / n, 1)}
        disc = [r for r in rs if not r["concorda"]]
        d["discordancias"] = len(disc)
        d["julgamento"] = {}
        for r in disc:
            j = JULGAMENTO.get((pid, r["controle"]))
            if j:
                d["julgamento"][j[0]] = d["julgamento"].get(j[0], 0) + 1
        out[pid] = d
    return out


def piores(res: list[dict], n: int = 10) -> list[dict]:
    disc = [r for r in res if r.get("escolhido") is not None and not r["concorda"]]
    disc.sort(key=lambda r: (-r["p_escolhido"], -r["margem"]))
    return disc[:n]


def imprimir(res: list[dict], resumo: dict, caixa_info: dict) -> None:
    print("=" * 96)
    print("  R3 COM O JEV — segundo extrator por seleção (Q1 data, Q5 valor) · %s" % jev.MODELO)
    print("=" * 96)
    for pid, d in resumo.items():
        print()
        print("  %s — %d respostas APROVADAS em %d licitações · %d requests · %d falhas"
              % (pid, d["medidas"], d["licitacoes"], d["requests"], d["falhas"]))
        print("     concordância com a aprovada%s: %d/%d = %.1f%%   (escolheu 'nenhum': %d)"
              % (" (só a data)" if pid == "Q1" else "", d["concordam"], d["medidas"], d["pct"],
                 d["escolheu_nenhum"]))
        e, mg, pa = d["p_escolhido"], d["margem"], d["p_alvo"]
        print("     p do escolhido: mediana %.3f (p10 %.3f · p90 %.3f) · margem p/ o 2º: mediana %.3f (p10 %.3f)"
              % (e["mediana"], e["p10"], e["p90"], mg["mediana"], mg["p10"]))
        print("     p do valor aprovado: mediana %.3f (p10 %.3f) · convicto (>= %.2f) em %d/%d"
              % (pa["mediana"], pa["p10"], CORTE, d["alvo_convicto"], d["medidas"]))
        c = d["candidatos_por_resposta"]
        print("     candidatos distintos por resposta: mediana %s · p90 %s" % (c["mediana"], c["p90"]))
        print("     concordância por faixa de p do escolhido: " + " · ".join(
            "%s: %d/%d" % (k, v["concordam"], v["n"]) for k, v in d["concordancia_por_faixa_de_p"].items()))
        if pid == "Q1":
            rg = d["regra_codigo_mais_tardia_entre_convictas"]
            print("     regra de código (a mais tardia entre as convictas): %d/%d = %.1f%% · %d com 2+ convictas"
                  % (rg["concordam"], d["medidas"], rg["pct"], rg["com_2_ou_mais_convictas"]))
            r5 = d["regra_codigo_mais_tardia_acima_de_0_5_pos_hoc"]
            print("     a mesma regra com p >= 0,5 (escolhida DEPOIS de ver os dados): %d/%d = %.1f%%"
                  % (r5["concordam"], d["medidas"], r5["pct"]))
        print("     corte (p >= · margem >=)  disparam  revisões (sem 'nenhum')  por licitação"
              "  [julgadas: defeito real]")
        for ct in d["cortes"]:
            print("        %.2f · %.2f              %4d      %4d (%d)              %.3f        [%d: %d]"
                  % (ct["p_min"], ct["margem_min"], ct["disparam"], ct["revisoes"],
                     ct["revisoes_sem_nenhum"], ct["revisoes_por_licitacao"], ct["revisoes_julgadas"],
                     ct["revisoes_defeito_real"]))
        if d["julgamento"]:
            print("     julgamento à mão das discordâncias: %s" % d["julgamento"])
    print()
    print("  AS 10 PIORES DISCORDÂNCIAS (maior p no escolhido errado)")
    for r in piores(res):
        j = JULGAMENTO.get((r["pergunta"], r["controle"]))
        print("   · %s %s  aprovada %s (p=%s, %sº) × Jev %s (p=%.3f, margem %.3f)%s"
              % (r["pergunta"], r["controle"], r["alvo"],
                 "%.3f" % r["p_alvo"] if r["p_alvo"] is not None else "—", r["posicao_alvo"] or "—",
                 r["escolhido"], r["p_escolhido"], r["margem"],
                 ("  => %s: %s" % j) if j else ""))
        te, ta = r.get("trecho_escolhido"), r.get("trecho_alvo")
        if te:
            print("       Jev  (%s p.%s): %s" % (te["arquivo"][:40], te["pagina"], te["trecho"][:300].replace("\n", " ")))
        if ta:
            print("       aprov(%s p.%s): %s" % (ta["arquivo"][:40], ta["pagina"], ta["trecho"][:300].replace("\n", " ")))
    print()
    print("  custo: US$ %.5f anunciado (%s) · %d chamadas · %d tokens de entrada · %.2f caracteres/token"
          % (caixa_info["usd"], jev.FONTE_PRECO, caixa_info["chamadas"], caixa_info["tokens"],
             caixa_info["chars_por_token"] or 0))


# ======================================================================= main
def destino() -> str:
    return os.path.join(DESTINO, "r3_jev_selecao_%s.json" % datetime.date.today().isoformat())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seco", action="store_true", help="monta os requests e estima; NÃO chama")
    ap.add_argument("--rejulgar", action="store_true", help="relê o JSON salvo e reaplica JULGAMENTO")
    ap.add_argument("--max", type=int, default=0, help="no máximo N respostas por pergunta (piloto)")
    ap.add_argument("--fios", type=int, default=4)
    ap.add_argument("--teto-usd", type=float, default=0.07)
    ap.add_argument("--livro", default=None, help="JSON que soma o gasto entre execuções")
    ap.add_argument("--teto-livro", type=float, default=None, help="teto somado no livro")
    ap.add_argument("--saida", default=None)
    a = ap.parse_args()
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    arq = a.saida or destino()

    if a.rejulgar:
        d = json.load(io.open(arq, encoding="utf-8"))
        d["resumo"] = resumir(d["respostas"])
        d["julgamento_a_mao"] = [{"pergunta": k[0], "controle": k[1], "classe": v[0], "nota": v[1]}
                                 for k, v in JULGAMENTO.items()]
        d["piores"] = [r["pergunta"] + " " + r["controle"] for r in piores(d["respostas"])]
        imprimir(d["respostas"], d["resumo"], d["custo"])
        io.open(arq, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1))
        print("  regravado: %s (US$ 0 — só releitura)" % os.path.relpath(arq, RAIZ))
        return 0

    t0 = time.time()
    with psycopg.connect(R69._dsn(), row_factory=dict_row) as conn:
        conn.read_only = True
        casos = carregar_casos(conn, a.max)
    print("  %d respostas: %s" % (len(casos), {p: sum(c["pid"] == p for c in casos) for p in PERGUNTAS}),
          flush=True)

    if a.seco:
        tot_chars = tot_req = tot_q = 0
        for pid in PERGUNTAS:
            ms = [montar(c) for c in casos if c["pid"] == pid]
            ch = sum(len(r["estado"]) + len(json.dumps(r["perguntas"], ensure_ascii=False))
                     for m in ms for r in m["requests"])
            st = sum(len(r["estado"]) for m in ms for r in m["requests"])
            nq = sum(len(r["perguntas"]) for m in ms for r in m["requests"])
            rq = sum(len(m["requests"]) for m in ms)
            mx = max((len(r["estado"]) for m in ms for r in m["requests"]), default=0)
            fora = sum(1 for c, m in zip([c for c in casos if c["pid"] == pid], ms) if c["alvo"] not in m["ids"])
            print("  %s: %d requests · %d Nouls · state %d mil caracteres (maior %d) · total c/ perguntas"
                  " %d mil · normalizadas %d · cortadas %d · alvo fora dos candidatos %d"
                  % (pid, rq, nq, st // 1000, mx, ch // 1000, sum(m["norm"] for m in ms),
                     sum(sum(m["cortes"].values()) for m in ms), fora))
            tot_chars += ch
            tot_req += rq
            tot_q += nq
        print("  estimativa: ~%d mil tokens (a 1,98 car/token) = US$ %.4f · reserva (1,5 car/token) US$ %.4f"
              % (tot_chars / 1.98 / 1000, tot_chars / 1.98 * jev.PRECO_ENTRADA_ANUNCIADO / 1e6,
                 tot_chars / CHARS_POR_TOKEN_RESERVA * jev.PRECO_ENTRADA_ANUNCIADO / 1e6))
        print("  NENHUMA chamada feita.")
        return 0

    # Uma vez, na thread principal: segredos.carregar() marca-se carregado ANTES de ler o
    # arquivo, e uma thread concorrente veria a chave ausente (a corrida conhecida).
    segredos.carregar()
    caixa = Caixa(a.teto_usd, a.livro, a.teto_livro, "71_jev_r3_selecao")
    print("  limite desta execução: US$ %.4f (anterior no livro: US$ %.4f)" % (caixa.limite, caixa.anterior),
          flush=True)
    parou: list = []
    res = rodar(casos, caixa, a.fios, parou)
    interrompido = None
    if parou:
        interrompido = "%d respostas ficaram de fora no teto; 1ª: %s" % (len(parou), parou[0])
        print("  PAROU NO TETO: %s" % interrompido)
    info = {"usd": round(caixa.usd, 6), "chamadas": caixa.chamadas, "tokens": caixa.tokens,
            "falhas": caixa.falhas, "chars_enviados": caixa.chars_enviados,
            "chars_por_token": round(caixa.chars_enviados / caixa.tokens, 3) if caixa.tokens else None,
            "limite_usd": round(caixa.limite, 6), "livro_anterior_usd": caixa.anterior,
            "preco": jev.FONTE_PRECO, "interrompido": interrompido}
    if not res:
        print("  sem resultado; custo US$ %.5f" % caixa.usd)
        return 1
    resumo = resumir(res)
    imprimir(res, resumo, info)
    os.makedirs(DESTINO, exist_ok=True)
    io.open(arq, "w", encoding="utf-8").write(json.dumps({
        "medido_em": datetime.datetime.now().isoformat(timespec="seconds"),
        "script": "scripts/71_jev_r3_selecao.py", "modelo": jev.MODELO,
        "fonte": "Postgres v3 (api_ro): verificacoes vigentes, verificacao_respostas APROVADO, respostas,"
                 " paginas da leitura da verificação",
        "parametros": {"entorno": ENTORNO, "max_nouls_por_request": MAX_NOULS, "max_estado": MAX_ESTADO,
                       "corte": CORTE, "poda": "69_: Q1 ano >= ano da compra; Q5 'R$' colado antes",
                       "camadas_regex": "69_ camada completa (+grafia)", "max_por_pergunta": a.max,
                       "escolha": "maior p entre os candidatos e o 'nenhum' (nenhum = menor dos lotes)",
                       "tarefa": TAREFA,
                       "exemplo_perguntas": {"candidato": noul_candidato("Q5", "c01", "R$ 60.000,00"),
                                             "nenhum": noul_nenhum("Q5", ["c01", "c04"])}},
        "custo": info, "resumo": resumo,
        "piores": [r["pergunta"] + " " + r["controle"] for r in piores(res)],
        "julgamento_a_mao": [{"pergunta": k[0], "controle": k[1], "classe": v[0], "nota": v[1]}
                             for k, v in JULGAMENTO.items()],
        "respostas": res}, ensure_ascii=False, indent=1))
    print("  salvo: %s  (%.0f s)" % (os.path.relpath(arq, RAIZ), time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
