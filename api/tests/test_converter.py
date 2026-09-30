# -*- coding: utf-8 -*-
"""
O fluxo de exceção do download (api/converter.py): o arquivo que o PNCP entrega e não é PDF vira PDF.

O fluxo de exceção para o arquivo da API que não é PDF (25/09/2026). No host não há
LibreOffice nem bsdtar: os testes de orquestração usam executáveis falsos; o de imagem é real (PyMuPDF); o do
LibreOffice de verdade só roda dentro da imagem do worker (`docker run ... pytest api/tests/test_converter.py`).
"""
from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from api import converter  # noqa: E402

RTF = b"{\\rtf1\\ansi\\deff0 {\\fonttbl {\\f0 Arial;}} \\f0\\fs24 EDITAL DE CHAMAMENTO PUBLICO 004/2026 para a folha de pagamento\\par}"


def _pdf(caminho: str, texto: str = "pagina de teste") -> str:
    import pymupdf
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), texto)
    d.save(caminho)
    d.close()
    return caminho


def _formato(caminho: str) -> str:
    with open(caminho, "rb") as f:
        cabeca = f.read(8)
    if cabeca.startswith(b"%PDF-"):
        return "PDF"
    if cabeca.startswith(b"{\\rtf"):
        return "RTF"
    if cabeca.startswith(b"PK\x03\x04"):
        return "ZIP ou OOXML (.docx/.xlsx)"
    if cabeca.startswith(b"\x89PNG"):
        return "PNG"
    if cabeca.startswith(b"Rar!"):
        return "RAR"
    return "desconhecido (%r)" % cabeca[:6]


def _der(tag: int, conteudo: bytes) -> bytes:
    n = len(conteudo)
    if n < 0x80:
        return bytes([tag, n]) + conteudo
    k = (n.bit_length() + 7) // 8
    return bytes([tag, 0x80 | k]) + n.to_bytes(k, "big") + conteudo


def _p7s(documento: bytes, ber: bool = False) -> bytes:
    """
    Uma assinatura CAdES "attached" (o .p7s do ICP-Brasil) com o documento dentro — só a estrutura do CMS, sem a
    criptografia: o conversor não confere a assinatura, só tira o documento de dentro. `ber=True` grava o documento
    como alguns assinadores fazem: OCTET STRING em pedaços e comprimento indefinido.
    """
    oid_assinado = _der(0x06, bytes.fromhex("2a864886f70d010702"))
    oid_dados = _der(0x06, bytes.fromhex("2a864886f70d010701"))
    if ber:
        pedacos = b"".join(_der(0x04, documento[i:i + 1000]) for i in range(0, len(documento), 1000))
        conteudo = b"\xa0\x80" + b"\x24\x80" + pedacos + b"\x00\x00" + b"\x00\x00"
    else:
        conteudo = _der(0xA0, _der(0x04, documento))
    assinado = _der(0x30, _der(0x02, b"\x01") + _der(0x31, b"") + _der(0x30, oid_dados + conteudo) + _der(0x31, b""))
    return _der(0x30, oid_assinado + _der(0xA0, assinado))


def _soffice_falso(chamadas):
    """Faz o papel do `soffice --convert-to pdf`: grava documento.pdf na --outdir."""
    def rodar(cmd, **_):
        chamadas.append(cmd)
        saida = cmd[cmd.index("--outdir") + 1]
        _pdf(os.path.join(saida, "documento.pdf"), "convertido de " + os.path.basename(cmd[-1]))

        class R:
            returncode, stdout, stderr = 0, "", ""
        return R()
    return rodar


def test_imagem_vira_pdf_de_uma_pagina(tmp_path):
    import pymupdf
    png = tmp_path / "aviso.png"
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 20), False)
    pix.clear_with(200)
    pix.save(str(png))
    (g,) = converter.para_pdf(str(png), "PNG", str(tmp_path), "01 - Aviso - aviso.pdf", formato_de=_formato)
    assert g.de == "PNG" and os.path.basename(g.caminho) == "01 - Aviso - aviso (convertido de PNG).pdf"
    with pymupdf.open(g.caminho) as d:
        assert d.page_count == 1


def test_rtf_com_nome_de_pdf_vai_ao_libreoffice_com_a_extensao_certa(tmp_path, monkeypatch):
    # Vale de São Domingos/MT: o edital é RTF servido como ".pdf". O LibreOffice escolhe o filtro também pelo nome.
    monkeypatch.setattr(converter, "libreoffice", lambda: "soffice")
    rtf = tmp_path / "01 - Edital - EDITAL.pdf"
    rtf.write_bytes(RTF)
    chamadas = []
    (g,) = converter.para_pdf(str(rtf), "RTF", str(tmp_path), rtf.name, rodar=_soffice_falso(chamadas),
                              formato_de=_formato)
    assert os.path.basename(g.caminho) == "01 - Edital - EDITAL (convertido de RTF).pdf" and g.de == "RTF"
    (cmd,) = chamadas
    assert cmd[0] == "soffice" and "--headless" in cmd and cmd[-1].endswith("documento.rtf")
    assert any(c.startswith("-env:UserInstallation=") for c in cmd)      # perfil próprio: jobs não brigam


def test_docx_e_zip_que_e_documento_nao_zip_comum(tmp_path, monkeypatch):
    monkeypatch.setattr(converter, "libreoffice", lambda: "soffice")
    docx = tmp_path / "02 - Anexo - modelo.pdf"
    with zipfile.ZipFile(docx, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
    chamadas = []
    (g,) = converter.para_pdf(str(docx), "ZIP ou OOXML (.docx/.xlsx)", str(tmp_path), docx.name,
                              rodar=_soffice_falso(chamadas), formato_de=_formato)
    assert g.de == "DOCX" and chamadas[0][-1].endswith("documento.docx")


def test_rar_abre_e_cada_arquivo_de_dentro_segue_a_regra(tmp_path, monkeypatch):
    monkeypatch.setattr(converter, "libreoffice", lambda: "soffice")
    monkeypatch.setattr(converter, "bsdtar", lambda: "bsdtar")
    rar = tmp_path / "03 - Edital - pacote.pdf"
    rar.write_bytes(b"Rar!\x1a\x07\x00falso")
    chamadas = []
    soffice = _soffice_falso(chamadas)

    def rodar(cmd, **kw):
        if cmd[0] == "bsdtar":                                # extrai um PDF pronto e um RTF
            destino = cmd[cmd.index("-C") + 1]
            os.makedirs(destino, exist_ok=True)
            _pdf(os.path.join(destino, "edital.pdf"), "edital de dentro do rar")
            with open(os.path.join(destino, "termo.rtf"), "wb") as f:
                f.write(RTF)

            class R:
                returncode, stdout, stderr = 0, "", ""
            return R()
        return soffice(cmd, **kw)

    gerados = converter.para_pdf(str(rar), "RAR", str(tmp_path), rar.name, rodar=rodar, formato_de=_formato)
    assert sorted((os.path.basename(g.caminho), g.de) for g in gerados) == [
        ("03 - Edital - pacote -- edital.pdf", "PDF"),
        ("03 - Edital - pacote -- termo (convertido de RTF).pdf", "RTF")]


def test_sem_ferramenta_ou_formato_desconhecido_diz_o_porque(tmp_path, monkeypatch):
    monkeypatch.setattr(converter, "libreoffice", lambda: None)
    rtf = tmp_path / "x.pdf"
    rtf.write_bytes(RTF)
    with pytest.raises(converter.NaoConverteu, match="LibreOffice ausente"):
        converter.para_pdf(str(rtf), "RTF", str(tmp_path), "x.pdf", formato_de=_formato)
    with pytest.raises(converter.NaoConverteu, match="não tem conversão"):
        converter.para_pdf(str(rtf), "desconhecido (b'{\"anoC')", str(tmp_path), "x.pdf", formato_de=_formato)
    monkeypatch.setattr(converter, "bsdtar", lambda: None)
    rar = tmp_path / "y.pdf"
    rar.write_bytes(b"Rar!\x1a\x07\x00falso")
    with pytest.raises(converter.NaoConverteu, match="libarchive-tools"):
        converter.para_pdf(str(rar), "RAR", str(tmp_path), "y.pdf", formato_de=_formato)


def test_pdf_cortado_diz_que_esta_cortado(tmp_path):
    # Novorizonte/MG, 25/09: o PNCP entrega o edital com exatamente 1 MiB, sem %%EOF nem árvore de páginas — o leitor
    # acha 0 páginas. Não há o que converter; o motivo tem de dizer o que é ("formato PDF não tem conversão" confundia).
    inteiro = open(_pdf(str(tmp_path / "x.pdf"), "edital de folha"), "rb").read()
    pdf = tmp_path / "01 - Edital - EDITAL.pdf"
    pdf.write_bytes(inteiro[: len(inteiro) // 2])
    with pytest.raises(converter.NaoConverteu, match="cortado"):
        converter.para_pdf(str(pdf), "PDF", str(tmp_path), pdf.name, formato_de=_formato)


@pytest.mark.skipif(os.name == "nt", reason="grupo de processos é POSIX: roda na imagem do worker")
def test_tempo_esgotado_mata_o_grupo_inteiro(tmp_path):
    # 25/09 noite: o RTF de 12,7 MB de Guarantã do Norte passou do limite; o subprocess.run matou só o `soffice` (um
    # script) e o soffice.bin ficou órfão convertendo — o worker a 250% de CPU. O tempo esgotado mata o grupo inteiro.
    import subprocess
    import time
    pidfile = tmp_path / "neto.pid"
    with pytest.raises(subprocess.TimeoutExpired):
        converter._rodar(["sh", "-c", "sleep 60 & echo $! > %s; wait" % pidfile], timeout=1)
    neto = int(pidfile.read_text())
    time.sleep(0.5)
    try:
        estado = open("/proc/%d/status" % neto).read()
    except OSError:
        estado = ""                                                            # já sumiu
    assert not estado or "zombie" in estado, estado[:80]


def test_zip_com_dois_arquivos_de_mesmo_nome_gera_dois_pdfs(tmp_path, monkeypatch):
    # "lote1/termo.rtf" e "lote2/termo.rtf" no mesmo ZIP: sem cuidado, o segundo PDF sobrescreveria o primeiro. E a
    # ordem é a mesma a cada download — o mesmo arquivo recebe sempre o mesmo nome (e a mesma linha em `arquivos`).
    monkeypatch.setattr(converter, "libreoffice", lambda: "soffice")
    zp = tmp_path / "04 - Anexo - anexos.pdf"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("lote2/termo.rtf", RTF)
        z.writestr("lote1/termo.rtf", RTF)
    chamadas = []
    gerados = converter.para_pdf(str(zp), "ZIP ou OOXML (.docx/.xlsx)", str(tmp_path), zp.name,
                                 rodar=_soffice_falso(chamadas), formato_de=_formato)
    assert [os.path.basename(g.caminho) for g in gerados] == [
        "04 - Anexo - anexos -- termo (convertido de RTF).pdf",
        "04 - Anexo - anexos -- termo (convertido de RTF) (2).pdf"]
    assert all(os.path.isfile(g.caminho) for g in gerados) and len(chamadas) == 2


def test_pdf_assinado_sai_de_dentro_da_assinatura(tmp_path, monkeypatch):
    # Câmara de Espigão do Oeste/RO, 25/09: o RAR trazia "Termo_de_Referencia-14.pdf" que começa com 30 83 — uma
    # assinatura ICP-Brasil (CAdES "attached") com o PDF dentro. DER ou BER, e assinatura de assinatura.
    pdf = open(_pdf(str(tmp_path / "tr.pdf"), "termo de referencia assinado"), "rb").read()
    for n, assinatura in enumerate((_p7s(pdf), _p7s(pdf, ber=True), _p7s(_p7s(pdf)))):
        p7s = tmp_path / ("0%d - Termo de Referência - TR.pdf" % n)
        p7s.write_bytes(assinatura)
        (g,) = converter.para_pdf(str(p7s), _formato(str(p7s)), str(tmp_path), p7s.name, formato_de=_formato)
        assert g.de == "P7S" and os.path.basename(g.caminho) == "0%d - Termo de Referência - TR (convertido de P7S).pdf" % n
        with open(g.caminho, "rb") as f:
            assert f.read() == pdf
    # o documento assinado que não é PDF segue a regra (um RTF assinado vai ao LibreOffice)
    monkeypatch.setattr(converter, "libreoffice", lambda: "soffice")
    rtf = tmp_path / "09 - Edital - EDITAL.pdf"
    rtf.write_bytes(_p7s(RTF))
    chamadas = []
    (g,) = converter.para_pdf(str(rtf), _formato(str(rtf)), str(tmp_path), rtf.name, rodar=_soffice_falso(chamadas),
                              formato_de=_formato)
    assert g.de == "RTF" and chamadas[0][-1].endswith("documento.rtf")
    # 30 83 que não é assinatura continua sem conversão, com o motivo
    lixo = tmp_path / "10 - Anexo - x.pdf"
    lixo.write_bytes(b"\x30\x83\x00\x00\x05lixo!")
    with pytest.raises(converter.NaoConverteu, match="não tem conversão"):
        converter.para_pdf(str(lixo), _formato(str(lixo)), str(tmp_path), lixo.name, formato_de=_formato)


def test_rar_dentro_de_zip_tambem_abre(tmp_path, monkeypatch):
    # SAAE/RO, 25/09: o edital é um ZIP com um RAR dentro, e os documentos estão no RAR.
    monkeypatch.setattr(converter, "libreoffice", lambda: "soffice")
    monkeypatch.setattr(converter, "bsdtar", lambda: "bsdtar")
    zp = tmp_path / "01 - Edital - 162358_editais.zip.pdf"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("28 EDITAL 028-2025.rar", b"Rar!\x1a\x07\x00falso")
    chamadas = []
    soffice = _soffice_falso(chamadas)

    def rodar(cmd, **kw):
        if cmd[0] == "bsdtar":
            with open(os.path.join(cmd[cmd.index("-C") + 1], "edital.rtf"), "wb") as f:
                f.write(RTF)

            class R:
                returncode, stdout, stderr = 0, "", ""
            return R()
        return soffice(cmd, **kw)

    (g,) = converter.para_pdf(str(zp), "ZIP ou OOXML (.docx/.xlsx)", str(tmp_path), zp.name, rodar=rodar,
                              formato_de=_formato)
    assert os.path.basename(g.caminho) == (
        "01 - Edital - 162358_editais.zip -- 28 EDITAL 028-2025 -- edital (convertido de RTF).pdf")


def test_nome_longo_e_cortado_sem_perder_o_sufixo():
    # Arquivo dentro de arquivo soma os nomes, e o Linux não aceita nome de arquivo com mais de 255 bytes. (Só as
    # funções de nome: no Windows do host o caminho inteiro passaria de 260 caracteres antes do teste.)
    raiz = "01 - Edital - " + "EDITAL Nº 028-SAAE-2025 PROC ADM Nº 232-2025 AMPLA " * 6
    convertido = converter._nome(raiz + ".pdf", "RTF")
    membro = converter._nome_membro(raiz, "ANEXO I - TERMO DE REFERENCIA.pdf")
    for nome in (convertido, membro):
        assert len(nome.encode("utf-8")) <= converter.LIMITE_NOME and nome.startswith("01 - Edital - EDITAL Nº 028")
    assert convertido.endswith(" (convertido de RTF).pdf")
    assert membro.endswith(" -- ANEXO I - TERMO DE REFERENCIA.pdf")
    assert converter._nome("01 - Edital - EDITAL.pdf", "RTF") == "01 - Edital - EDITAL (convertido de RTF).pdf"
    assert converter._nome_membro("03 - Edital - pacote", "termo") == "03 - Edital - pacote -- termo.pdf"


def _rar4(membros: dict) -> bytes:
    """
    Um RAR 4 de verdade, montado byte a byte com os arquivos só armazenados (método 0x30) — o `rar` que cria RAR não
    é livre e não está na imagem, mas o bsdtar abre este. Membro `(dados, modo)` escolhe o modo Unix (link: 0o120777).
    """
    import struct
    import zlib

    def bloco(tipo, flags, corpo):
        cabecalho = struct.pack("<BHH", tipo, flags, 7 + len(corpo)) + corpo
        return struct.pack("<H", zlib.crc32(cabecalho) & 0xFFFF) + cabecalho

    saida = b"Rar!\x1a\x07\x00" + bloco(0x73, 0, b"\x00" * 6)
    for nome, dados in membros.items():
        dados, modo = dados if isinstance(dados, tuple) else (dados, 0o100644)
        n = nome.encode("ascii")
        corpo = struct.pack("<IIBIIBBHI", len(dados), len(dados), 3, zlib.crc32(dados), 0x5D396000, 29, 0x30,
                            len(n), modo) + n
        saida += bloco(0x74, 0x8000, corpo) + dados
    return saida + bloco(0x7B, 0x4000, b"")


def _ferramenta_real(*nomes):
    faltam = [n for n in nomes if getattr(converter, n)() is None]
    return pytest.mark.skipif(bool(faltam), reason="%s só na imagem do worker" % ", ".join(faltam))


@_ferramenta_real("libreoffice")
def test_libreoffice_de_verdade_converte_o_rtf(tmp_path):
    import pymupdf
    rtf = tmp_path / "01 - Edital - EDITAL.pdf"
    rtf.write_bytes(RTF)
    (g,) = converter.para_pdf(str(rtf), "RTF", str(tmp_path), rtf.name)
    with pymupdf.open(g.caminho) as d:
        assert d.page_count >= 1 and "CHAMAMENTO PUBLICO 004/2026" in d[0].get_text()


@_ferramenta_real("libreoffice")
@pytest.mark.parametrize("fonte,conteudo,alvo,texto", [
    ("edital.rtf", RTF, "doc", "CHAMAMENTO PUBLICO 004/2026"),
    ("planilha.csv", b"orgao,objeto\nPrefeitura de Inhacora,FOLHA 2026\n", "xls", "FOLHA 2026"),
])
def test_libreoffice_de_verdade_le_doc_e_xls_antigos(tmp_path, fonte, conteudo, alvo, texto):
    # .doc e .xls antigos têm a mesma casca (OLE, d0 cf 11 e0) e o mesmo rótulo do `28.formato_real`; os dois vão ao
    # LibreOffice como ".doc" — a planilha tem que ser reconhecida pelo conteúdo, não pelo nome.
    import pymupdf
    from api.baixar import m28
    origem = tmp_path / fonte
    origem.write_bytes(conteudo)
    perfil = "file:///" + str(tmp_path / "perfil").replace(os.sep, "/").lstrip("/")
    subprocess.run([converter.libreoffice(), "-env:UserInstallation=" + perfil, "--headless", "--convert-to", alvo,
                    "--outdir", str(tmp_path / "ole"), str(origem)], check=True, capture_output=True, timeout=180)
    (ole,) = (tmp_path / "ole").iterdir()
    disfarcado = tmp_path / "02 - Edital - EDITAL.pdf"                    # como o PNCP serve: nome .pdf, bytes OLE
    disfarcado.write_bytes(ole.read_bytes())
    formato = m28().formato_real(str(disfarcado))
    assert formato == "OLE — .doc ou .xls antigo"
    (g,) = converter.para_pdf(str(disfarcado), formato, str(tmp_path), disfarcado.name)
    with pymupdf.open(g.caminho) as d:
        assert texto in "".join(p.get_text() for p in d)


@_ferramenta_real("bsdtar")
def test_de_verdade_zip_com_rar_de_pdf_assinado(tmp_path):
    # Os dois casos de 25/09 juntos, com o bsdtar e o `28.formato_real` de verdade: ZIP → RAR (SAAE/RO) → PDF
    # assinado pelo ICP-Brasil (Câmara de Espigão do Oeste/RO).
    pdf = open(_pdf(str(tmp_path / "x.pdf"), "termo de referencia assinado"), "rb").read()
    zp = tmp_path / "01 - Edital - 162358_editais.zip.pdf"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("28 EDITAL.rar", _rar4({"Termo_de_Referencia-14.pdf": _p7s(pdf)}))
    (g,) = converter.para_pdf(str(zp), "ZIP ou OOXML (.docx/.xlsx)", str(tmp_path), zp.name)
    assert g.de == "P7S" and os.path.basename(g.caminho) == (
        "01 - Edital - 162358_editais.zip -- 28 EDITAL -- Termo_de_Referencia-14 (convertido de P7S).pdf")
    with open(g.caminho, "rb") as f:
        assert f.read() == pdf


@_ferramenta_real("libreoffice", "bsdtar")
def test_rar_de_verdade_abre_converte_e_ignora_link(tmp_path):
    import pymupdf
    pdf = open(_pdf(str(tmp_path / "x.pdf"), "edital de dentro do rar"), "rb").read()
    rar = tmp_path / "03 - Edital - pacote.pdf"
    rar.write_bytes(_rar4({"edital.pdf": pdf, "termo.rtf": RTF, "senha.pdf": (b"/etc/passwd", 0o120777)}))
    gerados = converter.para_pdf(str(rar), "RAR", str(tmp_path), rar.name)
    assert {os.path.basename(g.caminho): g.de for g in gerados} == {
        "03 - Edital - pacote -- edital.pdf": "PDF",
        "03 - Edital - pacote -- termo (convertido de RTF).pdf": "RTF"}
    with pymupdf.open(next(g.caminho for g in gerados if g.de == "RTF")) as d:
        assert "CHAMAMENTO PUBLICO 004/2026" in d[0].get_text()
