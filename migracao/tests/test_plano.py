# -*- coding: utf-8 -*-
"""
O plano de importação: o que cada pasta do acervo vira, antes de tocar no banco.

Cada teste monta um snapshot sintético com a fábrica e confere o plano que sai
dele. Os casos são os do acervo real de 24/09/2026, reduzidos: uma extração do
agente, uma da API sem páginas congeladas, o controle de Castro-PR com uma pasta
contaminada, as licitações que só existem no corpus, a pasta sem arquivo nenhum.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migracao import plano as plano_mod  # noqa: E402
from migracao.acervo import Acervo  # noqa: E402

import fabrica  # noqa: E402
from fabrica import PastaFake  # noqa: E402

HOJE = date(2026, 9, 24)
C1 = "12345678000101-1-000001/2026"
C2 = "12345678000102-1-000002/2026"
C3 = "12345678000103-1-000003/2026"
C4 = "12345678000104-1-000004/2026"
C5 = "12345678000105-1-000005/2026"
C6 = "12345678000106-1-000006/2026"
EDITAL = b"%PDF edital um"
TR = b"%PDF termo de referencia"


def _pasta_agente(nome, controle, pdfs=None, em="2026-09-23T23:37:13-0300", de=None,
                  lidos=None, fim_prazo="2026-12-01T09:00", vereditos=None):
    pdfs = pdfs or {"01 - Edital.pdf": EDITAL}
    lidos = lidos or list(pdfs)
    paginas = [(a, 1, "texto de %s" % a) for a in lidos]
    rs = fabrica.respostas(lidos[0])
    return PastaFake(nome=nome, controle=controle, pdfs=pdfs, fim_prazo=fim_prazo,
                     auditoria=fabrica.auditoria(nome, rs, vereditos=vereditos),
                     leitura_paginas=paginas, respostas_agente=rs,
                     finalizado=fabrica.finalizado(nome, em=em, de=de))


def _montar(tmp_path, pastas, **kw):
    snap, vivo = fabrica.criar(str(tmp_path), pastas, **kw)
    return plano_mod.montar(Acervo(snap, vivo), hoje=HOJE)


def test_extracao_do_agente_vira_licitacao_verificada_com_leitura_e_execucao(tmp_path):
    p = _montar(tmp_path, [_pasta_agente("Pregão - Teste-SP", C1)])
    lic = p.licitacoes[C1]
    assert lic.estado == "verificada"
    assert lic.campos["uf"] == "SP" and lic.campos["escopo_dentro"] is True
    assert lic.campos["fim_prazo"] == "2026-12-01T09:00:00-03:00" and lic.campos["fim_prazo_tem_hora"]
    assert lic.canonica == "Pregão - Teste-SP"
    (le,) = [x for x in p.leituras if x.controle == C1]
    assert le.vigente and le.procedencia_texto == "legado_paginas_json"
    assert le.versao_ocr.startswith("host-5.4.0.20240606") and "(inferida)" in le.versao_ocr
    (ex,) = [x for x in p.execucoes if x.controle == C1]
    assert (ex.origem, ex.provedor, ex.modelo, ex.lote, ex.canonica) == (
        "agente", "claude-code", "claude-opus-5-5", 17, True)
    assert ex.brl is None and ex.preco_conhecido is False
    assert len(ex.respostas) == 17 and ex.leitura_pasta == "Pregão - Teste-SP"
    v = ex.verificacao
    assert v.vigente and v.versao_regras.startswith("legado:")
    assert (v.aprovadas, v.nao_localizado, v.respondidas, v.ancoradas) == (17, 2, 15, 15)
    assert {r["pergunta_id"] for r in v.respostas} == set(fabrica.PERGUNTAS)
    q6 = next(r for r in v.respostas if r["pergunta_id"] == "Q6")
    assert q6["ausencia"] == "sem_evidencia" and q6["arquivo_canonico"] is None
    q1 = next(r for r in v.respostas if r["pergunta_id"] == "Q1")
    assert q1["arquivo_canonico"] == "01 - Edital.pdf" and q1["pagina_final"] == 1
    (arq,) = p.arquivos[C1]
    assert arq.status == "ok" and arq.pasta == "Pregão - Teste-SP"


def test_extracao_pela_api_sem_paginas_congeladas(tmp_path):
    rs = fabrica.respostas("01 - Edital.pdf")
    pasta = PastaFake(nome="ABERTO Pregao - Api-RS", controle=C2, pdfs={"01 - Edital.pdf": EDITAL},
                      auditoria=fabrica.auditoria("ABERTO Pregao - Api-RS", rs, provedor="",
                                                  modelo="claude-opus-5", chamadas=0, brl=6.563,
                                                  modo="contexto-completo", agente=False))
    p = _montar(tmp_path, [pasta])
    (ex,) = [x for x in p.execucoes if x.controle == C2]
    assert (ex.origem, ex.provedor, ex.modelo, ex.effort, ex.lote) == ("api", "claude", "claude-opus-5", "high", 6)
    assert ex.brl is None and ex.brl_legado == 6.563 and ex.preco_conhecido is True
    assert ex.procedencia_completa is False and ex.custo_formula == "legado (cache_escrita desconhecida)"
    assert ex.chamadas == 3 and "chamadas" in ex.fonte_migracao["inferidos"]
    assert ex.tok_entrada == 200000 and ex.tok_cache_escrita is None
    assert ex.leitura_pasta is None and ex.verificacao.vigente
    assert p.licitacoes[C2].estado == "verificada"


def test_controle_em_duas_pastas_com_uma_contaminada(tmp_path):
    # Castro-PR: a pasta sem sufixo tem um PDF de outra licitação, e o agente o leu.
    contaminada = _pasta_agente("Castro-PR", C3, pdfs={"01 - Edital.pdf": EDITAL, "PE 133.pdf": TR},
                                lidos=["01 - Edital.pdf", "PE 133.pdf"], em="2026-09-23T23:57:59-0300")
    contaminada.inventario_arquivos = [{"seq": 1, "arquivo": "01 - Edital.pdf", "sha256": fabrica.sha(EDITAL)}]
    limpa = _pasta_agente("Castro-PR - 557-2026", C3, pdfs={"01 - Edital.pdf": EDITAL},
                          em="2026-09-23T23:58:00-0300")
    p = _montar(tmp_path, [contaminada, limpa])
    lic = p.licitacoes[C3]
    assert lic.canonica == "Castro-PR - 557-2026" and "fora do inventário" in lic.canonica_motivo
    assert lic.estado == "verificada" and lic.procedencia_incerta is False
    assert sorted(lic.pastas) == ["Castro-PR", "Castro-PR - 557-2026"]
    exs = {x.pasta: x for x in p.execucoes if x.controle == C3}
    assert exs["Castro-PR - 557-2026"].canonica and not exs["Castro-PR"].canonica
    assert exs["Castro-PR - 557-2026"].verificacao.vigente
    assert not exs["Castro-PR"].verificacao.vigente
    les = {x.pasta: x for x in p.leituras if x.controle == C3}
    assert les["Castro-PR - 557-2026"].vigente and not les["Castro-PR"].vigente
    status = {(a.pasta, a.nome): a.status for a in p.arquivos[C3]}
    assert status[("Castro-PR", "PE 133.pdf")] == "procedencia_incerta"
    # o mesmo nome e o mesmo conteúdo nas duas pastas é UMA linha de arquivos
    assert sum(1 for a in p.arquivos[C3] if a.nome == "01 - Edital.pdf") == 1


def test_empate_sem_criterio_vira_legado_suspeito_e_decisao(tmp_path):
    a = _pasta_agente("Pasta A", C4)
    b = _pasta_agente("Pasta B", C4)
    p = _montar(tmp_path, [a, b])
    assert p.licitacoes[C4].estado == "legado_suspeito"
    assert not any(x.verificacao and x.verificacao.vigente for x in p.execucoes if x.controle == C4)
    assert any(d["controle"] == C4 for d in p.decisoes)


def test_original_vence_a_reaproveitada(tmp_path):
    a = _pasta_agente("Capep", C4)
    b = _pasta_agente("Capep-Saude", C4, de="Capep")
    p = _montar(tmp_path, [a, b])
    assert p.licitacoes[C4].canonica == "Capep"
    exs = {x.pasta: x for x in p.execucoes if x.controle == C4}
    assert exs["Capep-Saude"].reaproveitado_de_pasta == "Capep"


def test_corpus_sem_pasta_nova_encerrada_e_fora_de_escopo(tmp_path):
    corpus = [
        {"controle": C1, "orgao": "A", "uf": "RS", "municipio": "A", "modalidade": "Pregão",
         "fim_prazo": "2026-12-01T09:00", "publicado_em": "2026-09-01", "situacao": "x",
         "dentro": True, "motivo": "folha", "objeto": "folha de pagamento"},
        {"controle": C2, "orgao": "B", "uf": "RS", "municipio": "B", "modalidade": "Pregão",
         "fim_prazo": "2026-04-01T09:00", "publicado_em": "2026-03-01", "situacao": "x",
         "dentro": True, "motivo": "folha", "objeto": "folha de pagamento"},
        {"controle": C3, "orgao": "C", "uf": "RS", "municipio": "C", "modalidade": "Dispensa",
         "fim_prazo": "2026-12-01T09:00", "publicado_em": "2026-09-01", "situacao": "x",
         "dentro": False, "motivo": "sistema ou plataforma que opera sobre a folha", "objeto": "software"}]
    p = _montar(tmp_path, [], corpus=corpus)
    assert p.licitacoes[C1].estado == "nova" and p.licitacoes[C1].campos["origem"] == "corpus"
    assert p.licitacoes[C2].estado == "fora_janela"
    fora = p.licitacoes[C3]
    assert fora.estado == "fora_escopo" and fora.campos["escopo_motivo"].startswith("sistema")
    assert fora.campos["escopo_dentro"] is False


def test_leitura_sem_execucao_e_preparada(tmp_path):
    pasta = PastaFake(nome="Preparada-SP", controle=C5, pdfs={"01 - Edital.pdf": EDITAL},
                      leitura_paginas=[("01 - Edital.pdf", 1, "texto")])
    p = _montar(tmp_path, [pasta])
    assert p.licitacoes[C5].estado == "preparada"
    (le,) = p.leituras
    assert le.vigente and le.n_paginas == 1


def test_pasta_sem_arquivo_segue_a_dica_do_livro(tmp_path):
    fmt = PastaFake(nome="Formato-MG", controle=C5, inventario_arquivos=[],
                    extras_inventario={"estado_no_livro": "formato-nao-suportado"})
    falhou = PastaFake(nome="Falhou-PR", controle=C6, inventario_arquivos=[],
                       extras_inventario={"sem_causa_registrada": "coletor antigo"})
    p = _montar(tmp_path, [fmt, falhou])
    assert p.licitacoes[C5].estado == "formato_nao_suportado"
    assert p.licitacoes[C6].estado == "falha_rede"


def test_baixada_sem_leitura(tmp_path):
    p = _montar(tmp_path, [PastaFake(nome="So PDF-SP", controle=C6, pdfs={"01 - Edital.pdf": EDITAL})])
    assert p.licitacoes[C6].estado == "baixada_ok"


def test_gemeas_por_texto_entre_controles_diferentes(tmp_path):
    # Caibi e Caibi - 724-2026: controles diferentes, o mesmo texto lido.
    a = _pasta_agente("Caibi-SC", C1)
    b = PastaFake(nome="Caibi-SC - 724-2026", controle=C2, pdfs={"01 - Edital.pdf": EDITAL},
                  leitura_paginas=[("01 - Edital.pdf", 1, "texto de 01 - Edital.pdf")])
    p = _montar(tmp_path, [a, b])
    assert p.licitacoes[C2].gemea_de == C1 and p.licitacoes[C1].gemea_de is None


def test_harness_promovido_e_experimentos(tmp_path):
    rs = fabrica.respostas("01 - Edital.pdf")
    api = PastaFake(nome="ABERTO Pregao - Adrianopolis-PR", controle=C2, pdfs={"01 - Edital.pdf": EDITAL},
                    auditoria=fabrica.auditoria("ABERTO Pregao - Adrianopolis-PR", rs, provedor="",
                                                modelo="claude-opus-5", chamadas=0, brl=6.563,
                                                modo="contexto-completo", agente=False))
    # formato real do harness: {Qn: texto}, evidência à parte
    como_dict = {r["id"]: r["resposta"] for r in rs}
    outra = {k: "outra" for k in como_dict}
    harness = {"_harness_ABERTO Pregao - Adrianopolis-PR.json": {
        "licitacao": "ABERTO Pregao - Adrianopolis-PR",
        "execucoes": [
            {"rotulo": "opus-5 · high", "modelo": "claude-opus-5", "effort": "high",
             "modo": "contexto-completo", "repeticao": 1, "entrada": 212295, "saida": 9018,
             "brl": 6.575, "respostas": como_dict},
            {"rotulo": "sonnet-5 · high", "modelo": "claude-sonnet-5", "effort": "high",
             "modo": "contexto-completo", "repeticao": 1, "entrada": 212000, "saida": 9000,
             "brl": 2.1, "respostas": outra}]}}
    p = _montar(tmp_path, [api], harness=harness)
    api_ex = next(x for x in p.execucoes if x.origem == "api")
    assert api_ex.fonte_migracao["harness"]["rotulo"] == "opus-5 · high"
    hs = [x for x in p.execucoes if x.origem == "harness"]
    # a repetição promovida É a execução da API: não entra de novo como harness
    assert [x.modelo for x in hs] == ["claude-sonnet-5"] and not hs[0].canonica


def test_auxiliares(tmp_path):
    pasta = _pasta_agente("Pirapo-RS", C1)
    pasta.itens_api = [{"numeroItem": 1, "descricao": "cessão"}]
    pasta.gabarito = {"licitacao": "Pirapo-RS", "perguntas": {
        "Q1": {"critica": True, "resposta_referencia": "08/10/2026", "fatos_obrigatorios": ["08/10/2026"]}}}
    execs = [{"em": "2026-09-23T12:54:41-0300", "script": "28_baixar_licitacao.py", "duracao_s": 0.1,
              "argumentos": "--todas", "custo_brl": 0.0, "baixadas": 2}]
    p = _montar(tmp_path, [pasta], execucoes=execs)
    assert p.itens_api[C1] == [{"numeroItem": 1, "descricao": "cessão"}]
    assert p.execucoes[0].verificacao.itens_api_usados is True
    (g,) = p.gabaritos
    assert (g["controle"], g["pergunta_id"], g["critica"]) == (C1, "Q1", True)
    (w,) = p.execucoes_workflow
    assert (w["script_legado"], w["custo_brl"], w["contadores"]) == ("28_baixar_licitacao.py", 0.0, {"baixadas": 2})


def test_gemeas_pelos_mesmos_pdfs_quando_uma_nao_tem_leitura(tmp_path):
    # Capão do Cipó 303 (agente, com leitura) e 304 (API, sem paginas.json):
    # controles diferentes, os mesmos PDFs. Sem texto congelado na 304, a
    # assinatura do texto não as junta; o conjunto de sha dos PDFs junta.
    a = _pasta_agente("Capao Do Cipo-RS", C1)
    rs = fabrica.respostas("01 - Edital.pdf")
    b = PastaFake(nome="ABERTO Capao do Cipo-RS", controle=C2, pdfs={"01 - Edital.pdf": EDITAL},
                  auditoria=fabrica.auditoria("ABERTO Capao do Cipo-RS", rs, provedor="", modelo="claude-opus-5",
                                              chamadas=3, brl=5.874, modo="contexto-completo", agente=False))
    p = _montar(tmp_path, [a, b])
    gemeas = {p.licitacoes[C1].gemea_de, p.licitacoes[C2].gemea_de} - {None}
    assert gemeas in ({C1}, {C2})
