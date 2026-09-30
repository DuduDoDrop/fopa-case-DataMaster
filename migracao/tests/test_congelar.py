# -*- coding: utf-8 -*-
"""
Testes do snapshot do acervo (`migracao/congelar.py`).

Arvore sintetica em `tmp_path`: 3 pastas em amostras/, 1 PDF falso, 1 JSON
invalido e 1 arquivo recem-modificado. Nada aqui toca o acervo real -- o
teste de verdade contra amostras/ e saidas/ e a execucao manual do CLI.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

import congelar  # noqa: E402

PDF_FALSO = b"%PDF-1.4\n%fake\n1 0 obj<<>>endobj\n%%EOF\n"


def _escreve(p: Path, conteudo, envelhece: bool = True):
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(conteudo, (dict, list)):
        conteudo = json.dumps(conteudo, ensure_ascii=False, indent=1)
    if isinstance(conteudo, str):
        p.write_text(conteudo, encoding="utf-8")
    else:
        p.write_bytes(conteudo)
    if envelhece:
        # Tudo que acabou de nascer em tmp_path tem mtime < 60 s; sem
        # envelhecer, o filtro de "ainda sendo escrito" pularia a arvore inteira.
        velho = time.time() - 3600
        os.utime(p, (velho, velho))


@pytest.fixture
def raiz(tmp_path: Path) -> Path:
    am = tmp_path / "amostras"
    sa = tmp_path / "saidas"

    # pasta A: completa (inventario, metadados, relatorio, PDF listado)
    _escreve(am / "A" / "_inventario.json", {
        "controle": "1-1", "arquivos": [{"arquivo": "edital.pdf", "sha256": ""}],
    })
    _escreve(am / "A" / "_metadados.md", "# A\n")
    _escreve(am / "A" / "RELATORIO.html", "<html>A</html>")
    _escreve(am / "A" / "_itens_api.json", [{"item": 1}])
    _escreve(am / "A" / "edital.pdf", PDF_FALSO)
    _escreve(am / "A" / "texto.txt", "nao deve ser copiado")

    # pasta B: inventario com JSON invalido (deve ser pulado e listado)
    _escreve(am / "B" / "_inventario.json", "{ isto nao e json")
    _escreve(am / "B" / "_metadados.md", "# B\n")

    # pasta C: sem inventario, com PDF fora de inventario e gabarito
    _escreve(am / "C" / "solto.pdf", PDF_FALSO + b"C")
    _escreve(am / "C" / "_gabarito.json", {"Q1": "x"})

    # arquivo na raiz de amostras/ nao e "pasta": fica de fora
    _escreve(am / "_resumo.json", {"n": 1})

    # saidas/: auditorias com provedor em uso.provedor / uso.modelo
    _escreve(sa / "A" / "auditoria.json", {
        "uso": {"provedor": "claude-code", "modelo": "claude-opus-5-5"}, "respostas": [],
    })
    _escreve(sa / "A" / "RELATORIO.html", "<html>rel</html>")
    _escreve(sa / "B" / "auditoria.json", {
        "uso": {"provedor": "", "modelo": "claude-opus-5"}, "respostas": [],
    })
    _escreve(sa / "_agente" / "A" / "paginas.json", {"paginas": []})
    _escreve(sa / "_agente" / "A" / "finalizado.json", {"em": "2026-09-24"})
    _escreve(sa / "_agente" / "A" / "respostas.json", {"Q1": "sim"})
    _escreve(sa / "_livro.json", {"x": 1})

    # arquivo recem-modificado: mtime agora (< 60 s) -> pulado
    _escreve(sa / "_agente" / "A" / "contexto_01.txt", "ainda escrevendo", envelhece=False)
    return tmp_path


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_copia_o_que_deve_e_so_isso(raiz: Path):
    res = congelar.congelar(raiz, destino="acervo", agora=datetime(2026, 9, 24, 10, 30))
    snap = Path(res["snapshot"])
    assert snap == raiz / "acervo" / "2026-09-24_1030"

    # amostras: so os 5 nomes permitidos
    assert (snap / "amostras" / "A" / "_inventario.json").is_file()
    assert (snap / "amostras" / "A" / "_metadados.md").is_file()
    assert (snap / "amostras" / "A" / "RELATORIO.html").is_file()
    assert (snap / "amostras" / "A" / "_itens_api.json").is_file()
    assert (snap / "amostras" / "C" / "_gabarito.json").is_file()
    assert not (snap / "amostras" / "A" / "edital.pdf").exists()
    assert not (snap / "amostras" / "A" / "texto.txt").exists()
    assert not (snap / "amostras" / "C" / "solto.pdf").exists()
    assert not (snap / "amostras" / "_resumo.json").exists()

    # saidas: inteiro, inclusive _agente e arquivos soltos
    assert (snap / "saidas" / "A" / "auditoria.json").is_file()
    assert (snap / "saidas" / "A" / "RELATORIO.html").is_file()
    assert (snap / "saidas" / "_agente" / "A" / "paginas.json").is_file()
    assert (snap / "saidas" / "_agente" / "A" / "respostas.json").is_file()
    assert (snap / "saidas" / "_livro.json").is_file()

    assert (snap / "manifesto.json").is_file()
    assert (snap / "relatorio.md").is_file()


def test_manifesto_tem_sha_certo_e_pdfs_sem_copia(raiz: Path):
    res = congelar.congelar(raiz, destino="acervo", agora=datetime(2026, 9, 24, 10, 30))
    snap = Path(res["snapshot"])
    man = json.loads((snap / "manifesto.json").read_text(encoding="utf-8"))

    copias = {c["caminho"]: c for c in man["copias"]}
    inv = copias["amostras/A/_inventario.json"]
    assert inv["sha256"] == _sha(raiz / "amostras" / "A" / "_inventario.json")
    assert inv["sha256"] == _sha(snap / "amostras" / "A" / "_inventario.json")
    assert inv["bytes"] == (raiz / "amostras" / "A" / "_inventario.json").stat().st_size

    pdfs = {p["caminho"]: p for p in man["pdfs"]}
    assert set(pdfs) == {"amostras/A/edital.pdf", "amostras/C/solto.pdf"}
    assert pdfs["amostras/A/edital.pdf"]["sha256"] == hashlib.sha256(PDF_FALSO).hexdigest()
    assert pdfs["amostras/A/edital.pdf"]["bytes"] == len(PDF_FALSO)
    assert pdfs["amostras/C/solto.pdf"]["sha256"] == hashlib.sha256(PDF_FALSO + b"C").hexdigest()
    for p in pdfs.values():
        assert p["mtime"]

    c = man["contagens"]
    assert c["pastas_amostras"] == 3
    assert c["inventarios"] == 1            # o de B e invalido, nao conta
    assert c["pdfs"] == 2
    assert c["pdfs_bytes"] == len(PDF_FALSO) * 2 + 1
    assert c["auditorias_por_provedor"] == {"claude-code/claude-opus-5-5": 1, "claude-opus-5": 1}
    assert c["finalizados"] == 1
    assert c["paginas"] == 1
    assert c["pastas_sem_inventario"] == 2  # B (invalido) e C
    assert c["pastas_pdf_fora_inventario"] == 1  # C


def test_pulados_sao_listados(raiz: Path):
    res = congelar.congelar(raiz, destino="acervo", agora=datetime(2026, 9, 24, 10, 30))
    snap = Path(res["snapshot"])
    man = json.loads((snap / "manifesto.json").read_text(encoding="utf-8"))
    pulados = {p["caminho"]: p["motivo"] for p in man["pulados"]}

    assert "amostras/B/_inventario.json" in pulados
    assert "json" in pulados["amostras/B/_inventario.json"].lower()
    assert "saidas/_agente/A/contexto_01.txt" in pulados
    assert "60" in pulados["saidas/_agente/A/contexto_01.txt"]

    assert not (snap / "amostras" / "B" / "_inventario.json").exists()
    assert not (snap / "saidas" / "_agente" / "A" / "contexto_01.txt").exists()

    rel = (snap / "relatorio.md").read_text(encoding="utf-8")
    assert "amostras/B/_inventario.json" in rel
    assert "saidas/_agente/A/contexto_01.txt" in rel
    assert "claude-code/claude-opus-5-5" in rel


def test_idempotente_dois_snapshots_iguais(raiz: Path):
    r1 = congelar.congelar(raiz, destino="acervo", agora=datetime(2026, 9, 24, 10, 30))
    r2 = congelar.congelar(raiz, destino="acervo", agora=datetime(2026, 9, 24, 10, 31))
    assert Path(r1["snapshot"]) != Path(r2["snapshot"])
    m1 = json.loads((Path(r1["snapshot"]) / "manifesto.json").read_text(encoding="utf-8"))
    m2 = json.loads((Path(r2["snapshot"]) / "manifesto.json").read_text(encoding="utf-8"))
    # so o bloco `execucao` (carimbo, caminho) pode diferir; o conteudo nao
    m1.pop("execucao")
    m2.pop("execucao")
    assert m1 == m2
    # e o snapshot anterior nao entra no seguinte
    assert not any(c["caminho"].startswith("acervo/") for c in m2["copias"])


def test_seco_nao_escreve_nada(raiz: Path):
    res = congelar.congelar(raiz, destino="acervo", seco=True, agora=datetime(2026, 9, 24, 10, 30))
    assert not (raiz / "acervo").exists()
    assert res["contagens"]["pdfs"] == 2
    assert res["contagens"]["inventarios"] == 1


def test_cli_seco(raiz: Path):
    cmd = [sys.executable, str(AQUI.parent / "congelar.py"), "--raiz", str(raiz), "--seco"]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    assert "pastas em amostras" in out.stdout
    assert not (raiz / "acervo").exists()


def test_caminho_longo_no_destino(raiz: Path):
    # O acervo real tem `saidas/<250 chars>`; somar `acervo/AAAA-MM-DD_HHMM/`
    # passa dos 260 do Windows. A origem cabe no limite, o destino nao.
    pasta = "P" * max(1, 250 - len(str(raiz / "saidas")) - 1 - 12)
    origem = raiz / "saidas" / pasta / "auditoria.json"
    assert len(str(origem)) <= 259
    _escreve(origem, {"uso": {"provedor": "x", "modelo": "y"}})
    res = congelar.congelar(raiz, destino="acervo", agora=datetime(2026, 9, 24, 10, 30))
    destino = Path(res["snapshot"]) / "saidas" / pasta / "auditoria.json"
    assert len(str(destino)) > 260
    assert os.path.isfile(congelar._longo(destino))
    man = json.loads((Path(res["snapshot"]) / "manifesto.json").read_text(encoding="utf-8"))
    assert "saidas/%s/auditoria.json" % pasta in {c["caminho"] for c in man["copias"]}


# ------------------------------------------------------------------ minors da revisão final da F0
def test_leituras_de_json_fecham_o_arquivo(tmp_path):
    # json.load(io.open(...)) sem `with`: o arquivo ficava aberto até o coletor passar — no Windows, handle
    # aberto trava rename/delete no meio do congelamento. Com os avisos ligados, ler um JSON válido, um
    # inválido e uma auditoria não pode deixar "unclosed file".
    import gc
    import warnings
    bom = tmp_path / "a.json"
    bom.write_text('{"uso": {"provedor": "", "modelo": "claude-opus-5"}}', encoding="utf-8")
    ruim = tmp_path / "b.json"
    ruim.write_text("{", encoding="utf-8")
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always", ResourceWarning)
        assert congelar._motivo_para_pular(bom, bom.stat(), time.time() + 3600, 60) is None
        assert congelar._motivo_para_pular(ruim, ruim.stat(), time.time() + 3600, 60).startswith("JSON invalido")
        assert congelar._provedor(bom) == "claude-opus-5"
        gc.collect()
    vazados = [str(a.message) for a in avisos if issubclass(a.category, ResourceWarning)]
    assert not vazados, vazados


def test_mtime_do_manifesto_tem_fuso_e_o_importador_o_mantem(tmp_path):
    # O manifesto gravava a hora local SEM fuso ("2026-09-24T03:12:00"): quem o lesse fora do importador
    # não saberia de onde. Agora vai com o fuso da máquina; o importador (_ts) aceita os dois formatos —
    # com fuso não mexe, e o manifesto antigo, sem fuso, segue valendo como -03:00.
    import re
    f = tmp_path / "x.json"
    f.write_text("{}", encoding="utf-8")
    st = f.stat()
    s = congelar._mtime_iso(st)
    assert re.search(r"[+-]\d{2}:\d{2}$", s), s
    assert int(datetime.fromisoformat(s).timestamp()) == int(st.st_mtime)
    sys.path.insert(0, str(AQUI.parent.parent))
    from migracao import importar
    assert importar._ts(s, local_sem_fuso=True) == s
    assert importar._ts("2026-09-24T03:12:00", local_sem_fuso=True) == "2026-09-24T03:12:00-03:00"

