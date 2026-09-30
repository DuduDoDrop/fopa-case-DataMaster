# -*- coding: utf-8 -*-
"""
Reverifica as execuções de uma comparação do harness — SEM chamar o modelo.

O 13_reverificar.py cuida das extrações de produção (saidas/<licitação>/). Este
cuida das COMPARAÇÕES (saidas/_harness_<licitação>.json), que guardam várias
configurações do mesmo edital lado a lado.

Por que existe: a primeira comparação entre modelos deu ancoragem 0/13 para o
Haiku 4.5. O trecho citado por ele estava certo e era literal; o que não batia
era o NOME DO ARQUIVO — ele cita "EDITAL.pdf", o arquivo é "01 - Edital -
EDITAL.pdf". O número media o verificador, não a leitura do modelo.

Corrigida a resolução do nome, a pergunta passa a ser: quanto daquele resultado
era defeito de medição? Responder isso re-executando custaria de novo, e traria
junto a variância da geração — duas mudanças de uma vez, nenhuma conclusão.
Como o Verificador é determinístico e as páginas vêm do OCR local, dá para
remedir a MESMA extração com a regra nova, de graça e sem ruído.

    python 14_reverificar_harness.py                   todas as comparações
    python 14_reverificar_harness.py --so Pirapo       filtra por licitação
"""
from __future__ import annotations

import argparse
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

from fopa import extrator, metadados, pagina, saida, verificador  # noqa: E402
from fopa.modelos import Uso                    # noqa: E402
from fopa.questionario import POR_ID            # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")
PREFIXO = "_harness_"


def reconstruir(execucao: dict, paginas: list) -> extrator.Extracao:
    """Remonta a Extracao a partir do que o harness salvou + páginas do disco."""
    respostas = []
    evid = execucao.get("evidencia", {})
    for pid, texto in execucao.get("respostas", {}).items():
        ev = evid.get(pid, {})
        respostas.append(extrator.Resposta(
            id=pid,
            pergunta=POR_ID[pid].texto if pid in POR_ID else "",
            resposta=texto,
            arquivo=ev.get("arquivo"),
            pagina=ev.get("pagina"),
            trecho_literal=ev.get("trecho"),
            pagina_citada=ev.get("pagina_citada")))
    respostas.sort(key=lambda r: int(r.id[1:]))
    return extrator.Extracao(
        licitacao=execucao.get("rotulo", ""),
        respostas=respostas, paginas=paginas,
        modo=execucao.get("modo", ""),
        uso=Uso(modelo=execucao.get("modelo", "")),
        arquivos=sorted({p.arquivo for p in paginas}))



def _promover(licitacao: str, pasta: str, ex: dict,
              extracao, relatorio) -> str:
    """Materializa uma execução da comparação como entregável de produção.

    Uma comparação já pagou pela extração: as respostas, a evidência e o uso de
    tokens estão salvos. O que faltava era só ESCREVER as saídas — planilha,
    nota, auditoria, metadados e relatório HTML — que o harness não gera porque
    seu trabalho é comparar, não entregar.

    Bertioga/SP é o caso que motivou isto: a licitação de referência do README
    perdeu a saída de produção num expurgo, e reexecutar custaria R$ 2,91 para
    obter exatamente o que já estava no disco.
    """
    extracao.licitacao = licitacao
    u = ex.get("uso") or {}
    extracao.uso.entrada = ex.get("entrada", u.get("entrada", 0))
    extracao.uso.saida = ex.get("saida", u.get("saida", 0))
    extracao.uso.modelo = ex.get("modelo", "")
    extracao.uso.segundos = ex.get("seg", 0.0)
    extracao.modo = ex.get("modo", "")

    destino = os.path.join(SAIDAS, licitacao)
    saida.escrever_json(extracao, relatorio, os.path.join(destino, "auditoria.json"))
    saida.escrever_nota(extracao, relatorio,
                        os.path.join(destino, "%s.md" % licitacao))
    try:
        saida.escrever_xlsx(extracao, relatorio,
                            os.path.join(destino, "%s.xlsx" % licitacao))
    except RuntimeError:
        pass
    metadados.atualizar(pasta, extracao, relatorio)
    pagina.escrever(extracao, relatorio, os.path.join(pasta, "RELATORIO.html"))
    return "%s -> saidas/%s/ + RELATORIO.html" % (ex["rotulo"], licitacao)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", default=None, help="trecho do nome da licitação")
    ap.add_argument("--promover", default=None, metavar="ROTULO",
                    help="materializa esta execução como saída de produção "
                         "(ex.: \"opus-5 · high\")")
    a = ap.parse_args()

    arquivos = [n for n in sorted(os.listdir(SAIDAS))
                if n.startswith(PREFIXO) and n.endswith(".json")
                and (not a.so or a.so.lower() in n.lower())] if os.path.isdir(SAIDAS) else []

    if not arquivos:
        print("nenhuma comparação encontrada em saidas/%s*.json" % PREFIXO)
        return 2

    for nome_json in arquivos:
        caminho = os.path.join(SAIDAS, nome_json)
        dados = json.load(open(caminho, encoding="utf-8"))
        licitacao = dados.get("licitacao", "")
        pasta = os.path.join(AMOSTRAS, licitacao)

        print("\n" + "=" * 92)
        print("  %s" % licitacao)
        print("=" * 92)
        if not os.path.isdir(pasta):
            print("  pasta de origem não encontrada — pulando")
            continue

        # o OCR é local: reler é gratuito, e é o que torna a remedição possível
        paginas = extrator.carregar_paginas(pasta)
        print("  %d páginas de %d arquivo(s) relidas do disco\n"
              % (len(paginas), len({p.arquivo for p in paginas})))

        print("%-26s %11s %11s %s" % ("configuração", "antes", "depois", "mudança"))
        print("-" * 92)

        mudou = False
        promovidas = []
        for ex in dados.get("execucoes", []):
            if "evidencia" not in ex:
                print("%-26s  (sem evidência salva — rodada anterior ao registro)"
                      % ex["rotulo"][:26])
                continue
            antes = "%d/%d" % (ex["ancoradas"], ex["respondidas"])
            novo_ext = reconstruir(ex, paginas)
            rel = verificador.verificar(novo_ext)
            depois = "%d/%d" % (rel.ancoradas, rel.respondidas)

            # A evidencia salva tem de acompanhar o numero. Deixar o alerta antigo
            # ao lado da contagem nova produz um arquivo que se contradiz — o
            # defeito exato que o projeto inteiro existe para nao cometer.
            for r in novo_ext.respostas:
                if r.id in ex.get("evidencia", {}):
                    ex["evidencia"][r.id]["veredito"] = r.veredito
                    ex["evidencia"][r.id]["alertas"] = list(r.alertas)

            d = rel.ancoradas - ex["ancoradas"]
            marca = "" if d == 0 else "%+d ancoradas" % d
            if d:
                mudou = True
            print("%-26s %11s %11s %s" % (ex["rotulo"][:26], antes, depois, marca))

            ex["ancoradas"], ex["respondidas"] = rel.ancoradas, rel.respondidas
            ex["taxa"] = round(rel.taxa_ancorada, 4)
            ex["aprovadas"], ex["revisar"] = rel.aprovadas, rel.revisar
            ex["reprovadas"], ex["nao_loc"] = rel.reprovadas, rel.nao_localizado

            if a.promover and ex["rotulo"].startswith(a.promover):
                promovidas.append(_promover(licitacao, pasta, ex, novo_ext, rel))

        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
        print("-" * 92)
        print("  %s · custo em API: R$ 0,00"
              % ("números atualizados" if mudou else "nenhuma mudança"))
        for linha in promovidas:
            print("  promovida a produção: %s" % linha)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
