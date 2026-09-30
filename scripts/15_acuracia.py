# -*- coding: utf-8 -*-
"""
Mede ACURÁCIA contra gabarito — a métrica que a ancoragem não dá.

    python 15_acuracia.py "ABERTO Concorrencia - Eletronica - Pirapo-RS"
    python 15_acuracia.py <licitação> --json saidas/_harness_<...>.json

A ancoragem prova que o trecho citado existe na página citada. Não prova que a
resposta responde à pergunta. Um extrator pode citar um trecho verdadeiro e
irrelevante: ancoragem 100%, acurácia zero. As duas métricas precisam existir
lado a lado, e o projeto só tinha uma.

COMO O GABARITO EVITA VIRAR OPINIÃO
Comparar texto livre com texto livre exigiria um juiz — e usar um modelo como
juiz devolveria ao sistema a subjetividade que ele existe para eliminar. Então o
gabarito não guarda a redação certa: guarda os FATOS que a resposta certa
precisa conter, em `_gabarito.json`, cada um com a página onde foi conferido.

    fatos_obrigatorios   sem eles a resposta está errada       -> acurácia
    fatos_desejaveis     enriquecem mas não definem            -> completude

Dois números diferentes, porque medem coisas diferentes: acertar o valor e
explicar o valor não são a mesma competência.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")



MESES = {"janeiro": "01", "fevereiro": "02", "marco": "03", "abril": "04",
         "maio": "05", "junho": "06", "julho": "07", "agosto": "08",
         "setembro": "09", "outubro": "10", "novembro": "11", "dezembro": "12"}
RE_DATA_EXTENSO = re.compile(
    r"\b(\d{1,2})\s+de\s+(%s)\s+de\s+(\d{4})\b" % "|".join(MESES))


def _datas_por_extenso(s: str) -> str:
    """"21 de setembro de 2026" e "21/09/2026" são a mesma data.

    O edital escreve das duas formas, às vezes na mesma página, e os modelos
    copiam a que estiver mais perto. Exigir uma delas reprova a outra — foi o
    que reprovou o Sonnet na Q1 de Bertioga, numa resposta correta.
    """
    return RE_DATA_EXTENSO.sub(
        lambda m: "%02d/%s/%s" % (int(m.group(1)), MESES[m.group(2)], m.group(3)), s)


def norm(s: str) -> str:
    """Normaliza para comparação, PRESERVANDO dígitos, vírgula e ponto.

    Tirar a pontuação numérica junto com a textual transformaria "250.000,00"
    em "25000000" e faria "2.500,00" casar com ele. Num domínio onde o erro de
    leitura de um valor é o modo de falha que importa, isso seria inaceitável.
    """
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = s.lower()
    s = re.sub(r"[^a-z0-9.,%:/ ]+", " ", s)
    # "09h00" e "09:00" sao o mesmo horario. O documento escreve com dois-pontos,
    # os modelos convertem para "h" — e o gabarito reprovava os tres por causa da
    # grafia. Um instrumento literal demais reprova acerto: foi o que ja aconteceu
    # com o nome do arquivo e com as faixas da RN-09.
    s = re.sub(r"(?<!\d)(\d{1,2})h(\d{2})(?!\d)", r"\g<1>:\g<2>", s)
    s = re.sub(r"(?<!\d)(\d{1,2})h(?![\d:])", r"\g<1>:00", s)
    s = re.sub(r"(?<!\d)(\d):(\d{2})(?!\d)", r"0\g<1>:\g<2>", s)
    s = _datas_por_extenso(s)
    return re.sub(r"\s+", " ", s).strip()


def contem(resposta: str, fato: str) -> bool:
    """O fato aparece na resposta?

    Números são comparados como token inteiro: "3" não pode casar dentro de
    "3.000,00" nem de "297". Sem essa âncora, a faixa de 3 servidores de Pirapó
    seria dada como presente em qualquer resposta que mencione um valor.
    """
    r, f = norm(resposta), norm(fato)
    if not f:
        return False
    if re.fullmatch(r"[\d.,%:]+", f):
        # "05 (cinco) dias" e "5 dias" são o mesmo prazo. O edital escreve com
        # zero à esquerda, o gabarito foi escrito sem, e a âncora de dígito
        # impedia o casamento — reprovando os três modelos numa resposta certa.
        padrao = r"0*" + re.escape(f) if f[:1].isdigit() else re.escape(f)
        # Ponto, vírgula ou dois-pontos só continuam o número quando vem dígito depois: "Total 1.896." termina a
        # frase, "1.896.000,00" é outro número. Recusar qualquer pontuação reprovou a Q13 de Bertioga (28/09).
        return re.search(r"(?<!\d)(?<!\d[.,:])%s(?!\d|[.,:]\d)" % padrao, r) is not None
    return f in r


def avaliar(resposta: str, ref: dict) -> dict:
    obrig = ref.get("fatos_obrigatorios", [])
    desej = ref.get("fatos_desejaveis", [])
    faltando = [f for f in obrig if not contem(resposta, f)]
    tem_desej = [d for d in desej if contem(resposta, d)]
    return dict(
        correta=not faltando,
        faltando=faltando,
        obrig=len(obrig),
        desejaveis=len(tem_desej),
        desejaveis_total=len(desej))


def _de_auditoria(caminho: str, rotulo: str | None = None) -> dict | None:
    if not os.path.isfile(caminho):
        return None
    d = json.load(open(caminho, encoding="utf-8"))
    modelo = d.get("uso", {}).get("modelo", "?")
    return dict(
        rotulo=rotulo or "produção (%s)" % modelo,
        respostas={r["id"]: r.get("resposta", "") for r in d.get("respostas", [])})


def carregar_execucoes(licitacao: str, caminho_json: str | None,
                       extras: list[str] | None = None) -> list[dict]:
    """Junta o que houver: o harness, a produção e execuções avulsas (--extra)."""
    execucoes = []
    alvo = caminho_json or os.path.join(SAIDAS, "_harness_%s.json" % licitacao)
    if os.path.isfile(alvo):
        d = json.load(open(alvo, encoding="utf-8"))
        for e in d.get("execucoes", []):
            execucoes.append(dict(rotulo=e["rotulo"], respostas=e.get("respostas", {})))

    prod = _de_auditoria(os.path.join(SAIDAS, licitacao, "auditoria.json"))
    if prod:
        execucoes.append(prod)

    # `--extra` existe para comparar execuções que moram FORA de `saidas/<nome>/`
    # — outro provedor, outro modelo, outro k. Elas não podem escrever na pasta
    # canônica, senão sobrescreveriam a produção; então precisam de um caminho
    # de entrada próprio aqui.
    for caminho in (extras or []):
        e = _de_auditoria(caminho)
        if e:
            execucoes.append(e)
        else:
            print("  aviso: --extra não encontrado, ignorado: %s" % caminho)
    return execucoes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("licitacao")
    ap.add_argument("--json", default=None, help="arquivo de comparação específico")
    ap.add_argument("--detalhe", action="store_true", help="lista o que faltou em cada erro")
    ap.add_argument("--extra", action="append", default=[], metavar="AUDITORIA.JSON",
                    help="auditoria.json de outra execução (repetível)")
    a = ap.parse_args()

    gab_path = os.path.join(AMOSTRAS, a.licitacao, "_gabarito.json")
    if not os.path.isfile(gab_path):
        print("sem gabarito para esta licitação: %s" % os.path.relpath(gab_path, RAIZ))
        print("a acurácia só pode ser medida onde existe gabarito construído à mão.")
        return 2

    gab = json.load(open(gab_path, encoding="utf-8"))
    perguntas = gab["perguntas"]
    criticas = [q for q, r in perguntas.items() if r.get("critica")]
    execucoes = carregar_execucoes(a.licitacao, a.json, a.extra)

    if not execucoes:
        print("nenhuma execução encontrada para comparar.")
        return 2

    print("=" * 100)
    print("  ACURÁCIA CONTRA GABARITO — %s" % a.licitacao)
    print("=" * 100)
    print("  gabarito: %d perguntas (%d críticas) · %s"
          % (len(perguntas), len(criticas), gab.get("construido_em", "")))
    print("  %s" % gab.get("metodo", "")[:96])
    print()
    print("%-26s %11s %11s %11s" % ("configuração", "acurácia", "críticas", "completude"))
    print("-" * 100)

    erros: dict[str, list[tuple[str, list[str]]]] = {}
    for ex in execucoes:
        ok = ok_crit = 0
        desej = desej_tot = 0
        meus_erros = []
        for qid, ref in perguntas.items():
            v = avaliar(ex["respostas"].get(qid, ""), ref)
            if v["correta"]:
                ok += 1
                if qid in criticas:
                    ok_crit += 1
            else:
                meus_erros.append((qid, v["faltando"]))
            desej += v["desejaveis"]
            desej_tot += v["desejaveis_total"]
        erros[ex["rotulo"]] = meus_erros
        print("%-26s %6d/%-4d %6d/%-4d %6d/%-4d"
              % (ex["rotulo"][:26], ok, len(perguntas),
                 ok_crit, len(criticas), desej, desej_tot))

    print("-" * 100)
    print("  acurácia .... respostas com TODOS os fatos obrigatórios")
    print("  críticas .... idem, só nas %d perguntas que entram no cálculo do lance" % len(criticas))
    print("  completude .. fatos desejáveis presentes (contexto, ressalvas, divergências)")

    if a.detalhe:
        print("\n" + "=" * 100)
        print("  O QUE FALTOU")
        print("=" * 100)
        for rotulo, lista in erros.items():
            if not lista:
                print("\n  %s — nenhum erro" % rotulo)
                continue
            print("\n  %s" % rotulo)
            for qid, faltando in lista:
                marca = " [CRÍTICA]" if qid in criticas else ""
                print("    %-4s%-11s faltou: %s" % (qid, marca, ", ".join(faltando)[:70]))
    else:
        print("\n  use --detalhe para ver o que faltou em cada erro")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
