# -*- coding: utf-8 -*-
"""
Baixa os documentos de UMA licitação do PNCP, pelo número de controle.

    python 28_baixar_licitacao.py --controle 29052875000119-1-000025/2026
    python 28_baixar_licitacao.py --auto          primeira do corpus ainda não baixada
    python 28_baixar_licitacao.py --auto --esperar 3600    insiste enquanto a API cai

POR QUE UM SCRIPT SÓ PARA ISSO
  O `20_monitor.py` baixa em lote, com livro-razão e circuit breaker — desenho
  certo para rodar sozinho de madrugada, e pesado demais para "baixar ESTA aqui".
  Este faz uma licitação, na mão, e escreve o mesmo `_inventario.json` que o
  resto do pipeline espera encontrar.

O FILTRO DE ESCOPO RODA ANTES DO DOWNLOAD
  Não depois. Baixar primeiro e decidir depois já custou uma extração inteira
  (Rio Azul/PR, R$ 4,26, 6 das 17 perguntas em branco). Aqui, se o objeto não
  passar em `escopo.avaliar`, nada é baixado — e o motivo é impresso.

SOBRE A `api/pncp/v1`
  É a instável das três do PNCP. Ela responde 503 por dias, e a causa aparece no
  corpo do erro: `Failed to obtain JDBC Connection`. Por isso o `--esperar`: em
  vez de falhar e exigir que alguém lembre de tentar de novo, o script insiste
  em intervalo fixo até o teto informado. Ver [[Disponibilidade do PNCP]].
"""
from __future__ import annotations

import argparse
import io
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

from fopa import escopo, execucao, nomes, pncp                                     # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
CORPUS = os.path.join(RAIZ, "saidas", "_corpus_escopo.json")

RE_CONTROLE = re.compile(r"^(\d{14})-\d+-(\d+)/(\d{4})$")

# LIMITES DE COLETA — um teto explícito, e o motivo de cada número.
#
# O PNCP aceita upload de qualquer órgão, sem sanitização declarada. Baixar sem
# teto significa que um arquivo mal formado, ou hostil, decide quanto disco e
# quanta memória o pipeline usa. Não é hipótese exótica: o maior anexo real da
# amostra tem 26 MB e 68 páginas, num edital de município pequeno.
#
# Os tetos são folgados de propósito — 4x o maior caso real observado. Um teto
# apertado recusaria edital legítimo, que é pior que baixar um arquivo grande:
# recusa silenciosa vira licitação não analisada.
MAX_BYTES = 120 * 1024 * 1024      # 120 MB por arquivo
MAX_BYTES_LICITACAO = 400 * 1024 * 1024   # 400 MB somando a licitação inteira
MAX_PAGINAS = 600                  # por arquivo, conferido APÓS baixar

# "MUNICIPIO DE CALDAS NOVAS" -> "Caldas Novas". A pasta segue a convenção que o
# painel e o `_do_nome()` já leem: "<Modalidade> - <Município>-<UF>".
RE_PREFIXO = re.compile(
    r"^(?:munic[íi]pio|prefeitura(?:\s+municipal)?|c[âa]mara(?:\s+municipal)?|"
    r"fundo|instituto|autarquia)\s+(?:municipal\s+)?d[eo]\s+", re.I)


def barra(t: str) -> None:
    print("\n" + "=" * 92 + "\n  %s\n" % t + "=" * 92)


def de_controle(controle: str) -> pncp.Licitacao:
    m = RE_CONTROLE.match(controle.strip())
    if not m:
        raise SystemExit("número de controle não reconhecido: %r\n"
                         "formato esperado: CNPJ-1-SEQ/ANO" % controle)
    cnpj, seq, ano = m.groups()
    # o sequencial vai zero-padded no controle e SEM zeros na URL
    return pncp.Licitacao(cnpj=cnpj, ano=ano, seq=str(int(seq)))


def nome_pasta(registro: dict) -> str:
    """Delega a `fopa.nomes` — o monitor usa a MESMA função. Ver ADR-013."""
    return nomes.nome_pasta(orgao=registro.get("orgao") or "",
                            modalidade=registro.get("modalidade") or "",
                            uf=registro.get("uf") or "")


def _chave(nome: str) -> str:
    """
    Chave de comparação de pasta: sem acento, sem caixa, sem o prefixo antigo.

    A comparação ingênua listou Pirapó, Adrianópolis e mais três como se não
    tivessem sido baixadas — porque o corpus escreve "Concorrência - Eletrônica"
    e a pasta no disco se chama "Concorrencia - Eletronica". O de-dup falhava
    para TODA licitação cuja modalidade tem acento, que são quase todas.
    """
    return nomes.chave(nome)


def candidatos() -> list[dict]:
    """
    Do corpus: as que passam no filtro e ainda não estão em amostras/.

    CASA POR CONTROLE ANTES DE CASAR POR NOME — e este foi o TERCEIRO lugar com
    o mesmo defeito.

    Corrigi primeiro em `30_mapa_editais.py`, depois em `ja_baixada()`, e as
    duas vezes não fui procurar os irmãos. O TCE-AC continuou aparecendo como
    candidato mesmo já estando em disco, porque a pasta se chama
    `Dispensa - Rio Branco-AC` — pelo município — e o corpus traz o órgão.

    A lição não é sobre esta função: é que um defeito de identidade aparece em
    todo lugar que decide "isso já está no acervo?". Quando um for encontrado, procurar
    os outros ANTES de fechar.
    """
    corpus = json.load(io.open(CORPUS, encoding="utf-8"))
    legado, controles = set(), set()
    for d in os.listdir(AMOSTRAS):
        if not os.path.isdir(os.path.join(AMOSTRAS, d)) or d.startswith("_"):
            continue
        if not os.path.isfile(os.path.join(AMOSTRAS, d, "_inventario.json")):
            continue        # destroco de tentativa falha — nao e download
        c = _controle_de(d)
        if c:
            controles.add(c)
        else:
            # SO estas ainda se defendem pelo nome. Sao as cinco pastas
            # coletadas a mao no inicio do projeto, sem `controle` e sem `link`
            # no inventario — nao ha identidade para comparar, entao o nome e o
            # unico anteparo que resta. Nenhuma delas colide com o corpus atual.
            legado.add(_chave(d))

    # AS QUE O LIVRO JÁ DEU POR IMPOSSÍVEIS.
    #
    # Uma licitação cujo único arquivo é RTF ou .doc não vira PDF amanhã. Se a
    # fila continuar oferecendo, o coletor baixa, farejamos os bytes, recusamos
    # e descartamos — todo dia, para sempre, por um motivo que não muda sozinho.
    #
    # Não é o mesmo que esquecê-las: o estado fica no livro com o formato real,
    # e `--reconferir` volta a olhar, porque o órgão PODE republicar em PDF. O
    # que sai é a retentativa cega, não o caso.
    impossiveis = set()
    if os.path.isfile(LIVRO):
        try:
            _l = json.load(io.open(LIVRO, encoding="utf-8")).get("registros", {})
            impossiveis = {c for c, v in _l.items()
                           if v.get("estado") == "formato-nao-suportado"}
        except (ValueError, OSError):
            impossiveis = set()

    saida = []
    for r in corpus["registros"]:
        ok, _ = escopo.avaliar(r.get("objeto") or "")
        if not ok:
            continue
        ctrl_r = (r.get("controle") or "").strip()
        if ctrl_r in controles:
            continue
        if ctrl_r in impossiveis:
            continue
        if _chave(nome_pasta(r)) in legado:
            continue
        saida.append(r)
    return saida


def pastas_orfas() -> list[str]:
    """
    Pastas sem `_inventario.json` — tentativas que morreram no meio.

    POR QUE ISSO PRECISA DE UMA FUNCAO PROPRIA
      A pasta e criada ANTES do download, nao depois. Quando a API caia no meio,
      sobrava um diretorio vazio — e `candidatos()` descarta tudo cujo nome ja
      existe em amostras/. O diretorio vazio passava a responder "ja esta no acervo"
      por uma licitacao que nunca foi baixada.

      Quatro licitacoes sumiram assim em 23/09: Gurinhata/MG, Pedra do Anta/MG,
      Sao Miguel do Iguacu/PR e Tapirai/MG. O coletor dizia "0 candidatas" com a
      conviccao de quem terminou o trabalho.

      O inventario e o unico atestado de download completo, porque e a ultima
      coisa que se escreve. Pasta sem inventario nao e download: e destroco.
    """
    orfas = []
    for d in sorted(os.listdir(AMOSTRAS)):
        p = os.path.join(AMOSTRAS, d)
        if not os.path.isdir(p) or d.startswith("_"):
            continue
        if not os.path.isfile(os.path.join(p, "_inventario.json")):
            orfas.append(d)
    return orfas


ASSINATURAS = (
    (b"%PDF-",            "PDF"),
    (b"PK\x03\x04",       "ZIP ou OOXML (.docx/.xlsx)"),
    (b"Rar!\x1a\x07",     "RAR"),
    (b"\xd0\xcf\x11\xe0",  "OLE — .doc ou .xls antigo"),
    (b"{\\rtf",           "RTF"),
    (b"\x89PNG",          "PNG"),
    (b"\xff\xd8\xff",     "JPEG"),
    (b"<",                "HTML ou XML"),
)


def formato_real(caminho: str) -> str:
    """
    O que o arquivo É, pelos primeiros bytes.

    POR QUE A RECUSA PRECISA DIZER ISTO
      Antes daqui, todo arquivo não-PDF era recusado com a mesma frase: *"não
      abre como PDF: Failed to open file ..."*. Ela mistura três coisas
      diferentes que pedem reações diferentes:

        · **PDF corrompido no download** — vale tentar de novo
        · **formato não suportado** (RTF, .doc, RAR) — tentar de novo nunca
          resolve; é limite declarado do sistema
        · **ZIP disfarçado de .pdf** — o sistema resolve sozinho

      Alto Araguaia/MT serve `Edital.pdf` que é **RTF**; Inhácora/RS serve
      `...documento.doc.pdf` que é **OLE**. Com a mensagem antiga, as duas
      apareciam no livro idênticas a uma falha de rede — e alguém tentaria de
      novo, todo dia, para sempre.

      Uma mensagem de erro que não distingue "insista" de "desista" custa
      tentativas infinitas.
    """
    try:
        with io.open(caminho, "rb") as f:
            b = f.read(16)
    except OSError:
        return "ilegível"
    for assinatura, nome in ASSINATURAS:
        if b.startswith(assinatura):
            return nome
    return "desconhecido (%r)" % b[:6]


def desempacotar(caminho: str, doc: dict) -> list | None:
    """
    Se o arquivo baixado for um ZIP, extrai os PDFs de dentro dele.

    Devolve `None` se nao for ZIP, `[]` se for ZIP sem PDF dentro, ou a lista
    de `ArquivoBaixado` extraidos.

    POR QUE ISSO EXISTE — O METADADO MENTE, OS BYTES NAO
      O PNCP anuncia, no JSON de documentos, um arquivo chamado
      `170773_editais_1769711492.zip.pdf`. Termina em `.pdf`. Nao e PDF:

        Content-Disposition: attachment; filename="...zip"
        primeiros bytes:     PK\x03\x04

      Tres fontes, duas contra o nome: o header HTTP diz ZIP, os bytes dizem
      ZIP. So o campo de metadado diz PDF.

      E a tese do projeto aplicada a formato de arquivo. A ancoragem existe
      porque a citacao de um modelo pode ser plausivel e falsa; aqui a extensao
      e plausivel e falsa. A defesa e a mesma nos dois casos: conferir contra o
      artefato, nunca contra o que se diz dele.

      Seis licitacoes so existem nesta forma — arquivo unico, e e um ZIP.
      Confiar na extensao entrega PDF corrompido ao modelo; recusar pela
      extensao perde as seis em silencio. Nenhuma das duas serve.
    """
    with io.open(caminho, "rb") as f:
        if f.read(4) != b"PK\x03\x04":
            return None

    import hashlib
    import zipfile

    pasta = os.path.dirname(caminho)
    raiz = os.path.basename(caminho)
    for suf in (".zip.pdf", ".pdf", ".zip"):
        if raiz.lower().endswith(suf):
            raiz = raiz[: -len(suf)]
            break

    extraidos = []
    aninhados = []
    try:
        with zipfile.ZipFile(caminho) as z:
            for nome in z.namelist():
                if nome.endswith("/"):
                    continue
                if nome.lower().endswith(".zip"):
                    # ZIP DENTRO DE ZIP. Dois casos reais no acervo:
                    # Sao Sebastiao do Alto/RJ ('39-2026 - VENDA DA FOLHA DE
                    # PAGAMENTO.zip') e Sarzedo/MG ('ETP E TR.zip'). Sem
                    # recursao, o desempacotamento para no primeiro nivel e
                    # devolve zero PDFs — indistinguivel de 'ZIP vazio'.
                    seguro = re.sub(r'[<>:"/\\|?*]', "", os.path.basename(nome))
                    tmp = os.path.join(os.path.dirname(caminho),
                                       ("_aninhado -- %s" % seguro)[:200])
                    with io.open(tmp, "wb") as saida:
                        saida.write(z.read(nome))
                    aninhados.append(tmp)
                    continue
                if not nome.lower().endswith(".pdf"):
                    continue
                # NUNCA usar o caminho de dentro do ZIP como caminho de escrita:
                # um `../../..` no nome escreveria fora da pasta de destino.
                # Zip slip e velho, mas continua funcionando em quem confia.
                seguro = re.sub(r'[<>:"/\\|?*]', "", os.path.basename(nome))
                alvo = os.path.join(pasta, ("%s -- %s" % (raiz[:40], seguro))[:200])
                dados = z.read(nome)
                with io.open(alvo, "wb") as saida:
                    saida.write(dados)
                extraidos.append(pncp.ArquivoBaixado(
                    seq=doc.get("sequencialDocumento"),
                    tipo=doc.get("tipoDocumentoNome"),
                    titulo="%s (de dentro do ZIP)" % seguro,
                    caminho=alvo,
                    bytes=len(dados),
                    sha256=hashlib.sha256(dados).hexdigest(),
                    baixado_em=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    origem=doc.get("url"),
                ))
    except zipfile.BadZipFile as e:
        print("   ZIP corrompido: %s" % e)
        return []

    # desce nos aninhados, com a MESMA funcao — a profundidade nao e conhecida
    for tmp in aninhados:
        filhos = desempacotar(tmp, doc)
        if filhos:
            extraidos.extend(filhos)
        elif os.path.isfile(tmp):
            os.remove(tmp)

    if extraidos:
        os.remove(caminho)                    # o container nao e documento
    return extraidos


def gravar_inventario(pasta, registro, objeto, dentro, motivo, lic,
                      baixados, recusados, falhas_download=None):
    """
    Escreve o `_inventario.json` da licitacao.

    EXTRAIDO PARA FUNCAO EM 23/09/2026, e o motivo e o que importa: este
    bloco vivia so no caminho de sucesso. Quando TODOS os arquivos eram
    recusados por formato, a funcao saia antes e deixava a pasta vazia --
    nove delas no acervo. E `pastas_orfas()` trata pasta sem inventario como
    'tentativa que morreu no meio', o que essas nao sao: elas terminaram,
    com a resposta 'nao da para ler isto'.

    Agora o atestado e escrito nos dois desfechos. `arquivos: []` com a lista
    de `recusados` dentro diz exatamente o que aconteceu.
    """
    inventario = {
        "licitacao": registro.get("orgao"),
        "uf": registro.get("uf"),
        "modalidade": registro.get("modalidade"),
        "controle": registro.get("controle"),
        "objeto": objeto,
        "escopo": {"dentro": dentro, "motivo": motivo},
        # ESTES TRÊS VÃO PARA O PAINEL, e sem eles ele fica cego.
        # `fim_prazo` é o que o card usa para dizer "fecha em N dias"; sem ele
        # o painel escreve "prazo não informado", que é o que ele escrevia em
        # 169 das 175 licitações até 23/09/2026.
        "fim_prazo": registro.get("fim_prazo") or "",
        "municipio": registro.get("municipio") or "",
        "situacao": registro.get("situacao") or "",
        "publicado_em": registro.get("publicado_em") or "",
        "link": lic.link,
        "baixado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "arquivos": [dict(seq=b.seq, tipo=b.tipo, titulo=b.titulo,
                          arquivo=os.path.basename(b.caminho), bytes=b.bytes,
                          sha256=b.sha256, origem=b.origem) for b in baixados],
        # A recusa fica no inventário, não só no terminal: é ela que explica
        # por que a extração tem menos documentos do que o PNCP anunciou.
        "recusados": recusados,
        # Recusa por politica e falha de rede sao coisas diferentes, e a
        # diferenca decide o que fazer: recusa nao se retenta, falha sim.
        "falhas_download": falhas_download or [],
        "limites": {"max_bytes_arquivo": MAX_BYTES,
                    "max_bytes_licitacao": MAX_BYTES_LICITACAO,
                    "max_paginas": MAX_PAGINAS},
    }
    caminho = os.path.join(pasta, "_inventario.json")
    json.dump(inventario, io.open(caminho, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return caminho


def avaliar_baixado(destino: str, ab, doc: dict,
                    total_bytes: int, sem_teto: bool = False) -> tuple[str | None, list]:
    """
    Decide se um arquivo JA BAIXADO entra no acervo. Devolve `(recusa, extraidos)`:
    `recusa` e o motivo textual (ou None quando o arquivo serve) e `extraidos`
    sao os PDFs tirados de dentro dele quando o arquivo e um ZIP disfarcado --
    nesse caso o container ja foi removido por `desempacotar()` e quem chama
    usa os extraidos NO LUGAR dele.

    EXTRAIDA DE `baixar()` EM 24/09/2026 (v3, plano secao 6, ajuste 5), sem
    mudar uma decisao: a v3 precisa da MESMA politica de recusa por HTTP, e
    ela vivia inline num laco que imprime e grava em `amostras/`. Aqui nao ha
    print nem escrita fora do `desempacotar()`; remover o arquivo recusado e
    registrar o sequencial continuam com quem chama, porque sao decisoes de
    onde o acervo mora, nao de o que o arquivo e.

    Os tetos são conferidos DEPOIS de escrever, porque o PNCP não declara
    tamanho antes do download. Silêncio aqui viraria licitação com documento
    faltando sem ninguém saber por quê.

    `sem_teto`: licitação confirmada como folha de pagamento pega todos os
    arquivos disponíveis. Quem
    chama passa True quando a licitação é folha (a v3: `fn_escopo_efetivo`, o
    rótulo humano manda) e os três tetos não recusam nada — Maringá 000199/2024
    perdeu o processo SEI de 773 páginas para o teto de 600, e a extração
    respondeu 5 de 17. Os tetos continuam valendo para o que não é folha.
    """
    recusa = None
    if not sem_teto and ab.bytes > MAX_BYTES:
        recusa = "%.1f MB excede o teto de %d MB" % (
            ab.bytes / 1048576.0, MAX_BYTES // 1048576)
    elif not sem_teto and total_bytes + ab.bytes > MAX_BYTES_LICITACAO:
        recusa = "a licitação passaria de %d MB no total" % (
            MAX_BYTES_LICITACAO // 1048576)
    else:
        try:
            import pymupdf
            with pymupdf.open(destino) as d:
                if not sem_teto and d.page_count > MAX_PAGINAS:
                    recusa = "%d páginas excede o teto de %d" % (
                        d.page_count, MAX_PAGINAS)
                elif d.page_count == 0:
                    # ZERO PAGINA NAO E EXCECAO, E ERA POR ISSO QUE PASSAVA.
                    #
                    # Jacarezinho/PR, 23/09/2026: o arquivo e um ZIP com
                    # dois PDFs dentro, e `pymupdf.open()` ABRE ele sem
                    # levantar nada -- devolve um documento de 0 paginas.
                    # Sem excecao, o caminho do ZIP logo abaixo nunca era
                    # alcancado, e o container entrava no acervo como se
                    # fosse o edital. O edital ficava lacrado dentro.
                    #
                    # Foi assim que os 12 "ZIP com PDF" do censo de formato
                    # chegaram ao disco: nao por codigo antigo, por este
                    # buraco. Um PDF de zero paginas nao e um PDF usavel --
                    # e a recusa tem que ser a mesma de "nao abre", para
                    # cair no desempacotamento.
                    real = formato_real(destino)
                    recusa = ("não abre como PDF — 0 páginas; o arquivo é %s"
                              % real)
        except Exception as e:                                # noqa: BLE001
            real = formato_real(destino)
            if real == "PDF":
                recusa = "PDF corrompido ou ilegível: %s" % str(e)[:44]
            else:
                recusa = "não abre como PDF — o arquivo é %s" % real

    # ANTES de recusar por "não abre como PDF", conferir se e um ZIP.
    if recusa and recusa.startswith("não abre como PDF"):
        dentro_zip = desempacotar(destino, doc)
        if dentro_zip:
            return None, dentro_zip
        if dentro_zip == []:
            recusa = "ZIP sem nenhum PDF dentro"

    return recusa, []


def baixar(registro: dict, esperar: int = 0, intervalo: int = 900) -> int:
    objeto = registro.get("objeto") or ""
    dentro, motivo = escopo.avaliar(objeto)

    barra("LICITAÇÃO — %s/%s" % (registro.get("orgao"), registro.get("uf")))
    print("  controle ... %s" % registro.get("controle"))
    print("  modalidade . %s" % registro.get("modalidade"))
    print("  escopo ..... %s — %s" % ("DENTRO" if dentro else "FORA", motivo))
    print("  objeto ..... %s" % objeto[:200])

    if not dentro:
        print("\n  Fora de escopo. Nada baixado — e é esse o ponto: o filtro roda")
        print("  ANTES do download, não depois da extração.")
        return 2

    lic = de_controle(registro["controle"])
    print("  link ....... %s" % lic.link)

    limite = time.time() + esperar
    while True:
        try:
            arquivos = lic.arquivos()
            break
        except pncp.ErroPNCP as e:
            if time.time() >= limite:
                print("\n  API de documentos indisponível: %s" % e)
                if esperar:
                    print("  Insisti por %ds e ela não voltou." % esperar)
                return 1
            print("  API fora — nova tentativa em %ds (até %s)"
                  % (intervalo, time.strftime("%H:%M:%S", time.localtime(limite))),
                  flush=True)
            time.sleep(intervalo)

    ativos = [a for a in arquivos if a.get("statusAtivo")]
    print("\n  %d arquivo(s), %d ativo(s)" % (len(arquivos), len(ativos)))
    if not ativos:
        print("  Nenhum arquivo ativo — nada a baixar.")
        return 1

    pasta = os.path.join(AMOSTRAS, nome_pasta_unico(registro))
    os.makedirs(pasta, exist_ok=True)
    print("  destino .... %s\n" % os.path.relpath(pasta, RAIZ))

    baixados = []
    total_bytes = 0
    recusados = []
    falhas_download = []
    for a in sorted(ativos, key=lambda x: x.get("sequencialDocumento") or 0):
        seq = a.get("sequencialDocumento")
        tipo = (a.get("tipoDocumentoNome") or "Documento").strip()
        titulo = (a.get("titulo") or "sem-titulo").strip()
        base = re.sub(r'[<>:"/\\|?*]', "", "%02d - %s - %s" % (seq, tipo, titulo))
        if not base.lower().endswith(".pdf"):
            base += ".pdf"
        destino = os.path.join(pasta, base)
        try:
            ab = pncp.baixar_arquivo(a, destino)
        except Exception as e:                                    # noqa: BLE001
            # FALHA DE REDE TAMBEM VAI PARA O INVENTARIO.
            #
            # Ate 23/09/2026 isto so imprimia no terminal e seguia. Quando
            # TODOS os arquivos falhavam assim, a licitacao terminava com
            # `arquivos: []` e `recusados: []` -- um inventario que nao diz
            # nada: nao baixamos e nao recusamos, e o leitor nao tem como
            # saber se faltou arquivo no PNCP ou se a rede caiu.
            #
            # Kalore/PR 48-2026 e Reserva/PR sairam assim esta noite, e quem
            # pegou foi a assercao que exige que pasta sem PDF explique por
            # que esta sem PDF. `recusados` e lista de recusa por POLITICA;
            # `falhas_download` e outra coisa, e por isso tem campo proprio:
            # recusa local nao se retenta, falha de rede se retenta.
            print("   %-62s FALHOU: %s" % (base[:62], e))
            falhas_download.append({
                "arquivo": base, "seq": seq, "tipo": tipo,
                "erro": "%s: %s" % (type(e).__name__, str(e)[:160]),
                "origem": a.get("url"),
            })
            continue

        # `recusa`, NAO `motivo`. O nome importa: ate 23/09 esta variavel se
        # chamava `motivo` e sobrescrevia o `motivo` devolvido por
        # `escopo.avaliar()` la em cima — o texto que justifica POR QUE a
        # licitacao entrou no corpus. O inventario gravava, no campo de escopo,
        # a recusa do ultimo arquivo do loop (ou None, quando nenhum foi
        # recusado). 43 dos 139 inventarios saíram assim.
        #
        # Num projeto cujo argumento e "toda decisao e auditavel", a decisao
        # que se perdeu foi justamente a primeira da cadeia. E se perdeu em
        # silencio, porque `None` num campo de texto nao parece defeito.
        recusa, dentro_zip = avaliar_baixado(destino, ab, a, total_bytes)
        if dentro_zip:
            print("   %-62s ZIP -> %d PDF(s)" % (base[:62], len(dentro_zip)))
            for extra in dentro_zip:
                total_bytes += extra.bytes
                baixados.append(extra)
                print("     %-60s %8d bytes  %s"
                      % (os.path.basename(extra.caminho)[:60],
                         extra.bytes, extra.sha256[:12]))
            continue

        if recusa:
            try:
                os.remove(destino)
            except OSError:
                pass
            # GRAVA O SEQUENCIAL TAMBEM. Sem ele, um arquivo recusado some do
            # rastro: o inventario nao registra que aquele sequencial foi visto,
            # e todo detector que compara "o que o acervo tem" com "o que a API tem"
            # passa a acusar o mesmo arquivo como NOVO, para sempre.
            # Foi o que aconteceu com Inhacora/RS na varredura de retificacoes.
            recusados.append({"seq": seq, "arquivo": base, "motivo": recusa,
                              "bytes": ab.bytes, "origem": a.get("url")})
            print("   %-62s RECUSADO: %s" % (base[:62], recusa))
            continue

        total_bytes += ab.bytes
        baixados.append(ab)
        print("   %-62s %8d bytes  %s" % (base[:62], ab.bytes, ab.sha256[:12]))

    if not baixados:
        # CÓDIGO 3 — nada foi baixado porque NENHUM arquivo era PDF.
        #
        # Isto não é falha de API, e tratá-lo como falha tem duas consequências
        # ruins: arma o disjuntor (que existe para detectar o portal fora do ar)
        # e deixa a licitação eternamente na fila, sendo retentada todo dia por
        # um motivo que nunca vai mudar sozinho.
        #
        # Alto Araguaia/MT publica o edital em RTF; Inhácora/RS em .doc. Os dois
        # vão continuar em RTF e .doc amanhã.
        formatos = sorted({(r.get("motivo") or "").split("é ")[-1]
                           for r in recusados
                           if "o arquivo é" in (r.get("motivo") or "")})
        # RECUSA TOTAL TAMBEM PRECISA DE ATESTADO.
        #
        # Ate 23/09/2026 este caminho saia sem escrever inventario e deixava
        # a pasta VAZIA no disco. Nove delas existem hoje, e sao exatamente as
        # `formato-nao-suportado` do livro: Fronteira/MG (duas), Dom Cavati/MG,
        # Inhacora/RS, Itaipava do Grajau/MA, Alto Araguaia/MT, Euclides da
        # Cunha/BA, Guaranta do Norte/MT e Transitar/PR.
        #
        # `pastas_orfas()` define orfa como 'pasta sem inventario = tentativa
        # que morreu no meio'. Estas NAO morreram no meio: terminaram, com a
        # resposta 'nao da para ler isto'. Sem inventario, o disco contradiz o
        # livro-razao, e `candidatos()` passa a responder 'ja esta no acervo' por
        # uma licitacao que nao esta la.
        #
        # O inventario com `arquivos: []` e as recusas dentro resolve os dois:
        # a pasta deixa de ser destroco e vira registro de que se tentou.
        gravar_inventario(pasta, registro, objeto, dentro, motivo, lic,
                          [], recusados, falhas_download)
        if formatos and len(recusados) == len(ativos):
            print("\n  Nenhum download: todos os %d arquivo(s) são de formato"
                  " não suportado (%s)." % (len(recusados), ", ".join(formatos)))
            print("  Não é falha da API — é limite declarado. Ver ADR-005.")
            print("  Inventário gravado assim mesmo: a pasta registra a recusa,")
            print("  em vez de ficar vazia contradizendo o livro-razão.")
            return 3
        print("\n  Nenhum download concluído.")
        print("  (inventário gravado com a lista de recusas)")
        return 1

    caminho = gravar_inventario(pasta, registro, objeto, dentro, motivo, lic,
                                baixados, recusados, falhas_download)

    if recusados:
        print("\n  %d arquivo(s) RECUSADO(S) pelos limites de coleta:" % len(recusados))
        for r in recusados:
            print("     %s — %s" % (r["arquivo"][:58], r["motivo"]))
    print("\n  inventário . %s  (SHA-256 e origem de cada arquivo)"
          % os.path.relpath(caminho, RAIZ))
    print("\n  Próximo passo:")
    print('      python 10_extrair_edital.py "%s"' % nome_pasta(registro))
    return 0


LIVRO = os.path.join(RAIZ, "saidas", "_livro_download.json")


def carregar_livro() -> dict:
    """
    Livro-razão do lote: o que já foi baixado, e o que falhou por quê.

    Ele existe porque 104 licitações contra uma API que responde 503 por dias
    NÃO cabem numa execução só. Sem livro, retomar significaria rebaixar tudo
    ou alguém manter a lista na cabeça. Mesma razão do `saidas/_livro.json` do
    monitor, e a chave é a mesma: o número de controle do PNCP.
    """
    if os.path.isfile(LIVRO):
        return json.load(io.open(LIVRO, encoding="utf-8"))
    return {"proposito": "Livro-razão do download em lote. Chave: numero_controle_pncp.",
            "registros": {}}


def reconciliar_livro(livro: dict) -> int:
    """
    Corrige entradas do livro que o disco desmente. Devolve quantas mudaram.

    POR QUE O LIVRO E O DISCO DIVERGEM
      Sitio Novo/RN estava no livro como `falhou`, carimbado 07:45, e a pasta
      com inventário completo estava em disco. A licitação falhou numa tentativa
      e foi baixada em outra — por outro caminho, num lote em que o `ctrl` não
      era a chave gravada — e ninguém voltou para corrigir a linha.

      Um livro-razão que diz "falhou" sobre algo que está no acervo é pior que
      não ter livro: quem o consulta para saber o que falta recebe uma lista com
      item a mais, vai atrás, e conclui que o sistema está confuso.

      O DISCO É A VERDADE. O livro é memória de intenção; o inventário é prova
      de fato. Quando discordam, o inventário ganha — ele só existe se o
      download terminou, porque é a última coisa escrita.

    Roda a cada carga, custa uma varredura de diretório e nenhuma chamada de API.
    """
    mudou = 0
    for ctrl, reg in livro.get("registros", {}).items():
        if reg.get("estado") in ("baixada", "ja-baixada", "fora-de-escopo"):
            continue
        pasta = _pasta_por_controle(ctrl)
        if not pasta:
            continue
        if os.path.isfile(os.path.join(AMOSTRAS, pasta, "_inventario.json")):
            reg["estado_anterior"] = reg.get("estado")
            reg["estado"] = "baixada"
            reg["pasta"] = pasta
            reg["reconciliado_em"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            mudou += 1
    return mudou


def gravar_livro(livro: dict) -> None:
    os.makedirs(os.path.dirname(LIVRO), exist_ok=True)
    json.dump(livro, io.open(LIVRO, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def _controle_de(pasta: str) -> str | None:
    """O `numero_controle_pncp` gravado, nas duas formas que o projeto tem."""
    f = os.path.join(AMOSTRAS, pasta, "_inventario.json")
    if not os.path.isfile(f):
        return None
    try:
        d = json.load(io.open(f, encoding="utf-8"))
    except (ValueError, OSError):
        return None
    c = (d.get("controle") or d.get("numero_controle_pncp")
         or (d.get("item") or {}).get("numero_controle_pncp"))
    return c.strip() if c else None


def _pasta_por_controle(controle: str) -> str | None:
    """Acha a pasta que JÁ guarda esta licitação, sob qualquer nome."""
    if not controle:
        return None
    alvo = controle.strip()
    for d in os.listdir(AMOSTRAS):
        if not os.path.isdir(os.path.join(AMOSTRAS, d)) or d.startswith("_"):
            continue
        if _controle_de(d) == alvo:
            return d
    return None


def nome_pasta_unico(registro: dict) -> str:
    """
    O nome de `nome_pasta()`, com o sequencial anexado se ja houver OUTRA
    licitacao ocupando esse nome.

    POR QUE — O MESMO DEFEITO DE IDENTIDADE, AGORA AO CONTRARIO
      `nome_pasta()` monta `<modalidade> - <municipio>-<UF>`. Dois pregoes do
      mesmo municipio produzem exatamente a mesma string.

      Antes disso ser corrigido, o coletor baixava o primeiro e anunciava
      "JA BAIXADA" para o segundo — que nunca tinha sido baixado. Em 172
      licitacoes em escopo, 142 nomes distintos: **30 sumiam em silencio**.
      Bento Goncalves/RS sozinho tem seis licitacoes colapsando numa pasta.

      E a terceira encarnacao do mesmo defeito neste arquivo. As duas primeiras
      eram "uma licitacao com dois nomes" (o TCE-AC). Esta e "duas licitacoes
      com um nome". A causa e identica: tratar rotulo como identidade.

      O numero de controle e a identidade. O nome da pasta e so endereco — e
      endereco precisa ser unico, nada mais.
    """
    base = nome_pasta(registro)
    ctrl = (registro.get("controle") or "").strip()
    dono = _pasta_por_controle(ctrl)
    if dono:
        return dono                       # ja esta no acervo; o endereco e o que existe

    alvo = os.path.join(AMOSTRAS, base)
    if not os.path.isdir(alvo):
        return base

    # A pasta existe e NAO e desta licitacao: desambigua pelo sequencial.
    m = re.search(r"-1-(\d+)/(\d{4})", ctrl)
    if m:
        return "%s - %s-%s" % (base, m.group(1).lstrip("0") or "0", m.group(2))
    return base


def mudou_no_portal(registro: dict) -> list[int]:
    """
    Sequenciais que o PNCP tem e o inventário local não.

    Lista vazia = nada mudou. Levanta exceção se a API não responder — quem
    chama decide se isso é motivo para rebaixar ou para deixar quieto.

    POR QUE A ANCORAGEM NÃO COBRE ISTO
      Uma licitação retificada continua ancorando perfeitamente: o trecho está
      mesmo na página que citamos. Só que o órgão substituiu o documento
      ontem, e a página é da versão velha.

      Verificar que a citação existe **não** verifica que o documento ainda
      vale. São duas perguntas, e o projeto só respondia a primeira.

      Retificação de edital é rotina — muda data de sessão, muda valor mínimo,
      muda anexo. `ja_baixada()` respondia "sim, ja esta no acervo" e o coletor seguia em
      frente, o que está certo para quem não mudou e errado exatamente para
      quem mudou.

    CUSTO: uma chamada por licitação. Por isso NÃO roda no caminho normal — só
    com `--reconferir`, que é operação deliberada e não parte do lote diário.
    """
    ctrl = (registro.get("controle") or "").strip()
    pasta = _pasta_por_controle(ctrl)
    if not pasta:
        return []
    inv = os.path.join(AMOSTRAS, pasta, "_inventario.json")
    if not os.path.isfile(inv):
        return []
    d = json.load(io.open(inv, encoding="utf-8"))

    locais = {a.get("seq") for a in d.get("arquivos", []) if a.get("seq")}
    locais |= {r.get("seq") for r in d.get("recusados", []) if r.get("seq")}

    lic = pncp.Licitacao.de_controle(ctrl)
    remotos = {a.get("sequencialDocumento") for a in lic.arquivos()
               if a.get("statusAtivo") is not False}
    return sorted(x for x in remotos - locais if x is not None)


def ja_baixada(registro: dict) -> bool:
    """
    Tem pasta, inventário e os arquivos que o inventário promete.

    CASA POR CONTROLE ANTES DE CASAR POR NOME — e isso custou uma licitação
    baixada duas vezes para ficar claro.

    A pasta antiga se chamava `Dispensa - Rio Branco-AC`, pelo MUNICÍPIO; o
    corpus traz o ÓRGÃO, e o coletor criou `Dispensa - Tribunal De Contas Do
    Estado Do Acre-AC` para a mesma licitação. Mesmo `numero_controle_pncp`,
    dois diretórios, e o mapa passou a contar a extração antiga como órfã.

    O nome da pasta é convenção; o número de controle é identidade. Quem manda
    é a identidade.
    """
    ctrl = (registro.get("controle") or "").strip()
    por_ctrl = _pasta_por_controle(ctrl)

    if ctrl and not por_ctrl:
        # TEM identidade e nenhuma pasta a carrega: esta licitacao nao esta no acervo.
        # NAO cair no nome aqui.
        #
        # A QUARTA VEZ DO MESMO DEFEITO, E A PRIMEIRA COM A LICAO JA ESCRITA
        #   Corrigi `30_mapa_editais.py`, depois esta funcao, depois
        #   `candidatos()`. No commit de `candidatos()` deixei escrito, com
        #   todas as letras, que "quando um defeito de identidade aparece,
        #   procurar os irmaos ANTES de fechar". E fechei sem procurar.
        #
        #   O resultado foi imediato: o lote seguinte pulou 27 das 30
        #   licitacoes recuperadas, porque o `or nome_pasta(registro)` desta
        #   linha reintroduzia exatamente a colisao que `candidatos()` tinha
        #   acabado de resolver. Duas funcoes, uma corrigida e outra nao,
        #   produzem o comportamento da nao corrigida.
        #
        #   Escrever a licao nao e aplicar a licao.
        return False

    pasta = os.path.join(AMOSTRAS, por_ctrl or nome_pasta(registro))
    inv = os.path.join(pasta, "_inventario.json")
    if not os.path.isfile(inv):
        return False
    try:
        d = json.load(io.open(inv, encoding="utf-8"))
    except (ValueError, OSError):
        return False
    arquivos = d.get("arquivos") or []
    if not arquivos:
        return False
    # Conferir que o arquivo EXISTE, e não só que o inventário o cita: um lote
    # interrompido no meio deixa inventário sem PDF, e um "já baixada" baseado
    # só no JSON marcaria como pronta uma pasta vazia.
    return all(os.path.isfile(os.path.join(pasta, a.get("arquivo") or ""))
               for a in arquivos)


def lote(esperar: int, intervalo_api: int, pausa: int, limite: int | None,
         falhas_seguidas_max: int = 8) -> int:
    cands = candidatos()
    if limite:
        cands = cands[:limite]

    _t0 = time.time()

    livro = carregar_livro()
    _corrigidas = reconciliar_livro(livro)
    if _corrigidas:
        print("  livro ...... %d registro(s) corrigido(s) contra o disco"
              % _corrigidas)
        gravar_livro(livro)
    barra("DOWNLOAD EM LOTE — %d licitação(ões) que passam no filtro" % len(cands))
    print("  destino .... amostras/<Modalidade> - <Município>-<UF>/")
    print("  livro ...... %s" % os.path.relpath(LIVRO, RAIZ))
    print("  pausa ...... %ds entre licitações (a API é frágil, não convém correr)"
          % pausa)
    print("  disjuntor .. para após %d falhas seguidas" % falhas_seguidas_max)

    ok = pulados = falhou = 0
    seguidas = 0

    for i, r in enumerate(cands, 1):
        ctrl = r.get("controle")
        rotulo = "%s/%s" % (RE_PREFIXO.sub("", r.get("orgao") or "").title(),
                            r.get("uf"))
        if ja_baixada(r):
            pulados += 1
            livro["registros"][ctrl] = {"estado": "ja-baixada",
                                        "pasta": nome_pasta(r)}
            print("\n[%3d/%d] %-42s JÁ BAIXADA" % (i, len(cands), rotulo[:42]))
            continue

        print("\n[%3d/%d] %-42s %s" % (i, len(cands), rotulo[:42], ctrl))
        motivo_falha = ""
        try:
            codigo = baixar(r, esperar=esperar, intervalo=intervalo_api)
        except KeyboardInterrupt:
            print("\n  interrompido. O livro guarda o progresso; rode de novo "
                  "para retomar de onde parou.")
            gravar_livro(livro)
            return 130
        except Exception as e:                                    # noqa: BLE001
            codigo = 1
            motivo_falha = "%s: %s" % (type(e).__name__, e)
            print("  erro inesperado: %s" % e)

        if codigo == 0:
            ok += 1
            seguidas = 0
            livro["registros"][ctrl] = {"estado": "baixada",
                                        "pasta": nome_pasta(r),
                                        "em": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        elif codigo == 2:
            # fora de escopo: não é falha da API, e não conta para o disjuntor
            pulados += 1
            seguidas = 0
            livro["registros"][ctrl] = {"estado": "fora-de-escopo"}
        elif codigo == 3:
            # formato não suportado: também não é falha da API. Fica no livro
            # com estado próprio para (a) não rearmar o disjuntor e (b) sair da
            # fila de retentativa, já que amanhã o arquivo continuará em RTF.
            pulados += 1
            seguidas = 0
            livro["registros"][ctrl] = {
                "estado": "formato-nao-suportado",
                "pasta": nome_pasta(r),
                "em": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        else:
            falhou += 1
            seguidas += 1
            # GRAVA O MOTIVO. Ate 23/09 o livro dizia so "falhou", e nove
            # licitacoes ficaram sem explicacao — indistinguiveis entre "a API
            # caiu naquele minuto" (vale repetir) e "esta licitacao nao tem
            # documento" (repetir nunca vai resolver).
            livro["registros"][ctrl] = {"estado": "falhou",
                                        "motivo": motivo_falha or "codigo %s" % codigo,
                                        "pasta": nome_pasta(r),
                                        "em": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

        gravar_livro(livro)

        if seguidas >= falhas_seguidas_max:
            # DISJUNTOR. Se oito seguidas falharam, o problema não é a licitação
            # nona: é a API. Insistir nas 90 restantes só produz 90 linhas de
            # erro e faz o operador procurar o defeito no lugar errado.
            print("\n  DISJUNTOR: %d falhas seguidas. A API caiu de novo." % seguidas)
            print("  O livro guarda o progresso — rode de novo quando ela voltar.")
            break

        if i < len(cands):
            time.sleep(pausa)

    barra("FIM DO LOTE")
    print("  baixadas ... %d" % ok)
    print("  puladas .... %d  (já tinham pasta e arquivos, ou fora de escopo)" % pulados)
    print("  falharam ... %d" % falhou)
    execucao.registrar("28_baixar_licitacao.py", _t0,
                       baixadas=ok, puladas=pulados, falhas=falhou,
                       candidatas=ok + pulados + falhou)
    print("\n  livro: %s" % os.path.relpath(LIVRO, RAIZ))
    if falhou:
        print("  Rodar de novo retoma só as que faltam — o livro é idempotente.")
    return 0 if ok or pulados else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Baixa os documentos de uma licitação")
    ap.add_argument("--controle", default=None, help="CNPJ-1-SEQ/ANO")
    ap.add_argument("--auto", action="store_true",
                    help="primeira do corpus que passa no filtro e não foi baixada")
    ap.add_argument("--todas", action="store_true",
                    help="TODAS as que passam no filtro, com livro-razão e disjuntor")
    ap.add_argument("--limite", type=int, default=None,
                    help="com --todas, para após N licitações")
    ap.add_argument("--pausa", type=int, default=3,
                    help="segundos entre licitações no lote (padrão 3)")
    ap.add_argument("--reconferir", action="store_true",
                    help="lista as JA BAIXADAS que mudaram no PNCP")
    ap.add_argument("--listar", action="store_true", help="só lista as candidatas")
    ap.add_argument("--esperar", type=int, default=0,
                    help="segundos insistindo enquanto a API estiver fora")
    # 15 MINUTOS, E NAO 2 NEM 5.
    #
    # Quando a api/pncp/v1 esta em 503 a causa e banco de dados, nao bloqueio
    # (o corpo do erro diz `Failed to obtain JDBC Connection`, e nao ha
    # X-RateLimit-*, Retry-After nem 429 em lugar nenhum). Bater de 2 em 2
    # minutos nao acelera nada: ela nao volta porque foi perguntada, e insistir
    # so adiciona carga a um servico que ja esta sem conexao para dar.
    #
    # O custo de esperar mais e no maximo alguns minutos de atraso na deteccao;
    # o custo de insistir demais e empurrar uma API publica que outras pessoas
    # tambem estao tentando usar.
    #
    # Subiu de 5 para 15 em 23/09, com o portal INTEIRO fora - nao so a API,
    # o site tambem. Queda dessa ordem nao se mede em minutos, e sondar de 5 em
    # 5 durante uma manutencao longa e so ruido no log de quem esta tentando
    # levantar o servico.
    ap.add_argument("--intervalo", type=int, default=900,
                    help="segundos entre tentativas quando a API está fora (padrão 900)")
    a = ap.parse_args()

    if a.todas:
        return lote(esperar=a.esperar, intervalo_api=a.intervalo,
                    pausa=a.pausa, limite=a.limite)

    if a.listar or (a.auto and not a.controle):
        cands = candidatos()
        if a.listar:
            barra("CANDIDATAS — passam no filtro e ainda não estão em amostras/")
            for r in cands[:40]:
                print("  %-44s %-3s %-24s %s"
                      % ((r.get("orgao") or "")[:44], r.get("uf"),
                         (r.get("modalidade") or "")[:24], r.get("controle")))
            print("\n  %d candidata(s)" % len(cands))
            return 0
        if not cands:
            print("nenhuma candidata: tudo que passa no filtro já foi baixado.")
            return 2
        return baixar(cands[0], esperar=a.esperar)

    if not a.controle:
        print("informe --controle ou --auto (ou --listar para ver as candidatas)")
        return 2

    corpus = json.load(io.open(CORPUS, encoding="utf-8"))
    reg = next((r for r in corpus["registros"]
                if r.get("controle") == a.controle.strip()), None)
    if reg is None:
        print("controle não está no corpus: %s" % a.controle)
        print("rode 24_corpus_escopo.py para atualizar, ou use --listar")
        return 2
    return baixar(reg, esperar=a.esperar)


if __name__ == "__main__":
    raise SystemExit(main())
