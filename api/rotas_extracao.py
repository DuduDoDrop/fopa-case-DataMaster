# -*- coding: utf-8 -*-
"""
O caminho da extração que o W23/W24 do n8n percorre (plano, seção 6):
/prompt, /responder-simulado, /gravado/v1/messages, /verificar e
/importar-respostas. Nenhuma rota daqui chama modelo: quem chama é o n8n, com
a credencial dele; o worker nunca tem a chave (`/health.anthropic_key_presente`).
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from fopa import extrator, melhor_de_n, modelos, verificador
from fopa.modelos import ErroModelo, Uso
from fopa.questionario import NAO_LOCALIZADO

from migracao import regras

from . import auth, banco, config, extracao, injecao, persistencia, politica, reconstrucao
from . import storage as storage_mod

router = APIRouter(dependencies=[Depends(auth.exigir_token)])


def _licitacao_da_leitura(conn, leitura_id: int) -> tuple[dict, list]:
    le = conn.execute("SELECT controle FROM leituras WHERE id = %s", (leitura_id,)).fetchone()
    if not le:
        raise HTTPException(404, "leitura %s não existe" % leitura_id)
    lic = conn.execute("SELECT * FROM licitacoes WHERE controle = %s", (le["controle"],)).fetchone()
    return lic, reconstrucao.paginas_da_leitura(conn, leitura_id)


@router.post("/prompt")
def prompt(corpo: dict = Body(...)):
    """
    Os corpos dos lotes, prontos para o HTTP Request do W23. `body` é o da
    Anthropic, `body_openai` o da Responses API; o n8n escolhe pelo provedor
    vigente em `configuracao`. `request_sha256` vai para `chamadas_modelo`.
    """
    from . import versao
    if not corpo.get("leitura_id"):
        raise HTTPException(422, "informe leitura_id")
    with banco.conectar() as conn:
        conn.row_factory = dict_row
        lic, paginas = _licitacao_da_leitura(conn, int(corpo["leitura_id"]))
    if not paginas:
        raise HTTPException(409, "leitura sem páginas")
    d = extracao.montar_prompt(
        paginas, corpo.get("rotulo") or reconstrucao._nome(lic), lote=int(corpo.get("lote") or 6),
        k_rag=int(corpo.get("k_rag") or 6), modo=corpo.get("modo"),
        modelo=corpo.get("modelo") or modelos.MODELO_EXTRATOR, effort=corpo.get("effort") or "high",
        max_tokens=int(corpo.get("max_tokens") or 16000), ids_pendentes=corpo.get("ids_pendentes"))
    d["versao_prompt"] = versao.versao_prompt()
    d["controle"] = lic["controle"]
    return d


@router.post("/responder-simulado")
def responder_simulado(corpo: dict = Body(...)):
    """O `ProvedorSimulado` (regex, sem rede) no envelope da Anthropic: o fluxo não muda."""
    if not isinstance(corpo.get("body"), dict):
        raise HTTPException(422, "informe body (o mesmo corpo enviado ao modelo)")
    return extracao.responder_simulado(corpo["body"])


@router.post("/gravado/v1/messages")
def gravado(corpo: dict = Body(...), controle: str = Query(...)):
    """
    Replay da execução canônica do controle, lote a lote — o plano B da demo sem
    rede (plano, F7): o canvas roda idêntico ao real, a R$ 0. O legado não tem
    chamadas gravadas; aí a resposta é remontada das respostas cruas.
    """
    if not isinstance(corpo.get("body"), dict):
        raise HTTPException(422, "informe body")
    _, usuario = extracao.partes_do_corpo(corpo["body"])
    ids = extracao.ids_do_usuario(usuario)
    with banco.conectar() as conn:
        conn.row_factory = dict_row
        e = conn.execute("SELECT e.* FROM verificacoes v JOIN execucoes_modelo e ON e.id = v.execucao_id"
                         " WHERE v.controle = %s AND v.vigente", (controle,)).fetchone()
        if not e:
            raise HTTPException(404, "sem execução canônica para %s" % controle)
        # Só os lotes normais bem-sucedidos: uma chamada de reforço do Best-of-N (rodada > 0) com os mesmos ids, ou
        # uma que falhou, não é o que a execução respondeu naquele lote (revisão da v3.1, 28/09).
        for c in reversed(conn.execute("SELECT lote_ids, dados FROM chamadas_modelo WHERE execucao_id = %s"
                                       " AND rodada = 0 AND COALESCE(http_status, 200) = 200"
                                       " AND COALESCE(stop_reason, 'end_turn') = 'end_turn'"
                                       " ORDER BY id", (e["id"],)).fetchall()):
            if set(c["lote_ids"] or []) == set(ids) and c["dados"]:
                return c["dados"]
        crus = {r["pergunta_id"]: r for r in conn.execute(
            "SELECT * FROM respostas WHERE execucao_id = %s", (e["id"],)).fetchall()}
    dados = {"respostas": [{"id": i, "resposta": crus[i]["resposta"], "arquivo": crus[i]["arquivo_citado"],
                            "pagina": crus[i]["pagina_citada"], "trecho_literal": crus[i]["trecho_literal"],
                            "conflito": crus[i]["conflito"], "confianca": crus[i]["confianca"] or "media"}
                           for i in ids if i in crus]}
    return extracao.envelope_anthropic(dados, "gravado:%s" % (e["modelo"] or ""))


# ------------------------------------------------------------------ fusão das chamadas gravadas
def _n_configurado(conn) -> int:
    """O N do Best-of-N (`configuracao.melhor_de_n`, db/050); 1 = desligado. Sem a linha, desligado."""
    linha = conn.execute("SELECT valor FROM configuracao WHERE chave = 'melhor_de_n'").fetchone()
    try:
        return max(1, int(linha["valor"])) if linha else 1
    except (TypeError, ValueError):
        return 1


def _chamadas(conn, execucao_id: int, modelo: str) -> tuple[dict, list, list]:
    """
    As chamadas gravadas: `(por_lote, reforcos, tentadas)`. Rodada 0 (os lotes normais): a última BEM-SUCEDIDA de
    cada lote vale — retentativa sobrescreve a que falhou. Rodada > 0 (o reforço do Best-of-N, db/050): as
    bem-sucedidas, em ordem, como `(rodada, ids, dados, uso)` em `reforcos`; e TODAS, inclusive as que falharam, como
    `(rodada, ids)` em `tentadas` — o reforço tentado e pago entra no registro mesmo sem candidato.
    """
    por_lote: dict[frozenset, tuple] = {}
    reforcos: list[tuple] = []
    tentadas: list[tuple] = []
    for c in conn.execute("SELECT * FROM chamadas_modelo WHERE execucao_id = %s ORDER BY id",
                          (execucao_id,)).fetchall():
        if (c.get("rodada") or 0) > 0:
            tentadas.append((c["rodada"], list(c["lote_ids"] or [])))
        if c["http_status"] not in (None, 200) or (c["stop_reason"] or "end_turn") != "end_turn":
            continue
        try:
            dados = extracao.dados_do_envelope(c["dados"])
        except (ValueError, TypeError, KeyError):
            continue
        uso = Uso(entrada=c["tok_entrada"] or 0, saida=c["tok_saida"] or 0,
                  cache_escrita=c["tok_cache_escrita"] or 0, cache_leitura=c["tok_cache_leitura"] or 0,
                  chamadas=1, segundos=float(c["segundos"] or 0), modelo=modelo)
        ids = list(c["lote_ids"] or [])
        if (c.get("rodada") or 0) > 0:
            reforcos.append((c["rodada"], ids, dados, uso))
        else:
            por_lote[frozenset(ids)] = (ids, dados, uso)
    return por_lote, reforcos, tentadas


def _extracao(e: dict, lic: dict, por_lote: dict, paginas: list):
    """O `extrator.extrair` da v2 sobre as chamadas da rodada 0 (provedor gravado, páginas congeladas)."""
    prov = extracao.ProvedorGravado(e["provedor"] or "claude", list(por_lote.values()))
    agente = e["origem"] == "agente"
    try:
        ext = extracao.extrair_gravado(
            paginas, reconstrucao._nome(lic), prov, modelo=e["modelo"] or "",
            modo="contexto-completo" if agente else (e["modo"] if e["modo"] in ("rag", "contexto-completo") else None),
            lote=17 if agente else (e["lote"] or 6), k_rag=e["k_rag"] or 6, effort=e["effort"] or "high")
    except ErroModelo as erro:
        raise HTTPException(422, str(erro))
    if agente:
        ext.modo = "agente"
    return ext


def _aplicar_reforcos(ext, reforcos: list, tentadas: list, n: int) -> dict | None:
    """
    Best-of-N (v3.1): os candidatos do reforço entram na disputa, pergunta a pergunta, e o verificador escolhe
    (`melhor_de_n.aplicar`). O custo das chamadas de reforço bem-sucedidas entra no uso da execução. A pergunta que
    o reforço não trouxe (chamada que falhou, ou que voltou sem ela) não vira candidata — é tentativa que falhou, e
    o registro a conta. Sem nenhuma tentativa de reforço, `None`.
    """
    if not tentadas:
        return None
    candidatos: dict[str, list] = {}
    for _, ids, dados, uso in reforcos:
        ext.uso.somar(uso)
        for r in extrator.respostas_do_lote(dados, ids, pular_ausentes=True):
            candidatos.setdefault(r.id, []).append(r)
    feitas: dict[str, int] = {}
    for _, ids in tentadas:
        for pid in ids:
            feitas[pid] = feitas.get(pid, 0) + 1
    registro = {"n": n, "rodadas": max(rodada for rodada, _ in tentadas),
                "perguntas": melhor_de_n.aplicar(ext, candidatos, feitas)}
    # a abstenção é uma condição observada (condicoes.py): a pergunta que o reforço achou deixa de ser abstenção
    ext.condicoes.abstencoes = [r.id for r in ext.respostas
                                if r.resposta.strip().lower().startswith(NAO_LOCALIZADO.lower())]
    return registro


def verificar_execucao(conn, execucao_id: int, modalidade: str | None = None,
                       usar_itens_api: bool = True) -> dict:
    """Funde as chamadas gravadas, escolhe entre os candidatos do reforço, verifica e fecha a execução.
    Não torna nada vigente."""
    from . import versao
    conn.row_factory = dict_row
    e = conn.execute("SELECT * FROM execucoes_modelo WHERE id = %s", (execucao_id,)).fetchone()
    if not e:
        raise HTTPException(404, "execução %s não existe" % execucao_id)
    if not e["leitura_id"]:
        raise HTTPException(409, "execução %s sem leitura: não há texto contra o que verificar" % execucao_id)
    vr = versao.versao_regras()
    if conn.execute("SELECT 1 FROM verificacoes WHERE execucao_id = %s AND versao_regras = %s",
                    (execucao_id, vr)).fetchone():
        raise HTTPException(409, "a execução %s já foi verificada na versão %s" % (execucao_id, vr[:12]))

    por_lote, reforcos, tentadas = _chamadas(conn, execucao_id, e["modelo"] or "")
    cobertos = set().union(*por_lote) if por_lote else set()
    faltam = [i for i in extracao.IDS if i not in cobertos]
    if faltam:
        raise HTTPException(422, "as chamadas gravadas não cobrem: %s" % ", ".join(faltam))

    lic = conn.execute("SELECT * FROM licitacoes WHERE controle = %s", (e["controle"],)).fetchone()
    leitura = conn.execute("SELECT condicoes FROM leituras WHERE id = %s", (e["leitura_id"],)).fetchone()
    paginas = reconstrucao.paginas_da_leitura(conn, e["leitura_id"])
    ext = _extracao(e, lic, por_lote, paginas)
    registro_n = _aplicar_reforcos(ext, reforcos, tentadas, _n_configurado(conn))
    agente = e["origem"] == "agente"
    c = ext.condicoes
    lc = leitura["condicoes"] or {}
    c.arquivos_ocr = list(lc.get("arquivos_ocr") or [])
    c.paginas_ocr = lc.get("paginas_ocr") or 0
    c.furtivos = list(lc.get("furtivos") or [])
    # Injeção de verdade (api/injecao.py): só os trechos SUSPEITOS contam como texto furtivo.
    suspeitos = injecao.suspeitos(conn, storage_mod.abrir(config.carregar()), e["leitura_id"], lc)
    if suspeitos is not None:
        c.furtivos = suspeitos
    # Só é "provedor secundário" o plano B de OUTRO fornecedor (ADR-012); simulado,
    # gravado e agente não são degradação de leitura (70_:528-537).
    c.secundario = (e["provedor"] or "") not in ("claude", "simulado", "gravado", "claude-code", "")
    crus = [r.para_dict() for r in ext.respostas]           # antes do verificador mexer
    itens = None
    if usar_itens_api:
        linha = conn.execute("SELECT payload FROM itens_api WHERE controle = %s", (e["controle"],)).fetchone()
        itens = linha["payload"] if linha else None
    rel = politica.aplicar(ext, verificador.verificar(ext, itens, modalidade=modalidade or lic["modalidade"]))

    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO respostas (execucao_id, pergunta_id, resposta, arquivo_citado, pagina_citada,"
            " trecho_literal, conflito, confianca) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT DO NOTHING",
            [(execucao_id, r["id"], r["resposta"] or "", r["arquivo"], r["pagina"], r["trecho_literal"],
              r["conflito"], r["confianca"] if r["confianca"] in ("alta", "media", "baixa") else None)
             for r in crus])
    u = ext.uso
    # O agente local (ADR-014) não passou por API: sem preço, mesmo com o modelo que ele registra (claude-opus-5-5)
    # na tabela desde 26/09 — senão a execução ficaria com R$ 0,00, e R$ 0 nunca é o que se grava (ADR-012).
    preco = u.preco_conhecido and not agente
    conn.execute(
        "UPDATE execucoes_modelo SET status = 'ok', erro = NULL, chamadas = %s, tok_entrada = %s,"
        " tok_saida = %s, tok_cache_escrita = %s, tok_cache_leitura = %s, tok_raciocinio = %s,"
        " segundos = %s, usd = %s, brl = %s, usd_brl = %s, preco_conhecido = %s,"
        " respostas_sha256 = %s, finalizado_em = now() WHERE id = %s",
        (u.chamadas, u.entrada, u.saida, u.cache_escrita, u.cache_leitura, u.raciocinio, u.segundos,
         round(u.usd, 4) if preco else None, round(u.brl, 3) if preco else None,
         modelos.USD_BRL if preco else None, preco, regras.respostas_sha256(crus), execucao_id))
    vid = persistencia.gravar_verificacao(conn, execucao_id=execucao_id, controle=e["controle"],
                                         leitura_id=e["leitura_id"], ext=ext, rel=rel,
                                         versao_regras=vr, itens_api_usados=bool(itens))
    if registro_n is not None:
        conn.execute("UPDATE verificacoes SET melhor_de_n = %s WHERE id = %s", (Jsonb(registro_n), vid))
    conn.commit()
    return {"execucao_id": execucao_id, "verificacao_id": vid, "versao_regras": vr,
            "resumo": persistencia.resumo(ext, rel),
            "respostas": [{"id": r.id, "veredito": r.veredito, "alertas": r.alertas, "arquivo": r.arquivo,
                           "arquivo_canonico": r.arquivo_canonico, "pagina": r.pagina,
                           "pagina_citada": r.pagina_citada} for r in ext.respostas],
            "q13_estruturada": regras.q13_estruturada(next((r.resposta for r in ext.respostas
                                                             if r.id == "Q13"), "")),
            "brl": round(u.brl, 3) if preco else None, "melhor_de_n": registro_n}


@router.post("/reforco")
def reforco(corpo: dict = Body(...)):
    """
    W23, depois dos lotes — o Best-of-N (v3.1; N=3, só as que falham). Funde o que já foi gravado (os lotes e os
    reforços anteriores), roda o verificador e devolve os lotes SÓ das perguntas que ainda falham, ou `fim`.
    Corpo: o mesmo do /prompt + `execucao_id`.

    A rodada sai do banco (a maior gravada + 1): o n8n não guarda estado. `fim` quando N (configuracao.melhor_de_n)
    é 1, quando as N-1 rodadas já foram, quando não sobra falha, e para o gravado e o agente (não há modelo a quem
    perguntar de novo). Nunca chama modelo: quem chama é o W23, com a credencial dele.
    """
    if not corpo.get("execucao_id"):
        raise HTTPException(422, "informe execucao_id")
    execucao_id = int(corpo["execucao_id"])
    with banco.conectar() as conn:
        conn.row_factory = dict_row
        e = conn.execute("SELECT * FROM execucoes_modelo WHERE id = %s", (execucao_id,)).fetchone()
        if not e:
            raise HTTPException(404, "execução %s não existe" % execucao_id)
        n = _n_configurado(conn)
        rodada = conn.execute("SELECT COALESCE(max(rodada), 0) AS r FROM chamadas_modelo WHERE execucao_id = %s",
                              (execucao_id,)).fetchone()["r"] + 1
        fim = {"fim": True, "rodada": rodada, "ids": [], "modo": e["modo"], "lotes": []}
        if (n <= 1 or rodada > n - 1 or not e["leitura_id"] or e["origem"] in ("agente", "gravado", "legado")
                or (e["provedor"] or "") == "gravado"):
            return fim
        # A vaga do W23 (fn_tomar_vaga_extracao) reserva o pior caso de uma extração SEM reforço; o reforço gasta
        # depois dela. Com o gasto do dia já no teto (a mesma conta da vaga: gasto_diario, dia de São Paulo), não há
        # reforço — fica o original e a extração segue (ADR-024).
        orc = conn.execute("SELECT teto_brl_dia FROM orcamento WHERE vigente").fetchone()
        if orc and orc["teto_brl_dia"] is not None:
            gasto = conn.execute("SELECT COALESCE(sum(brl), 0) AS brl FROM gasto_diario"
                                 " WHERE dia = (now() AT TIME ZONE 'America/Sao_Paulo')::date").fetchone()["brl"]
            if gasto >= orc["teto_brl_dia"]:
                return dict(fim, motivo="sem reforço: o gasto do dia (R$ %.2f) já atingiu o teto (R$ %.2f)"
                            % (gasto, orc["teto_brl_dia"]))
        por_lote, reforcos, tentadas = _chamadas(conn, execucao_id, e["modelo"] or "")
        cobertos = set().union(*por_lote) if por_lote else set()
        if any(i not in cobertos for i in extracao.IDS):
            return fim      # o W23 só chega aqui com todos os lotes; sem eles não há o que avaliar
        lic = conn.execute("SELECT * FROM licitacoes WHERE controle = %s", (e["controle"],)).fetchone()
        paginas = reconstrucao.paginas_da_leitura(conn, e["leitura_id"])
    ext = _extracao(e, lic, por_lote, paginas)
    _aplicar_reforcos(ext, reforcos, tentadas, n)
    pendentes = melhor_de_n.falhas(ext, corpo.get("modalidade") or lic["modalidade"])
    if not pendentes:
        return fim
    d = extracao.montar_prompt(
        paginas, corpo.get("rotulo") or reconstrucao._nome(lic), lote=int(corpo.get("lote") or e["lote"] or 6),
        k_rag=int(corpo.get("k_rag") or e["k_rag"] or 6),
        modo=e["modo"] if e["modo"] in ("rag", "contexto-completo") else None,
        modelo=corpo.get("modelo") or e["modelo"] or modelos.MODELO_EXTRATOR,
        effort=corpo.get("effort") or e["effort"] or "high",
        max_tokens=int(corpo.get("max_tokens") or 16000), ids_pendentes=pendentes)
    return {"fim": False, "rodada": rodada, "ids": pendentes, "modo": d["modo"], "lotes": d["lotes"]}


@router.post("/verificar")
def verificar(corpo: dict = Body(...)):
    """W24 passo 2: funde, verifica e fecha a execução. A vigência é do W24."""
    if not corpo.get("execucao_id"):
        raise HTTPException(422, "informe execucao_id")
    with banco.conectar() as conn:
        return verificar_execucao(conn, int(corpo["execucao_id"]), corpo.get("modalidade"),
                                  bool(corpo.get("usar_itens_api", True)))


@router.post("/importar-respostas")
def importar_respostas(corpo: dict = Body(...)):
    """
    O caminho oficial de custo zero (ADR-014): as 17 respostas que um agente
    produziu sobre a leitura congelada entram como execução `agente` e passam
    pelo MESMO verificador que a API.
    """
    from . import versao
    erros = extracao.validar_respostas(corpo.get("respostas"))
    if erros:
        raise HTTPException(422, "respostas inválidas: " + "; ".join(erros))
    if not corpo.get("controle") or not corpo.get("leitura_id"):
        raise HTTPException(422, "informe controle e leitura_id")
    proc = corpo.get("procedencia") or {}
    with banco.conectar() as conn:
        conn.row_factory = dict_row
        le = conn.execute("SELECT controle FROM leituras WHERE id = %s", (corpo["leitura_id"],)).fetchone()
        if not le or le["controle"] != corpo["controle"]:
            raise HTTPException(422, "a leitura %s não é do controle %s" % (corpo["leitura_id"], corpo["controle"]))
        eid = conn.execute(
            "INSERT INTO execucoes_modelo (controle, leitura_id, origem, provedor, modelo, modo, effort, lote,"
            " status, canonica, versao_prompt, fonte_migracao) VALUES (%s, %s, 'agente', %s, %s, 'agente',"
            " 'agente', 17, 'em_curso', true, %s, %s) RETURNING id",
            (corpo["controle"], corpo["leitura_id"], proc.get("provedor") or "claude-code",
             proc.get("modelo") or "claude-opus-5-5", versao.versao_prompt(),
             Jsonb({"sessao": proc.get("sessao"), "via": "/importar-respostas"}))).fetchone()["id"]
        conn.execute(
            "INSERT INTO chamadas_modelo (execucao_id, lote_ids, dados, stop_reason, tentativas, preco_conhecido)"
            " VALUES (%s, %s, %s, 'end_turn', 1, false)",
            (eid, extracao.IDS, Jsonb({"respostas": corpo["respostas"]})))
        conn.commit()
        if corpo.get("verificar", True) is False:
            # O site ("Importar respostas do agente", W11) leva a licitação a `respondida` e deixa o W24 verificar
            # e publicar, como depois do W23 — verificar aqui também faria duas verificações da mesma execução.
            return {"execucao_id": eid, "controle": corpo["controle"], "verificacao_id": None, "verificado": False}
        return verificar_execucao(conn, eid, corpo.get("modalidade"), bool(corpo.get("usar_itens_api", True)))


__all__ = ["router", "verificar_execucao"]
