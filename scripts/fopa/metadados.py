# -*- coding: utf-8 -*-
"""
Realimenta o `_metadados.md` da licitação com o que o pipeline observou.

Por que isto existe: o inventário diz *quais arquivos existem*. O que o analista
precisa saber ao reabrir a pasta seis meses depois é **o que foi encontrado neles** —
os conflitos, as respostas críticas, as pendências. Essa informação nascia na
execução e morria no `auditoria.json`.

A seção de observações é delimitada por marcadores. Tudo que estiver fora deles é
preservado: comentários escritos à mão pelo analista convivem com os gerados.
"""
from __future__ import annotations

import os
import re
from datetime import date

from .extrator import Extracao
from .questionario import NAO_LOCALIZADO, POR_ID
from .verificador import Relatorio, APROVADO, REVISAR, REPROVADO, nao_encontrou

INICIO = "<!-- fopa:observacoes:inicio -->"
FIM = "<!-- fopa:observacoes:fim -->"

# perguntas cujo erro move o lance — destacadas nas observações
CRITICAS = tuple(p.id for p in POR_ID.values() if p.critico)


def _bloco(ext: Extracao, rel: Relatorio, quando: str) -> str:
    # A TAG vem ANTES de tudo, e como tag do Obsidian (#) e como aviso.
    #
    # Como `#tag`, ela entra na busca e no graph do vault: da para achar todas
    # as licitacoes suspeitas sem abrir uma por uma. Como callout `danger`, ela
    # aparece para quem abrir a nota sem estar procurando por ela.
    #
    # As duas formas porque servem a leitores diferentes: quem filtra e quem le.
    cond = getattr(ext, "condicoes", None)
    tags = cond.tags() if cond is not None else []
    cabeca = []
    if tags:
        cabeca = ["> [!danger] %s" % " · ".join(tags),
                  "> Este edital contém texto **furtivo** — visível para a máquina",
                  "> e não para quem abre o PDF. Não é degradação de leitura: é",
                  "> tentativa de manipulação, e pede decisão humana antes do lance.",
                  ">"]
        for m in (cond.furtivos or [])[:4]:
            cabeca.append("> - `%s`" % m)
        cabeca += ["", "#prompt-injection #conteudo-suspeito", ""]

    L = [INICIO, "",
         "## Observações do pipeline",
         ""] + cabeca + [
         "> [!info] Gerado automaticamente em %s" % quando,
         "> Modo `%s` · modelo `%s` · %d chamada(s) · **R$ %.3f** · %d páginas de %d arquivo(s)"
         % (ext.modo, ext.uso.modelo or "-", ext.uso.chamadas, ext.uso.brl,
            len(ext.paginas), len(ext.arquivos)),
         ">",
         "> **Verificação:** %s" % rel,
         ""]

    # --- conflitos: o que mais importa saber ao reabrir a pasta
    conflitos = [r for r in ext.respostas if r.conflito]
    if conflitos:
        L += ["### ⚠ Conflitos entre documentos", ""]
        for r in conflitos:
            L += ["**%s — %s**" % (r.id, r.pergunta), "",
                  "> %s" % r.conflito.replace("\n", " "), "",
                  "Resposta adotada: %s" % r.resposta.replace("\n", " ")[:320],
                  "Origem: `%s`" % r.info, ""]

    # --- reprovadas: nunca podem passar despercebidas
    reprovadas = [r for r in ext.respostas if r.veredito == REPROVADO]
    if reprovadas:
        L += ["### ✖ Respostas reprovadas na verificação", ""]
        for r in reprovadas:
            L += ["- **%s** — %s" % (r.id, "; ".join(r.alertas) or "sem detalhe")]
        L += [""]

    # --- alertas globais (pirâmide, unidade, cruzamento com API)
    if rel.alertas_globais:
        L += ["### Alertas globais", ""]
        L += ["- %s" % g for g in rel.alertas_globais]
        L += [""]

    # --- as respostas que movem o lance
    L += ["### Respostas críticas", "", "| # | Resposta | Origem | Veredito |", "|---|---|---|---|"]
    for r in ext.respostas:
        if r.id not in CRITICAS:
            continue
        marca = {APROVADO: "✅", REVISAR: "⚠", REPROVADO: "✖"}[r.veredito]
        resp = r.resposta.replace("|", "\\|").replace("\n", " ")
        L.append("| **%s** | %s | `%s` | %s |"
                 % (r.id, resp[:190] + ("…" if len(resp) > 190 else ""), r.info, marca))
    L += [""]

    # --- não localizados: pendência de campo, não falha
    nao = [r for r in ext.respostas if nao_encontrou(r.resposta)]
    if nao:
        L += ["### Não localizados nos documentos disponíveis", "",
              "Não são falhas de extração: são informações que o edital não traz. "
              "Cada uma é candidata a pedido de esclarecimento ao órgão.", ""]
        for r in nao:
            L += ["- **%s** — %s" % (r.id, r.pergunta)]
        L += [""]

    L += ["> [!todo] Pendências desta licitação",
          "> - [ ] Revisar as respostas marcadas ⚠",
          "> - [ ] Conferir a pirâmide salarial contra o anexo original"]
    if nao:
        L += ["> - [ ] Avaliar pedido de esclarecimento para os campos não localizados"]
    L += ["", FIM]
    return "\n".join(L)


def atualizar(pasta: str, ext: Extracao, rel: Relatorio,
              quando: str | None = None) -> str:
    """
    Escreve (ou substitui) a seção de observações no `_metadados.md` da pasta.

    Preserva tudo que estiver fora dos marcadores — inclusive comentários que o
    analista tenha escrito à mão.
    """
    quando = quando or date.today().strftime("%d/%m/%Y")
    caminho = os.path.join(pasta, "_metadados.md")
    bloco = _bloco(ext, rel, quando)

    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            texto = f.read()
    else:
        texto = ("---\ntipo: edital\nstatus: extraido\n---\n\n# %s\n\n"
                 % ext.licitacao)

    if INICIO in texto and FIM in texto:
        i, j = texto.index(INICIO), texto.index(FIM) + len(FIM)
        texto = texto[:i] + bloco + texto[j:]
    else:
        texto = texto.rstrip() + "\n\n---\n\n" + bloco + "\n"

    # mantém o frontmatter em dia com o resultado da execução
    def _campo(nome, valor):
        nonlocal texto
        padrao = re.compile(r"^%s:.*$" % re.escape(nome), re.M)
        linha = "%s: %s" % (nome, valor)
        if padrao.search(texto):
            texto = padrao.sub(linha, texto, count=1)
        elif texto.startswith("---"):
            fim_fm = texto.index("---", 3)
            texto = texto[:fim_fm] + linha + "\n" + texto[fim_fm:]

    _campo("extraido_em", date.today().isoformat())
    _campo("modo_extracao", ext.modo)
    _campo("ancoragem", "%d/%d" % (rel.ancoradas, rel.respondidas))
    _campo("conflitos", sum(1 for r in ext.respostas if r.conflito))
    _campo("custo_brl", "%.3f" % ext.uso.brl)

    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return caminho


__all__ = ["atualizar", "INICIO", "FIM"]
