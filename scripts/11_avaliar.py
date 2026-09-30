# -*- coding: utf-8 -*-
"""
Harness de avaliação — varre modelos, efforts e modos sobre o MESMO edital.

    python 11_avaliar.py <pasta> --modelos claude-opus-5,claude-sonnet-5,claude-haiku-4-5
    python 11_avaliar.py <pasta> --efforts high,medium,low
    python 11_avaliar.py <pasta> --modos rag,contexto-completo
    python 11_avaliar.py <pasta> --repeticoes 3          mede variância

O OCR roda UMA vez e é reaproveitado em todas as configurações: sem isso, comparar
6 configs custaria 6× o tempo de leitura e introduziria ruído de preparação.

MÉTRICAS
  ancoragem       o trecho existe na página citada (determinístico, sem IA)
  concordância    quantas respostas coincidem com a configuração de referência
  conflitos       divergências entre documentos que a config percebeu
  custo e tempo   por execução

Sobre a concordância: sem gabarito humano, ela é o melhor sinal disponível de
acurácia. Duas configurações independentes chegarem à mesma resposta em um campo
crítico é evidência fraca mas real; divergirem é sinal forte de que uma está errada.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
import unicodedata

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import extrator, modelos, verificador          # noqa: E402
from fopa.questionario import NAO_LOCALIZADO, POR_ID     # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")
CRITICAS = tuple(p.id for p in POR_ID.values() if p.critico)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", re.sub(r"\s+", " ", s.lower())).strip()


def _motivo(alerta: str) -> str:
    """Agrupa o alerta do Verificador numa causa.

    O texto do alerta carrega similaridade e número de página, que mudam a cada
    resposta; sem agrupar, contar motivos devolveria uma lista de ocorrências
    únicas, que não diz nada sobre a causa dominante.
    """
    a = _norm(alerta)
    if "nao confere" in a or "nao encontrado na pagina" in a:
        return "trecho não confere com a página"
    if "pagina" in a and ("inexistente" in a or "fora" in a):
        return "página inexistente"
    if "sem trecho" in a or "trecho curto" in a or "muito curto" in a:
        return "trecho ausente ou curto"
    if "arquivo" in a:
        return "arquivo não encontrado"
    return alerta.split(".")[0][:44]


def concordancia(a, b, apenas_criticas: bool = False) -> float:
    """Fração de respostas que dizem substancialmente a mesma coisa."""
    ids = CRITICAS if apenas_criticas else tuple(p.id for p in POR_ID.values())
    iguais = 0
    for pid in ids:
        ra, rb = a.por_id(pid), b.por_id(pid)
        if not ra or not rb:
            continue
        na, nb = _norm(ra.resposta), _norm(rb.resposta)
        nl_a = na.startswith("nao localizado")
        nl_b = nb.startswith("nao localizado")
        if nl_a and nl_b:
            iguais += 1
        elif nl_a != nl_b:
            pass
        elif difflib.SequenceMatcher(None, na, nb, autojunk=False).ratio() >= 0.62:
            iguais += 1
    return iguais / len(ids)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("--modelos", default="claude-opus-5")
    ap.add_argument("--efforts", default="high")
    ap.add_argument("--modos", default="")
    ap.add_argument("--sufixo", default="", help="distingue varreduras da mesma licitacao")
    ap.add_argument("--repeticoes", type=int, default=1)
    ap.add_argument("--lote", type=int, default=6)
    a = ap.parse_args()

    pasta = a.pasta if os.path.isdir(a.pasta) else os.path.join(AMOSTRAS, a.pasta)
    if not os.path.isdir(pasta):
        print("pasta não encontrada:", pasta)
        return 2
    nome = os.path.basename(pasta.rstrip("\\/"))

    modelos_l = [m.strip() for m in a.modelos.split(",") if m.strip()]
    efforts_l = [e.strip() for e in a.efforts.split(",") if e.strip()]
    modos_l = [m.strip() for m in a.modos.split(",") if m.strip()] or [None]

    print("=" * 104)
    print("  HARNESS — %s" % nome)
    print("  modelos: %s | efforts: %s | modos: %s | repetições: %d"
          % (",".join(modelos_l), ",".join(efforts_l),
             ",".join(m or "auto" for m in modos_l), a.repeticoes))
    print("=" * 104)

    print("\n  Preparando documentos (OCR roda uma vez só)...")
    t0 = time.time()
    paginas = extrator.carregar_paginas(pasta)
    print("  %d páginas de %d arquivo(s) em %.0fs"
          % (len(paginas), len({p.arquivo for p in paginas}), time.time() - t0))

    try:
        provedor = modelos.obter_provedor()
    except modelos.ErroModelo as e:
        print("\n  %s" % e)
        return 3

    execucoes, referencia = [], None
    for modelo in modelos_l:
        for effort in efforts_l:
            # Haiku ignora effort — rodar as duas variantes seria gastar à toa
            if modelo.startswith("claude-haiku") and effort != efforts_l[0]:
                continue
            for modo in modos_l:
                for rep in range(1, a.repeticoes + 1):
                    rot = "%s · %s%s%s" % (
                        modelo.replace("claude-", ""), effort,
                        "" if not modo else " · " + modo,
                        "" if a.repeticoes == 1 else " · #%d" % rep)
                    print("\n  ▶ %s" % rot)
                    t = time.time()
                    try:
                        ext = extrator.extrair(
                            pasta, provedor, modelo=modelo, modo=modo,
                            lote=a.lote, effort=effort, paginas_prontas=paginas)
                        rel = verificador.verificar(ext)
                    except Exception as e:                      # noqa: BLE001
                        print("     FALHOU: %s" % e)
                        continue
                    if referencia is None:
                        referencia = ext
                    conc = concordancia(ext, referencia)
                    conc_crit = concordancia(ext, referencia, apenas_criticas=True)
                    reg = dict(
                        rotulo=rot, modelo=modelo, effort=effort,
                        modo=ext.modo, repeticao=rep,
                        ancoradas=rel.ancoradas, respondidas=rel.respondidas,
                        taxa=round(rel.taxa_ancorada, 4),
                        aprovadas=rel.aprovadas, revisar=rel.revisar,
                        reprovadas=rel.reprovadas, nao_loc=rel.nao_localizado,
                        conflitos=sum(1 for r in ext.respostas if r.conflito),
                        entrada=ext.uso.entrada, saida=ext.uso.saida,
                        brl=round(ext.uso.brl, 3), seg=round(time.time() - t, 1),
                        concordancia=round(conc, 4), concordancia_criticas=round(conc_crit, 4),
                        respostas={r.id: r.resposta for r in ext.respostas},
                        # A evidência precisa ser persistida: quando a ancoragem
                        # despenca num modelo, só o trecho citado diz se o erro é
                        # de LEITURA ou desobediência à regra de citação literal.
                        evidencia={r.id: dict(
                            arquivo=r.arquivo, pagina=r.pagina,
                            trecho=r.trecho_literal, veredito=r.veredito,
                            alertas=list(r.alertas)) for r in ext.respostas})
                    execucoes.append(reg)
                    print("     ancoragem %d/%d · %d conflito(s) · concord. %.0f%% "
                          "(críticas %.0f%%) · R$ %.2f · %.0fs"
                          % (rel.ancoradas, rel.respondidas, reg["conflitos"],
                             100 * conc, 100 * conc_crit, reg["brl"], reg["seg"]))

    # ------------------------------------------------------------ tabela
    print("\n" + "=" * 104)
    print("  COMPARATIVO")
    print("=" * 104)
    print("%-34s %-17s %9s %6s %7s %7s %8s %7s"
          % ("configuração", "modo", "ancoragem", "confl", "não-loc",
             "concord", "R$", "seg"))
    print("-" * 104)
    for r in execucoes:
        print("%-34s %-17s %4d/%-4d %6d %7d %6.0f%% %8.2f %7.0f"
              % (r["rotulo"][:34], r["modo"], r["ancoradas"], r["respondidas"],
                 r["conflitos"], r["nao_loc"], 100 * r["concordancia"],
                 r["brl"], r["seg"]))

    if len(execucoes) > 1:
        base = execucoes[0]
        print("\n  Relativo a %s:" % base["rotulo"])
        for r in execucoes[1:]:
            eco = (1 - r["brl"] / base["brl"]) * 100 if base["brl"] else 0
            print("    %-34s custo %+6.0f%% · concord. %3.0f%% · críticas %3.0f%%"
                  % (r["rotulo"][:34], -eco, 100 * r["concordancia"],
                     100 * r["concordancia_criticas"]))

        print("\n  Por que a ancoragem falhou (alertas por configuração):")
        for r in execucoes:
            if r["ancoradas"] == r["respondidas"]:
                continue
            motivos = {}
            for _pid, ev in r.get("evidencia", {}).items():
                for al in ev.get("alertas", []):
                    m = _motivo(al)
                    motivos[m] = motivos.get(m, 0) + 1
            if motivos:
                ordem = sorted(motivos.items(), key=lambda x: -x[1])
                print("    %-22s %s" % (r["rotulo"].split(" · ")[0],
                      " · ".join("%s ×%d" % (m, n) for m, n in ordem)))

        print("\n  Divergências nas perguntas críticas:")
        houve = False
        for pid in CRITICAS:
            vistos = {}
            for r in execucoes:
                vistos.setdefault(_norm(r["respostas"].get(pid, ""))[:90], []).append(
                    r["rotulo"].split(" · ")[0])
            if len(vistos) > 1:
                houve = True
                print("    %s:" % pid)
                for txt, quem in vistos.items():
                    print("       [%s] %s" % (", ".join(sorted(set(quem))), txt[:78]))
        if not houve:
            print("    nenhuma — todas as configurações concordam nas críticas")

    os.makedirs(SAIDAS, exist_ok=True)
    # Sem sufixo, uma varredura de effort sobrescreveria a comparacao de modelos
    # da mesma licitacao — apagando uma medicao paga para gravar outra.
    dest = os.path.join(SAIDAS, "_harness_%s%s.json"
                        % (nome, ("_" + a.sufixo) if a.sufixo else ""))
    with open(dest, "w", encoding="utf-8") as f:
        json.dump({"licitacao": nome, "execucoes": execucoes}, f,
                  ensure_ascii=False, indent=1)
    print("\n  salvo: %s" % os.path.relpath(dest, RAIZ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
