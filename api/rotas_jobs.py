# -*- coding: utf-8 -*-
"""
Jobs longos do worker (plano, seção 6): /jobs/baixar, /jobs/paginas,
/jobs/importar, /jobs/historico (W41) e GET /jobs/{id}. POST devolve 202
{job_id}; o estado mora na tabela `jobs` (ver `api.jobs`).

VALIDAR ANTES DE ENFILEIRAR
  O que dá para recusar sem trabalho (controle malformado, licitação que não
  existe, doc sem url, pasta de snapshot que não existe) é recusado aqui, com
  422/404 síncrono. Um job que nasce condenado custaria ao n8n um laço inteiro
  de Wait → GET para descobrir o que o POST já sabia.

O LAÇO DO n8n
  `GET /jobs/{id}` devolve `status` ∈ queued | running | done | error. O laço
  do W21/W22 tem de continuar enquanto for `queued` OU `running`: com
  `FOPA_JOBS_CONCORRENCIA=2`, um terceiro job espera na fila.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse

from . import auth, banco, config, jobs
from . import storage as storage_mod


@asynccontextmanager
async def _ciclo(_app):
    # No arranque: jobs que o processo anterior deixou `running` viram
    # `error` (plano, seção 6). No fim: a fila para; o que rodava vira órfão
    # declarado no próximo arranque, nunca um `running` eterno.
    jobs.recuperar_orfaos_no_arranque()
    yield
    jobs.encerrar()


router = APIRouter(lifespan=_ciclo)
_AUTH = [Depends(auth.exigir_token)]


def _aceito(job_id: str, reaproveitado: bool) -> JSONResponse:
    return JSONResponse({"job_id": job_id, "reaproveitado": reaproveitado}, status_code=202)


def _controle_valido(corpo: dict) -> str:
    from migracao import regras
    bruto = corpo.get("controle")
    controle = bruto.strip() if isinstance(bruto, str) else ""
    try:
        regras.partes_controle(controle)
    except ValueError:
        raise HTTPException(422, "controle ausente ou fora do formato CNPJ-1-SEQ/ANO: %r" % (bruto,)) from None
    return controle


def _licitacao_existe(controle: str) -> None:
    with banco.conectar() as conn:
        if not conn.execute("SELECT 1 FROM licitacoes WHERE controle = %s", (controle,)).fetchone():
            raise HTTPException(404, "licitação não existe: %s" % controle)


def _storage():
    return storage_mod.abrir(config.carregar())


# ------------------------------------------------------------------ GET
@router.get("/jobs/{job_id}", dependencies=_AUTH)
def obter_job(job_id: str):
    d = jobs.obter(job_id)
    if not d:
        raise HTTPException(404, "job não existe: %s" % job_id)
    return d


# ------------------------------------------------------------------ /jobs/paginas (W22)
@router.post("/jobs/paginas", dependencies=_AUTH)
def jobs_paginas(corpo: dict = Body(...)):
    """Congela o texto da licitação: `leituras` + `paginas` (ver `api.leitura`)."""
    from . import leitura
    controle = _controle_valido(corpo)
    _licitacao_existe(controle)

    def trabalho(ctx):
        return leitura.ler_licitacao(controle, _storage(), progresso=ctx.progresso)

    return _aceito(*jobs.submeter("paginas", controle, trabalho, deduplicar=True))


# ------------------------------------------------------------------ /jobs/baixar (W21)
def _docs_validos(corpo: dict) -> list[dict]:
    docs = corpo.get("docs")
    if not isinstance(docs, list):
        raise HTTPException(422, "docs deve ser a lista do PNCP /arquivos (filtrada e ordenada pelo n8n)")
    for i, d in enumerate(docs):
        if not isinstance(d, dict) or not isinstance(d.get("url"), str) or not d["url"].strip():
            raise HTTPException(422, "docs[%d] sem url" % i)
        seq = d.get("sequencialDocumento")
        # O nome do arquivo é "%02d - ..." (28:549): sem sequencial inteiro não
        # há nome, e o 28 morreria no meio do laço.
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise HTTPException(422, "docs[%d].sequencialDocumento deve ser inteiro: %r" % (i, seq))
    return docs


@router.post("/jobs/baixar", dependencies=_AUTH)
def jobs_baixar(corpo: dict = Body(...)):
    """Baixa, avalia e grava os documentos (ver `api.baixar`). Não transiciona estado."""
    from . import baixar
    controle = _controle_valido(corpo)
    docs = _docs_validos(corpo)
    _licitacao_existe(controle)

    def trabalho(ctx):
        return baixar.baixar_licitacao(controle, docs, _storage(), progresso=ctx.progresso)

    return _aceito(*jobs.submeter("baixar", controle, trabalho, deduplicar=True))


# ------------------------------------------------------------------ /jobs/historico (W41)
@router.post("/jobs/historico", dependencies=_AUTH)
def jobs_historico():
    """
    A rodada diária do histórico do PNCP (W41): licitações novas, itens e resultados do acervo, cabeçalhos pendentes e
    contratos (ver `api.historico_pncp.rodada_diaria`). Uma por vez: POST com a rodada ainda viva devolve o job dela.
    """
    from . import historico_pncp
    url = config.carregar().database_url
    if not url:
        raise HTTPException(503, "worker sem DATABASE_URL")

    def trabalho(ctx):
        return historico_pncp.rodada_diaria(url, progresso=ctx.progresso)

    # Fila `rede`: a rodada espera o PNCP quase o tempo todo e não pode ocupar a vaga do OCR.
    return _aceito(*jobs.submeter("historico", None, trabalho, deduplicar=True, fila=jobs.FILA_REDE))


# ------------------------------------------------------------------ /jobs/importar (seção 9)
@router.post("/jobs/importar", dependencies=_AUTH)
def jobs_importar(corpo: dict = Body(...)):
    """
    Importa um snapshot do acervo v2 (`migracao.importar.aplicar`) e publica o
    que ficou `verificada` (`migracao.publicar.publicar`), como job.

    `{snapshot_dir, amostras_dir, hoje?, manifesto_sha256?, seco?}`. O
    `manifesto_sha256` amarra o job ao snapshot que alguém conferiu: outro
    manifesto na mesma pasta aborta antes de escrever.
    """
    snap, vivo = corpo.get("snapshot_dir"), corpo.get("amostras_dir")
    for nome, valor in (("snapshot_dir", snap), ("amostras_dir", vivo)):
        if not isinstance(valor, str) or not os.path.isdir(valor):
            raise HTTPException(422, "%s não é uma pasta: %r" % (nome, valor))
    if not os.path.isfile(os.path.join(snap, "manifesto.json")):
        raise HTTPException(422, "snapshot sem manifesto.json: %s" % snap)
    try:
        hoje = date.fromisoformat(corpo["hoje"]) if corpo.get("hoje") else None
    except (TypeError, ValueError):
        raise HTTPException(422, "hoje deve ser AAAA-MM-DD: %r" % (corpo.get("hoje"),)) from None
    esperado = (corpo.get("manifesto_sha256") or "").strip().lower() or None
    seco = bool(corpo.get("seco"))

    def trabalho(ctx):
        from migracao import importar, plano as plano_mod, publicar
        from migracao.acervo import Acervo
        ctx.progresso(etapa="planejando", snapshot=snap)
        acervo = Acervo(snap, vivo)
        if esperado and acervo.manifesto_sha256 != esperado:
            raise ValueError("manifesto do snapshot tem sha %s, esperado %s: nada importado"
                             % (acervo.manifesto_sha256, esperado))
        plano = plano_mod.montar(acervo, hoje=hoje or date.today())
        resumo = {"snapshot": plano.carimbo, "manifesto_sha256": plano.manifesto_sha256,
                  "licitacoes": len(plano.licitacoes), "leituras": len(plano.leituras),
                  "execucoes": len(plano.execucoes), "decisoes": len(plano.decisoes),
                  "avisos": len(plano.avisos)}
        if seco:
            return {"seco": True, "plano": resumo}
        storage = _storage()
        ctx.progresso(etapa="importando", **resumo)
        with banco.conectar() as conn:
            contagens = importar.aplicar(conn, plano, acervo, storage)
        ctx.progresso(etapa="publicando")
        with banco.conectar() as conn:
            publicacao = publicar.publicar(conn, storage)
        return {"seco": False, "plano": resumo, "contagens": contagens, "publicacao": publicacao}

    return _aceito(*jobs.submeter("importar", None, trabalho))


__all__ = ["router"]
