# -*- coding: utf-8 -*-
"""
O fluxo de exceção do download: o arquivo que o PNCP entrega e NÃO é PDF.

O fluxo de exceção para o arquivo da API que não é PDF (25/09/2026). Até aqui todo
arquivo não-PDF era recusado como `formato_nao_suportado` e nunca mais tentado — em 25/09 eram 41 licitações de folha
presas assim, uma aberta (Vale de São Domingos/MT, edital em RTF com nome `.pdf`). Agora ele vira PDF, e o resto do
pipeline (páginas congeladas, OCR, a citação "arquivo — p. N") funciona igual — ler o texto cru perderia a página:

  - RTF, OLE (.doc/.xls), OOXML (.docx/.xlsx/.pptx), ODF e HTML → LibreOffice sem tela (`soffice --headless`);
  - PNG e JPEG → PDF de uma página (PyMuPDF); a leitura (W22) faz o OCR;
  - RAR (bsdtar) e ZIP sem PDF dentro → cada arquivo de dentro passa pela mesma regra (PDF entra como veio);
  - assinatura digital com o documento dentro (CAdES, o .p7s do ICP-Brasil) → o documento sai de dentro e segue
    a mesma regra.

Quem chama (`api/baixar.py`) registra o ORIGINAL com status `convertido` e cada PDF gerado como filho dele (`pai`),
com a origem na proveniência — como o ZIP. Se a conversão falhar, o arquivo continua `formato_nao_suportado`, com o
motivo escrito (`NaoConverteu`), nunca em silêncio.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import uuid
import zipfile
from dataclasses import dataclass

TEMPO_LIMITE = 180          # segundos por conversão do LibreOffice (um edital de 100 páginas leva ~10 s)
PROFUNDIDADE_MAXIMA = 3     # ZIP com RAR dentro (SAAE/RO, 25/09) abre; compactado em 4 camadas, não
LIMITE_NOME = 200           # bytes: arquivo dentro de arquivo soma os nomes, e o Linux recusa nome com mais de 255


class NaoConverteu(Exception):
    """A conversão não produziu um PDF que abre — a mensagem é o motivo que vai para `arquivos.motivo`."""


@dataclass
class Gerado:
    caminho: str        # o PDF gerado, na pasta de trabalho do job
    de: str             # o formato de origem ("RTF", "DOCX", "PDF" quando veio pronto de dentro de um RAR...)


# O formato real vem de `28_baixar_licitacao.formato_real` (pelos primeiros bytes); o rótulo curto vai para o nome.
OFFICE = {"RTF": ("RTF", ".rtf"), "OLE — .doc ou .xls antigo": ("DOC", ".doc"), "HTML ou XML": ("HTML", ".html")}
IMAGEM = {"PNG": "PNG", "JPEG": "JPEG"}


def _rodar(cmd, capture_output=True, text=True, errors="replace", timeout=None, env=None):
    """
    O `subprocess.run`, mas o tempo esgotado mata o GRUPO inteiro: o `soffice` é um script que sobe o `soffice.bin`, e
    matar só o filho direto deixava o soffice.bin órfão, convertendo para sempre (25/09 noite: o RTF de 12,7 MB de
    Guarantã do Norte passou do limite e o worker ficou a 250% de CPU).
    """
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE if capture_output else None,
                         stderr=subprocess.PIPE if capture_output else None, text=text, errors=errors, env=env,
                         start_new_session=True)
    try:
        saida, erro = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (AttributeError, ProcessLookupError, PermissionError):         # Windows não tem grupo; ou já morreu
            p.kill()
        p.communicate()
        raise
    return subprocess.CompletedProcess(cmd, p.returncode, saida, erro)


def _programa(*nomes: str) -> str | None:
    for n in nomes:
        achado = shutil.which(n)
        if achado:
            return achado
    return None


def libreoffice() -> str | None:
    return _programa("soffice", "libreoffice")


def bsdtar() -> str | None:
    """O `bsdtar` (libarchive) abre RAR 4 e 5. O `7zip` do Debian bookworm vem sem o código do RAR, que não é livre."""
    return _programa("bsdtar")


def _livre(caminho: str) -> str:
    """Dois `edital.pdf` em pastas diferentes do mesmo RAR não podem virar o mesmo arquivo: o segundo ganha " (2)"."""
    raiz, ext = os.path.splitext(caminho)
    n = 2
    while os.path.exists(caminho):
        caminho = "%s (%d)%s" % (raiz, n, ext)
        n += 1
    return caminho


def _ooxml(caminho: str) -> tuple[str, str] | None:
    """ZIP que é documento do Office (ou ODF): devolve (rótulo, extensão) para o LibreOffice; ZIP comum, None."""
    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = set(z.namelist())
            if "mimetype" in nomes:
                tipo = z.read("mimetype").decode("ascii", "replace")
                for chave, saida in (("opendocument.text", ("ODT", ".odt")),
                                     ("opendocument.spreadsheet", ("ODS", ".ods")),
                                     ("opendocument.presentation", ("ODP", ".odp"))):
                    if chave in tipo:
                        return saida
            if "[Content_Types].xml" in nomes:
                if any(n.startswith("word/") for n in nomes):
                    return ("DOCX", ".docx")
                if any(n.startswith("xl/") for n in nomes):
                    return ("XLSX", ".xlsx")
                if any(n.startswith("ppt/") for n in nomes):
                    return ("PPTX", ".pptx")
    except (zipfile.BadZipFile, OSError, KeyError):
        return None
    return None


def _eh_pdf(caminho: str) -> bool:
    with open(caminho, "rb") as f:
        return f.read(5) == b"%PDF-"


def _conferir(pdf: str) -> str:
    """Só conta como convertido o PDF que abre com páginas — o mesmo critério do `avaliar_baixado`."""
    import pymupdf
    try:
        with pymupdf.open(pdf) as d:
            if d.page_count == 0:
                raise NaoConverteu("o PDF gerado não tem páginas")
    except NaoConverteu:
        raise
    except Exception as e:                                                  # noqa: BLE001
        raise NaoConverteu("o PDF gerado não abre: %s" % str(e)[:80])
    return pdf


def _office(caminho: str, rotulo: str, extensao: str, saida: str, rodar) -> str:
    programa = libreoffice()
    if not programa:
        raise NaoConverteu("LibreOffice ausente no worker (a imagem precisa de libreoffice-writer-nogui)")
    trabalho = tempfile.mkdtemp(prefix="fopa-converter-", dir=os.path.dirname(saida) or None)
    try:
        # A extensão certa na entrada: o PNCP serve RTF com nome `.pdf`, e o LibreOffice escolhe o filtro também pelo
        # nome. O perfil do LibreOffice vai para uma pasta própria: dois jobs ao mesmo tempo não brigam pelo mesmo.
        entrada = os.path.join(trabalho, "documento" + extensao)
        shutil.copyfile(caminho, entrada)
        perfil = "file:///" + os.path.join(trabalho, "perfil-%s" % uuid.uuid4().hex).replace("\\", "/").lstrip("/")
        cmd = [programa, "-env:UserInstallation=" + perfil, "--headless", "--norestore", "--nolockcheck",
               "--convert-to", "pdf", "--outdir", trabalho, entrada]
        try:
            r = rodar(cmd, capture_output=True, text=True, errors="replace", timeout=TEMPO_LIMITE)
        except subprocess.TimeoutExpired:
            raise NaoConverteu("o LibreOffice passou de %d s convertendo o %s" % (TEMPO_LIMITE, rotulo))
        gerado = os.path.join(trabalho, "documento.pdf")
        if not os.path.isfile(gerado):
            erro = ((getattr(r, "stderr", "") or "") + " " + (getattr(r, "stdout", "") or "")).strip()
            raise NaoConverteu("o LibreOffice não gerou PDF a partir do %s%s" % (rotulo, (": " + erro[:120]) if erro else ""))
        shutil.move(gerado, saida)
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)
    return _conferir(saida)


def _imagem(caminho: str, saida: str) -> str:
    import pymupdf
    try:
        with pymupdf.open(caminho) as img:
            dados = img.convert_to_pdf()
    except Exception as e:                                                  # noqa: BLE001
        raise NaoConverteu("a imagem não abre: %s" % str(e)[:80])
    with open(saida, "wb") as f:
        f.write(dados)
    return _conferir(saida)


def _extrair(caminho: str, destino: str, rotulo: str, rodar) -> list[str]:
    os.makedirs(destino, exist_ok=True)
    if rotulo == "ZIP":
        try:
            with zipfile.ZipFile(caminho) as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    alvo = os.path.normpath(os.path.join(destino, info.filename))
                    # "../x" num ZIP escreveria fora da pasta do job: recusar custa menos que confiar.
                    if not alvo.startswith(os.path.normpath(destino) + os.sep):
                        continue
                    os.makedirs(os.path.dirname(alvo), exist_ok=True)
                    with z.open(info) as src, open(alvo, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        except (zipfile.BadZipFile, OSError) as e:
            raise NaoConverteu("o ZIP não abre: %s" % str(e)[:80])
    else:
        programa = bsdtar()
        if not programa:
            raise NaoConverteu("bsdtar ausente no worker (a imagem precisa do pacote libarchive-tools para abrir RAR)")
        # O bsdtar recusa "../" e caminho absoluto por padrão. Nomes com acento dentro do RAR pedem locale UTF-8:
        # no locale C ele avisa, sai com erro e o RAR inteiro seria recusado.
        try:
            r = rodar([programa, "-x", "-f", caminho, "-C", destino], capture_output=True, text=True,
                      errors="replace", timeout=TEMPO_LIMITE, env=dict(os.environ, LC_ALL="C.UTF-8"))
        except subprocess.TimeoutExpired:
            raise NaoConverteu("o bsdtar passou de %d s abrindo o RAR" % TEMPO_LIMITE)
        if getattr(r, "returncode", 0) != 0:
            raise NaoConverteu("o bsdtar não abriu o RAR: %s" % ((getattr(r, "stderr", "") or "").strip()[:120]))
    arquivos = []
    for raiz, pastas, nomes in os.walk(destino):
        pastas.sort()                              # a mesma ordem a cada download: o mesmo nome para o mesmo arquivo
        for n in sorted(nomes):
            p = os.path.join(raiz, n)
            if not os.path.islink(p):              # um link dentro do RAR apontaria para fora da pasta do job
                arquivos.append(p)
    return arquivos


def _cortar(texto: str, n_bytes: int) -> str:
    return texto.encode("utf-8")[:max(n_bytes, 0)].decode("utf-8", "ignore").rstrip()


def _nome(base: str, rotulo: str) -> str:
    """`01 - Edital - EDITAL.pdf` (que é RTF) → `01 - Edital - EDITAL (convertido de RTF).pdf`."""
    raiz = base[:-4] if base.lower().endswith(".pdf") else os.path.splitext(base)[0]
    sufixo = " (convertido de %s).pdf" % rotulo
    return _cortar(raiz, LIMITE_NOME - len(sufixo.encode("utf-8"))) + sufixo


def _nome_membro(raiz: str, membro: str) -> str:
    """`<raiz> -- <membro>.pdf`; se passar do limite, corta a raiz — o nome do membro é o que identifica o arquivo."""
    membro = membro[:-4] if membro.lower().endswith(".pdf") else membro
    membro = _cortar(membro, LIMITE_NOME // 2) + ".pdf"
    return _cortar(raiz, LIMITE_NOME - len((" -- " + membro).encode("utf-8"))) + " -- " + membro


# Assinatura digital "attached" (CAdES/PKCS#7 — o .p7s/.p7m do ICP-Brasil): o documento vai DENTRO da assinatura.
_OID_ASSINADO = bytes.fromhex("2a864886f70d010702")         # 1.2.840.113549.1.7.2, signedData


def _tlv(dados: bytes, i: int) -> tuple[int, int, int, int]:
    """O TLV do DER/BER que começa em `i`: (tag, início do valor, fim do valor, próximo). Aceita o comprimento
    indefinido do BER: os filhos até o 00 00."""
    tag, n, j = dados[i], dados[i + 1], i + 2
    if n == 0x80:
        k = j
        while dados[k:k + 2] != b"\x00\x00":
            k = _tlv(dados, k)[3]
        return tag, j, k, k + 2
    if n & 0x80:
        m = n & 0x7F
        n, j = int.from_bytes(dados[j:j + m], "big"), j + m
    if j + n > len(dados):
        raise ValueError("o TLV passa do fim do arquivo")
    return tag, j, j + n, j + n


def _filhos(dados: bytes, ini: int, fim: int) -> list:
    saida, i = [], ini
    while i < fim:
        saida.append(_tlv(dados, i))
        i = saida[-1][3]
    return saida


def _de_dentro_da_assinatura(dados: bytes) -> bytes | None:
    """O documento de dentro de uma assinatura CAdES "attached" — sem conferir a assinatura; None se não for uma."""
    try:
        tag, ini, fim, _ = _tlv(dados, 0)
        info = _filhos(dados, ini, fim) if tag == 0x30 else []
        if (len(info) < 2 or info[0][0] != 0x06 or dados[info[0][1]:info[0][2]] != _OID_ASSINADO
                or info[1][0] != 0xA0):
            return None
        assinado = _filhos(dados, info[1][1], info[1][2])[0]               # SignedData
        encapsulado = _filhos(dados, assinado[1], assinado[2])[2]          # versão, algoritmos, encapContentInfo
        partes = _filhos(dados, encapsulado[1], encapsulado[2])
        if len(partes) < 2 or partes[1][0] != 0xA0:
            return None                                                    # "detached": o documento não vem junto
        octetos = _filhos(dados, partes[1][1], partes[1][2])[0]
        if octetos[0] == 0x04:
            return dados[octetos[1]:octetos[2]]
        if octetos[0] == 0x24:                                             # OCTET STRING em pedaços (BER)
            return b"".join(dados[p[1]:p[2]] for p in _filhos(dados, octetos[1], octetos[2]))
    except (IndexError, ValueError):
        return None
    return None


def _assinado(caminho: str, formato: str, pasta: str, base: str, rodar, formato_de, profundidade: int) -> list[Gerado]:
    """
    Câmara de Espigão do Oeste/RO, 25/09: `Termo_de_Referencia-14.pdf` começa com 30 83 — é a assinatura ICP-Brasil
    com o PDF dentro. O documento sai de dentro (a assinatura não é conferida) e segue a mesma regra: PDF entra como
    veio, .doc assinado vai ao LibreOffice. Assinatura de assinatura (coassinatura em série) também abre.
    """
    with open(caminho, "rb") as f:
        dados = f.read()
    camadas = 0
    while camadas < 5:
        dentro = _de_dentro_da_assinatura(dados)
        if dentro is None:
            break
        dados, camadas = dentro, camadas + 1
    if not camadas:
        raise NaoConverteu("formato %s não tem conversão para PDF" % formato)
    if dados.startswith(b"%PDF-"):
        destino = _livre(os.path.join(pasta, _nome(base, "P7S")))
        with open(destino, "wb") as f:
            f.write(dados)
        return [Gerado(_conferir(destino), "P7S")]
    interno = os.path.join(tempfile.mkdtemp(prefix="p7s-", dir=pasta), "documento")
    with open(interno, "wb") as f:
        f.write(dados)
    return para_pdf(interno, formato_de(interno), pasta, base, rodar=rodar, formato_de=formato_de,
                    profundidade=profundidade + 1)


def para_pdf(caminho: str, formato: str, pasta: str, base: str, *, rodar=_rodar,
             formato_de=None, profundidade: int = 0) -> list[Gerado]:
    """
    O arquivo `caminho` (baixado como `base`, formato real `formato`) vira um ou mais PDFs em `pasta`.

    Devolve os gerados; levanta `NaoConverteu` com o motivo se nada sair. `formato_de` é o `28.formato_real`
    (injetável nos testes); `rodar` é o `subprocess.run` (idem).
    """
    if formato_de is None:
        from .baixar import m28
        formato_de = m28().formato_real
    if formato == "PDF":
        # Novorizonte/MG, 25/09: o PNCP entrega o edital cortado em 1 MiB (sem %%EOF e sem a árvore de páginas) — não
        # há o que converter; o motivo diz o que é, para ninguém procurar o erro no produto.
        with open(caminho, "rb") as f:
            f.seek(0, os.SEEK_END)
            tamanho = f.tell()
            f.seek(max(0, tamanho - 2048))
            fim = f.read()
        if b"%%EOF" not in fim:
            raise NaoConverteu(f"é PDF, mas está cortado: termina em {tamanho} bytes sem o fim do arquivo (%%EOF) —"
                               f" o PNCP entrega assim")
        raise NaoConverteu("é PDF, mas está quebrado: o leitor não acha nenhuma página")
    if formato in OFFICE:
        rotulo, extensao = OFFICE[formato]
        return [Gerado(_office(caminho, rotulo, extensao, _livre(os.path.join(pasta, _nome(base, rotulo))), rodar),
                       rotulo)]
    if formato in IMAGEM:
        rotulo = IMAGEM[formato]
        return [Gerado(_imagem(caminho, _livre(os.path.join(pasta, _nome(base, rotulo)))), rotulo)]
    if formato.startswith("desconhecido"):
        if profundidade >= PROFUNDIDADE_MAXIMA:
            raise NaoConverteu("formato %s não tem conversão para PDF" % formato)
        return _assinado(caminho, formato, pasta, base, rodar, formato_de, profundidade)
    if formato.startswith("ZIP"):
        office = _ooxml(caminho)
        if office:
            rotulo, extensao = office
            return [Gerado(_office(caminho, rotulo, extensao, _livre(os.path.join(pasta, _nome(base, rotulo))), rodar),
                           rotulo)]
        conteiner = "ZIP"
    elif formato == "RAR":
        conteiner = "RAR"
    else:
        raise NaoConverteu("formato %s não tem conversão para PDF" % formato)

    if profundidade >= PROFUNDIDADE_MAXIMA:
        raise NaoConverteu("%s compactado em mais de %d camadas" % (conteiner, PROFUNDIDADE_MAXIMA))
    raiz = base[:-4] if base.lower().endswith(".pdf") else os.path.splitext(base)[0]
    dentro = _extrair(caminho, os.path.join(pasta, "%s-%s" % (conteiner.lower(), uuid.uuid4().hex[:8])), conteiner, rodar)
    gerados, motivos = [], []
    for membro in dentro:
        nome_membro = os.path.basename(membro)
        if _eh_pdf(membro):
            destino = _livre(os.path.join(pasta, _nome_membro(raiz, nome_membro)))
            shutil.copyfile(membro, destino)
            try:
                gerados.append(Gerado(_conferir(destino), "PDF"))
            except NaoConverteu as e:
                motivos.append("%s: %s" % (nome_membro, e))
            continue
        try:
            gerados += para_pdf(membro, formato_de(membro), pasta, "%s -- %s" % (raiz, nome_membro), rodar=rodar,
                                formato_de=formato_de, profundidade=profundidade + 1)
        except NaoConverteu as e:
            motivos.append("%s: %s" % (nome_membro, e))
    if not gerados:
        raise NaoConverteu("%s sem nada que vire PDF (%s)" % (conteiner, "; ".join(motivos)[:200] or "vazio"))
    return gerados


__all__ = ["para_pdf", "NaoConverteu", "Gerado", "libreoffice", "bsdtar"]
