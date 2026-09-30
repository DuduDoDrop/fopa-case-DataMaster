# -*- coding: utf-8 -*-
"""
Injeção suspeita de verdade (24/09/2026): só o trecho com cara de instrução é suspeito, e o texto
identificado aparece num "ver mais" abaixo do aviso.

O detector (`scripts/fopa/furtivo.py`) acha texto que a máquina lê e o humano não vê — e acerta nisso.
O que estava errado era a CONCLUSÃO: todo achado virava a tag "Prompt Injection" e degradava a
leitura. Conferido à mão em 24/09, nas 135 licitações com a tag não havia uma instrução sequer:

  texto branco (81)        timbre da prefeitura em faixa colorida (CNPJ, site, @perfil)
  alpha 0 (52)             a camada de OCR de página escaneada — as mesmas palavras que a imagem mostra
  corpo < 3 pt (14)        planta baixa no anexo de engenharia ("ÁREA: 51.88 m2")
  fora da página (4)       metadado de impressão ("Assinado por:", "Página 114 / 151")

Aqui cada trecho é guardado COM o texto (db/028) e classificado: é suspeito só o que tem cara de
ordem para uma IA. A reconstrução da verificação (api/reconstrucao.py) passa a levar só os suspeitos
como texto furtivo — sem suspeito, sem tag e sem degradar —, e o site mostra todos os trechos, com a
classe, num "ver mais". Este arquivo entra no hash de `versao_regras` (api/versao.py): o W30 reaplica.

Uso (dentro do worker, onde estão os PDFs):
    python -m api.injecao --todos        # toda leitura cuja condição tem texto furtivo e ainda não foi varrida
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import unicodedata

import psycopg
from psycopg.rows import dict_row

import api  # noqa: F401  (põe scripts/ no sys.path)
from fopa import furtivo

# Frases que FALAM COM UMA IA. Cada padrão é uma frase, nunca uma palavra solta, e é conferido contra
# texto de edital de verdade (api/tests/test_injecao.py): a camada de OCR de uma página escaneada é a
# página inteira, e "emissão de nota fiscal", "aprovar a proposta", "Sistema: SIGEP", "ignorar as
# regras deste edital" e "inteligência artificial" num requisito de software são edital, não ataque.
# O texto chega normalizado: minúsculo, sem acento, espaços colapsados.
PADROES_INSTRUCAO = [
    # mandar esquecer o que veio antes
    r"\b(?:ignor|desconsider|esquec)\w*\s+(?:todas\s+|todos\s+)?(?:as\s+|os\s+|suas\s+)?"
    r"(?:instruc\w*|orientac\w*|comandos?|regras?)\s+(?:anteriores|acima|previas|dadas|recebidas)",
    r"\b(?:ignore|disregard|forget)\s+(?:all\s+|any\s+)?(?:of\s+)?(?:the\s+|your\s+)?"
    r"(?:previous|prior|above|preceding|earlier|system)\b",
    # marcas de papel de conversa de chat
    r"(?:^|[\s>])(?:system|assistant)\s*:\s*\S",
    r"<\|?\s*(?:system|im_start|im_end|assistant)\s*\|?>",
    r"\[/?(?:inst|system)\]",
    # falar com a máquina
    r"\bvoce e (?:um|uma|o|a)\s+(?:avaliador\w*|assistente|modelo|ia|inteligencia|juiz|chatbot|robo)\b",
    r"\b(?:se|caso)\s+voce\s+(?:for|e|seja)\s+(?:um|uma)\s+(?:ia|inteligencia|modelo|assistente|robo|llm)\b",
    r"\byou are (?:a|an|the)\s+(?:\w+\s+){0,2}(?:assistant|model|ai|evaluator|reviewer|judge|grader|llm|chatbot)\b",
    r"\bif you are (?:an?\s+)?(?:ai|llm|language model|assistant|chatbot|gpt)\b",
    r"\b(?:note|instructions?|message)\s+(?:to|for)\s+(?:the\s+|any\s+)?(?:ai|llm|model|assistant|language model)\b",
    r"\b(?:nota|instruc\w*|mensagem|aviso|atencao)\s+(?:para|ao|a)\s+(?:a\s+|o\s+)?(?:ia|inteligencia artificial"
    r"|modelo de linguagem|assistente virtual)\b",
    # pedir o veredito
    r"\b(?:atribua|conceda)\s+(?:a\s+)?(?:nota|pontuacao)\s+(?:maxima|10|dez|100)\b",
    r"\b(?:give|assign|award)\s+(?:this\s+|the\s+)?(?:\w+\s+)?(?:a\s+)?(?:maximum\s+|max\s+|perfect\s+)?"
    r"(?:score|rating|grade)\b",
    r"\brate\s+(?:this|the)\s+\w+\s+\d+\s*/\s*\d+",
    r"\b(?:aprove|classifique|considere)\s+(?:esta|este|essa|esse)\s+(?:proposta|empresa|licitante)\s+"
    r"(?:como\s+)?(?:a\s+)?(?:vencedora|aprovad\w*|habilitad\w*|melhor)",
    r"\b(?:responda|escreva)\s+(?:apenas|somente|sempre)\b",
    r"\b(?:respond|answer|reply)\s+(?:only|always)\b",
    # o vocabulário da própria máquina
    r"\b(?:prompt|chatgpt|gpt-?\d\w*|llm|large language model|language model|modelo de linguagem)\b",
]
RE_INSTRUCAO = re.compile("|".join("(?:%s)" % p for p in PADROES_INSTRUCAO), re.I)

# Quanto do texto de um trecho fica guardado. Uma página de OCR inteira não precisa ir ao banco para
# alguém ver que é a página; um trecho suspeito vai inteiro (é raro e é o que interessa ler).
LIMITE_TEXTO = 1500
LIMITE_TEXTO_SUSPEITO = 20000

CLASSES_BENIGNAS = (
    ("texto transparente", "camada de texto invisível (OCR sobre imagem escaneada): o texto que a página mostra"),
    ("texto branco", "texto branco — em edital é timbre ou cabeçalho sobre faixa colorida"),
    ("corpo de", "letra minúscula — planta, carimbo ou numeração"),
    ("fora da área visível", "fora da página — metadado de impressão"),
)


def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().lower()


def classificar(texto: str, motivo: str) -> tuple[bool, str]:
    """(suspeito, por quê). Suspeito = frase com cara de ordem para uma IA; o resto diz o que é."""
    m = RE_INSTRUCAO.search(_normalizar(texto))
    if m:
        return True, "tem cara de instrução para IA: «%s»" % m.group(0)[:80]
    for prefixo, classe in CLASSES_BENIGNAS:
        if (motivo or "").startswith(prefixo):
            return False, classe
    return False, "texto escondido sem instrução"


def _tipo(motivo: str) -> str:
    """O tipo do achado, sem o detalhe: "corpo de 1.2pt" e "corpo de 2.0pt" são o mesmo tipo."""
    for prefixo, _ in CLASSES_BENIGNAS:
        if (motivo or "").startswith(prefixo):
            return prefixo
    return motivo or "?"


def agrupar(achados) -> list[dict]:
    """
    Um trecho por (página, tipo), na ordem em que o detector leu. O detector acha linha a linha, e uma
    instrução quebrada em duas linhas só é instrução com as duas juntas.
    """
    grupos: dict[tuple, dict] = {}
    for x in achados:
        g = grupos.setdefault((x.pagina, _tipo(x.motivo)), {
            "pagina": x.pagina, "motivo": x.motivo, "partes": [], "tamanho": None})
        g["partes"].append(x.amostra)
        if x.tamanho and (g["tamanho"] is None or x.tamanho < g["tamanho"]):
            g["tamanho"] = x.tamanho
            if _tipo(x.motivo) == "corpo de":
                g["motivo"] = x.motivo          # o menor corpo é o que descreve o trecho
    saida = []
    for g in grupos.values():
        texto = "\n".join(g["partes"])
        suspeito, classe = classificar(texto, g["motivo"])
        limite = LIMITE_TEXTO_SUSPEITO if suspeito else LIMITE_TEXTO
        saida.append({"pagina": g["pagina"], "motivo": g["motivo"], "texto": texto[:limite],
                      "linhas": len(g["partes"]), "caracteres": len(texto),
                      "tamanho": round(g["tamanho"] or 0, 2), "suspeito": suspeito, "classe": classe})
    return saida


def _arquivos_da_leitura(conn, leitura_id: int) -> list[dict]:
    return conn.execute(
        "SELECT DISTINCT a.id, a.nome, a.storage_key FROM paginas p JOIN arquivos a ON a.id = p.arquivo_id"
        " WHERE p.leitura_id = %s AND a.storage_key IS NOT NULL ORDER BY a.nome", (leitura_id,)).fetchall()


def varrer_leitura(conn, storage, leitura_id: int) -> dict:
    """
    Varre os PDFs de UMA leitura e grava cada trecho com texto e classe. Leitura já varrida não é varrida
    de novo (a varredura é função dos bytes, que são congelados): devolve o que já está gravado.
    """
    feita = conn.execute("SELECT arquivos, achados, suspeitos, erro FROM furtivos_varreduras WHERE leitura_id = %s",
                         (leitura_id,)).fetchone()
    if feita:
        return dict(feita)
    arquivos, achados, suspeitos, erros = 0, 0, 0, []
    for a in _arquivos_da_leitura(conn, leitura_id):
        try:
            corpo = storage.get(a["storage_key"])
        except Exception as e:                                             # noqa: BLE001
            erros.append("%s: %s" % (a["nome"], str(e)[:120]))
            continue
        arquivos += 1
        fd, caminho = tempfile.mkstemp(suffix=".pdf")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(corpo)
            v = furtivo.varrer(caminho)
        finally:
            os.unlink(caminho)
        if v.erro:
            erros.append("%s: %s" % (a["nome"], v.erro))
        for g in agrupar(v.achados):
            conn.execute(
                "INSERT INTO furtivos_achados (leitura_id, arquivo, pagina, motivo, texto, linhas, caracteres,"
                " tamanho, classe, suspeito) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (leitura_id, a["nome"], g["pagina"], g["motivo"], g["texto"], g["linhas"], g["caracteres"],
                 g["tamanho"], g["classe"], g["suspeito"]))
            achados += 1
            suspeitos += int(g["suspeito"])
    r = {"arquivos": arquivos, "achados": achados, "suspeitos": suspeitos, "erro": "; ".join(erros)[:500] or None}
    conn.execute("INSERT INTO furtivos_varreduras (leitura_id, arquivos, achados, suspeitos, erro)"
                 " VALUES (%s, %s, %s, %s, %s)", (leitura_id, arquivos, achados, suspeitos, r["erro"]))
    return r


def furtivos_para_condicoes(conn, leitura_id: int | None) -> list[str] | None:
    """
    O que a verificação leva como texto furtivo: só os SUSPEITOS, com o texto. None = a leitura nunca foi
    varrida por aqui — quem chama segue com o que a condição da leitura diz (o comportamento antigo).
    """
    v = None if leitura_id is None else conn.execute(
        "SELECT erro FROM furtivos_varreduras WHERE leitura_id = %s", (leitura_id,)).fetchone()
    # Varredura com erro não absolve: "não consegui conferir" não é "benigno" — segue o que a leitura dizia.
    if v is None or v["erro"]:
        return None
    return ["%s p.%d: %s — «%s»" % (r["arquivo"], r["pagina"], r["motivo"], r["texto"][:120])
            for r in conn.execute("SELECT arquivo, pagina, motivo, texto FROM furtivos_achados"
                                  " WHERE leitura_id = %s AND suspeito ORDER BY id", (leitura_id,)).fetchall()]


def suspeitos(conn, storage, leitura_id: int | None, condicoes_leitura: dict | None) -> list[str] | None:
    """
    Os furtivos que a verificação leva. Leitura sem texto furtivo: None (nada muda). Com furtivo e nunca
    varrida: varre agora (os PDFs estão no storage do worker) e devolve só os suspeitos.
    """
    lc = condicoes_leitura or {}
    if leitura_id is None or not (lc.get("furtivos") or lc.get("texto_furtivo")):
        return None
    ja = furtivos_para_condicoes(conn, leitura_id)
    if ja is not None or storage is None:
        return ja
    varrer_leitura(conn, storage, leitura_id)
    return furtivos_para_condicoes(conn, leitura_id)


def main(argv=None) -> int:
    from api import config, storage as storage_mod
    ap = argparse.ArgumentParser(description="Varre de novo o texto furtivo das leituras e classifica (R$ 0).")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--todos", action="store_true", required=True)
    a = ap.parse_args(argv)
    if not a.database_url:
        print("falta --database-url (ou DATABASE_URL)", file=sys.stderr)
        return 2
    st = storage_mod.abrir(config.carregar())
    with psycopg.connect(a.database_url, row_factory=dict_row) as conn:
        alvos = [r["id"] for r in conn.execute(
            "SELECT le.id FROM leituras le WHERE jsonb_array_length(COALESCE(le.condicoes->'furtivos',"
            " le.condicoes->'texto_furtivo', '[]'::jsonb)) > 0 AND NOT EXISTS"
            " (SELECT 1 FROM furtivos_varreduras v WHERE v.leitura_id = le.id) ORDER BY le.id").fetchall()]
        print("%d leitura(s) a varrer" % len(alvos), flush=True)
        tot = {"achados": 0, "suspeitos": 0}
        for i, lid in enumerate(alvos, start=1):
            r = varrer_leitura(conn, st, lid)
            conn.commit()
            tot["achados"] += r["achados"]
            tot["suspeitos"] += r["suspeitos"]
            if r["suspeitos"] or i % 25 == 0 or i == len(alvos):
                print("%d/%d · leitura %d: %d achado(s), %d suspeito(s)%s" % (
                    i, len(alvos), lid, r["achados"], r["suspeitos"], " · erro: " + r["erro"] if r["erro"] else ""),
                    flush=True)
        print("total: %(achados)d achado(s), %(suspeitos)d suspeito(s)" % tot, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
