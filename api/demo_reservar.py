# -*- coding: utf-8 -*-
"""
Reserva de licitações para a demonstração (plano, seção 10, linha F7;
`Checklist F7 Ensaio.md`).

A demo sem PNCP (e a sem rede) precisa de licitações que o W20 leve direto ao
W23 pelo Switch: estado `preparada`, com o texto congelado em
`leituras`/`paginas` — nada a baixar nem a ler no dia. Este CLI escolhe essas
licitações, diz por que escolheu cada uma, marca e solta.

    --listar              reservadas agora (ainda servem?) + candidatas com o porquê
    --reservar [N]        garante N reservadas (padrão 3); conta as que já estão
    --controles C [C ...] com --reservar/--soltar/--rearmar: só estas
    --prazo DIAS          com --reservar: sessão em hoje+DIAS às 17h de Brasília
                          (o valor original fica no registro e o --soltar devolve)
    --ate AAAA-MM-DD      dia da demo, para dizer quem ainda estará aberta (padrão hoje+7)
    --soltar              desfaz a reserva (todas, ou as --controles)
    --rearmar             reservada que a demo publicou -> preparada, com o replay
                          pronto para o provedor `gravado`. Precisa de uma transição
                          que o banco ainda NÃO tem (ver TRANSICAO_PROPOSTA); sem
                          ela, recusa sem mexer em nada.

Reservar é gravar duas colunas:
  * `reserva_demo=true` — `fn_reivindicar` (021, o claim do W10) nunca pega; só o
    W20 chamado com `forcar=true`;
  * `ensaio=true` — T15 (`fn_vigente_exige_ensaio`, 005): sem isso a verificação
    de uma execução `simulado`/`gravado` não pode virar vigente e o W24 falha.
    O card do site mostra o selo "ensaio".
Cada rodada que muda alguma coisa vira uma linha em `execucoes_workflow`
(`workflow='demo_reservar'`), que o site lista em /execucoes, com o antes e o
depois de cada licitação — é de lá que o `--soltar` tira o valor original.
Nada muda sem dizer.

Nunca reserva licitação publicada: ela já tem resultado no site e não existe
caminho `publicada -> W23` sem baixar de novo (seção 5, Switch do W20).

Onde roda:
    docker exec fopa-worker python -m api.demo_reservar --listar
        (papel worker_rw; a imagem precisa ter este arquivo — refaça o build ou
        `docker cp api/demo_reservar.py fopa-worker:/app/api/`)
    DATABASE_URL=postgresql://worker_rw:<senha>@127.0.0.1:5433/fopa python -m api.demo_reservar --listar
`--listar` só lê (transação READ ONLY; roda até com api_ro).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import banco
from .consultas import JEV_ESCOPO

LOG_WORKFLOW = "demo_reservar"
PADRAO_N = 3
HORA_SESSAO = "17:00"                 # --prazo: horário de Brasília da sessão renovada
# Faixa de tamanho que custa ~R$ 3-4 e poucos minutos por edital no provedor
# real (Checklist F7): fora dela a licitação não sai, só desce na fila.
FAIXA_CHARS = (30_000, 150_000)
RE_CONTROLE = re.compile(r"^\d{14}-\d+-\d+/\d{4}$")
LOCK = "fopa.demo_reservar"
MOTIVO_REARMAR = "demo: rearmar reservada (api/demo_reservar.py --rearmar)"
# A mudança de banco que o --rearmar pede (descrita no relatório da F7; o CLI
# não cria migração). Sem ela, uma reservada que a demo publicou não volta a
# `preparada`, e o provedor `gravado` — que repete a execução da verificação
# VIGENTE do controle — não tem como rodar na mesma licitação sem PNCP.
TRANSICAO_PROPOSTA = ("INSERT INTO transicoes (de, para, nota) VALUES ('publicada', 'preparada',\n"
                      "    'demo: rearmar reservada (api/demo_reservar.py --rearmar)');")

# Tudo o que o CLI precisa saber de uma licitação, numa consulta. `gravado_pronto`
# espelha o /gravado/v1/messages (rotas_extracao.py): a execução da verificação
# vigente, pelas chamadas gravadas ou pelas 17 respostas cruas.
_SQL = """
WITH jev AS ({jev})
SELECT l.controle, l.slug, l.orgao, l.uf, l.municipio, l.modalidade, left(l.objeto, 110) AS objeto,
       l.estado::text AS estado, l.fim_prazo, l.publicado_em, l.reserva_demo, l.ensaio,
       l.escopo_dentro, l.procedencia_incerta, l.gemea_de,
       fn_no_recorte(l.fim_prazo, l.publicado_em) AS no_recorte,
       (l.fim_prazo AT TIME ZONE 'America/Sao_Paulo')::date AS dia_sessao,
       (l.lease_por IS NOT NULL AND l.lease_ate >= now()) AS com_lease,
       le.id AS leitura_id, le.chars_total, le.modo_sugerido,
       CASE WHEN jsonb_typeof(le.condicoes -> 'paginas_ocr') = 'number'
            THEN (le.condicoes ->> 'paginas_ocr')::numeric::int ELSE 0 END AS paginas_ocr,
       CASE WHEN jsonb_typeof(le.condicoes -> 'furtivos') = 'array'
            THEN jsonb_array_length(le.condicoes -> 'furtivos') ELSE 0 END AS furtivos,
       (SELECT count(*) FROM paginas p WHERE p.leitura_id = le.id)::int AS n_paginas,
       (SELECT count(*) FROM arquivos a WHERE a.controle = l.controle AND a.status = 'ok'
           AND a.storage_key IS NOT NULL)::int AS pdfs_ok,
       v.id AS verificacao_vigente, e.id AS execucao_vigente, e.origem AS origem_vigente,
       (e.id IS NOT NULL AND (
            EXISTS (SELECT 1 FROM chamadas_modelo c WHERE c.execucao_id = e.id AND c.dados IS NOT NULL)
         OR (SELECT count(DISTINCT r.pergunta_id) FROM respostas r WHERE r.execucao_id = e.id) >= 17
       )) AS gravado_pronto,
       j.p_filtro_ok
  FROM licitacoes l
  LEFT JOIN leituras le ON le.id = l.leitura_vigente_id
  LEFT JOIN verificacoes v ON v.controle = l.controle AND v.vigente
  LEFT JOIN execucoes_modelo e ON e.id = v.execucao_id
  LEFT JOIN jev j ON j.controle = l.controle
 WHERE {onde}
 ORDER BY l.controle
"""

# Sessão renovada: dia civil de São Paulo + DIAS, às HORA_SESSAO de lá. O mesmo
# valor o dia inteiro, para que rodar de novo no mesmo dia não mude nada.
_PRAZO = ("((((now() AT TIME ZONE 'America/Sao_Paulo')::date + %(dias)s::int) + %(hora)s::time)"
          " AT TIME ZONE 'America/Sao_Paulo')")


# ------------------------------------------------------------------ leitura
def _linhas(conn, onde: str, args=()) -> list[dict]:
    sql = _SQL.replace("{jev}", JEV_ESCOPO).replace("{onde}", onde)
    return conn.cursor(row_factory=dict_row).execute(sql, args).fetchall()


def _hoje(conn) -> date:
    return conn.execute("SELECT (now() AT TIME ZONE 'America/Sao_Paulo')::date").fetchone()[0]


def _sem_acento(s: str | None) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def tipica(modalidade: str | None) -> bool:
    """Pregão e concorrência: o caso comum. Dispensa tem brancos esperados (Rio Branco, 11)."""
    m = _sem_acento(modalidade)
    return m.startswith("pregao") or m.startswith("concorrencia")


def impedimentos(c: dict) -> list[tuple[str, str]]:
    """Por que esta licitação NÃO serve para a demo sem PNCP. Vazio = serve."""
    m = []
    if c["estado"] != "preparada":
        if c["estado"] in ("publicada", "verificada"):
            m.append(("estado", "%s: já tem resultado no site, e o W20 não a leva ao W23 sem baixar de novo"
                      % c["estado"]))
        else:
            m.append(("estado", "estado %s: a demo sem PNCP precisa de preparada (texto congelado)" % c["estado"]))
    if not c["escopo_dentro"]:
        m.append(("escopo", "fora do escopo de folha (ADR-003): fn_tomar_vaga_extracao recusa"))
    if not c["no_recorte"]:
        m.append(("recorte", "fora do recorte de 2026 (ADR-015): fn_tomar_vaga_extracao recusa"))
    if not c["leitura_id"] or not c["n_paginas"]:
        m.append(("sem_texto", "sem texto congelado (leitura vigente sem páginas)"))
    if not c["pdfs_ok"]:
        m.append(("sem_pdf", "nenhum PDF no storage: o link 'p. N' do site não abriria"))
    if c["com_lease"]:
        m.append(("lease", "com lease ativo: o W10/W20 está trabalhando nela agora"))
    if c["procedencia_incerta"]:
        m.append(("procedencia", "procedência incerta na importação"))
    if c["ensaio"] and not c["reserva_demo"]:
        m.append(("ensaio", "já é licitação de ensaio de outro uso"))
    return m


def _fora_da_faixa(chars) -> float:
    lo, hi = FAIXA_CHARS
    if chars is None:
        return 99.0
    if chars < lo:
        return round((lo - chars) / 10_000, 1)
    if chars > hi:
        return round((chars - hi) / 10_000, 1)
    return 0.0


def _nivel(c: dict) -> tuple:
    """A qualidade para a demo, sem desempate: é o que a diversidade de UF respeita."""
    return (not c["gravado_pronto"], c["furtivos"] > 0, not tipica(c["modalidade"]),
            c["modo_sugerido"] != "contexto-completo", c["paginas_ocr"] > 0, _fora_da_faixa(c["chars_total"]),
            c["gemea_de"] is not None)


def chave(c: dict, ate: date) -> tuple:
    aberta = c["dia_sessao"] is not None and c["dia_sessao"] >= ate
    return _nivel(c) + (not aberta, -(c["p_filtro_ok"] or 0.0),
                        -(c["fim_prazo"].timestamp() if c["fim_prazo"] else 0.0), c["controle"])


def escolher(elegiveis: list[dict], n: int, ate: date) -> list[dict]:
    """As N primeiras pela chave, trocando a vez por outra UF quando o nível empata."""
    restantes = sorted(elegiveis, key=lambda c: chave(c, ate))
    niveis = {c["controle"]: _nivel(c) for c in restantes}
    escolhidas, ufs = [], set()
    while restantes and len(escolhidas) < n:
        topo = niveis[restantes[0]["controle"]]
        pega = next((c for c in restantes if niveis[c["controle"]] == topo and c["uf"] not in ufs), restantes[0])
        escolhidas.append(pega)
        ufs.add(pega["uf"])
        restantes.remove(pega)
    return escolhidas


def _data(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "?"


def porque(c: dict, hoje: date, ate: date) -> list[str]:
    """O porquê de uma candidata, na ordem em que pesa na escolha."""
    r = ["texto congelado: leitura #%s, %d p., %s caracteres, modo %s"
         % (c["leitura_id"], c["n_paginas"] or 0,
            "%d mil" % round((c["chars_total"] or 0) / 1000), c["modo_sugerido"] or "?")]
    if c["gravado_pronto"]:
        r.append("gravado pronto: replay da execução %s #%s (verificação vigente), sem rede"
                 % (c["origem_vigente"], c["execucao_vigente"]))
    else:
        r.append("gravado ainda não: sem verificação vigente, o /gravado/v1/messages responde 404 até ela passar"
                 " uma vez pelo W23 real e voltar a preparada (--rearmar)")
    r.append("sem texto furtivo" if not c["furtivos"] else
             "%d trecho(s) de texto furtivo: a tag de injeção manda para a revisão — serve ao bloco de"
             " segurança, não ao fluxo principal" % c["furtivos"])
    r.append((c["modalidade"] or "modalidade ?") + ("" if tipica(c["modalidade"]) else
                                                     " (atípica: dispensa/inexigibilidade têm brancos esperados)"))
    r.append("sem OCR" if not c["paginas_ocr"] else
             "OCR em %d p. (texto de imagem ancora pior)" % c["paginas_ocr"])
    fora = _fora_da_faixa(c["chars_total"])
    if fora:
        r.append("tamanho fora da faixa de ~R$ 3-4 (%d-%d mil caracteres)"
                 % (FAIXA_CHARS[0] // 1000, FAIXA_CHARS[1] // 1000))
    if c["gemea_de"]:
        r.append("gêmea de %s (mesmo conjunto de PDFs; informativo)" % c["gemea_de"])
    d = c["dia_sessao"]
    if d is None:
        r.append("sem data de sessão (entra no recorte pela publicação em %s); está na fila do W10, e reservar"
                 " a tira de lá" % _data(c["publicado_em"]))
    elif d >= ate:
        r.append("sessão em %s: ainda aberta no dia da demo" % _data(d))
    elif d < hoje:
        r.append("sessão já passou (%s): o W10 não a pega de qualquer jeito, reservar não atrasa nada; sem"
                 " --prazo o site a mostra encerrada" % _data(d))
    else:
        r.append("sessão em %s, antes do dia da demo (%s): use --prazo" % (_data(d), _data(ate)))
    if c["p_filtro_ok"] is not None:
        r.append("Jev: filtro %d%% (score de que a regra acertou; nunca decisão)" % round(100 * c["p_filtro_ok"]))
    else:
        r.append("Jev: sem score de filtro (o W01 com Jev ainda não a avaliou)")
    return r


def situacao_reservada(c: dict) -> tuple[bool, str]:
    """(serve agora para a demo sem PNCP?, o que dizer)."""
    outros = [t for k, t in impedimentos(c) if k not in ("estado", "ensaio")]
    if c["estado"] == "preparada" and not outros:
        return True, ("pronta para a demo sem PNCP" + (
            "; e para a sem rede (gravado pronto)" if c["gravado_pronto"] else
            "; sem replay gravado ainda (a sem rede precisa dela processada 1x e rearmada)"))
    if c["estado"] == "publicada":
        return False, ("consumida pela demo (publicada, vigente de execução %s): --rearmar a devolve a preparada%s"
                       % (c["origem_vigente"], " com o gravado pronto" if c["gravado_pronto"] else ""))
    if c["estado"] == "retificada":
        return False, ("o PNCP mudou o edital (W01/W70): precisa baixar de novo, não serve mais sem PNCP;"
                       " --soltar e reserve outra")
    if c["estado"] in ("extraindo", "respondida", "verificada"):
        return False, "em processamento agora (%s)" % c["estado"]
    if c["estado"] != "preparada":
        return False, "estado %s: não serve para a demo sem PNCP; --soltar e reserve outra" % c["estado"]
    return False, "; ".join(outros)


def _resumo(c: dict, hoje: date, ate: date, com_porque: bool = True) -> dict:
    d = {k: c[k] for k in ("controle", "slug", "orgao", "uf", "municipio", "modalidade", "objeto", "estado",
                           "reserva_demo", "ensaio", "gravado_pronto", "origem_vigente")}
    d["fim_prazo"] = _iso(c["fim_prazo"])
    if com_porque:
        d["porque"] = porque(c, hoje, ate)
    return d


def listar(conn, ate: date | None = None, limite: int = 10) -> dict:
    """Só lê. Reservadas agora (ainda servem?), candidatas em ordem e o que ficou de fora."""
    with conn.transaction():
        hoje = _hoje(conn)
        ate = ate or hoje + timedelta(days=7)
        linhas = _linhas(conn, "(l.estado = 'preparada' OR l.reserva_demo)")
    reservadas = []
    for c in linhas:
        if c["reserva_demo"]:
            serve, texto = situacao_reservada(c)
            reservadas.append(dict(_resumo(c, hoje, ate, com_porque=False), serve=serve, situacao=texto))
    elegiveis, fora, textos = [], {}, {}
    for c in linhas:
        if c["reserva_demo"]:
            continue
        m = impedimentos(c)
        if m:
            fora[m[0][0]] = fora.get(m[0][0], 0) + 1
            textos.setdefault(m[0][0], m[0][1])
        else:
            elegiveis.append(c)
    ordem = escolher(elegiveis, len(elegiveis), ate)
    return {"hoje": hoje.isoformat(), "ate": ate.isoformat(), "reservadas": reservadas,
            "total_candidatas": len(ordem),
            "abertas_no_dia": sum(1 for c in ordem if c["dia_sessao"] and c["dia_sessao"] >= ate),
            "gravado_pronto": sum(1 for c in ordem if c["gravado_pronto"]),
            "candidatas": [_resumo(c, hoje, ate) for c in ordem[:limite]],
            "fora": [{"motivo": k, "texto": textos[k], "n": n} for k, n in sorted(fora.items(), key=lambda x: -x[1])]}


# ------------------------------------------------------------------ escrita
def _iso(v):
    return v.isoformat() if isinstance(v, (date, datetime)) else v


def _dt(v):
    return datetime.fromisoformat(v) if isinstance(v, str) else v


def _originais(conn, controles: list[str]) -> dict:
    """O registro mais recente de reservar/soltar de cada controle (é dele que vem o original)."""
    if not controles:
        return {}
    linhas = conn.cursor(row_factory=dict_row).execute(
        "SELECT DISTINCT ON (it ->> 'controle') it ->> 'controle' AS controle,"
        "       w.contadores ->> 'acao' AS acao, it -> 'original' AS original, it -> 'depois' AS depois"
        "  FROM execucoes_workflow w"
        " CROSS JOIN LATERAL jsonb_array_elements(COALESCE(w.contadores -> 'itens', '[]'::jsonb)) it"
        " WHERE w.workflow = %s AND w.contadores ->> 'acao' IN ('reservar', 'soltar')"
        "   AND it ->> 'controle' = ANY(%s)"
        " ORDER BY it ->> 'controle', w.id DESC", (LOG_WORKFLOW, controles)).fetchall()
    return {x["controle"]: x for x in linhas if x["acao"] == "reservar"}


def _registrar(conn, acao: str, argumentos: dict, itens: list, extra: dict, inicio: float):
    if not itens:
        return None
    return conn.execute(
        "INSERT INTO execucoes_workflow (workflow, gatilho, argumentos, contadores, status, custo_brl, duracao_s)"
        " VALUES (%s, 'cli', %s, %s, 'ok', 0, %s) RETURNING id",
        (LOG_WORKFLOW, Jsonb(argumentos), Jsonb(dict(acao=acao, itens=itens, **extra)),
         round(time.monotonic() - inicio, 3))).fetchone()[0]


def _estado_flags(reserva, ensaio, fim) -> dict:
    return {"reserva_demo": reserva, "ensaio": ensaio, "fim_prazo": _iso(fim)}


def reservar(conn, n: int | None = None, controles: list[str] | None = None,
             prazo_dias: int | None = None, ate: date | None = None) -> dict:
    """
    Garante N reservadas (ou reserva exatamente `controles`). Idempotente: as que
    já estão reservadas contam, e rodar de novo no mesmo dia não muda nada.
    """
    inicio = time.monotonic()
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK,))
        hoje = _hoje(conn)
        ate = ate or hoje + timedelta(days=7)
        if controles:
            linhas = _linhas(conn, "l.controle = ANY(%s)", (controles,))
            ja = [c for c in linhas if c["reserva_demo"]]
            recusadas = [{"controle": x, "motivos": ["não existe no banco"]}
                         for x in controles if x not in {c["controle"] for c in linhas}]
            alvo = []
            for c in linhas:
                if c["reserva_demo"]:
                    continue
                m = impedimentos(c)
                if m:
                    recusadas.append({"controle": c["controle"], "motivos": [t for _, t in m]})
                else:
                    alvo.append(c)
        else:
            n = PADRAO_N if n is None else n
            linhas = _linhas(conn, "(l.estado = 'preparada' OR l.reserva_demo)")
            ja = [c for c in linhas if c["reserva_demo"]]
            recusadas = []
            elegiveis = [c for c in linhas if not c["reserva_demo"] and not impedimentos(c)]
            alvo = escolher(elegiveis, max(0, n - len(ja)), ate)

        args = {"dias": prazo_dias, "hora": HORA_SESSAO}
        itens, novas = [], []
        for c in alvo:
            r = conn.execute(
                "UPDATE licitacoes SET reserva_demo = true, ensaio = true,"
                "       fim_prazo = CASE WHEN %(dias)s::int IS NULL THEN fim_prazo ELSE " + _PRAZO + " END"
                " WHERE controle = %(c)s AND estado = 'preparada' AND NOT reserva_demo"
                "   AND (lease_por IS NULL OR lease_ate < now())"
                " RETURNING reserva_demo, ensaio, fim_prazo", dict(args, c=c["controle"])).fetchone()
            if r is None:           # o W10/W20 pegou entre a consulta e o UPDATE
                recusadas.append({"controle": c["controle"], "motivos": ["mudou durante a reserva (lease/estado)"]})
                continue
            itens.append({"controle": c["controle"],
                          "antes": _estado_flags(False, c["ensaio"], c["fim_prazo"]),
                          "depois": _estado_flags(*r),
                          "original": {"ensaio": c["ensaio"], "fim_prazo": _iso(c["fim_prazo"]),
                                       "fim_prazo_conhecido": True}})
            novas.append(dict(_resumo(c, hoje, ate), depois=_estado_flags(*r)))

        # As que já estavam: completa o ensaio (o /api/admin/reservar-demo do site
        # não o marca) e renova o prazo, carregando o original do registro.
        originais = _originais(conn, [c["controle"] for c in ja])
        mantidas = []
        for c in ja:
            if c["estado"] != "preparada":
                mantidas.append(dict(_resumo(c, hoje, ate, com_porque=False),
                                     situacao=situacao_reservada(c)[1]))
                continue
            r = conn.execute(
                "UPDATE licitacoes SET ensaio = true,"
                "       fim_prazo = CASE WHEN %(dias)s::int IS NULL THEN fim_prazo ELSE " + _PRAZO + " END"
                " WHERE controle = %(c)s AND reserva_demo AND (NOT ensaio OR (%(dias)s::int IS NOT NULL"
                "   AND fim_prazo IS DISTINCT FROM " + _PRAZO + "))"
                " RETURNING reserva_demo, ensaio, fim_prazo", dict(args, c=c["controle"])).fetchone()
            mantidas.append(dict(_resumo(c, hoje, ate, com_porque=False), situacao=situacao_reservada(c)[1],
                                 depois=_estado_flags(*r) if r else None))
            if r is None:
                continue
            o = originais.get(c["controle"])
            original = (o["original"] if o else
                        {"ensaio": c["ensaio"], "fim_prazo": None, "fim_prazo_conhecido": False})
            itens.append({"controle": c["controle"], "antes": _estado_flags(True, c["ensaio"], c["fim_prazo"]),
                          "depois": _estado_flags(*r), "original": original})

        total = len(ja) + len(novas)
        faltam = 0 if controles else max(0, n - total)
        log = _registrar(conn, "reservar", {"n": n, "controles": controles, "prazo_dias": prazo_dias,
                                            "ate": ate.isoformat()},
                         itens, {"recusadas": recusadas}, inicio)
    return {"novas": novas, "ja_reservadas": mantidas, "recusadas": recusadas, "faltam": faltam,
            "total_reservadas": total, "registro": log, "ate": ate.isoformat()}


def soltar(conn, controles: list[str] | None = None) -> dict:
    """
    Desfaz a reserva: `reserva_demo=false` e, pelo registro da reserva, o `ensaio`
    e o `fim_prazo` de antes. Duas exceções, sempre ditas: vigente de execução
    simulado/gravado mantém `ensaio=true` (T15) e prazo mexido por outro fica.
    """
    inicio = time.monotonic()
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK,))
        onde, args = "l.reserva_demo", ()
        if controles:
            onde, args = "l.reserva_demo AND l.controle = ANY(%s)", (controles,)
        linhas = _linhas(conn, onde, args)
        originais = _originais(conn, [c["controle"] for c in linhas])
        itens, soltas = [], []
        for c in linhas:
            o = originais.get(c["controle"])
            orig = o["original"] if o else None
            notas = []
            ensaio = c["ensaio"] if orig is None or orig.get("ensaio") is None else orig["ensaio"]
            if not ensaio and c["origem_vigente"] in ("simulado", "gravado"):
                ensaio = True
                notas.append("a verificação vigente é de execução %s: ensaio fica true (T15 — sem ele ela não"
                             " poderia ser vigente); para sair do ensaio, reprocesse com provedor real ou importe"
                             " as respostas do agente" % c["origem_vigente"])
            fim = c["fim_prazo"]
            if orig is None:
                notas.append("sem registro desta reserva (feita pelo site?): ensaio e fim_prazo ficam como estão")
            elif orig.get("fim_prazo_conhecido"):
                posto = _dt((o["depois"] or {}).get("fim_prazo"))
                if posto == c["fim_prazo"]:
                    fim = _dt(orig.get("fim_prazo"))
                else:
                    notas.append("fim_prazo mudou depois da reserva (%s): fica como está" % _iso(c["fim_prazo"]))
            r = conn.execute(
                "UPDATE licitacoes SET reserva_demo = false, ensaio = %s, fim_prazo = %s"
                " WHERE controle = %s AND reserva_demo RETURNING reserva_demo, ensaio, fim_prazo",
                (ensaio, fim, c["controle"])).fetchone()
            itens.append({"controle": c["controle"], "antes": _estado_flags(True, c["ensaio"], c["fim_prazo"]),
                          "depois": _estado_flags(*r), "notas": notas})
            soltas.append(dict(_resumo(c, None, None, com_porque=False), depois=_estado_flags(*r), notas=notas))
        log = _registrar(conn, "soltar", {"controles": controles}, itens, {}, inicio)
    return {"soltas": soltas, "registro": log}


def rearmar(conn, controles: list[str] | None = None) -> dict:
    """
    Reservada que a demo publicou -> `preparada` pela máquina de estados, com a
    verificação vigente intacta: é ela que o provedor `gravado` repete. Recusa
    (sem mexer) enquanto a transição `publicada -> preparada` não existir.
    """
    inicio = time.monotonic()
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK,))
        onde, args = "l.reserva_demo AND l.estado = 'publicada'", ()
        if controles:
            onde, args = onde + " AND l.controle = ANY(%s)", (controles,)
        linhas = _linhas(conn, onde, args)
        if not linhas:
            return {"rearmadas": [], "puladas": [], "recusado": None, "registro": None}
        if not conn.execute("SELECT fn_transicao_permitida('publicada', 'preparada')").fetchone()[0]:
            return {"rearmadas": [], "puladas": [], "registro": None,
                    "alvo": [c["controle"] for c in linhas], "sql": TRANSICAO_PROPOSTA,
                    "recusado": "a tabela `transicoes` não tem publicada -> preparada; sem ela a reservada"
                                " publicada não volta ao W23 sem PNCP. Nada foi alterado."}
        itens, feitas, puladas = [], [], []
        for c in linhas:
            if not c["leitura_id"] or not c["n_paginas"]:
                puladas.append({"controle": c["controle"], "motivo": "sem texto congelado"})
                continue
            if c["com_lease"]:
                puladas.append({"controle": c["controle"], "motivo": "com lease ativo (W20 terminando?)"})
                continue
            conn.execute("SELECT fn_transicao(%s, 'preparada', %s, %s)",
                         (c["controle"], MOTIVO_REARMAR,
                          Jsonb({"verificacao_vigente": c["verificacao_vigente"],
                                 "origem_vigente": c["origem_vigente"], "gravado_pronto": c["gravado_pronto"]})))
            itens.append({"controle": c["controle"], "de": "publicada", "para": "preparada",
                          "verificacao_vigente": c["verificacao_vigente"], "gravado_pronto": c["gravado_pronto"]})
            feitas.append(dict(_resumo(c, None, None, com_porque=False), gravado_pronto=c["gravado_pronto"]))
        log = _registrar(conn, "rearmar", {"controles": controles}, itens, {"puladas": puladas}, inicio)
    return {"rearmadas": feitas, "puladas": puladas, "recusado": None, "registro": log}


# ------------------------------------------------------------------ CLI
def _linha_lic(d: dict) -> str:
    return "%s · %s/%s · %s" % (d["controle"], d.get("orgao") or "?", d.get("uf") or "?", d.get("modalidade") or "?")


def _flags(d: dict | None) -> str:
    if not d:
        return "sem mudança"
    return "reserva_demo=%s, ensaio=%s, fim_prazo=%s" % (
        str(d["reserva_demo"]).lower(), str(d["ensaio"]).lower(), d["fim_prazo"] or "—")


def _imprimir_listar(r: dict) -> None:
    ate = date.fromisoformat(r["ate"])
    print("FOPA v3 · reserva para a demo — hoje %s, dia da demo %s (--ate)\n"
          % (_data(date.fromisoformat(r["hoje"])), _data(ate)))
    print("Reservadas agora: %d" % len(r["reservadas"]))
    if not r["reservadas"]:
        print("  (nenhuma — `--reservar %d` escolhe as primeiras candidatas abaixo)" % PADRAO_N)
    for d in r["reservadas"]:
        print("  %s %s\n      %s | %s" % ("ok" if d["serve"] else "!!", _linha_lic(d), d["situacao"],
                                           _flags(d)))
    print("\nCandidatas: %d preparadas no escopo e no recorte de 2026, sem impedimento"
          " (%d ainda abertas em %s; %d com gravado pronto)."
          % (r["total_candidatas"], r["abertas_no_dia"], _data(ate), r["gravado_pronto"]))
    if r["total_candidatas"] and not r["abertas_no_dia"]:
        print("  Nenhuma estará aberta no dia: sem --prazo, as reservadas aparecem encerradas no site.")
    if r["total_candidatas"] and not r["gravado_pronto"]:
        print("  Nenhuma tem replay gravado: a demo sem rede precisa de uma processada 1x (provedor real) e"
              " rearmada (--rearmar).")
    if r["candidatas"]:
        print("As %d primeiras, na ordem em que --reservar escolhe:" % len(r["candidatas"]))
    for i, d in enumerate(r["candidatas"], 1):
        print("\n%2d. %s" % (i, _linha_lic(d)))
        print("    objeto: %s" % (d["objeto"] or "?"))
        for p in d["porque"]:
            print("    - %s" % p)
    if r["fora"]:
        print("\nFora da demo (preparadas que não servem, pelo primeiro motivo):")
        for f in r["fora"]:
            print("  %5d  %s" % (f["n"], f["texto"]))


def _imprimir_reservar(r: dict) -> None:
    print("Reservadas nesta rodada: %d" % len(r["novas"]))
    for d in r["novas"]:
        print("  + %s\n      %s" % (_linha_lic(d), _flags(d["depois"])))
        for p in d["porque"]:
            print("      - %s" % p)
    if r["ja_reservadas"]:
        print("Já estavam reservadas: %d" % len(r["ja_reservadas"]))
        for d in r["ja_reservadas"]:
            print("  = %s\n      %s | %s" % (_linha_lic(d), d["situacao"], _flags(d.get("depois"))))
    for x in r["recusadas"]:
        print("Recusada: %s — %s" % (x["controle"], "; ".join(x["motivos"])))
    if r["faltam"]:
        print("Faltaram %d: não há candidatas suficientes (veja --listar)." % r["faltam"])
    print("Total reservado agora: %d." % r["total_reservadas"]
          + (" Registro: execucoes_workflow #%s (o site lista em /execucoes)." % r["registro"]
             if r["registro"] else " Nada mudou."))


def _imprimir_soltar(r: dict) -> None:
    print("Soltas: %d" % len(r["soltas"]))
    for d in r["soltas"]:
        print("  - %s\n      %s" % (_linha_lic(d), _flags(d["depois"])))
        for nota in d["notas"]:
            print("      ! %s" % nota)
    print("Registro: execucoes_workflow #%s." % r["registro"] if r["registro"] else "Nada reservado: nada mudou.")


def _imprimir_rearmar(r: dict) -> None:
    if r["recusado"]:
        print("Recusado: %s\nAlvo: %s\nMudança de banco necessária (migração a decidir):\n%s"
              % (r["recusado"], ", ".join(r["alvo"]), r["sql"]))
        return
    if not r["rearmadas"] and not r["puladas"]:
        print("Nenhuma reservada publicada: nada a rearmar.")
    for d in r["rearmadas"]:
        print("  ~ %s: publicada -> preparada (%s)" % (
            _linha_lic(d), "gravado pronto" if d["gravado_pronto"] else "sem replay gravado"))
    for x in r["puladas"]:
        print("  pulada %s: %s" % (x["controle"], x["motivo"]))
    if r["registro"]:
        print("Registro: execucoes_workflow #%s." % r["registro"])


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m api.demo_reservar",
        description="Escolhe, reserva e solta licitações em `preparada` para a demonstração (F7).")
    acao = p.add_mutually_exclusive_group(required=True)
    acao.add_argument("--listar", action="store_true", help="reservadas + candidatas com o porquê (só lê)")
    acao.add_argument("--reservar", nargs="?", type=int, const=-1, metavar="N",
                      help="garante N reservadas (padrão %d); com --controles, reserva só estas" % PADRAO_N)
    acao.add_argument("--soltar", action="store_true", help="desfaz a reserva (todas, ou as --controles)")
    acao.add_argument("--rearmar", action="store_true",
                      help="reservada publicada pela demo -> preparada (precisa da transição proposta)")
    p.add_argument("--controles", nargs="+", metavar="CONTROLE")
    p.add_argument("--prazo", type=int, metavar="DIAS", help="com --reservar: sessão em hoje+DIAS, 17h de Brasília")
    p.add_argument("--ate", type=date.fromisoformat, metavar="AAAA-MM-DD", help="dia da demo (padrão hoje+7)")
    p.add_argument("--limite", type=int, default=10, help="candidatas mostradas no --listar (padrão 10)")
    p.add_argument("--json", action="store_true", help="saída em JSON")
    return p


def main(argv=None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")
    p = _parser()
    a = p.parse_args(argv)
    if a.controles:
        ruins = [c for c in a.controles if not RE_CONTROLE.match(c)]
        if ruins:
            p.error("controle fora do formato do PNCP (00000000000000-1-000000/2026): %s" % ", ".join(ruins))
        a.controles = list(dict.fromkeys(a.controles))
    if a.prazo is not None and (a.reservar is None or not 1 <= a.prazo <= 60):
        p.error("--prazo vai com --reservar e fica entre 1 e 60 dias")
    if a.reservar is not None and a.reservar != -1 and (a.reservar < 1 or a.controles):
        p.error("--reservar N pede N >= 1 e não se mistura com --controles")
    try:
        with banco.conectar() as conn:
            conn.autocommit = True
            if a.listar:
                conn.read_only = True
                r, imprimir, ok = listar(conn, a.ate, a.limite), _imprimir_listar, True
            elif a.reservar is not None:
                n = None if a.reservar == -1 else a.reservar
                r = reservar(conn, n=n, controles=a.controles, prazo_dias=a.prazo, ate=a.ate)
                imprimir, ok = _imprimir_reservar, not r["recusadas"] and not r["faltam"]
            elif a.soltar:
                r, imprimir, ok = soltar(conn, a.controles), _imprimir_soltar, True
            else:
                r = rearmar(conn, a.controles)
                imprimir, ok = _imprimir_rearmar, not r["recusado"] and not r["puladas"]
    except banco.BancoIndisponivel as e:
        print("erro: %s (aponte DATABASE_URL para o fopa-postgres, papel worker_rw)" % e, file=sys.stderr)
        return 1
    except psycopg.Error as e:
        print("erro no banco: %s" % str(e).strip().splitlines()[0], file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1,
                         default=lambda v: _iso(v) if isinstance(v, (date, datetime)) else str(v)))
    else:
        imprimir(r)
    return 0 if ok else 2


__all__ = ["listar", "reservar", "soltar", "rearmar", "impedimentos", "porque", "escolher", "chave",
           "TRANSICAO_PROPOSTA", "MOTIVO_REARMAR", "LOG_WORKFLOW", "main"]

if __name__ == "__main__":
    sys.exit(main())
