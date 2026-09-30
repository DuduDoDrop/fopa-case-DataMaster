# -*- coding: utf-8 -*-
"""
Antes × depois da v3.1 — Pirapó e Bertioga, no Claude e no GPT (plano da v3.1, Task 8).

    python scripts/35_antes_depois.py --seco            estima montando os prompts reais: NENHUMA chamada de modelo
    python scripts/35_antes_depois.py                   mede de verdade (gasta: só com autorização explícita)
    python scripts/35_antes_depois.py --licitacoes "C:\\...\\amostras\\<pasta>" --modelos gpt-5.6-sol --configs depois

O QUE COMPARA
  A v3.1 mudou duas coisas no extrator (a ordem do prompt e o Best-of-N com N=3, só nas que falham):

    antes    perguntas-primeiro, N=1     a mensagem da v3.0, byte a byte; o documento é regravado a cada lote
    depois   documentos-primeiro, N=3    o documento vai para o cache do provedor; o reforço reamostra só o que falha

  Decisão de 28/09: remedir Pirapó e Bertioga — as duas licitações com `_gabarito.json` — no Claude e no GPT.
  Para cada licitação × modelo × configuração: `extrator.extrair` → `verificador.verificar` → acurácia contra o
  gabarito (a mesma do `15_acuracia.py`: todas e críticas) → custo pelo `ext.uso` (entrada, cache gravado, cache
  lido, saída, US$ e R$), tempo, aprovadas/revisar/reprovadas e quantas perguntas o reforço recuperou.

  Cada execução vira `<saidas>/<licitação>/<modelo>-<config>/auditoria.json` (o escritor do 33_varredura_modelos,
  que o `15_acuracia.py --extra` lê); o consolidado, `resultado.json` + `resultado.md` (regravados a cada execução,
  para uma queda no meio não perder o que já foi pago).

O TETO
  Antes de cada execução: gasto medido até ali (o `ext.uso` das já feitas) + a estimativa da próxima > teto → para.
  Execução que falha no meio não devolve o `ext.uso` do que já foi cobrado: conta-se a estimativa dela. Modelo sem
  preço no catálogo (`modelos.PRECOS`) não roda — sem preço, o teto não protegeria nada.

O --SECO
  Monta os prompts de verdade (as mesmas funções do extrator: `_paginas_do_lote`, `usuario_do_lote`,
  `recuperacao.escolher_modo`), conta os tokens (o o200k_base do `27_orcamento_openai.py`; no Claude, com o fator
  medido), simula o cache chamada a chamada (`simular_cache`) e aplica o preço do `modelos.py` (`Uso.usd`). As
  hipóteses — saída por lote e tamanho do reforço — são declaradas na saída e em `estimativa.json`.
"""
from __future__ import annotations

import argparse
import functools
import importlib.util
import io
import itertools
import json
import math
import os
import re
import sys
import time

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import condicoes as cond                                            # noqa: E402
from fopa import extrator, inventario, modelos, saida, verificador           # noqa: E402
from fopa import recuperacao as rec                                           # noqa: E402
from fopa.questionario import ESQUEMA_LOTE, PERGUNTAS, instrucao_sistema      # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")

# as duas configurações — "depois" é o padrão da v3.1 (extrator.ORDEM_PADRAO, melhor_de_n.N_PADRAO)
CONFIGURACOES = {
    "antes": {"ordem": "perguntas-primeiro", "melhor_de_n": 1},
    "depois": {"ordem": "documentos-primeiro", "melhor_de_n": 3},
}
MODELOS_PADRAO = ("claude-opus-5-5", "gpt-5.6-sol")
TETO_BRL_PADRAO = 60.0
# a extração é a de produção: os padrões do `extrair` (6 perguntas por lote, k=6 no RAG, effort high)
LOTE, K_RAG, EFFORT = 6, 6, "high"

# ------------------------------------------------------------------ hipóteses da estimativa (declaradas)
# Saída por chamada. Medido em 23/09 nestas duas licitações (saidas/_varredura_*): o Opus 5.5 escreveu ~2.900 tokens
# por lote (8.721 e 8.554 em 3 lotes) e o gpt-5.6-sol ~4.000 (12.009 em 3, raciocínio incluso). 4 mil cobre os dois.
SAIDA_POR_LOTE = 4_000
# O reforço do Best-of-N: 1 lote extra pequeno por execução "depois". As perguntas são as que voltaram "não
# localizado" nas execuções de 23/09 (Q15–Q17 em Pirapó, Q17 em Bertioga). Se a ausência for real — a Q15 e a Q16
# de Pirapó são "Não localizado" no próprio gabarito —, o reforço usa as N-1 = 2 rodadas: o --seco mostra esse
# total também (pior caso).
REFORCO_PERGUNTAS = ("Q15", "Q16", "Q17")
REFORCO_RODADAS = 1
# Tokens. O estimador é o do 27_orcamento_openai.py: tiktoken, codificação o200k_base (a do gpt-5.x). Conferido
# contra as execuções reais de 23/09 (saidas/_varredura_*/gpt-*, entrada + cache lido), com o esquema do structured
# output somado ao sistema:   Pirapó 81.535 estimados × 81.493 medidos (+0,05%) · Bertioga 40.899 × 40.932 (-0,08%).
# O Claude usa outro tokenizador e não há contador local (contar exato é chamada de API, proibida no --seco). O
# fator vem das mesmas licitações, mesmos prompts, no claude-opus-5-5 de 23/09 — entrada + cache lido + o sistema
# gravado no 1º lote (1.542 = 3.084 lidos / 2):   Pirapó 140.610 / 81.535 = 1,72 · Bertioga 72.011 / 40.899 = 1,76.
FATOR_TOKENS_CLAUDE = 1.74


# ------------------------------------------------------------------ plano
def provedor_do_modelo(modelo: str) -> str:
    """claude-* → Claude; gpt-* → OpenAI (os dois provedores de `modelos.obter_provedor`)."""
    if modelo.startswith("claude-"):
        return "claude"
    if modelo.startswith("gpt-"):
        return "openai"
    raise ValueError("modelo sem provedor conhecido: %r (use claude-* ou gpt-*)" % modelo)


def matriz(pastas: list[str], lista_modelos: list[str], configs: list[str]) -> list[dict]:
    """As execuções, em ordem: licitação → modelo → configuração."""
    for c in configs:
        if c not in CONFIGURACOES:
            raise ValueError("configuração desconhecida: %r (use %s)" % (c, " ou ".join(CONFIGURACOES)))
    plano = []
    for pasta in pastas:
        nome = os.path.basename(pasta.rstrip("\\/"))
        for m in lista_modelos:
            prov = provedor_do_modelo(m)
            for c in configs:
                plano.append(dict(pasta=pasta, licitacao=nome, modelo=m, provedor=prov, config=c, **CONFIGURACOES[c]))
    return plano


def destino(saidas_dir: str, licitacao: str, modelo: str, config: str) -> str:
    return os.path.join(saidas_dir, licitacao, "%s-%s" % (modelo, config), "auditoria.json")


def licitacoes_padrao(amostras: str = AMOSTRAS) -> list[str]:
    """As pastas de `amostras/` com `_gabarito.json` — só onde há gabarito a acurácia existe."""
    if not os.path.isdir(amostras):
        return []
    return [os.path.join(amostras, d) for d in sorted(os.listdir(amostras))
            if os.path.isfile(os.path.join(amostras, d, "_gabarito.json"))]


def modalidade_da_pasta(pasta: str) -> str:
    """A do portal (`_inventario.json`, como o worker faz com a do banco); sem inventário, o nome da pasta — a mesma
    reserva do `verificador.modalidade_da`. Na execução, a Q3 ainda tem a precedência (modalidade_da)."""
    inv = inventario.ler(pasta) or {}
    return inv.get("modalidade") or os.path.basename(pasta.rstrip("\\/"))


# ------------------------------------------------------------------ acurácia e reforço
def agregar_acuracia(respostas: dict[str, str], perguntas: dict[str, dict], avaliar) -> dict:
    """Todas, críticas e completude — a conta do 15_acuracia.py; `avaliar` é o dele. Resposta ausente conta errada."""
    criticas = {q for q, ref in perguntas.items() if ref.get("critica")}
    acertos = crit = desej = desej_total = 0
    erradas = []
    for q, ref in perguntas.items():
        v = avaliar(respostas.get(q, ""), ref)
        if v["correta"]:
            acertos += 1
            crit += q in criticas
        else:
            erradas.append(q)
        desej += v["desejaveis"]
        desej_total += v["desejaveis_total"]
    return {"acertos": acertos, "total": len(perguntas), "criticas_acertos": crit, "criticas_total": len(criticas),
            "desejaveis": desej, "desejaveis_total": desej_total, "erradas": erradas}


def resumo_reforco(registro: dict) -> dict:
    """O que o Best-of-N fez (`ext.melhor_de_n`). Recuperada = trocou por um candidato com evidência — ancorado (2)
    ou achado noutra página (1); trocar uma reprovada por uma ausência declarada (0) melhora, mas não recupera."""
    registro = registro or {}
    perguntas = registro.get("perguntas") or {}
    trocadas = [p for p in perguntas.values() if p.get("escolhida")]
    return {"rodadas": registro.get("rodadas", 0), "reforcadas": len(perguntas), "trocadas": len(trocadas),
            "recuperadas": sum(1 for p in trocadas if p["pontos"][p["escolhida"]][0] >= 1)}


# ------------------------------------------------------------------ estimativa: prompts, tokens, cache, preço
def sistema_do_prompt() -> str:
    """O que antecede as mensagens em toda chamada: a instrução de sistema e o esquema do structured output. Os dois
    provedores recebem o esquema, estável, no prefixo que vai para o cache junto com o sistema."""
    return instrucao_sistema() + "\n\n" + json.dumps(ESQUEMA_LOTE, ensure_ascii=False)


def chamadas_da_execucao(paginas: list, licitacao: str, ordem: str, melhor_de_n: int, lote: int = LOTE,
                         k_rag: int = K_RAG, reforco=REFORCO_PERGUNTAS, rodadas: int = REFORCO_RODADAS):
    """`(modo, [(sistema, usuario), ...])` — as chamadas que o `extrair` faria, com os prompts de verdade: o mesmo
    modo, as mesmas páginas por lote e a mesma mensagem. O reforço (N > 1) entra como hipótese: `rodadas` lotes
    com as perguntas de `reforco`, nunca mais que as N-1 rodadas do Best-of-N."""
    modo = rec.escolher_modo(paginas)
    indice = rec.IndiceBM25(paginas) if modo == "rag" else None
    ids = [p.id for p in PERGUNTAS]
    grupos = [ids[i:i + lote] for i in range(0, len(ids), lote)]
    grupos += [list(reforco)] * max(0, min(rodadas, melhor_de_n - 1))
    sistema = sistema_do_prompt()
    chamadas = []
    for g in grupos:
        contexto = rec.montar_contexto(extrator._paginas_do_lote(paginas, g, modo, indice, k_rag))
        chamadas.append((sistema, extrator.usuario_do_lote(contexto, g, licitacao, ordem, cache=modo != "rag")))
    return modo, chamadas


def blocos_da_chamada(sistema: str, usuario, contar) -> list[tuple[str, int, bool]]:
    """A chamada em blocos `(texto, tokens, marca)`, na ordem do prompt. `marca` = o bloco termina num breakpoint de
    cache do Claude: o sistema sempre (ProvedorClaude.responder_json); o resto, onde `modelos.conteudo_claude` põe
    `cache_control` — na ordem nova, o prefixo licitação + documentos. A OpenAI ignora as marcas (cache
    automático)."""
    conteudo = modelos.conteudo_claude(usuario)
    if isinstance(conteudo, str):
        conteudo = [{"type": "text", "text": conteudo}]
    return [(sistema, contar(sistema), True)] + [(b["text"], contar(b["text"]), "cache_control" in b)
                                                 for b in conteudo]


def simular_cache(chamadas: list[list[tuple]], provedor: str, minimo: int) -> list[dict]:
    """
    A entrada de cada chamada dividida em comum, gravada no cache e lida do cache, na ordem das chamadas.

    Cada chamada é a lista dos seus blocos `(chave, tokens, marca)` (ver `blocos_da_chamada`); blocos iguais têm a
    mesma chave. O cache dos dois provedores casa por PREFIXO: um trecho só é lido se tudo antes dele for idêntico ao
    de uma chamada anterior. As chamadas de uma execução são seguidas, bem dentro da janela de 5 minutos.

      Claude (explícito)  lê o maior prefixo terminado numa marca que já foi gravado; cada marca depois dele grava
                          o trecho desde o último ponto em cache, se o prefixo tiver ao menos `minimo` tokens (abaixo
                          disso a API não guarda: entrada comum). Depois da última marca: entrada comum.
      OpenAI (automático) lê o maior prefixo de blocos igual ao de uma chamada anterior (se ≥ `minimo`) e GRAVA o
                          resto — a fatura de 23/09: 122.407 tokens gravados contra 321 de entrada nova (Resultados
                          medidos, "O defeito: 45,6% do custo foi GRAVAR cache"). Prompt abaixo do mínimo não entra.

    Preço (modelos.Uso.usd): comum 1× · gravado CACHE_ESCRITA (1,25×) · lido CACHE_LEITURA (0,10×) da entrada.
    Com S = sistema, D = documentos, P = perguntas do lote, e o contexto completo (D igual em todos os lotes):
      antes    Claude  S gravado no 1º lote e lido nos outros; D+P entrada comum em TODOS os lotes
               OpenAI  S+P+D gravado em TODOS os lotes (o que eles têm em comum, S, fica abaixo do mínimo)
      depois   os dois S+D gravado no 1º lote e lido nos seguintes, reforço incluído; P comum (Claude) ou gravado
    No RAG cada lote recupera outras páginas: D muda, nenhuma ordem lê documento do cache — e no Claude a ordem nova
    passa a pagar a gravação (1,25×) de cada contexto.
    """
    if provedor not in ("claude", "openai"):
        raise ValueError("provedor sem regra de cache: %r" % provedor)
    gravados: set[tuple] = set()
    divisoes = []
    for blocos in chamadas:
        chaves = [b[0] for b in blocos]
        acum = list(itertools.accumulate(b[1] for b in blocos))
        total = acum[-1] if acum else 0
        if provedor == "claude":
            marcas = [i for i, b in enumerate(blocos) if b[2]]
            lidas = [i for i in marcas if tuple(chaves[:i + 1]) in gravados]
            lido = acum[lidas[-1]] if lidas else 0
            ponto, gravado = lido, 0
            for i in marcas:
                if acum[i] <= ponto or acum[i] < minimo:
                    continue
                gravado += acum[i] - ponto
                ponto = acum[i]
                gravados.add(tuple(chaves[:i + 1]))
            divisoes.append({"entrada": total - lido - gravado, "cache_escrita": gravado, "cache_leitura": lido})
            continue
        if total < minimo:
            divisoes.append({"entrada": total, "cache_escrita": 0, "cache_leitura": 0})
            continue
        iguais = [i for i in range(len(blocos)) if tuple(chaves[:i + 1]) in gravados]
        lido = acum[iguais[-1]] if iguais and acum[iguais[-1]] >= minimo else 0
        gravados.update(tuple(chaves[:i + 1]) for i in range(len(blocos)))
        divisoes.append({"entrada": 0, "cache_escrita": total - lido, "cache_leitura": lido})
    return divisoes


def minimo_cache(modelo: str) -> int:
    """O menor prefixo que o provedor guarda. 1.024 na OpenAI; no Claude, o Opus 5 e o 5.5 guardaram o sistema de
    1.542 tokens em 23/09 (cache_leitura > 0). O Haiku 4.5 pede 4.096 (plano da v3.1, Review Focus 4)."""
    return 4096 if modelo.startswith("claude-haiku-4-5") else 1024


def _custo(u: modelos.Uso) -> dict:
    """Os tokens e o preço de um `Uso`. Sem preço no catálogo, US$ e R$ ficam None — nunca 0, que seria grátis."""
    conhecido = u.preco_conhecido
    return {"chamadas": u.chamadas, "entrada": u.entrada, "cache_escrita": u.cache_escrita,
            "cache_leitura": u.cache_leitura, "saida": u.saida,
            "usd": round(u.usd, 4) if conhecido else None, "brl": round(u.brl, 3) if conhecido else None}


def custo_estimado(chamadas: list[list[tuple]], modelo: str, saida_por_chamada: int = SAIDA_POR_LOTE) -> dict:
    """A fórmula da estimativa: o cache simulado (`simular_cache`) com a regra do provedor do modelo, a saída da
    hipótese em cada chamada, e o preço do `modelos.py` — o próprio `Uso.usd` da execução real."""
    partes = simular_cache(chamadas, provedor_do_modelo(modelo), minimo_cache(modelo))
    return _custo(modelos.Uso(
        entrada=sum(p["entrada"] for p in partes), cache_escrita=sum(p["cache_escrita"] for p in partes),
        cache_leitura=sum(p["cache_leitura"] for p in partes), saida=saida_por_chamada * len(chamadas),
        chamadas=len(chamadas), modelo=modelo))


def contador(provedor: str, enc=None):
    """`tokens(texto)` do provedor. `enc` é o o200k_base do tiktoken; sem ele, caracteres/4 — aproximação declarada
    (no texto destes editais o o200k dá 3,7 a 4,0 caracteres por token). No Claude, × FATOR_TOKENS_CLAUDE."""
    @functools.lru_cache(maxsize=None)
    def base(texto: str) -> int:
        if enc is None:
            return math.ceil(len(texto) / 4)
        return len(enc.encode(texto, disallowed_special=()))

    if provedor == "claude":
        return lambda texto: round(FATOR_TOKENS_CLAUDE * base(texto))
    return base


def tokenizador():
    """`(enc, descrição)`: o o200k_base, como o 27_orcamento_openai.py; sem tiktoken, `(None, ...)` → caracteres/4."""
    try:
        import tiktoken
        return tiktoken.get_encoding("o200k_base"), "o200k_base (tiktoken, como o 27_orcamento_openai.py)"
    except Exception:                                                  # noqa: BLE001 — sem pacote ou sem o arquivo
        return None, "caracteres/4 (tiktoken indisponível — aproximação)"


def estimar_execucao(paginas: list, licitacao: str, modelo: str, ordem: str, melhor_de_n: int, contar,
                     rodadas: int = REFORCO_RODADAS) -> dict:
    """`{"modo", "uso"}` de uma execução, sem chamar modelo."""
    modo, chamadas = chamadas_da_execucao(paginas, licitacao, ordem, melhor_de_n, rodadas=rodadas)
    return {"modo": modo, "uso": custo_estimado([blocos_da_chamada(s, u, contar) for s, u in chamadas], modelo)}


# ------------------------------------------------------------------ o teto e a execução medida
def cabe_no_teto(gasto_brl: float, estimativa_brl: float | None, teto_brl: float) -> bool:
    """A próxima execução só roda se o gasto medido + a estimativa dela não passar do teto. Sem estimativa (modelo
    sem preço), não roda."""
    return estimativa_brl is not None and gasto_brl + estimativa_brl <= teto_brl


def _brl_de(registro: dict | None):
    return ((registro or {}).get("uso") or {}).get("brl")


def rodar(plano: list[dict], estimativas: list[dict], teto_brl: float, medir_um, depois_de_cada=None):
    """Roda o plano em ordem, com o teto conferido antes de cada execução. Devolve `(registros, gasto, parada)`;
    `parada` diz por que parou antes do fim (None se foi até o fim)."""
    registros: list[dict] = []
    gasto = 0.0
    for i, (item, est) in enumerate(zip(plano, estimativas), 1):
        previsto = _brl_de(est)
        rotulo_item = "%s · %s · %s" % (rotulo(item["licitacao"]), item["modelo"], item["config"])
        if not cabe_no_teto(gasto, previsto, teto_brl):
            parada = ("teto: gasto medido R$ %s + estimativa R$ %s de %s passaria de R$ %s — parei antes dela; "
                      "%d execução(ões) não rodaram" % (_decimal(gasto), _decimal(previsto), rotulo_item,
                                                        _decimal(teto_brl), len(plano) - i + 1))
            print("\n  PAROU — %s" % parada, flush=True)
            return registros, gasto, parada
        print("\n  [%d/%d] %s   (estimativa R$ %s · gasto até aqui R$ %s)"
              % (i, len(plano), rotulo_item, _decimal(previsto), _decimal(gasto)), flush=True)
        try:
            reg = medir_um(item, est)
        except Exception as e:                                         # noqa: BLE001 — registra e segue
            reg = {"licitacao": item["licitacao"], "modelo": item["modelo"], "provedor": item["provedor"],
                   "config": item["config"], "ordem": item["ordem"], "melhor_de_n": item["melhor_de_n"],
                   "erro": str(e), "uso": None, "acuracia": None, "estimativa_brl": previsto}
            print("     FALHOU: %s   (conta a estimativa no gasto)" % str(e)[:200], flush=True)
        medido = _brl_de(reg)
        gasto += medido if medido is not None else (previsto or 0.0)
        registros.append(reg)
        if depois_de_cada:
            depois_de_cada(registros, gasto)
    return registros, gasto, None


def medir(item: dict, lic: dict, provedor, avaliar, saidas_dir: str, estimativa: dict) -> dict:
    """Uma execução paga: extrair → verificar → acurácia → auditoria.json. Devolve o registro da execução."""
    t0 = time.time()
    ext = extrator.extrair(lic["pasta"], provedor, modelo=item["modelo"], lote=LOTE, k_rag=K_RAG, effort=EFFORT,
                           paginas_prontas=lic["paginas"], ordem=item["ordem"], melhor_de_n=item["melhor_de_n"],
                           modalidade=lic["modalidade"])
    rel = verificador.verificar(ext, modalidade=lic["modalidade"])
    segundos = time.time() - t0
    obs = lic.get("observadas")
    if obs is not None:              # o OCR foi observado uma vez, ao carregar as páginas; cada auditoria o registra
        ext.condicoes.arquivos_ocr = list(obs.arquivos_ocr)
        ext.condicoes.paginas_ocr = obs.paginas_ocr
        ext.condicoes.furtivos = list(obs.furtivos)
    caminho = saida.escrever_json(ext, rel, destino(saidas_dir, item["licitacao"], item["modelo"], item["config"]))
    u = ext.uso
    return {
        "licitacao": item["licitacao"], "modelo": item["modelo"], "provedor": item["provedor"],
        "config": item["config"], "ordem": item["ordem"], "melhor_de_n": item["melhor_de_n"],
        "modalidade": lic["modalidade"], "modo": ext.modo,
        "acuracia": (agregar_acuracia({r.id: r.resposta for r in ext.respostas}, lic["gabarito"], avaliar)
                     if lic.get("gabarito") else None),
        "verificacao": {"aprovadas": rel.aprovadas, "revisar": rel.revisar, "reprovadas": rel.reprovadas,
                        "nao_localizado": rel.nao_localizado, "taxa_ancorada": round(rel.taxa_ancorada, 4)},
        "uso": dict(_custo(u), raciocinio=u.raciocinio, segundos_modelo=round(u.segundos, 1)),
        "reforco": resumo_reforco(ext.melhor_de_n),
        "melhor_de_n_registro": ext.melhor_de_n,
        "segundos": round(segundos, 1),
        "estimativa_brl": _brl_de(estimativa),
        "auditoria": os.path.relpath(caminho, saidas_dir),
        "erro": None,
    }


# ------------------------------------------------------------------ comparação e tabelas
def diferenca_pct(antes: float | None, depois: float | None) -> float | None:
    if not antes or depois is None:
        return None
    return (depois - antes) / antes * 100.0


def comparar(registros: list[dict]) -> list[dict]:
    """Antes × depois lado a lado, por licitação e modelo, na ordem em que aparecem."""
    pares: dict[tuple, dict] = {}
    for r in registros:
        pares.setdefault((r["licitacao"], r["modelo"]), {})[r["config"]] = r
    linhas = []
    for (lic, modelo), p in pares.items():
        a, d = p.get("antes"), p.get("depois")
        if a is None or d is None:
            continue
        aa, ad = a.get("acuracia") or {}, d.get("acuracia") or {}
        linhas.append({
            "licitacao": lic, "modelo": modelo,
            "brl_antes": _brl_de(a), "brl_depois": _brl_de(d), "custo_pct": diferenca_pct(_brl_de(a), _brl_de(d)),
            "acertos_antes": aa.get("acertos"), "acertos_depois": ad.get("acertos"),
            "total": aa.get("total") or ad.get("total"),
            "acuracia_delta": (ad["acertos"] - aa["acertos"]
                               if aa.get("acertos") is not None and ad.get("acertos") is not None else None),
            "criticas_antes": aa.get("criticas_acertos"), "criticas_depois": ad.get("criticas_acertos"),
            "criticas_total": aa.get("criticas_total") or ad.get("criticas_total")})
    return linhas


def rotulo(licitacao: str) -> str:
    """"ABERTO Concorrencia - Eletronica - Pirapo-RS" → "Pirapo-RS": o trecho Município-UF do nome da pasta."""
    for parte in licitacao.split(" - "):
        if re.search(r"-[A-Z]{2}$", parte.strip()):
            return parte.strip()
    return licitacao


def _milhar(n) -> str:
    return "—" if n is None else f"{int(n):,}".replace(",", ".")


def _decimal(v, casas: int = 2) -> str:
    return "—" if v is None else ("%.*f" % (casas, v)).replace(".", ",")


def _pct(v) -> str:
    if v is None:
        return "—"
    return "0,0%" if abs(v) < 0.05 else ("%+.1f%%" % v).replace(".", ",")


def _delta(n) -> str:
    return "—" if n is None else ("%+d" % n if n else "0")


def _fracao(a, b) -> str:
    return "—" if a is None or b is None else "%d/%d" % (a, b)


def _linha(celulas) -> str:
    return "| " + " | ".join(str(c) for c in celulas) + " |"


def tabela_comparacao(linhas: list[dict]) -> str:
    out = [_linha(["licitação", "modelo", "R$ antes", "R$ depois", "Δ custo", "acurácia antes", "acurácia depois",
                   "Δ acurácia", "críticas antes → depois"]), _linha(["---"] * 9)]
    for l in linhas:
        crit = ("—" if l["criticas_antes"] is None and l["criticas_depois"] is None else "%s → %s" % (
            _fracao(l["criticas_antes"], l["criticas_total"]), _fracao(l["criticas_depois"], l["criticas_total"])))
        out.append(_linha([rotulo(l["licitacao"]), l["modelo"], _decimal(l["brl_antes"]), _decimal(l["brl_depois"]),
                           _pct(l["custo_pct"]), _fracao(l["acertos_antes"], l["total"]),
                           _fracao(l["acertos_depois"], l["total"]), _delta(l["acuracia_delta"]), crit]))
    return "\n".join(out)


_TOKENS = ("chamadas", "entrada", "cache_escrita", "cache_leitura", "saida")


def tabela_estimativas(estimativas: list[dict]) -> str:
    out = [_linha(["licitação", "modelo", "config", "modo", "chamadas", "entrada", "cache gravado", "cache lido",
                   "saída (hip.)", "US$", "R$"]), _linha(["---"] * 11)]
    soma = dict.fromkeys(_TOKENS, 0)
    usd = brl = 0.0
    for e in estimativas:
        u = e["uso"]
        out.append(_linha([rotulo(e["licitacao"]), e["modelo"], e["config"], e["modo"], u["chamadas"],
                           _milhar(u["entrada"]), _milhar(u["cache_escrita"]), _milhar(u["cache_leitura"]),
                           _milhar(u["saida"]), _decimal(u["usd"], 4), _decimal(u["brl"])]))
        for k in _TOKENS:
            soma[k] += u[k]
        usd += u["usd"] or 0.0
        brl += u["brl"] or 0.0
    out.append("| **total** | | | | %d | %s | %s | %s | %s | %s | **%s** |" % (
        soma["chamadas"], _milhar(soma["entrada"]), _milhar(soma["cache_escrita"]), _milhar(soma["cache_leitura"]),
        _milhar(soma["saida"]), _decimal(usd, 4), _decimal(brl)))
    return "\n".join(out)


def tabela_execucoes(registros: list[dict]) -> str:
    colunas = ["licitação", "modelo", "config", "modo", "acurácia", "críticas", "completude",
               "aprov. · rev. · repr.", "não loc.", "reforço", "chamadas", "entrada", "cache gravado", "cache lido",
               "saída", "R$", "R$ estimado", "tempo"]
    out = [_linha(colunas), _linha(["---"] * len(colunas))]
    for r in registros:
        base = [rotulo(r["licitacao"]), r["modelo"], r["config"]]
        if r.get("erro"):
            out.append(_linha(base + ["FALHOU: %s" % r["erro"][:80].replace("|", "/")]
                              + ["—"] * (len(colunas) - 6) + [_decimal(r.get("estimativa_brl")), "—"]))
            continue
        a, v, u, f = r.get("acuracia") or {}, r["verificacao"], r["uso"], r["reforco"]
        reforco = ("—" if r["melhor_de_n"] <= 1 else "%d rodada(s) · %d de %d recuperada(s)"
                   % (f["rodadas"], f["recuperadas"], f["reforcadas"]))
        out.append(_linha(base + [
            r["modo"], _fracao(a.get("acertos"), a.get("total")),
            _fracao(a.get("criticas_acertos"), a.get("criticas_total")),
            _fracao(a.get("desejaveis"), a.get("desejaveis_total")),
            "%d · %d · %d" % (v["aprovadas"], v["revisar"], v["reprovadas"]), v["nao_localizado"], reforco,
            u["chamadas"], _milhar(u["entrada"]), _milhar(u["cache_escrita"]), _milhar(u["cache_leitura"]),
            _milhar(u["saida"]), _decimal(u["brl"]), _decimal(r.get("estimativa_brl")), "%.0fs" % r["segundos"]]))
    return "\n".join(out)


# ------------------------------------------------------------------ main
def barra(t: str) -> None:
    print("\n" + "=" * 110 + "\n  %s\n" % t + "=" * 110)


def _acuracia_mod():
    """`15_acuracia.py` começa com dígito: não dá para importar pelo nome (como no 34_placar.py)."""
    spec = importlib.util.spec_from_file_location("acuracia", os.path.join(AQUI, "15_acuracia.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _gravar_json(caminho: str, dados: dict) -> None:
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with io.open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)


def _gravar_texto(caminho: str, texto: str) -> None:
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with io.open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)


def _hipoteses() -> dict:
    return {"saida_por_chamada": SAIDA_POR_LOTE, "reforco_perguntas": list(REFORCO_PERGUNTAS),
            "reforco_rodadas": REFORCO_RODADAS, "fator_tokens_claude": FATOR_TOKENS_CLAUDE,
            "cache_escrita": modelos.CACHE_ESCRITA, "cache_leitura": modelos.CACHE_LEITURA}


def _argumentos(argv):
    ap = argparse.ArgumentParser(description="Antes × depois da v3.1: licitações com gabarito × modelos × configs")
    ap.add_argument("--seco", action="store_true", help="só estima: NENHUMA chamada de modelo")
    ap.add_argument("--licitacoes", nargs="+", metavar="PASTA",
                    help="pastas das licitações (caminho absoluto ou nome em amostras/); "
                         "padrão: as de amostras/ com _gabarito.json")
    ap.add_argument("--modelos", nargs="+", default=list(MODELOS_PADRAO))
    ap.add_argument("--teto-brl", type=float, default=TETO_BRL_PADRAO,
                    help="gasto máximo em R$ (medido pelo ext.uso + a estimativa da próxima execução)")
    ap.add_argument("--configs", nargs="+", choices=list(CONFIGURACOES), default=list(CONFIGURACOES))
    ap.add_argument("--saidas", default=os.path.join(SAIDAS, "_antes_depois"))
    return ap.parse_args(argv)


def main(argv=None) -> int:
    a = _argumentos(argv)
    pastas = ([p if os.path.isabs(p) else os.path.join(AMOSTRAS, p) for p in a.licitacoes]
              if a.licitacoes else licitacoes_padrao())
    if not pastas:
        print("nenhuma licitação com _gabarito.json em %s" % AMOSTRAS)
        return 2
    faltam = [p for p in pastas if not os.path.isdir(p)]
    if faltam:
        print("pasta não encontrada: %s" % "; ".join(faltam))
        return 2
    try:
        plano = matriz(pastas, a.modelos, list(dict.fromkeys(a.configs)))
    except ValueError as e:
        print(e)
        return 2

    barra("ANTES × DEPOIS DA v3.1 — %s" % ("ESTIMATIVA (--seco: nenhuma chamada de modelo)" if a.seco
                                            else "MEDIÇÃO (chamadas pagas)"))
    for c in dict.fromkeys(a.configs):
        print("  %-10s %s, N=%d" % (c, CONFIGURACOES[c]["ordem"], CONFIGURACOES[c]["melhor_de_n"]))
    print("  modelos .. %s" % ", ".join(a.modelos))
    print("  teto ..... R$ %s — gasto medido (ext.uso) + a estimativa da próxima execução" % _decimal(a.teto_brl))
    print("  câmbio ... US$ 1 = R$ %s (modelos.USD_BRL)" % _decimal(modelos.USD_BRL))
    print("  saídas ... %s" % a.saidas)

    # 1. as páginas, uma vez por licitação (OCR local, sem custo), reaproveitadas em todas as execuções dela
    print("\n  páginas (lidas uma vez por licitação)")
    lics: dict[str, dict] = {}
    for pasta in dict.fromkeys(pastas):
        nome = os.path.basename(pasta.rstrip("\\/"))
        t0 = time.time()
        obs = cond.Condicoes()
        paginas = extrator.carregar_paginas(pasta, observador=obs)
        if not paginas:
            print("    %-14s nenhuma página legível — os PDFs estão aí? (o worktree não tem os PDFs, gitignorados)"
                  % rotulo(nome))
            continue
        gab, gabarito = os.path.join(pasta, "_gabarito.json"), None
        if os.path.isfile(gab):
            with io.open(gab, encoding="utf-8") as f:
                gabarito = json.load(f).get("perguntas")
        lics[pasta] = {"pasta": pasta, "nome": nome, "paginas": paginas, "modalidade": modalidade_da_pasta(pasta),
                       "gabarito": gabarito, "observadas": obs}
        print("    %-14s %3d páginas de %d arquivo(s) · %s · %s%s%s  (%.0fs)"
              % (rotulo(nome), len(paginas), len({p.arquivo for p in paginas}), rec.escolher_modo(paginas),
                 lics[pasta]["modalidade"], " · OCR em %d arquivo(s)" % len(obs.arquivos_ocr)
                 if obs.arquivos_ocr else "", "" if gabarito else " · SEM GABARITO", time.time() - t0))
    plano = [p for p in plano if p["pasta"] in lics]
    if not plano:
        return 2

    # 2. a estimativa de cada execução — é ela que o teto confere antes de cada chamada paga
    enc, desc_tok = tokenizador()
    contadores = {p: contador(p, enc) for p in ("claude", "openai")}

    def estimar(item, rodadas=REFORCO_RODADAS):
        lic = lics[item["pasta"]]
        return dict(licitacao=item["licitacao"], modelo=item["modelo"], config=item["config"],
                    **estimar_execucao(lic["paginas"], lic["nome"], item["modelo"], item["ordem"],
                                       item["melhor_de_n"], contadores[item["provedor"]], rodadas=rodadas))

    estimativas = [estimar(i) for i in plano]
    total = sum(_brl_de(e) or 0.0 for e in estimativas)
    # pior caso do reforço: as N-1 rodadas inteiras, onde isso passa da hipótese
    pior = sum(_brl_de(estimar(i, rodadas=i["melhor_de_n"] - 1) if i["melhor_de_n"] - 1 > REFORCO_RODADAS
                       else e) or 0.0 for i, e in zip(plano, estimativas))
    sem_preco = sorted({e["modelo"] for e in estimativas if _brl_de(e) is None})

    barra("ESTIMATIVA POR EXECUÇÃO")
    md_est = tabela_estimativas(estimativas)
    comp_est = tabela_comparacao(comparar(estimativas))
    print(md_est + "\n\n  antes × depois (estimado)\n\n" + comp_est)
    print("\n  HIPÓTESES (o que não se mede antes de gastar)")
    print("    tokens ..... %s + o esquema do structured output" % desc_tok)
    if enc is not None:
        print("                 (bateu a entrada medida do GPT em 23/09 nestas licitações: erro abaixo de 0,1%)")
    print("                 Claude = %s × isso (medido nas mesmas licitações, claude-opus-5-5 de 23/09)"
          % _decimal(FATOR_TOKENS_CLAUDE))
    print("    saída ...... %s tokens por chamada (medido em 23/09: Opus 5.5 ~2.900, gpt-5.6-sol ~4.000 por lote)"
          % _milhar(SAIDA_POR_LOTE))
    print("    reforço .... %d lote extra pequeno por \"depois\" (%s)"
          % (REFORCO_RODADAS, ", ".join(REFORCO_PERGUNTAS)))
    print("    cache ...... prefixo idêntico e dentro dos 5 min (as chamadas de uma execução são seguidas); Claude:")
    print("                 sistema sempre, documentos na ordem nova (cache_control); OpenAI: automático, o que não")
    print("                 é lido é gravado (fatura de 23/09). Gravação %s× e leitura %s× da entrada (modelos.py)"
          % (_decimal(modelos.CACHE_ESCRITA), _decimal(modelos.CACHE_LEITURA)))
    print("    pior caso .. ausência real (ex.: a Q15 e a Q16 de Pirapó, \"Não localizado\" no gabarito) nunca")
    print("                 ancora: o reforço usa as N-1 rodadas inteiras → total R$ %s (+R$ %s)"
          % (_decimal(pior), _decimal(pior - total)))
    if sem_preco:
        print("\n  SEM PREÇO no catálogo (modelos.PRECOS): %s — a estimativa não sai e o teto não protege"
              % ", ".join(sem_preco))
    print("\n  TOTAL ESTIMADO: R$ %s em %d execuções — %s de R$ %s"
          % (_decimal(total), len(estimativas), "cabe no teto" if total <= a.teto_brl else "PASSA DO TETO",
             _decimal(a.teto_brl)))

    os.makedirs(a.saidas, exist_ok=True)
    _gravar_json(os.path.join(a.saidas, "estimativa.json"), {
        "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"), "usd_brl": modelos.USD_BRL, "tokenizador": desc_tok,
        "hipoteses": _hipoteses(), "teto_brl": a.teto_brl, "execucoes": estimativas,
        "total_brl": round(total, 3), "pior_caso_brl": round(pior, 3)})
    _gravar_texto(os.path.join(a.saidas, "estimativa.md"),
                  "# Antes × depois da v3.1 — estimativa (%s)\n\n%s\n\n## Antes × depois (estimado)\n\n%s\n\n"
                  "Total estimado: **R$ %s** (pior caso do reforço: R$ %s). Tokens: %s.\n"
                  % (time.strftime("%d/%m/%Y %H:%M"), md_est, comp_est, _decimal(total), _decimal(pior), desc_tok))
    print("  estimativa gravada em %s" % os.path.join(a.saidas, "estimativa.json"))

    if a.seco:
        print("\n  (--seco: nada executado)")
        return 0

    # 3. a medição — chamadas pagas, com o teto conferido antes de cada uma
    if sem_preco:
        print("\n  não rodo: sem preço, o teto não protegeria nada.")
        return 2
    try:
        provedores = {p: modelos.obter_provedor(provedor=p) for p in dict.fromkeys(i["provedor"] for i in plano)}
    except modelos.ErroModelo as e:
        print("\n  %s" % e)
        return 3
    avaliar = _acuracia_mod().avaliar

    def medir_um(item, est):
        reg = medir(item, lics[item["pasta"]], provedores[item["provedor"]], avaliar, a.saidas, est)
        ac, v, u, f = reg["acuracia"] or {}, reg["verificacao"], reg["uso"], reg["reforco"]
        print("     acurácia %s (críticas %s) · %d aprov. · %d rev. · %d repr. · reforço %d rodada(s), "
              "%d recuperada(s)"
              % (_fracao(ac.get("acertos"), ac.get("total")),
                 _fracao(ac.get("criticas_acertos"), ac.get("criticas_total")),
                 v["aprovadas"], v["revisar"], v["reprovadas"], f["rodadas"], f["recuperadas"]))
        print("     entrada %s · cache gravado %s · lido %s · saída %s · R$ %s (estimado R$ %s) · %.0fs"
              % (_milhar(u["entrada"]), _milhar(u["cache_escrita"]), _milhar(u["cache_leitura"]),
                 _milhar(u["saida"]), _decimal(u["brl"]), _decimal(reg["estimativa_brl"]), reg["segundos"]),
              flush=True)
        return reg

    def gravar(registros, gasto, parada=None):
        _gravar_json(os.path.join(a.saidas, "resultado.json"), {
            "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"), "usd_brl": modelos.USD_BRL, "teto_brl": a.teto_brl,
            "configuracoes": CONFIGURACOES, "gasto_brl": round(gasto, 3), "parada": parada,
            "execucoes": registros, "comparacao": comparar(registros)})
        _gravar_texto(os.path.join(a.saidas, "resultado.md"),
                      "# Antes × depois da v3.1 — medição (%s)\n\n"
                      "antes = perguntas-primeiro, N=1 · depois = documentos-primeiro, N=3 · effort %s · "
                      "US$ 1 = R$ %s\n\n## Antes × depois\n\n%s\n\n## Execuções\n\n%s\n\n"
                      "Gasto medido (ext.uso): **R$ %s** de um teto de R$ %s.%s\n"
                      % (time.strftime("%d/%m/%Y %H:%M"), EFFORT, _decimal(modelos.USD_BRL),
                         tabela_comparacao(comparar(registros)), tabela_execucoes(registros), _decimal(gasto),
                         _decimal(a.teto_brl), "\n\n**Parou antes do fim** — %s." % parada if parada else ""))

    barra("MEDIÇÃO")
    registros, gasto, parada = rodar(plano, estimativas, a.teto_brl, medir_um, depois_de_cada=gravar)
    gravar(registros, gasto, parada)

    barra("RESULTADO")
    print(tabela_comparacao(comparar(registros)) + "\n\n" + tabela_execucoes(registros))
    print("\n  gasto medido (ext.uso): R$ %s de um teto de R$ %s%s"
          % (_decimal(gasto), _decimal(a.teto_brl), " — PAROU: %s" % parada if parada else ""))
    print("  resultado em %s (e resultado.md)" % os.path.join(a.saidas, "resultado.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
