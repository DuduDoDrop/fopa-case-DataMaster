# -*- coding: utf-8 -*-
"""
A baseline de OCR precisa provar duas coisas antes de servir de referência:

  1. que ela se reproduz na máquina que a gerou — `medir.py` contra o próprio
     host tem de dar 6/6 idênticas e similaridade mínima 1,0. Se nem o host se
     reproduz, qualquer diferença medida na imagem Docker é ruído, não sinal;
  2. que o `manifest.json` descreve os arquivos que estão no disco — sha do
     PDF, 6 PNG, 6 textos, dpi e configuração iguais às do pipeline. Um
     manifesto desatualizado transformaria a medição em comparação de coisas
     diferentes sem ninguém perceber.

Nada aqui usa mock: o Tesseract roda de verdade. Sem Tesseract o teste é
PULADO com o motivo, nunca aprovado em silêncio.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import medir  # noqa: E402


def _sha256(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


@pytest.fixture(scope="module")
def manifest() -> dict:
    with open(os.path.join(AQUI, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def tesseract() -> str:
    try:
        return medir.resolver_tesseract(None)
    except medir.ocr.OcrIndisponivel as e:
        pytest.skip("Tesseract indisponível: %s" % e)


@pytest.fixture(scope="module")
def mesmo_host(manifest, tesseract) -> bool:
    """
    Esta é a máquina que gerou a baseline? (mesmo sistema e mesmo build do Tesseract do manifest)

    Reproduzir 6/6 é prova do HOST que gerou a baseline. Dentro da imagem (Linux, outro build do 5.4.0) a
    leitura difere de propósito medido: 0/6 idênticas, similaridade mínima 0,992 — medição do build, não
    portão, com a decisão "a imagem é a referência" na ADR-008. Antes os dois testes abaixo FALHAVAM na
    imagem (minor da revisão final da F0); agora lá o de reprodução pula dizendo por quê, e o da CLI
    continua provando que ela grava o JSON e nunca falha por diferença.
    """
    sistema = str(manifest["plataforma"]["sistema"]).split("-", 1)[0]
    return platform.system() == sistema and medir.versao_tesseract() == str(manifest["tesseract_host"])


# ------------------------------------------------------------------ manifesto
def test_manifest_tem_seis_paginas_e_os_arquivos_existem(manifest):
    assert len(manifest["paginas"]) == 6
    assert manifest["dpi"] == 150
    for n in manifest["paginas"]:
        assert os.path.exists(os.path.join(AQUI, medir.nome_png(n))), n
        assert os.path.exists(os.path.join(AQUI, medir.nome_txt(n))), n


def test_manifest_sha_do_pdf_bate(manifest):
    pdf = os.path.join(RAIZ, manifest["pdf"])
    assert os.path.exists(pdf), pdf
    assert _sha256(pdf) == manifest["sha256_pdf"]


def test_manifest_sha_dos_png_e_txt_batem(manifest):
    # `arquivos` lista sha por nome: é o que denuncia um PNG regenerado sem
    # regenerar o texto (ou vice-versa).
    assert len(manifest["arquivos"]) == 12
    for nome, sha in manifest["arquivos"].items():
        assert _sha256(os.path.join(AQUI, nome)) == sha, nome


def test_manifest_configuracao_e_a_do_pipeline(manifest):
    # A baseline só é comparável com produção se usar o MESMO perfil que
    # `ocr.ler_documento` usa em texto corrido (RN-20).
    cfg = manifest["configuracao_ocr"]
    perfil = medir.ocr.PERFIL_TEXTO
    assert (cfg["lang"], cfg["psm"], cfg["oem"]) == (perfil["lang"], perfil["psm"], perfil["oem"])
    assert manifest["dpi"] == perfil["dpi"]
    assert manifest["tessdata_sha256"] == medir.tessdata_sha256()


def test_png_e_a_rasterizacao_do_pdf_a_150dpi(manifest):
    # Prova que o PNG versionado é regenerável: mesma página, mesmo dpi,
    # mesmos pixels. Sem isto o PNG seria um binário sem procedência.
    fitz = pytest.importorskip("fitz")
    from PIL import Image
    pdf = os.path.join(RAIZ, manifest["pdf"])
    doc = fitz.open(pdf)
    try:
        for i, n in enumerate(manifest["paginas"]):
            esperado = medir.ocr._renderizar(doc, i, manifest["dpi"])
            png = Image.open(os.path.join(AQUI, medir.nome_png(n))).convert("RGB")
            assert png.size == esperado.size
            assert png.tobytes() == esperado.tobytes(), "página %d" % n
    finally:
        doc.close()


# ------------------------------------------------------------------ medição
def test_medir_contra_o_proprio_host_reproduz(manifest, tesseract, mesmo_host):
    if not mesmo_host:
        pytest.skip("não é o host que gerou a baseline (%s, Tesseract %s): a comparação daqui com ele é "
                    "medição, não reprodução (ADR-008)" % (manifest["plataforma"]["sistema"], manifest["tesseract_host"]))
    resultado = medir.medir(tesseract)
    assert resultado["identicas"] == 6, resultado
    assert resultado["similaridade_min"] == 1.0, resultado
    assert [p["pagina"] for p in resultado["paginas"]] == manifest["paginas"]
    for p in resultado["paginas"]:
        assert p["identica"] is True
        assert p["chars_host"] == p["chars_aqui"] > 0


def test_cli_escreve_json_e_nunca_falha_por_diferenca(tmp_path, tesseract, mesmo_host):
    saida = tmp_path / "docs" / "ocr-equivalencia-<sha>.json"
    proc = subprocess.run(
        [sys.executable, os.path.join(AQUI, "medir.py"), "--saida", str(saida),
         "--tesseract", tesseract],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    gerados = list((tmp_path / "docs").glob("ocr-equivalencia-*.json"))
    assert len(gerados) == 1, gerados
    # o <sha> do nome é o do binário usado, nunca o literal
    assert "<sha>" not in gerados[0].name
    with open(gerados[0], encoding="utf-8") as f:
        dados = json.load(f)
    for chave in ("tesseract", "tessdata_sha256", "paginas", "identicas",
                  "similaridade_min", "plataforma"):
        assert chave in dados, chave
    assert 0 <= dados["identicas"] <= 6 and 0 < dados["similaridade_min"] <= 1.0
    if mesmo_host:                   # no host que gerou a baseline, a medição é reprodução: 6/6
        assert dados["identicas"] == 6
        assert "6/6" in proc.stdout
