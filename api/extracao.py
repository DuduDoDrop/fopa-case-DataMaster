# -*- coding: utf-8 -*-
"""
A extração em três tempos, como o n8n a executa (plano, seção 5, W23/W24):

  1. /prompt monta, para cada lote, o corpo EXATO que o `ProvedorClaude` da v2
     manda pelo SDK (modelos.py:206-233), sem `stream`. O n8n faz a chamada com
     um HTTP Request cru e grava cada resposta em `chamadas_modelo`.
  2. /verificar funde as chamadas gravadas com o próprio `extrator.extrair` da
     v2, por meio de um `ProvedorGravado` que devolve o que foi gravado em vez
     de chamar o modelo, e passa o resultado ao verificador.
  3. O custo de cada chamada já foi contado quando ela foi feita (/custo); aqui
     só se fecha a execução.

Nada deste arquivo chama modelo. `ProvedorSimulado` é regex sobre o contexto;
`ProvedorGravado` é leitura do banco.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile

from fopa import extrator
from fopa import recuperacao as rec
from fopa.modelos import ErroModelo, Provedor, ProvedorSimulado, Uso, conteudo_claude, texto_usuario
from fopa.questionario import ESQUEMA_LOTE, NAO_LOCALIZADO, PERGUNTAS, instrucao_sistema

from migracao import regras

IDS = [p.id for p in PERGUNTAS]
RE_ID = re.compile(r"^(Q\d+)\. ", re.M)


# ------------------------------------------------------------------ corpos
def corpo_claude(sistema: str, usuario, esquema: dict, modelo: str, max_tokens: int,
                 effort: str) -> dict:
    """O mesmo dicionário de `ProvedorClaude.responder_json`, menos o `stream`. `usuario` em duas partes (v3.1)
    vira dois blocos, com o de documentos em cache (`modelos.conteudo_claude`)."""
    corpo = {"model": modelo, "max_tokens": max_tokens,
             "system": [{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}],
             "messages": [{"role": "user", "content": conteudo_claude(usuario)}]}
    # Haiku 4.5 é de geração anterior: não aceita thinking adaptativo nem effort (modelos.py:209-219).
    if not modelo.startswith("claude-haiku-4-5"):
        corpo["thinking"] = {"type": "adaptive"}
        corpo["output_config"] = {"effort": effort, "format": {"type": "json_schema", "schema": esquema}}
    else:
        corpo["output_config"] = {"format": {"type": "json_schema", "schema": esquema}}
    return corpo


def corpo_openai(sistema: str, usuario, esquema: dict, modelo: str, max_tokens: int,
                 effort: str) -> dict:
    """O mesmo de `ProvedorOpenAI.responder_json` (Responses API, ADR-012). O cache da OpenAI é automático por
    prefixo: basta o texto começar pelos documentos."""
    return {"model": modelo, "instructions": sistema, "input": texto_usuario(usuario),
            "max_output_tokens": max_tokens,
            "reasoning": {"effort": effort},
            "text": {"format": {"type": "json_schema", "name": "respostas_fopa",
                                "schema": esquema, "strict": True}}}


def paginas_do_lote(paginas: list, grupo: list[str], modo: str, indice, k_rag: int) -> list:
    """A MESMA seleção de páginas do `extrator.extrair` — é a função dele (v3.1: uma só, para não divergir)."""
    return extrator._paginas_do_lote(paginas, grupo, modo, indice, k_rag)


def montar_prompt(paginas: list, licitacao: str, *, lote: int = 6, k_rag: int = 6,
                  modo: str | None = None, modelo: str = "claude-opus-5", effort: str = "high",
                  max_tokens: int = 16000, ids_pendentes: list | None = None,
                  ordem: str = extrator.ORDEM_PADRAO) -> dict:
    if not paginas:
        raise ValueError("leitura sem páginas")
    modo_efetivo = rec.escolher_modo(paginas, forcado=modo)
    indice = rec.IndiceBM25(paginas) if modo_efetivo == "rag" else None
    ids = [i for i in IDS if not ids_pendentes or i in set(ids_pendentes)]
    sistema = instrucao_sistema()
    lotes = []
    for i in range(0, len(ids), lote):
        grupo = ids[i:i + lote]
        contexto = rec.montar_contexto(paginas_do_lote(paginas, grupo, modo_efetivo, indice, k_rag))
        usuario = extrator.usuario_do_lote(contexto, grupo, licitacao, ordem, cache=modo_efetivo != "rag")
        body = corpo_claude(sistema, usuario, ESQUEMA_LOTE, modelo, max_tokens, effort)
        lotes.append({"ids": grupo, "body": body,
                      "body_openai": corpo_openai(sistema, usuario, ESQUEMA_LOTE, modelo, max_tokens, effort),
                      "request_sha256": hashlib.sha256(regras.json_canonico(body)).hexdigest()})
    return {"modo": modo_efetivo, "lotes": lotes}


# ------------------------------------------------------------------ envelopes
def _texto(usuario) -> str:
    """O texto da mensagem do usuário: string, `(prefixo, sufixo)` ou o `content` em blocos da Claude API."""
    if isinstance(usuario, str):
        return usuario
    if isinstance(usuario, (list, tuple)):
        return "\n\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in usuario)
    return ""


def ids_do_usuario(usuario) -> list[str]:
    """
    Os ids do lote, lidos do bloco de perguntas — FORA do bloco de documentos, nas duas ordens: depois do fim dos
    documentos (ordem nova, v3.1) ou antes deles (a de sempre, que o banco guarda nas chamadas antigas). Uma linha
    "Q3. ..." dentro de um edital não é pergunta do lote.
    """
    texto = _texto(usuario)
    if extrator.FIM_DOCUMENTOS in texto:
        ids = RE_ID.findall(texto.split(extrator.FIM_DOCUMENTOS, 1)[1])
        if ids:
            return ids
    return RE_ID.findall(texto.split("=== DOCUMENTOS ===")[0])


def partes_do_corpo(body: dict) -> tuple[str, str]:
    """(sistema, usuário) de um corpo da Anthropic ou da OpenAI."""
    if "messages" in body:
        sistema = body.get("system")
        if isinstance(sistema, list):
            sistema = "".join(b.get("text", "") for b in sistema)
        return sistema or "", _texto(body["messages"][0]["content"])
    return body.get("instructions") or "", body.get("input") or ""


def envelope_anthropic(dados: dict, modelo: str) -> dict:
    """O formato de resposta da Messages API — o Code node de parse do W23 não muda."""
    return {"id": "msg_fopa_%s" % modelo, "type": "message", "role": "assistant", "model": modelo,
            "content": [{"type": "text", "text": json.dumps(dados, ensure_ascii=False)}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0}}


def responder_simulado(body: dict) -> dict:
    sistema, usuario = partes_do_corpo(body)
    dados, _ = ProvedorSimulado().responder_json(sistema, usuario, ESQUEMA_LOTE, "simulado")
    ids = ids_do_usuario(usuario)
    dados = {"respostas": [r for r in dados["respostas"] if not ids or r["id"] in ids]}
    return envelope_anthropic(dados, "simulado")


def dados_do_envelope(env) -> dict:
    """O JSON de respostas dentro de um envelope da Anthropic ou da OpenAI."""
    if isinstance(env, str):
        env = json.loads(env)
    if "respostas" in env:
        return env
    if "content" in env:           # Anthropic: só blocos text, nunca content[0] (pode ser thinking)
        texto = "".join(b.get("text", "") for b in env["content"] if b.get("type") == "text")
    elif "output_text" in env:
        texto = env["output_text"]
    else:                          # OpenAI Responses: output[].content[] do tipo output_text
        texto = "".join(c.get("text", "") for o in env.get("output") or []
                        for c in o.get("content") or [] if c.get("type") == "output_text")
    return json.loads(texto)


# ------------------------------------------------------------------ provedor gravado
class ProvedorGravado(Provedor):
    """
    Devolve o que foi gravado em `chamadas_modelo`, lote a lote, casado pelos ids.

    O `nome` importa: `extrator.extrair` grava `c.provedor = provedor.nome` e marca
    secundário todo provedor fora de ('claude', 'simulado', '') (extrator.py:339-346)
    — um nome genérico faria toda execução sair "degradada".
    """

    def __init__(self, nome: str, chamadas: list[tuple[list, dict, Uso]]):
        self.nome = nome
        self.chamadas = chamadas

    def responder_json(self, sistema, usuario, esquema, modelo, max_tokens=16000, effort="high"):
        ids = set(ids_do_usuario(usuario))
        for lote_ids, dados, uso in self.chamadas:
            if set(lote_ids) == ids:
                return dados, uso
        raise ErroModelo("nenhuma chamada gravada para o lote %s" % sorted(ids))


def extrair_gravado(paginas: list, licitacao: str, provedor: ProvedorGravado, *, modelo: str,
                    modo: str | None, lote: int, k_rag: int, effort: str) -> extrator.Extracao:
    """Roda o `extrator.extrair` da v2 com o provedor gravado e as páginas congeladas."""
    with tempfile.TemporaryDirectory() as d:
        # extrair usa o nome da pasta como nome da licitação; "/" não cabe em nome de pasta
        pasta = os.path.join(d, re.sub(r'[<>:"/\\|?*]', "-", licitacao) or "licitacao")
        os.makedirs(pasta)
        return extrator.extrair(pasta, provedor, modelo=modelo, modo=modo, lote=lote, k_rag=k_rag,
                                effort=effort, paginas_prontas=paginas)


# ------------------------------------------------------------------ validação do agente
def validar_respostas(respostas) -> list[str]:
    """O que o esquema exige e o agente pode ter esquecido (70_extracao_por_agente.py:412-429)."""
    if not isinstance(respostas, list):
        return ["respostas precisa ser uma lista"]
    erros = []
    ids = [r.get("id") for r in respostas if isinstance(r, dict)]
    faltam = [i for i in IDS if i not in ids]
    if faltam:
        erros.append("faltam: %s" % ", ".join(faltam))
    for r in respostas:
        if not isinstance(r, dict):
            erros.append("item que não é objeto")
            continue
        if r.get("pagina") is not None and not isinstance(r.get("pagina"), int):
            erros.append("%s: pagina precisa ser inteiro" % r.get("id"))
        if r.get("confianca") not in ("alta", "media", "baixa"):
            erros.append("%s: confianca fora de alta/media/baixa" % r.get("id"))
    return erros


__all__ = ["montar_prompt", "corpo_claude", "corpo_openai", "responder_simulado", "dados_do_envelope",
           "envelope_anthropic", "ids_do_usuario", "partes_do_corpo", "ProvedorGravado",
           "extrair_gravado", "validar_respostas", "IDS", "NAO_LOCALIZADO"]
