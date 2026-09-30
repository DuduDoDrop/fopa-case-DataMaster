# -*- coding: utf-8 -*-
"""
Uma `Extracao` do pacote `fopa` remontada a partir do banco.

É a peça que deixa o verificador e o RELATORIO da v2 rodarem sobre o Postgres
sem mudar uma linha deles (plano, seção 6, `/reverificar` e `/render`).

POR QUE `reconstruir()` E NUNCA `extrair()`
  A fusão do `extrator.extrair` não repõe `pagina_citada`, e é só por esse
  campo que o verificador mantém o rastro de página corrigida
  (verificador.py:150-158). Reverificar por `extrair()` faria REVISAR virar
  APROVADO em silêncio — Adrianópolis Q9 e Fruta de Leite Q12 no acervo.
  Aqui a resposta é remontada como o `13_reverificar.reconstruir()` faz com a
  auditoria: arquivo e página FINAIS da verificação-base, e a página que o
  modelo citou quando for outra.

O TEXTO É O CONGELADO
  Páginas vêm de `paginas` da leitura da execução (ADR-011): reverificar nunca
  relê PDF nem faz OCR. Execução sem leitura (as 10 da API do v2) não se
  reverifica — não há texto congelado contra o que conferir.
"""
from __future__ import annotations

from dataclasses import dataclass

from psycopg.rows import dict_row

from fopa import condicoes as cond
from fopa import extrator
from fopa import recuperacao as rec
from fopa.modelos import Uso
from fopa.questionario import POR_ID
from fopa.verificador import Relatorio


class SemLeitura(RuntimeError):
    """A execução não tem páginas congeladas: não há contra o que verificar."""


class NaoEncontrado(LookupError):
    pass


@dataclass
class UsoLegado(Uso):
    """
    Uso com o custo GRAVADO no v2, nunca recalculado.

    A fórmula mudou (modelos.py:63-66) e ninguém guardou `cache_escrita` das
    extrações da API: recalcular fabricaria um número (plano, seção 9, passo 4).
    """

    brl_fixo: float | None = None
    usd_fixo: float | None = None

    @property
    def preco_conhecido(self) -> bool:
        return self.brl_fixo is not None

    @property
    def usd(self) -> float:
        return float(self.usd_fixo or 0.0)

    @property
    def brl(self) -> float:
        return float(self.brl_fixo or 0.0)


class UsoAgente(Uso):
    """
    Uso de uma execução do AGENTE LOCAL (Claude Code, sem API; ADR-014): não houve chamada cobrada, então não há
    preço a aplicar — nem quando o modelo que ele registra (`claude-opus-5-5`) entrou na tabela para a API (26/09).
    Sem isto o relatório mostraria "R$ 0,00", e R$ 0 nunca é o que se mostra (ADR-012).
    """

    @property
    def preco_conhecido(self) -> bool:
        return False


def _ordem(pid: str) -> int:
    try:
        return int(pid[1:])
    except (TypeError, ValueError):
        return 999


def uso_da_execucao(e: dict) -> Uso:
    base = dict(entrada=e.get("tok_entrada") or 0, saida=e.get("tok_saida") or 0,
                cache_escrita=e.get("tok_cache_escrita") or 0,
                cache_leitura=e.get("tok_cache_leitura") or 0,
                raciocinio=e.get("tok_raciocinio") or 0, chamadas=e.get("chamadas") or 0,
                segundos=float(e.get("segundos") or 0.0), modelo=e.get("modelo") or "")
    if e.get("brl") is None and e.get("brl_legado") is not None:
        fonte = e.get("fonte_migracao") or {}
        return UsoLegado(**base, brl_fixo=float(e["brl_legado"]), usd_fixo=fonte.get("usd_legado"))
    if e.get("origem") == "agente" or e.get("provedor") == "claude-code":
        return UsoAgente(**base)
    return Uso(**base)


def condicoes_de_dict(d: dict | None) -> cond.Condicoes:
    """O inverso de `Condicoes.para_dict()` (o formato gravado na auditoria)."""
    d = d or {}
    doc, ocr, mod = d.get("documentos") or {}, d.get("ocr") or {}, d.get("modelo") or {}
    return cond.Condicoes(
        esperados=doc.get("esperados") or 0, obtidos=doc.get("obtidos") or 0,
        faltando=list(doc.get("faltando") or []),
        arquivos_ocr=list(ocr.get("arquivos") or []), paginas_ocr=ocr.get("paginas") or 0,
        provedor=mod.get("provedor") or "", modelo=mod.get("modelo") or "",
        effort=mod.get("effort") or "", secundario=bool(mod.get("secundario")),
        corpus_horas=d.get("corpus_horas"), furtivos=list(d.get("texto_furtivo") or []),
        abstencoes=list(d.get("abstencoes") or []))


def condicoes_reobservadas(leitura_condicoes: dict | None, base: dict | None, e: dict,
                           respostas: list) -> cond.Condicoes:
    """
    Como o 13_reverificar corrigido faz: os fatos sobre OS ARQUIVOS (OCR, texto
    furtivo) vêm da leitura, que é o que foi observado quando o texto foi
    congelado; a procedência da EXECUÇÃO (provedor, modelo, effort) vem do
    registro. Reverificar muda o veredito, nunca a origem.
    """
    c = condicoes_de_dict(base)
    lc = leitura_condicoes or {}
    c.arquivos_ocr = list(lc.get("arquivos_ocr") or (lc.get("ocr") or {}).get("arquivos") or [])
    c.paginas_ocr = lc.get("paginas_ocr") or (lc.get("ocr") or {}).get("paginas") or 0
    c.furtivos = list(lc.get("furtivos") or lc.get("texto_furtivo") or [])
    if not c.provedor:
        c.provedor = e.get("provedor") or ""
        c.modelo = c.modelo or e.get("modelo") or ""
        c.effort = c.effort or e.get("effort") or ""
        c.secundario = c.provedor not in ("claude", "claude-code", "simulado", "gravado", "")
    c.abstencoes = [r.id for r in respostas
                    if (r.resposta or "").strip().lower().startswith("não localizado")]
    return c


def _execucao(conn, execucao_id: int) -> dict:
    e = conn.execute("SELECT * FROM execucoes_modelo WHERE id = %s", (execucao_id,)).fetchone()
    if not e:
        raise NaoEncontrado("execução %s não existe" % execucao_id)
    return e


def _licitacao(conn, controle: str) -> dict:
    return conn.execute("SELECT * FROM licitacoes WHERE controle = %s", (controle,)).fetchone()


def paginas_da_leitura(conn, leitura_id: int) -> list[rec.Pagina]:
    return [rec.Pagina(r["arquivo_nome"], r["numero"], r["texto"]) for r in conn.execute(
        "SELECT arquivo_nome, numero, texto FROM paginas WHERE leitura_id = %s ORDER BY ordem",
        (leitura_id,)).fetchall()]


def respostas_da_execucao(conn, execucao_id: int, base_verificacao_id: int | None) -> list[extrator.Resposta]:
    crus = conn.execute("SELECT * FROM respostas WHERE execucao_id = %s", (execucao_id,)).fetchall()
    base = {}
    if base_verificacao_id:
        base = {r["pergunta_id"]: r for r in conn.execute(
            "SELECT * FROM verificacao_respostas WHERE verificacao_id = %s",
            (base_verificacao_id,)).fetchall()}
    saida = []
    for r in sorted(crus, key=lambda x: _ordem(x["pergunta_id"])):
        b = base.get(r["pergunta_id"])
        if b and b["pagina_final"] is not None:
            arquivo = b["arquivo_canonico"] or r["arquivo_citado"]
            pagina = b["pagina_final"]
            citada = b["pagina_citada"] if b["pagina_citada"] is not None else r["pagina_citada"]
            pagina_citada = citada if (citada is not None and citada != pagina) else None
        else:
            arquivo, pagina, pagina_citada = r["arquivo_citado"], r["pagina_citada"], None
        p = POR_ID.get(r["pergunta_id"])
        saida.append(extrator.Resposta(
            id=r["pergunta_id"], pergunta=p.texto if p else r["pergunta_id"], resposta=r["resposta"],
            arquivo=arquivo, pagina=pagina, trecho_literal=r["trecho_literal"],
            conflito=r["conflito"], confianca=r["confianca"] or "media", pagina_citada=pagina_citada))
    return saida


def _nome(lic: dict) -> str:
    """O nome que o RELATORIO mostra e que o verificador usa como última fonte de modalidade."""
    if lic.get("rotulo"):
        return lic["rotulo"]
    local = "%s/%s" % (lic.get("municipio"), lic.get("uf")) if lic.get("municipio") else lic["controle"]
    return "%s - %s" % (lic.get("modalidade") or "Licitação", local)


def extracao_para_verificar(conn, execucao_id: int, base_verificacao_id: int | None = None, storage=None):
    """(Extracao pronta para o verificador, contexto). Levanta SemLeitura sem texto congelado."""
    conn.row_factory = dict_row
    e = _execucao(conn, execucao_id)
    if not e["leitura_id"]:
        raise SemLeitura("reverificação pendente de leitura: a execução %s não tem páginas "
                         "congeladas (legado da API sem paginas.json)" % execucao_id)
    lic = _licitacao(conn, e["controle"])
    leitura = conn.execute("SELECT * FROM leituras WHERE id = %s", (e["leitura_id"],)).fetchone()
    base = None
    if base_verificacao_id:
        base = conn.execute("SELECT condicoes FROM verificacoes WHERE id = %s",
                            (base_verificacao_id,)).fetchone()
    respostas = respostas_da_execucao(conn, execucao_id, base_verificacao_id)
    paginas = paginas_da_leitura(conn, e["leitura_id"])
    c = condicoes_reobservadas(leitura["condicoes"], base["condicoes"] if base else None, e, respostas)
    # Injeção de verdade (api/injecao.py): leitura com texto furtivo leva só os trechos SUSPEITOS.
    from . import injecao
    suspeitos = injecao.suspeitos(conn, storage, e["leitura_id"], leitura["condicoes"])
    if suspeitos is not None:
        c.furtivos = suspeitos
    ext = extrator.Extracao(
        licitacao=_nome(lic), respostas=respostas, paginas=paginas, modo=e["modo"] or "",
        uso=uso_da_execucao(e), arquivos=list(dict.fromkeys(p.arquivo for p in paginas)),
        provedor=e["provedor"] or "", effort=e["effort"] or "", condicoes=c)
    return ext, {"controle": e["controle"], "slug": lic["slug"], "modalidade": lic["modalidade"],
                 "leitura_id": e["leitura_id"], "execucao": e, "licitacao": lic}


def extracao_verificada(conn, verificacao_id: int):
    """(Extracao com os vereditos DO BANCO, Relatorio do banco, contexto) — para o render."""
    conn.row_factory = dict_row
    v = conn.execute("SELECT * FROM verificacoes WHERE id = %s", (verificacao_id,)).fetchone()
    if not v:
        raise NaoEncontrado("verificação %s não existe" % verificacao_id)
    e = _execucao(conn, v["execucao_id"])
    lic = _licitacao(conn, v["controle"])
    respostas = respostas_da_execucao(conn, e["id"], verificacao_id)
    vr = {r["pergunta_id"]: r for r in conn.execute(
        "SELECT * FROM verificacao_respostas WHERE verificacao_id = %s", (verificacao_id,)).fetchall()}
    for r in respostas:
        b = vr.get(r.id)
        if b:
            r.veredito, r.alertas, r.arquivo_canonico = b["veredito"], list(b["alertas"] or []), b["arquivo_canonico"]
    paginas = paginas_da_leitura(conn, v["leitura_id"]) if v["leitura_id"] else []
    if paginas:
        arquivos = list(dict.fromkeys(p.arquivo for p in paginas))
    else:
        arquivos = [r["nome"] for r in conn.execute(
            "SELECT nome FROM arquivos WHERE controle = %s AND status = 'ok' ORDER BY seq NULLS LAST, nome",
            (v["controle"],)).fetchall()]
    ext = extrator.Extracao(
        licitacao=_nome(lic), respostas=respostas, paginas=paginas, modo=e["modo"] or "",
        uso=uso_da_execucao(e), arquivos=arquivos, provedor=e["provedor"] or "",
        effort=e["effort"] or "", condicoes=condicoes_de_dict(v["condicoes"]))
    rel = Relatorio(aprovadas=v["aprovadas"] or 0, revisar=v["revisar"] or 0,
                    reprovadas=v["reprovadas"] or 0, nao_localizado=v["nao_localizado"] or 0,
                    ancoradas=v["ancoradas"] or 0, alertas_globais=list(v["alertas_globais"] or []))
    return ext, rel, {"controle": v["controle"], "slug": lic["slug"], "link": lic["link"],
                      "verificacao": v, "licitacao": lic}


__all__ = ["extracao_para_verificar", "extracao_verificada", "uso_da_execucao",
           "condicoes_de_dict", "condicoes_reobservadas", "UsoLegado", "UsoAgente", "SemLeitura", "NaoEncontrado"]
