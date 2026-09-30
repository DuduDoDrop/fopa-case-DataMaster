# -*- coding: utf-8 -*-
"""
R4 com o Jev — o "sustenta?" apontado para o OUTRO documento da licitação.

    python 72_jev_r4_conflito.py --seco                monta tudo, conta caracteres, NÃO chama
    python 72_jev_r4_conflito.py --teto-usd 0.03 [--livro caixa.json --teto-livro 0.10]

CHAMA O JEV (frações de centavo; teto DURO). Lê o Postgres da v3 (api_ro, só leitura)
e, onde a licitação não tem páginas congeladas, o TEXTO JÁ EXTRAÍDO em amostras/
(o .txt do pdftotext ao lado do PDF, amostras/<pasta>/texto-extraido/, ou um cache
de OCR que já exista em saidas/). Nenhum OCR novo: PDF sem texto extraído fica de
fora, e isso é contado. Não escreve em banco nem em amostras/saidas. Grava a medição
em docs/medicoes/r4_jev_conflito_<data>.json.

O GABARITO — as 13 licitações da medição da RN-13 (Regras de negócio)
  A amostra de então: as 7 ABERTAS (Capão do Cipó, Pirapó, Quevedos, Adrianópolis,
  Bertioga, Fruta de Leite, Rio Azul — saidas/_benchmark.json) e as 6 do lote do
  Opus (São Lourenço do Sul, Santa Efigênia, Rio Branco, Jaboatão, Santo Antônio do
  Pinhal, Paulo Bento — saidas/_lote_claude-opus-5.json). Pirapó/RS e Quevedos/RS
  têm de sair "contradiz" convicto na Q2 (D-011, D-012: a minuta não enumera a
  população que o edital licita). As outras 11 têm de ficar quietas. Rio Azul/PR e
  Jaboatão/PE saíram da amostra (D-013, D-014: não eram compra de folha) e não têm
  texto nem resposta em lugar nenhum — ficam "não medidas".

O QUE SE PERGUNTA — o critério MEDIDO do 64_ (PERGUNTA/CRITERIOS), sem reescrever
  O state é o do api/jev.py corpo_sustenta com a TROCA: no lugar da página citada vão
  páginas de OUTRO documento. O `trecho_citado` sai, porque ele é da página citada —
  mandá-lo daria ao Jev justamente a evidência que sustenta, e o "sustenta" viria dele.

      {"afirmacao": <Q2 aprovada>, "pergunta_respondida": "O que diz o Objeto do Edital ?",
       "onde": "<outro arquivo>, páginas a e b (outro documento da mesma licitação)",
       "paginas_do_outro_documento": "=== PÁGINA a ===\\n...\\n\\n=== PÁGINA b ===\\n..."}

QUAL É O "OUTRO DOCUMENTO" — duas camadas, decididas antes de rodar
  A (a da nota): top-2 do BM25 da Q2 em cada OUTRO arquivo; e, no arquivo citado, as
    páginas a 3 ou mais da citada — é onde mora a minuta quando vem no mesmo PDF,
    como em Pirapó (p. 18) e Quevedos (p. 35), que têm um arquivo só ou quase.
  B (o localizador da RN-13): as páginas que ABREM uma definição de objeto
    (verificador.RE_OBJETO com "folha" na janela), menos a citada. Separa falha de
    SELEÇÃO de página (A não levou a página) de falha de JULGAMENTO (o Jev leu e não viu).
  Controle: a própria página citada, com o trecho — o corpo_sustenta original. Tem de
  dar "sustenta"; se não der, a troca não quer dizer nada.

  Dispara (revisão): "contradiz" com confiança >= 0,75 (CONVICCAO do api/jev.py).
"""
from __future__ import annotations

import argparse
import datetime
import difflib
import glob
import importlib.util
import io
import json
import os
import re
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

from fopa import jev, questionario, segredos, verificador         # noqa: E402
from fopa import recuperacao as rec                               # noqa: E402


def _carregar(nome: str, arquivo: str):
    spec = importlib.util.spec_from_file_location(nome, os.path.join(AQUI, arquivo))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_64 = _carregar("ancoragem64", "64_jev_ancoragem.py")           # PERGUNTA e CRITERIOS medidos
_71 = _carregar("selecao71", "71_jev_r3_selecao.py")            # Caixa (teto duro) e _dsn

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")
DESTINO = os.path.join(RAIZ, "docs", "medicoes")
Q2 = next(p for p in questionario.PERGUNTAS if p.id == "Q2")
CONVICCAO = 0.75                  # 1 - api/jev.py CONVICCAO
DISTANCIA_MESMO_ARQUIVO = 3       # no arquivo citado, "outro documento" = páginas a >= 3 da citada
MAX_ESTADO = 55_000
MIN_CHARS_PAGINA = 80             # abaixo disso a página não tem texto que se leia

# (pasta em amostras/, controle PNCP, município, o que o gabarito espera)
LICITACOES = [
    ("ABERTO Concorrencia - Eletronica - Capao do Cipo-RS", "04213779000184-1-000304/2026", "Capão do Cipó/RS", "quieta"),
    ("ABERTO Concorrencia - Eletronica - Pirapo-RS", "91553941000108-1-000039/2026", "Pirapó/RS", "contradiz"),
    ("ABERTO Concorrencia - Eletronica - Quevedos-RS", "94444122000110-1-000073/2026", "Quevedos/RS", "contradiz"),
    ("ABERTO Pregao - Eletronico - Adrianopolis-PR", "76105642000117-1-000027/2026", "Adrianópolis/PR", "quieta"),
    ("ABERTO Pregao - Eletronico - Bertioga-SP", "68020916000147-1-000190/2026", "Bertioga/SP", "quieta"),
    ("ABERTO Pregao - Eletronico - Fruta de Leite-MG", "01612483000148-1-000037/2026", "Fruta de Leite/MG", "quieta"),
    ("ABERTO Pregao - Eletronico - Rio Azul-PR", None, "Rio Azul/PR", "quieta"),
    ("Concorrencia - Eletronica - Sao Lourenco do Sul-RS", "87893111000152-1-000381/2026", "São Lourenço do Sul/RS", "quieta"),
    ("Pregao - Eletronico - Santo Antonio do Pinhal-SP", "45701455000172-1-000034/2026", "Santo Antônio do Pinhal/SP", "quieta"),
    ("Pregao - Presencial - Paulo Bento-RS", "04215168000175-1-000044/2025", "Paulo Bento/RS", "quieta"),
    ("Credenciamento - Santa Efigenia de Minas-MG", "18307462000111-1-000029/2026", "Santa Efigênia de Minas/MG", "quieta"),
    ("Dispensa - Rio Branco-AC", "04035135000143-1-000015/2026", "Rio Branco/AC (TCE-AC)", "quieta"),
    ("Inexigibilidade - Jaboatao dos Guararapes-PE", "10377679000196-1-000221/2026", "Jaboatão dos Guararapes/PE", "quieta"),
]

# OCR que JÁ EXISTE em disco (não se roda OCR aqui): pasta -> {prefixo do arquivo: json}
OCR_EXISTENTE = {
    "Concorrencia - Eletronica - Sao Lourenco do Sul-RS": {"01": os.path.join(SAIDAS, "_ocr_sao_lourenco.json")},
}
# A resposta da Q2 de Bertioga: Bertioga não tem verificação na v3 (baixada_ok); vale a
# execução de referência do harness (Opus 5 · high, ancorada), como no gabarito.
HARNESS_BERTIOGA = os.path.join(SAIDAS, "_harness_ABERTO Pregao - Eletronico - Bertioga-SP.json")


# ================================================================== textos
def _limpar(s: str) -> str:
    s = re.sub(r"[ \t\r\v]{2,}", " ", s or "")
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def _prefixo(nome: str) -> str:
    m = re.match(r"\s*(\d+)\s*-", nome)
    return m.group(1).zfill(2) if m else ""


def textos_da_pasta(pasta: str) -> tuple[dict, list]:
    """
    {arquivo: [texto da página 1, 2, ...]} com o texto JÁ extraído, e a lista do que
    ficou de fora (PDF sem texto: exigiria OCR novo). Duplicata de conteúdo sai.
    """
    base = os.path.join(AMOSTRAS, pasta)
    docs, fora, vistos = {}, [], {}
    if not os.path.isdir(base):
        return docs, [{"arquivo": "(pasta inexistente em amostras/)", "motivo": "sem texto em disco"}]
    extraidos = {_prefixo(os.path.basename(f)): f
                 for f in glob.glob(os.path.join(base, "texto-extraido", "*.txt"))}
    for pdf in sorted(glob.glob(os.path.join(base, "*.pdf"))):
        nome = os.path.basename(pdf)
        stem = nome[:-4]
        txt, origem = os.path.join(base, stem + ".txt"), None
        paginas = None
        ocr = OCR_EXISTENTE.get(pasta, {}).get(_prefixo(nome))
        if os.path.exists(txt) and os.path.getsize(txt) > 200:
            paginas, origem = io.open(txt, encoding="utf-8", errors="replace").read().split("\f"), \
                "amostras/.../" + stem + ".txt (pdftotext)"
        elif _prefixo(nome) in extraidos and os.path.getsize(extraidos[_prefixo(nome)]) > 200:
            f = extraidos[_prefixo(nome)]
            paginas, origem = io.open(f, encoding="utf-8", errors="replace").read().split("\f"), \
                "amostras/.../texto-extraido/" + os.path.basename(f)
        elif ocr and os.path.exists(ocr):
            d = json.load(io.open(ocr, encoding="utf-8"))
            paginas, origem = list(d["paginas"]), "saidas/" + os.path.basename(ocr) + " (OCR já existente)"
        if not paginas:
            fora.append({"arquivo": nome, "motivo": "sem texto extraído (exigiria OCR novo)"})
            continue
        while paginas and not paginas[-1].strip():
            paginas.pop()
        chave = hash("".join(paginas))
        if chave in vistos:
            fora.append({"arquivo": nome, "motivo": "duplicata de " + vistos[chave]})
            continue
        vistos[chave] = nome
        docs[nome] = {"paginas": paginas, "origem": origem}
    return docs, fora


def textos_do_postgres(conn, controle: str) -> dict:
    l = conn.execute("SELECT id FROM leituras WHERE controle = %s AND vigente ORDER BY id DESC LIMIT 1",
                     (controle,)).fetchone()
    if not l:
        return {}
    docs: dict = {}
    for p in conn.execute("SELECT arquivo_nome, numero, texto FROM paginas WHERE leitura_id = %s"
                          " ORDER BY ordem, arquivo_nome, numero", (l["id"],)).fetchall():
        d = docs.setdefault(p["arquivo_nome"], {"paginas": [], "origem": "Postgres v3, leitura %d" % l["id"]})
        while len(d["paginas"]) < p["numero"] - 1:
            d["paginas"].append("")
        d["paginas"].append(p["texto"] or "")
    return docs


def casar_arquivo(citado: str, nomes: list[str]) -> str | None:
    """O arquivo citado pela v3 no disco: mesmo nome, ou mesmo prefixo 'NN -' e nome mais parecido."""
    if not citado:
        return None
    stem = re.sub(r"\.pdf$", "", citado, flags=re.I)
    for n in nomes:
        if re.sub(r"\.pdf$", "", n, flags=re.I) == stem:
            return n
    mesmos = [n for n in nomes if _prefixo(n) == _prefixo(citado)]
    if not mesmos:
        return None
    return max(mesmos, key=lambda n: difflib.SequenceMatcher(None, n.lower(), citado.lower()).ratio())


# ================================================================== resposta Q2
def resposta_q2(conn, controle: str | None, pasta: str) -> dict | None:
    if controle:
        r = conn.execute(
            "SELECT vr.veredito, vr.arquivo_canonico, vr.pagina_final, vr.alertas, r.resposta, r.trecho_literal"
            "  FROM verificacoes v"
            "  JOIN verificacao_respostas vr ON vr.verificacao_id = v.id AND vr.pergunta_id = 'Q2'"
            "  JOIN respostas r ON r.execucao_id = v.execucao_id AND r.pergunta_id = 'Q2'"
            " WHERE v.controle = %s AND v.vigente", (controle,)).fetchone()
        if r:
            return {"resposta": r["resposta"], "trecho": r["trecho_literal"], "arquivo": r["arquivo_canonico"],
                    "pagina": r["pagina_final"], "veredito": r["veredito"],
                    "rn13_na_v3": any("RN-13" in a for a in (r["alertas"] or [])),
                    "fonte": "Postgres v3 (verificação vigente)"}
    if "Bertioga" in pasta and os.path.exists(HARNESS_BERTIOGA):
        e = json.load(io.open(HARNESS_BERTIOGA, encoding="utf-8"))["execucoes"][0]
        ev = e["evidencia"]["Q2"]
        return {"resposta": e["respostas"]["Q2"], "trecho": ev["trecho"], "arquivo": ev["arquivo"],
                "pagina": ev["pagina"], "veredito": "APROVADO (harness)", "rn13_na_v3": None,
                "fonte": "saidas/_harness_…Bertioga-SP.json, execução '%s'" % e["rotulo"]}
    return None


# ================================================================== páginas
def define_objeto(texto: str) -> bool:
    """O localizador da RN-13 (verificador.verificar_objeto): abre uma definição de objeto de folha."""
    for m in verificador.RE_OBJETO.finditer(texto or ""):
        if verificador.RE_DEFINE_FOLHA.search(verificador._normalizar(texto[m.start():m.start() + 600])):
            return True
    return False


def selecionar(docs: dict, citado: str | None, pag_citada: int | None) -> dict:
    """{"A": [(arquivo, [páginas])], "B": [(arquivo, [páginas])]} — ver o docstring do módulo."""
    paginas = [rec.Pagina(a, i + 1, t) for a, d in docs.items() for i, t in enumerate(d["paginas"])
               if len((t or "").strip()) >= MIN_CHARS_PAGINA]
    if not paginas:
        return {"A": [], "B": []}
    idx = rec.IndiceBM25(paginas)
    ranking = [(paginas[i], s) for i, s in idx.pontuar(rec.consulta_da_pergunta(Q2)) if s > 0]
    A, B = [], []
    for arq in docs:
        if arq == citado and pag_citada:
            elig = [p for p, _ in ranking if p.arquivo == arq
                    and abs(p.numero - pag_citada) >= DISTANCIA_MESMO_ARQUIVO]
        else:
            elig = [p for p, _ in ranking if p.arquivo == arq]
        if elig:
            A.append((arq, sorted(p.numero for p in elig[:2])))
        defs = [p for p, _ in ranking if p.arquivo == arq and define_objeto(p.texto)
                and not (arq == citado and p.numero == pag_citada)]
        if defs:
            B.append((arq, sorted(p.numero for p in defs[:3])))
    return {"A": A, "B": B}


def _marcar(docs, arq, nums, teto) -> str:
    partes = ["=== PÁGINA %d ===\n%s" % (n, _limpar(docs[arq]["paginas"][n - 1])) for n in nums]
    texto = "\n\n".join(partes)
    return texto if len(texto) <= teto else texto[:teto]


def estado_outro(q2: dict, docs: dict, arq: str, nums: list[int]) -> str:
    base = {"afirmacao": q2["resposta"], "pergunta_respondida": Q2.texto,
            "onde": "%s, página%s %s (outro documento da mesma licitação)"
                    % (arq, "s" if len(nums) > 1 else "", " e ".join(str(n) for n in nums))}
    folga = MAX_ESTADO - len(json.dumps(base, ensure_ascii=False)) - 200
    base["paginas_do_outro_documento"] = _marcar(docs, arq, nums, folga)
    return json.dumps(base, ensure_ascii=False)


def estado_controle(q2: dict, docs: dict, arq: str) -> str:
    """O corpo_sustenta original, só com a página citada."""
    base = {"afirmacao": q2["resposta"], "pergunta_respondida": Q2.texto, "trecho_citado": q2["trecho"],
            "onde": "%s, página %s" % (q2["arquivo"], q2["pagina"])}
    folga = MAX_ESTADO - len(json.dumps(base, ensure_ascii=False)) - 200
    base["documento"] = _marcar(docs, arq, [q2["pagina"]], folga)
    return json.dumps(base, ensure_ascii=False)


PERGUNTAS_JEV = {"relacao": jev.escolha(_64.PERGUNTA, _64.CRITERIOS)}


# ==================================================================== montagem
def montar(conn) -> list[dict]:
    casos = []
    for pasta, controle, municipio, esperado in LICITACOES:
        c = {"pasta": pasta, "controle": controle, "municipio": municipio, "esperado": esperado,
             "requests": [], "fora": []}
        q2 = resposta_q2(conn, controle, pasta)
        docs = textos_do_postgres(conn, controle) if controle else {}
        if not docs:
            docs, c["fora"] = textos_da_pasta(pasta)
        c["fontes"] = {a: d["origem"] for a, d in docs.items()}
        if not q2 or not docs:
            c["nao_medida"] = ("sem resposta da Q2" if not q2 else "") + \
                              (" e " if not q2 and not docs else "") + ("sem texto em disco" if not docs else "")
            casos.append(c)
            continue
        citado = casar_arquivo(q2["arquivo"], list(docs))
        c["q2"] = {k: v for k, v in q2.items() if k != "resposta"}
        c["q2"]["resposta"] = (q2["resposta"] or "")[:600]
        c["q2"]["arquivo_local"] = citado
        pag = q2["pagina"] if isinstance(q2["pagina"], int) else None
        sel = selecionar(docs, citado, pag)
        c["selecao"] = {k: [{"arquivo": a, "paginas": ns} for a, ns in v] for k, v in sel.items()}
        if citado and pag and len((docs[citado]["paginas"][pag - 1] if pag <= len(docs[citado]["paginas"])
                                   else "").strip()) >= MIN_CHARS_PAGINA:
            c["requests"].append({"camada": "controle", "arquivo": citado, "paginas": [pag],
                                  "estado": estado_controle(q2, docs, citado)})
        else:
            c["controle_ausente"] = "página citada sem texto extraído (%s p.%s)" % (q2["arquivo"], q2["pagina"])
        feitos = {}
        for camada in ("A", "B"):
            for arq, nums in sel[camada]:
                chave = (arq, tuple(nums))
                if chave in feitos:                     # mesma página nas duas camadas: uma chamada só
                    c["requests"].append({"camada": camada, "arquivo": arq, "paginas": nums,
                                          "igual_a": feitos[chave]})
                    continue
                feitos[chave] = len(c["requests"])
                c["requests"].append({"camada": camada, "arquivo": arq, "paginas": nums,
                                      "estado": estado_outro(q2, docs, arq, nums)})
        casos.append(c)
    return casos


# ===================================================================== rodada
def rodar(casos: list[dict], caixa) -> None:
    for c in casos:
        for rq in c["requests"]:
            if "estado" not in rq:
                continue
            try:
                ans, uso = caixa.perguntar(rq["estado"], PERGUNTAS_JEV)
            except _71.TetoAtingido as e:
                rq["erro"] = "teto: %s" % e
                continue
            except jev.ErroJev as e:
                rq["erro"] = "%s %s" % (e, (e.corpo or "")[:160])
                continue
            r = ans.get("relacao") or {}
            rq.update({"escolha": r.get("choice"), "confianca": r.get("confidence"),
                       "probabilidades": r.get("probabilities"), "usd": uso["usd"],
                       "tokens": uso["input_tokens"], "chars_estado": len(rq["estado"])})
        for rq in c["requests"]:                        # as repetidas herdam a resposta
            if "igual_a" in rq:
                o = c["requests"][rq["igual_a"]]
                for k in ("escolha", "confianca", "probabilidades", "erro"):
                    if k in o:
                        rq[k] = o[k]


# Julgado À MÃO depois da rodada de 24/09/2026, lendo as páginas (--rejulgar reaplica, US$ 0).
JULGAMENTO = {
    "Pirapó/RS": (
        "não pegou",
        "O Jev leu a página certa: a Cláusula Primeira da minuta (EDITAL p. 18) diz só 'servidores "
        "públicos municipais dos Poderes Executivo e Legislativo' contra 'ativos, inativos e "
        "pensionistas da Prefeitura, Câmara e FAPS'. Disse sustenta 0,77 (B); no TR p. 1, sustenta "
        "0,74. Omitir população não é 'afirmar o oposto' no critério do 64_."),
    "Quevedos/RS": (
        "não pegou",
        "EDITAL p. 35, Cláusula Primeira da minuta: 'folha de pagamento dos servidores públicos e "
        "demais beneficiários' contra '(ativos, inativos, pensionistas e estagiários)'. sustenta 0,70 "
        "(B) e 0,88 (A, p. 31+35)."),
    "São Lourenço do Sul/RS": (
        "verdadeiro, já sinalizado",
        "O edital ORIGINAL (digitalizado, superado pelo 05) diz 1.925 servidores; o vigente, 1.782. "
        "Contradição real, de NÚMERO e contra versão superada — o extrator já a relatou como "
        "conflito na Q2 (REVISAR) e a RN-36 deixa divergência de número para o código. Seria uma "
        "revisão repetida."),
    "Paulo Bento/RS": (
        "falso, abaixo do corte",
        "TR (EDITAL p. 22): 'aproximado de 156 matrículas'; a resposta: 143 do Executivo + 13 do "
        "Legislativo — soma 156. Não há contradição; o Jev não soma ('not a calculator'). "
        "contradiz 0,63 (A) e 0,73 (B), abaixo de 0,75."),
}


def dispara(rq: dict, escolha: str = "contradiz") -> bool:
    return rq.get("escolha") == escolha and (rq.get("confianca") or 0) >= CONVICCAO


def resumir(casos: list[dict]) -> dict:
    medidas = [c for c in casos if "nao_medida" not in c]
    out = {"licitacoes": len(casos), "medidas": len(medidas),
           "nao_medidas": [{"municipio": c["municipio"], "motivo": c["nao_medida"]} for c in casos
                           if "nao_medida" in c]}
    for nome, camadas in (("A", {"A"}), ("B", {"B"}), ("A+B", {"A", "B"})):
        vp = fp = fn = vn = 0
        for c in medidas:
            sinal = any(dispara(r) for r in c["requests"] if r["camada"] in camadas)
            if c["esperado"] == "contradiz":
                vp += sinal
                fn += not sinal
            else:
                fp += sinal
                vn += not sinal
        chamadas = [r for c in medidas for r in c["requests"] if r["camada"] in camadas and "igual_a" not in r]
        out["camada_" + nome] = {
            "pegou_os_2": "%d/2" % vp, "quietas": "%d/%d" % (vn, vn + fp), "falsos_positivos": fp,
            "chamadas": len(chamadas),
            "contradiz_convicto": sum(dispara(r) for r in chamadas),
            "nada_diz_convicto": sum(dispara(r, "nada_diz") for r in chamadas),
            "sustenta": sum(r.get("escolha") == "sustenta" for r in chamadas)}
    ctl = [r for c in medidas for r in c["requests"] if r["camada"] == "controle"]
    out["controle_pagina_citada"] = {"n": len(ctl), "sustenta": sum(r.get("escolha") == "sustenta" for r in ctl),
                                     "sem_texto_da_citada": sum("controle_ausente" in c for c in medidas)}
    return out


def imprimir(casos: list[dict], resumo: dict, info: dict) -> None:
    print("=" * 100)
    print("  R4 COM O JEV — 'sustenta?' contra o OUTRO documento · Q2 · critério do 64_ · %s" % jev.MODELO)
    print("=" * 100)
    for c in casos:
        print()
        print("  %s  [gabarito: %s]" % (c["municipio"], c["esperado"]))
        if "nao_medida" in c:
            print("     NÃO MEDIDA — %s" % c["nao_medida"])
            continue
        q = c["q2"]
        print("     Q2 (%s, %s): %s p.%s · RN-13 na v3: %s"
              % (q["fonte"][:34], q["veredito"], (q["arquivo"] or "")[:48], q["pagina"], q["rn13_na_v3"]))
        print("     resposta: %s" % q["resposta"][:150].replace("\n", " "))
        if c.get("controle_ausente"):
            print("     controle: %s" % c["controle_ausente"])
        for rq in c["requests"]:
            marca = " <== DISPARA" if dispara(rq) else ""
            if "erro" in rq:
                print("     %-8s %-50s p.%-8s ERRO %s" % (rq["camada"], rq["arquivo"][:50],
                                                           ",".join(map(str, rq["paginas"])), rq["erro"][:60]))
                continue
            pr = rq.get("probabilidades") or {}
            print("     %-8s %-50s p.%-8s %-9s %.2f  (s %.2f · c %.2f · n %.2f)%s"
                  % (rq["camada"], rq["arquivo"][:50], ",".join(map(str, rq["paginas"])),
                     rq.get("escolha"), rq.get("confianca") or 0, pr.get("sustenta", 0),
                     pr.get("contradiz", 0), pr.get("nada_diz", 0), marca))
        for f in c["fora"]:
            print("     fora: %s — %s" % (f["arquivo"][:60], f["motivo"]))
        if c["municipio"] in JULGAMENTO:
            print("     => %s: %s" % JULGAMENTO[c["municipio"]])
    print()
    print("-" * 100)
    print("  %d de %d licitações medidas; não medidas: %s"
          % (resumo["medidas"], resumo["licitacoes"],
             ", ".join("%s (%s)" % (x["municipio"], x["motivo"]) for x in resumo["nao_medidas"]) or "—"))
    for k in ("camada_A", "camada_B", "camada_A+B"):
        d = resumo[k]
        print("  %-10s pegou %s · quietas %s · %d chamadas: contradiz convicto %d · nada_diz convicto %d · sustenta %d"
              % (k, d["pegou_os_2"], d["quietas"], d["chamadas"], d["contradiz_convicto"],
                 d["nada_diz_convicto"], d["sustenta"]))
    ct = resumo["controle_pagina_citada"]
    print("  controle (página citada, corpo_sustenta original): sustenta %d/%d · sem texto da citada: %d"
          % (ct["sustenta"], ct["n"], ct["sem_texto_da_citada"]))
    print("  custo: US$ %.5f anunciado · %d chamadas · %d tokens · %.2f caracteres/token"
          % (info["usd"], info["chamadas"], info["tokens"], info["chars_por_token"] or 0))


# ======================================================================= main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seco", action="store_true", help="monta os requests e estima; NÃO chama")
    ap.add_argument("--rejulgar", action="store_true", help="relê o JSON salvo e reaplica JULGAMENTO")
    ap.add_argument("--teto-usd", type=float, default=0.03)
    ap.add_argument("--livro", default=None)
    ap.add_argument("--teto-livro", type=float, default=None)
    a = ap.parse_args()
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    arq = os.path.join(DESTINO, "r4_jev_conflito_%s.json" % datetime.date.today().isoformat())
    if a.rejulgar:
        d = json.load(io.open(arq, encoding="utf-8"))
        d["resumo"] = resumir(d["licitacoes"])
        d["julgamento_a_mao"] = [{"municipio": k, "classe": v[0], "nota": v[1]} for k, v in JULGAMENTO.items()]
        imprimir(d["licitacoes"], d["resumo"], d["custo"])
        io.open(arq, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1))
        print("  regravado: %s (US$ 0 — só releitura)" % os.path.relpath(arq, RAIZ))
        return 0
    t0 = time.time()
    with psycopg.connect(_71.R69._dsn(), row_factory=dict_row) as conn:
        conn.read_only = True
        casos = montar(conn)

    rqs = [r for c in casos for r in c["requests"] if "estado" in r]
    chars = sum(len(r["estado"]) + len(json.dumps(PERGUNTAS_JEV, ensure_ascii=False)) for r in rqs)
    print("  %d licitações · %d requests · %d mil caracteres · estimativa US$ %.4f (a 2 car/token)"
          % (len(casos), len(rqs), chars // 1000, chars / 2 * jev.PRECO_ENTRADA_ANUNCIADO / 1e6), flush=True)
    if a.seco:
        for c in casos:
            print("   %-28s %s" % (c["municipio"][:28], c.get("nao_medida") or
                                   "A=%s  B=%s  fontes=%d fora=%d" % (
                                       [(x["arquivo"][:22], x["paginas"]) for x in c["selecao"]["A"]],
                                       [(x["arquivo"][:22], x["paginas"]) for x in c["selecao"]["B"]],
                                       len(c["fontes"]), len(c["fora"]))))
        print("  NENHUMA chamada feita.")
        return 0

    segredos.carregar()                  # na thread principal, antes de qualquer chamada
    caixa = _71.Caixa(a.teto_usd, a.livro, a.teto_livro, "72_jev_r4_conflito")
    print("  limite desta execução: US$ %.4f (anterior no livro: US$ %.4f)" % (caixa.limite, caixa.anterior),
          flush=True)
    rodar(casos, caixa)
    info = {"usd": round(caixa.usd, 6), "chamadas": caixa.chamadas, "tokens": caixa.tokens,
            "falhas": caixa.falhas, "chars_por_token": round(caixa.chars_enviados / caixa.tokens, 3)
            if caixa.tokens else None, "limite_usd": round(caixa.limite, 6),
            "livro_anterior_usd": caixa.anterior, "preco": jev.FONTE_PRECO}
    resumo = resumir(casos)
    imprimir(casos, resumo, info)
    for c in casos:                                  # o state não vai para o JSON (é texto do edital)
        for r in c["requests"]:
            r.pop("estado", None)
    os.makedirs(DESTINO, exist_ok=True)
    io.open(arq, "w", encoding="utf-8").write(json.dumps({
        "medido_em": datetime.datetime.now().isoformat(timespec="seconds"),
        "script": "scripts/72_jev_r4_conflito.py", "modelo": jev.MODELO,
        "pergunta": _64.PERGUNTA, "criterios": _64.CRITERIOS,
        "parametros": {"conviccao": CONVICCAO, "distancia_no_mesmo_arquivo": DISTANCIA_MESMO_ARQUIVO,
                       "camada_A": "top-2 BM25 da Q2 por outro arquivo; no citado, páginas a >= 3 da citada",
                       "camada_B": "páginas que abrem definição de objeto (verificador.RE_OBJETO + 'folha'),"
                                   " menos a citada; até 3 por arquivo",
                       "state": "corpo_sustenta com a troca: sem trecho_citado; 'paginas_do_outro_documento'",
                       "controle": "corpo_sustenta original com a página citada"},
        "custo": info, "resumo": resumo,
        "julgamento_a_mao": [{"municipio": k, "classe": v[0], "nota": v[1]} for k, v in JULGAMENTO.items()],
        "licitacoes": casos}, ensure_ascii=False, indent=1))
    print("  salvo: %s  (%.0f s)" % (os.path.relpath(arq, RAIZ), time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
