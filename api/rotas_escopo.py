# -*- coding: utf-8 -*-
"""
POST /escopo/reavaliar — a regra de escopo de HOJE sobre o veredito gravado.

Um cache do resultado de uma regra morre quando a regra muda (40_fumaca,
teste 12). A licitação guarda `escopo_versao` (o sha de escopo.py que a
julgou, `versao.escopo_versao()`); tudo o que foi julgado por outra versão é
reavaliado aqui e gravado por `fn_aplicar_escopo` (db/019), que também move o
estado: o que ainda não tem evidência sai da fila para `fora_escopo`, o que a
regra voltou a aceitar recomeça em `nova`, e o publicado só troca a marca.

`seco: true` só conta, sem gravar. `controles: [...]` restringe.
Sem objeto não se julga: o vazio daria "fora" e tiraria da fila por engano.
Quem chama é o W01 (depois de um deploy que muda a regra) ou o operador; o Jev
nunca (T25).
"""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Body, Depends
from psycopg.rows import dict_row


from . import auth, banco, escopo_ajuste, versao

router = APIRouter(dependencies=[Depends(auth.exigir_token)])

ORIGEM = "W01: regra de escopo reaplicada"


@router.post("/escopo/reavaliar")
def reavaliar(corpo: dict = Body(default={})):
    seco = bool(corpo.get("seco"))
    controles = corpo.get("controles")
    atual = versao.escopo_versao()
    sql = ("SELECT controle, objeto, escopo_dentro, estado::text AS estado FROM licitacoes"
           " WHERE escopo_versao IS DISTINCT FROM %s")
    params: list = [atual]
    if controles:
        sql += " AND controle = ANY(%s)"
        params.append(list(controles))
    contagem: Counter = Counter()
    mudaram = []
    with banco.conectar() as conn:
        conn.row_factory = dict_row
        linhas = conn.execute(sql + " ORDER BY controle", params).fetchall()
        for l in linhas:
            if not (l["objeto"] or "").strip():
                contagem["sem_objeto"] += 1
                continue
            dentro, motivo = escopo_ajuste.avaliar(l["objeto"])
            if seco:
                r = "mesma_decisao" if dentro == l["escopo_dentro"] else "mudaria"
            else:
                r = conn.execute("SELECT fn_aplicar_escopo(%s, %s, %s, %s, %s) AS r",
                                 (l["controle"], dentro, motivo, atual, ORIGEM)).fetchone()["r"]
            contagem[r] += 1
            if dentro != l["escopo_dentro"]:
                mudaram.append({"controle": l["controle"], "estado_antes": l["estado"],
                                "de": l["escopo_dentro"], "para": dentro, "motivo": motivo, "resultado": r})
        if not seco:
            conn.commit()
    return {"escopo_versao": atual, "seco": seco, "avaliadas": len(linhas),
            "resultado": dict(contagem), "mudaram": mudaram}


__all__ = ["router"]
