# -*- coding: utf-8 -*-
"""
O plano de importação: o acervo v2 inteiro traduzido em linhas da v3, em memória.

Nada aqui toca o banco nem o storage. `montar()` lê o snapshot e decide, para
cada licitação, o estado, a pasta canônica, os arquivos com status, as leituras
congeladas, as execuções com procedência e as verificações — seguindo a seção
9 do plano. `importar.py` só escreve o que sair daqui.

A separação existe porque as decisões são muitas, pequenas e todas nasceram de
um caso real; testá-las com um snapshot sintético de três pastas é o único
jeito de mantê-las honestas quando o acervo mudar.

O texto das páginas NÃO fica no plano (são ~40 mil páginas): a leitura guarda
só metadados, e o importador relê o `paginas.json` de uma pasta por vez.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from datetime import date

from fopa import recuperacao as rec
from fopa.pncp import Licitacao as LicitacaoPNCP

from . import regras
from .acervo import Acervo

# O paginas.json não registra a versão do Tesseract. "host" é inferência pelo
# fuso -0300 de `preparado_em` (a máquina de desenvolvimento), e fica escrito
# assim: nunca como se tivesse sido medido (seção 9, passo 3).
VERSAO_OCR_HOST = "host-5.4.0.20240606+tessdata_fast:c4932b937207 (inferida)"
TESSDATA_HOST = "c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb"
CUSTO_FORMULA_LEGADO = "legado (cache_escrita desconhecida)"
MODELO_AGENTE_PADRAO = "claude-opus-5-5"

RE_DATA = re.compile(r"^(\d{4}-\d{2}-\d{2})")
RE_UF = re.compile(r"^[A-Z]{2}$")


@dataclass
class LicitacaoPlano:
    controle: str
    campos: dict
    estado: str = "nova"
    estado_motivo: str | None = None
    pastas: list = field(default_factory=list)
    canonica: str | None = None
    canonica_motivo: str | None = None
    procedencia_incerta: bool = False
    gemea_de: str | None = None


@dataclass
class LeituraPlano:
    controle: str
    pasta: str
    preparado_em: str | None
    segundos: float | None
    condicoes: dict
    hashes_bytes: dict
    assinatura: dict
    assinatura_conjunto: str
    assinatura_nomes: str
    n_paginas: int
    chars_total: int
    modo_sugerido: str
    limpa: bool
    vigente: bool = False
    versao_ocr: str = VERSAO_OCR_HOST
    tessdata_sha256: str = TESSDATA_HOST
    procedencia_texto: str = "legado_paginas_json"


@dataclass
class VerificacaoPlano:
    versao_regras: str
    vigente: bool
    aprovadas: int
    revisar: int
    reprovadas: int
    nao_localizado: int
    ancoradas: int | None
    respondidas: int
    taxa_ancorada: float | None
    alertas_globais: list
    tags: list
    degradada: bool
    condicoes: dict
    q13_estruturada: dict
    itens_api_usados: bool
    auditoria_json: dict
    respostas: list


@dataclass
class ExecucaoPlano:
    chave: str
    controle: str
    pasta: str
    origem: str
    provedor: str | None
    modelo: str | None
    modo: str | None
    effort: str | None
    lote: int | None
    status: str
    canonica: bool
    procedencia_completa: bool
    fonte_migracao: dict
    respostas: list
    respostas_sha256: str
    k_rag: int | None = None
    rotulo: str | None = None
    chamadas: int | None = None
    tok_entrada: int | None = None
    tok_saida: int | None = None
    tok_cache_escrita: int | None = None
    tok_cache_leitura: int | None = None
    tok_raciocinio: int | None = None
    segundos: float | None = None
    usd: float | None = None
    brl: float | None = None
    preco_conhecido: bool | None = None
    brl_legado: float | None = None
    custo_formula: str | None = None
    iniciado_em: str | None = None
    finalizado_em: str | None = None
    leitura_pasta: str | None = None
    reaproveitado_de_pasta: str | None = None
    verificacao: VerificacaoPlano | None = None


@dataclass
class Plano:
    carimbo: str
    manifesto_sha256: str
    licitacoes: dict = field(default_factory=dict)
    pastas_legado: list = field(default_factory=list)
    arquivos: dict = field(default_factory=dict)
    leituras: list = field(default_factory=list)
    execucoes: list = field(default_factory=list)
    gabaritos: list = field(default_factory=list)
    itens_api: dict = field(default_factory=dict)
    execucoes_workflow: list = field(default_factory=list)
    decisoes: list = field(default_factory=list)
    avisos: list = field(default_factory=list)


# ------------------------------------------------------------------ campos
def _data(s) -> str | None:
    m = RE_DATA.match(str(s or ""))
    return m.group(1) if m else None


def _uf(s) -> str | None:
    s = str(s or "").strip().upper()
    return s if RE_UF.match(s) else None


def _campos(controle: str, base: dict, origem: str, rotulo: str | None, livro: dict) -> dict:
    """As colunas de `licitacoes` a partir do inventário (ou do corpus)."""
    cnpj, ano, seq = regras.partes_controle(controle)
    escopo = base.get("escopo") if isinstance(base.get("escopo"), dict) else None
    dentro = escopo.get("dentro") if escopo else base.get("dentro")
    motivo = escopo.get("motivo") if escopo else base.get("motivo")
    fim, tem_hora = regras.fim_prazo(base.get("fim_prazo"))
    reg = livro.get(controle) or {}
    return {
        "ano": ano, "seq": seq,
        "orgao": base.get("orgao") or None, "uf": _uf(base.get("uf")),
        "municipio": base.get("municipio") or None, "modalidade": base.get("modalidade") or None,
        "objeto": base.get("objeto") or None, "situacao": base.get("situacao") or None,
        "publicado_em": _data(base.get("publicado_em")),
        "fim_prazo": fim, "fim_prazo_tem_hora": tem_hora,
        "link": base.get("link") or LicitacaoPNCP.de_controle(controle).link,
        "atualizado_pncp": (str(reg.get("atualizado_pncp"))[:19].replace("T", " ")
                            if reg.get("atualizado_pncp") else None),
        "visto_em": _data(reg.get("visto_em")),
        "escopo_dentro": bool(dentro) if dentro is not None else True,
        "escopo_motivo": motivo or None, "escopo_versao": "legado",
        "rotulo": rotulo, "origem": origem,
    }


# ------------------------------------------------------------------ verificação
def _int(v, padrao=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return padrao


def _verificacao(aud: dict, aud_sha: str, vigente: bool, nomes, itens_api_usados: bool) -> VerificacaoPlano:
    v = aud.get("verificacao") or {}
    ap, rv, rp, nl = (_int(v.get(k)) for k in ("aprovadas", "revisar", "reprovadas", "nao_localizado"))
    respondidas = ap + rv + rp - nl
    taxa = v.get("taxa_ancorada")
    # O Relatorio não grava `ancoradas`; o painel v2 o recupera assim
    # (painel.py:350). A taxa vem com 4 casas, então o arredondamento é exato.
    ancoradas = int(round(taxa * respondidas)) if taxa is not None else None
    cond = aud.get("condicoes") or {}
    q13 = next((r.get("resposta") for r in aud.get("respostas") or [] if r.get("id") == "Q13"), "")
    respostas = []
    for r in aud.get("respostas") or []:
        veredito = r.get("veredito")
        if veredito not in ("APROVADO", "REVISAR", "REPROVADO"):
            veredito = "REVISAR"      # nunca APROVADO por falta de informação
        final = r.get("pagina")
        respostas.append({
            "pergunta_id": r.get("id"), "veredito": veredito,
            "arquivo_canonico": regras.resolver_nome(r.get("arquivo"), nomes),
            "pagina_final": final,
            # a página que o MODELO citou: a corrigida guarda a original em
            # `pagina_citada`; sem correção, é a própria (verificador.py:150-158)
            "pagina_citada": r.get("pagina_citada") if r.get("pagina_citada") is not None else final,
            "alertas": list(r.get("alertas") or []),
            "ausencia": regras.ausencia(r),
        })
    return VerificacaoPlano(
        versao_regras="legado:" + aud_sha, vigente=vigente,
        aprovadas=ap, revisar=rv, reprovadas=rp, nao_localizado=nl,
        ancoradas=ancoradas, respondidas=respondidas, taxa_ancorada=taxa,
        alertas_globais=list(v.get("alertas_globais") or []),
        tags=list(cond.get("tags") or []), degradada=bool(cond.get("degradada")),
        condicoes=cond, q13_estruturada=regras.q13_estruturada(q13),
        itens_api_usados=itens_api_usados, auditoria_json=aud, respostas=respostas)


def _crua(r: dict) -> dict:
    """A resposta como o modelo a deu (colunas de `respostas`)."""
    pag = r.get("pagina_citada") if r.get("pagina_citada") is not None else r.get("pagina")
    return {"pergunta_id": r.get("id"), "resposta": r.get("resposta") or "",
            "arquivo_citado": r.get("arquivo"), "pagina_citada": pag,
            "trecho_literal": r.get("trecho_literal"), "conflito": r.get("conflito"),
            "confianca": r.get("confianca") if r.get("confianca") in ("alta", "media", "baixa") else None}


# ------------------------------------------------------------------ execuções
def _execucao_agente(pasta, controle, aud, aud_sha, acervo: Acervo, canonica, vigente, nomes,
                     itens_api_usados) -> ExecucaoPlano:
    fin = acervo.finalizado(pasta) or {}
    ag = aud.get("agente") or {}
    crus = acervo.respostas_agente(pasta)
    if crus:
        respostas, resp_sha = crus
    else:
        respostas, resp_sha = aud.get("respostas") or [], None
    lista = [_crua(r) for r in respostas]
    uso = aud.get("uso") or {}
    return ExecucaoPlano(
        chave="agente:" + pasta, controle=controle, pasta=pasta, origem="agente",
        provedor="claude-code", modelo=ag.get("modelo") or uso.get("modelo") or MODELO_AGENTE_PADRAO,
        modo="agente", effort="agente", lote=17, status="ok", canonica=canonica,
        procedencia_completa=True, chamadas=_int(uso.get("chamadas"), None),
        # Extração por agente não passa pela API: não há fatura, e o modelo não
        # tem preço na tabela. NULL, nunca 0 (ADR-012, saida.py:169-173).
        usd=None, brl=None, preco_conhecido=False,
        fonte_migracao={"chave": "agente:" + pasta, "pasta": pasta, "auditoria_sha256": aud_sha,
                        "respostas_json_sha256": resp_sha, "finalizado": fin or None},
        respostas=lista, respostas_sha256=regras.respostas_sha256(respostas),
        iniciado_em=None, finalizado_em=fin.get("em") or ag.get("finalizado_em"),
        leitura_pasta=pasta if acervo.tem_leitura(pasta) else None,
        reaproveitado_de_pasta=fin.get("reaproveitado_de") or ag.get("reaproveitado_de"),
        verificacao=_verificacao(aud, aud_sha, vigente, nomes, itens_api_usados))


def _execucao_api(pasta, controle, aud, aud_sha, acervo: Acervo, canonica, vigente, nomes,
                  itens_api_usados, lote_linhas: dict, harness_por_pasta: dict) -> ExecucaoPlano:
    uso = aud.get("uso") or {}
    modelo = uso.get("modelo") or "claude-opus-5"
    inferidos = ["provedor", "effort", "lote"]
    chamadas = _int(uso.get("chamadas"), None)
    if not chamadas:
        chamadas = 3           # lote 6 = 3 chamadas; o 0 veio de promoção do harness
        inferidos.append("chamadas")
    fonte = {"chave": "api:" + pasta, "pasta": pasta, "auditoria_sha256": aud_sha,
             "usd_legado": uso.get("usd"), "inferidos": inferidos,
             "lote": lote_linhas.get(pasta), "harness": None}
    for nome_arquivo, h in harness_por_pasta.get(pasta, []):
        casou = regras.casar_harness(aud, h, modelo)
        if casou != "ambíguo":
            fonte["harness"] = dict(casou, arquivo=nome_arquivo)
            break
    if fonte["harness"] is None and uso.get("chamadas") in (0, None) and harness_por_pasta.get(pasta):
        fonte["harness"] = "ambíguo"
    respostas = aud.get("respostas") or []
    return ExecucaoPlano(
        chave="api:" + pasta, controle=controle, pasta=pasta, origem="api",
        provedor="claude", modelo=modelo, modo=aud.get("modo") or None, effort="high", lote=6,
        k_rag=6 if aud.get("modo") == "rag" else None, status="ok", canonica=canonica,
        # Custo e tokens como vieram, NUNCA recalculados: a fórmula mudou
        # (modelos.py:63-66) e ninguém guardou cache_escrita (seção 9, passo 4).
        procedencia_completa=False, chamadas=chamadas,
        tok_entrada=_int(uso.get("entrada"), None), tok_saida=_int(uso.get("saida"), None),
        tok_cache_escrita=None, tok_cache_leitura=_int(uso.get("cache_leitura"), None),
        tok_raciocinio=_int(uso.get("raciocinio"), None), segundos=uso.get("segundos"),
        usd=None, brl=None, preco_conhecido=True, brl_legado=uso.get("brl"),
        custo_formula=CUSTO_FORMULA_LEGADO, fonte_migracao=fonte,
        respostas=[_crua(r) for r in respostas], respostas_sha256=regras.respostas_sha256(respostas),
        leitura_pasta=None,
        verificacao=_verificacao(aud, aud_sha, vigente, nomes, itens_api_usados))


# ------------------------------------------------------------------ estado
_SO_FORMATO = {"formato_nao_suportado", "zip_container"}


def _estado(lic: LicitacaoPlano, arquivos: list, tem_leitura: bool, tem_vigente: bool,
            suspeito: bool, dicas: list, hoje: date) -> tuple[str, str]:
    c = lic.campos
    if not c["escopo_dentro"]:
        return "fora_escopo", c.get("escopo_motivo") or "fora do escopo de folha"
    if not lic.pastas:
        fim = _data(c.get("fim_prazo"))
        if fim and fim < hoje.isoformat():
            return "fora_janela", "sessão encerrada antes da importação; nunca baixada"
        return "nova", "no corpus de escopo, ainda não baixada"
    if suspeito:
        return "legado_suspeito", "duas pastas com execução e nenhum critério para escolher"
    if tem_vigente:
        return "verificada", "importada do acervo v2 com verificação"
    if tem_leitura:
        return "preparada", "páginas congeladas pelo agente; sem extração"
    status = [a.status for a in arquivos]
    if "ok" in status:
        return "baixada_ok", "PDFs no acervo; ainda não lidos"
    # Mesma regra do W21 (28:562-602): só formato -> formato_nao_suportado;
    # falha de rede -> falha_rede; senão sem_pdf_legivel.
    if "formato-nao-suportado" in dicas or (status and all(s in _SO_FORMATO for s in status)):
        return "formato_nao_suportado", "nenhum arquivo em formato legível"
    if "falhou" in dicas or "sem_causa" in dicas or "falha_rede" in status:
        return "falha_rede", "download falhou no v2; retentável"
    return "sem_pdf_legivel", "nenhum PDF legível no acervo"


# ------------------------------------------------------------------ montar
def montar(acervo: Acervo, hoje: date) -> Plano:
    plano = Plano(carimbo=acervo.carimbo, manifesto_sha256=acervo.manifesto_sha256)
    livro = acervo.livro()

    # 1. identidade: corpus como base, inventário por cima
    for r in acervo.corpus():
        c = (r.get("controle") or "").strip()
        try:
            regras.partes_controle(c)
        except ValueError:
            plano.avisos.append("corpus: controle inválido %r" % c)
            continue
        plano.licitacoes[c] = LicitacaoPlano(controle=c, campos=_campos(c, r, "corpus", None, livro))

    por_controle: dict[str, list[tuple[str, dict]]] = collections.defaultdict(list)
    for pasta, inv in acervo.pastas_com_inventario():
        c = (inv.get("controle") or "").strip()
        try:
            regras.partes_controle(c)
        except ValueError:
            plano.avisos.append("%s: inventário sem controle válido (%r)" % (pasta, c))
            continue
        por_controle[c].append((pasta, inv))

    lote = acervo.lote() or {}
    lote_linhas = {l.get("licitacao"): l for l in lote.get("linhas") or []}
    harness_por_pasta = collections.defaultdict(list)
    for nome_arq, h in acervo.harness():
        harness_por_pasta[h.get("licitacao")].append((nome_arq, h))
    promovidos: set[tuple[str, int]] = set()

    for c, pastas in sorted(por_controle.items()):
        pastas.sort(key=lambda x: x[0])
        multiplas = len(pastas) > 1

        # arquivos por pasta, antes de saber a canônica (a limpeza da leitura depende deles)
        arqs_pasta, shas_inv = {}, {}
        for pasta, inv in pastas:
            arqs = regras.arquivos_da_pasta(inv, acervo.disco(pasta), contaminada=multiplas)
            for a in arqs:
                a.pasta = pasta
            arqs_pasta[pasta] = arqs
            shas_inv[pasta] = {a.sha256 for a in arqs if a.do_inventario and a.sha256}

        # candidatas à canônica
        auds, cands, leituras_meta = {}, [], {}
        for pasta, inv in pastas:
            a = acervo.auditoria(pasta)
            if a:
                auds[pasta] = a
            meta = None
            if acervo.tem_leitura(pasta):
                le = acervo.leitura(pasta) or {}
                hashes = le.get("hashes") or {}
                assinatura = acervo.assinatura(pasta) or {}
                paginas = [rec.Pagina(p.get("arquivo"), p.get("numero"), p.get("texto") or "")
                           for p in le.get("paginas") or []]
                meta = LeituraPlano(
                    controle=c, pasta=pasta, preparado_em=le.get("preparado_em"),
                    segundos=le.get("segundos"), condicoes=le.get("condicoes") or {},
                    hashes_bytes=hashes, assinatura=assinatura,
                    assinatura_conjunto=regras.assinatura_conjunto(assinatura),
                    assinatura_nomes=regras.assinatura_nomes(assinatura),
                    n_paginas=len(paginas), chars_total=sum(len(p) for p in paginas),
                    modo_sugerido=rec.escolher_modo(paginas) if paginas else "contexto-completo",
                    limpa=regras.leitura_limpa(hashes, shas_inv[pasta]))
                leituras_meta[pasta] = meta
            fin = acervo.finalizado(pasta) or {}
            quando = (fin.get("em") or (a[0].get("agente") or {}).get("finalizado_em")) if a else None
            cands.append({"pasta": pasta, "tem_execucao": pasta in auds, "finalizado_em": quando,
                          "reaproveitado_de": fin.get("reaproveitado_de"),
                          "leitura_limpa": meta.limpa if meta else None})

        if multiplas:
            canonica, motivo = regras.escolher_canonica(cands)
        else:
            canonica, motivo = pastas[0][0], "única pasta"
        com_execucao = [x for x in cands if x["tem_execucao"]]
        suspeito = multiplas and len(com_execucao) > 1 and canonica is None
        if multiplas and canonica is None and not suspeito:
            # nenhuma execução (ou uma só já resolvida acima): a pasta de
            # referência é a de leitura limpa mais recente, senão a primeira.
            limpas = [p for p, m in leituras_meta.items() if m.limpa]
            canonica = sorted(limpas)[0] if limpas else pastas[0][0]
            motivo = "sem execução: pasta de referência para metadados e leitura"
        if suspeito:
            plano.decisoes.append({"controle": c, "pastas": [p for p, _ in pastas],
                                   "motivo": motivo, "candidatas": com_execucao})

        base_inv = dict(pastas)[canonica] if canonica else pastas[0][1]
        lic = plano.licitacoes.get(c)
        campos = _campos(c, base_inv, "legado", canonica or pastas[0][0], livro)
        if lic is None:
            lic = LicitacaoPlano(controle=c, campos=campos)
            plano.licitacoes[c] = lic
        else:
            lic.campos = campos
        lic.pastas = [p for p, _ in pastas]
        lic.canonica, lic.canonica_motivo = canonica, motivo

        # arquivos da licitação: canônica primeiro; nas outras pastas, o mesmo
        # conteúdo já visto é alias, o mesmo nome e conteúdo é a mesma linha.
        ordem = ([canonica] if canonica else []) + [p for p, _ in pastas if p != canonica]
        vistos_nome: dict[str, regras.ArquivoLegado] = {}
        vistos_sha: dict[str, str] = {}
        linhas = []
        for pasta in ordem:
            for a in arqs_pasta[pasta]:
                ja = vistos_nome.get(a.nome)
                if ja is not None:
                    if ja.sha256 != a.sha256 and a.sha256:
                        plano.avisos.append("%s: '%s' com conteúdo diferente em %s e %s"
                                            % (c, a.nome, ja.pasta, pasta))
                    continue
                if (a.sha256 and a.sha256 in vistos_sha and a.status in ("ok", "fora_inventario")
                        and pasta != canonica):
                    a.status, a.alias_de = "alias_duplicado", vistos_sha[a.sha256]
                vistos_nome[a.nome] = a
                if a.sha256 and a.tem_bytes and a.sha256 not in vistos_sha:
                    vistos_sha[a.sha256] = a.nome
                linhas.append(a)
        plano.arquivos[c] = linhas
        nomes = {a.nome for a in linhas}

        # leituras: a vigente é a da pasta canônica (se tiver), senão a limpa mais recente
        for pasta, meta in leituras_meta.items():
            plano.leituras.append(meta)
        if leituras_meta:
            if canonica in leituras_meta and not suspeito:
                vig = canonica
            else:
                ordenadas = sorted(leituras_meta.values(),
                                   key=lambda m: (m.limpa, m.preparado_em or ""), reverse=True)
                vig = ordenadas[0].pasta
            leituras_meta[vig].vigente = True

        # execuções
        tem_vigente = False
        for pasta, (aud, aud_sha) in auds.items():
            e_canonica = (pasta == canonica) and not suspeito
            itens = acervo.tem_itens_api(pasta)
            eh_agente = ("agente" in aud) or ((aud.get("uso") or {}).get("provedor") == "claude-code")
            if eh_agente:
                ex = _execucao_agente(pasta, c, aud, aud_sha, acervo, e_canonica, e_canonica, nomes, itens)
            else:
                ex = _execucao_api(pasta, c, aud, aud_sha, acervo, e_canonica, e_canonica, nomes, itens,
                                   lote_linhas, harness_por_pasta)
                h = ex.fonte_migracao.get("harness")
                if isinstance(h, dict):
                    promovidos.add((h["arquivo"], h["indice"]))
            tem_vigente = tem_vigente or e_canonica
            plano.execucoes.append(ex)

        # itens da API e gabarito (da canônica, senão de qualquer pasta)
        for pasta in ordem:
            if c not in plano.itens_api and acervo.tem_itens_api(pasta):
                plano.itens_api[c] = acervo.itens_api(pasta)
            g = acervo.gabarito(pasta)
            if g and not any(x["controle"] == c for x in plano.gabaritos):
                for pid, q in (g.get("perguntas") or {}).items():
                    plano.gabaritos.append({
                        "controle": c, "pergunta_id": pid, "critica": bool(q.get("critica")),
                        "resposta_referencia": q.get("resposta_referencia"),
                        "fatos_obrigatorios": list(q.get("fatos_obrigatorios") or []),
                        "fatos_desejaveis": list(q.get("fatos_desejaveis") or []),
                        "fonte": {"arquivo_gabarito": pasta, "metodo": g.get("metodo"),
                                  "construido_em": g.get("construido_em"), "citacoes": q.get("fonte"),
                                  "observacao": q.get("observacao")}})

        dicas = []
        for _, inv in pastas:
            if inv.get("estado_no_livro"):
                dicas.append(inv["estado_no_livro"])
            if inv.get("sem_causa_registrada"):
                dicas.append("sem_causa")
        lic.estado, lic.estado_motivo = _estado(lic, linhas, bool(leituras_meta), tem_vigente,
                                                suspeito, dicas, hoje)
        for pasta, _ in pastas:
            plano.pastas_legado.append({"pasta": pasta, "controle": c, "canonica": pasta == canonica,
                                        "motivo": motivo if pasta == canonica else None})

    # licitações só do corpus: estado pelo escopo e pelo prazo
    for c, lic in plano.licitacoes.items():
        if not lic.pastas:
            lic.estado, lic.estado_motivo = _estado(lic, [], False, False, False, [], hoje)

    # 2. harness que não virou execução canônica, e experimentos
    pasta_para_controle = {p["pasta"]: p["controle"] for p in plano.pastas_legado}
    for pasta, lista in harness_por_pasta.items():
        c = pasta_para_controle.get(pasta)
        if not c:
            plano.avisos.append("harness de pasta sem controle: %s" % pasta)
            continue
        for nome_arq, h in lista:
            for i, e in enumerate(h.get("execucoes") or []):
                if (nome_arq, i) in promovidos:
                    continue
                rs = regras.respostas_do_harness(e)
                chave = "harness:%s:%d" % (nome_arq, i)
                plano.execucoes.append(ExecucaoPlano(
                    chave=chave, controle=c, pasta=pasta, origem="harness",
                    provedor="claude" if str(e.get("modelo", "")).startswith("claude") else "openai",
                    modelo=e.get("modelo"), modo=e.get("modo"), effort=e.get("effort"), lote=6,
                    rotulo=e.get("rotulo"), status="ok", canonica=False, procedencia_completa=False,
                    tok_entrada=_int(e.get("entrada"), None), tok_saida=_int(e.get("saida"), None),
                    segundos=e.get("seg"), brl_legado=e.get("brl"), preco_conhecido=True,
                    custo_formula=CUSTO_FORMULA_LEGADO,
                    fonte_migracao={"chave": chave, "arquivo": nome_arq, "indice": i,
                                    "repeticao": e.get("repeticao")},
                    respostas=[_crua(r) for r in rs], respostas_sha256=regras.respostas_sha256(rs)))
    for pasta_exp, aud, sha in acervo.experimentos():
        alvo = aud.get("licitacao")
        c = pasta_para_controle.get(alvo)
        if not c:
            plano.avisos.append("experimento %s sem controle (licitacao=%r): não importado"
                                % (pasta_exp, alvo))
            continue
        uso = aud.get("uso") or {}
        rs = aud.get("respostas") or []
        chave = "experimento:" + pasta_exp
        modelo = uso.get("modelo")
        plano.execucoes.append(ExecucaoPlano(
            chave=chave, controle=c, pasta=pasta_exp, origem="experimento",
            provedor="openai" if str(modelo or "").startswith("gpt") else "claude",
            modelo=modelo, modo=aud.get("modo"), effort=uso.get("effort") or None, lote=6,
            status="ok", canonica=False, procedencia_completa=False,
            chamadas=_int(uso.get("chamadas"), None), tok_entrada=_int(uso.get("entrada"), None),
            tok_saida=_int(uso.get("saida"), None), tok_cache_leitura=_int(uso.get("cache_leitura"), None),
            segundos=uso.get("segundos"), brl_legado=uso.get("brl"), preco_conhecido=True,
            custo_formula=CUSTO_FORMULA_LEGADO,
            fonte_migracao={"chave": chave, "pasta": pasta_exp, "auditoria_sha256": sha,
                            "usd_legado": uso.get("usd")},
            respostas=[_crua(r) for r in rs], respostas_sha256=regras.respostas_sha256(rs),
            verificacao=_verificacao(aud, sha, False, {a.nome for a in plano.arquivos.get(c, [])},
                                     False)))

    # 3. gêmeas entre controles diferentes: o mesmo TEXTO lido (70_:489-503) ou,
    #    quando uma delas não tem leitura (legado da API), o mesmo CONJUNTO de
    #    PDFs — mesmos bytes, mesmo texto. Conjunto idêntico, não "algum em
    #    comum": dividir só o edital (Capão do Cipó 303/304) é outra coisa.
    pai: dict[str, str] = {}

    def raiz(c):
        while pai.get(c, c) != c:
            c = pai[c]
        return c

    def juntar(grupo):
        grupo = sorted(grupo)
        for c in grupo[1:]:
            pai[raiz(c)] = raiz(grupo[0])

    por_assinatura = collections.defaultdict(set)
    for le in plano.leituras:
        if le.vigente:
            por_assinatura[le.assinatura_conjunto].add(le.controle)
    por_bytes = collections.defaultdict(set)
    for c, linhas in plano.arquivos.items():
        shas = frozenset(a.sha256 for a in linhas if a.status == "ok" and a.do_inventario and a.sha256)
        if shas:
            por_bytes[shas].add(c)
    for grupo in list(por_assinatura.values()) + list(por_bytes.values()):
        if len(grupo) > 1:
            juntar(grupo)
    grupos = collections.defaultdict(set)
    for c in pai:
        grupos[raiz(c)].add(c)
    for grupo in grupos.values():
        grupo |= {raiz(next(iter(grupo)))}
        if len(grupo) < 2:
            continue
        verificadas = sorted(c for c in grupo if plano.licitacoes[c].estado == "verificada")
        rep = verificadas[0] if verificadas else sorted(grupo)[0]
        for c in grupo:
            if c != rep:
                plano.licitacoes[c].gemea_de = rep

    # 4. log legado do v2
    for e in acervo.execucoes_legado():
        extras = {k: v for k, v in e.items()
                  if k not in ("em", "script", "duracao_s", "argumentos", "custo_brl")}
        plano.execucoes_workflow.append({
            "workflow": "legado", "script_legado": e.get("script"), "iniciado_em": e.get("em"),
            "duracao_s": e.get("duracao_s"), "argumentos": {"linha": e.get("argumentos")},
            "custo_brl": e.get("custo_brl") or 0.0, "contadores": extras, "status": "ok"})
    return plano


__all__ = ["Plano", "LicitacaoPlano", "LeituraPlano", "ExecucaoPlano", "VerificacaoPlano",
           "montar", "VERSAO_OCR_HOST", "TESSDATA_HOST"]
