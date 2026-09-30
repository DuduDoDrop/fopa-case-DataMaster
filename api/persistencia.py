# -*- coding: utf-8 -*-
"""
Gravar o que o verificador decidiu: `verificacoes` + `verificacao_respostas`.

Usado por `/reverificar` e `/verificar`. A verificação nasce NÃO vigente:
trocar a vigente é decisão do fluxo (W24/W30), nunca efeito colateral de
reverificar (ADR-014: "a mudança de números é decisão").

O `auditoria_json` é o mesmo dicionário que o v2 gravava em `auditoria.json`,
produzido pelo próprio `fopa.saida.escrever_json` — não uma cópia do formato.
"""
from __future__ import annotations

import json
import os
import tempfile

from psycopg.types.json import Jsonb

from fopa import saida

from migracao import regras


class VerificacaoRepetida(RuntimeError):
    """Já existe verificação desta execução nesta versão das regras."""


def auditoria_json(ext, rel) -> dict:
    with tempfile.TemporaryDirectory() as d:
        caminho = saida.escrever_json(ext, rel, os.path.join(d, "auditoria.json"))
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)


def resumo(ext, rel) -> dict:
    c = ext.condicoes
    return {"aprovadas": rel.aprovadas, "revisar": rel.revisar, "reprovadas": rel.reprovadas,
            "nao_localizado": rel.nao_localizado, "ancoradas": rel.ancoradas,
            "respondidas": rel.respondidas, "taxa_ancorada": round(rel.taxa_ancorada, 4),
            "alertas_globais": list(rel.alertas_globais or []), "tags": c.tags(),
            "degradada": c.degradada}


def gravar_verificacao(conn, *, execucao_id: int, controle: str, leitura_id: int | None, ext, rel,
                       versao_regras: str, itens_api_usados: bool) -> int:
    aud = auditoria_json(ext, rel)
    q13 = next((r.resposta for r in ext.respostas if r.id == "Q13"), "")
    res = resumo(ext, rel)
    linha = conn.execute(
        "INSERT INTO verificacoes (execucao_id, controle, leitura_id, versao_regras, aprovadas, revisar,"
        " reprovadas, nao_localizado, ancoradas, respondidas, taxa_ancorada, alertas_globais, tags,"
        " degradada, condicoes, q13_estruturada, itens_api_usados, auditoria_json, vigente)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false)"
        " ON CONFLICT (execucao_id, versao_regras) DO NOTHING RETURNING id",
        (execucao_id, controle, leitura_id, versao_regras, res["aprovadas"], res["revisar"],
         res["reprovadas"], res["nao_localizado"], res["ancoradas"], res["respondidas"],
         res["taxa_ancorada"], res["alertas_globais"], res["tags"], res["degradada"],
         Jsonb(ext.condicoes.para_dict()), Jsonb(regras.q13_estruturada(q13)), itens_api_usados,
         Jsonb(aud))).fetchone()
    if not linha:
        raise VerificacaoRepetida("a execução %s já tem verificação na versão %s" % (execucao_id, versao_regras))
    vid = linha["id"] if isinstance(linha, dict) else linha[0]
    ids = {r[0] if not isinstance(r, dict) else r["nome"]: (r[1] if not isinstance(r, dict) else r["id"])
           for r in conn.execute("SELECT nome, id FROM arquivos WHERE controle = %s", (controle,)).fetchall()}
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO verificacao_respostas (verificacao_id, pergunta_id, veredito, arquivo_canonico,"
            " arquivo_id, pagina_final, pagina_citada, alertas, ausencia)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [(vid, r.id, r.veredito, r.arquivo_canonico, ids.get(r.arquivo_canonico), r.pagina,
              r.pagina_citada if r.pagina_citada is not None else r.pagina, list(r.alertas or []),
              regras.ausencia(r.para_dict())) for r in ext.respostas])
    return vid


__all__ = ["gravar_verificacao", "auditoria_json", "resumo", "VerificacaoRepetida"]
