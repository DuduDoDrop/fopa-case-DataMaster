# -*- coding: utf-8 -*-
"""
Os 5 ajustes obrigatórios da v3 no pacote `fopa` e no `28_baixar_licitacao.py`
(Plano FOPA v3, seção 6). Cada teste exercita o comportamento real — nada aqui
é mock do que está sendo testado — e a suíte roda sem chave de API e sem rede.

Os defaults novos têm que preservar o comportamento antigo: `40_fumaca.py`
chama `verificar()` e `escrever()` sem kwargs novos e precisa continuar verde.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import re
import sys
import zipfile

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
SCRIPTS = os.path.join(RAIZ, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from fopa import pagina, pncp, verificador                          # noqa: E402
from fopa import recuperacao as rec                                 # noqa: E402
from fopa.extrator import Extracao, Resposta                        # noqa: E402
from fopa.modelos import Uso                                        # noqa: E402
from fopa.questionario import NAO_LOCALIZADO                        # noqa: E402


# ------------------------------------------------------------ fixtures sintéticas
TEXTO = (
    "EDITAL DE CONCORRENCIA 01/2026\n"
    "O valor minimo de arrematacao e de R$ 1.250.000,00 (um milhao duzentos e\n"
    "cinquenta mil reais), conforme previsto no item 5.2 deste instrumento.\n"
)
TRECHO = "O valor minimo de arrematacao e de R$ 1.250.000,00"
ARQUIVO = "01 - Edital - EDITAL.pdf"


def montar(trecho: str = TRECHO, citado: str = ARQUIVO, q3: str | None = None,
           licitacao: str = "fixture") -> Extracao:
    """Uma extração mínima no molde do `40_fumaca.montar()`.

    `citado` é o nome que o modelo escreveu; a página congelada fica sempre em
    `ARQUIVO`. É a diferença entre os dois que o `arquivo_canonico` resolve.
    """
    pg = rec.Pagina(arquivo=ARQUIVO, numero=1, texto=TEXTO)
    respostas = [Resposta(id="Q5", pergunta="Qual o valor mínimo?",
                          resposta="R$ 1.250.000,00", arquivo=citado,
                          pagina=1, trecho_literal=trecho)]
    if q3 is not None:
        respostas.append(Resposta(id="Q3", pergunta="Qual a modalidade?",
                                  resposta=q3, arquivo=ARQUIVO, pagina=1,
                                  trecho_literal=q3))
    return Extracao(licitacao=licitacao, respostas=respostas, paginas=[pg],
                    arquivos=[ARQUIVO])


# ------------------------------------------------------------ (1) modalidade explícita
def test_modalidade_explicita_entra_quando_q3_e_pasta_nao_dizem_nada():
    ext = montar(q3=NAO_LOCALIZADO)
    assert verificador.modalidade_da(ext) == ""
    assert verificador.modalidade_da(ext, "Dispensa de Licitação") == "dispensa"
    # `None` explícito é o mesmo que não informar
    assert verificador.modalidade_da(ext, None) == ""


def test_q3_vence_a_modalidade_explicita():
    ext = montar(q3="Inexigibilidade de licitação")
    assert verificador.modalidade_da(ext, "Dispensa") == "inexigibilidade"


def test_explicita_vence_o_nome_da_pasta():
    # a pasta diz "Dispensa", o portal diz "Credenciamento": o portal entra
    # no lugar da pasta, nunca na frente da Q3
    ext = montar(q3=NAO_LOCALIZADO, licitacao="Dispensa - Cidade-UF")
    assert verificador.modalidade_da(ext) == "dispensa"
    assert verificador.modalidade_da(ext, "Credenciamento") == "credenciamento"


def test_verificar_encadeia_a_modalidade_ate_os_nao_localizados():
    # Q1 fica em branco; em dispensa isso NÃO é lacuna (RN-15)
    ext = montar(q3=NAO_LOCALIZADO)
    ext.respostas.append(Resposta(id="Q1", pergunta="Data da sessão?",
                                  resposta=NAO_LOCALIZADO))
    rel = verificador.verificar(ext, modalidade="Dispensa de Licitação")
    q1 = ext.por_id("Q1")
    assert any(a.startswith("não se aplica a esta modalidade") for a in q1.alertas)
    assert any("modalidade dispensa" in g for g in rel.alertas_globais)

    # sem a explícita, o mesmo branco é lacuna — o comportamento antigo
    ext2 = montar(q3=NAO_LOCALIZADO)
    ext2.respostas.append(Resposta(id="Q1", pergunta="Data da sessão?",
                                   resposta=NAO_LOCALIZADO))
    verificador.verificar(ext2)
    assert not any(a.startswith("não se aplica") for a in ext2.por_id("Q1").alertas)


# ------------------------------------------------------------ (2) arquivo_canonico
def test_arquivo_canonico_resolvido_pelo_verificador():
    ext = montar(citado="EDITAL.pdf")             # sufixo, sem o prefixo de ordenação
    verificador.verificar(ext)
    r = ext.por_id("Q5")
    assert r.veredito == verificador.APROVADO
    assert r.arquivo == "EDITAL.pdf"              # o que o modelo citou fica intacto
    assert r.arquivo_canonico == ARQUIVO
    assert r.para_dict()["arquivo_canonico"] == ARQUIVO


def test_arquivo_canonico_none_quando_nao_localizado():
    ext = montar()
    ext.respostas.append(Resposta(id="Q1", pergunta="Data da sessão?",
                                  resposta=NAO_LOCALIZADO))
    verificador.verificar(ext)
    assert ext.por_id("Q1").arquivo_canonico is None
    assert ext.por_id("Q1").para_dict()["arquivo_canonico"] is None
    # citação de arquivo que não existe no conjunto também não resolve
    ext2 = montar(citado="anexo-inexistente.pdf")
    verificador.verificar(ext2)
    assert ext2.por_id("Q5").arquivo_canonico is None


# ------------------------------------------------------------ (3) _link_pdf e escrever
def test_link_pdf_sem_nada_e_o_comportamento_antigo():
    assert pagina._link_pdf("a b#1.pdf", 3) == "a%20b%231.pdf#page=3"
    assert pagina._link_pdf("a b.pdf", None) == "a%20b.pdf"
    assert pagina._link_pdf(None, 3) == ""


def test_link_pdf_com_base_pdf_url_faz_quote_completo():
    assert (pagina._link_pdf("01 - Edital 50%.pdf", 2, base_pdf_url="https://s3/x/")
            == "https://s3/x/01%20-%20Edital%2050%25.pdf#page=2")


def test_link_pdf_com_url_por_arquivo_vence_a_base():
    mapa = {"01 - Edital.pdf": "https://cdn/assinada?sig=abc"}
    assert (pagina._link_pdf("01 - Edital.pdf", 4, base_pdf_url="https://s3/x/",
                             url_por_arquivo=mapa)
            == "https://cdn/assinada?sig=abc#page=4")
    # arquivo fora do mapa cai na base
    assert (pagina._link_pdf("02 - Anexo.pdf", None, base_pdf_url="https://s3/x/",
                             url_por_arquivo=mapa)
            == "https://s3/x/02%20-%20Anexo.pdf")


def _html(ext: Extracao, tmp_path, **kw) -> str:
    rel = verificador.verificar(ext)
    destino = pagina.escrever(ext, rel, str(tmp_path / "RELATORIO.html"), **kw)
    return io.open(destino, encoding="utf-8").read()


def test_escrever_usa_link_voltar_e_default_antigo(tmp_path):
    ext = montar()
    html = _html(ext, tmp_path, link_voltar="/licitacoes/xyz")
    assert html.count('href="/licitacoes/xyz"') == 2
    assert "../index.html" not in html

    html = _html(montar(), tmp_path)
    assert html.count('href="../index.html"') == 2


def test_escrever_linka_pelo_arquivo_canonico(tmp_path):
    ext = montar(citado="EDITAL.pdf")
    html = _html(ext, tmp_path, base_pdf_url="https://s3/x/")
    assert 'href="https://s3/x/01%20-%20Edital%20-%20EDITAL.pdf#page=1"' in html
    assert 'href="EDITAL.pdf' not in html


def test_escrever_preco_nao_configurado(tmp_path):
    ext = montar()
    ext.uso = Uso(entrada=1000, saida=100, chamadas=1, modelo="modelo-sem-tabela")
    assert ext.uso.preco_conhecido is False
    html = _html(ext, tmp_path)
    assert "preço não configurado" in html
    assert "R$ 0,00" not in html

    ext = montar()
    ext.uso = Uso(entrada=1000, saida=100, chamadas=1, modelo="claude-opus-5")
    html = _html(ext, tmp_path)
    assert "preço não configurado" not in html
    assert "custo da extração" in html


def test_escrever_paginas_nao_congeladas(tmp_path):
    ext = montar()
    ext.paginas = []
    html = _html(ext, tmp_path)
    assert "páginas não congeladas" in html
    assert "0 páginas" not in html

    html = _html(montar(), tmp_path)
    assert "1 páginas" in html




@pytest.mark.parametrize("provedor,trecho", [
    ("simulado", "respostas geradas pelo simulador, sem modelo nenhum"),
    ("gravado", "replay de chamadas gravadas"),
])
def test_escrever_ensaio_diz_o_que_e(tmp_path, provedor, trecho):
    # O W23 da v3 grava o modelo CONFIGURADO também no simulado: o RELATORIO do
    # ENSAIO publicado (verificação 228) dizia "modelo claude-opus-5" e "R$ 0.00
    # custo da extração" — uma extração real de graça, para quem lê. Execução de
    # ensaio se identifica no topo e no rodapé.
    ext = montar()
    ext.provedor = provedor
    ext.uso = Uso(entrada=1000, saida=100, chamadas=3, modelo="claude-opus-5")
    html = _html(ext, tmp_path)
    assert '<p class="tagensaio">' in html and trecho in html
    assert "provedor <code>%s</code>" % provedor in html
    assert "claude-opus-5 (provedor %s)" % provedor in html, "o rodapé também diz"

    for real in ("claude", ""):
        ext = montar()
        ext.provedor = real
        assert "tagensaio" not in _html(ext, tmp_path).split("</style>", 1)[1]


def test_escrever_custo_em_reais_com_virgula(tmp_path):
    ext = montar()
    ext.uso = Uso(entrada=1000, saida=100, chamadas=1, modelo="claude-opus-5")
    html = _html(ext, tmp_path)
    assert re.search(r"<b>R\$ \d+,\d{2}</b><span>custo da extração", html), "R$ 0.00 é formato americano"


def test_escrever_questionario_empilha_no_celular(tmp_path):
    # A 390px a tabela de 4 colunas passava da tela (400px em Capão do Cipó,
    # 641px em Santa Efigênia): o #, com 15ch de mínimo, e o selo do veredito
    # não encolhem. No celular cada linha vira um cartão — código e pergunta,
    # resposta, e origem ao lado do veredito — e a barra de status vai para a
    # linha inteira.
    html = _html(montar(), tmp_path)
    assert '<table class="q"><thead>' in html
    celular = html.split("@media(max-width:640px){", 1)[1].split("@media print", 1)[0]
    assert "table.q thead{display:none}" in celular
    assert "table.q tr{display:grid" in celular
    assert "tr.st-ok{box-shadow:inset 3px 0 0 var(--teal)}" in celular


# ------------------------------------------------------------ (5) avaliar_baixado
def _carregar_28():
    caminho = os.path.join(SCRIPTS, "28_baixar_licitacao.py")
    spec = importlib.util.spec_from_file_location("baixar_licitacao_28", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def m28():
    return _carregar_28()


DOC = {"sequencialDocumento": 1, "tipoDocumentoNome": "Edital",
       "titulo": "Edital", "url": "https://pncp.gov.br/x"}


def _pdf_bytes(texto: str = "Edital sintetico") -> bytes:
    import pymupdf
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), texto)
    return d.tobytes()


def _gravar(caminho, dados: bytes) -> pncp.ArquivoBaixado:
    with io.open(caminho, "wb") as f:
        f.write(dados)
    return pncp.ArquivoBaixado(seq=1, tipo="Edital", titulo="Edital",
                               caminho=str(caminho), bytes=len(dados),
                               sha256=hashlib.sha256(dados).hexdigest(),
                               baixado_em="2026-09-24T00:00:00", origem=DOC["url"])


def test_avaliar_pdf_valido(m28, tmp_path):
    destino = tmp_path / "01 - Edital - Edital.pdf"
    ab = _gravar(destino, _pdf_bytes())
    assert m28.avaliar_baixado(str(destino), ab, DOC, 0) == (None, [])
    assert destino.is_file()


def test_avaliar_zip_disfarcado_com_dois_pdfs(m28, tmp_path):
    # DEFLATED de propósito: com ZIP_STORED os bytes do PDF ficam crus dentro
    # do container e o MuPDF, que é tolerante, "repara" um documento de 1
    # página a partir deles — e o ZIP passaria como PDF válido. Os ZIPs do
    # PNCP vêm comprimidos (Jacarezinho/PR abriu com 0 páginas), e é esse o
    # caso que o desempacotamento existe para pegar.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("edital.pdf", _pdf_bytes("edital"))
        z.writestr("anexo/tr.pdf", _pdf_bytes("termo"))
    destino = tmp_path / "X.pdf"
    ab = _gravar(destino, buf.getvalue())
    recusa, extraidos = m28.avaliar_baixado(str(destino), ab, DOC, 0)
    assert recusa is None
    assert len(extraidos) == 2
    assert all(os.path.isfile(e.caminho) for e in extraidos)
    assert not destino.exists()                  # o container não é documento


def test_avaliar_zip_sem_pdf(m28, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("leia-me.txt", "nada aqui")
    destino = tmp_path / "X.pdf"
    ab = _gravar(destino, buf.getvalue())
    assert m28.avaliar_baixado(str(destino), ab, DOC, 0) == ("ZIP sem nenhum PDF dentro", [])


def test_avaliar_rtf_disfarcado(m28, tmp_path):
    destino = tmp_path / "Edital.pdf"
    ab = _gravar(destino, b"{\\rtf1\\ansi Edital em RTF}")
    recusa, extraidos = m28.avaliar_baixado(str(destino), ab, DOC, 0)
    assert recusa and "RTF" in recusa
    assert extraidos == []


def test_avaliar_teto_por_arquivo(m28, tmp_path, monkeypatch):
    monkeypatch.setattr(m28, "MAX_BYTES", 10)
    destino = tmp_path / "grande.pdf"
    ab = _gravar(destino, _pdf_bytes())
    recusa, extraidos = m28.avaliar_baixado(str(destino), ab, DOC, 0)
    assert recusa and "excede o teto" in recusa
    assert extraidos == []


def test_avaliar_teto_da_licitacao(m28, tmp_path, monkeypatch):
    monkeypatch.setattr(m28, "MAX_BYTES_LICITACAO", 10)
    destino = tmp_path / "ok.pdf"
    ab = _gravar(destino, _pdf_bytes())
    recusa, _ = m28.avaliar_baixado(str(destino), ab, DOC, total_bytes=5)
    assert recusa and "passaria de" in recusa
