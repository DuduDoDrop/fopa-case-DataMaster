# -*- coding: utf-8 -*-
"""
Medição antes × depois da v3.1 — `scripts/35_antes_depois.py` (plano da v3.1, Task 8).

Decisão de 28/09/2026: remedir Pirapó e Bertioga no Claude e no GPT — antes (perguntas primeiro, N=1, a
v3.0) e depois (documentos primeiro com o documento em cache, Best-of-N com N=3). A medição gasta dinheiro de
verdade: por isso o script tem o `--seco` (estima montando os prompts reais, sem chamar modelo) e um teto em R$.

Nada aqui chama modelo nem rede. As partes puras (matriz, acurácia, cache, custo, teto, tabelas) são testadas
direto; a execução medida roda com um provedor-roteiro, e o `main` com o carregador de páginas e a fábrica de
provedores trocados por dublês.
"""
from __future__ import annotations

import importlib.util
import json
import os

import pytest

import api  # põe scripts/ no sys.path e impede o pacote fopa de ler o .env
from api import extracao
from fopa import extrator, modelos
from fopa import recuperacao as rec
from fopa.modelos import Provedor, Uso
from fopa.questionario import instrucao_sistema

SCRIPTS = os.path.join(api.RAIZ, "scripts")


def _carregar(nome: str, arquivo: str):
    """Os scripts começam com dígito: não dá para importar pelo nome (o 34_placar faz o mesmo com o 15_acuracia)."""
    spec = importlib.util.spec_from_file_location(nome, os.path.join(SCRIPTS, arquivo))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ad():
    return _carregar("antes_depois_35", "35_antes_depois.py")


@pytest.fixture(scope="module")
def avaliar():
    return _carregar("acuracia_15", "15_acuracia.py").avaliar


# ------------------------------------------------------------------ um edital de duas páginas e um provedor-roteiro
ARQ = "01 - Edital.pdf"
P1 = ("O objeto é a contratação de instituição financeira para gestão da folha de pagamento "
      "dos servidores municipais, com exclusividade.")
P2 = "A sessão pública ocorrerá em 10 de outubro de 2026, às 9 horas, no portal de compras."
PAGINAS = [rec.Pagina(arquivo=ARQ, numero=1, texto=P1), rec.Pagina(arquivo=ARQ, numero=2, texto=P2)]
IDS = ["Q%d" % i for i in range(1, 18)]
BOA = {"resposta": "Gestão da folha de pagamento", "arquivo": ARQ, "pagina": 1, "confianca": "alta",
       "trecho_literal": "contratação de instituição financeira para gestão da folha"}
Q7_BOA = dict(BOA, resposta="Sessão em 10/10/2026", pagina=2,
              trecho_literal="A sessão pública ocorrerá em 10 de outubro de 2026")
Q7_RUIM = dict(BOA, resposta="Sessão em 11/11/2026", pagina=2,
               trecho_literal="a sessão será no dia 11 de novembro de 2026")      # não está na página: reprova
GABARITO = {"Q2": {"critica": False, "fatos_obrigatorios": ["folha"]},
            "Q7": {"critica": True, "fatos_obrigatorios": ["10/10/2026"]}}


class Roteiro(Provedor):
    """Responde BOA a tudo, menos às perguntas do roteiro: a tentativa k de uma pergunta sai da lista dela.

    Cada execução começa pelo lote Q1–Q6: ali o roteiro recomeça, para que o `main` possa reusar o mesmo provedor
    nas duas configurações, como faz com o real."""

    nome = "claude"

    def __init__(self, roteiro: dict[str, list[dict]]):
        self.roteiro = roteiro
        self.vistas: dict[str, int] = {}
        self.usuarios: list = []

    def responder_json(self, sistema, usuario, esquema, modelo, max_tokens=16000, effort="high"):
        ids = extracao.ids_do_usuario(usuario)
        if ids[:1] == ["Q1"]:
            self.vistas = {}
        self.usuarios.append(usuario)
        respostas = []
        for pid in ids:
            k = self.vistas.get(pid, 0)
            self.vistas[pid] = k + 1
            plano = self.roteiro.get(pid)
            respostas.append(dict(plano[min(k, len(plano) - 1)] if plano else BOA, id=pid))
        return {"respostas": respostas}, Uso(entrada=1000, cache_leitura=500, saida=200, chamadas=1, modelo=modelo)


def _licitacao(tmp_path) -> dict:
    pasta = tmp_path / "Pregão Eletrônico 1-2026 - Cidade-RS"
    pasta.mkdir()
    return {"pasta": str(pasta), "nome": pasta.name, "paginas": list(PAGINAS), "modalidade": "Pregão Eletrônico",
            "gabarito": GABARITO, "observadas": None}


# ------------------------------------------------------------------ matriz de configurações
def test_matriz_cruza_licitacao_modelo_e_configuracao_nessa_ordem(ad):
    plano = ad.matriz([os.path.join("x", "Pirapo-RS"), os.path.join("x", "Bertioga-SP")],
                      ["claude-opus-5-5", "gpt-5.6-sol"], ["antes", "depois"])
    assert [(p["licitacao"], p["modelo"], p["config"]) for p in plano] == [
        ("Pirapo-RS", "claude-opus-5-5", "antes"), ("Pirapo-RS", "claude-opus-5-5", "depois"),
        ("Pirapo-RS", "gpt-5.6-sol", "antes"), ("Pirapo-RS", "gpt-5.6-sol", "depois"),
        ("Bertioga-SP", "claude-opus-5-5", "antes"), ("Bertioga-SP", "claude-opus-5-5", "depois"),
        ("Bertioga-SP", "gpt-5.6-sol", "antes"), ("Bertioga-SP", "gpt-5.6-sol", "depois")]
    assert [(p["provedor"], p["ordem"], p["melhor_de_n"]) for p in plano[:4]] == [
        ("claude", "perguntas-primeiro", 1), ("claude", "documentos-primeiro", 3),
        ("openai", "perguntas-primeiro", 1), ("openai", "documentos-primeiro", 3)]
    assert plano[0]["pasta"] == os.path.join("x", "Pirapo-RS")


def test_matriz_recusa_configuracao_e_modelo_desconhecidos(ad):
    with pytest.raises(ValueError, match="meio"):
        ad.matriz(["P"], ["claude-opus-5-5"], ["meio"])
    with pytest.raises(ValueError, match="llama-9"):
        ad.matriz(["P"], ["llama-9"], ["antes"])


# ------------------------------------------------------------------ acurácia contra o gabarito
def test_acuracia_conta_todas_as_criticas_e_a_completude(ad, avaliar):
    perguntas = {
        "Q1": {"critica": True, "fatos_obrigatorios": ["08/10/2026"], "fatos_desejaveis": ["09:00"]},
        "Q2": {"critica": False, "fatos_obrigatorios": ["cessao onerosa"], "fatos_desejaveis": ["60 meses"]},
        "Q5": {"critica": True, "fatos_obrigatorios": ["250.000,00"]},
        "Q9": {"critica": False, "fatos_obrigatorios": ["60"]}}
    respostas = {"Q1": "Sessão em 08/10/2026 às 09h00", "Q2": "Cessão onerosa da folha",
                 "Q5": "R$ 2.500,00"}                                   # a Q9 não veio: conta como errada
    assert ad.agregar_acuracia(respostas, perguntas, avaliar) == {
        "acertos": 2, "total": 4, "criticas_acertos": 1, "criticas_total": 2,
        "desejaveis": 1, "desejaveis_total": 2, "erradas": ["Q5", "Q9"]}


def test_numero_no_fim_da_frase_e_o_mesmo_numero(avaliar):
    """Bertioga, Q13, 28/09: "…; Total 1.896. População coberta…" traz o 1.896 — o ponto é da frase, não do número.
    A âncora de dígito recusava qualquer pontuação depois do número e reprovou uma resposta certa."""
    ref = {"fatos_obrigatorios": ["1.896"]}
    assert avaliar("CLT 124; Estatutário com RGPS 98; Total 1.896. População coberta: Administração Direta", ref)[
        "correta"]
    assert avaliar("Total 1.896: vínculos, não pessoas", ref)["correta"]
    assert avaliar("Total 1.896", ref)["correta"]
    # a âncora continua valendo: o fato não casa dentro de outro número
    assert not avaliar("R$ 1.896.000,00", ref)["correta"]
    assert not avaliar("R$ 1.896,50", ref)["correta"]
    assert not avaliar("21.896 vínculos", ref)["correta"]
    assert not avaliar("faixa 3.000,00", {"fatos_obrigatorios": ["3"]})["correta"]


# ------------------------------------------------------------------ o efeito do cache, chamada a chamada
def test_cache_claude_antes_grava_so_o_sistema_e_cobra_o_documento_em_todo_lote(ad):
    chamadas = [[("S", 1500, True), ("perguntas %d + documentos" % i, 40_000, False)] for i in range(3)]
    assert ad.simular_cache(chamadas, "claude", 1024) == [
        {"entrada": 40_000, "cache_escrita": 1500, "cache_leitura": 0},
        {"entrada": 40_000, "cache_escrita": 0, "cache_leitura": 1500},
        {"entrada": 40_000, "cache_escrita": 0, "cache_leitura": 1500}]


def test_cache_claude_depois_grava_o_documento_uma_vez_e_le_nos_lotes_seguintes(ad):
    chamadas = [[("S", 1500, True), ("D", 40_000, True), ("perguntas %d" % i, 500, False)] for i in range(3)]
    assert ad.simular_cache(chamadas, "claude", 1024) == [
        {"entrada": 500, "cache_escrita": 41_500, "cache_leitura": 0},
        {"entrada": 500, "cache_escrita": 0, "cache_leitura": 41_500},
        {"entrada": 500, "cache_escrita": 0, "cache_leitura": 41_500}]


def test_cache_claude_depois_no_rag_grava_cada_contexto_e_so_le_o_sistema(ad):
    # no RAG cada lote recupera outras páginas: o prefixo muda e a ordem nova paga a gravação sem nunca ler
    chamadas = [[("S", 1500, True), ("D%d" % i, 20_000, True), ("P%d" % i, 500, False)] for i in range(3)]
    assert ad.simular_cache(chamadas, "claude", 1024) == [
        {"entrada": 500, "cache_escrita": 21_500, "cache_leitura": 0},
        {"entrada": 500, "cache_escrita": 20_000, "cache_leitura": 1500},
        {"entrada": 500, "cache_escrita": 20_000, "cache_leitura": 1500}]


def test_cache_openai_antes_regrava_o_prompt_inteiro_em_cada_lote(ad):
    # o que os lotes têm em comum (o sistema) fica abaixo do mínimo de 1.024 tokens: nada a ler
    chamadas = [[("S", 765, False), ("perguntas %d + documentos" % i, 27_000, False)] for i in range(3)]
    assert ad.simular_cache(chamadas, "openai", 1024) == [
        {"entrada": 0, "cache_escrita": 27_765, "cache_leitura": 0}] * 3


def test_cache_openai_depois_uma_gravacao_e_leituras_inclusive_no_reforco(ad):
    chamadas = [[("S", 765, False), ("D", 26_500, False), ("perguntas %d" % i, 500, False)] for i in range(4)]
    assert ad.simular_cache(chamadas, "openai", 1024) == [
        {"entrada": 0, "cache_escrita": 27_765, "cache_leitura": 0},
        {"entrada": 0, "cache_escrita": 500, "cache_leitura": 27_265},
        {"entrada": 0, "cache_escrita": 500, "cache_leitura": 27_265},
        {"entrada": 0, "cache_escrita": 500, "cache_leitura": 27_265}]


def test_prompt_abaixo_do_minimo_nao_entra_no_cache(ad):
    assert ad.simular_cache([[("S", 800, True), ("M", 100, False)]] * 2, "claude", 1024) == [
        {"entrada": 900, "cache_escrita": 0, "cache_leitura": 0}] * 2
    assert ad.simular_cache([[("S", 800, False), ("M", 100, False)]] * 2, "openai", 1024) == [
        {"entrada": 900, "cache_escrita": 0, "cache_leitura": 0}] * 2
    # o Haiku 4.5 pede 4.096: um sistema de 1.500 tokens fica fora do cache
    assert ad.simular_cache([[("S", 1500, True), ("M", 100, False)]], "claude", 4096) == [
        {"entrada": 1600, "cache_escrita": 0, "cache_leitura": 0}]


# ------------------------------------------------------------------ custo estimado
def test_custo_estimado_usa_o_preco_e_os_multiplicadores_do_modelos_py(ad):
    # Opus 5.5: US$ 4 de entrada e 20 de saída por milhão; cache grava a 1,25× e lê a 0,10× da entrada
    chamadas = [[("S", 1000, True), ("D", 100_000, True), ("P%d" % i, 1000, False)] for i in range(3)]
    e = ad.custo_estimado(chamadas, "claude-opus-5-5", saida_por_chamada=4000)
    assert {k: e[k] for k in ("chamadas", "entrada", "cache_escrita", "cache_leitura", "saida")} == {
        "chamadas": 3, "entrada": 3000, "cache_escrita": 101_000, "cache_leitura": 202_000, "saida": 12_000}
    # 3.000×4 + 101.000×5 + 202.000×0,4 + 12.000×20 = 837.800 → US$ 0,8378
    assert e["usd"] == pytest.approx(0.8378, abs=1e-6)
    assert e["brl"] == pytest.approx(0.8378 * modelos.USD_BRL, abs=1e-3)


def test_custo_estimado_sem_preco_no_catalogo_fica_desconhecido(ad):
    e = ad.custo_estimado([[("S", 5000, True)]], "claude-sem-preco-1", saida_por_chamada=4000)
    assert e["usd"] is None and e["brl"] is None


def test_contador_sem_tiktoken_e_caracteres_sobre_4_e_o_claude_aplica_o_fator_medido(ad):
    assert ad.contador("openai", None)("x" * 400) == 100
    assert ad.contador("claude", None)("x" * 400) == round(100 * ad.FATOR_TOKENS_CLAUDE)


# ------------------------------------------------------------------ os prompts da estimativa são os do extrator
def test_estimativa_monta_os_prompts_de_verdade_na_ordem_antiga(ad):
    modo, chamadas = ad.chamadas_da_execucao(PAGINAS, "Pregão 1-2026", "perguntas-primeiro", 1)
    ctx = rec.montar_contexto(PAGINAS)
    assert modo == "contexto-completo"
    assert [u for _, u in chamadas] == [
        extrator.montar_mensagem(ctx, IDS[0:6], "Pregão 1-2026", "perguntas-primeiro"),
        extrator.montar_mensagem(ctx, IDS[6:12], "Pregão 1-2026", "perguntas-primeiro"),
        extrator.montar_mensagem(ctx, IDS[12:17], "Pregão 1-2026", "perguntas-primeiro")]
    assert all(s.startswith(instrucao_sistema()) for s, _ in chamadas)


def test_estimativa_na_ordem_nova_soma_o_reforco_ate_n_menos_1_rodadas(ad):
    ctx = rec.montar_contexto(PAGINAS)
    _, chamadas = ad.chamadas_da_execucao(PAGINAS, "Pregão 1-2026", "documentos-primeiro", 3)
    reforco = list(ad.REFORCO_PERGUNTAS)
    assert [u for _, u in chamadas] == [
        extrator.montar_partes(ctx, IDS[0:6], "Pregão 1-2026"),
        extrator.montar_partes(ctx, IDS[6:12], "Pregão 1-2026"),
        extrator.montar_partes(ctx, IDS[12:17], "Pregão 1-2026"),
        extrator.montar_partes(ctx, reforco, "Pregão 1-2026")]        # hipótese: 1 lote de reforço
    assert len(ad.chamadas_da_execucao(PAGINAS, "L", "documentos-primeiro", 3, rodadas=2)[1]) == 5
    assert len(ad.chamadas_da_execucao(PAGINAS, "L", "documentos-primeiro", 2, rodadas=2)[1]) == 4   # N-1 = 1
    assert len(ad.chamadas_da_execucao(PAGINAS, "L", "perguntas-primeiro", 1, rodadas=2)[1]) == 3    # sem reforço


def test_blocos_seguem_as_marcas_de_cache_do_provedor_claude(ad):
    # sistema sempre em cache; na ordem nova, o prefixo (licitação + documentos) também — modelos.conteudo_claude
    assert ad.blocos_da_chamada("SIS", ("PREFIXO", "SUFIXO"), len) == [
        ("SIS", 3, True), ("PREFIXO", 7, True), ("SUFIXO", 6, False)]
    assert ad.blocos_da_chamada("SIS", "MENSAGEM", len) == [("SIS", 3, True), ("MENSAGEM", 8, False)]


def test_documentos_primeiro_troca_a_regravacao_por_leitura_no_contexto_completo(ad):
    grande = [rec.Pagina(arquivo=ARQ, numero=i, texto=("cláusula %d da folha de pagamento. " % i) * 140)
              for i in range(1, 31)]                  # ~150 mil caracteres: contexto completo, bem acima do mínimo
    contar = ad.contador("openai", None)
    antes = ad.estimar_execucao(grande, "L", "gpt-5.6-sol", "perguntas-primeiro", 1, contar)
    depois = ad.estimar_execucao(grande, "L", "gpt-5.6-sol", "documentos-primeiro", 3, contar)
    assert antes["modo"] == depois["modo"] == "contexto-completo"
    assert antes["uso"]["chamadas"] == 3 and depois["uso"]["chamadas"] == 4
    assert antes["uso"]["cache_leitura"] == 0
    assert depois["uso"]["cache_escrita"] < antes["uso"]["cache_escrita"] / 2
    assert depois["uso"]["cache_leitura"] > antes["uso"]["cache_escrita"] / 2
    assert depois["uso"]["usd"] < antes["uso"]["usd"]


# ------------------------------------------------------------------ o teto
def test_teto_barra_a_execucao_cuja_estimativa_passaria_dele(ad):
    assert ad.cabe_no_teto(50.0, 9.99, 60.0)
    assert ad.cabe_no_teto(50.0, 10.0, 60.0)                 # chegar exatamente ao teto ainda cabe
    assert not ad.cabe_no_teto(50.0, 10.01, 60.0)
    assert not ad.cabe_no_teto(0.0, None, 60.0)              # sem preço não há estimativa: não roda


def test_rodar_para_antes_da_execucao_que_passaria_do_teto(ad):
    plano = ad.matriz(["P"], ["claude-opus-5-5", "gpt-5.6-sol"], ["antes", "depois"])
    feitas, parciais = [], []

    def medir(item, est):
        feitas.append((item["modelo"], item["config"]))
        return {"licitacao": item["licitacao"], "modelo": item["modelo"], "config": item["config"],
                "uso": {"brl": 3.5}}

    registros, gasto, parada = ad.rodar(plano, [{"uso": {"brl": 3.0}}] * 4, 10.0, medir,
                                        depois_de_cada=lambda regs, g: parciais.append((len(regs), g)))
    # 0+3 ≤ 10 roda (3,5) · 3,5+3 ≤ 10 roda (7,0) · 7+3 ≤ 10 roda (10,5) · 10,5+3 > 10 para
    assert feitas == [("claude-opus-5-5", "antes"), ("claude-opus-5-5", "depois"), ("gpt-5.6-sol", "antes")]
    assert gasto == pytest.approx(10.5) and len(registros) == 3
    assert parciais == [(1, pytest.approx(3.5)), (2, pytest.approx(7.0)), (3, pytest.approx(10.5))]
    assert "gpt-5.6-sol" in parada and "depois" in parada


def test_rodar_conta_a_estimativa_quando_a_execucao_falha(ad):
    plano = ad.matriz(["P"], ["claude-opus-5-5"], ["antes", "depois"])

    def medir(item, est):
        if item["config"] == "antes":
            raise RuntimeError("caiu no 2º lote")        # o que já foi cobrado não volta no ext.uso
        return {"licitacao": item["licitacao"], "modelo": item["modelo"], "config": item["config"],
                "uso": {"brl": 2.0}}

    registros, gasto, parada = ad.rodar(plano, [{"uso": {"brl": 3.0}}, {"uso": {"brl": 2.5}}], 60.0, medir)
    assert registros[0]["erro"] == "caiu no 2º lote" and registros[0]["uso"] is None
    assert registros[1]["uso"] == {"brl": 2.0}
    assert gasto == pytest.approx(5.0) and parada is None


# ------------------------------------------------------------------ o registro do reforço
def test_resumo_do_reforco_conta_rodadas_trocas_e_recuperacoes(ad):
    registro = {"n": 3, "rodadas": 2, "perguntas": {
        "Q15": {"tentativas": 3, "escolhida": 0, "pontos": [[0, 0.0], [0, 0.0], [0, 0.0]]},  # ausência que ficou
        "Q7": {"tentativas": 2, "escolhida": 1, "pontos": [[-1, 0.41], [2, 1.0]]},           # recuperada
        "Q9": {"tentativas": 2, "escolhida": 1, "pontos": [[-1, 0.3], [0, 0.0]]}}}          # trocou, sem evidência
    assert ad.resumo_reforco(registro) == {"rodadas": 2, "reforcadas": 3, "trocadas": 2, "recuperadas": 1}
    assert ad.resumo_reforco({}) == {"rodadas": 0, "reforcadas": 0, "trocadas": 0, "recuperadas": 0}


# ------------------------------------------------------------------ tabelas
PIRAPO = "ABERTO Concorrencia - Eletronica - Pirapo-RS"


def _reg(config, brl, acertos=None, criticas=None, erro=None):
    return {"licitacao": PIRAPO, "modelo": "claude-opus-5-5", "config": config, "erro": erro,
            "uso": None if erro else {"brl": brl},
            "acuracia": None if acertos is None else {"acertos": acertos, "total": 17,
                                                       "criticas_acertos": criticas, "criticas_total": 7}}


def test_comparacao_mostra_a_diferenca_de_custo_e_de_acuracia(ad):
    md = ad.tabela_comparacao(ad.comparar([_reg("antes", 4.0, 15, 6), _reg("depois", 3.0, 16, 7)]))
    assert "| Pirapo-RS | claude-opus-5-5 | 4,00 | 3,00 | -25,0% | 15/17 | 16/17 | +1 | 6/7 → 7/7 |" in md


def test_comparacao_com_uma_execucao_que_falhou_nao_inventa_diferenca(ad):
    md = ad.tabela_comparacao(ad.comparar([_reg("antes", 4.0, 15, 6), _reg("depois", None, erro="caiu")]))
    assert "| Pirapo-RS | claude-opus-5-5 | 4,00 | — | — | 15/17 | — | — | 6/7 → — |" in md


def test_comparacao_de_estimativas_so_tem_custo(ad):
    md = ad.tabela_comparacao(ad.comparar([_reg("antes", 4.1), _reg("depois", 4.51)]))
    assert "| Pirapo-RS | claude-opus-5-5 | 4,10 | 4,51 | +10,0% | — | — | — | — |" in md


def test_tabela_de_estimativas_soma_o_total_em_reais(ad):
    uso = {"chamadas": 3, "entrada": 137_000, "cache_escrita": 1331, "cache_leitura": 2662, "saida": 12_000,
           "usd": 0.8, "brl": 4.08}
    ests = [{"licitacao": PIRAPO, "modelo": "claude-opus-5-5", "config": "antes", "modo": "contexto-completo",
             "uso": uso},
            {"licitacao": PIRAPO, "modelo": "claude-opus-5-5", "config": "depois", "modo": "contexto-completo",
             "uso": dict(uso, chamadas=4, usd=0.6, brl=3.06)}]
    md = ad.tabela_estimativas(ests)
    assert ("| Pirapo-RS | claude-opus-5-5 | antes | contexto-completo | 3 | 137.000 | 1.331 | 2.662 | 12.000 "
            "| 0,8000 | 4,08 |") in md
    assert md.rstrip().splitlines()[-1] == ("| **total** | | | | 7 | 274.000 | 2.662 | 5.324 | 24.000 | 1,4000 "
                                            "| **7,14** |")


# ------------------------------------------------------------------ de onde vêm a modalidade e as licitações
def test_modalidade_vem_do_inventario_e_na_falta_dele_do_nome_da_pasta(ad, tmp_path):
    com = tmp_path / "ABERTO Concorrencia - Eletronica - Pirapo-RS"
    com.mkdir()
    (com / "_inventario.json").write_text(json.dumps({"modalidade": "Concorrência - Eletrônica"}),
                                          encoding="utf-8")
    sem = tmp_path / "Dispensa - Rio Branco-AC"
    sem.mkdir()
    assert ad.modalidade_da_pasta(str(com)) == "Concorrência - Eletrônica"
    assert ad.modalidade_da_pasta(str(sem)) == "Dispensa - Rio Branco-AC"


def test_licitacoes_padrao_sao_as_que_tem_gabarito(ad, tmp_path):
    for nome, gabarito in (("P - Pirapo-RS", True), ("B - Bertioga-SP", True), ("Q - Quevedos-RS", False)):
        (tmp_path / nome).mkdir()
        if gabarito:
            (tmp_path / nome / "_gabarito.json").write_text("{}", encoding="utf-8")
    assert ad.licitacoes_padrao(str(tmp_path)) == [str(tmp_path / "B - Bertioga-SP"),
                                                  str(tmp_path / "P - Pirapo-RS")]


# ------------------------------------------------------------------ uma execução medida (provedor-roteiro)
def test_medir_depois_extrai_com_reforco_verifica_pontua_e_grava_a_auditoria(ad, avaliar, tmp_path):
    lic = _licitacao(tmp_path)
    saidas = tmp_path / "saidas"
    prov = Roteiro({"Q7": [Q7_RUIM, Q7_BOA]})
    item = ad.matriz([lic["pasta"]], ["claude-opus-5-5"], ["depois"])[0]
    reg = ad.medir(item, lic, prov, avaliar, str(saidas), {"uso": {"brl": 1.23}})

    assert all(isinstance(u, tuple) for u in prov.usuarios)          # ordem nova: (prefixo em cache, sufixo)
    assert reg["uso"]["chamadas"] == 4                                # 3 lotes + 1 reforço, que entra no custo
    assert (reg["uso"]["entrada"], reg["uso"]["cache_leitura"], reg["uso"]["saida"]) == (4000, 2000, 800)
    assert reg["reforco"] == {"rodadas": 1, "reforcadas": 1, "trocadas": 1, "recuperadas": 1}
    assert reg["verificacao"]["reprovadas"] == 0
    assert reg["acuracia"]["acertos"] == 2 and reg["acuracia"]["erradas"] == []
    assert reg["estimativa_brl"] == 1.23 and reg["erro"] is None
    caminho = saidas / lic["nome"] / "claude-opus-5-5-depois" / "auditoria.json"
    with open(caminho, encoding="utf-8") as f:
        d = json.load(f)
    assert d["licitacao"] == lic["nome"] and d["uso"]["chamadas"] == 4
    assert next(r for r in d["respostas"] if r["id"] == "Q7")["trecho_literal"] == Q7_BOA["trecho_literal"]


def test_medir_antes_e_a_extracao_de_sempre(ad, avaliar, tmp_path):
    lic = _licitacao(tmp_path)
    prov = Roteiro({"Q7": [Q7_RUIM, Q7_BOA]})
    item = ad.matriz([lic["pasta"]], ["claude-opus-5-5"], ["antes"])[0]
    reg = ad.medir(item, lic, prov, avaliar, str(tmp_path / "saidas"), {"uso": {"brl": 1.0}})

    assert all(isinstance(u, str) for u in prov.usuarios)            # ordem antiga: texto único, sem cache novo
    assert reg["uso"]["chamadas"] == 3
    assert reg["reforco"] == {"rodadas": 0, "reforcadas": 0, "trocadas": 0, "recuperadas": 0}
    assert reg["verificacao"]["reprovadas"] == 1 and reg["acuracia"]["erradas"] == ["Q7"]


# ------------------------------------------------------------------ o main, de ponta a ponta, sem modelo
def _pasta_com_gabarito(tmp_path):
    pasta = tmp_path / "Pregão Eletrônico 1-2026 - Cidade-RS"
    pasta.mkdir()
    (pasta / "_gabarito.json").write_text(json.dumps({"perguntas": GABARITO}), encoding="utf-8")
    return pasta


def test_main_seco_estima_e_nao_chama_modelo(ad, tmp_path, monkeypatch, capsys):
    pasta = _pasta_com_gabarito(tmp_path)

    def proibido(*a, **k):
        raise AssertionError("o --seco chamou modelo")

    monkeypatch.setattr(ad.extrator, "carregar_paginas", lambda p, **k: list(PAGINAS))
    monkeypatch.setattr(ad.extrator, "extrair", proibido)
    monkeypatch.setattr(ad.modelos, "obter_provedor", proibido)
    saidas = tmp_path / "saidas"
    assert ad.main(["--seco", "--licitacoes", str(pasta), "--saidas", str(saidas)]) == 0

    with open(saidas / "estimativa.json", encoding="utf-8") as f:
        est = json.load(f)
    assert [(e["modelo"], e["config"]) for e in est["execucoes"]] == [
        ("claude-opus-5-5", "antes"), ("claude-opus-5-5", "depois"),
        ("gpt-5.6-sol", "antes"), ("gpt-5.6-sol", "depois")]
    assert est["total_brl"] == pytest.approx(sum(e["uso"]["brl"] for e in est["execucoes"]), abs=0.01)
    assert "TOTAL ESTIMADO" in capsys.readouterr().out
    assert not (saidas / "resultado.json").exists()


def test_main_mede_as_configuracoes_e_grava_o_resultado(ad, tmp_path, monkeypatch):
    pasta = _pasta_com_gabarito(tmp_path)
    prov = Roteiro({"Q7": [Q7_RUIM, Q7_BOA]})
    monkeypatch.setattr(ad.extrator, "carregar_paginas", lambda p, **k: list(PAGINAS))
    monkeypatch.setattr(ad.modelos, "obter_provedor", lambda **k: prov)
    saidas = tmp_path / "saidas"
    assert ad.main(["--licitacoes", str(pasta), "--modelos", "claude-opus-5-5", "--saidas", str(saidas)]) == 0

    with open(saidas / "resultado.json", encoding="utf-8") as f:
        res = json.load(f)
    assert [(r["config"], r["acuracia"]["acertos"]) for r in res["execucoes"]] == [("antes", 1), ("depois", 2)]
    assert res["comparacao"][0]["acuracia_delta"] == 1 and res["parada"] is None
    for config in ("antes", "depois"):
        assert (saidas / pasta.name / ("claude-opus-5-5-%s" % config) / "auditoria.json").is_file()
    md = (saidas / "resultado.md").read_text(encoding="utf-8")
    assert "| Cidade-RS | claude-opus-5-5 |" in md and "| 1/2 | 2/2 | +1 |" in md
