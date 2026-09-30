# -*- coding: utf-8 -*-
"""
Rotas do Jev (segundo sinal). O n8n pede os corpos, chama o Jev com a
credencial dele e devolve a resposta para interpretar; o worker grava o sinal
em `sinais_jev` e, havendo convicção, a candidata (fila de revisão). Nenhuma
rota daqui escreve veredito, confiança ou escopo (T25).
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from fopa import jev as cliente

from . import auth, banco, escopo_ajuste, jev

router = APIRouter(prefix="/jev", dependencies=[Depends(auth.exigir_token)])


@router.post("/escopo/corpos")
def escopo_corpos(corpo: dict = Body(...)):
    """Um corpo por objeto, com o que a REGRA decidiu ao lado (é contra ela que se discorda)."""
    reqs = []
    for it in corpo.get("itens") or []:
        dentro, motivo = escopo_ajuste.avaliar(it.get("objeto") or "")
        reqs.append({"controle": it.get("controle"), "regra_dentro": dentro, "regra_motivo": motivo,
                     "body": jev.corpo_escopo(it.get("objeto") or "")})
    return {"url": cliente.URL, "criterio_versao": jev.CRITERIO_ESCOPO, "requisicoes": reqs}


@router.post("/escopo/edital/corpos")
def escopo_edital_corpos(corpo: dict = Body(...)):
    """
    O escopo com o EDITAL (73_): objeto + páginas da leitura vigente escolhidas por termo. Só licitação com
    leitura (extraída); a regra ao lado é a que está gravada. `so_faltando`: pula quem já tem esse sinal.
    """
    controles = [c for c in (corpo.get("controles") or []) if c]
    with banco.conectar() as conn:
        conn.row_factory = dict_row
        reqs = _escopo_edital(conn, controles, bool(corpo.get("so_faltando")))
    return {"url": cliente.URL, "criterio_versao": jev.CRITERIO_ESCOPO_EDITAL, "requisicoes": reqs}


def _escopo_edital(conn, controles: list[str], so_faltando: bool) -> list[dict]:
    linhas = conn.execute(
        "SELECT l.controle, l.objeto, l.escopo_dentro, l.leitura_vigente_id FROM licitacoes l"
        " WHERE l.controle = ANY(%s) AND l.leitura_vigente_id IS NOT NULL"
        "   AND NOT (%s AND EXISTS (SELECT 1 FROM sinais_jev s WHERE s.tipo = 'escopo'"
        "        AND s.controle = l.controle AND s.criterio_versao = %s))"
        " ORDER BY l.controle",
        (controles, so_faltando, "escopo-" + jev.CRITERIO_ESCOPO_EDITAL)).fetchall()
    reqs = []
    for x in linhas:
        paginas = [(p["arquivo_nome"], p["numero"], p["texto"]) for p in conn.execute(
            "SELECT arquivo_nome, numero, texto FROM paginas WHERE leitura_id = %s ORDER BY arquivo_nome, numero",
            (x["leitura_vigente_id"],)).fetchall()]
        body, como = jev.corpo_escopo_edital(x["objeto"], paginas)
        reqs.append({"controle": x["controle"], "regra_dentro": bool(x["escopo_dentro"]),
                     "contexto_enviado": como, "body": body})
    return reqs


def _gravar(conn, **s) -> int:
    return conn.execute(
        "INSERT INTO sinais_jev (tipo, controle, verificacao_id, pergunta_id, criterio_versao, regra, resposta,"
        " p_sim, confianca, probabilidades, contexto_enviado, candidata, usd, tok_entrada, modelo_jev)"
        " VALUES (%(tipo)s, %(controle)s, %(verificacao_id)s, %(pergunta_id)s, %(criterio_versao)s, %(regra)s,"
        " %(resposta)s, %(p_sim)s, %(confianca)s, %(probabilidades)s, %(contexto_enviado)s, %(candidata)s,"
        " %(usd)s, %(tok_entrada)s, %(modelo_jev)s) RETURNING id", s).fetchone()["id"]


@router.post("/escopo/interpretar")
def escopo_interpretar(corpo: dict = Body(...)):
    resp = corpo.get("resposta") or {}
    s = jev.interpretar_escopo(bool(corpo.get("regra_dentro")), resp.get("answers"), resp.get("usage"))
    contexto = corpo.get("contexto_enviado") or "objeto"
    criterio = jev.CRITERIO_ESCOPO_EDITAL if contexto.startswith("edital") else jev.CRITERIO_ESCOPO
    with banco.conectar() as conn:
        conn.row_factory = dict_row
        s["sinal_id"] = _gravar(conn, tipo="escopo", controle=corpo.get("controle"), verificacao_id=None,
                                pergunta_id=None, criterio_versao="escopo-" + criterio,
                                regra="dentro" if corpo.get("regra_dentro") else "fora",
                                resposta=s["resposta"], p_sim=s["p_sim"], confianca=s["confianca"],
                                probabilidades=None, contexto_enviado=contexto, candidata=s["candidata"],
                                usd=s["usd"], tok_entrada=s["tok_entrada"], modelo_jev=resp.get("model"))
        conn.commit()
    return s


@router.post("/sustenta/corpos")
def sustenta_corpos(corpo: dict = Body(...)):
    """
    Toda resposta que cita trecho, qualquer veredito, ganha a métrica do Jev: o quanto a passagem sustenta a
    resposta. Sem trecho não há passagem para
    julgar. `so_faltando`: pula a pergunta que já tem o sinal do critério atual (rodar de novo é barato).
    """
    vid = corpo.get("verificacao_id")
    if not vid:
        raise HTTPException(422, "informe verificacao_id")
    with banco.conectar() as conn:
        conn.row_factory = dict_row
        v = conn.execute("SELECT * FROM verificacoes WHERE id = %s", (vid,)).fetchone()
        if not v:
            raise HTTPException(404, "verificação %s não existe" % vid)
        if not v["leitura_id"]:
            raise HTTPException(409, "verificação sem páginas congeladas: não há passagem para julgar")
        linhas = conn.execute(
            "SELECT vr.pergunta_id, vr.veredito, vr.arquivo_canonico, vr.pagina_final, r.resposta,"
            " r.trecho_literal, p.texto AS pergunta FROM verificacao_respostas vr"
            " JOIN respostas r ON r.execucao_id = %s AND r.pergunta_id = vr.pergunta_id"
            " JOIN perguntas p ON p.id = vr.pergunta_id"
            " WHERE vr.verificacao_id = %s AND vr.ausencia IS NULL"
            "   AND coalesce(r.trecho_literal, '') <> '' AND vr.arquivo_canonico IS NOT NULL"
            # "já tem sinal" = da mesma EXECUÇÃO (re-verificar não muda a resposta — api/consultas.py)
            "   AND NOT (%s AND EXISTS (SELECT 1 FROM sinais_jev s JOIN verificacoes vs ON vs.id = s.verificacao_id"
            "        WHERE s.tipo = 'sustenta' AND vs.execucao_id = %s AND s.pergunta_id = vr.pergunta_id"
            "        AND s.criterio_versao = %s))"
            " ORDER BY vr.pergunta_id",
            (v["execucao_id"], vid, bool(corpo.get("so_faltando")), v["execucao_id"],
             jev.CRITERIO_SUSTENTA)).fetchall()
        reqs = []
        for x in linhas:
            paginas = [p["texto"] for p in conn.execute(
                "SELECT texto FROM paginas WHERE leitura_id = %s AND arquivo_nome = %s ORDER BY numero",
                (v["leitura_id"], x["arquivo_canonico"])).fetchall()]
            body, como = jev.corpo_sustenta(x["pergunta"], x["resposta"], x["trecho_literal"],
                                            x["arquivo_canonico"], x["pagina_final"], paginas)
            reqs.append({"pergunta_id": x["pergunta_id"], "veredito": x["veredito"], "contexto_enviado": como,
                         "body": body})
        # A mesma rodada da W24 leva o escopo com o EDITAL (73_), uma vez por licitação lida: sem ele, a extraída
        # daqui em diante ficaria só com a nota do objeto (api/consultas.py:JEV_ESCOPO faz a média). Sem
        # pergunta = o escopo da licitação; o `interpretar` abaixo reconhece e grava como sinal de escopo.
        for r in _escopo_edital(conn, [v["controle"]], so_faltando=True):
            reqs.append(dict(r, pergunta_id=None, tipo="escopo"))
    return {"url": cliente.URL, "criterio_versao": jev.CRITERIO_SUSTENTA, "controle": v["controle"],
            "requisicoes": reqs}


@router.post("/sustenta/interpretar")
def sustenta_interpretar(corpo: dict = Body(...)):
    if corpo.get("pergunta_id") is None and str(corpo.get("contexto_enviado") or "").startswith("edital"):
        # a requisição de escopo que a rodada da W24 levou junto (sustenta_corpos)
        with banco.conectar() as conn:
            conn.row_factory = dict_row
            x = conn.execute("SELECT l.controle, l.escopo_dentro FROM verificacoes v JOIN licitacoes l"
                             " ON l.controle = v.controle WHERE v.id = %s", (corpo.get("verificacao_id"),)).fetchone()
        if not x:
            raise HTTPException(404, "verificação não existe")
        return escopo_interpretar({"controle": x["controle"], "regra_dentro": bool(x["escopo_dentro"]),
                                   "contexto_enviado": corpo.get("contexto_enviado"),
                                   "resposta": corpo.get("resposta")})
    resp = corpo.get("resposta") or {}
    s = jev.interpretar_sustenta(resp.get("answers"), resp.get("usage"))
    with banco.conectar() as conn:
        conn.row_factory = dict_row
        v = conn.execute("SELECT controle FROM verificacoes WHERE id = %s",
                         (corpo.get("verificacao_id"),)).fetchone()
        if not v:
            raise HTTPException(404, "verificação não existe")
        vr = conn.execute("SELECT veredito FROM verificacao_respostas WHERE verificacao_id = %s AND pergunta_id = %s",
                          (corpo.get("verificacao_id"), corpo.get("pergunta_id"))).fetchone()
        veredito = vr["veredito"] if vr else None
        s["sinal_id"] = _gravar(conn, tipo="sustenta", controle=v["controle"],
                                verificacao_id=corpo.get("verificacao_id"), pergunta_id=corpo.get("pergunta_id"),
                                criterio_versao=jev.CRITERIO_SUSTENTA, regra=veredito, resposta=s["resposta"],
                                p_sim=s["p_sustenta"], confianca=s["confianca"],
                                probabilidades=Jsonb(s["probabilidades"]) if s["probabilidades"] else None,
                                contexto_enviado=corpo.get("contexto_enviado"), candidata=s["candidata"],
                                usd=s["usd"], tok_entrada=s["tok_entrada"], modelo_jev=resp.get("model"))
        if s["candidata"] and veredito == "APROVADO":
            # Fila de revisão humana — o veredito do verificador NÃO muda. Só a APROVADA abre revisão: é
            # nela que mora o ponto cego da ancoragem; a REVISAR já está com um revisor humano e o score vai à tela.
            conn.execute("INSERT INTO revisoes_humanas (controle, verificacao_id, pergunta_id, motivo, status)"
                         " VALUES (%s, %s, %s, %s, 'aberta')",
                         (v["controle"], corpo.get("verificacao_id"), corpo.get("pergunta_id"),
                          "jev: %s p=%.2f (%s)" % (s["resposta"], s["confianca"] or 0,
                                                   corpo.get("contexto_enviado") or "?")))
        conn.commit()
    return s


__all__ = ["router"]
