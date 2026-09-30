# -*- coding: utf-8 -*-
"""
Reverifica extrações já salvas — SEM chamar o modelo.

As respostas do extrator estão em `saidas/<licitação>/auditoria.json`. As páginas
são recarregadas localmente (OCR é local e gratuito). Com as duas coisas, o
Verificador roda de novo do zero.

Por que isto importa além da economia: o Verificador é determinístico, então
reverificar é reprodutível. Quando uma regra de verificação muda — como a correção
do reconhecedor de "não localizado" — dá para medir o efeito da mudança sobre todo
o histórico, sem gastar um token e sem a variância da geração poluir a comparação.

    python 13_reverificar.py              todas as saídas
    python 13_reverificar.py --so ABERTO  só as que começam com isso
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import inventario, pncp
from fopa import extrator, metadados, pagina, saida, verificador   # noqa: E402
from fopa import condicoes as cond                                 # noqa: E402
from fopa.modelos import Uso                                 # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")


def reconstruir(dados: dict, pasta: str) -> extrator.Extracao:
    """Remonta a Extracao a partir do JSON salvo + páginas relidas do disco."""
    # As condicoes sobre OS ARQUIVOS (OCR, texto furtivo, documento nao lido)
    # sao re-observadas agora, no mesmo passe que rele as paginas: sao fatos do
    # disco, e o disco pode ter mudado. As condicoes sobre A EXECUCAO
    # (provedor, modelo, effort) so existem no JSON salvo e vem de la.
    c = cond.Condicoes()
    paginas = extrator.carregar_paginas(pasta, observador=c)
    u = dados.get("uso", {})
    uso = Uso(entrada=u.get("entrada", 0), saida=u.get("saida", 0),
              cache_leitura=u.get("cache_leitura", 0), chamadas=u.get("chamadas", 0),
              segundos=u.get("segundos", 0.0), modelo=u.get("modelo", ""))
    respostas = []
    for r in dados.get("respostas", []):
        respostas.append(extrator.Resposta(
            id=r["id"], pergunta=r.get("pergunta", ""),
            resposta=r.get("resposta", ""), arquivo=r.get("arquivo"),
            pagina=r.get("pagina"), trecho_literal=r.get("trecho_literal"),
            conflito=r.get("conflito"), confianca=r.get("confianca", "media"),
            # sem isto, o rastro da correcao de pagina se perde a cada releitura
            pagina_citada=r.get("pagina_citada")))
    respostas.sort(key=lambda r: int(r.id[1:]))
    # A PROCEDENCIA SOBREVIVE A REVERIFICACAO.
    #
    # `provedor`, `effort` e as `condicoes` nao eram remontados, e o
    # `escrever_json` grava o que a Extracao tem: toda reverificacao apagava
    # quem gerou a resposta e sob que condicoes. Em 23/09/2026 isso zerou o
    # `provedor: claude-code` de extracoes feitas por agente -- que passaram a
    # parecer execucoes sem origem -- e, nas da API, apagou OCR, texto furtivo
    # e documento faltando. Reverificar muda o veredito; nunca a origem.
    return extrator.Extracao(
        licitacao=dados.get("licitacao", os.path.basename(pasta)),
        respostas=respostas, paginas=paginas,
        modo=dados.get("modo", ""), uso=uso,
        arquivos=dados.get("arquivos", sorted({p.arquivo for p in paginas})),
        provedor=u.get("provedor", ""), effort=u.get("effort", ""),
        condicoes=_condicoes(c, dados, pasta, paginas, respostas))


def _condicoes(c: cond.Condicoes, dados: dict, pasta: str, paginas, respostas):
    """Completa as condicoes re-observadas com o que so o JSON salvo sabe."""
    salvo = dados.get("condicoes") or {}
    mod = salvo.get("modelo") or {}
    u = dados.get("uso", {})
    esperados = cond.documentos_esperados(pasta)
    c.esperados = len(esperados)
    c.obtidos = len({p.arquivo for p in paginas})
    c.faltando = cond.nao_lidos(esperados, {p.arquivo for p in paginas})
    c.provedor = mod.get("provedor") or u.get("provedor", "")
    c.modelo = mod.get("modelo") or u.get("modelo", "")
    c.effort = mod.get("effort") or u.get("effort", "")
    c.secundario = bool(mod.get("secundario"))
    c.corpus_horas = salvo.get("corpus_horas")
    c.abstencoes = [r.id for r in respostas
                    if (r.resposta or "").strip().lower().startswith("não localizado")]
    return c


def itens_da_api(nome: str, pasta: str) -> list[dict] | None:
    """
    Os itens da licitacao, do cache em disco ou da API.

    O cache e o `_itens_api.json` ao lado do inventario. A reverificacao roda
    varias vezes por dia e a API do PNCP ja provou cair; consultar toda vez
    trocaria uma regra barata por uma dependencia de rede.
    """
    cache = os.path.join(pasta, "_itens_api.json")
    if os.path.isfile(cache):
        try:
            return json.load(io.open(cache, encoding="utf-8"))
        except (ValueError, OSError):
            pass
    inv = os.path.join(pasta, "_inventario.json")
    if not os.path.isfile(inv):
        return None
    try:
        # apelido resolvido em `fopa/inventario.py` — ver 52_prazo_ao_vivo
        d = inventario.ler(os.path.dirname(inv)) or {}
        ctrl = d.get("controle")
        if not ctrl:
            return None
        itens = pncp._get(pncp.Licitacao.de_controle(ctrl)._u("/itens"))
    except Exception:                                  # noqa: BLE001
        return None
    try:
        io.open(cache, "w", encoding="utf-8").write(
            json.dumps(itens, ensure_ascii=False))
    except OSError:
        pass
    return itens


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", default=None)
    ap.add_argument("--modelo", default=None, help="só reverifica extrações deste modelo")
    a = ap.parse_args()

    alvos = []
    for n in sorted(os.listdir(SAIDAS)) if os.path.isdir(SAIDAS) else []:
        d = os.path.join(SAIDAS, n)
        j = os.path.join(d, "auditoria.json")
        if not os.path.isfile(j):
            continue
        if a.so and not n.startswith(a.so):
            continue
        alvos.append((n, j))

    print("=" * 100)
    print("  REVERIFICAÇÃO — %d extração(ões) · sem chamar o modelo" % len(alvos))
    print("=" * 100)
    print("%-46s %-14s %-14s %s" % ("licitação", "antes", "depois", "mudança"))
    print("-" * 100)

    totais = dict(anc_a=0, resp_a=0, anc_d=0, resp_d=0, repr_a=0, repr_d=0)
    for nome, jpath in alvos:
        dados = json.load(open(jpath, encoding="utf-8"))
        pasta = os.path.join(AMOSTRAS, nome)
        if not os.path.isdir(pasta):
            # O NOME DA SAÍDA NÃO É O NOME DA ORIGEM, e o auditoria sabe disso.
            #
            # As execuções de comparação ficam em pastas com rótulo próprio
            # (`_openai_bertioga`, `_openai_pirapo`), porque o ponto delas é
            # separar duas rodadas da MESMA licitação. Resolver a origem pelo
            # nome da pasta falhava nessas duas, e a linha "(pasta de origem
            # não encontrada)" saía em toda execução.
            #
            # Ruído recorrente é pior que ruído único: ensina o operador a
            # passar o olho pela saída sem ler. E aqui custava caro — as duas
            # ignoradas eram justamente as extrações do GPT, as únicas que não
            # estavam sendo reverificadas contra as regras novas.
            #
            # O campo `licitacao` do auditoria guarda a pasta de origem.
            alt = (dados.get("licitacao") or "").strip()
            if alt and os.path.isdir(os.path.join(AMOSTRAS, alt)):
                pasta = os.path.join(AMOSTRAS, alt)
        if not os.path.isdir(pasta):
            print("%-46s  (pasta de origem não encontrada)" % nome[:46])
            continue
        v = dados.get("verificacao", {})
        antes = "%d/%d · %dR" % (
            int(round(v.get("taxa_ancorada", 0) * (17 - v.get("nao_localizado", 0)))),
            17 - v.get("nao_localizado", 0), v.get("reprovadas", 0))

        try:
            ext = reconstruir(dados, pasta)
        except Exception as e:                                  # noqa: BLE001
            # uma pasta ilegivel nao derruba a reverificacao das outras 80
            print("%-46s  (falhou ao reler: %s)" % (nome[:46], str(e)[:60]))
            continue
        # ITENS DA API -- sem eles a `verificar_contra_api` nao roda.
        #
        # Ela existia desde o inicio, documentada como "custa zero e tem alto
        # poder de deteccao", e NENHUM dos nove chamadores de `verificar()`
        # passava `itens_api`. Era codigo morto: nem o alto poder de deteccao
        # nem o bug de sinonimo que ela tinha chegaram a acontecer.
        #
        # Aqui e o lugar certo para ligar: o 13_reverificar ja e o script que
        # roda sem modelo, sobre o que esta no disco. A consulta e cacheada por
        # licitacao no proprio disco, para nao bater na API a cada reverificacao.
        rel = verificador.verificar(ext, itens_api=itens_da_api(nome, pasta))
        depois = "%d/%d · %dR" % (rel.ancoradas, rel.respondidas, rel.reprovadas)

        destino = os.path.join(SAIDAS, nome)
        saida.escrever_json(ext, rel, os.path.join(destino, "auditoria.json"))
        # chaves que o `escrever_json` nao conhece (ex.: o bloco `agente` do
        # 70_extracao_por_agente.py) voltam como estavam
        extras = {k: v for k, v in dados.items()
                  if k not in json.load(open(jpath, encoding="utf-8"))}
        if extras:
            novo = json.load(open(jpath, encoding="utf-8"))
            novo.update(extras)
            with open(jpath, "w", encoding="utf-8") as f:
                json.dump(novo, f, ensure_ascii=False, indent=1)
        saida.escrever_nota(ext, rel, os.path.join(destino, "%s.md" % nome))
        try:
            saida.escrever_xlsx(ext, rel, os.path.join(destino, "%s.xlsx" % nome))
        except RuntimeError:
            pass
        metadados.atualizar(pasta, ext, rel)
        pagina.escrever(ext, rel, os.path.join(pasta, "RELATORIO.html"))

        d_repr = rel.reprovadas - v.get("reprovadas", 0)
        marca = "" if d_repr == 0 else ("%+d reprovadas" % d_repr)
        print("%-46s %-14s %-14s %s" % (nome[:46], antes, depois, marca))

        totais["anc_d"] += rel.ancoradas
        totais["resp_d"] += rel.respondidas
        totais["repr_a"] += v.get("reprovadas", 0)
        totais["repr_d"] += rel.reprovadas

    print("-" * 100)
    if totais["resp_d"]:
        print("  ancoragem agora ... %d/%d (%.1f%%)"
              % (totais["anc_d"], totais["resp_d"],
                 100.0 * totais["anc_d"] / totais["resp_d"]))
        print("  reprovadas ........ %d (antes: %d)" % (totais["repr_d"], totais["repr_a"]))
    print("  custo em API ...... R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
