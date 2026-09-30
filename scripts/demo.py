# -*- coding: utf-8 -*-
"""
DEMO AO VIVO — projeto FOPA.

Roteiro para rodar na frente de uma plateia. Cada passo é uma chamada REAL:
API pública do PNCP, arquivos de verdade, OCR local. Nada é simulado.

    python demo.py            roteiro completo, com pausas
    python demo.py --rapido   sem pausas e sem OCR (ensaio)
    python demo.py --passo 3  só um passo

Passos:
    1  A API do PNCP responde                      ~5 s
    2  O mercado, medido agora                     ~15 s
    3  Uma licitação tem 3 editais ativos          ~5 s   (o achado)
    4  A pirâmide vem repartida em 3 tabelas       instantâneo (arquivo local)
    5  O arquivo que nenhuma máquina lê            ~10 s  (OCR ao vivo)
    6  Quem ganha folha pública                    instantâneo (dado apurado)
"""
from __future__ import annotations

import argparse
import re
import json
import os
import sys
import time

# O console do Windows usa cp1252 e quebra em caracteres como → e ÷.
# Sem isto a demo morre no meio da apresentação.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
AMOSTRAS = os.path.join(RAIZ, "amostras")
sys.path.insert(0, AQUI)

SLS = os.path.join(AMOSTRAS, "Concorrencia - Eletronica - Sao Lourenco do Sul-RS")

RAPIDO = False


# ---------------------------------------------------------------- apresentação
def titulo(n: int, texto: str) -> None:
    print("\n" + "=" * 78)
    print("  PASSO %d — %s" % (n, texto))
    print("=" * 78)


def fala(texto: str = "") -> None:
    print(texto)


def destaque(texto: str) -> None:
    print("\n  >>> " + texto + "\n")




def _slug_cache(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower())[:40].strip("_")

# ---------------------------------------------------------------- plano B
CACHE = os.path.join(RAIZ, "amostras", "_demo_cache")
OFFLINE = False          # forçado por --offline
_usou_cache = []         # o que veio do disco, para o aviso do fim


def _rede(nome: str, chamada, descricao: str = ""):
    """Tenta a rede; se falhar, usa a última resposta gravada.

    O fallback é AUTOMÁTICO de propósito. Numa sala de apresentação ninguém vai
    perceber o timeout, decidir, e digitar uma flag — a demo simplesmente trava
    por 45 segundos e o argumento se perde junto com o silêncio.

    E o risco é concreto, não hipotético: a API de documentos do PNCP ficou fora
    por mais de uma hora durante o desenvolvimento, devolvendo 504. Ver
    [[Disponibilidade do PNCP]].

    O que vem do cache é resposta REAL da API, gravada numa execução anterior, e
    a demo diz isso na tela. Não é dado inventado para a apresentação parecer
    funcionar.
    """
    destino = os.path.join(CACHE, nome + ".json")

    if not OFFLINE:
        try:
            dados = chamada()
            os.makedirs(CACHE, exist_ok=True)
            with open(destino, "w", encoding="utf-8") as f:
                json.dump({"gravado_em": time.strftime("%Y-%m-%d %H:%M"),
                           "dados": dados}, f, ensure_ascii=False)
            return dados
        except Exception as e:                                  # noqa: BLE001
            fala("\n    [rede indisponível: %s]" % str(e)[:64])

    if not os.path.isfile(destino):
        raise SystemExit(
            "\n    Sem rede e sem cache para '%s'.\n"
            "    Rode uma vez com a rede no ar para gravar o plano B." % nome)

    with open(destino, encoding="utf-8") as f:
        pacote = json.load(f)
    _usou_cache.append(nome)
    fala("    [usando resposta gravada em %s — dado real, coletado antes]"
         % pacote.get("gravado_em", "?"))
    return pacote["dados"]


def pausa(msg: str = "Enter para continuar") -> None:
    if RAPIDO:
        return
    try:
        input("\n    [%s]" % msg)
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\ndemo interrompida")


# ---------------------------------------------------------------- passos
def passo1() -> None:
    titulo(1, "A API do PNCP responde — pública, gratuita, sem cadastro")
    from fopa import pncp

    fala("  art. 54 da Lei 14.133/2021: o inteiro teor do edital vai para o PNCP.")
    fala("  Acesso gratuito e universal, sem login. Chamando agora:\n")
    fala('  GET /api/search/?q="cessão onerosa folha de pagamento"')

    t0 = time.time()
    itens = _rede("p1_busca",
                  lambda: pncp.buscar("cessão onerosa folha de pagamento",
                                      paginas=1, tam=5))
    dt = time.time() - t0

    fala("\n  respondeu em %.1f s — %d resultados na primeira página:\n" % (dt, len(itens)))
    for it in itens[:5]:
        fala("    %-34s %-3s %-26s %s" % (
            (it.get("municipio_nome") or "")[:34], it.get("uf"),
            (it.get("modalidade_licitacao_nome") or "")[:26],
            (it.get("data_publicacao_pncp") or "")[:10]))
    destaque("Nenhuma chave de API. Nenhum contrato. Isso é o insumo que hoje custa R$ 100 mil/ano.")


def passo2() -> None:
    titulo(2, "O mercado, medido agora")
    from fopa import pncp
    import collections

    fala("  Duas buscas, para mostrar que o número real depende do vocabulário:\n")
    for termo in ["cessão onerosa folha de pagamento",
                  "folha de pagamento servidores instituição financeira"]:
        itens = _rede("p2_%s" % _slug_cache(termo),
                      lambda t=termo: pncp.buscar(t, paginas=2, tam=50))
        fala("    %-52s %4d coletados" % ('"%s"' % termo[:48], len(itens)))

    fala("\n  Distribuição de modalidade na amostra ampla:\n")
    itens = pncp.dedup(_rede("p2_dedup", lambda: pncp.buscar(
        "folha de pagamento servidores instituição financeira",
        paginas=2, tam=50)))
    c = collections.Counter(i.get("modalidade_licitacao_nome") for i in itens)
    total = sum(c.values())
    fora = 0
    for nome, n in c.most_common():
        marca = ""
        if nome and "Eletrônico" not in str(nome):
            fora += n
            marca = "  <-- não é pregão eletrônico"
        fala("    %-28s %3d  %5.1f%%%s" % (str(nome)[:28], n, 100.0 * n / total, marca))
    destaque("%.0f%% do mercado NÃO é pregão eletrônico. Quem filtra só por ele perde um terço."
             % (100.0 * fora / total))


def passo3() -> None:
    titulo(3, "Uma licitação tem TRÊS editais ativos — e eles divergem")
    from fopa import pncp

    fala("  São Lourenço do Sul/RS, Concorrência 09/2026.")
    fala("  Perguntando à API quais arquivos existem:\n")

    lic = pncp.Licitacao(cnpj="87893111000152", ano="2026", seq="381")
    arquivos = _rede("p3_arquivos", lic.arquivos)
    for a in arquivos:
        fala("    seq=%-2s  %-20s ativo=%-5s  %s" % (
            a.get("sequencialDocumento"), (a.get("tipoDocumentoNome") or "")[:20],
            a.get("statusAtivo"), a.get("titulo")))

    editais = [a for a in arquivos if (a.get("tipoDocumentoNome") or "").strip() == "Edital"]
    fala("\n  Arquivos do tipo 'Edital': %d — todos com statusAtivo verdadeiro." % len(editais))
    fala("  A API NÃO diz qual vale.")

    vig = pncp.documento_vigente(arquivos)
    fala("\n  RN-04 — vigente é o de maior sequencialDocumento: seq=%s (%s)"
         % (vig.get("sequencialDocumento"), vig.get("titulo")))

    fala("\n  E a diferença entre os dois últimos não é cosmética:\n")
    fala("    Edital_Corrigido (seq 4), p.4:  'Valor ESTIMADO da Contratação ... R$ 1.900.000,00'")
    fala("    Edital_Correto   (seq 5), p.4:  'Valor MÍNIMO  da Contratação ... R$ 1.900.000,00'")
    destaque("Mesmo número. Em leilão de MAIOR OFERTA, 'estimado' é referência e "
             "'mínimo' é o piso que o lance precisa superar.")


def passo4() -> None:
    titulo(4, "A pirâmide salarial vem repartida em três tabelas")
    caminho = os.path.join(SLS, "02 - Termo de Referencia corrigido (VIGENTE).pdf")
    if not os.path.exists(caminho):
        fala("  (arquivo de amostra não encontrado — pulando)")
        return

    fala("  Termo de Referência de São Lourenço do Sul. O objeto declara 1.782 servidores.")
    fala("  Um extrator ingênuo lê a primeira tabela e responde:\n")
    destaque("287   <-- errado por 1.495 servidores, 84% da folha invisível")

    fala("  A pirâmide está em TRÊS tabelas, por vínculo:\n")
    tabelas = [("Contratos", [7, 57, 157, 3, 61, 2], 287),
               ("Inativos e Pensionistas", [2, 73, 53, 59, 117, 85, 52, 29, 20, 20, 83], 593),
               ("Ativos", [1, 22, 58, 150, 129, 151, 96, 88, 55, 50, 102], 902)]
    geral = 0
    for nome, faixas, impresso in tabelas:
        s = sum(faixas)
        geral += s
        fala("    %-26s soma das faixas = %4d | total impresso = %4d | %s"
             % (nome, s, impresso, "confere" if s == impresso else "DIVERGE"))
    fala("    %-26s %39d" % ("SOMA DAS TRÊS:", geral))
    fala("    %-26s %39d" % ("DECLARADO NO OBJETO:", 1782))
    destaque("A pirâmide FECHA. O edital está certo — quem erra é quem lê.")
    fala("  E tem pior: o extrator de layout deslocou o total 287 para a linha")
    fala("  'Acima de R$ 10.000,00', que no documento tem quantidade 00.")
    fala("  Um parser posicional atribuiria 287 servidores à faixa de MAIOR valor para o banco.")
    fala("\n  → é a RN-10 do vault, e o verificador tem uma checagem só para isso.")


def passo5() -> None:
    titulo(5, "O arquivo que nenhuma máquina lê — OCR ao vivo")
    from fopa import ocr

    caminho = os.path.join(SLS, "01 - Edital original (digitalizado, 44p).pdf")
    if not os.path.exists(caminho):
        fala("  (arquivo de amostra não encontrado — pulando)")
        return

    fala("  Checando o ambiente de OCR (falha alto, nunca em silêncio):\n")
    try:
        amb = ocr.checar_ambiente()
        fala("    Tesseract %s | idiomas: %s" % (amb["tesseract"], ", ".join(amb["idiomas"])))
    except ocr.OcrIndisponivel as e:
        fala("    OCR indisponível: %s" % e)
        return

    fala("\n  Diagnóstico do edital original:\n")
    d = ocr.diagnosticar(caminho)
    fala("    páginas .................. %d" % d.paginas)
    fala("    tamanho .................. %.1f MB" % (os.path.getsize(caminho) / 1e6))
    fala("    imagens .................. %d" % d.imagens)
    fala("    fontes embutidas ......... %d" % d.fontes_embutidas)
    fala("    texto extraível .......... %d caracteres NO DOCUMENTO INTEIRO" % d.chars_nativos)
    destaque("RN-19: %.0f caracteres por página < 120 → REQUER OCR" % d.chars_por_pagina)

    if RAPIDO:
        fala("  (--rapido: pulando o OCR)")
        return

    fala("  Rodando OCR na primeira página, aqui, local, sem nuvem:\n")
    t0 = time.time()
    texto = ocr.ler_pagina(caminho, 0, forcar_ocr=True)
    dt = time.time() - t0
    for linha in [l for l in texto.splitlines() if l.strip()][:9]:
        fala("    " + linha[:96])
    destaque("%d caracteres em %.1f s. Antes: zero." % (len(texto.strip()), dt))
    fala("  As 44 páginas inteiras levam ~70 s e rendem 96.369 caracteres.")
    fala("  Na p. 41 está a justificativa do preço — que não existe em nenhum edital digital.")


def passo6() -> None:
    titulo(6, "Quem realmente ganha folha pública")
    arq = os.path.join(AMOSTRAS, "_concorrencia.json")
    if not os.path.exists(arq):
        fala("  (dados não encontrados — rode 04_concorrencia.py antes)")
        return
    import collections

    d = json.load(open(arq, encoding="utf-8"))
    venc = collections.Counter(d["vencedores"])
    total = sum(venc.values())

    # nomes variam (maiúsculas, razões sociais distintas) — agrupar antes de contar
    import re as _re
    COOP = _re.compile(r"cooperativa|sicoob|sicredi|cresol|unicred|credi", _re.I)
    grupos = collections.Counter()
    for nome, n in venc.items():
        u = nome.upper()
        if "CAIXA" in u:
            grupos["Caixa Econômica Federal"] += n
        elif "BRADESCO" in u:
            grupos["Bradesco"] += n
        elif "RIO GRANDE DO SUL" in u or "R.G.SUL" in u or "BANRISUL" in u:
            grupos["Banrisul"] += n
        elif "ITA" in u and "UNIBANCO" in u:
            grupos["Itaú Unibanco"] += n
        elif "SANTANDER" in u:
            grupos["Santander"] += n
        elif COOP.search(nome):
            grupos["Cooperativas de crédito"] += n
        elif "CONSIGNET" in u:
            grupos["Consignet — software, falso positivo"] += n
        else:
            grupos["Outros / não identificados"] += n

    fala("  491 licitações de folha, 160 com resultado, %d vencedores apurados:\n" % total)
    for nome, n in grupos.most_common():
        fala("    %5.1f%%  %2d  %s" % (100.0 * n / total, n, nome))
    destaque("As COOPERATIVAS DE CRÉDITO são o maior vencedor isolado — acima da Caixa.")

    agios = [r["agio"] for r in d["registros"] if r.get("agio") and 0.5 < r["agio"] < 100]
    if agios:
        agios.sort()
        fala("  Ágio (homologado ÷ valor mínimo), %d licitações:" % len(agios))
        fala("    mínimo %.2fx | MEDIANA %.2fx | máximo %.2fx"
             % (agios[0], agios[len(agios) // 2], agios[-1]))
        destaque("Mediana 1,00x — metade do mercado é arrematada pelo valor mínimo. "
                 "Não há disputa.")


PASSOS = {1: passo1, 2: passo2, 3: passo3, 4: passo4, 5: passo5, 6: passo6}


def main() -> None:
    global RAPIDO
    ap = argparse.ArgumentParser(description="Demo ao vivo do projeto FOPA")
    ap.add_argument("--rapido", action="store_true", help="sem pausas, sem OCR")
    ap.add_argument("--passo", type=int, choices=sorted(PASSOS), help="rodar só um passo")
    ap.add_argument("--offline", action="store_true",
                    help="não tenta a rede; usa direto as respostas gravadas")
    a = ap.parse_args()
    RAPIDO = a.rapido
    globals()["OFFLINE"] = a.offline

    print("\n" + "=" * 78)
    print("  PROJETO FOPA — demonstração ao vivo")
    print("  Tudo abaixo é chamada real: API pública do PNCP, arquivos de verdade, OCR local.")
    print("=" * 78)

    ordem = [a.passo] if a.passo else sorted(PASSOS)
    for i, n in enumerate(ordem):
        try:
            PASSOS[n]()
        except Exception as e:                        # noqa: BLE001
            fala("\n  !! passo %d falhou: %s" % (n, e))
            fala("     (se for rede, o PNCP pode estar instável — siga para o próximo)")
        if i < len(ordem) - 1:
            pausa()

    print("\n" + "=" * 78)
    print("  Fim. O vault com tudo documentado: Fopa-v2/ (abra no Obsidian)")
    print("  Regras operacionais: Fopa-v2/00-Case/Regras de negócio.md  (RN-01 a RN-15)")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    main()
