# -*- coding: utf-8 -*-
"""
O Jev (TypeSafe) na v3: o worker MONTA a pergunta e INTERPRETA a resposta; o
n8n faz a chamada, com a credencial dele (segredo só em Credential, e o nó
aparece no canvas). Ver Fopa-v2/11-Produto-v3/Jev na v3.md.

Os critérios não são reescritos aqui: vêm dos scripts que os MEDIRAM —
`63_jev_escopo.CRITERIOS['v3']` (o v1 errou Águas de Chapecó com 71%; o v2
errava 9 folhas reais do acervo com p <= 0,25; o v3 zera esses erros — 67_), o v3.1 de `77_jev_credenciamento.V31`
(o v3 + o credenciamento, 25/09) e `64_jev_ancoragem.PERGUNTA/CRITERIOS` (a prova adversarial:
data trocada -> contradiz 1,00). Trocar o texto é trocar o experimento.

A LINHA: nada daqui escreve veredito, confiança ou escopo (T25). A saída é um
sinal, e o sinal com convicção vira candidata para olho humano.
"""
from __future__ import annotations

import importlib.util
import json
import os

from fopa import jev as cliente

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")


def _script(nome: str):
    spec = importlib.util.spec_from_file_location("_jev_" + nome.split("_")[0], os.path.join(_SCRIPTS, nome))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_63 = _script("63_jev_escopo.py")
_64 = _script("64_jev_ancoragem.py")
_73 = _script("73_jev_escopo_rag.py")
_77 = _script("77_jev_credenciamento.py")

# 67_: v2 errava folha de livro-texto; v3 AUC 0,968. 77_ (25/09): v3.1 = o v3 + o CREDENCIAMENTO, o ponto cego medido
# (folhas reconhecidas 96,8% -> 100%; credenciamentos de folha < 0,5 de 23 para 6 em 137; as mesmas recusas pegas).
# Catálogo: Fopa-v2/01-Fundamentos/Jev — configuração e melhorias.md
CRITERIO_ESCOPO = "v3.1"
CRITERIO_SUSTENTA = "64:pergunta+criterios"
# 73_ (24/09 noite): o mesmo v3 com as
# páginas do edital escolhidas por termo. Sozinho, pega menos recusa humana (78,9% × 89,5%); a MÉDIA com o
# só-objeto derruba o alarme falso na folha de 4% para 0,8% e pega as mesmas — a tela mostra a média
# (api/consultas.py:JEV_ESCOPO), e as duas notas ficam gravadas cruas.
CRITERIO_ESCOPO_EDITAL = "v3+edital"
# Acurácia plana entre 0,50 e 0,95 (auditoria independente): distância do 0,5
# nessa faixa não ordena nada. Discordar exige p <= 0,25 ou p >= 0,75.
CONVICCAO = 0.25
# 32k tokens em `state` + a maior pergunta (docs.typesafe.ai/models); sondado:
# 63.750 caracteres passam, 67.500 voltam max_tokens_exceeded. Margem de 750.
MAX_CHARS_STATE = 63_000


def _usd(usage: dict | None) -> float:
    ent = (usage or {}).get("input_tokens") or 0
    return ent * cliente.PRECO_ENTRADA_ANUNCIADO / 1_000_000     # saída é gratuita (documentado)


# ------------------------------------------------------------------ escopo
def corpo_escopo(objeto: str) -> dict:
    c = _77.V31
    return {"state": objeto or "", "model": cliente.MODELO,
            "questions": {"escopo": cliente.noul(c["pergunta"], c["sim"], c["nao"])}}


def corpo_escopo_edital(objeto: str, paginas: list[tuple[str, int, str]]) -> tuple[dict, str]:
    """O escopo com o EDITAL: objeto + as páginas da leitura com mais termos da pergunta (73_:rag)."""
    trechos = _73.rag(paginas)
    state = json.dumps({"objeto": objeto or "", "trechos_do_edital": trechos}, ensure_ascii=False)
    como = "edital RAG %dp (%d caracteres)" % (len(trechos), sum(len(t["texto"]) for t in trechos))
    return ({"state": state, "model": cliente.MODELO,
             "questions": {"escopo": cliente.noul(_73.PERGUNTA_RAG, _73.CRITERIO["sim"], _73.CRITERIO["nao"])}},
            como)


def interpretar_escopo(regra_dentro: bool, answers: dict, usage: dict | None) -> dict:
    p = cliente.valor((answers or {}).get("escopo") or {})
    p = float(p) if p is not None else None
    jev_diz = p is not None and p >= 0.5
    convicto = p is not None and (p <= CONVICCAO or p >= 1 - CONVICCAO)
    return {"p_sim": p, "resposta": None if p is None else ("sim" if jev_diz else "nao"),
            "confianca": None if p is None else round(abs(p - 0.5) * 2, 4),
            # O score do FILTRO: a probabilidade, segundo o Jev, de a regra ter
            # acertado nesta licitação — P(folha) se a regra aceitou, 1 - P(folha)
            # se recusou. Agregado sobre a busca, mede o ruído do PNCP.
            "p_filtro_ok": None if p is None else (p if regra_dentro else 1 - p),
            "discorda": p is not None and jev_diz != bool(regra_dentro),
            "candidata": p is not None and jev_diz != bool(regra_dentro) and convicto,
            "usd": _usd(usage), "tok_entrada": (usage or {}).get("input_tokens")}


# ------------------------------------------------------------------ sustenta?
def janela(paginas: list[str], alvo: int, teto: int = MAX_CHARS_STATE) -> tuple[str, str]:
    """
    O documento inteiro quando cabe; senão uma JANELA em volta da página citada,
    uma página para cada lado por vez (64_jev_ancoragem._texto_do_documento).
    Truncar nos primeiros N caracteres cortaria justamente a página citada, e o
    "nada_diz" que viria disso pareceria achado.
    """
    if not paginas:
        return "", "nada"

    def marcar(i: int) -> str:
        return "=== PÁGINA %d ===\n%s" % (i + 1, paginas[i])

    if sum(len(p) for p in paginas) <= teto:
        return "\n\n".join(marcar(i) for i in range(len(paginas))), "documento"
    alvo = max(0, min((alvo or 1) - 1, len(paginas) - 1))
    ini = fim = alvo
    total = len(paginas[alvo])
    while True:
        cresceu = False
        if ini - 1 >= 0 and total + len(paginas[ini - 1]) <= teto:
            ini -= 1
            total += len(paginas[ini])
            cresceu = True
        if fim + 1 < len(paginas) and total + len(paginas[fim + 1]) <= teto:
            fim += 1
            total += len(paginas[fim])
            cresceu = True
        if not cresceu:
            break
    return ("\n\n".join(marcar(i) for i in range(ini, fim + 1)),
            "janela %dp (de %d)" % (fim - ini + 1, len(paginas)))


def corpo_sustenta(pergunta: str, resposta: str, trecho: str, arquivo: str, pagina: int,
                   paginas_do_arquivo: list[str]) -> tuple[dict, str]:
    base = {"afirmacao": resposta, "pergunta_respondida": pergunta, "trecho_citado": trecho,
            "onde": "%s, página %s" % (arquivo, pagina)}
    folga = MAX_CHARS_STATE - len(json.dumps(base, ensure_ascii=False)) - 200
    texto, como = janela(paginas_do_arquivo, pagina, max(folga, 1000))
    if texto:
        base["documento" if como == "documento" else "paginas_em_volta_da_citada"] = texto
    return ({"state": json.dumps(base, ensure_ascii=False), "model": cliente.MODELO,
             "questions": {"relacao": cliente.escolha(_64.PERGUNTA, _64.CRITERIOS)}}, como)


def interpretar_sustenta(answers: dict, usage: dict | None) -> dict:
    r = (answers or {}).get("relacao") or {}
    escolha = r.get("choice")
    conf = r.get("confidence")
    conf = float(conf) if conf is not None else None
    probs = r.get("probabilities") or {}
    # O score da RESPOSTA: a probabilidade de o trecho sustentar a afirmação.
    # Sem a distribuição, só a escolha "sustenta" com sua confiança diz algo.
    p_sust = probs.get("sustenta")
    if p_sust is None and escolha == "sustenta":
        p_sust = conf
    return {"resposta": escolha, "confianca": conf, "probabilidades": probs or None,
            "p_sustenta": float(p_sust) if p_sust is not None else None,
            "candidata": escolha in ("contradiz", "nada_diz") and (conf or 0) >= 1 - CONVICCAO,
            "usd": _usd(usage), "tok_entrada": (usage or {}).get("input_tokens")}


__all__ = ["corpo_escopo", "interpretar_escopo", "janela", "corpo_sustenta", "interpretar_sustenta",
           "CRITERIO_ESCOPO", "CRITERIO_SUSTENTA", "CONVICCAO", "MAX_CHARS_STATE"]
