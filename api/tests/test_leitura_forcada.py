# -*- coding: utf-8 -*-
"""
OCR forçado por arquivo e rotação (Pacote B, 26/09/2026) — a parte que não precisa de banco.

Sete licitações ficaram sem extração com o conteúdo no PDF: camada de texto cortada à direita (Piraí, Blumenau,
Pomerode), carimbo de autenticação em texto por cima de uma página em imagem (Cuiabá, SEFAZ/MT, Mineiros) e um
contrato escaneado de cabeça para baixo (Timon). `leitura.so_imagem` troca o arquivo marcado, na pasta temporária,
por uma cópia só de imagem com o mesmo nome e o mesmo número de páginas; o `carregar_paginas` intocado vê página sem
texto e faz o OCR sozinho. Os PDFs aqui são sintéticos e o OCR é o Tesseract do host, como em test_jobs.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from api import leitura  # noqa: E402
from fopa import condicoes as cond  # noqa: E402
from fopa import extrator  # noqa: E402

FRASE = "CONTRATO DE PRESTACAO DE SERVICOS BANCARIOS DA FOLHA DE PAGAMENTO DOS SERVIDORES MUNICIPAIS"
CORTADA = FRASE[:len(FRASE) // 2]


def _pagina_em_imagem(texto_visivel: str, girar: int = 0) -> Image.Image:
    """Uma página A4 com o texto desenhado, rasterizada a 200 dpi e girada como um scanner distraído giraria."""
    d = pymupdf.open()
    pg = d.new_page()
    for i in range(6):
        pg.insert_text((40, 90 + 40 * i), texto_visivel, fontsize=9)
    pix = pg.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    return img.rotate(girar, expand=True) if girar else img


def _pdf_imagem(img: Image.Image, camada: str | None = None) -> bytes:
    """PDF de uma página: a imagem ocupa a página e, se houver, `camada` vai por cima como texto invisível."""
    buf = io.BytesIO()
    img.save(buf, "PNG")
    d = pymupdf.open()
    pg = d.new_page()
    pg.insert_image(pg.rect, stream=buf.getvalue())
    if camada:
        for i in range(6):
            pg.insert_text((40, 90 + 40 * i), camada, fontsize=9, render_mode=3)
    return d.tobytes()


def _ler(pasta: Path):
    c = cond.Condicoes()
    return extrator.carregar_paginas(str(pasta), observador=c), c


def _normal(t: str) -> str:
    return " ".join(t.upper().split())


def test_camada_de_texto_cortada_e_lida_pela_imagem(tmp_path):
    nome = "01 - Edital - edital cortado.pdf"
    (tmp_path / nome).write_bytes(_pdf_imagem(_pagina_em_imagem(FRASE), camada=CORTADA))

    # sem marcação: a camada cortada passa do limiar (RN-19) e o OCR é pulado — o texto é só a metade
    paginas, c = _ler(tmp_path)
    assert c.arquivos_ocr == []
    assert "SERVIDORES" not in _normal(paginas[0].texto)

    assert leitura.so_imagem(str(tmp_path / nome)) == 1
    paginas, c = _ler(tmp_path)
    assert [(p.arquivo, p.numero) for p in paginas] == [(nome, 1)]     # mesmo nome, mesma página: a citação não muda
    assert c.arquivos_ocr == [nome]                                    # condição degradada, dita
    assert "FOLHA DE PAGAMENTO DOS SERVIDORES" in _normal(paginas[0].texto)


def test_pagina_de_cabeca_para_baixo_se_le_girando_180(tmp_path):
    nome = "01 - Minuta do Contrato - contrato invertido.pdf"
    (tmp_path / nome).write_bytes(_pdf_imagem(_pagina_em_imagem(FRASE, girar=180)))

    paginas, _ = _ler(tmp_path)
    assert "FOLHA DE PAGAMENTO" not in _normal(paginas[0].texto)       # o OCR do escaneado invertido sai ilegível

    leitura.so_imagem(str(tmp_path / nome), girar=180)
    paginas, _ = _ler(tmp_path)
    assert "FOLHA DE PAGAMENTO DOS SERVIDORES" in _normal(paginas[0].texto)


def test_so_imagem_preserva_paginas_e_troca_largura_por_altura_ao_girar_90(tmp_path):
    d = pymupdf.open()
    for _ in range(3):
        d.new_page(width=300, height=500).insert_text((20, 40), "pagina")
    caminho = tmp_path / "x.pdf"
    caminho.write_bytes(d.tobytes())

    assert leitura.so_imagem(str(caminho), girar=90) == 3
    with pymupdf.open(str(caminho)) as g:
        assert len(g) == 3
        assert all(round(p.rect.width) == 500 and round(p.rect.height) == 300 for p in g)
        assert all(not p.get_text().strip() for p in g)               # só imagem: nenhum texto nativo sobra


@pytest.mark.parametrize("girar", [45, -90, 360])
def test_so_imagem_recusa_angulo_fora_dos_quatro(tmp_path, girar):
    caminho = tmp_path / "x.pdf"
    caminho.write_bytes(_pdf_imagem(_pagina_em_imagem("x")))
    with pytest.raises(ValueError):
        leitura.so_imagem(str(caminho), girar=girar)


def test_marcacao_muda_a_versao_ocr_e_sem_marcacao_nao():
    # ARMADILHA do _gravar: ON CONFLICT (controle, assinatura_nomes, versao_ocr) DO NOTHING devolve a leitura antiga
    # quando a chave se repete. Outro OCR, outro texto: a configuração entra na versao_ocr.
    base = "linux-5.4.0-src+leptonica-1.84.1+tessdata_fast:abcdefabcdef+x86_64"
    assert leitura.versao_com_marcas(base, {}) == base
    a = leitura.versao_com_marcas(base, {"01 - Edital.pdf": 0})
    b = leitura.versao_com_marcas(base, {"01 - Edital.pdf": 180})
    c = leitura.versao_com_marcas(base, {"02 - Anexo.pdf": 0})
    assert a.startswith(base + "+forcado:") and len({a, b, c}) == 3
    assert leitura.versao_com_marcas(base, {"x.pdf": 0, "y.pdf": 90}) == \
        leitura.versao_com_marcas(base, {"y.pdf": 90, "x.pdf": 0})     # a ordem das marcações não conta
