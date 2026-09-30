# -*- coding: utf-8 -*-
"""
Fábrica de snapshots sintéticos no formato de `congelar.py`.

Cada pasta fake escreve, no snapshot, o que o congelamento copia
(`amostras/<p>/_inventario.json`, `saidas/<p>/auditoria.json`,
`saidas/_agente/<p>/*.json`), e no "disco vivo" os PDFs, com o sha no
manifesto. Os PDFs são bytes quaisquer: o importador nunca os abre, só confere
o sha e copia.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field

PERGUNTAS = ["Q%d" % i for i in range(1, 18)]


def _grava(caminho: str, obj) -> None:
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def respostas(arquivo: str, pagina: int = 1, **sobrescreve) -> list[dict]:
    """17 respostas cruas; Q6 e Q16 "não localizado" como no acervo real."""
    rs = []
    for pid in PERGUNTAS:
        if pid in ("Q6", "Q16"):
            r = {"id": pid, "resposta": "Não localizado", "arquivo": None, "pagina": None,
                 "trecho_literal": None, "conflito": None, "confianca": "alta"}
        else:
            r = {"id": pid, "resposta": "resposta %s" % pid, "arquivo": arquivo, "pagina": pagina,
                 "trecho_literal": "trecho %s" % pid, "conflito": None, "confianca": "alta"}
        r.update(sobrescreve.get(pid, {}))
        rs.append(r)
    return rs


def auditoria(licitacao: str, rs: list[dict], provedor="claude-code", modelo="claude-opus-5-5",
              chamadas=1, brl=None, modo="agente", tags=(), furtivos=(), agente=True,
              vereditos: dict | None = None) -> dict:
    vereditos = vereditos or {}
    saida_rs = []
    for r in rs:
        d = dict(r, pergunta="pergunta %s" % r["id"], pagina_citada=None,
                 veredito=vereditos.get(r["id"], "APROVADO"), alertas=[], info="")
        saida_rs.append(d)
    nl = sum(1 for r in rs if (r["resposta"] or "").startswith("Não localizado"))
    rev = sum(1 for v in vereditos.values() if v == "REVISAR")
    aud = {
        "licitacao": licitacao, "modo": modo, "arquivos": sorted({r["arquivo"] for r in rs if r["arquivo"]}),
        "paginas": 3,
        "uso": {"modelo": modelo, "provedor": provedor, "effort": "agente" if agente else "",
                "chamadas": chamadas, "entrada": 0 if agente else 200000, "saida": 0 if agente else 5000,
                "raciocinio": 0, "cache_leitura": 0 if agente else 3000, "segundos": 0.0,
                "usd": None if brl is None else round(brl / 5.1, 4), "brl": brl},
        "condicoes": {"tags": list(tags), "degradada": bool(furtivos), "motivos": [],
                      "documentos": {"esperados": 1, "obtidos": 1, "faltando": []},
                      "ocr": {"arquivos": [], "paginas": 0},
                      "modelo": {"provedor": provedor, "modelo": modelo, "effort": "agente",
                                 "secundario": False},
                      "texto_furtivo": list(furtivos), "corpus_horas": 2.0, "abstencoes": ["Q6", "Q16"]},
        "verificacao": {"aprovadas": 17 - rev, "revisar": rev, "reprovadas": 0, "nao_localizado": nl,
                        "taxa_ancorada": 1.0, "alertas_globais": ["RN-15: 2 pergunta(s) sem resposta"]},
        "respostas": saida_rs,
    }
    if agente:
        aud["agente"] = {"provedor": provedor, "modelo": modelo, "reaproveitado_de": None,
                         "finalizado_em": "2026-09-23T23:37:13-0300"}
    return aud


@dataclass
class PastaFake:
    nome: str
    controle: str
    pdfs: dict = field(default_factory=dict)            # nome -> bytes (no disco)
    inventario_arquivos: list | None = None            # None = monta a partir de pdfs
    recusados: list = field(default_factory=list)
    extras_inventario: dict = field(default_factory=dict)
    dentro: bool = True
    fim_prazo: str = "2026-12-01T09:00"
    auditoria: dict | None = None
    leitura_paginas: list | None = None                # [(arquivo, numero, texto)]
    leitura_hashes: dict | None = None                 # None = sha dos pdfs lidos
    leitura_condicoes: dict | None = None              # None = sem OCR nem texto furtivo
    respostas_agente: list | None = None
    finalizado: dict | None = None
    itens_api: list | None = None
    gabarito: dict | None = None


def criar(raiz: str, pastas: list[PastaFake], corpus: list | None = None,
          livro: dict | None = None, harness: dict | None = None, lote: dict | None = None,
          execucoes: list | None = None) -> tuple[str, str]:
    """Escreve o snapshot e o disco vivo. Devolve (snapshot, amostras_vivo)."""
    snap = os.path.join(raiz, "acervo", "2026-09-24_0150")
    vivo = os.path.join(raiz, "amostras")
    pdfs_manifesto = []
    for p in pastas:
        for nome, conteudo in p.pdfs.items():
            destino = os.path.join(vivo, p.nome, nome)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with open(destino, "wb") as f:
                f.write(conteudo)
            pdfs_manifesto.append({"caminho": "amostras/%s/%s" % (p.nome, nome),
                                   "bytes": len(conteudo), "sha256": sha(conteudo),
                                   "mtime": "2026-09-23T10:00:00"})
        arqs = p.inventario_arquivos
        if arqs is None:
            arqs = [{"seq": i + 1, "tipo": "Edital", "titulo": n, "arquivo": n,
                     "bytes": len(c), "sha256": sha(c), "pag": 3, "chars": 900,
                     "requer_ocr": False, "origem": "https://pncp/%d" % (i + 1)}
                    for i, (n, c) in enumerate(p.pdfs.items())]
        inv = {"controle": p.controle, "orgao": "MUNICIPIO DE TESTE", "uf": "SP",
               "municipio": "Teste", "modalidade": "Pregão - Eletrônico",
               "objeto": "cessão onerosa da folha de pagamento", "situacao": "Divulgada no PNCP",
               "publicado_em": "2026-09-01", "fim_prazo": p.fim_prazo,
               "link": "https://pncp.gov.br/app/editais/x", "escopo": {"dentro": p.dentro,
                                                                        "motivo": "folha de pagamento"},
               "arquivos": arqs, "recusados": p.recusados}
        inv.update(p.extras_inventario)
        _grava(os.path.join(snap, "amostras", p.nome, "_inventario.json"), inv)
        if p.itens_api is not None:
            _grava(os.path.join(snap, "amostras", p.nome, "_itens_api.json"), p.itens_api)
        if p.gabarito is not None:
            _grava(os.path.join(snap, "amostras", p.nome, "_gabarito.json"), p.gabarito)
        if p.auditoria is not None:
            _grava(os.path.join(snap, "saidas", p.nome, "auditoria.json"), p.auditoria)
        ag = os.path.join(snap, "saidas", "_agente", p.nome)
        if p.leitura_paginas is not None:
            lidos = sorted({a for a, _, _ in p.leitura_paginas})
            hashes = p.leitura_hashes if p.leitura_hashes is not None else {
                a: sha(p.pdfs[a]) for a in lidos if a in p.pdfs}
            _grava(os.path.join(ag, "paginas.json"), {
                "licitacao": p.nome, "preparado_em": "2026-09-23T22:14:17-0300", "segundos": 0.2,
                "condicoes": p.leitura_condicoes or {"arquivos_ocr": [], "paginas_ocr": 0, "furtivos": []},
                "hashes": hashes, "pedacos": ["contexto_01.txt"],
                "paginas": [{"arquivo": a, "numero": n, "texto": t} for a, n, t in p.leitura_paginas]})
            _grava(os.path.join(ag, "assinatura.json"), {
                a: sha("\n".join(t for x, _, t in p.leitura_paginas if x == a).encode()) for a in lidos})
        if p.respostas_agente is not None:
            _grava(os.path.join(ag, "respostas.json"), {"respostas": p.respostas_agente})
        if p.finalizado is not None:
            _grava(os.path.join(ag, "finalizado.json"), p.finalizado)
    if corpus is not None:
        _grava(os.path.join(snap, "saidas", "_corpus_escopo.json"),
               {"coletado_em": "2026-09-23 21:00", "registros": corpus})
    _grava(os.path.join(snap, "saidas", "_livro.json"), {"versao": 1, "licitacoes": livro or {}})
    _grava(os.path.join(snap, "saidas", "_livro_download.json"), {"registros": {}})
    for nome, conteudo in (harness or {}).items():
        _grava(os.path.join(snap, "saidas", nome), conteudo)
    if lote is not None:
        _grava(os.path.join(snap, "saidas", "_lote_claude-opus-5.json"), lote)
    if execucoes is not None:
        os.makedirs(os.path.join(snap, "saidas"), exist_ok=True)
        with open(os.path.join(snap, "saidas", "_execucoes.jsonl"), "w", encoding="utf-8") as f:
            for e in execucoes:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    _grava(os.path.join(snap, "manifesto.json"), {
        "versao": 1, "execucao": {"carimbo": "2026-09-24_0150"},
        "pdfs": pdfs_manifesto, "copias": [], "pulados": [], "contagens": {}})
    return snap, vivo


def finalizado(pasta: str, em: str = "2026-09-23T23:37:13-0300", de: str | None = None) -> dict:
    return {"licitacao": pasta, "aprovadas": 17, "revisar": 0, "reprovadas": 0,
            "nao_localizado": 2, "taxa_ancorada": 1.0, "reaproveitado_de": de, "em": em}


# ------------------------------------------------------------------ verificador real
def auditoria_verificada(nome: str, rs: list[dict], paginas: list[tuple], furtivos=(),
                         modelo: str = "claude-opus-5-5", agente: bool = True) -> dict:
    """
    A auditoria que o v2 grava, produzida pelo VERIFICADOR REAL sobre as páginas
    dadas — como o `70_extracao_por_agente.py finalizar` faz. É o que permite
    testar reverificação por fidelidade: a v3 tem de reproduzir exatamente isto.
    """
    import sys as _sys
    import tempfile
    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "scripts"))
    from fopa import condicoes as cond, extrator, saida, verificador
    from fopa import recuperacao as rec
    from fopa.modelos import Uso
    from fopa.questionario import POR_ID
    respostas = [extrator.Resposta(
        id=r["id"], pergunta=POR_ID[r["id"]].texto, resposta=r["resposta"], arquivo=r.get("arquivo"),
        pagina=r.get("pagina"), trecho_literal=r.get("trecho_literal"), conflito=r.get("conflito"),
        confianca=r.get("confianca") or "media") for r in rs]
    c = cond.Condicoes(provedor="claude-code" if agente else "claude", modelo=modelo,
                       effort="agente" if agente else "high", furtivos=list(furtivos))
    ext = extrator.Extracao(licitacao=nome, respostas=respostas,
                            paginas=[rec.Pagina(a, n, t) for a, n, t in paginas],
                            modo="agente" if agente else "contexto-completo",
                            uso=Uso(chamadas=1, modelo=modelo), arquivos=sorted({a for a, _, _ in paginas}),
                            provedor=c.provedor, effort=c.effort, condicoes=c)
    rel = verificador.verificar(ext)
    with tempfile.TemporaryDirectory() as d:
        caminho = saida.escrever_json(ext, rel, os.path.join(d, "auditoria.json"))
        with open(caminho, encoding="utf-8") as f:
            aud = json.load(f)
    if agente:
        aud["agente"] = {"provedor": "claude-code", "modelo": modelo, "reaproveitado_de": None,
                         "finalizado_em": "2026-09-23T23:37:13-0300"}
    return aud
