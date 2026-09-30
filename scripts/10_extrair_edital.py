# -*- coding: utf-8 -*-
"""
Pipeline end-to-end de uma licitação: documentos → 17 respostas → verificação → saídas.

    python 10_extrair_edital.py "ABERTO Pregao - Eletronico - Bertioga-SP"
    python 10_extrair_edital.py <pasta> --modo rag
    python 10_extrair_edital.py <pasta> --simulado      (sem chamar o modelo)

Saídas em saidas/<licitação>/: .xlsx, .md e .json de auditoria.
"""
from __future__ import annotations

import argparse
import os
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

from fopa import extrator, metadados, modelos, pagina, saida, verificador  # noqa: E402
from fopa.verificador import APROVADO, REVISAR, REPROVADO  # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")


def barra(t: str) -> None:
    print("\n" + "=" * 78 + "\n  " + t + "\n" + "=" * 78)


def main() -> int:
    ap = argparse.ArgumentParser(description="Extrai as 17 perguntas de uma licitação")
    ap.add_argument("pasta", help="pasta em amostras/ ou caminho completo")
    ap.add_argument("--modo", choices=["contexto-completo", "rag"], default=None)
    ap.add_argument("--provedor", choices=sorted(modelos.PROVEDORES),
                    default="claude", help="claude (padrão), openai (plano B) ou simulado")
    # O padrão do modelo depende do provedor, então ele só pode ser resolvido
    # DEPOIS do parse. Deixar MODELO_EXTRATOR aqui mandaria "claude-opus-5"
    # para a API do OpenAI e a mensagem de erro seria sobre modelo inexistente.
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--effort", choices=["low", "medium", "high"], default="high",
                    help="esforço de raciocínio (padrão high)")
    ap.add_argument("--lote", type=int, default=6, help="perguntas por requisição")
    ap.add_argument("--k", type=int, default=6, help="páginas recuperadas por pergunta (rag)")
    ap.add_argument("--simulado", action="store_true", help="não chama o modelo")
    ap.add_argument("--saida", default=None)
    a = ap.parse_args()
    a.modelo = a.modelo or modelos.modelo_padrao(a.provedor)

    pasta = a.pasta if os.path.isdir(a.pasta) else os.path.join(AMOSTRAS, a.pasta)
    if not os.path.isdir(pasta):
        print("pasta não encontrada: %s" % pasta)
        return 2

    nome = os.path.basename(pasta.rstrip("\\/"))
    # ENSAIO NAO ESCREVE NA PASTA CANONICA -- e a protecao estava pela metade.
    #
    # Havia ja uma regra dizendo "o ensaio NAO escreve no entregavel", e ela
    # cobria `_metadados.md` e `RELATORIO.html`, que moram em `amostras/`.
    # Nao cobria `saidas/<licitacao>/`, porque o destino era calculado ANTES,
    # nesta linha, e com `--simulado` sem `--saida` ele era a pasta canonica.
    #
    # O custo apareceu em 23/09/2026: testando os comandos do README, rodei
    # `10_extrair_edital.py "ABERTO Pregao - Eletronico - Bertioga-SP"
    # --simulado` e isso sobrescreveu a auditoria de PRODUCAO de Bertioga --
    # a licitacao mais estudada do projeto, a unica com gabarito humano
    # conferido a mao. 16 aprovadas de 17 viraram 17 respostas sinteticas de
    # confianca baixa. Nao houve aviso.
    #
    # Os numeros sobreviveram no `_harness_*.json`; a evidencia por resposta
    # (arquivo, pagina, trecho literal) nao, e so se recupera rodando o
    # extrator de novo.
    #
    # Agora o simulado tem pasta propria. Um ensaio que destroi o resultado
    # real nao e ensaio.
    if a.simulado and not a.saida:
        destino = os.path.join(SAIDAS, "_ensaio_simulado", nome)
        print("  saida .......... %s" % os.path.relpath(destino, RAIZ))
        print("                   (--simulado nunca escreve na pasta canônica)")
    else:
        destino = a.saida or os.path.join(SAIDAS, nome)

    barra("FOPA — extração de edital")
    print("  licitação ...... %s" % nome)
    print("  provedor ....... %s" % ("simulado" if a.simulado else a.provedor))
    print("  modelo ......... %s" % ("simulado" if a.simulado else a.modelo))
    # o effort e impresso mesmo no simulado: e o que foi PEDIDO, e e isso que
    # a auditoria grava. `provedor: simulado` ja diz ao leitor que foi ignorado.
    print("  effort ......... %s%s" % (a.effort, "  (ignorado pelo simulado)" if a.simulado else ""))
    print("  modo ........... %s" % (a.modo or "automático (por tamanho)"))

    barra("1/4  Lendo documentos")
    t0 = time.time()

    def mostrar(arquivo, diag):
        print("   %-56s %3dp  %7d chars %s"
              % (arquivo[:56], diag.paginas, diag.chars_nativos,
                 "OCR" if diag.requer_ocr else ""))

    try:
        provedor = modelos.obter_provedor(simulado=a.simulado,
                                          provedor=a.provedor)
    except modelos.ErroModelo as e:
        print("\n  %s" % e)
        return 3

    try:
        ext = extrator.extrair(pasta, provedor, modelo=a.modelo, modo=a.modo,
                               lote=a.lote, k_rag=a.k, effort=a.effort,
                               progresso=mostrar)
    except Exception as e:                                   # noqa: BLE001
        print("\n  falhou: %s" % e)
        return 1

    print("\n   %d páginas de %d arquivo(s) em %.1fs"
          % (len(ext.paginas), len(ext.arquivos), time.time() - t0))
    print("   modo escolhido: %s" % ext.modo)

    barra("2/4  Extração — 17 perguntas")
    print("   %s" % ext.uso)

    barra("3/4  Verificação (determinística, sem IA)")
    rel = verificador.verificar(ext)
    print("   %s\n" % rel)
    for r in ext.respostas:
        marca = {APROVADO: "  ", REVISAR: "⚠ ", REPROVADO: "✖ "}[r.veredito]
        print("   %s%-4s %-58s %s" % (marca, r.id, r.resposta.replace("\n", " ")[:58],
                                      r.info[:34]))
    if rel.alertas_globais:
        print()
        for g in rel.alertas_globais:
            print("   ⚠ %s" % g)

    barra("4/4  Saídas")
    try:
        x = saida.escrever_xlsx(ext, rel, os.path.join(destino, "%s.xlsx" % nome))
        print("   planilha ... %s" % os.path.relpath(x, RAIZ))
    except RuntimeError as e:
        print("   planilha ... pulada (%s)" % e)
    n = saida.escrever_nota(ext, rel, os.path.join(destino, "%s.md" % nome))
    j = saida.escrever_json(ext, rel, os.path.join(destino, "auditoria.json"))
    print("   nota ....... %s" % os.path.relpath(n, RAIZ))
    print("   auditoria .. %s" % os.path.relpath(j, RAIZ))
    # realimenta a pasta da licitação com o que foi observado nela
    # O ensaio NAO escreve no entregavel.
    #
    # `_metadados.md` e `RELATORIO.html` moram dentro de `amostras/`, ao lado dos
    # PDFs — e nao em `--saida`. Entao, ate aqui, um `--simulado` sobrescrevia o
    # relatorio real com a saida do localizador por regex: 17 respostas de
    # confianca baixa no lugar das que custaram R$ 4,34 para produzir. Nao havia
    # aviso; so o `git status` denunciava, e so para quem olhasse.
    #
    # A regra e a mais estreita que resolve: quem nao e a execucao canonica da
    # licitacao le tudo e nao publica nada. Isso cobre DOIS casos, e o segundo
    # so apareceu depois de morder de novo:
    #
    #   --simulado   o localizador por regex substituia respostas que custaram
    #                R$ 4,34, com 17 itens de confianca baixa.
    #   --saida X    uma execucao de COMPARACAO (outro provedor, outro modelo,
    #                outro k) manda as planilhas para X e mesmo assim publicava
    #                o relatorio por cima do canonico. Comparar dois provedores
    #                destruia o resultado do primeiro.
    ensaio = a.simulado or bool(a.saida)
    if ensaio:
        motivo = ("ensaio simulado" if a.simulado
                  else "execução de comparação (--saida)")
        print("   metadados .. (pulado: %s não escreve no entregável)" % motivo)
        print("   relatório .. (pulado: %s não escreve no entregável)" % motivo)
    else:
        m = metadados.atualizar(pasta, ext, rel)
        print("   metadados .. %s  (observações do pipeline)" % os.path.relpath(m, RAIZ))
        # o HTML fica JUNTO dos PDFs para que os links relativos abram na página
        h = pagina.escrever(ext, rel, os.path.join(pasta, "RELATORIO.html"))
        print("   relatório .. %s  (clique no Info abre o PDF na página)"
              % os.path.relpath(h, RAIZ))

    if a.simulado:
        print("\n   custo total desta extração: R$ 0,000  (nenhuma chamada de modelo)")
    elif ext.uso.preco_conhecido:
        print("\n   custo total desta extração: R$ %.3f\n" % ext.uso.brl)
    else:
        # "R$ 0,000" aqui seria enganoso: a chamada foi cobrada, só falta
        # a tabela para converter token em dinheiro.
        print("\n   custo: %s tokens de entrada e %s de saída — preço de %s não"
              % (f"{ext.uso.entrada + ext.uso.cache_leitura:,}".replace(",", "."),
                 f"{ext.uso.saida:,}".replace(",", "."), ext.uso.modelo))
        print("   configurado, então não há R$ a exibir (ver FOPA_PRECO_* no .env)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
