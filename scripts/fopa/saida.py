# -*- coding: utf-8 -*-
"""
Saídas do pipeline: planilha, nota do vault e JSON de auditoria.

A planilha segue o modelo que a área já usa (cabeçalho vermelho, texto branco),
com três abas: Respostas, Pirâmide e Auditoria. O trecho literal NÃO vai para a
aba de respostas — ele vive na auditoria, que é onde se confere.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict

from .extrator import Extracao
from .questionario import NAO_LOCALIZADO
from .verificador import nao_encontrou
from .verificador import APROVADO, REVISAR, REPROVADO, Relatorio

VERMELHO = "B23A32"
TINTA = "11243D"


# ---------------------------------------------------------------- planilha
def escrever_xlsx(ext: Extracao, rel: Relatorio, destino: str) -> str:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError as e:
        raise RuntimeError("openpyxl não instalado: pip install openpyxl") from e

    wb = Workbook()
    fill = PatternFill("solid", fgColor=VERMELHO)
    cab = Font(color="FFFFFF", bold=True, size=11)
    borda = Border(*[Side(style="thin", color="DDDDDD")] * 4)
    topo = Alignment(vertical="top", wrap_text=True)

    def cabecalho(ws, colunas, larguras):
        ws.append(colunas)
        for i, l in enumerate(larguras, start=1):
            ws.column_dimensions[get_column_letter(i)].width = l
        for c in ws[1]:
            c.fill, c.font, c.alignment = fill, cab, Alignment(vertical="center")
        ws.freeze_panes = "A2"

    # --- aba Respostas
    ws = wb.active
    ws.title = "Respostas"
    cabecalho(ws, ["Pergunta", "Resposta", "Info"], [52, 88, 34])
    for r in ext.respostas:
        marca = "⚠ " if r.veredito == REVISAR else ("✖ " if r.veredito == REPROVADO else "")
        ws.append(["%s. %s" % (r.id, r.pergunta), marca + r.resposta, r.info])
    for linha in ws.iter_rows(min_row=2):
        for c in linha:
            c.alignment, c.border = topo, borda

    # --- aba Pirâmide
    wp = wb.create_sheet("Pirâmide")
    cabecalho(wp, ["Vínculo / tabela", "Faixa", "Qtd", "Arquivo", "Página"], [34, 44, 12, 42, 10])
    q13 = ext.por_id("Q13")
    if q13 and not nao_encontrou(q13.resposta):
        for bloco in re.split(r";\s*(?=[A-ZÀ-Ú])|\n", q13.resposta):
            bloco = bloco.strip()
            if not bloco:
                continue
            m = re.search(r"(.*?)(de\s*R\$.*?|acima\s*de\s*R\$.*?)[:\-]?\s*(\d{1,5})\s*$",
                          bloco, re.I)
            if m:
                wp.append([m.group(1).strip(" -—:"), m.group(2).strip(),
                           int(m.group(3)), q13.arquivo or "", q13.pagina or ""])
            else:
                wp.append([bloco, "", "", q13.arquivo or "", q13.pagina or ""])
    else:
        wp.append(["Não localizado", "", "", "", ""])
    for linha in wp.iter_rows(min_row=2):
        for c in linha:
            c.alignment, c.border = topo, borda

    # --- aba Auditoria
    wa = wb.create_sheet("Auditoria")
    cabecalho(wa, ["ID", "Veredito", "Confiança", "Arquivo", "Pág.",
                   "Trecho literal", "Alertas"], [8, 13, 12, 42, 8, 82, 62])
    for r in ext.respostas:
        wa.append([r.id, r.veredito, r.confianca, r.arquivo or "", r.pagina or "",
                   r.trecho_literal or "", " | ".join(r.alertas)])
    wa.append([])
    wa.append(["", "RESUMO", str(rel)])
    for g in (rel.alertas_globais or []):
        wa.append(["", "GLOBAL", g])
    for linha in wa.iter_rows(min_row=2):
        for c in linha:
            c.alignment, c.border = topo, borda

    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    wb.save(destino)
    return destino


# ---------------------------------------------------------------- nota do vault
def escrever_nota(ext: Extracao, rel: Relatorio, destino: str, link_pncp: str = "") -> str:
    linhas = [r"---", "tipo: edital", "status: %s" % (
        "verificado" if rel.reprovadas == 0 else "a-verificar"),
        "licitacao: %s" % ext.licitacao,
        "modo_extracao: %s" % ext.modo,
        "modelo: %s" % (ext.uso.modelo or "-"),
        "custo_brl: %.3f" % ext.uso.brl,
        "atualizado: 2026-09-22",
        "tags:", "  - edital", "  - extraido", r"---", "",
        "# %s" % ext.licitacao, ""]

    if link_pncp:
        linhas += ["> [!info] Origem", "> PNCP: %s" % link_pncp,
                   "> Arquivos lidos: %d" % len(ext.arquivos), ""]

    linhas += ["> [!%s] Verificação" % ("success" if rel.reprovadas == 0 else "warning"),
               "> %s" % rel, ">",
               "> Modo: `%s` · modelo `%s` · %d chamada(s) · **R$ %.3f**"
               % (ext.modo, ext.uso.modelo, ext.uso.chamadas, ext.uso.brl), ""]

    if rel.alertas_globais:
        linhas += ["> [!danger] Alertas globais"]
        linhas += ["> - %s" % g for g in rel.alertas_globais]
        linhas += [""]

    linhas += ["## Questionário", "",
               "| Pergunta | Resposta | Info |", "|---|---|---|"]
    for r in ext.respostas:
        marca = "⚠ " if r.veredito == REVISAR else ("✖ " if r.veredito == REPROVADO else "")
        resp = r.resposta.replace("|", "\\|").replace("\n", " ")
        linhas.append("| %s. %s | %s%s | `%s` |" % (
            r.id, r.pergunta, marca, resp, r.info))

    linhas += ["", "## Auditoria", ""]
    for r in ext.respostas:
        if nao_encontrou(r.resposta):
            continue
        linhas += ["### %s — %s" % (r.id, r.veredito), ""]
        if r.trecho_literal:
            linhas += ["> %s" % r.trecho_literal.replace("\n", " ")[:500], ""]
        linhas += ["`%s`" % r.info, ""]
        for a in r.alertas:
            linhas += ["> [!warning] %s" % a, ""]

    linhas += ["## Relacionadas", "",
               "[[MOC Editais]] · [[Questionário de extração]] · [[Regras de negócio]] · "
               "[[4 Verificador]]", ""]

    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))
    return destino


# ---------------------------------------------------------------- json
def escrever_json(ext: Extracao, rel: Relatorio, destino: str) -> str:
    dados = {
        "licitacao": ext.licitacao,
        "modo": ext.modo,
        "arquivos": ext.arquivos,
        "paginas": len(ext.paginas),
        "uso": {"modelo": ext.uso.modelo, "provedor": ext.provedor,
                "effort": ext.effort, "chamadas": ext.uso.chamadas,
                "entrada": ext.uso.entrada, "saida": ext.uso.saida,
                "raciocinio": ext.uso.raciocinio,
                "cache_leitura": ext.uso.cache_leitura,
                "segundos": round(ext.uso.segundos, 2),
                # `null` e nao `0.0` quando falta a tabela de preco: zero seria
                # lido como "foi de graca" por qualquer script que consuma este
                # arquivo, e a chamada foi cobrada.
                "usd": round(ext.uso.usd, 4) if ext.uso.preco_conhecido else None,
                "brl": round(ext.uso.brl, 3) if ext.uso.preco_conhecido else None},
        "condicoes": ext.condicoes.para_dict(),
        "verificacao": {"aprovadas": rel.aprovadas, "revisar": rel.revisar,
                        "reprovadas": rel.reprovadas,
                        "nao_localizado": rel.nao_localizado,
                        "taxa_ancorada": round(rel.taxa_ancorada, 4),
                        "alertas_globais": rel.alertas_globais},
        "respostas": [r.para_dict() for r in ext.respostas],
    }
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    return destino


__all__ = ["escrever_xlsx", "escrever_nota", "escrever_json"]
