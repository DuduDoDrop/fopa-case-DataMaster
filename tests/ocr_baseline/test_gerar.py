# -*- coding: utf-8 -*-
"""
`gerar.py` regenera a baseline de OCR. O caso normal é rodar SEM `--origem`
(o PDF de 6 páginas já está versionado): antes, isso gravava `pdf_origem: null`
no manifest novo e a baseline perdia de qual edital e de quais páginas físicas
ela veio (minor da revisão final da F0). A procedência só vale para o MESMO
PDF: é o sha256 que decide.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import gerar  # noqa: E402


def test_sem_origem_preserva_a_procedencia_do_manifest_do_mesmo_pdf(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    pdf.write_bytes(b"%PDF-1.7 fixture")
    man = tmp_path / "manifest.json"
    origem = {"caminho": "amostras/x/01 - Edital.pdf", "sha256": "ab" * 32, "paginas_fisicas": [1, 2]}
    man.write_text(json.dumps({"sha256_pdf": hashlib.sha256(b"%PDF-1.7 fixture").hexdigest(),
                               "pdf_origem": origem}), encoding="utf-8")
    assert gerar.procedencia_anterior(str(pdf), str(man)) == origem

    pdf.write_bytes(b"%PDF-1.7 outro")          # outro PDF: a procedência antiga não vale para ele
    assert gerar.procedencia_anterior(str(pdf), str(man)) is None
    assert gerar.procedencia_anterior(str(pdf), str(tmp_path / "nao-existe.json")) is None


def test_o_manifest_versionado_tem_procedencia_e_ela_seria_preservada():
    with open(os.path.join(AQUI, "manifest.json"), encoding="utf-8") as f:
        m = json.load(f)
    assert m["pdf_origem"] and m["pdf_origem"]["paginas_fisicas"] == m["paginas"]
    fixture = os.path.join(AQUI, gerar.PDF_FIXTURE)
    assert gerar.procedencia_anterior(fixture, os.path.join(AQUI, "manifest.json")) == m["pdf_origem"]
