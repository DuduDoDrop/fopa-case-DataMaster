# -*- coding: utf-8 -*-
"""
Regras puras da importação do acervo v2 (plano, seção 9) — sem banco, sem disco.

Cada teste nasce de um caso REAL do snapshot de 24/09/2026, reduzido ao
mínimo. O nome do caso está no teste para que a regra continue explicável
quando o caso não estiver mais à vista.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from migracao import regras  # noqa: E402

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _disco(**arquivos):
    """{nome: sha} -> o formato que o manifesto dá por pasta."""
    return {nome: {"sha256": sha, "bytes": 1000 + i}
            for i, (nome, sha) in enumerate(arquivos.items())}


# ------------------------------------------------------------- identidade
def test_partes_do_controle():
    assert regras.partes_controle("58987629000110-1-000123/2026") == ("58987629000110", 2026, 123)


def test_controle_invalido_levanta():
    with pytest.raises(ValueError):
        regras.partes_controle("Pregao - Eletronico - Castro-PR")


@pytest.mark.parametrize("bruto,esperado,tem_hora", [
    ("2026-09-16T08:30", "2026-09-16T08:30:00-03:00", True),
    ("2026-09-16T08:30:00", "2026-09-16T08:30:00-03:00", True),
    ("2026-10-08", "2026-10-08T00:00:00-03:00", False),
    ("", None, None),
    (None, None, None),
    ("prazo não informado", None, None),
])
def test_fim_prazo_no_fuso_de_brasilia(bruto, esperado, tem_hora):
    # O PNCP publica a hora local de Brasília sem fuso; sem horário de verão
    # desde 2019, -03:00 é fixo. Só data = sessão sem hora declarada.
    assert regras.fim_prazo(bruto) == (esperado, tem_hora)


# ------------------------------------------------------------- arquivos
def test_arquivo_do_inventario_casado_com_o_disco_por_nome():
    inv = {"arquivos": [{"seq": 1, "tipo": "Edital", "titulo": "edital", "arquivo": "01 - Edital.pdf",
                         "bytes": 999, "sha256": SHA_A, "pag": 18, "chars": 54998,
                         "requer_ocr": False, "origem": "https://pncp/x"}]}
    arqs = regras.arquivos_da_pasta(inv, _disco(**{"01 - Edital.pdf": SHA_A}))
    assert len(arqs) == 1
    a = arqs[0]
    assert (a.nome, a.status, a.sha256, a.seq, a.paginas) == ("01 - Edital.pdf", "ok", SHA_A, 1, 18)
    assert a.bytes == 1000 and a.bytes_aproximado is False   # o disco manda: byte exato
    assert a.tem_bytes


def test_kb_do_esquema_antigo_vira_byte_exato_quando_o_disco_confirma():
    inv = {"arquivos": [{"seq": 1, "arquivo": "01 - Edital.pdf", "kb": 6512, "sha256": SHA_A}]}
    a = regras.arquivos_da_pasta(inv, _disco(**{"01 - Edital.pdf": SHA_A}))[0]
    assert a.bytes == 1000 and a.bytes_aproximado is False


def test_legado_sem_nome_casa_pelo_prefixo_do_sha():
    # Rio Branco/AC: 24 entradas do primeiro coletor têm só `sha` de 16 hex e
    # nenhum nome; o nome certo é o do disco, que é o que o modelo citou.
    inv = {"arquivos": [{"seq": 1, "tipo": "Termo de Referencia", "sha": SHA_A[:16], "kb": 112,
                         "pag": 5, "ocr": "nao", "ativo": True}]}
    a = regras.arquivos_da_pasta(inv, _disco(**{"01 - Termo SEI 2.pdf": SHA_A}))[0]
    assert (a.nome, a.status, a.sha256) == ("01 - Termo SEI 2.pdf", "ok", SHA_A)
    assert a.requer_ocr is False and a.ativo_pncp is True


def test_mesmo_conteudo_com_outro_nome_e_alias():
    # Os 101 `*.PDF.pdf`: o mesmo PDF gravado duas vezes, com e sem a extensão dobrada.
    inv = {"arquivos": [{"seq": 1, "arquivo": "01 - Edital.pdf", "sha256": SHA_A}]}
    arqs = regras.arquivos_da_pasta(inv, _disco(**{"01 - Edital.pdf": SHA_A,
                                                   "01 - Edital.PDF.pdf": SHA_A}))
    por_nome = {a.nome: a for a in arqs}
    assert por_nome["01 - Edital.pdf"].status == "ok"
    assert por_nome["01 - Edital.PDF.pdf"].status == "alias_duplicado"
    assert por_nome["01 - Edital.PDF.pdf"].alias_de == "01 - Edital.pdf"


def test_pdf_no_disco_fora_do_inventario():
    inv = {"arquivos": [{"seq": 1, "arquivo": "01 - Edital.pdf", "sha256": SHA_A}]}
    arqs = regras.arquivos_da_pasta(inv, _disco(**{"01 - Edital.pdf": SHA_A, "intruso.pdf": SHA_B}))
    intruso = next(a for a in arqs if a.nome == "intruso.pdf")
    assert intruso.status == "fora_inventario" and intruso.tem_bytes


def test_pdf_fora_do_inventario_em_pasta_contaminada_e_procedencia_incerta():
    # Castro-PR: o monitor gravou na pasta os PDFs de OUTRA licitação.
    inv = {"arquivos": [{"seq": 1, "arquivo": "01 - Edital.pdf", "sha256": SHA_A}]}
    arqs = regras.arquivos_da_pasta(inv, _disco(**{"01 - Edital.pdf": SHA_A, "PE 133.pdf": SHA_B}),
                                    contaminada=True)
    assert next(a for a in arqs if a.nome == "PE 133.pdf").status == "procedencia_incerta"


def test_sha_do_inventario_diferente_do_disco_e_corrompido():
    inv = {"arquivos": [{"seq": 1, "arquivo": "01 - Edital.pdf", "sha256": SHA_A}]}
    a = regras.arquivos_da_pasta(inv, _disco(**{"01 - Edital.pdf": SHA_B}))[0]
    assert a.status == "corrompido" and "difere" in a.motivo


def test_listado_no_inventario_e_ausente_do_disco():
    inv = {"arquivos": [{"seq": 1, "arquivo": "01 - Edital.pdf", "sha256": SHA_A, "kb": 3}]}
    a = regras.arquivos_da_pasta(inv, {})[0]
    assert a.status == "ausente_no_disco" and not a.tem_bytes
    assert a.bytes == 3 * 1024 and a.bytes_aproximado is True


@pytest.mark.parametrize("motivo,status", [
    ("não abre como PDF — o arquivo é RTF", "formato_nao_suportado"),
    ("ZIP sem nenhum PDF dentro", "formato_nao_suportado"),
    ("130.2 MB excede o teto de 120 MB", "recusado_politica"),
    ("a licitação passaria de 400 MB no total", "recusado_politica"),
    ("PDF corrompido ou ilegível: xref", "corrompido"),
])
def test_recusas_viram_status_pelo_motivo(motivo, status):
    inv = {"arquivos": [], "recusados": [{"seq": 2, "arquivo": "02 - Anexo.pdf", "motivo": motivo,
                                          "bytes": 10, "origem": "u"}]}
    a = regras.arquivos_da_pasta(inv, {})[0]
    assert (a.nome, a.status, a.motivo) == ("02 - Anexo.pdf", status, motivo)
    assert not a.tem_bytes


def test_falha_de_download_e_falha_de_rede():
    inv = {"arquivos": [], "falhas_download": [{"arquivo": "03 - X.pdf", "seq": 3,
                                                "erro": "URLError: timed out"}]}
    a = regras.arquivos_da_pasta(inv, {})[0]
    assert (a.status, a.motivo) == ("falha_rede", "URLError: timed out")


def test_pdf_tirado_de_zip_aponta_para_o_container():
    inv = {"arquivos": [{"seq": 20, "arquivo": "20 - Ata -- Ata.pdf", "sha256": SHA_A,
                         "de_zip": "20 - Ata.zip.pdf"}]}
    arqs = regras.arquivos_da_pasta(inv, _disco(**{"20 - Ata -- Ata.pdf": SHA_A}))
    por_nome = {a.nome: a for a in arqs}
    assert por_nome["20 - Ata.zip.pdf"].status == "zip_container"
    assert por_nome["20 - Ata -- Ata.pdf"].pai == "20 - Ata.zip.pdf"


def test_nota_de_zip_vazio_no_inventario():
    inv = {"arquivos": [{"seq": 3, "arquivo": "03 - Edital.zip.pdf", "sha256": SHA_A,
                         "nota": "ZIP sem nenhum PDF dentro"}]}
    a = regras.arquivos_da_pasta(inv, _disco(**{"03 - Edital.zip.pdf": SHA_A}))[0]
    assert a.status == "formato_nao_suportado"


# ------------------------------------------------------------- canônica
def _cand(pasta, **kw):
    base = dict(pasta=pasta, tem_execucao=True, finalizado_em="2026-09-23T23:57:55-0300",
                reaproveitado_de=None, leitura_limpa=True)
    base.update(kw)
    return base


def test_canonica_unica_candidata():
    assert regras.escolher_canonica([_cand("A")]) == ("A", "única pasta com execução")


def test_canonica_prefere_leitura_sem_pdf_de_fora():
    # Castro-PR: a pasta sem sufixo leu 9 PDFs de outra licitação.
    pasta, motivo = regras.escolher_canonica([
        _cand("Castro-PR", leitura_limpa=False, finalizado_em="2026-09-23T23:57:59-0300"),
        _cand("Castro-PR - 557-2026", leitura_limpa=True, finalizado_em="2026-09-23T23:58:00-0300")])
    assert pasta == "Castro-PR - 557-2026" and "fora do inventário" in motivo


def test_canonica_prefere_a_mais_recente():
    pasta, _ = regras.escolher_canonica([
        _cand("A", finalizado_em="2026-09-23T23:00:00-0300"),
        _cand("B", finalizado_em="2026-09-23T23:30:00-0300")])
    assert pasta == "B"


def test_canonica_original_vence_reaproveitada():
    # Capep: as duas finalizadas no mesmo segundo; a "-Saude" reaproveitou a outra.
    pasta, motivo = regras.escolher_canonica([
        _cand("Capep-Saude", reaproveitado_de="Capep"), _cand("Capep")])
    assert pasta == "Capep" and "reaproveit" in motivo


def test_canonica_empate_sem_criterio_e_none():
    assert regras.escolher_canonica([_cand("A"), _cand("B")])[0] is None


def test_canonica_ignora_pasta_sem_execucao():
    # Rio Branco/AC: a pasta do TCE-AC só tem leitura; a execução é a outra.
    assert regras.escolher_canonica([_cand("Rio Branco", leitura_limpa=None),
                                     _cand("TCE-AC", tem_execucao=False)])[0] == "Rio Branco"


# ------------------------------------------------------------- leitura
def test_assinatura_do_conjunto_ignora_nome_de_arquivo():
    # Gêmeas: mesmo texto lido, nomes de arquivo diferentes (Caibi, Caibi - 724-2026).
    a = regras.assinatura_conjunto({"01 - Edital.pdf": "x1", "02 - TR.pdf": "x2"})
    b = regras.assinatura_conjunto({"EDITAL.pdf": "x2", "TR.pdf": "x1"})
    assert a == b and len(a) == 64
    assert regras.assinatura_conjunto({"a": "x1"}) != a


def test_leitura_limpa_quando_todos_os_bytes_estao_no_inventario():
    assert regras.leitura_limpa({"a.pdf": SHA_A}, {SHA_A, SHA_B}) is True
    assert regras.leitura_limpa({"a.pdf": SHA_A, "b.pdf": SHA_C}, {SHA_A}) is False


# ------------------------------------------------------------- respostas
@pytest.mark.parametrize("r,esperado", [
    ({"resposta": "Pregão eletrônico", "trecho_literal": "pregão", "alertas": []}, None),
    ({"resposta": "Não localizado", "trecho_literal": None,
      "alertas": ["não se aplica a esta modalidade — dispensa não tem sessão"]}, "nao_se_aplica"),
    ({"resposta": "Não localizado nos documentos", "trecho_literal": None, "alertas": []},
     "sem_evidencia"),
    ({"resposta": "R$ 1.000,00", "trecho_literal": "", "alertas": []}, "falta_evidencia"),
])
def test_ausencia_tem_tres_tipos(r, esperado):
    # Os mesmos três blocos do RELATORIO (pagina.py): não se aplica, sem
    # evidência (a ausência é a resposta) e evidência que falta (defeito).
    assert regras.ausencia(r) == esperado


def test_respostas_sha_estavel():
    rs = [{"id": "Q2", "resposta": "b"}, {"id": "Q1", "resposta": "a"}]
    assert regras.respostas_sha256(rs) == regras.respostas_sha256(list(reversed(rs)))
    assert regras.respostas_sha256(rs) == hashlib.sha256(
        regras.json_canonico(sorted(rs, key=lambda r: int(r["id"][1:])))).hexdigest()


# ------------------------------------------------------------- harness
def _aud(**resp):
    return {"respostas": [{"id": k, "resposta": v} for k, v in resp.items()]}


def test_harness_casa_repeticao_identica():
    h = {"execucoes": [
        {"rotulo": "opus-5 · high", "repeticao": 1, "respostas": [{"id": "Q1", "resposta": "x"}]},
        {"rotulo": "sonnet-5 · high", "repeticao": 1, "respostas": [{"id": "Q1", "resposta": "x"}]},
        {"rotulo": "opus-5 · high", "repeticao": 2, "respostas": [{"id": "Q1", "resposta": "y"}]}]}
    casou = regras.casar_harness(_aud(Q1="y"), h, modelo="claude-opus-5")
    assert casou == {"rotulo": "opus-5 · high", "repeticao": 2, "indice": 2}


def test_harness_sem_casamento_exato_e_ambiguo():
    h = {"execucoes": [{"rotulo": "opus-5 · high", "repeticao": 1,
                        "respostas": [{"id": "Q1", "resposta": "z"}]}]}
    assert regras.casar_harness(_aud(Q1="y"), h, modelo="claude-opus-5") == "ambíguo"


# ------------------------------------------------------------- nome citado
@pytest.mark.parametrize("citado,esperado", [
    ("01 - Edital - EDITAL.pdf", "01 - Edital - EDITAL.pdf"),            # exato
    ("EDITAL.pdf", "01 - Edital - EDITAL.pdf"),                          # sufixo
    ("ARQUIVO 02 - TR - termo.pdf", "02 - TR - termo.pdf"),              # rótulo colado
    ("anexo.pdf", None),                                                 # não existe
    (None, None),
])
def test_nome_citado_resolve_como_o_verificador(citado, esperado):
    nomes = {"01 - Edital - EDITAL.pdf", "02 - TR - termo.pdf"}
    assert regras.resolver_nome(citado, nomes) == esperado


def test_nome_citado_ambiguo_nao_resolve():
    # Dois candidatos: a citação é de fato ambígua e o link não pode escolher.
    assert regras.resolver_nome("edital.pdf", {"01 - edital.pdf", "02 - edital.pdf"}) is None


# ------------------------------------------------------------- Q13
def test_q13_estruturada_vira_json_com_os_totais():
    texto = ("Até R$ 2.000,00: 32; R$ 2.000,01 a R$ 3.000,00: 93; "
             "Acima de R$ 3.000,01: 12. Total: 137")
    d = regras.q13_estruturada(texto)
    assert d["tipo"] == "faixa salarial"
    assert d["soma"] == 137 and d["total_declarado"] == 137 and d["confere"] is True
    assert [l["quantidade"] for l in d["grupos"][0]["linhas"]] == [32, 93, 12]
    assert regras.q13_estruturada("Não localizado")["tipo"] == "ausente"


def test_respostas_do_harness_no_formato_real():
    # O harness grava {Qn: texto} e a evidência à parte, não a lista da auditoria.
    e = {"respostas": {"Q1": "09/10/2026", "Q6": "Não localizado"},
         "evidencia": {"Q1": {"arquivo": "01 - Edital.pdf", "pagina": 1, "trecho": "09 de outubro",
                              "veredito": "APROVADO", "alertas": []}}}
    rs = regras.respostas_do_harness(e)
    assert rs == [
        {"id": "Q1", "resposta": "09/10/2026", "arquivo": "01 - Edital.pdf", "pagina": 1,
         "trecho_literal": "09 de outubro", "conflito": None, "confianca": None},
        {"id": "Q6", "resposta": "Não localizado", "arquivo": None, "pagina": None,
         "trecho_literal": None, "conflito": None, "confianca": None}]
    lista = [{"id": "Q1", "resposta": "x"}]
    assert regras.respostas_do_harness({"respostas": lista}) == lista


def test_harness_casa_no_formato_real():
    h = {"execucoes": [{"rotulo": "opus-5 · high", "repeticao": 1, "respostas": {"Q1": "y"}}]}
    assert regras.casar_harness(_aud(Q1="y"), h, modelo="claude-opus-5")["indice"] == 0


def test_assinatura_com_nomes_distingue_o_mesmo_texto_sob_nomes_diferentes():
    # Capep: o mesmo texto lido sob "…__A.pdf" (downloader antigo cortou o nome)
    # e "…__AGOSTO_2026_Retificado.pdf". Para a gêmea é a mesma leitura; para a
    # citação não é — a resposta cita pelo nome.
    a = {"03 - Edital - X__A.pdf": "e22386", "04 - ETP.pdf": "4a6211"}
    b = {"03 - Edital - X__AGOSTO_2026_Retificado.pdf": "e22386", "04 - ETP.pdf": "4a6211"}
    assert regras.assinatura_conjunto(a) == regras.assinatura_conjunto(b)
    assert regras.assinatura_nomes(a) != regras.assinatura_nomes(b)
    assert regras.assinatura_nomes(a) == regras.assinatura_nomes(dict(reversed(list(a.items()))))
