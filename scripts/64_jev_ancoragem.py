# -*- coding: utf-8 -*-
"""
O trecho citado SUSTENTA a resposta? — o ponto cego da ancoragem.

    python 64_jev_ancoragem.py [--so <pasta>] [--max N]

CHAMA O JEV. Nao chama o extrator: le as extracoes que ja estao em disco.

O QUE A ANCORAGEM GARANTE, E O QUE ELA NAO GARANTE
  O Verificador confere, caractere a caractere, que o `trecho_literal` EXISTE
  na pagina citada. Isso mata a citacao inventada -- e e a espinha do projeto.

  Mas existir nao e sustentar. Um trecho pode estar literalmente na pagina e
  ainda assim nao dizer o que a resposta afirma:

      resposta ...... "o prazo de vigencia e de 60 meses"
      trecho .......... "...prazo de 12 meses para a garantia contratual..."

  O trecho e real, a pagina e a certa, a ancoragem APROVA -- e a resposta esta
  errada. Esse e o buraco, e ele e estrutural: comparacao de texto nao sabe
  ler.

O QUE O JEV ACRESCENTA, E SO ISSO
  O cookbook de citation check do fornecedor separa as duas perguntas de
  proposito: a presenca literal fica FORA do modelo (e trabalho de codigo), e
  o modelo julga apenas a RELACAO entre a afirmacao e a passagem:

      supports ...... a passagem afirma ou implica diretamente a resposta
      contradicts ... a passagem diz o oposto
      says_nothing .. a passagem nao trata do que a resposta afirma

  E exatamente a divisao que a ADR-004 exige. O Jev nao ve a pagina inteira,
  nao escolhe o trecho, nao aprova nada: ele opina sobre um par que o proprio
  codigo ja montou e ja verificou.

O QUE ESTE SCRIPT NAO FAZ
  Nao altera `veredito`, nao mexe em `confianca`, nao reprova resposta. Grava
  um arquivo separado. Se um dia o numero dele passar a decidir, a ADR-004 foi
  violada -- o Jev e adendo de assertividade, nao
  motivo de decisao.
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import jev, ocr                                         # noqa: E402

SAIDAS = os.path.join(RAIZ, "saidas")
AMOSTRAS = os.path.join(RAIZ, "amostras")
DESTINO = os.path.join(SAIDAS, "_jev_ancoragem.json")

PERGUNTA = ("A passagem citada do edital sustenta a afirmação? Julgue apenas a "
            "relação entre as duas: a passagem diz, ou implica diretamente, "
            "aquilo que a afirmação declara? Não avalie se a afirmação é "
            "verdadeira no mundo — só se ESTA passagem a sustenta.")
CRITERIOS = {
    "sustenta": ("a passagem afirma o que a declaração diz, ou implica isso "
                 "diretamente, sem precisar de outra informação"),
    "contradiz": ("a passagem afirma o oposto da declaração, ou um valor, prazo "
                  "ou nome diferente do que ela declara"),
    "nada_diz": ("a passagem não trata do que a declaração afirma — fala de "
                 "outro assunto, de outro campo, ou é genérica demais"),
}


_CACHE_PAG: dict = {}


def _texto_da_pagina(pasta: str, aud: dict, r: dict) -> str:
    """
    O texto da pagina citada, lido do PDF em disco.

    Devolve "" quando nao acha o arquivo -- e ai o Jev julga so o trecho, que
    e o comportamento antigo. Melhor degradar para menos contexto do que
    inventar contexto.
    """
    arq = r.get("arquivo") or ""
    pag = r.get("pagina")
    if not arq or not isinstance(pag, int) or pag < 1:
        return ""
    origem = aud.get("licitacao") or pasta
    caminho = os.path.join(AMOSTRAS, origem, arq)
    if not os.path.isfile(caminho):
        caminho = os.path.join(AMOSTRAS, pasta, arq)
    if not os.path.isfile(caminho):
        return ""
    chave = (caminho, pag)
    if chave in _CACHE_PAG:
        return _CACHE_PAG[chave]
    try:
        texto = ocr.ler_pagina(caminho, pag - 1)
    except Exception:                                             # noqa: BLE001
        texto = ""
    _CACHE_PAG[chave] = texto
    return texto


_CACHE_DOC: dict = {}

# LIMITE DOCUMENTADO, E CONFERIDO CONTRA A API.
#
# https://docs.typesafe.ai/models.md diz, para jev-1.13 / jev-latest:
#
#     "64k tokens per request; 32k tokens for `state` plus the longest question"
#
# Sao dois tetos, e o que pega aqui e o SEGUNDO: o edital vai inteiro no
# `state`, entao o orcamento util e 32k, nao 64k. Como a pergunta tem algumas
# centenas de tokens, metade do request fica inutilizavel na pratica -- e nao
# ha como contornar, porque `state` e onde o documento tem que ir.
#
# Conferido por sondagem em 23/09/2026: 63.750 caracteres passam (32.179
# tokens de entrada) e 67.500 voltam
# `{"detail":{"error_type":"max_tokens_exceeded"}}`.
#
# DUAS COISAS QUE CUSTARAM TEMPO, E VALEM PARA A PROXIMA API
#   · A primeira versao cortava em 400 mil caracteres -- uma ordem de grandeza
#     acima do limite real -- e 48 de 137 chamadas voltaram HTTP 400.
#   · O limite foi procurado na pagina de API, que e onde estao os codigos de
#     erro (401, 422, 429, 529). `max_tokens_exceeded` NAO esta nessa lista, e
#     o limite esta na pagina de modelos. As duas paginas nao se referenciam.
#     Procurar o teto onde o erro esta documentado foi a hipotese razoavel e
#     errado.
#
# 58.000 caracteres ficam em ~29k tokens: folga suficiente para a pergunta e
# para a variacao de tokenizacao entre textos.
MAX_DOC_CHARS = 58_000


def _paginas_do_documento(pasta: str, aud: dict, r: dict):
    arq = r.get("arquivo") or ""
    if not arq:
        return [], ""
    origem = aud.get("licitacao") or pasta
    caminho = os.path.join(AMOSTRAS, origem, arq)
    if not os.path.isfile(caminho):
        caminho = os.path.join(AMOSTRAS, pasta, arq)
    if not os.path.isfile(caminho):
        return [], ""
    if caminho in _CACHE_DOC:
        return _CACHE_DOC[caminho], caminho
    try:
        paginas = ocr.ler_documento(caminho)
    except Exception:                                             # noqa: BLE001
        paginas = []
    _CACHE_DOC[caminho] = paginas
    return paginas, caminho


def _texto_do_documento(pasta: str, aud: dict, r: dict):
    """
    O documento inteiro quando cabe; uma JANELA em volta da pagina citada
    quando nao cabe. Devolve `(texto, como)`.

    POR QUE JANELA, E NAO TRUNCAR
      Truncar nos primeiros N caracteres corta o fim do edital -- e a pagina
      citada pode estar justamente ali. O resultado seria o Jev dizendo
      "nada_diz" sobre uma resposta correta, porque a evidencia nao foi
      enviada. Erro silencioso e do tipo caro: parece achado.

      A janela cresce a partir da pagina citada, uma pagina para cada lado por
      vez, ate encher o orcamento. Assim o contexto que se paga e sempre o
      MAIS PROXIMO da evidencia.

    `como` vai para o resultado: "documento", "janela Np" ou "pagina". Saber
    quanto contexto cada resposta recebeu e o que torna a comparacao honesta.
    """
    paginas, caminho = _paginas_do_documento(pasta, aud, r)
    if not paginas:
        return "", "nada"
    nome = os.path.basename(caminho)
    inteiro = ocr.marcar_paginas(paginas, nome)
    if len(inteiro) <= MAX_DOC_CHARS:
        return inteiro, "documento"

    alvo = (r.get("pagina") or 1) - 1
    alvo = max(0, min(alvo, len(paginas) - 1))
    ini = fim = alvo
    total = len(paginas[alvo])
    while True:
        cresceu = False
        if ini - 1 >= 0 and total + len(paginas[ini - 1]) <= MAX_DOC_CHARS:
            ini -= 1
            total += len(paginas[ini])
            cresceu = True
        if fim + 1 < len(paginas) and total + len(paginas[fim + 1]) <= MAX_DOC_CHARS:
            fim += 1
            total += len(paginas[fim])
            cresceu = True
        if not cresceu:
            break
    janela = ocr.marcar_paginas(paginas[ini:fim + 1], nome)
    return janela, "janela %dp (de %d)" % (fim - ini + 1, len(paginas))


def prova_adversarial(a) -> int:
    """
    O segundo sinal so vale se ele SOUBER DIZER NAO.

    Rodando sobre as extracoes reais, o Jev disse `sustenta` em 100% delas.
    Isso tem duas leituras opostas -- "as respostas estao certas" e "ele
    concorda com qualquer coisa" -- e nenhuma medicao sobre dados certos
    distingue as duas.

    Esta prova pega uma resposta real, com a pagina real, e adultera SO a
    afirmacao. Se ele continuar dizendo `sustenta`, o sinal e inutil e nao
    deve entrar em lugar nenhum.

    Medido em 23/09/2026, pagina 1 do edital de Pirapo/RS:

        original ....................... sustenta   0,99
        data trocada (08/10 -> 19/03) .. contradiz  1,00
        resposta de outra pergunta ..... nada_diz   0,55
        valor inventado ................ nada_diz   1,00

    A segunda linha e a que importa: trecho real, pagina certa, valor errado
    -- exatamente o que a ancoragem aprova e nao tem como pegar.
    """
    alvo = os.path.join(SAIDAS, "ABERTO Concorrencia - Eletronica - Pirapo-RS",
                        "auditoria.json")
    if not os.path.isfile(alvo):
        print("falta a extração de Pirapó/RS, que é a base da prova.")
        return 1
    aud = json.load(io.open(alvo, encoding="utf-8"))
    base = next((r for r in aud.get("respostas") or []
                 if r.get("id") == "Q1" and r.get("trecho_literal")), None)
    if not base:
        print("Q1 de Pirapó não tem trecho — nada a provar.")
        return 1
    pagina = _texto_da_pagina("ABERTO Concorrencia - Eletronica - Pirapo-RS",
                              aud, base)
    orig = base.get("resposta") or ""
    casos = [
        ("original", orig, "sustenta"),
        ("data trocada", orig.replace("08/10/2026", "19/03/2027")
                             .replace("09h00", "15h30"), "contradiz"),
        ("resposta de outra pergunta",
         "O prazo de vigência do contrato é de 60 (sessenta) meses, prorrogável.",
         "nada_diz"),
        ("valor inventado",
         "O valor mínimo de arrematação é de R$ 7.412.900,00.", "nada_diz"),
    ]
    doc_prova = (_texto_do_documento("ABERTO Concorrencia - Eletronica - Pirapo-RS",
                                     aud, base)[0]
                 if a.contexto == "documento" else "")
    print("  PROVA ADVERSARIAL — contexto %s, afirmação adulterada" % a.contexto)
    print("  página %s de %s · %d caracteres"
          % (base.get("pagina"), base.get("arquivo"), len(pagina)))
    print()
    ok = 0
    for rotulo, resposta, esperado in casos:
        # A PROVA TEM QUE RODAR NO MESMO CONTEXTO QUE A PRODUCAO.
        #
        # Mais contexto podia piorar isto, e essa e a hipotese que precisa ser
        # testada: com o documento inteiro, o Jev tem MAIS texto onde achar
        # alguma coisa que "sustente" uma afirmacao adulterada. Um sinal que
        # para de dizer nao quando ganha contexto e pior que um sinal fraco.
        corpo = {
            "afirmacao": resposta,
            "pergunta_respondida": base.get("pergunta"),
            "trecho_citado": base.get("trecho_literal"),
            "onde": "%s, página %s" % (base.get("arquivo"), base.get("pagina")),
        }
        if a.contexto == "documento":
            corpo["documento_inteiro"] = doc_prova
        else:
            corpo["pagina_inteira"] = pagina
        estado = json.dumps(corpo, ensure_ascii=False)
        try:
            ans, _ = jev.perguntar(estado, {"relacao": jev.escolha(PERGUNTA,
                                                                  CRITERIOS)})
        except jev.ErroJev as e:
            print("     %-28s FALHOU: %s" % (rotulo, e))
            continue
        r = ans.get("relacao") or {}
        acertou = r.get("choice") == esperado
        ok += 1 if acertou else 0
        print("     %-28s -> %-10s conf %.2f   esperado %-10s %s"
              % (rotulo, r.get("choice"), r.get("confidence") or 0.0,
                 esperado, "ok" if acertou else "<- NAO PEGOU"))
    print()
    if ok == len(casos):
        print("  Ele sabe dizer não. O `sustenta` em 100% das respostas reais")
        print("  não é carimbo — é concordância com dados que estão certos.")
    else:
        print("  %d de %d. Um sinal que não pega afirmação adulterada não" % (ok, len(casos)))
        print("  acrescenta nada, e não deve entrar em lugar nenhum.")
    return 0 if ok == len(casos) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", default=None, help="filtra por nome de pasta")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--pausa", type=float, default=0.15)
    ap.add_argument("--contexto", choices=["trecho", "pagina", "documento"],
                    default="pagina",
                    help="o que o Jev recebe como passagem")
    ap.add_argument("--prova", action="store_true",
                    help="prova adversarial: adultera respostas e vê se ele pega")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if a.prova:
        return prova_adversarial(a)

    arquivos = sorted(glob.glob(os.path.join(SAIDAS, "*", "auditoria.json")))
    if a.so:
        arquivos = [f for f in arquivos if a.so.lower() in f.lower()]
    if not arquivos:
        print("nenhuma auditoria em saidas/ — nada a conferir.")
        return 1

    print("=" * 100)
    print("  O TRECHO SUSTENTA A RESPOSTA? — segundo sinal sobre o que a")
    print("  ancoragem já aprovou. O Jev NÃO altera veredito nenhum.")
    print("=" * 100)
    print()

    linhas, custo, segundos, falhas = [], 0.0, 0.0, 0
    for f in arquivos:
        pasta = os.path.basename(os.path.dirname(f))
        try:
            aud = json.load(io.open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        respostas = aud.get("respostas") or []
        # so as que a ancoragem APROVOU: e justamente nelas que o ponto cego
        # mora. Onde ela ja reprovou ou mandou revisar, nao ha o que somar.
        alvos = [r for r in respostas
                 if r.get("veredito") == "APROVADO" and (r.get("trecho_literal") or "").strip()]
        if not alvos:
            continue
        if a.max:
            alvos = alvos[: a.max]
        print("  %s  (%d aprovadas com trecho)" % (pasta[:62], len(alvos)))
        for r in alvos:
            # CONTEXTO: A PAGINA INTEIRA, NAO SO O TRECHO.
            #
            # Mandando so o `trecho_literal`, o Jev julga um fragmento cortado
            # -- e um trecho que termina em "deverá estar apta a iniciar a
            # operacionalização..." nao tem como sustentar um prazo que vem na
            # frase seguinte. Foi exatamente o que aconteceu com a Q10 de
            # Pirapo na primeira rodada: `nada_diz`, porque o prazo estava
            # fora do recorte.
            #
            # A pagina inteira custa ~700 tokens a US$ 0,042/M -- tres
            # centesimos de centavo. E o trecho continua marcado dentro dela,
            # para o Jev saber qual parte foi citada.
            corpo = {
                "afirmacao": r.get("resposta"),
                "pergunta_respondida": r.get("pergunta"),
                "trecho_citado": r.get("trecho_literal"),
                "onde": "%s, página %s" % (r.get("arquivo"), r.get("pagina")),
            }
            if a.contexto == "pagina":
                pag = _texto_da_pagina(pasta, aud, r)
                if pag:
                    corpo["pagina_inteira"] = pag
            elif a.contexto == "documento":
                doc, como = _texto_do_documento(pasta, aud, r)
                if doc:
                    corpo["documento" if como == "documento" else
                          "paginas_em_volta_da_citada"] = doc
                else:
                    como = "pagina"
                    pag = _texto_da_pagina(pasta, aud, r)
                    if pag:
                        corpo["pagina_inteira"] = pag
            estado = json.dumps(corpo, ensure_ascii=False)
            try:
                ans, uso = jev.perguntar(
                    estado, {"relacao": jev.escolha(PERGUNTA, CRITERIOS)})
            except jev.ErroJev as e:
                falhas += 1
                print("     %-4s FALHOU: %s" % (r.get("id"), e))
                continue
            rel = ans.get("relacao") or {}
            escolha = rel.get("choice")
            conf = rel.get("confidence") or 0.0
            custo += uso["usd"]
            segundos += uso["segundos"]
            linhas.append({
                "pasta": pasta, "id": r.get("id"),
                "pergunta": r.get("pergunta"),
                "resposta": (r.get("resposta") or "")[:300],
                "trecho": (r.get("trecho_literal") or "")[:300],
                "arquivo": r.get("arquivo"), "pagina": r.get("pagina"),
                "veredito_ancoragem": r.get("veredito"),
                "contexto_enviado": (como if a.contexto == "documento"
                                     else a.contexto),
                "jev_relacao": escolha, "jev_confianca": conf,
                "probabilidades": rel.get("probabilities"),
            })
            if escolha != "sustenta":
                print("     %-4s %-12s conf %.2f · %s"
                      % (r.get("id"), escolha, conf,
                         (r.get("pergunta") or "")[:52]))
            time.sleep(a.pausa)

    if not linhas:
        print("\n  nenhuma resposta conferida.")
        return 1

    n = len(linhas)
    from collections import Counter
    c = Counter(x["jev_relacao"] for x in linhas)
    print()
    print("-" * 100)
    print("  %d respostas que a ancoragem APROVOU, relidas pelo Jev"
          "  (contexto: %s):" % (n, a.contexto))
    for k in ("sustenta", "contradiz", "nada_diz", None):
        if c.get(k):
            print("     %-12s %4d  (%.0f%%)" % (k or "sem resposta", c[k],
                                                100.0 * c[k] / n))
    divergentes = [x for x in linhas if x["jev_relacao"] != "sustenta"]
    print()
    if divergentes:
        print("  ONDE O JEV NÃO VIU SUSTENTAÇÃO — %d caso(s)" % len(divergentes))
        print("  A ancoragem aprovou cada um deles: o trecho EXISTE na página.")
        print("  A pergunta aqui é outra — se ele DIZ o que a resposta afirma.")
        print()
        for x in sorted(divergentes, key=lambda z: -z["jev_confianca"])[:12]:
            print("     %-40s %-4s %-10s conf %.2f"
                  % (x["pasta"][:40], x["id"], x["jev_relacao"],
                     x["jev_confianca"]))
            print("        pergunta: %s" % (x["pergunta"] or "")[:78])
            print("        resposta: %s" % (x["resposta"] or "")[:78])
            print("        trecho .: %s" % (x["trecho"] or "")[:78].replace("\n", " "))
            print()
    else:
        print("  O Jev viu sustentação em TODAS. Isso não prova que estão")
        print("  certas — prova que este segundo sinal não achou nada, o que")
        print("  é informação diferente.")

    print("  custo .......... US$ %.5f  (%s)" % (custo, jev.FONTE_PRECO))
    print("  tempo .......... %.1f s em %d chamadas (%.0f ms cada)"
          % (segundos, n, 1000.0 * segundos / max(1, n)))
    if falhas:
        print("  falhas ......... %d" % falhas)

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps(
        {"medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
         "pergunta": PERGUNTA, "criterios": CRITERIOS, "modelo": jev.MODELO,
         "contexto": a.contexto, "respostas": n, "por_relacao": dict(c),
         "divergentes": len(divergentes), "usd": round(custo, 6),
         "preco": jev.FONTE_PRECO, "linhas": linhas},
        ensure_ascii=False, indent=1))
    print()
    print("  salvo em saidas/_jev_ancoragem.json")
    print("  NENHUM veredito foi alterado — este script só mede.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
