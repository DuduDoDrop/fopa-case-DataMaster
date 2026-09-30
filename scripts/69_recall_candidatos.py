# -*- coding: utf-8 -*-
"""
R3, passo zero — o valor aprovado está entre os candidatos que a regex acha?

    python 69_recall_candidatos.py [--k 6] [--entorno 200] [--hora 120]

NÃO CHAMA MODELO. Custo US$ 0. Lê o Postgres da v3 (papel api_ro, só leitura):
as verificações VIGENTES, as respostas APROVADAS de Q1 e Q5 e as páginas
CONGELADAS da leitura de cada verificação. Não escreve no banco. Grava a medição
em docs/medicoes/r3_recall_candidatos_<data>.json.

O QUE O R3 PROPÕE (Jev — casos de uso avaliados, R3)
  Um segundo extrator que não GERA o valor: SELECIONA entre candidatos que a
  regex acha na página (datas para a Q1, valores em reais para a Q5). O Jev
  escolhe, o código copia — "It cannot invent a value or transpose a digit".
  O preço disso é que o recall passa a ser da regex: se o valor certo não está
  entre os candidatos, o Jev não tem como escolhê-lo, e a discordância com o
  Claude vira revisão humana à toa.

A PERGUNTA, NO MOLDE DO 46_recall_recuperacao.py
  Uma resposta APROVADA tem trecho conferido na página citada; então a página
  citada é, por construção, uma página onde a resposta está. A pergunta vira
  aritmética: o valor que a resposta afirma está entre os candidatos que a regex
  acha naquela página? E quantos candidatos há — porque cada candidato a mais é
  uma chance a mais de a seleção errar.

CAMADAS DE CANDIDATOS (cumulativas; cada uma mede o que a anterior perde)
  Q1  verificador   \\d{2}/\\d{2}/\\d{4} no texto cru  (verificador.verificar_sanidade)
      +extenso      "21 de setembro de 2026"         (15_acuracia._datas_por_extenso / MESES)
      +grafia       16.09.2026 · 29 / 09 /2026 · 1/9/2026 · 1 7 / 0 9 / 2 0 2 6  (nova, só aqui)
  Q5  verificador   \\d{1,3}(?:\\.\\d{3})*,\\d{2}         (verificador.verificar_contra_api)
      +grafia       âncora de dígito (60000,00 não vira 000,00), R$ sem centavos,
                    dígito quebrado pelo OCR (2.236.436,1 6)            (nova, só aqui)

ESCOPOS (camada completa)
  citada        a página que a resposta aprovada cita          — o passo zero pedido
  top-k         as páginas que o BM25 da PRÓPRIA pergunta traz (k=6 + SEMPRE_INCLUIR)
  leitura       todas as páginas congeladas da licitação
  leitura·poda  a leitura, com o corte que o código faz sem olhar a resposta
                (Q1: ano da data >= ano da compra; Q5: valor com "R$" colado antes)
  O R3 de produção não pode usar a página citada pelo Claude se quiser ser um
  extrator INDEPENDENTE; os outros escopos mostram o que custa não usar.

Q1 TEM HORA
  O candidato é a data; a hora vem do entorno. Mede-se se a hora da resposta
  está a ±120 caracteres da data certa e quantas vezes há MAIS DE UMA hora ali
  (propostas até 08h00, abertura 08h30, disputa 09h00) — o que decide se a
  discordância de hora pode abrir revisão.
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
import time
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

from fopa import extrator, questionario                           # noqa: E402
from fopa import recuperacao as rec                               # noqa: E402
from fopa import verificador                                      # noqa: E402

DESTINO = os.path.join(RAIZ, "docs", "medicoes")
# o teto de `state` que o worker aplica (api/jev.py, MAX_CHARS_STATE; 32k tokens)
TETO_ESTADO = 63_000
POR_ID = {p.id: p for p in questionario.PERGUNTAS}
PERGUNTAS = ("Q1", "Q5")


def _carregar_acuracia():
    """MESES e `_datas_por_extenso` do 15_acuracia.py, sem copiá-los (molde do 34_placar)."""
    spec = importlib.util.spec_from_file_location(
        "acuracia15", os.path.join(AQUI, "15_acuracia.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ACURACIA = _carregar_acuracia()
MESES = ACURACIA.MESES                    # "janeiro" -> "01" (sem acento: "marco")


def _dsn() -> str:
    """Mesmo caminho do 65_jev_ausencia.py. A senha nunca é impressa."""
    if os.environ.get("FOPA_DSN_LEITURA"):
        return os.environ["FOPA_DSN_LEITURA"]
    env = {}
    with io.open(os.path.join(RAIZ, "docker", ".env"), encoding="utf-8") as f:
        for l in f:
            if "=" in l and not l.lstrip().startswith("#"):
                k, _, v = l.strip().partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    return "postgresql://api_ro:%s@127.0.0.1:5433/fopa" % env["API_RO_PASSWORD"]


# ======================================================================= datas
# Camada "verificador": a regex de partida do R3 (verificador.verificar_sanidade).
RE_DATA_VERIFICADOR = re.compile(r"\d{2}/\d{2}/\d{4}")
# Camada "+grafia": separador ponto/hífen, espaço em volta da barra, dia e mês
# de um dígito, ordinal "1o de" (o "1º" depois do NFKD). NOVA — não havia no pacote.
RE_DATA_GRAFIA = re.compile(
    r"(?<![\d/.])(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})(?![\d/])")
RE_DATA_EXTENSO_ORDINAL = re.compile(
    r"\b(\d{1,2})o?\s+de\s+(%s)\s+de\s+(\d{4})\b" % "|".join(MESES))
# só para classificar falha — "16 de setembro" / "16/09" sem ano por perto
RE_DIA_MES_SEM_ANO = re.compile(
    r"(?<![\d/.])(\d{1,2})\s*(?:/|\.|\s+de\s+)\s*(\d{1,2}|%s)(?!\s*(?:/|\.|-|de)\s*\d)"
    % "|".join(MESES))
# dígitos que o OCR separou um a um ("1 7 / 0 9 / 2 0 2 6", "0 9 h 4 5"): só a
# sequência de dígitos ISOLADOS é juntada — "2026 09:00" fica como está.
RE_OCR_ESPACADO = re.compile(r"(?<!\d)\d(?: \d)+(?!\d)")


def _juntar_ocr(s: str) -> str:
    return RE_OCR_ESPACADO.sub(lambda m: m.group(0).replace(" ", ""), s)


def _data_valida(d: int, m: int, a: int) -> bool:
    return 1 <= d <= 31 and 1 <= m <= 12 and 1900 <= a <= 2100


def _fmt_data(d, m, a) -> str | None:
    d, m, a = int(d), int(m), int(a)
    return "%02d/%02d/%04d" % (d, m, a) if _data_valida(d, m, a) else None


def _norm_texto(texto: str) -> str:
    """
    O `norm` do 15_acuracia SEM a reescrita de hora: ascii, minúsculas, o mesmo
    filtro de caracteres, e o `_datas_por_extenso` dele ("21 de setembro de 2026"
    -> "21/09/2026").

    A reescrita de hora do `norm` ("9h" -> "09:00") estraga justamente o que a Q1
    precisa ler: "08hs20min" vira "08:00s20min" e "10h 05 min" vira "10:00 05 min".
    O hífen fica (o `norm` o tira), para "16-09-2026" continuar sendo data.
    """
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9.,%:/\- ]+", " ", s)
    return ACURACIA._datas_por_extenso(re.sub(r"\s+", " ", s).strip())


def candidatos_data(texto: str) -> dict:
    """
    Candidatos a data de uma página, por camada.

    Devolve {"camadas": {nome: set(dd/mm/aaaa)}, "ocorrencias": [(valor, ini, fim)],
    "origem": {valor: a primeira regra que o achou}, "norm": texto normalizado
    (onde as posições valem)}.
    """
    bruto = texto or ""
    norm = _norm_texto(bruto)
    origem: dict = {}
    c0 = {v for v in RE_DATA_VERIFICADOR.findall(bruto) if _fmt_data(*v.split("/"))}
    for v in c0:                                                    # 99/99/9999 não é data
        origem[v] = "verificador"
    c1 = set(c0)
    for m in RE_DATA_VERIFICADOR.finditer(norm):                    # extenso já virou dd/mm/aaaa
        v = _fmt_data(*m.group(0).split("/"))
        if v:
            c1.add(v)
            origem.setdefault(v, "data por extenso")
    c2 = set(c1)
    ocorr = []
    for m in RE_DATA_GRAFIA.finditer(norm):
        v = _fmt_data(*m.groups())
        if v:
            c2.add(v)
            ocorr.append((v, m.start(), m.end()))
            g = m.group(0)
            origem.setdefault(v, "separador ponto ou hífen (16.09.2026)" if "." in g or "-" in g else
                              "espaço no separador (29 / 09 /2026)" if " " in g else
                              "dia ou mês com um dígito (1/9/2026)")
    for m in RE_DATA_EXTENSO_ORDINAL.finditer(norm):                # "1o de outubro de 2026"
        v = _fmt_data(m.group(1), MESES[m.group(2)], m.group(3))
        if v:
            c2.add(v)
            ocorr.append((v, m.start(), m.end()))
            origem.setdefault(v, "extenso com ordinal (1º de outubro de 2026)")
    junto = _juntar_ocr(norm)
    if junto != norm:
        vistos = {v for v, _, _ in ocorr}
        for m in RE_DATA_GRAFIA.finditer(junto):
            v = _fmt_data(*m.groups())
            if v and v not in vistos:
                c2.add(v)
                # posição aproximada no texto normalizado (o passe juntou dígitos)
                ocorr.append((v, min(m.start(), len(norm) - 1), min(m.end(), len(norm))))
                origem.setdefault(v, "dígitos espaçados pelo OCR (1 7 / 0 9 / 2 0 2 6)")
    ocorr = _sem_sobreposicao(ocorr)
    return {"camadas": {"verificador": c0, "+extenso": c1, "+grafia": c2},
            "ocorrencias": ocorr, "origem": origem, "norm": norm}


# ================================================================= valores (R$)
# Camada "verificador": a regex de verificador.verificar_contra_api, sem âncora
# (é assim que ela roda lá: "60000,00" devolve "000,00").
RE_VALOR_VERIFICADOR = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
# Camada "+grafia" (NOVA): âncora de dígito, inteiro sem separador de milhar,
# R$ sem centavos, e o passe que junta dígito que o OCR separou com espaço.
RE_VALOR_ANCORADO = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d+),(\d{2})(?!\d)")
RE_VALOR_SEM_CENTAVOS = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})+|\d+)(?![\d.]|,\s*\d)")
RE_ESPACO_NUMERICO = re.compile(r"(?<=[\d.,]) (?=[\d.,])")
RE_VALOR_RESPOSTA = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})")


def _centavos(inteiro: str, cent: str = "00") -> int:
    return int(re.sub(r"\D", "", inteiro) or "0") * 100 + int(cent or "0")


def fmt_reais(c: int) -> str:
    inteiro, cent = divmod(int(c), 100)
    return "%s,%02d" % ("{:,}".format(inteiro).replace(",", "."), cent)


def candidatos_valor(texto: str) -> dict:
    bruto = texto or ""
    c0 = {_centavos(*v.split(",")) for v in RE_VALOR_VERIFICADOR.findall(bruto)}
    origem = {v: "verificador" for v in c0}
    ocorr = []
    c1 = set(c0)
    for m in RE_VALOR_ANCORADO.finditer(bruto):
        v = _centavos(m.group(1), m.group(2))
        c1.add(v)
        ocorr.append((v, m.start(), m.end()))
        origem.setdefault(v, "inteiro sem separador de milhar (60000,00)")
    for m in RE_VALOR_SEM_CENTAVOS.finditer(bruto):
        v = _centavos(m.group(1))
        c1.add(v)
        ocorr.append((v, m.start(1), m.end()))           # o número, sem o "R$" (a poda o procura antes)
        origem.setdefault(v, "R$ sem centavos (R$ 60.000)")
    junto = RE_ESPACO_NUMERICO.sub("", bruto)
    if junto != bruto:
        vistos = {v for v, _, _ in ocorr}
        for m in RE_VALOR_ANCORADO.finditer(junto):
            v = _centavos(m.group(1), m.group(2))
            if v not in vistos:
                c1.add(v)
                ocorr.append((v, min(m.start(), len(bruto) - 1), min(m.end(), len(bruto))))
                origem.setdefault(v, "dígito separado pelo OCR (2.236.436,1 6)")
    ocorr = _sem_sobreposicao(ocorr)
    return {"camadas": {"verificador": c0, "+grafia": c1}, "ocorrencias": ocorr,
            "origem": origem, "norm": bruto}


def _sem_sobreposicao(ocorr: list) -> list:
    """Uma ocorrência por trecho do texto: a mesma data achada por duas regex conta uma vez."""
    saida, fim = [], -1
    for v, i, f in sorted(ocorr, key=lambda x: (x[1], -x[2])):
        if i < fim:
            continue
        saida.append((v, i, f))
        fim = f
    return saida


CANDIDATOS = {"Q1": candidatos_data, "Q5": candidatos_valor}
ESCOPOS = ("citada", "top-k", "leitura", "leitura·poda")
CAMADAS = {"Q1": ("verificador", "+extenso", "+grafia"), "Q5": ("verificador", "+grafia")}


# ================================================================ valor-alvo
def _n(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


SEM_ALVO = ("nao ha", "nao localiz", "sem sessao", "sem valor", "o edital nao", "o aviso nao",
            "nao existe", "inexistente")


def alvo(pid: str, resposta: str):
    """
    O valor que a resposta aprovada AFIRMA, normalizado — ou None, quando ela não
    afirma um (credenciamento sem sessão, contratação sem valor).

    Q1: a data do começo da resposta ("DD/MM/AAAA às HHhMM", o formato pedido).
    Q5: o primeiro "R$ X,YY" da resposta, salvo quando ela abre negando o valor.
    """
    r = resposta or ""
    if verificador.nao_encontrou(r) or _n(r).startswith(SEM_ALVO):
        return None, None
    if pid == "Q1":
        m = re.match(r"\W{0,3}(\d{2})/(\d{2})/(\d{4})", r)
        if not m:
            return None, None
        h = re.search(r"\b(\d{1,2})h(\d{2})\b", r[:40])
        return _fmt_data(*m.groups()), ("%02d:%s" % (int(h.group(1)), h.group(2)) if h else None)
    m = RE_VALOR_RESPOSTA.search(r)
    return (_centavos(m.group(1), m.group(2)) if m else None), None


# ======================================================================= hora
# "09:00", "9h", "09h30", "09hr00min", "08hs15min", "às 10 horas", "09h:30min".
# O ":" exige minutos ("ANEXO 1:" não é hora); o "h" não pode abrir palavra
# ("2 habitantes" também não).
RE_HORA = re.compile(
    r"(?<![\d/.,])(\d{1,2})\s*(?:h(?:rs?|s|oras?)?(?![a-z])\s*:?\s*(\d{2})?|:\s*(\d{2}))(?![\d/])")


def horas_no_entorno(norm: str, ocorr: list, valor: str, raio: int) -> set:
    """As horas que aparecem até `raio` caracteres de cada ocorrência da data `valor`."""
    horas = set()
    for v, i, f in ocorr:
        if v != valor:
            continue
        janela = _juntar_ocr(norm[max(0, i - raio):f + raio])   # "0 9 h 4 5" -> "09 h 45"
        for m in RE_HORA.finditer(janela):
            hh, mm = int(m.group(1)), int(m.group(2) or m.group(3) or 0)
            if hh <= 23 and mm <= 59:
                horas.add("%02d:%02d" % (hh, mm))
    return horas


# ==================================================================== poda
def passa_poda(pid: str, controle: str, texto: str, ocorrencia: tuple) -> bool:
    """
    O corte que o código pode fazer ANTES do Jev, sem olhar a resposta.

    Q1: data com ano >= o ano da compra (o número de controle termina em /AAAA).
        Tira a lei de 2021, a portaria de 2023, a certidão de 2025.
    Q5: valor escrito com "R$" colado antes. Tira preço unitário de tabela,
        percentual, índice, número de artigo com vírgula.
    """
    v, i, _ = ocorrencia
    if pid == "Q1":
        return int(v[-4:]) >= int(controle[-4:])
    return re.search(r"R\$\s*$", texto[max(0, i - 8):i]) is not None


# ================================================================== estado
def chars_de_estado(ocorr: list, tamanho: int, entorno: int) -> int:
    """Caracteres do estado que o R3 mandaria: ±entorno de cada candidato, janelas unidas."""
    total, fim = 0, -1
    for _, i, f in sorted(ocorr, key=lambda x: x[1]):
        a, b = max(0, i - entorno), min(tamanho, f + entorno)
        if a < fim:
            a = fim
        if b > a:
            total += b - a
            fim = b
    return total


# =============================================================== classificação
def classificar_falha(pid: str, valor, pagina_texto: str, cand_outras_paginas: dict) -> str:
    """Por que o valor aprovado não está entre os candidatos da página citada."""
    em_outra = [k for k, c in cand_outras_paginas.items() if valor in c]
    if pid == "Q1":
        d, m, a = valor.split("/")
        norm = _norm_texto(pagina_texto)
        for x in RE_DIA_MES_SEM_ANO.finditer(norm):
            dd, mm = x.group(1), x.group(2)
            mm = MESES.get(mm, mm)
            if dd.isdigit() and mm.isdigit() and int(dd) == int(d) and int(mm) == int(m):
                return "data sem ano na página citada"
        if em_outra:
            return "data só em outra página da leitura"
        return "data ausente da leitura (inferida ou fora das páginas congeladas)"
    # Q5
    digitos = str(valor // 100)
    if em_outra:
        return "valor só em outra página da leitura"
    if digitos in re.sub(r"\D", "", pagina_texto):
        return "valor na página em grafia que a regex não pega"
    if re.search(r"milh[aoõ]|mil reais|reais\)", _n(pagina_texto)):
        return "valor por extenso na página (sem algarismos)"
    return "valor ausente da leitura"


# ==================================================================== medição
def _estat(xs: list) -> dict:
    if not xs:
        return {"n": 0}
    xs = sorted(xs)
    return {"n": len(xs), "media": round(statistics.mean(xs), 1), "mediana": statistics.median(xs),
            "p90": xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))], "max": xs[-1]}


def _pct(a: int, b: int) -> float | None:
    return round(100.0 * a / b, 1) if b else None


def medir(conn, k: int, entorno: int, raio_hora: int) -> dict:
    linhas = conn.execute(
        "SELECT v.controle, v.leitura_id, vr.pergunta_id, vr.arquivo_canonico, vr.pagina_final,"
        "       vr.ausencia, r.resposta, r.trecho_literal"
        "  FROM verificacao_respostas vr"
        "  JOIN verificacoes v ON v.id = vr.verificacao_id AND v.vigente"
        "  JOIN respostas r ON r.execucao_id = v.execucao_id AND r.pergunta_id = vr.pergunta_id"
        " WHERE vr.veredito = 'APROVADO' AND vr.pergunta_id = ANY(%s)"
        " ORDER BY v.controle, vr.pergunta_id", (list(PERGUNTAS),)).fetchall()

    cache_leitura: dict = {}

    def leitura(lid: int):
        if lid not in cache_leitura:
            pags = conn.execute("SELECT arquivo_nome, numero, texto FROM paginas WHERE leitura_id = %s"
                                " ORDER BY ordem, arquivo_nome, numero", (lid,)).fetchall()
            paginas = [rec.Pagina(p["arquivo_nome"], p["numero"], p["texto"]) for p in pags]
            cand = {pid: {(p.arquivo, p.numero): CANDIDATOS[pid](p.texto) for p in paginas}
                    for pid in PERGUNTAS}
            indice = rec.IndiceBM25(paginas)
            # posição de cada página no ranking BM25 da pergunta (1 = a primeira)
            posicao = {pid: {(paginas[i].arquivo, paginas[i].numero): n + 1 for n, (i, _) in
                             enumerate(indice.pontuar(rec.consulta_da_pergunta(POR_ID[pid])))}
                       for pid in PERGUNTAS}
            cache_leitura.clear()                    # uma leitura por vez na memória
            cache_leitura[lid] = (paginas, indice, cand, posicao)
        return cache_leitura[lid]

    res = {pid: {"aprovadas": 0, "sem_leitura": 0, "sem_pagina": 0, "sem_alvo": [], "casos": []}
           for pid in PERGUNTAS}
    for x in linhas:
        pid = x["pergunta_id"]
        R = res[pid]
        R["aprovadas"] += 1
        if x["leitura_id"] is None:
            R["sem_leitura"] += 1
            continue
        if x["pagina_final"] is None or not x["arquivo_canonico"]:
            R["sem_pagina"] += 1
            continue
        paginas, indice, cand, posicao = leitura(x["leitura_id"])
        chave = (x["arquivo_canonico"], x["pagina_final"])
        if chave not in cand[pid]:
            R["sem_pagina"] += 1
            continue
        valor, hora = alvo(pid, x["resposta"])
        if valor is None:
            R["sem_alvo"].append({"controle": x["controle"], "resposta": (x["resposta"] or "")[:160]})
            continue
        ultima = CAMADAS[pid][-1]
        c_cit = cand[pid][chave]
        texto_cit = next(p.texto for p in paginas if (p.arquivo, p.numero) == chave)
        por_camada = {cam: valor in c_cit["camadas"][cam] for cam in CAMADAS[pid]}

        # escopos
        topk = {(p.arquivo, p.numero) for p in
                rec.paginas_para_pergunta(indice, POR_ID[pid], k=k, sempre=extrator.SEMPRE_INCLUIR)}
        escopos = {}
        for nome, chaves, podar in (("citada", [chave], False), ("top-k", sorted(topk), False),
                                    ("leitura", list(cand[pid].keys()), False),
                                    ("leitura·poda", list(cand[pid].keys()), True)):
            vals, n_occ, chars = set(), 0, 0
            for ch in chaves:
                c = cand[pid][ch]
                occ = [o for o in c["ocorrencias"]
                       if not podar or passa_poda(pid, x["controle"], c["norm"], o)]
                vals |= {o[0] for o in occ}
                n_occ += len(occ)
                chars += chars_de_estado(occ, len(c["norm"]), entorno)
            escopos[nome] = {"paginas": len(chaves), "cobre": valor in vals, "distintos": len(vals),
                             "ocorrencias": n_occ, "chars_estado": chars}

        caso = {"controle": x["controle"], "arquivo": chave[0], "pagina": chave[1],
                "valor": valor if pid == "Q1" else fmt_reais(valor),
                "por_camada": por_camada, "escopos": escopos,
                "candidatos_citada": sorted(c_cit["camadas"][ultima]) if pid == "Q1"
                else [fmt_reais(v) for v in sorted(c_cit["camadas"][ultima])]}
        if pid == "Q1":
            horas = horas_no_entorno(c_cit["norm"], c_cit["ocorrencias"], valor, raio_hora)
            caso["hora"] = hora
            caso["horas_no_entorno"] = sorted(horas)
            caso["hora_no_entorno"] = (hora in horas) if hora else None
        # ---- falhas, cada uma no ponto em que acontece
        falhas = []
        if not por_camada["verificador"] and por_camada[ultima]:
            falhas.append({"onde": "regex de partida (camada verificador)",
                           "tipo": c_cit["origem"].get(valor, "?")})
        if not por_camada[ultima]:
            outras = {"%s p.%d" % ch: cand[pid][ch]["camadas"][ultima]
                      for ch in cand[pid] if ch != chave}
            falhas.append({"onde": "página citada (camada completa)",
                           "tipo": classificar_falha(pid, valor, texto_cit, outras),
                           "outras_paginas": [k2 for k2, c in outras.items() if valor in c][:5]})
        if not escopos["top-k"]["cobre"] and escopos["leitura"]["cobre"]:
            onde = [ch for ch in cand[pid] if valor in {o[0] for o in cand[pid][ch]["ocorrencias"]}]
            melhor = min(posicao[pid][ch] for ch in onde)
            falhas.append({"onde": "top-k do BM25 da pergunta",
                           "tipo": "a página com o valor fica fora do top-%d" % k
                                   + (" (é a pág. 1, a capa)" if chave[1] == 1 else ""),
                           "posicao_bm25_pagina_citada": posicao[pid][chave],
                           "melhor_posicao_com_o_valor": melhor})
        if escopos["leitura"]["cobre"] and not escopos["leitura·poda"]["cobre"]:
            falhas.append({"onde": "poda por código",
                           "tipo": "data com ano anterior ao da compra" if pid == "Q1"
                           else "valor sem R$ colado antes (tabela)"})
        if falhas:
            caso["falhas"] = falhas
            caso["trecho"] = (x["trecho_literal"] or "")[:240]
        R["casos"].append(caso)
    return res


def resumir(pid: str, R: dict) -> dict:
    casos = R["casos"]
    n = len(casos)
    cam = CAMADAS[pid]
    ultima = cam[-1]
    cob = {c: sum(x["por_camada"][c] for x in casos) for c in cam}
    cit = [x["escopos"]["citada"] for x in casos]
    out = {
        "aprovadas": R["aprovadas"],
        "sem_leitura_congelada": R["sem_leitura"],
        "sem_pagina_citada": R["sem_pagina"],
        "sem_valor_alvo": len(R["sem_alvo"]),
        "com_valor_alvo": n,
        "cobertura_pagina_citada": {c: {"cobre": cob[c], "pct": _pct(cob[c], n)} for c in cam},
        "candidatos_pagina_citada": {
            "ocorrencias": _estat([e["ocorrencias"] for e in cit]),
            "distintos": _estat([e["distintos"] for e in cit]),
            # o piso que qualquer seletor tem de bater: sortear entre os distintos
            "acerto_por_sorteio_pct": round(100.0 * statistics.mean(
                [(1.0 / e["distintos"]) if e["cobre"] and e["distintos"] else 0.0 for e in cit]), 1)
            if cit else None},
        "escopos": {},
        "falhas": {},
    }
    for f in (f for x in casos for f in x.get("falhas", [])):
        grupo = out["falhas"].setdefault(f["onde"], {})
        grupo[f["tipo"]] = grupo.get(f["tipo"], 0) + 1
    for nome in ESCOPOS:
        es = [x["escopos"][nome] for x in casos]
        d = {"cobre": sum(e["cobre"] for e in es), "pct": _pct(sum(e["cobre"] for e in es), n),
             "paginas": _estat([e["paginas"] for e in es]),
             "distintos": _estat([e["distintos"] for e in es]),
             "ocorrencias": _estat([e["ocorrencias"] for e in es]),
             "chars_estado": _estat([e["chars_estado"] for e in es]),
             "ocorrencias_total": sum(e["ocorrencias"] for e in es),
             "acima_do_teto_de_estado": sum(e["chars_estado"] > TETO_ESTADO for e in es),
             "chars_estado_total": sum(e["chars_estado"] for e in es)}
        out["escopos"][nome] = d
    if pid == "Q1":
        com_hora = [x for x in casos if x.get("hora") and x["por_camada"][ultima]]
        out["hora"] = {
            "respostas_com_hora_e_data_coberta": len(com_hora),
            "hora_certa_no_entorno": sum(bool(x["hora_no_entorno"]) for x in com_hora),
            "data_certa_com_mais_de_uma_hora_por_perto": sum(len(x["horas_no_entorno"]) > 1
                                                             for x in com_hora)}
    return out


# ===================================================================== saída
def _linha_estat(e: dict) -> str:
    if not e.get("n"):
        return "—"
    return "média %5.1f · mediana %4s · p90 %4s · máx %4s" % (e["media"], e["mediana"], e["p90"], e["max"])


def imprimir(resumo: dict, res: dict, entorno: int, raio_hora: int) -> None:
    print("=" * 88)
    print("  R3 · PASSO ZERO — o valor aprovado está entre os candidatos da regex?")
    print("=" * 88)
    print("  Postgres v3 (api_ro, só leitura) · verificações vigentes · páginas congeladas")
    for pid in PERGUNTAS:
        s = resumo[pid]
        cam = CAMADAS[pid]
        print()
        print("  %s — %s" % (pid, POR_ID[pid].texto))
        print("  " + "-" * 86)
        print("  aprovadas %d · sem leitura congelada %d · sem página %d · sem valor-alvo %d"
              " · MEDIDAS %d" % (s["aprovadas"], s["sem_leitura_congelada"], s["sem_pagina_citada"],
                                 s["sem_valor_alvo"], s["com_valor_alvo"]))
        print()
        print("  cobertura na PÁGINA CITADA, camadas cumulativas:")
        for c in cam:
            x = s["cobertura_pagina_citada"][c]
            print("     %-12s %3d/%-3d  %5.1f%%" % (c, x["cobre"], s["com_valor_alvo"], x["pct"] or 0))
        cc = s["candidatos_pagina_citada"]
        print()
        print("  candidatos na página citada (camada %s):" % cam[-1])
        print("     ocorrências    %s" % _linha_estat(cc["ocorrencias"]))
        print("     distintos      %s" % _linha_estat(cc["distintos"]))
        print("     acerto por sorteio entre os distintos: %.1f%% (o piso do seletor)"
              % (cc["acerto_por_sorteio_pct"] or 0))
        print()
        print("  por ESCOPO (camada %s; estado = ±%d caracteres por candidato, janelas unidas):"
              % (cam[-1], entorno))
        print("     poda (%s)" % ("ano da data >= ano da compra" if pid == "Q1" else "valor com R$ colado antes"))
        print("     %-13s %11s %5s  %-44s" % ("escopo", "cobre", "págs", "valores distintos"))
        for nome in ESCOPOS:
            e = s["escopos"][nome]
            print("     %-13s %3d %6.1f%% %5s  %s"
                  % (nome, e["cobre"], e["pct"] or 0, e["paginas"].get("mediana", "—"),
                     _linha_estat(e["distintos"])))
        print("     %-13s %-44s %s" % ("", "ocorrências (= Nouls)", "caracteres de estado"))
        for nome in ESCOPOS:
            e = s["escopos"][nome]
            print("     %-13s md %4s · p90 %4s · máx %5s        md %6s · p90 %6s · máx %6s"
                  % (nome, e["ocorrencias"].get("mediana"), e["ocorrencias"].get("p90"),
                     e["ocorrencias"].get("max"), e["chars_estado"].get("mediana"),
                     e["chars_estado"].get("p90"), e["chars_estado"].get("max")))
        e = s["escopos"]["leitura·poda"]
        print("     somado nas %d respostas (leitura·poda): %d ocorrências, %d mil caracteres de estado;"
              " %d acima do teto de estado (%d mil caracteres)"
              % (s["com_valor_alvo"], e["ocorrencias_total"], round(e["chars_estado_total"] / 1000),
                 e["acima_do_teto_de_estado"], TETO_ESTADO // 1000))
        if pid == "Q1":
            h = s["hora"]
            print()
            print("  hora (±%d caracteres de cada ocorrência da data certa, na página citada):" % raio_hora)
            print("     a hora da resposta está por perto: %d de %d"
                  % (h["hora_certa_no_entorno"], h["respostas_com_hora_e_data_coberta"]))
            print("     a data certa tem MAIS DE UMA hora por perto: %d de %d"
                  % (h["data_certa_com_mais_de_uma_hora_por_perto"], h["respostas_com_hora_e_data_coberta"]))
        print()
        print("  FALHAS, classificadas no ponto em que acontecem:")
        if not s["falhas"]:
            print("     nenhuma")
        for onde, tipos in s["falhas"].items():
            print("     %s — %d" % (onde, sum(tipos.values())))
            for t, n in sorted(tipos.items(), key=lambda kv: -kv[1]):
                print("       %3d  %s" % (n, t))
            if onde.startswith("top-k"):
                fs = [f for x in res[pid]["casos"] for f in x.get("falhas", []) if f["onde"] == onde]
                pos = sorted(f["posicao_bm25_pagina_citada"] for f in fs)
                mel = sorted(f["melhor_posicao_com_o_valor"] for f in fs)
                print("            posição no BM25 da pergunta — página citada: mediana %s (%s a %s);"
                      " melhor página com o valor: mediana %s (%s a %s)"
                      % (statistics.median(pos), pos[0], pos[-1], statistics.median(mel), mel[0], mel[-1]))
        for x in res[pid]["casos"]:
            for f in x.get("falhas", []):
                if f["onde"].startswith(("página citada", "poda")):
                    print("       · %s  %s p.%s  valor %s — %s"
                          % (x["controle"], x["arquivo"][:30], x["pagina"], x["valor"], f["tipo"]))
                    if f.get("outras_paginas"):
                        print("         também em: %s" % ", ".join(f["outras_paginas"][:3]))
        if res[pid]["sem_alvo"]:
            print()
            print("  sem valor-alvo (a resposta aprovada não afirma %s):" % ("data de sessão" if pid == "Q1" else "valor"))
            for x in res[pid]["sem_alvo"]:
                print("       · %s  %s" % (x["controle"], x["resposta"][:70]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=6, help="k do BM25 (o do extrator é 6)")
    ap.add_argument("--entorno", type=int, default=200, help="± caracteres por candidato no estado")
    ap.add_argument("--hora", type=int, default=120, help="± caracteres para achar a hora da Q1")
    a = ap.parse_args()
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    t0 = time.time()
    with psycopg.connect(_dsn(), row_factory=dict_row) as conn:
        conn.read_only = True
        res = medir(conn, a.k, a.entorno, a.hora)
    resumo = {pid: resumir(pid, res[pid]) for pid in PERGUNTAS}
    imprimir(resumo, res, a.entorno, a.hora)

    os.makedirs(DESTINO, exist_ok=True)
    destino = os.path.join(DESTINO, "r3_recall_candidatos_%s.json" % datetime.date.today().isoformat())
    json.dump({"medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "script": "scripts/69_recall_candidatos.py",
               "fonte": "Postgres v3 (api_ro): verificacoes vigentes, verificacao_respostas APROVADO,"
                        " respostas, paginas da leitura da verificação",
               "parametros": {"k": a.k, "sempre_incluir": list(extrator.SEMPRE_INCLUIR),
                              "entorno_chars": a.entorno, "raio_hora_chars": a.hora,
                              "camadas": {pid: list(CAMADAS[pid]) for pid in PERGUNTAS}},
               "custo_usd": 0.0,
               "resumo": resumo,
               "casos": {pid: res[pid]["casos"] for pid in PERGUNTAS},
               "sem_valor_alvo": {pid: res[pid]["sem_alvo"] for pid in PERGUNTAS}},
              io.open(destino, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print()
    print("  salvo: %s  (%.0f s)" % (os.path.relpath(destino, RAIZ), time.time() - t0))
    print("  custo em API de modelo: US$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
