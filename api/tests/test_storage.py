# -*- coding: utf-8 -*-
"""
Testes do storage content-addressed (`api/storage.py`), backend `fs`.

As chaves são o contrato com o Postgres (`arquivos.storage_key`) e com o S3 de
depois: por isso a validação é testada tão de perto quanto o put/get.
"""
import hashlib
import os

import pytest

from api import config, storage

SHA_A = "a" * 64


@pytest.fixture
def st(tmp_path):
    return storage.Storage(str(tmp_path))


# ------------------------------------------------------------------ chaves
def test_chave_pdf_e_html_tem_o_formato_do_plano():
    assert storage.chave_pdf("12345678000199", 2026, 7, SHA_A) == \
        "pdf/12345678000199/2026/7/%s.pdf" % SHA_A
    assert storage.chave_html("pregao-eletronico-pirapo-pr", 42) == \
        "html/pregao-eletronico-pirapo-pr/42.html"


def test_chave_pdf_exige_cnpj_numerico_e_sha_de_64_hex():
    with pytest.raises(storage.ChaveInvalida):
        storage.chave_pdf("12.345.678/0001-99", 2026, 7, SHA_A)
    with pytest.raises(storage.ChaveInvalida):
        storage.chave_pdf("12345678000199", 2026, 7, "abc")
    with pytest.raises(storage.ChaveInvalida):
        storage.chave_pdf("12345678000199", 2026, 7, "A" * 64)   # hex minúsculo, sempre


@pytest.mark.parametrize("chave", [
    "pdf/a b.pdf",            # espaço
    "pdf/a%20b.pdf",          # percent-encoding
    "html/licitação/1.html",  # não-ASCII
    "../fora.pdf",            # sai da raiz
    "pdf/../../fora.pdf",
    "/pdf/abs.pdf",           # absoluta
    "pdf//duplo.pdf",         # segmento vazio
    "pdf\\win.pdf",           # separador do Windows não é separador de chave
    "",
    "C:/pdf/x.pdf",
    "html/abc./1.html",       # segmento terminado em ponto: o Windows o apaga e "abc." vira "abc"
    "pdf/x.pdf.",             # idem no nome do arquivo
])
def test_rejeita_chave_invalida(st, chave):
    with pytest.raises(storage.ChaveInvalida):
        storage.validar_chave(chave)
    with pytest.raises(storage.ChaveInvalida):
        st.put(chave, b"x")
    with pytest.raises(storage.ChaveInvalida):
        st.get(chave)
    with pytest.raises(storage.ChaveInvalida):
        st.existe(chave)
    with pytest.raises(storage.ChaveInvalida):
        st.caminho(chave)


def test_aceita_chaves_do_plano():
    for chave in ("pdf/12345678000199/2026/7/%s.pdf" % SHA_A,
                  "html/pregao-pirapo-pr/1.html",
                  "acervo/2026-09-24/manifesto.json"):
        assert storage.validar_chave(chave) == chave


# ------------------------------------------------------------------ fs
def test_put_get_e_sha256(st):
    dados = b"%PDF-1.4 conteudo de teste"
    chave = storage.chave_pdf("12345678000199", 2026, 1, hashlib.sha256(dados).hexdigest())
    assert not st.existe(chave)
    sha = st.put(chave, dados)
    assert sha == hashlib.sha256(dados).hexdigest()
    assert st.existe(chave)
    assert st.get(chave) == dados
    assert os.path.isfile(st.caminho(chave))


def test_caminho_fica_dentro_da_raiz(st, tmp_path):
    caminho = st.caminho("html/slug/1.html")
    assert os.path.commonpath([str(tmp_path), caminho]) == str(tmp_path)
    assert caminho.endswith(os.path.join("html", "slug", "1.html"))


def test_put_sobrescreve_atomicamente_e_nao_deixa_temporario(st):
    st.put("html/s/1.html", b"v1")
    st.put("html/s/1.html", b"v2")
    assert st.get("html/s/1.html") == b"v2"
    pasta = os.path.dirname(st.caminho("html/s/1.html"))
    assert os.listdir(pasta) == ["1.html"]


def test_get_de_chave_inexistente_e_erro_claro(st):
    with pytest.raises(storage.ObjetoInexistente):
        st.get("pdf/x/1/1/%s.pdf" % SHA_A)


def test_put_recusa_conteudo_que_nao_bate_com_o_sha_da_chave_pdf(st):
    # A chave é content-addressed: gravar bytes com outro sha sob ela seria
    # mentir para o banco (`arquivos.sha256`) sem ninguém perceber.
    chave = storage.chave_pdf("12345678000199", 2026, 1, SHA_A)
    with pytest.raises(storage.ConteudoDivergente):
        st.put(chave, b"nao e o conteudo de sha aaaa...")


def test_storage_cria_raiz_se_nao_existir(tmp_path):
    raiz = os.path.join(str(tmp_path), "dados", "novo")
    s = storage.Storage(raiz)
    s.put("html/a/1.html", b"x")
    assert os.path.isdir(raiz)


def test_s3_sem_configuracao_falha_alto_com_o_nome_da_variavel():
    # Construir nunca falha (o /health tem de responder dizendo o que falta);
    # usar sem S3_* é StorageIndisponivel com o NOME da variável. O backend s3
    # de verdade é testado em test_storage_s3.py.
    s3 = storage.StorageS3()
    assert "S3_" in (storage.StorageS3.__doc__ or "")
    for chamada in (lambda: s3.put("a/b", b"x"), lambda: s3.get("a/b"),
                    lambda: s3.existe("a/b"), lambda: s3.presign("a/b")):
        with pytest.raises(storage.StorageIndisponivel, match="S3_BUCKET"):
            chamada()
    with pytest.raises(NotImplementedError):     # S3 não tem caminho local
        s3.caminho("a/b")


def test_abrir_pelo_config(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BACKEND", "fs")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    s = storage.abrir(config.carregar())
    assert isinstance(s, storage.Storage) and not isinstance(s, storage.StorageS3)
    assert s.descrever() == {"backend": "fs", "raiz": str(tmp_path), "ok": True, "existe": True}
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    assert isinstance(storage.abrir(config.carregar()), storage.StorageS3)


def test_descrever_nao_cria_a_raiz_e_diz_se_o_put_vai_funcionar(tmp_path):
    # Minor adiado da revisão final da F0: o /health CRIAVA a raiz para poder dizer "gravável" — no host sem
    # STORAGE_ROOT, um GET deixava um C:\dados para trás. Agora ele não cria nada e responde a pergunta que
    # importa: o primeiro `put` vai conseguir? (a raiz, ou o ancestral mais próximo que existe, é pasta gravável)
    raiz = os.path.join(str(tmp_path), "volume", "ainda-nao-existe")
    assert storage.Storage(raiz).descrever() == {"backend": "fs", "raiz": raiz, "ok": True, "existe": False}
    assert not os.path.exists(os.path.join(str(tmp_path), "volume")), "o /health criou pasta"
    s = storage.Storage(raiz)
    s.put("html/x/1.html", b"<p>1</p>")          # o put cria o que faltar, como sempre
    assert s.descrever() == {"backend": "fs", "raiz": raiz, "ok": True, "existe": True}


def test_descrever_raiz_impossivel_nao_e_ok(tmp_path):
    arquivo = tmp_path / "sou-um-arquivo"
    arquivo.write_bytes(b"x")
    raiz = os.path.join(str(arquivo), "dados")    # o ancestral que existe é um ARQUIVO: nenhum put funcionaria
    assert storage.Storage(raiz).descrever() == {"backend": "fs", "raiz": raiz, "ok": False, "existe": False}
