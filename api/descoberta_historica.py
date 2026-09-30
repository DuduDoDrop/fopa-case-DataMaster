# -*- coding: utf-8 -*-
"""
Descoberta HISTÓRICA no PNCP (R$ 0), de 24/09/2026: o Analytics com todo o histórico possível, sempre dentro do
escopo de licitação, e um filtro de data na página.

O W01 descobre o que está no recorte de 2026 (ADR-015) e ignora o resto. Aqui a MESMA busca do PNCP
(`api/search`, a do W01 e do corpus) é lida ano a ano, desde 2021 (Lei 14.133), com os termos do W01
(tabela `termos`) e os do corpus; a regra de escopo (ADR-003) decide como sempre, antes de qualquer IA, e
cada licitação vai por `fn_registrar_historico` (db/030): o passado entra SÓ como histórico — nunca na fila
paga —, dentro do recorte é o caminho do W01, e o que já está no banco não é tocado.

O termo AMPLO ("folha de pagamento", ~10 mil resultados) traz software de folha, curso, consignado: dele só
entra o que a regra aceita (`so_dentro`). Os termos específicos entram inteiros, como no W01 — o que a regra
recusou fica registrado para o "mostrar fora do escopo" do analytics e para o Jev conferir a regra.

Por ano, porque a busca não passa de 10 mil resultados por consulta; e página a página até a página curta
(a busca vem com páginas cheias — o corte da consulta/v1 é outro defeito, scripts/fopa/pncp.py).

Uso (do host, como o coletor):
    python -m api.descoberta_historica --database-url URL [--de-ano 2021] [--ate-ano 2026] [--seco]
Depois: python -m api.historico_pncp --faltando --sem-cabecalho --so-dentro   (itens e resultados)
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import date

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

import api  # noqa: F401  (põe scripts/ no sys.path)
from api import escopo_ajuste
from fopa import pncp

TAMANHO = 50
MAX_PAGINAS = 200              # 10 mil por consulta, o teto da busca
PAUSA = 0.2
ANO_INICIAL = 2021             # o PNCP começa com a Lei 14.133
RE_CONTROLE = re.compile(r"^(\d{14})-(\d+)-(\d+)/(\d{4})$")

# Os do corpus (scripts/24_corpus_escopo.py:TERMOS) que o W01 não usa — além dos `termos` ativos dele.
TERMOS_EXTRA = (
    "gestão de consignações folha de pagamento",
    "administração da folha de pagamento",
    "processamento da folha de pagamento",
    "centralização dos serviços de pagamento",
    "centralização da folha de pagamento",
    "empresa bancária folha de pagamento",
    "serviços bancários folha de pagamento",
)
AMPLOS = ("folha de pagamento",)


def _txt(v) -> str:
    return "" if v is None or v is False or v == 0 else str(v)


def normalizar(it: dict) -> dict | None:
    """Do `api/search` para as colunas de licitacoes — a mesma conversão do nó "Normalizar" do W01."""
    controle = str(it.get("numero_controle_pncp") or "").strip()
    m = RE_CONTROLE.match(controle)
    if not m:
        return None
    cnpj = str(it.get("orgao_cnpj") or "")
    cnpj = cnpj if re.fullmatch(r"\d{14}", cnpj) else m.group(1)
    ano = int(it.get("ano") or 0) or int(m.group(4))
    seq = int(it.get("numero_sequencial") or 0) or int(m.group(3))
    atualizado = it.get("data_atualizacao_pncp")
    return {
        "controle": controle,
        "texto_escopo": " ".join(_txt(it.get(c)) for c in ("description", "objeto", "objetoCompra", "title")),
        "payload": {
            "controle": controle, "ano": ano, "seq": seq,
            "orgao": it.get("orgao_nome"), "uf": it.get("uf"), "municipio": it.get("municipio_nome"),
            "modalidade": it.get("modalidade_licitacao_nome"),
            "objeto": _txt(it.get("description"))[:1200] or None,
            "situacao": it.get("situacao_nome"),
            "publicado_em": it.get("data_publicacao_pncp"),
            "fim_prazo": it.get("data_fim_vigencia"),
            "atualizado_pncp": str(atualizado)[:19] if atualizado else None,
            "link": "https://pncp.gov.br/app/editais/%s/%d/%d" % (cnpj, ano, seq),
        },
    }


def buscar(termo: str, ano: int, get=pncp._get, pausa: float = 0.0, espera: float = 10.0,
           tentativas: int = 3) -> tuple[list[dict], dict]:
    """
    Todas as páginas de UM termo num ano (status=todos: aberto ou não), até a página curta. A página que cai
    é pedida de novo (`tentativas`, esperando `espera`, 2×`espera`…) — em 24/09 à noite 22 consultas caíram
    numa página funda; se desistir, a exceção LEVA o que já foi lido (`e.itens`, `e.pagina`), como no
    `pncp.buscar_com_info`.
    """
    itens, total, paginas = [], None, 0
    for p in range(1, MAX_PAGINAS + 1):
        q = urllib.parse.urlencode({"q": termo, "tipos_documento": "edital", "ordenacao": "-data", "pagina": p,
                                    "tam_pagina": TAMANHO, "status": "todos", "anos": ano})
        for tentativa in range(tentativas):
            try:
                d = get(pncp.BASE_BUSCA + "?" + q)
                break
            except pncp.ErroPNCP as e:
                if tentativa == tentativas - 1:
                    raise pncp.ErroPNCP(str(e), itens=itens, pagina=p) from e
                if espera:
                    time.sleep(espera * (tentativa + 1))
        paginas += 1
        if total is None:
            total = d.get("total")
        lote = d.get("items") or []
        itens.extend(lote)
        if len(lote) < TAMANHO:
            break
        if pausa:
            time.sleep(pausa)
    return itens, {"total_declarado": total, "lidos": len(itens), "paginas": paginas}


def registrar(conn, normalizados: list[dict], hoje: date, so_dentro: bool = False,
              escopo_versao: str | None = None) -> dict:
    """A regra decide o escopo; `fn_registrar_historico` (db/030) decide o que entra e como."""
    if escopo_versao is None:
        from api import versao
        escopo_versao = versao.escopo_versao()
    acoes: collections.Counter = collections.Counter()
    for n in normalizados:
        dentro, motivo = escopo_ajuste.avaliar(n["texto_escopo"])
        if so_dentro and not dentro:
            acoes["descartada_pela_regra"] += 1
            continue
        payload = dict(n["payload"], escopo_dentro=dentro, escopo_motivo=motivo, escopo_versao=escopo_versao)
        r = conn.execute("SELECT acao FROM fn_registrar_historico(%s, %s, %s)",
                         (n["controle"], Jsonb(payload), hoje)).fetchone()
        acoes[r["acao"] if isinstance(r, dict) else r[0]] += 1
    return dict(acoes)


def pares(texto: str | None) -> set[tuple[str, int]]:
    """ "termo@ano; termo@ano" → {(termo, ano)}: refazer só as consultas que falharam."""
    saida = set()
    for parte in (texto or "").split(";"):
        if "@" in parte:
            termo, _, ano = parte.strip().rpartition("@")
            saida.add((termo.strip(), int(ano)))
    return saida


def termos_da_rodada(conn) -> list[tuple[str, bool]]:
    """(termo, so_dentro): os ativos do W01 e os do corpus inteiros; o amplo, só o que a regra aceita."""
    ativos = [r[0] if not isinstance(r, dict) else r["termo"] for r in conn.execute(
        "SELECT termo FROM termos WHERE ativo ORDER BY prioridade NULLS LAST, termo").fetchall()]
    vistos, saida = set(), []
    for t in list(ativos) + list(TERMOS_EXTRA):
        if t.lower() not in vistos:
            vistos.add(t.lower())
            saida.append((t, False))
    return saida + [(t, True) for t in AMPLOS if t.lower() not in vistos]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Descoberta histórica no PNCP, ano a ano (R$ 0).")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--de-ano", type=int, default=ANO_INICIAL)
    ap.add_argument("--ate-ano", type=int, default=date.today().year)
    ap.add_argument("--seco", action="store_true", help="só busca e conta; não grava nada")
    ap.add_argument("--pares", help='só estas consultas: "termo@ano; termo@ano" (refazer as que falharam)')
    a = ap.parse_args(argv)
    if not a.database_url:
        print("falta --database-url (ou DATABASE_URL)", file=sys.stderr)
        return 2
    from api import versao
    ev = versao.escopo_versao()
    hoje = date.today()
    total = collections.Counter()
    falhas = []
    with psycopg.connect(a.database_url, row_factory=dict_row) as conn:
        termos = termos_da_rodada(conn)
        so = pares(a.pares)
        print("%d termo(s) × %d ano(s)%s" % (len(termos), a.ate_ano - a.de_ano + 1, " · SECO" if a.seco else ""),
              flush=True)
        for termo, so_dentro in termos:
            for ano in range(a.de_ano, a.ate_ano + 1):
                if so and (termo, ano) not in so:
                    continue
                try:
                    brutos, info = buscar(termo, ano, pausa=PAUSA)
                except pncp.ErroPNCP as e:
                    parcial = getattr(e, "itens", None) or []
                    falhas.append((termo, ano, "página %s: %s" % (getattr(e, "pagina", "?"), str(e)[-120:])))
                    print("  FALHOU %-48s %d na página %s (%d lidos antes): %s" % (
                        termo[:48], ano, getattr(e, "pagina", "?"), len(parcial), str(e)[-100:]), flush=True)
                    if parcial and not a.seco:
                        norm = [n for n in (normalizar(x) for x in parcial) if n]
                        acoes = registrar(conn, norm, hoje, so_dentro=so_dentro, escopo_versao=ev)
                        conn.commit()
                        total.update(acoes)
                        print("         parcial gravado: %s" % json.dumps(acoes, ensure_ascii=False), flush=True)
                    continue
                norm = [n for n in (normalizar(x) for x in brutos) if n]
                acoes = {} if a.seco else registrar(conn, norm, hoje, so_dentro=so_dentro, escopo_versao=ev)
                conn.commit()
                total.update(acoes)
                print("  %-48s %d: %4d de %5s declarados · %s" % (
                    termo[:48], ano, info["lidos"], info["total_declarado"],
                    json.dumps(acoes, ensure_ascii=False) if acoes else "-"), flush=True)
    print("total:", json.dumps(dict(total), ensure_ascii=False), flush=True)
    if falhas:
        print("%d consulta(s) FALHARAM — a descoberta ficou parcial nelas:" % len(falhas), flush=True)
        for t, ano, e in falhas:
            print("   · %s %d: %s" % (t, ano, e), flush=True)
        print('para refazer: --pares "%s"' % "; ".join("%s@%d" % (t, ano) for t, ano, _ in falhas), flush=True)
    return 0 if not falhas else 1


if __name__ == "__main__":
    sys.exit(main())
