# -*- coding: utf-8 -*-
"""
A ordem do prompt (v3.1).

O cache dos dois provedores casa por PREFIXO. Até a v3.0 a mensagem começava pelas perguntas do lote — que mudam a
cada lote — e o documento, idêntico nos três lotes, era regravado três vezes: 45,6% da fatura da OpenAI foi
gravação de cache (Fopa-v2/04-Avaliacao/Resultados medidos.md). Documentos primeiro: o prefixo é o mesmo nos
lotes, 1 gravação + 2 leituras. No Claude o cache precisa ser pedido: o bloco de documentos leva `cache_control`.

O formato antigo continua disponível (`perguntas-primeiro`) para medir o "antes" com o mesmo código, e o worker
continua lendo chamadas antigas gravadas no banco (reverificação, provedor gravado).
"""
from __future__ import annotations

import pytest

from api import extracao
from fopa import extrator, modelos
from fopa import recuperacao as rec
from fopa.questionario import ESQUEMA_LOTE

CTX = "=== ARQUIVO 01 - Edital.pdf | PÁGINA 1 ===\nObjeto: folha de pagamento dos servidores."
L1, L2 = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"], ["Q7", "Q8", "Q9", "Q10", "Q11", "Q12"]


def test_ordem_velha_reproduz_o_texto_de_hoje():
    esperado = """LICITAÇÃO: %s

Responda as perguntas abaixo usando EXCLUSIVAMENTE os documentos fornecidos.

%s

=== DOCUMENTOS ===

%s

=== FIM DOS DOCUMENTOS ===

Devolva uma resposta para CADA pergunta listada, na ordem, com trecho literal,
arquivo e página física conforme os marcadores "=== ARQUIVO x | PÁGINA n ===".""" % (
        "Pregão 1/2026", extrator._bloco_perguntas(["Q1", "Q2"]), CTX)
    assert extrator.montar_mensagem(CTX, ["Q1", "Q2"], "Pregão 1/2026", "perguntas-primeiro") == esperado


def test_ordem_nova_poe_documentos_antes_e_o_prefixo_e_igual_entre_lotes():
    p1, s1 = extrator.montar_partes(CTX, L1, "Pregão 1/2026")
    p2, s2 = extrator.montar_partes(CTX, L2, "Pregão 1/2026")
    assert p1 == p2                                     # o que o cache reaproveita de um lote para o outro
    assert p1.startswith("LICITAÇÃO: Pregão 1/2026") and p1.rstrip().endswith("=== FIM DOS DOCUMENTOS ===")
    assert CTX in p1 and "Q7." not in p1                # nenhuma pergunta dentro do prefixo
    assert s2.index("Q7.") < s2.index("Devolva uma resposta")
    assert extrator.ORDEM_PADRAO == "documentos-primeiro"
    assert extrator.montar_mensagem(CTX, L2, "Pregão 1/2026") == p2 + "\n\n" + s2


def test_ordem_desconhecida_falha_alto():
    with pytest.raises(ValueError, match="ordem"):
        extrator.montar_partes(CTX, L1, "L", "perguntas-no-fim")


@pytest.mark.parametrize("modelo", ["claude-opus-5-5", "claude-haiku-4-5"])
def test_corpo_claude_marca_cache_so_no_bloco_de_documentos(modelo):
    partes = extrator.montar_partes(CTX, L1, "L")
    corpo = extracao.corpo_claude("sistema", partes, ESQUEMA_LOTE, modelo, 16000, "high")
    blocos = corpo["messages"][0]["content"]
    assert [b["text"] for b in blocos] == list(partes)
    assert blocos[0]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in blocos[1]
    assert corpo["system"][0]["cache_control"] == {"type": "ephemeral"}    # o sistema continua em cache
    assert ("thinking" in corpo) == (modelo != "claude-haiku-4-5")         # Haiku 4.5 segue sem thinking


def test_corpo_claude_com_texto_unico_continua_como_hoje():
    corpo = extracao.corpo_claude("sistema", "texto", ESQUEMA_LOTE, "claude-opus-5-5", 16000, "high")
    assert corpo["messages"][0]["content"] == "texto"


def test_conteudo_claude_e_o_mesmo_no_sdk_e_no_corpo_do_n8n():
    partes = extrator.montar_partes(CTX, L1, "L")
    assert modelos.conteudo_claude(partes) == extracao.corpo_claude(
        "s", partes, ESQUEMA_LOTE, "claude-opus-5-5", 16000, "high")["messages"][0]["content"]


def test_corpo_openai_recebe_texto_unico_com_documentos_primeiro():
    partes = extrator.montar_partes(CTX, L1, "L")
    corpo = extracao.corpo_openai("sistema", partes, ESQUEMA_LOTE, "gpt-5.6-sol", 16000, "high")
    assert corpo["input"] == partes[0] + "\n\n" + partes[1]
    assert corpo["input"].index("=== DOCUMENTOS ===") < corpo["input"].index("Q1.")


def test_ids_do_usuario_le_as_duas_ordens_e_content_em_lista():
    velha = extrator.montar_mensagem(CTX, L2, "L", "perguntas-primeiro")
    nova = extrator.montar_partes(CTX, L2, "L")
    assert extracao.ids_do_usuario(velha) == L2
    assert extracao.ids_do_usuario("\n\n".join(nova)) == L2
    assert extracao.ids_do_usuario([{"type": "text", "text": t} for t in nova]) == L2
    # uma linha "Q3. ..." DENTRO do documento não é pergunta do lote
    com_q_no_texto = extrator.montar_partes(CTX + "\nQ3. item do termo de referência", L2, "L")
    assert extracao.ids_do_usuario("\n\n".join(com_q_no_texto)) == L2


def test_partes_do_corpo_devolve_texto_quando_content_e_lista():
    partes = extrator.montar_partes(CTX, L1, "L")
    corpo = extracao.corpo_claude("sistema", partes, ESQUEMA_LOTE, "claude-opus-5-5", 16000, "high")
    sistema, usuario = extracao.partes_do_corpo(corpo)
    assert sistema == "sistema" and usuario == partes[0] + "\n\n" + partes[1]


def test_simulado_da_as_mesmas_respostas_nas_duas_ordens():
    """O simulado é o piso da medição e o provedor do CI: a ordem não pode mudar o que ele acha.

    Ele separa as páginas por regex até o fim do texto; na ordem nova, sem parar no fim do bloco de documentos,
    o bloco de perguntas viraria texto da última página — e ele "acharia" trechos nas próprias perguntas.
    """
    ctx = rec.montar_contexto([
        rec.Pagina(arquivo="01 - Edital.pdf", numero=1,
                   texto="O objeto é a contratação de instituição financeira para a folha de pagamento."),
        rec.Pagina(arquivo="01 - Edital.pdf", numero=2,
                   texto="A sessão pública será realizada em 10/10/2026 às 9h no portal.")])
    ids = [p for p in extracao.IDS]
    sim = modelos.ProvedorSimulado()
    velha, _ = sim.responder_json("s", extrator.montar_mensagem(ctx, ids, "L", "perguntas-primeiro"), ESQUEMA_LOTE, "s")
    nova, _ = sim.responder_json("s", extrator.montar_partes(ctx, ids, "L"), ESQUEMA_LOTE, "s")
    assert nova["respostas"] == velha["respostas"]


def test_simulado_responde_os_ids_do_lote_na_ordem_nova():
    partes = extrator.montar_partes(CTX, L2, "L")
    corpo = extracao.corpo_claude("sistema", partes, ESQUEMA_LOTE, "claude-opus-5-5", 16000, "high")
    env = extracao.responder_simulado(corpo)
    assert sorted(r["id"] for r in extracao.dados_do_envelope(env)["respostas"]) == sorted(L2)


def test_montar_prompt_lotes_compartilham_o_prefixo_em_contexto_completo():
    paginas = [rec.Pagina(arquivo="01 - Edital.pdf", numero=1, texto="Objeto: folha de pagamento.")]
    p = extracao.montar_prompt(paginas, "L", modo="contexto-completo", modelo="claude-opus-5-5")
    prefixos = {l["body"]["messages"][0]["content"][0]["text"] for l in p["lotes"]}
    assert len(p["lotes"]) == 3 and len(prefixos) == 1
    assert [extracao.ids_do_usuario(l["body"]["messages"][0]["content"]) for l in p["lotes"]] == [
        l["ids"] for l in p["lotes"]]
    antigo = extracao.montar_prompt(paginas, "L", modo="contexto-completo", modelo="claude-opus-5-5",
                                    ordem="perguntas-primeiro")
    assert isinstance(antigo["lotes"][0]["body"]["messages"][0]["content"], str)


def test_rag_poe_documentos_primeiro_mas_nao_marca_o_documento_para_cache():
    """No RAG cada lote recupera páginas diferentes: o prefixo de documentos nunca se repete entre lotes, e marcá-lo
    para cache no Claude cobraria a gravação (1,25×) sem nenhuma leitura — +43% em Bertioga, pela estimativa da
    medição antes/depois (28/09). Os documentos continuam antes das perguntas; só o cache_control do bloco sai."""
    paginas = [rec.Pagina(arquivo="01 - Edital.pdf", numero=n, texto="Página %d: folha de pagamento, sessão, lance." % n)
               for n in range(1, 4)]
    p = extracao.montar_prompt(paginas, "L", modo="rag", modelo="claude-opus-5-5")
    assert p["modo"] == "rag"
    for lote in p["lotes"]:
        conteudo = lote["body"]["messages"][0]["content"]
        assert isinstance(conteudo, str)                                     # sem bloco em cache
        assert conteudo.index("=== DOCUMENTOS ===") < conteudo.index("Responda as perguntas")
        assert extracao.ids_do_usuario(conteudo) == lote["ids"]
    completo = extracao.montar_prompt(paginas, "L", modo="contexto-completo", modelo="claude-opus-5-5")
    assert all(isinstance(l["body"]["messages"][0]["content"], list) for l in completo["lotes"])
