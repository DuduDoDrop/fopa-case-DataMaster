# -*- coding: utf-8 -*-
"""
Os contratos da folha, direto do PNCP (db/049).

A compra (db/027) diz quem venceu e por quanto; o CONTRATO diz o que foi assinado: valor inicial, global e acumulado
(com os aditivos), parcelas, a data da assinatura e a VIGÊNCIA — até quando aquele banco fica com a folha daquele
órgão. Custo R$ 0: API pública, nenhum modelo.

TRÊS CONSULTAS, TODAS RÁPIDAS (medido em 27/09/2026, do servidor de produção)
  1. BUSCA — api/search com tipos_documento=contrato e os termos ATIVOS da descoberta (tabela `termos`): os contratos
     de folha do país inteiro, inclusive os de licitação que o FOPA não tem. 500 por página, ~0,5 s.
  2. DETALHE — api/pncp /orgaos/{cnpj}/contratos/{ano}/{seq}: o vínculo com a compra (`numeroControlePncpCompra`), o
     fornecedor e os valores. ~0,1 s. A busca devolve `item_url` no caminho do PORTAL (/contratos/{cnpj}/{ano}/{seq});
     na API o caminho é /orgaos/... — por isso a URL sai do controle, não do `item_url`.
  3. ADITIVOS — .../termos. 204 = nenhum.
  A consulta/v1/contratos (por órgão e período) serve o mesmo contrato, mas leva 18-25 s por chamada, traz todos os
  contratos do órgão e aceita no máximo 365 dias: não é o caminho.

SÓ DESCE NO QUE MUDOU
  A busca traz `data_atualizacao_pncp` de cada contrato — o mesmo carimbo do detalhe, com nanossegundos. A rodada relê
  a busca inteira (segundos) e só pede detalhe e aditivos do contrato novo ou cujo carimbo passou do guardado;
  `forcar` relê todos (a rodada diária força no domingo, para o aditivo que não mexa no carimbo).

ESCOPO
  A busca por "folha de pagamento" traz também o sistema de RH e o consignado. O contrato é julgado pela mesma regra das
  licitações (api/escopo_ajuste.avaliar) sobre o objeto dele.

Uso (a partir da raiz):
    python -m api.contratos_pncp            # busca e lê o que é novo ou mudou
    python -m api.contratos_pncp --forcar   # relê detalhe e aditivos de todos
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

import api  # noqa: F401  (põe scripts/ no sys.path)
from fopa import pncp

from . import escopo_ajuste
from .historico_pncp import _dia, _lista, _quando

RE_CONTRATO = re.compile(r"^(\d{14})-2-(\d+)/(\d{4})$")
TAMANHO_BUSCA = 500
# Teto de segurança, não de conteúdo: 40 páginas de 500 são 20 mil contratos por termo, e "folha de pagamento" inteira
# declara ~5 mil (27/09/2026). Se um dia bater no teto, o `por_termo` da rodada mostra lidos < total.
MAX_PAGINAS_BUSCA = 40


def partes(controle: str) -> tuple[str, int, int]:
    m = RE_CONTRATO.match(controle or "")
    if not m:
        raise ValueError("contrato fora do formato CNPJ-2-SEQ/ANO: %r" % controle)
    cnpj, seq, ano = m.groups()
    return cnpj, int(ano), int(seq)


def url_contrato(controle: str) -> str:
    cnpj, ano, seq = partes(controle)
    return "%s/orgaos/%s/contratos/%s/%s" % (pncp.BASE_PNCP, cnpj, ano, seq)


def url_busca(termo: str, pagina: int) -> str:
    return pncp.BASE_BUSCA + "?" + urllib.parse.urlencode({
        "q": termo, "tipos_documento": "contrato", "ordenacao": "-data", "pagina": pagina,
        "tam_pagina": TAMANHO_BUSCA, "status": "todos"})


def _carimbo(s) -> datetime | None:
    """O carimbo da busca tem nanossegundos ("...T16:01:24.035098042"), o do detalhe não: compara no segundo."""
    return _quando(str(s)[:19]) if s else None


def buscar(termos: list[str], get=pncp._get) -> tuple[dict, dict]:
    """
    Todos os contratos que a busca acha: `{controle: {"carimbo", "termo"}}` (o termo que achou primeiro) e, por termo,
    o total que a busca declara e quantos foram lidos. A busca que cai no meio de um termo NÃO derruba a rodada: o que
    já foi lido segue, e o termo leva o `erro` (a rodada fica cega, como a do W01 com busca falha).
    """
    achados, por_termo = {}, {}
    for termo in termos:
        total, lidos, erro = None, 0, None
        for pagina in range(1, MAX_PAGINAS_BUSCA + 1):
            try:
                d = get(url_busca(termo, pagina)) or {}
            except pncp.ErroPNCP as e:
                erro = "página %d: %s" % (pagina, str(e)[:200])
                break
            if total is None:
                total = d.get("total")
            lote = d.get("items") or []
            lidos += len(lote)
            for it in lote:
                c = it.get("numero_controle_pncp")
                if c and RE_CONTRATO.match(c) and c not in achados:
                    achados[c] = {"carimbo": _carimbo(it.get("data_atualizacao_pncp")), "termo": termo}
            if len(lote) < TAMANHO_BUSCA:
                break
        por_termo[termo] = {"total": total, "lidos": lidos, **({"erro": erro} if erro else {})}
    return achados, por_termo


def detalhar(controle: str, get=pncp._get) -> tuple[dict, list]:
    """O contrato e os aditivos dele, crus. Levanta ValueError (controle) ou pncp.ErroPNCP."""
    base = url_contrato(controle)
    return get(base), _lista(get(base + "/termos", vazio_ok=True))


def gravar(conn, controle: str, d: dict, aditivos: list, termo_busca: str | None) -> None:
    orgao, unidade = d.get("orgaoEntidade") or {}, d.get("unidadeOrgao") or {}
    dentro, motivo = escopo_ajuste.avaliar(d.get("objetoContrato") or "")
    carimbos = [c for c in (_quando(d.get("dataAtualizacaoGlobal")), _quando(d.get("dataAtualizacao"))) if c]
    conn.execute(
        "INSERT INTO pncp_contratos (controle, controle_compra, payload, orgao_cnpj, orgao, uf, municipio,"
        " ni_fornecedor, fornecedor, objeto, tipo, valor_inicial, valor_global, valor_acumulado, valor_parcela,"
        " parcelas, receita, assinado_em, vigencia_inicio, vigencia_fim, publicado_em, atualizado_pncp,"
        " escopo_dentro, escopo_motivo, termo_busca, buscado_em)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
        " %s, now())"
        " ON CONFLICT (controle) DO UPDATE SET controle_compra = EXCLUDED.controle_compra, payload = EXCLUDED.payload,"
        " orgao_cnpj = EXCLUDED.orgao_cnpj, orgao = EXCLUDED.orgao, uf = EXCLUDED.uf, municipio = EXCLUDED.municipio,"
        " ni_fornecedor = EXCLUDED.ni_fornecedor, fornecedor = EXCLUDED.fornecedor, objeto = EXCLUDED.objeto,"
        " tipo = EXCLUDED.tipo, valor_inicial = EXCLUDED.valor_inicial, valor_global = EXCLUDED.valor_global,"
        " valor_acumulado = EXCLUDED.valor_acumulado, valor_parcela = EXCLUDED.valor_parcela,"
        " parcelas = EXCLUDED.parcelas, receita = EXCLUDED.receita, assinado_em = EXCLUDED.assinado_em,"
        " vigencia_inicio = EXCLUDED.vigencia_inicio, vigencia_fim = EXCLUDED.vigencia_fim,"
        " publicado_em = EXCLUDED.publicado_em, atualizado_pncp = EXCLUDED.atualizado_pncp,"
        " escopo_dentro = EXCLUDED.escopo_dentro, escopo_motivo = EXCLUDED.escopo_motivo,"
        " termo_busca = COALESCE(pncp_contratos.termo_busca, EXCLUDED.termo_busca), buscado_em = now()",
        (controle, d.get("numeroControlePncpCompra"), Jsonb(d), orgao.get("cnpj"), orgao.get("razaoSocial"),
         unidade.get("ufSigla"), unidade.get("municipioNome"), d.get("niFornecedor"),
         d.get("nomeRazaoSocialFornecedor"), d.get("objetoContrato"), (d.get("tipoContrato") or {}).get("nome"),
         d.get("valorInicial"), d.get("valorGlobal"), d.get("valorAcumulado"), d.get("valorParcela"),
         d.get("numeroParcelas"), d.get("receita"), _dia(d.get("dataAssinatura")),
         _dia(d.get("dataVigenciaInicio")), _dia(d.get("dataVigenciaFim")), _quando(d.get("dataPublicacaoPncp")),
         max(carimbos) if carimbos else None, dentro, motivo, termo_busca))
    for i, t in enumerate(aditivos, start=1):
        conn.execute(
            "INSERT INTO pncp_contrato_termos (controle_contrato, sequencial, payload, tipo, objeto, valor_acrescido,"
            " valor_global, prazo_aditado_dias, assinado_em, vigencia_fim, buscado_em)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())"
            " ON CONFLICT (controle_contrato, sequencial) DO UPDATE SET payload = EXCLUDED.payload,"
            " tipo = EXCLUDED.tipo, objeto = EXCLUDED.objeto, valor_acrescido = EXCLUDED.valor_acrescido,"
            " valor_global = EXCLUDED.valor_global, prazo_aditado_dias = EXCLUDED.prazo_aditado_dias,"
            " assinado_em = EXCLUDED.assinado_em, vigencia_fim = EXCLUDED.vigencia_fim, buscado_em = now()",
            (controle, t.get("sequencialTermoContrato") or i, Jsonb(t), t.get("tipoTermoContratoNome"),
             t.get("objetoTermoContrato"), t.get("valorAcrescido"), t.get("valorGlobal"), t.get("prazoAditadoDias"),
             _dia(t.get("dataAssinatura")), _dia(t.get("dataVigenciaFim"))))


def ler_um(database_url: str, controle: str, termo_busca: str | None, get=pncp._get) -> dict:
    """Detalhe e aditivos de UM contrato, gravados numa transação; devolve o que aconteceu, nunca levanta."""
    try:
        d, aditivos = detalhar(controle, get=get)
    except (ValueError, pncp.ErroPNCP) as e:
        return {"controle": controle, "ok": False, "aditivos": 0, "erro": str(e)[:300]}
    if not isinstance(d, dict) or not d:
        return {"controle": controle, "ok": False, "aditivos": 0, "erro": "o PNCP não devolveu o contrato"}
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        gravar(conn, controle, d, aditivos, termo_busca)
        conn.commit()
    return {"controle": controle, "ok": True, "aditivos": len(aditivos), "erro": None}


def coletar(database_url: str, get=pncp._get, forcar: bool = False, paralelo: int = 4, progresso=None) -> dict:
    """
    A passada dos contratos: a busca inteira e, do que é novo ou mudou (ou de todos, com `forcar`), detalhe e
    aditivos. Devolve os números da rodada.
    """
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        termos = [r["termo"] for r in conn.execute("SELECT termo FROM termos WHERE ativo ORDER BY prioridade, termo")]
        guardados = {r["controle"]: r["atualizado_pncp"] for r in
                     conn.execute("SELECT controle, atualizado_pncp FROM pncp_contratos").fetchall()}
    achados, por_termo = buscar(termos, get=get)

    def mudou(controle: str) -> bool:
        if forcar or controle not in guardados:
            return True
        novo, velho = achados[controle]["carimbo"], guardados[controle]
        return novo is not None and (velho is None or novo > velho)

    alvos = [c for c in achados if mudou(c)]
    lidos = falhas = aditivos = 0
    erros = []
    if progresso:
        progresso(etapa="contratos", feitos=0, total=len(alvos), achados=len(achados))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, paralelo)) as ex:
        for n, r in enumerate(ex.map(lambda c: ler_um(database_url, c, achados[c]["termo"], get=get), alvos), 1):
            if r["ok"]:
                lidos += 1
                aditivos += r["aditivos"]
            else:
                falhas += 1
                if len(erros) < 20:
                    erros.append("%s: %s" % (r["controle"], r["erro"]))
            if progresso and (n % 100 == 0 or n == len(alvos)):
                progresso(etapa="contratos", feitos=n, total=len(alvos), achados=len(achados))
    return {"contratos_achados": len(achados), "contratos_lidos": lidos,
            "contratos_novos": sum(1 for c in alvos if c not in guardados), "contratos_falhas": falhas,
            "aditivos_lidos": aditivos, "busca": por_termo,
            "cego": any("erro" in t for t in por_termo.values()), "erros_contratos": erros}


__all__ = ["partes", "url_contrato", "url_busca", "buscar", "detalhar", "gravar", "ler_um", "coletar"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Contratos de folha no PNCP: busca, detalhe e aditivos (R$ 0).")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--forcar", action="store_true", help="relê detalhe e aditivos de todos, não só do que mudou")
    ap.add_argument("--paralelo", type=int, default=4)
    a = ap.parse_args(argv)
    if not a.database_url:
        print("falta --database-url (ou DATABASE_URL)", file=sys.stderr)
        return 2
    inicio = time.time()

    def mostrar(**p):
        print("%s: %s/%s (achados na busca: %s) · %.0f s"
              % (p.get("etapa"), p.get("feitos"), p.get("total"), p.get("achados"), time.time() - inicio), flush=True)

    r = coletar(a.database_url, forcar=a.forcar, paralelo=a.paralelo, progresso=mostrar)
    print({k: v for k, v in r.items() if k != "erros_contratos"}, flush=True)
    for e in r["erros_contratos"]:
        print("  falha " + e, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
