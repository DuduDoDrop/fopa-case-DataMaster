# -*- coding: utf-8 -*-
"""
O RELATORIO.html de uma verificação, gerado pelo `fopa.pagina.escrever` da v2
e gravado no storage (plano, seção 6, `/render`).

O que muda em relação ao v2 é só o endereço dos PDFs: em vez do nome cru ao
lado do HTML (que quebrava com `%` em 26-29 anexos), cada link aponta para
`/api/pdf/{slug}/{arquivo_id}#page=N`, servido atrás do login. O HTML em si é
o mesmo que foi aprovado — é o `pagina.py`, não uma cópia.
"""
from __future__ import annotations

import os
import tempfile

from fopa import pagina

from . import reconstrucao
from .storage import chave_html


def renderizar(conn, storage, verificacao_id: int) -> dict:
    ext, rel, ctx = reconstrucao.extracao_verificada(conn, verificacao_id)
    slug = ctx["slug"]
    url_por_arquivo = {r["nome"]: "/api/pdf/%s/%d" % (slug, r["id"]) for r in conn.execute(
        "SELECT id, nome FROM arquivos WHERE controle = %s", (ctx["controle"],)).fetchall()}
    with tempfile.TemporaryDirectory() as d:
        destino = os.path.join(d, "RELATORIO.html")
        pagina.escrever(ext, rel, destino, link_pncp=ctx["link"] or "",
                        url_por_arquivo=url_por_arquivo, link_voltar="/")
        with open(destino, "rb") as f:
            dados = f.read()
    chave = chave_html(slug, verificacao_id)
    sha = storage.put(chave, dados)
    return {"html_uri": chave, "bytes": len(dados), "sha256": sha}


__all__ = ["renderizar"]
