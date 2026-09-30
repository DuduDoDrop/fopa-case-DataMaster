# -*- coding: utf-8 -*-
"""
Monitor diário — o laço de produto: só processa o que é NOVO.

    python 20_monitor.py --seco         mostra o que faria, sem baixar nem extrair
    python 20_monitor.py                baixa os novos e extrai
    python 20_monitor.py --sem-extrair  baixa e cadastra, extração fica para depois

Pensado para rodar de madrugada e de novo à tarde. O comportamento que importa é
o do dia comum: **não há edital novo, e ele termina em segundos sem gastar nada.**

O LIVRO-RAZÃO
O que separa este script de rodar `12_lote.py` num agendador é `saidas/_livro.json`:
para cada licitação já vista guarda o número de controle do PNCP, quando foi
vista, se foi extraída e quanto custou. Sem ele, a execução das 6h reprocessaria
as 13 licitações da pasta e pagaria de novo por respostas que já estão no disco —
e isso não é hipótese, é o que o lote faz hoje.

O número de controle é a chave certa: é estável, vem do próprio PNCP e não muda
quando o órgão publica uma retificação. O nome da pasta, não — ele é derivado do
órgão e da modalidade, e duas licitações do mesmo município colidiriam.

CUSTO
Consulta ao PNCP: gratuita, sem cadastro (Lei 14.133/2021 art. 54).
Só a extração gasta, e só nas licitações novas.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
import traceback
import unicodedata

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import (escopo, execucao, extrator, metadados, modelos,
                  nomes, pagina, painel, pncp, saida, verificador)  # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")
LIVRO = os.path.join(SAIDAS, "_livro.json")

# Os dois termos que a busca textual do PNCP responde melhor para este objeto.
# Medidos no demo: cobrem as licitações de cessão de folha sem trazer ruído.
TERMOS = (
    "cessão onerosa folha de pagamento",
    "folha de pagamento servidores instituição financeira",
    # "INSTITUICAO BANCARIA", nao "financeira". Tres das cinco licitacoes que
    # a varredura de recall achou e a busca nao -- Pirassununga/SP, Sao Jose
    # dos Campos/SP e Pompeia/SP -- escrevem "bancaria" no objeto.
    # Densidade medida deste termo: 132 de folha em 150 itens (88%), tao boa
    # quanto a dos dois primeiros.
    "folha de pagamento instituição bancária",
    # A varredura de 2026-08 cobrou mais tres, e o monitor leva os dois de
    # maior alcance medido: "creditos da folha" sozinho responde por tres das
    # seis perdidas (Aguas de Chapeco/SC, Pitanga/PR, Bonito/PE), e
    # "folha salarial" e o sinonimo que nenhum termo cobria. O terceiro
    # ("empresa bancaria") fica so no corpus, que varre mais fundo.
    "créditos da folha de pagamento",
    # a frase que os editais realmente usam -- com "provenientes" no
    # meio, que quebra a anterior. 109 ocorrencias no corpus, 100% no
    # escopo. Ver o comentario longo no 24_corpus_escopo.py.
    "créditos provenientes da folha de pagamento",
    "folha salarial instituição financeira",
)

# A classificação mora em `fopa/escopo.py`, com suíte própria em
# `23_testa_escopo.py`. Ficava aqui, inline, e foi assim que Rio Azul/PR entrou:
# um objeto de terceirização de consignações passou, custou uma extração e
# voltou com 6 de 17 perguntas em branco.
#
# Regra que só existe dentro de um script não tem como ser testada contra os
# documentos reais — e foi lendo os doze objetos verdadeiros que o critério
# apareceu.


def classificar(item: dict) -> tuple[bool, str]:
    """Regra antes de IA (ADR-003). Devolve (é do escopo, motivo)."""
    texto = " ".join(str(item.get(c) or "") for c in
                     ("description", "objeto", "objetoCompra", "title"))
    return escopo.avaliar(texto)


def prazo_de(item: dict) -> datetime.date | None:
    """`data_fim_vigencia` é o fim do prazo de propostas."""
    bruto = item.get("data_fim_vigencia") or item.get("dataEncerramentoProposta")
    if not bruto:
        return None
    try:
        return datetime.date.fromisoformat(str(bruto)[:10])
    except (ValueError, TypeError):
        return None


def esta_aberto(item: dict, hoje: datetime.date) -> bool:
    """Licitação com sessão já encerrada não é oportunidade, é histórico.

    Sem este filtro a primeira execução do monitor via 125 editais "novos" — a
    busca textual devolve todo o acervo, não a janela recente. Processá-los
    custaria umas quatro centenas de reais para produzir respostas sobre
    certames que já aconteceram.
    """
    p = prazo_de(item)
    return p is None or p >= hoje



def atualizado_em(item: dict) -> str:
    """Quando o PNCP mexeu nesta licitação pela última vez.

    `data_atualizacao_pncp` vem na PRÓPRIA busca, então comparar com o que está
    no livro custa zero chamada extra. É o que torna a detecção de retificação
    viável num job diário: a alternativa seria consultar `/arquivos` de cada uma
    das 90 conhecidas, todo dia, contra uma API que já provou cair.
    """
    return str(item.get("data_atualizacao_pncp") or "")[:19]


def foi_retificada(item: dict, registro: dict) -> bool:
    """O documento mudou desde a última vez que processamos?

    Este é o furo que o livro-razão criava ao fazer seu trabalho. Evitar
    reprocessar é o que o torna útil — e um edital RETIFICADO tem o mesmo número
    de controle com conteúdo diferente, então seria ignorado para sempre.

    No domínio isso é o pior lugar possível para errar: a D-003 e a D-006 são
    casos de retificação, e em Bertioga a sessão foi SUSPENSA por um comunicado
    publicado depois do edital. Um monitor que ignora retificação erra justamente
    onde o sistema mais vale.
    """
    visto = str(registro.get("atualizado_pncp") or "")
    agora = atualizado_em(item)
    if not agora:
        return False
    if not visto:
        # Registro antigo, de antes deste campo existir. Não dá para saber se
        # mudou; marcar como retificada reprocessaria as 90 de uma vez. Guarda o
        # carimbo agora e compara a partir da próxima execução.
        registro["atualizado_pncp"] = agora
        return False
    return agora > visto


def carregar_livro() -> dict:
    if os.path.isfile(LIVRO):
        try:
            return json.load(open(LIVRO, encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"versao": 1, "licitacoes": {}}


def gravar_livro(livro: dict) -> None:
    os.makedirs(SAIDAS, exist_ok=True)
    livro["atualizado_em"] = datetime.datetime.now().isoformat(timespec="seconds")
    with open(LIVRO, "w", encoding="utf-8") as f:
        json.dump(livro, f, ensure_ascii=False, indent=1)


def semear_do_disco(livro: dict) -> int:
    """Registra o que já está na pasta, para a primeira execução não reprocessar.

    Sem isto, o primeiro `--seco` acusaria 13 licitações "novas" que estão
    extraídas e pagas desde ontem.
    """
    novos = 0
    for nome in sorted(os.listdir(AMOSTRAS)):
        pasta = os.path.join(AMOSTRAS, nome)
        if not os.path.isdir(pasta) or nome.startswith("_"):
            continue
        inv_p = os.path.join(pasta, "_inventario.json")
        if not os.path.isfile(inv_p):
            continue
        try:
            inv = json.load(open(inv_p, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        chave = inv.get("numero_controle") or nome
        if chave in livro["licitacoes"]:
            continue
        extraida = os.path.isfile(os.path.join(SAIDAS, nome, "auditoria.json"))
        livro["licitacoes"][chave] = dict(
            pasta=nome, orgao=inv.get("orgao"), uf=inv.get("uf"),
            municipio=inv.get("municipio"), fim_prazo=inv.get("fim_prazo"),
            visto_em=inv.get("extraido_em") or str(datetime.date.today()),
            # sem carimbo: a primeira execução que vir esta licitação na busca
            # grava o de agora, e a comparação passa a valer a partir dali
            atualizado_pncp="",
            extraida=extraida, origem="semeado do disco")
        novos += 1
    return novos



def _sha_curto(caminho: str) -> str:
    import hashlib
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def baixar_licitacao(item: dict, pasta: str) -> dict:
    """Baixa os arquivos e escreve o `_inventario.json` que o painel consome.

    O inventário não é enfeite: é dele que saem o prazo que ordena o painel, o
    link para o PNCP e a lista de documentos com SHA-256. Um edital baixado sem
    inventário aparece no disco e some do painel.

    Cada arquivo é nomeado `NN - Tipo - TITULO.pdf`, que é o formato que o resto
    do pipeline espera — a ordem de precedência entre Edital, Termo de Referência
    e anexos é lida desse prefixo.
    """
    lic = pncp.Licitacao.de_item(item)
    if lic is None:
        raise ValueError("item sem item_url utilizável")

    # A listagem vem ANTES de criar a pasta, de propósito.
    #
    # Num teste real o PNCP deu timeout justamente aqui, e a pasta já existia:
    # sobrou um diretório vazio em amostras/, que o painel leria como uma
    # licitação sem dado nenhum. Um job que roda sozinho às 5h30 não pode
    # deixar rastro de tentativa frustrada — ele tenta de novo amanhã, e o
    # livro-razão já garante isso ao não registrar o que falhou.
    docs = [d for d in lic.arquivos() if d.get("statusAtivo")]
    docs.sort(key=lambda d: d.get("sequencialDocumento") or 0)
    if not docs:
        raise ValueError("licitação sem arquivo ativo no PNCP")

    os.makedirs(pasta, exist_ok=True)
    baixados, falhos = [], 0
    for d in docs:
        tipo = (d.get("tipoDocumentoNome") or "Outros Documentos").strip()
        titulo = nomes.limpar(d.get("titulo") or "DOCUMENTO").upper()[:60]
        nome = "%02d - %s - %s.pdf" % (d.get("sequencialDocumento") or 0, tipo, titulo)
        destino = os.path.join(pasta, nome)
        try:
            arq = pncp.baixar_arquivo(d, destino)
        except Exception as e:                                  # noqa: BLE001
            falhos += 1
            print("          arquivo %s falhou: %s" % (nome[:40], e))
            continue
        # SHA COMPLETO E A URL DE ORIGEM -- igual ao coletor.
        #
        # Ate 23/09/2026 aqui se gravava `sha` com 16 caracteres e nenhuma
        # `origem`. O coletor grava `sha256` inteiro mais a URL de onde o
        # arquivo veio, e a suite conta a diferenca como "esquema antigo".
        #
        # Nao e formalidade: procedencia verificavel e o argumento central
        # deste projeto. Um PDF com hash truncado e sem URL nao prova de onde
        # veio -- e as 53 licitacoes que o monitor baixou hoje entraram todas
        # assim, levando a divida de 43 para 223 arquivos.
        baixados.append(dict(seq=arq.seq, tipo=arq.tipo, titulo=arq.titulo,
                             kb=round(arq.bytes / 1024),
                             sha256=arq.sha256, origem=getattr(arq, "origem", None)
                             or d.get("url"),
                             arquivo=nome))

    # Nenhum arquivo desceu: a pasta não serve para nada e não fica.
    if not baixados:
        try:
            os.rmdir(pasta)
        except OSError:
            pass
        raise ValueError("nenhum dos %d arquivo(s) pôde ser baixado" % len(docs))

    inv = dict(
        incompleto=bool(falhos),
        arquivos_que_falharam=falhos,
        modalidade=item.get("modalidade_licitacao_nome") or "",
        orgao=item.get("orgao_nome") or "",
        uf=item.get("uf") or "",
        municipio=item.get("municipio_nome") or "",
        # OS DOIS NOMES, ATE O ESQUEMA SER UNIFICADO.
        #
        # O coletor grava `controle`, `publicado_em` e `escopo`; o monitor
        # gravava `numero_controle` e `data_publicacao`. Os dois programas
        # escrevem o MESMO arquivo, `_inventario.json`, com chaves diferentes.
        #
        # Em 23/09/2026 isso saiu do papel: o monitor baixou 53 licitacoes e a
        # suite acusou "223 arquivos no esquema antigo", contra um teto de 43.
        # Toda medicao que usa o numero de controle como IDENTIDADE (ADR-013)
        # simplesmente nao enxergava essas 53.
        #
        # Duplicar campo e feio e e o menor conserto que restaura a leitura de
        # todo mundo hoje. A unificacao num `fopa/inventario.py` continua em
        # BACKLOG.md como decisao pendente -- e e ela que apaga esta duplicata.
        numero_controle=item.get("numero_controle_pncp") or "",
        controle=item.get("numero_controle_pncp") or "",
        fim_prazo=str(prazo_de(item) or ""),
        objeto=(item.get("description") or "")[:1200],
        data_publicacao=str(item.get("data_publicacao_pncp") or "")[:10],
        publicado_em=str(item.get("data_publicacao_pncp") or "")[:10],
        escopo=dict(zip(("dentro", "motivo"),
                        escopo.avaliar(item.get("description") or ""))),
        link=lic.link,
        extraido_em=str(datetime.date.today()),
        arquivos=baixados)
    with open(os.path.join(pasta, "_inventario.json"), "w", encoding="utf-8") as f:
        json.dump(inv, f, ensure_ascii=False, indent=1)
    return inv


def _fechar(t0, **campos):
    """
    Registra a execucao no historico, sempre — inclusive quando nao houve nada
    a fazer, e sobretudo quando a busca falhou.

    O `_execucoes.jsonl` existe para dar a serie de DISPONIBILIDADE do PNCP, e
    ate 23/09/2026 o monitor era o unico script de rede que nao escrevia nela.
    Justo o que roda duas vezes por dia — a execucao que MAIS diz sobre a
    disponibilidade era a que nao deixava rastro.

    `buscas_falhas` entra em toda linha: uma serie que so registra os dias bons
    mede o clima, nao a API.
    """
    try:
        execucao.registrar("20_monitor.py", t0, **campos)
    except Exception:                                             # noqa: BLE001
        pass
    return 0


def main() -> int:
    _t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--seco", action="store_true",
                    help="não baixa nem extrai; só relata o que faria")
    ap.add_argument("--sem-extrair", action="store_true",
                    help="baixa e cadastra, mas não chama o modelo")
    ap.add_argument("--modelo", default=modelos.MODELO_EXTRATOR)
    # QUANTAS PAGINAS -- E POR QUE 2 ERA POUCO DEMAIS.
    #
    # O default era 2, desde sempre, sem ninguem revisitar. Medido em 23/09/2026
    # sobre o termo "folha de pagamento servidores instituicao financeira":
    #
    #     pagina  1 .... 41 de 50 sao de folha
    #     pagina  4 .... 43 de 50
    #     pagina  8 .... 41 de 50
    #     pagina 16 .... 45 de 50
    #     800 itens varridos, 699 de folha -- 87%
    #
    # A DENSIDADE NAO CAI. O ranking do `api/search` nao concentra os relevantes
    # nas primeiras paginas, entao parar na 2a nao e "pegar os melhores": e ver
    # 100 de 800+, ou 12%.
    #
    # Foi assim que Dracena/SP e Sao Jose dos Campos/SP ficaram de fora -- estao
    # na PAGINA 3 de um termo que o projeto ja usava. A varredura de recall as
    # marcou como "a busca perdeu", e a busca nao tinha perdido: ela nao tinha
    # olhado.
    ap.add_argument("--paginas", type=int, default=10)
    ap.add_argument("--max", type=int, default=5,
                    help="teto de extrações por execução (padrão 5)")
    ap.add_argument("--teto-brl", type=float, default=25.0,
                    help="teto de gasto por execução em R$ (padrão 25)")
    ap.add_argument("--falhas-seguidas", type=int, default=3,
                    help="desiste depois desta quantidade de falhas em sequência")
    a = ap.parse_args()

    agora = datetime.datetime.now()
    print("=" * 92)
    print("  MONITOR FOPA — %s" % agora.strftime("%d/%m/%Y %H:%M"))
    print("=" * 92)

    livro = carregar_livro()
    semeados = semear_do_disco(livro)
    if semeados:
        print("  livro-razão semeado com %d licitação(ões) já em disco" % semeados)
    print("  já conhecidas: %d" % len(livro["licitacoes"]))

    # ------------------------------------------------------- 1. consulta
    print("\n  [1/4] Consultando o PNCP (gratuito, sem cadastro)")
    achados: list[dict] = []
    falhas_busca = []
    for termo in TERMOS:
        try:
            itens = pncp.buscar(termo, paginas=a.paginas, tam=50)
        except pncp.ErroPNCP as e:
            # APROVEITAR O PARCIAL, E CONTINUAR DIZENDO QUE FOI PARCIAL.
            # A busca que morre na pagina 4 leu tres paginas de verdade. Antes
            # elas eram descartadas; agora entram, e o termo continua na lista
            # de falhas -- porque "vi parte" nao autoriza concluir "nao ha".
            parcial = getattr(e, "itens", []) or []
            print("        falha na busca %r na pág %d: %s"
                  % (termo[:34], getattr(e, "pagina", 0), e))
            if parcial:
                print("        %s aproveitando %d item(ns) lidos antes da falha"
                      % (" " * 34, len(parcial)))
                achados.extend(parcial)
            falhas_busca.append(termo)
            continue
        print("        %-54s %4d itens" % ('"%s"' % termo[:52], len(itens)))
        achados.extend(itens)

    achados = pncp.dedup(achados)
    print("        %d após deduplicação" % len(achados))

    # "NADA A FAZER" E "NAO CONSEGUI OLHAR" NAO PODEM SAIR IGUAIS.
    #
    # Ate 23/09/2026 uma busca que falhava so imprimia a linha de erro e o
    # monitor seguia. Com as buscas fora, ele chegava em "0 apos deduplicacao",
    # depois "nenhum edital novo", e fechava com "NADA A FAZER — custo R$ 0,00"
    # — a MESMA tela de um dia tranquilo.
    #
    # Rodando de madrugada, sem ninguem olhando, isso e uma licitacao perdida
    # que nao deixa rastro: o log diz que o sistema trabalhou e nao achou nada.
    #
    # E nao e hipotese. Numa execucao real de 23/09 as DUAS buscas de TERMOS
    # falharam com `RemoteDisconnected` -- 100% delas -- e a saida final foi
    # indistinguivel de um dia sem novidade.
    if falhas_busca:
        print()
        print("  " + "!" * 86)
        if len(falhas_busca) == len(TERMOS):
            print("  NENHUMA das %d buscas funcionou. Esta execução ficou CEGA:"
                  % len(TERMOS))
            print("  não há o que concluir dela, nem mesmo que não havia nada.")
        else:
            print("  ATENÇÃO — %d de %d buscas falharam. Esta execução não viu o"
                  % (len(falhas_busca), len(TERMOS)))
            print("  mercado inteiro, e o que vem abaixo é PISO, não total.")
        for t in falhas_busca:
            print("     · %s" % t[:74])
        print("  " + "!" * 86)

    # ------------------------------------------------------- 2. classificação
    print("\n  [2/4] Classificando por regra (sem IA — ADR-003)")
    no_escopo, descartados = [], {}
    for it in achados:
        ok, motivo = classificar(it)
        if ok:
            no_escopo.append(it)
        else:
            descartados[motivo] = descartados.get(motivo, 0) + 1
    print("        %d no escopo" % len(no_escopo))
    for motivo, n in sorted(descartados.items(), key=lambda x: -x[1]):
        print("        %4d descartados — %s" % (n, motivo))

    # ------------------------------------------------------- 3. o que é novo
    print("\n  [3/4] Separando o que é novo E ainda aberto")
    hoje = agora.date()
    novos, encerrados, conhecidos = [], 0, 0
    retificadas = []
    for it in no_escopo:
        chave = it.get("numero_controle_pncp") or it.get("numeroControlePNCP") or it.get("id")
        if not chave:
            continue
        if chave in livro["licitacoes"]:
            registro = livro["licitacoes"][chave]
            if foi_retificada(it, registro):
                retificadas.append((chave, it))
            else:
                conhecidos += 1
            continue
        if not esta_aberto(it, hoje):
            encerrados += 1
            # registra para não reavaliar amanhã o mesmo certame encerrado
            livro["licitacoes"][chave] = dict(
                pasta=None, orgao=it.get("orgao_nome"), uf=it.get("uf"),
                municipio=it.get("municipio_nome"),
                fim_prazo=str(prazo_de(it) or ""),
                visto_em=str(hoje), extraida=False,
                origem="monitor", motivo="prazo encerrado")
            continue
        novos.append((chave, it))

    print("        %4d já conhecidos e sem mudança" % conhecidos)
    print("        %4d com prazo encerrado (arquivados sem custo)" % encerrados)
    if retificadas:
        print("        %4d RETIFICADAS desde a última leitura — entram de novo na fila:"
              % len(retificadas))
        for chave, it in retificadas[:6]:
            reg = livro["licitacoes"][chave]
            print("             %-34s visto %s -> agora %s"
                  % ((it.get("orgao_nome") or "")[:34],
                     str(reg.get("atualizado_pncp"))[:10], atualizado_em(it)[:10]))

    # Retificada tem precedência sobre nova: o documento mudou numa licitação que
    # já orientou uma decisão, e a resposta antiga ficou errada sem ninguém saber.
    novos.sort(key=lambda kv: prazo_de(kv[1]) or datetime.date.max)
    retificadas.sort(key=lambda kv: prazo_de(kv[1]) or datetime.date.max)
    novos = retificadas + novos

    if not novos:
        print("        nenhum edital novo nem retificado.")
        print("\n" + "=" * 92)
        if falhas_busca:
            print("  NADA VISTO — %d de %d buscas falharam."
                  % (len(falhas_busca), len(TERMOS)))
            print("  Isto NÃO é \"nada a fazer\": é \"não consegui olhar\".")
            print("  Rode de novo quando a API voltar.")
        else:
            print("  NADA A FAZER — custo desta execução: R$ 0,00")
        print("=" * 92)
        gravar_livro(livro)
        painel.escrever(AMOSTRAS, SAIDAS, os.path.join(AMOSTRAS, "index.html"))
        return _fechar(_t0, custo_brl=0.0, candidatas=len(achados),
                       no_escopo=len(no_escopo), novos=0, extraidas=0,
                       buscas_falhas=len(falhas_busca), termos=len(TERMOS),
                       cego=len(falhas_busca) == len(TERMOS))

    print("        %d edital(is) NOVO(S) e aberto(s), do prazo mais curto ao mais longo:"
          % len(novos))
    for chave, it in novos[:20]:
        p = prazo_de(it)
        print("          %-10s %-30s %s"
              % (p.strftime("%d/%m") if p else "—", str(chave)[:30],
                 (it.get("orgao_nome") or "")[:42]))
    if len(novos) > 20:
        print("          ... e mais %d" % (len(novos) - 20))

    # Trava de gasto. Este script roda às 6h sem ninguém olhando; um acervo
    # inesperado não pode virar uma fatura de três dígitos sem autorização.
    if len(novos) > a.max:
        print("\n        TETO: %d novos, limite de %d por execução."
              % (len(novos), a.max))
        print("        Processando os %d de prazo mais curto; o resto entra na"
              " próxima." % a.max)
        novos = novos[:a.max]

    if a.seco:
        print("\n" + "=" * 92)
        print("  EXECUÇÃO SECA — nada foi baixado nem extraído. Custo: R$ 0,00")
        print("=" * 92)
        return _fechar(_t0, custo_brl=0.0, candidatas=len(achados),
                       novos=len(novos), extraidas=0, seco=True,
                       buscas_falhas=len(falhas_busca), termos=len(TERMOS))

    # ------------------------------------------------------- 4. baixar e extrair
    print("\n  [4/4] Baixando e extraindo")
    custo = 0.0
    processados = 0
    seguidas = 0
    for chave, it in novos:
        if custo >= a.teto_brl:
            print("        TETO DE GASTO atingido (R$ %.2f de R$ %.2f). "
                  "O restante fica para a próxima execução." % (custo, a.teto_brl))
            break
        # A MESMA função do coletor em lote, de propósito.
        # Antes daqui o monitor montava o nome por conta própria e produzia,
        # para a mesma licitação, um endereço diferente do `28`. Duas pastas,
        # uma licitação, e o de-dup de cada um cego para o do outro — ADR-013.
        nome = nomes.nome_pasta(
            orgao=it.get("orgao_nome") or chave,
            modalidade=(it.get("modalidade_licitacao_nome")
                        or it.get("modalidade_nome") or "Licitacao"),
            uf=it.get("uf") or "")[:90]
        pasta = os.path.join(AMOSTRAS, nome)
        try:
            inv = baixar_licitacao(it, pasta)
            livro["licitacoes"][chave] = dict(
                pasta=nome, orgao=it.get("orgao_nome"), uf=it.get("uf"),
                municipio=it.get("municipio_nome"),
                fim_prazo=inv.get("fim_prazo"),
                arquivos=len(inv.get("arquivos") or []),
                visto_em=str(datetime.date.today()),
                # o carimbo que faz a detecção de retificação funcionar
                atualizado_pncp=atualizado_em(it),
                extraida=False, origem="monitor")
            seguidas = 0
            print("        %-46s %d arquivo(s) baixado(s)"
                  % (nome[:46], len(inv.get("arquivos") or [])))

            if not inv.get("arquivos"):
                print("          sem arquivo utilizável — extração pulada")
                continue
            if a.sem_extrair:
                print("          cadastrado; extração adiada")
                continue

            provedor = modelos.obter_provedor()
            ext = extrator.extrair(pasta, provedor, modelo=a.modelo)
            rel = verificador.verificar(ext)
            destino = os.path.join(SAIDAS, nome)
            saida.escrever_json(ext, rel, os.path.join(destino, "auditoria.json"))
            saida.escrever_nota(ext, rel, os.path.join(destino, "%s.md" % nome))
            try:
                saida.escrever_xlsx(ext, rel, os.path.join(destino, "%s.xlsx" % nome))
            except RuntimeError:
                pass
            metadados.atualizar(pasta, ext, rel)
            pagina.escrever(ext, rel, os.path.join(pasta, "RELATORIO.html"))

            livro["licitacoes"][chave]["extraida"] = True
            livro["licitacoes"][chave]["custo_brl"] = round(ext.uso.brl, 3)
            custo += ext.uso.brl
            processados += 1
            print("        %-46s %s · R$ %.2f" % (nome[:46], rel, ext.uso.brl))
        except Exception as e:                                  # noqa: BLE001
            seguidas += 1
            print("        %-46s FALHOU: %s" % (nome[:46], str(e)[:76]))
            # Disjuntor. A API do PNCP é pública e gratuita, e não é confiável:
            # num teste real ela devolveu 504 em sequência, inclusive para uma
            # licitação que já estava baixada aqui. Sem isto, o job das 5h30
            # moeria 48 licitações × 3 tentativas contra uma fonte morta, e o
            # log da manhã seria ilegível.
            #
            # Desistir é seguro porque o livro-razão só registra o que deu
            # certo: o que falhou hoje é tentado de novo amanhã, sem duplicar
            # nada e sem custo nenhum.
            if seguidas >= a.falhas_seguidas:
                print("\n        %d falhas seguidas — a fonte parece indisponível."
                      % seguidas)
                print("        Interrompendo. Nada foi registrado no livro-razão,")
                print("        então a próxima execução retoma daqui.")
                break

    gravar_livro(livro)
    painel.escrever(AMOSTRAS, SAIDAS, os.path.join(AMOSTRAS, "index.html"))

    print("\n" + "=" * 92)
    if seguidas >= a.falhas_seguidas:
        print("  INTERROMPIDO por indisponibilidade da fonte.")
    print("  %d processado(s) · custo desta execução: R$ %.2f" % (processados, custo))
    print("  painel atualizado: amostras/index.html")
    print("=" * 92)
    return _fechar(_t0, custo_brl=round(custo, 3), candidatas=len(achados),
                   novos=len(novos), extraidas=processados,
                   interrompido=seguidas >= a.falhas_seguidas,
                   buscas_falhas=len(falhas_busca), termos=len(TERMOS))


if __name__ == "__main__":
    raise SystemExit(main())
