# -*- coding: utf-8 -*-
"""
Histórico de compra e venda da folha, direto da API do PNCP.

Para cada controle: o cabeçalho da compra (api/consulta/v1 — valores estimado e homologado,
situação, datas de publicação, abertura e encerramento), os itens (situação: homologado, deserto,
fracassado…) e, dos itens com resultado, os resultados (vencedor, CNPJ, natureza jurídica, porte,
valor homologado, data). Não precisa do edital, nem de modelo: custo R$ 0.

Guarda o PAYLOAD inteiro de cada resposta — "todos os itens que a API disponibiliza" — e extrai
as colunas que o analytics consulta (db/027). Idempotente: rodar de novo atualiza as mesmas linhas.
Falha do PNCP marca só a tentativa (`pncp_coletas`); o que uma coleta anterior trouxe fica.

Uso (a partir da raiz):
    python -m api.historico_pncp --todos                 # todo controle de `licitacoes`
    python -m api.historico_pncp --faltando --paralelo 4 # só o que nunca deu certo
    python -m api.historico_pncp --controles 04035135000143-1-000015/2026
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

import api  # noqa: F401  (põe scripts/ no sys.path)
from fopa import pncp

RE_CONTROLE = re.compile(r"^(\d{14})-\d+-(\d+)/(\d{4})$")
TAMANHO_PAGINA = 100
# Itens e resultados pelo gateway `pncp-api`: medido em 24/09/2026, 0,04-0,09 s por chamada contra
# 15-25 s do caminho `api/pncp` (mesmo JSON). O cabeçalho da compra continua na API de consulta.
BASE_ITENS = "https://pncp.gov.br/pncp-api/v1"
BRASILIA = timezone(timedelta(hours=-3))      # o PNCP publica horário de Brasília, sem fuso (sem horário de verão)


class Limitador:
    """
    Ritmo compartilhado entre as threads para a API de CONSULTA (o cabeçalho da compra).

    Ela devolve 429 quando três threads pedem juntas — medido em 24/09/2026: 90 s de espera por
    compra, contra 0,3 s com ritmo. O gateway de itens/resultados não tem esse limite. Espaçar é
    mais rápido que insistir: o 429 do `pncp._get` espera 30 s, 60 s…
    """

    def __init__(self, por_segundo: float = 1.0):
        self.intervalo = 1.0 / por_segundo
        self._proximo = 0.0
        self._trava = threading.Lock()

    def esperar(self) -> None:
        # perf_counter, não monotonic: no Windows o monotonic anda em degraus de 15,6 ms (24/09: 4 intervalos
        # de 50 ms mediram 187,5 ms = 12 degraus). E dorme em laço até a hora marcada: o sono pode acordar cedo.
        with self._trava:
            agora = time.perf_counter()
            alvo = max(agora, self._proximo)
            self._proximo = alvo + self.intervalo
        while (falta := alvo - time.perf_counter()) > 0:
            time.sleep(falta)


def partes(controle: str) -> tuple[str, int, int]:
    m = RE_CONTROLE.match(controle or "")
    if not m:
        raise ValueError("controle fora do formato CNPJ-1-SEQ/ANO: %r" % controle)
    cnpj, seq, ano = m.groups()
    return cnpj, int(seq), int(ano)


def _quando(s) -> datetime | None:
    if not s:
        return None
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=BRASILIA)


def _dia(s) -> date | None:
    return date.fromisoformat(str(s)[:10]) if s else None


def _lista(r) -> list:
    """O PNCP às vezes devolve objeto solto onde deveria vir lista (PNCP - resultados.md)."""
    if r is None:
        return []
    return r if isinstance(r, list) else [r]


def _uma_vez(url: str, timeout: int = 30):
    """
    GET de UMA tentativa para o cabeçalho na passada rápida: o 429 da API de consulta custava 30 s +
    60 s de espera por compra no `pncp._get`. Aqui a recusa volta na hora e o cabeçalho fica para a
    passada lenta (`--so-cabecalhos`).
    """
    req = urllib.request.Request(url, headers={"User-Agent": pncp.USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise pncp.ErroPNCP("uma tentativa: %s — %s" % (url, e)) from None


def adiar_cabecalho(url: str, timeout: int | None = None):
    """
    Nem tenta: 24/09 21h a API de consulta passou a TRAVAR (30 s de timeout por compra) enquanto o
    gateway dava itens em 0,1 s. Com `--sem-cabecalho` a passada rápida grava itens e resultados e o
    cabeçalho fica, marcado, para a passada lenta (`--so-cabecalhos`).
    """
    raise pncp.ErroPNCP("adiado para a passada de cabeçalhos (--so-cabecalhos)")


def url_cabecalho(controle: str) -> str:
    cnpj, seq, ano = partes(controle)
    return "%s/orgaos/%s/compras/%s/%s" % (pncp.BASE_CONSULTA, cnpj, ano, seq)


def buscar(controle: str, get=pncp._get, limitador: Limitador | None = None, get_cabecalho=None) -> dict:
    """
    As três consultas de um controle, cruas. O CABEÇALHO é opcional: recusado (429 da API de
    consulta), vem `compra=None` com o motivo, e itens/resultados seguem. Levanta ValueError
    (controle) ou pncp.ErroPNCP (itens ou resultados).
    """
    cnpj, seq, ano = partes(controle)
    chamadas = 1
    if limitador is not None:
        limitador.esperar()
    compra, erro_cabecalho = None, None
    try:
        compra = (get_cabecalho or get)(url_cabecalho(controle))
    except pncp.ErroPNCP as e:
        erro_cabecalho = str(e)[:300]
    base = "%s/orgaos/%s/compras/%s/%s" % (BASE_ITENS, cnpj, ano, seq)
    itens, pagina = [], 1
    while True:
        lote = _lista(get("%s/itens?pagina=%d&tamanhoPagina=%d" % (base, pagina, TAMANHO_PAGINA)))
        chamadas += 1
        itens += lote
        if len(lote) < TAMANHO_PAGINA:
            break
        pagina += 1
    resultados = []
    for it in itens:
        if it.get("temResultado"):
            for r in _lista(get("%s/itens/%s/resultados" % (base, it.get("numeroItem")))):
                r.setdefault("numeroItem", it.get("numeroItem"))
                resultados.append(r)
            chamadas += 1
    return {"compra": compra, "erro_cabecalho": erro_cabecalho, "itens": itens, "resultados": resultados,
            "chamadas": chamadas}


def gravar_cabecalho(conn, controle: str, c: dict) -> None:
    orgao, unidade = c.get("orgaoEntidade") or {}, c.get("unidadeOrgao") or {}
    conn.execute(
        "INSERT INTO pncp_compras (controle, payload, orgao_cnpj, orgao, uf, municipio, modalidade, objeto,"
        " valor_estimado, valor_homologado, situacao, publicado_em, abertura_em, encerramento_em,"
        " existe_resultado, atualizado_pncp, buscado_em)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())"
        " ON CONFLICT (controle) DO UPDATE SET payload = EXCLUDED.payload, orgao_cnpj = EXCLUDED.orgao_cnpj,"
        " orgao = EXCLUDED.orgao, uf = EXCLUDED.uf, municipio = EXCLUDED.municipio,"
        " modalidade = EXCLUDED.modalidade, objeto = EXCLUDED.objeto, valor_estimado = EXCLUDED.valor_estimado,"
        " valor_homologado = EXCLUDED.valor_homologado, situacao = EXCLUDED.situacao,"
        " publicado_em = EXCLUDED.publicado_em, abertura_em = EXCLUDED.abertura_em,"
        " encerramento_em = EXCLUDED.encerramento_em, existe_resultado = EXCLUDED.existe_resultado,"
        " atualizado_pncp = EXCLUDED.atualizado_pncp, buscado_em = now()",
        (controle, Jsonb(c), orgao.get("cnpj"), orgao.get("razaoSocial"), unidade.get("ufSigla"),
         unidade.get("municipioNome"), c.get("modalidadeNome"), c.get("objetoCompra"),
         c.get("valorTotalEstimado"), c.get("valorTotalHomologado"), c.get("situacaoCompraNome"),
         _quando(c.get("dataPublicacaoPncp")), _quando(c.get("dataAberturaProposta")),
         _quando(c.get("dataEncerramentoProposta")), c.get("existeResultado"),
         _quando(c.get("dataAtualizacaoGlobal") or c.get("dataAtualizacao"))))


def gravar(conn, controle: str, dados: dict) -> None:
    if dados["compra"] is not None:
        gravar_cabecalho(conn, controle, dados["compra"])
    for it in dados["itens"]:
        conn.execute(
            "INSERT INTO pncp_itens (controle, numero_item, payload, descricao, situacao, valor_total,"
            " tem_resultado, criterio, buscado_em) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())"
            " ON CONFLICT (controle, numero_item) DO UPDATE SET payload = EXCLUDED.payload,"
            " descricao = EXCLUDED.descricao, situacao = EXCLUDED.situacao, valor_total = EXCLUDED.valor_total,"
            " tem_resultado = EXCLUDED.tem_resultado, criterio = EXCLUDED.criterio, buscado_em = now()",
            (controle, it.get("numeroItem"), Jsonb(it), it.get("descricao"), it.get("situacaoCompraItemNome"),
             it.get("valorTotal"), it.get("temResultado"), it.get("criterioJulgamentoNome")))
    for i, r in enumerate(dados["resultados"], start=1):
        conn.execute(
            "INSERT INTO pncp_resultados (controle, numero_item, sequencial, payload, ni_fornecedor, fornecedor,"
            " natureza_juridica, porte, valor_homologado, data_resultado, situacao, cancelado_em, buscado_em)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())"
            " ON CONFLICT (controle, numero_item, sequencial) DO UPDATE SET payload = EXCLUDED.payload,"
            " ni_fornecedor = EXCLUDED.ni_fornecedor, fornecedor = EXCLUDED.fornecedor,"
            " natureza_juridica = EXCLUDED.natureza_juridica, porte = EXCLUDED.porte,"
            " valor_homologado = EXCLUDED.valor_homologado, data_resultado = EXCLUDED.data_resultado,"
            " situacao = EXCLUDED.situacao, cancelado_em = EXCLUDED.cancelado_em, buscado_em = now()",
            (controle, r.get("numeroItem"), r.get("sequencialResultado") or i, Jsonb(r), r.get("niFornecedor"),
             r.get("nomeRazaoSocialFornecedor"), r.get("naturezaJuridicaNome"), r.get("porteFornecedorNome"),
             r.get("valorTotalHomologado"), _dia(r.get("dataResultado")),
             r.get("situacaoCompraItemResultadoNome"), _quando(r.get("dataCancelamento"))))


def _registrar(conn, controle: str, ok: bool, erro: str | None, chamadas: int) -> None:
    # Uma falha NÃO desfaz uma coleta boa: `ok` só vai de falso a verdadeiro. Com o PNCP fora do ar (30/09),
    # a releitura diária do acervo marcava ok=false em tudo e o analytics, que só conta `ok`, ficava vazio
    # com os dados intactos. O erro da última tentativa fica registrado; as chamadas, as da última que deu certo.
    conn.execute("INSERT INTO pncp_coletas (controle, ok, erro, chamadas, em) VALUES (%s, %s, %s, %s, now())"
                 " ON CONFLICT (controle) DO UPDATE SET ok = pncp_coletas.ok OR EXCLUDED.ok, erro = EXCLUDED.erro,"
                 " chamadas = CASE WHEN EXCLUDED.ok THEN EXCLUDED.chamadas ELSE pncp_coletas.chamadas END,"
                 " em = now()", (controle, ok, erro, chamadas))


def coletar_um(conn, controle: str, get=pncp._get, limitador: Limitador | None = None,
               get_cabecalho=None) -> dict:
    """Busca e grava UM controle numa transação; devolve o que aconteceu, nunca levanta."""
    try:
        dados = buscar(controle, get=get, limitador=limitador, get_cabecalho=get_cabecalho)
    except (ValueError, pncp.ErroPNCP) as e:
        erro = str(e)[:500]
        if not isinstance(e, ValueError):
            _registrar(conn, controle, False, erro, 0)
            conn.commit()
        return {"controle": controle, "ok": False, "itens": 0, "resultados": 0, "chamadas": 0, "erro": erro,
                "cabecalho": False}
    gravar(conn, controle, dados)
    # Sem cabeçalho NESTA passada não é "indisponível" se uma coleta anterior já o trouxe: a rodada diária relê itens e
    # resultados do acervo inteiro sem o cabeçalho, e marcaria todo dia o que está completo.
    tem_cabecalho = dados["compra"] is not None or conn.execute(
        "SELECT 1 FROM pncp_compras WHERE controle = %s", (controle,)).fetchone() is not None
    parcial = None if tem_cabecalho else "cabeçalho indisponível: %s" % dados["erro_cabecalho"]
    _registrar(conn, controle, True, parcial, dados["chamadas"])
    conn.commit()
    return {"controle": controle, "ok": True, "itens": len(dados["itens"]), "resultados": len(dados["resultados"]),
            "chamadas": dados["chamadas"], "erro": parcial, "cabecalho": dados["compra"] is not None}


def coletar_cabecalho(conn, controle: str, get=pncp._get, limitador: Limitador | None = None) -> bool:
    """A passada lenta: só o cabeçalho de quem ficou sem ele. True = gravado."""
    if limitador is not None:
        limitador.esperar()
    try:
        c = get(url_cabecalho(controle))
    except (ValueError, pncp.ErroPNCP):
        return False
    gravar_cabecalho(conn, controle, c)
    conn.execute("UPDATE pncp_coletas SET erro = NULL, em = now() WHERE controle = %s", (controle,))
    conn.commit()
    return True


def _alvos(conn, a) -> list[str]:
    if a.so_cabecalhos:
        return [r["controle"] for r in conn.execute(
            "SELECT k.controle FROM pncp_coletas k WHERE k.ok AND NOT EXISTS"
            " (SELECT 1 FROM pncp_compras c WHERE c.controle = k.controle) ORDER BY k.controle").fetchall()]
    if a.controles:
        return [c.strip() for c in a.controles.split(",") if c.strip()]
    sql = "SELECT l.controle FROM licitacoes l"
    if a.faltando:
        sql += " WHERE NOT EXISTS (SELECT 1 FROM pncp_coletas k WHERE k.controle = l.controle AND k.ok)"
        # O analytics abre no escopo de folha: com a descoberta histórica (db/030) o acervo tem milhares de
        # licitações que a regra recusou, e o gateway anda a minutos por centena.
        if getattr(a, "so_dentro", False):
            sql += " AND l.escopo_dentro"
    sql += " ORDER BY l.escopo_dentro DESC, l.publicado_em DESC NULLS LAST, l.controle"
    if a.limite:
        sql += " LIMIT %d" % int(a.limite)
    return [r["controle"] for r in conn.execute(sql).fetchall()]


# O cabeçalho vem da API de consulta, a única que estrangula: em 27/09 ela passou a 5 por minuto (429 e esperas de 30 s)
# enquanto o gateway dava itens e resultados a 70 chamadas por segundo. O cabeçalho não entra nos números financeiros (o
# analytics cai para o que a descoberta gravou e para a soma dos itens), então a rodada dá a ele um TEMPO, não uma
# meta: uma tentativa por compra, até TEMPO_CABECALHOS_S; o que sobrar fica para amanhã — nunca segura a rodada.
TEMPO_CABECALHOS_S = 600


def _vencedores(conn) -> int:
    return conn.execute("SELECT count(*) AS n FROM pncp_resultados WHERE cancelado_em IS NULL").fetchone()["n"]


def rodada_diaria(database_url: str, get=pncp._get, get_cabecalho=_uma_vez, progresso=None, paralelo: int = 4,
                  forcar_contratos: bool | None = None) -> dict:
    """
    A rodada do W41, todo dia às 04:30 (até ali o coletor só tinha rodado na mão, em 24 e 25/09). Idempotente; cada
    passada grava o que leu:
      1. NOVAS — o que nunca teve coleta boa (a licitação que o W01 achou): a compra inteira, o cabeçalho numa
         tentativa só, no ritmo da API de consulta;
      2. ACERVO — o que já foi coletado: itens e resultados de novo, sem o cabeçalho — o vencedor homologado depois, o
         resultado cancelado. O gateway responde em ~0,1 s (27/09: 6.607 licitações em ~8 min), então vai o acervo
         inteiro, todo dia;
      3. CABEÇALHOS — o de quem ficou sem (a API de consulta recusou): uma tentativa por compra, até
         TEMPO_CABECALHOS_S; o resto fica para a rodada seguinte;
      4. CONTRATOS — api/contratos_pncp: a busca inteira; detalhe e aditivos do que mudou (de todos, no domingo).
    Devolve os números da rodada (o W41 grava em `execucoes_workflow.contadores`).
    """
    from . import contratos_pncp
    inicio = time.time()
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        vencedores_antes = _vencedores(conn)
        ordem = " ORDER BY l.escopo_dentro DESC, l.publicado_em DESC NULLS LAST, l.controle"
        novas = [r["controle"] for r in conn.execute(
            "SELECT l.controle FROM licitacoes l WHERE NOT EXISTS"
            " (SELECT 1 FROM pncp_coletas k WHERE k.controle = l.controle AND k.ok)" + ordem).fetchall()]
        acervo = [r["controle"] for r in conn.execute(
            "SELECT l.controle FROM licitacoes l JOIN pncp_coletas k ON k.controle = l.controle AND k.ok"
            + ordem).fetchall()]
    limitador = Limitador()
    erros: list[str] = []

    def passada(etapa: str, controles: list[str], um) -> tuple[int, int]:
        ok = falhas = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, paralelo)) as ex:
            for n, r in enumerate(ex.map(um, controles), 1):
                if r["ok"]:
                    ok += 1
                else:
                    falhas += 1
                    if len(erros) < 20:
                        erros.append("%s (%s): %s" % (r["controle"], etapa, (r.get("erro") or "")[:200]))
                if progresso and (n % 100 == 0 or n == len(controles)):
                    progresso(etapa=etapa, feitos=n, total=len(controles))
        return ok, falhas

    def nova(controle):
        with psycopg.connect(database_url, row_factory=dict_row) as c:
            return coletar_um(c, controle, get=get, limitador=limitador, get_cabecalho=get_cabecalho)

    def do_acervo(controle):
        with psycopg.connect(database_url, row_factory=dict_row) as c:
            return coletar_um(c, controle, get=get, get_cabecalho=adiar_cabecalho)

    novas_ok, novas_falhas = passada("novas", novas, nova)
    acervo_ok, acervo_falhas = passada("acervo", acervo, do_acervo)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        sem_cabecalho = _alvos(conn, argparse.Namespace(so_cabecalhos=True))
    prazo = time.time() + TEMPO_CABECALHOS_S
    cabecalhos_ok = cabecalhos_tentados = 0
    for n, controle in enumerate(sem_cabecalho, 1):
        if time.time() > prazo:
            break
        cabecalhos_tentados += 1
        with psycopg.connect(database_url, row_factory=dict_row) as c:
            cabecalhos_ok += coletar_cabecalho(c, controle, get=get_cabecalho, limitador=limitador)
        if progresso and (n % 50 == 0 or n == len(sem_cabecalho)):
            progresso(etapa="cabeçalhos", feitos=n, total=len(sem_cabecalho))
    if forcar_contratos is None:
        forcar_contratos = datetime.now(BRASILIA).weekday() == 6
    contratos = contratos_pncp.coletar(database_url, get=get, forcar=forcar_contratos, paralelo=paralelo,
                                       progresso=progresso)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        vencedores_novos = _vencedores(conn) - vencedores_antes
    erros += contratos.pop("erros_contratos")[:max(0, 20 - len(erros))]
    return {"novas": len(novas), "novas_coletadas": novas_ok, "acervo": len(acervo), "acervo_atualizado": acervo_ok,
            "falhas": novas_falhas + acervo_falhas, "cabecalhos": cabecalhos_ok,
            "cabecalhos_tentados": cabecalhos_tentados, "cabecalhos_pendentes": len(sem_cabecalho) - cabecalhos_ok,
            "vencedores_novos": vencedores_novos,
            **contratos, "contratos_forcados": forcar_contratos, "erros": erros,
            "duracao_s": round(time.time() - inicio)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Histórico de compra e venda da folha pela API do PNCP (R$ 0).")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    alvo = ap.add_mutually_exclusive_group(required=True)
    alvo.add_argument("--diario", action="store_true",
                      help="a rodada do W41: novas, acervo (itens e resultados), cabeçalhos pendentes e contratos")
    alvo.add_argument("--todos", action="store_true", help="todo controle de `licitacoes`")
    alvo.add_argument("--faltando", action="store_true", help="só o que nunca teve coleta boa")
    alvo.add_argument("--controles", help="lista separada por vírgula")
    alvo.add_argument("--so-cabecalhos", action="store_true",
                      help="passada lenta: só o cabeçalho de quem ficou sem ele (API de consulta, com retentativa)")
    ap.add_argument("--sem-cabecalho", action="store_true",
                    help="passada rápida sem tentar o cabeçalho (a API de consulta travando); fica para --so-cabecalhos")
    ap.add_argument("--so-dentro", action="store_true",
                    help="com --faltando: só o que a regra de escopo aceitou (o que o analytics mostra por padrão)")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--paralelo", type=int, default=4, help="threads (itens e resultados vão em paralelo)")
    ap.add_argument("--consulta-por-segundo", type=float, default=1.0,
                    help="ritmo do cabeçalho na API de consulta (a que devolve 429)")
    a = ap.parse_args(argv)
    if not a.database_url:
        print("falta --database-url (ou DATABASE_URL)", file=sys.stderr)
        return 2
    if a.diario:
        t0 = time.time()
        r = rodada_diaria(a.database_url, paralelo=a.paralelo, progresso=lambda **p: print(
            "%s: %s/%s · %.0f s" % (p.get("etapa"), p.get("feitos"), p.get("total"), time.time() - t0), flush=True))
        print(r, flush=True)
        return 0
    with psycopg.connect(a.database_url, row_factory=dict_row) as conn:
        alvos = _alvos(conn, a)
    print("%d controle(s) a coletar, %d em paralelo" % (len(alvos), a.paralelo), flush=True)
    inicio, feitos, falhas, chamadas = time.time(), 0, 0, 0
    limitador = Limitador(a.consulta_por_segundo)

    def um(controle):
        with psycopg.connect(a.database_url, row_factory=dict_row) as c:
            if a.so_cabecalhos:
                ok = coletar_cabecalho(c, controle, limitador=limitador)
                return {"controle": controle, "ok": ok, "chamadas": 1, "erro": None if ok else "cabeçalho recusado"}
            # passada rápida: cabeçalho numa tentativa só; recusado, fica para --so-cabecalhos
            if a.sem_cabecalho:
                return coletar_um(c, controle, get_cabecalho=adiar_cabecalho)
            return coletar_um(c, controle, limitador=limitador, get_cabecalho=_uma_vez)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, a.paralelo)) as ex:
        for r in ex.map(um, alvos):
            feitos += 1
            falhas += 0 if r["ok"] else 1
            chamadas += r["chamadas"]
            if not r["ok"]:
                print("  falha %s: %s" % (r["controle"], (r["erro"] or "")[:160]), flush=True)
            if feitos % 50 == 0 or feitos == len(alvos):
                print("%d/%d · %d falha(s) · %d chamada(s) · %.0f s" % (feitos, len(alvos), falhas, chamadas,
                                                                    time.time() - inicio), flush=True)
    return 0 if feitos else 1


if __name__ == "__main__":
    sys.exit(main())
