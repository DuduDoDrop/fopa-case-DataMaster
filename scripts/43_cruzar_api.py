# -*- coding: utf-8 -*-
"""
Cruza a resposta do modelo com o campo estruturado da API do PNCP.

    python 43_cruzar_api.py

NÃO CHAMA MODELO. Lê `auditoria.json` do disco e consulta a API pública.

POR QUE ISTO VALE MAIS QUE A ANCORAGEM SOZINHA
  A ancoragem responde *"o trecho citado existe naquela página?"*. É forte, mas
  é uma verificação **interna**: confere a resposta contra o mesmo documento de
  onde ela saiu. Se o modelo lesse a tabela errada do edital e citasse
  corretamente essa tabela errada, a ancoragem aprovaria — e estaria certa em
  aprovar, porque o trecho está lá.

  Duas das 17 perguntas têm resposta também num campo estruturado que o órgão
  preencheu **à parte**, no formulário do PNCP:

    Q4 (critério de julgamento) ←→ `criterioJulgamentoNome`
    Q5 (valor mínimo)           ←→ `valorTotal`

  Isso é uma **segunda fonte independente**. O órgão digitou o valor no
  formulário e escreveu o valor no PDF; se os dois batem com o que o modelo
  leu, não foi acerto casual de citação.

  É o mesmo princípio da ADR-004 levado um passo adiante: lá, quem verifica não
  pode ser quem responde. Aqui, **contra o que se verifica** também não pode
  ser só o que o modelo escolheu ler.

  Medido em 23/09/2026: **11 de 11 em Q4 e 9 de 9 em Q5** (2 sem valor na
  API). O "6 de 6" anterior comparava so a PRIMEIRA PALAVRA do criterio --
  "maior" -- entao "Maior lance" contra "Maior desconto" dava OK. Ver as
  extrações
  cujo inventário guarda o número de controle.

ARMADILHA QUE ESTE ARQUIVO JÁ CAIU
  A primeira versão deste cruzamento acusou Quevedos/RS de divergir: modelo
  R$ 323.725,10, API `323725.1`. O modelo estava certo e o comparador errado —
  a API devolve float com UM decimal, e o regex exigia dois, truncando para
  `323725`.

  Um comparador frouxo produz falso alarme, que é o modo de falha mais caro
  numa ferramenta de auditoria: ensina o operador que o alarme mente.
"""
from __future__ import annotations

import glob
import io
import json
import os
import re
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")
sys.path.insert(0, AQUI)

from fopa.verificador import familia_criterio   # noqa: E402
from fopa import execucao, inventario, pncp  # noqa: E402

# 1.234.567,89 · 1234,56 · 1234.56 · 1234
RE_VALOR = re.compile(r"(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}|\d[\d.]*)")


def valor_de(texto: str) -> float | None:
    """O primeiro valor monetário de um texto em português, como float."""
    m = RE_VALOR.search(str(texto or ""))
    if not m:
        return None
    v = m.group(1)
    if "," in v:                       # 1.234.567,89 -> 1234567.89
        v = v.replace(".", "").replace(",", ".")
    elif v.count(".") > 1:             # 1.234.567 -> 1234567
        v = v.replace(".", "")
    try:
        return round(float(v), 2)
    except ValueError:
        return None


RE_FOLHA_ITEM = re.compile(
    r"folha\s+de\s+pagamento|folha\s+de\s+sal[áa]rio|cess[ãa]o\s+onerosa|"
    r"cr[ée]ditos?\s+(?:provenientes\s+)?da\s+folha|pagamento\s+d[oe]s?\s+servidor",
    re.I)


def item_da_folha(itens: list[dict]) -> dict:
    """
    Entre os itens da licitação, o que é da FOLHA — e não simplesmente o primeiro.

    POR QUE `itens[0]` NÃO SERVE
      Osório/RS licita **dois módulos** no mesmo pregão:

        item 1 · BAIXA DE BOLETOS DE COBRANÇA IPTU E TAXAS   (Módulo B)
        item 2 · MÓDULO A - FOLHA DE PAGAMENTO               (Módulo A)

      O item da folha é o **segundo**. Quem pegar `itens[0]` compara a resposta
      do modelo contra o valor dos boletos de IPTU, acusa divergência de três
      ordens de grandeza, e conclui que o modelo errou.

      São 4 licitações com mais de um item em 175. Três delas são **duplicata
      de cadastro** — Espigão d'Oeste/RO tem `CONTRATAÇÃO DE INSTITUIÇÃO
      FINANCEIRA` e `CONTRATAÇÃO DE INSTITUIÇÃO FINANCEIRAA`, com dois As.
      Nessas, qualquer item serve. Osório é o único multi-módulo real.

      Um caso em 175 não justifica ignorar: justifica uma linha de código.
    """
    if not itens:
        return {}
    if len(itens) == 1:
        return itens[0]
    com_folha = [it for it in itens
                 if RE_FOLHA_ITEM.search(str(it.get("descricao") or ""))]
    if len(com_folha) == 1:
        return com_folha[0]
    # empate (duplicata de cadastro) ou nenhum: o de quantidade 1 tem
    # precedência, porque item com unidade própria não é o contrato inteiro
    for grupo in (com_folha or itens):
        q = grupo.get("quantidade")
        if q is not None and abs(float(q) - 1.0) < 0.001:
            return grupo
    return (com_folha or itens)[0]


def controle_de(auditoria: dict, pasta: str) -> str:
    # Ver o comentario em 45_retificacoes.py: `fopa/inventario` normaliza os
    # apelidos, entao `controle` aparece mesmo nas pastas do esquema antigo
    # do monitor, que gravava `numero_controle`.
    for cand in (auditoria.get("licitacao") or pasta, pasta):
        inv = inventario.ler(os.path.join(AMOSTRAS, cand))
        if inv:
            c = (inv.get("controle") or "").strip()
            if c:
                return c
    return ""


def main() -> int:
    _t0 = time.time()
    print("=" * 84)
    print("  CRUZAMENTO — resposta do modelo × campo estruturado do PNCP")
    print("=" * 84)
    print("  %-42s %-13s %-11s %s" % ("licitação", "Q5 modelo", "API", "Q5/Q4"))
    print("  " + "-" * 82)

    placar = {"q5_ok": 0, "q5_dif": 0, "q5_sem": 0,
              "q4_ok": 0, "q4_dif": 0, "q4_sem": 0, "sem_controle": 0}
    divergencias, registros = [], []

    for f in sorted(glob.glob(os.path.join(SAIDAS, "*", "auditoria.json"))):
        pasta = os.path.basename(os.path.dirname(f))
        if pasta.startswith("_"):
            continue
        d = json.load(io.open(f, encoding="utf-8"))
        ctrl = controle_de(d, pasta)
        if not ctrl:
            placar["sem_controle"] += 1
            print("  %-42s (inventário sem número de controle)" % pasta[:42])
            continue
        try:
            itens = pncp.Licitacao.de_controle(ctrl).itens()
        except Exception as e:                                    # noqa: BLE001
            print("  %-42s ERRO %s" % (pasta[:42], str(e)[:28]))
            continue

        it = item_da_folha(itens)
        resp = {r.get("id"): (r.get("resposta") or "") for r in d.get("respostas", [])}

        modelo5 = valor_de(resp.get("Q5"))
        api5 = it.get("valorTotal")
        api5 = round(float(api5), 2) if api5 is not None else None

        # `valorTotal` SÓ É DINHEIRO QUANDO `quantidade` É 1.
        #
        # Santa Efigênia de Minas/MG registra `quantidade = 389`,
        # `unidadeMedida = "SERVIDOR"` e `valorUnitarioEstimado = 1,00` — então
        # `valorTotal = 389,00` não são reais, são **servidores**. Comparar a
        # resposta de Q5 contra isso acusaria o modelo de errar por três ordens
        # de grandeza, quando o modelo estava certo: o edital diz que "a
        # proposta de preços não será necessária, visto que o objeto deste
        # certame é gratuito", e foi isso que ele respondeu, com o trecho
        # ancorado.
        #
        # Falso alarme numa ferramenta de auditoria é o modo de falha mais
        # caro: ensina o operador que o alarme mente.
        qtd = it.get("quantidade")
        unidade = (it.get("unidadeMedida") or "").strip()
        if qtd is not None and abs(float(qtd) - 1.0) > 0.001:
            placar["q5_sem"] += 1
            s5 = "n/a (qtd %s %s)" % (qtd, unidade[:12])
            modelo5 = api5 = None
        elif modelo5 is None or api5 is None:
            placar["q5_sem"] += 1; s5 = "s/dado"
        elif abs(modelo5 - api5) <= 0.01:
            placar["q5_ok"] += 1; s5 = "OK"
        else:
            placar["q5_dif"] += 1; s5 = "DIVERGE"
            divergencias.append((pasta, "Q5", modelo5, api5))

        q4 = resp.get("Q4", "")
        api4 = it.get("criterioJulgamentoNome") or ""
        if not q4 or "ão localizado" in q4 or not api4:
            placar["q4_sem"] += 1; s4 = "s/dado"
        else:
            # COMPARAR FAMILIA, NAO PALAVRA.
            #
            # A versao anterior comparava so a PRIMEIRA palavra
            # (`api4.lower().split()[0]`), que para todo criterio de oferta e
            # "maior". Com isso "MAIOR LANCE" contra "Maior desconto" dava OK
            # -- criterios genuinamente diferentes passando como iguais. Foi
            # essa regra que produziu o "6 de 6 conferem" desta nota.
            #
            # `familia_criterio` sabe que maior oferta / maior lance / maior
            # preco ofertado sao a MESMA coisa, e que maior desconto e menor
            # preco sao OUTRAS.
            fd, fa = familia_criterio(q4), familia_criterio(api4)
            if fd and fa and fd == fa:
                placar["q4_ok"] += 1; s4 = "OK"
            elif fd and fa == "nao_se_aplica":
                # A API nao declara criterio (contratacao direta) e o edital
                # declara. Documento mais informativo que a API nao e
                # divergencia.
                placar["q4_ok"] += 1; s4 = "OK (só no doc)"
            elif fd and fa:
                placar["q4_dif"] += 1; s4 = "DIVERGE"
                divergencias.append((pasta, "Q4", "%s (%s)" % (q4[:30], fd), api4))
            else:
                placar["q4_sem"] += 1; s4 = "s/familia"

        print("  %-42s %-13s %-11s %s / %s"
              % (pasta[:42], str(modelo5)[:13], str(api5)[:11], s5, s4))
        registros.append({"pasta": pasta, "controle": ctrl,
                          "q5_modelo": modelo5, "q5_api": api5, "q5": s5,
                          "q4_modelo": q4[:120], "q4_api": api4, "q4": s4})
        time.sleep(0.25)

    print()
    print("  Q5 × valorTotal .............. %d OK · %d diverge · %d sem dado"
          % (placar["q5_ok"], placar["q5_dif"], placar["q5_sem"]))
    print("  Q4 × criterioJulgamentoNome .. %d OK · %d diverge · %d sem dado"
          % (placar["q4_ok"], placar["q4_dif"], placar["q4_sem"]))
    if placar["sem_controle"]:
        print("  %d extração(ões) sem número de controle no inventário —"
              % placar["sem_controle"])
        print("  são as pastas coletadas à mão no início do projeto (ADR-013).")
    if divergencias:
        print("\n  DIVERGÊNCIAS — conferir à mão antes de concluir que o modelo errou:")
        for p, q, m, a in divergencias:
            print("   %-40s %s: modelo %s | API %s" % (p[:40], q, m, a))

    execucao.registrar("43_cruzar_api.py", _t0,
                       q5_ok=placar["q5_ok"], q5_diverge=placar["q5_dif"],
                       q4_ok=placar["q4_ok"], q4_diverge=placar["q4_dif"])
    destino = os.path.join(SAIDAS, "_cruzamento_api.json")
    json.dump({"medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "placar": placar, "registros": registros},
              io.open(destino, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n  salvo: %s" % os.path.relpath(destino, RAIZ))
    print("  custo em API de modelo: R$ 0,00")
    return 1 if divergencias else 0


if __name__ == "__main__":
    raise SystemExit(main())
