# -*- coding: utf-8 -*-
"""
O Best-of-N na v3 (28/09/2026): `POST /reforco` e a escolha no `/verificar`, contra Postgres real.

O n8n (W23) faz os lotes normais (rodada 0) e depois pergunta ao worker o que reforçar; o worker funde o que já foi
gravado, roda o verificador e devolve os lotes SÓ das perguntas que falharam — ou `fim`. As chamadas do reforço
voltam gravadas com `rodada > 0`; o `/verificar` escolhe, por pergunta, entre o original e os candidatos, pelo
veredito do verificador, e grava o registro em `verificacoes.melhor_de_n`. O modelo continua sendo chamado só pelo
n8n: nenhuma rota aqui fala com modelo.
"""
from __future__ import annotations

import json

import psycopg

from api.tests.test_worker_extracao import C1, H, _execucao_simulada, amb, pg  # noqa: F401  (fixtures)
from fopa.questionario import NAO_LOCALIZADO

CORPO = dict(provedor="simulado", modelo="simulado", effort="high", lote=6, k_rag=6, max_tokens=16000)
TRECHO_BOM = "Data da sessão pública: 10/10/2026 às 09h00."


def _reforco(amb, eid, **kw):
    corpo = dict(CORPO, leitura_id=amb["leitura"], execucao_id=eid)
    corpo.update(kw)
    r = amb["c"].post("/reforco", headers=H, json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _nao_localizadas(amb, eid) -> set[str]:
    """As perguntas que o simulado não achou nas chamadas gravadas — é o que o reforço tem de pedir."""
    with psycopg.connect(amb["url"]) as c:
        vazias = set()
        for (dados,) in c.execute("SELECT dados FROM chamadas_modelo WHERE execucao_id = %s", (eid,)):
            texto = "".join(b["text"] for b in dados["content"] if b["type"] == "text")
            vazias |= {r["id"] for r in json.loads(texto)["respostas"]
                       if (r["resposta"] or "").startswith(NAO_LOCALIZADO)}
    return vazias


def _gravar_reforco(amb, eid, pid, rodada, *, trecho=TRECHO_BOM, http_status=200):
    dados = {"respostas": [{"id": pid, "resposta": "10/10/2026 às 9h", "arquivo": "01 - Edital.pdf", "pagina": 1,
                            "trecho_literal": trecho, "conflito": None, "confianca": "alta"}]}
    env = {"content": [{"type": "text", "text": json.dumps(dados, ensure_ascii=False)}], "stop_reason": "end_turn"}
    with psycopg.connect(amb["url"]) as c:
        c.execute("INSERT INTO chamadas_modelo (execucao_id, lote_ids, dados, stop_reason, http_status, tentativas,"
                  " tok_entrada, tok_saida, request_sha256, usd, brl, preco_conhecido, rodada)"
                  " VALUES (%s, %s, %s, 'end_turn', %s, 1, 10, 5, 'x', 0, 0, true, %s)",
                  (eid, [pid], json.dumps(env), http_status, rodada))


def test_reforco_devolve_so_as_perguntas_que_falharam(amb):
    eid = _execucao_simulada(amb)
    esperadas = _nao_localizadas(amb, eid)
    assert esperadas, "o cenário precisa de pergunta que o simulado não acha"
    d = _reforco(amb, eid)
    assert d["fim"] is False and d["rodada"] == 1
    assert set(d["ids"]) == esperadas
    assert sorted(i for l in d["lotes"] for i in l["ids"]) == sorted(d["ids"])
    assert all(len(l["ids"]) <= 6 for l in d["lotes"])
    corpo = d["lotes"][0]["body"]
    assert isinstance(corpo["messages"][0]["content"], list)        # ordem nova: documentos em cache


def test_verificar_escolhe_o_candidato_do_reforco_e_ignora_chamada_que_falhou(amb):
    eid = _execucao_simulada(amb)
    falhas = sorted(_reforco(amb, eid)["ids"], key=lambda i: int(i[1:]))
    boa, quebrada = falhas[0], (falhas[1] if len(falhas) > 1 else None)
    _gravar_reforco(amb, eid, boa, 1)
    if quebrada:
        _gravar_reforco(amb, eid, quebrada, 1, http_status=500)      # falha no reforço: fica o original
    r = amb["c"].post("/verificar", headers=H, json={"execucao_id": eid})
    assert r.status_code == 200, r.text
    d = r.json()
    reg = d["melhor_de_n"]["perguntas"]
    assert reg[boa]["escolhida"] == 1 and reg[boa]["tentativas"] == 2
    # a tentativa que falhou conta no registro (Review Focus 5): tentou 2 vezes, ficou a original
    assert quebrada is None or (reg[quebrada]["escolhida"] == 0 and reg[quebrada]["tentativas"] == 2
                                and reg[quebrada]["falhas"] == 1)
    assert d["melhor_de_n"]["rodadas"] == 1 and d["melhor_de_n"]["n"] == 3
    with psycopg.connect(amb["url"]) as c:
        salvo = c.execute("SELECT melhor_de_n FROM verificacoes WHERE id = %s", (d["verificacao_id"],)).fetchone()[0]
        assert salvo == d["melhor_de_n"]
        trecho = c.execute("SELECT trecho_literal FROM respostas WHERE execucao_id = %s AND pergunta_id = %s",
                           (eid, boa)).fetchone()[0]
        assert trecho == TRECHO_BOM                                   # a resposta gravada é a escolhida
        chamadas, entrada = c.execute("SELECT chamadas, tok_entrada FROM execucoes_modelo WHERE id = %s",
                                      (eid,)).fetchone()
        assert chamadas == 4 and entrada >= 10                        # o reforço bem-sucedido entra no custo


def test_reforco_para_quando_as_rodadas_acabam_ou_n_e_1(amb):
    eid = _execucao_simulada(amb)
    pid = _reforco(amb, eid)["ids"][0]
    _gravar_reforco(amb, eid, pid, 1, trecho="texto que não está no edital")
    d = _reforco(amb, eid)
    assert d["fim"] is False and d["rodada"] == 2                     # ainda falha: segunda rodada
    _gravar_reforco(amb, eid, pid, 2, trecho="outro texto que não está no edital")
    d = _reforco(amb, eid)
    assert d["fim"] is True and d["lotes"] == []                      # N=3: no máximo 2 rodadas
    with psycopg.connect(amb["url"], autocommit=True) as c:
        c.execute("UPDATE configuracao SET valor = '1' WHERE chave = 'melhor_de_n'")
    try:
        assert _reforco(amb, _execucao_simulada(amb))["fim"] is True     # N=1 desliga o reforço
    finally:
        with psycopg.connect(amb["url"], autocommit=True) as c:
            c.execute("UPDATE configuracao SET valor = '3' WHERE chave = 'melhor_de_n'")


def test_reforco_nao_se_aplica_ao_gravado_nem_sem_execucao(amb):
    eid = _execucao_simulada(amb)
    with psycopg.connect(amb["url"]) as c:
        c.execute("UPDATE execucoes_modelo SET provedor = 'gravado', origem = 'gravado' WHERE id = %s", (eid,))
    assert _reforco(amb, eid)["fim"] is True
    r = amb["c"].post("/reforco", headers=H, json=dict(CORPO, leitura_id=amb["leitura"]))
    assert r.status_code == 422
    r = amb["c"].post("/reforco", headers=H, json=dict(CORPO, leitura_id=amb["leitura"], execucao_id=999999))
    assert r.status_code == 404
    assert amb["c"].post("/reforco", json=dict(CORPO, execucao_id=eid)).status_code == 401


def test_reforco_respeita_o_teto_de_gasto_do_dia(amb):
    """A vaga do W23 reserva o pior caso de uma extração sem reforço (fn_tomar_vaga_extracao); o reforço gasta
    DEPOIS dela. Com o gasto do dia no teto, não há reforço: fica o original e a extração segue (ADR-024)."""
    eid = _execucao_simulada(amb)
    with psycopg.connect(amb["url"], autocommit=True) as c:
        antes = c.execute("SELECT teto_brl_dia FROM orcamento WHERE vigente").fetchone()[0]
        c.execute("UPDATE orcamento SET teto_brl_dia = 1.00 WHERE vigente")
        c.execute("INSERT INTO chamadas_modelo (execucao_id, lote_ids, http_status, brl, preco_conhecido)"
                  " VALUES (%s, ARRAY['Q1'], 500, 1.50, true)", (eid,))      # o dia já gastou R$ 1,50
    try:
        d = _reforco(amb, eid)
        assert d["fim"] is True and d["lotes"] == [] and "teto" in d["motivo"]
    finally:
        with psycopg.connect(amb["url"], autocommit=True) as c:
            c.execute("UPDATE orcamento SET teto_brl_dia = %s WHERE vigente", (antes,))


def _inventar_na_rodada_0(amb, eid, pid):
    """Troca, na chamada gravada da rodada 0, a resposta de `pid` por uma citação que não está no edital (REPROVADA)."""
    with psycopg.connect(amb["url"]) as c:
        cid, dados = c.execute("SELECT id, dados FROM chamadas_modelo WHERE execucao_id = %s AND rodada = 0"
                               " AND %s = ANY(lote_ids)", (eid, pid)).fetchone()
        bloco = next(b for b in dados["content"] if b["type"] == "text")
        respostas = json.loads(bloco["text"])
        for r in respostas["respostas"]:
            if r["id"] == pid:
                r.update(resposta="inventada", arquivo="01 - Edital.pdf", pagina=1, confianca="alta",
                         trecho_literal="a sessão será realizada no dia 31 de dezembro de 2030 no auditório")
        bloco["text"] = json.dumps(respostas, ensure_ascii=False)
        c.execute("UPDATE chamadas_modelo SET dados = %s WHERE id = %s", (json.dumps(dados), cid))


def test_reforco_que_omite_a_pergunta_nao_inventa_nao_localizado(amb):
    """Revisão (28/09), item 1: o reforço veio 200/end_turn mas sem a pergunta. Silêncio não é resposta (ADR-011): nada
    de "Não localizado" fabricado vencendo a original — conta como tentativa que falhou."""
    eid = _execucao_simulada(amb)
    pid = sorted(_nao_localizadas(amb, eid), key=lambda i: int(i[1:]))[0]
    _inventar_na_rodada_0(amb, eid, pid)
    assert pid in _reforco(amb, eid)["ids"]                          # a original agora é REPROVADA
    env = {"content": [{"type": "text", "text": json.dumps({"respostas": []})}], "stop_reason": "end_turn"}
    with psycopg.connect(amb["url"]) as c:
        c.execute("INSERT INTO chamadas_modelo (execucao_id, lote_ids, dados, stop_reason, http_status, tentativas,"
                  " request_sha256, rodada) VALUES (%s, %s, %s, 'end_turn', 200, 1, 'x', 1)",
                  (eid, [pid], json.dumps(env)))
    d = amb["c"].post("/verificar", headers=H, json={"execucao_id": eid}).json()
    reg = d["melhor_de_n"]["perguntas"][pid]
    assert (reg["escolhida"], reg["tentativas"], reg["falhas"]) == (0, 2, 1)
    with psycopg.connect(amb["url"]) as c:
        resposta = c.execute("SELECT resposta FROM respostas WHERE execucao_id = %s AND pergunta_id = %s",
                             (eid, pid)).fetchone()[0]
    assert resposta == "inventada"                                     # ficou a original, não um vazio inventado


def test_registro_existe_mesmo_quando_todo_reforco_falha(amb):
    """Revisão (28/09), item 2: 2 rodadas pagas e todas as chamadas em HTTP 500 — o registro diz que o reforço foi
    tentado (e quantas vezes), em vez de sumir."""
    eid = _execucao_simulada(amb)
    falhas = _reforco(amb, eid)["ids"]
    for rodada in (1, 2):
        for pid in falhas:
            _gravar_reforco(amb, eid, pid, rodada, http_status=500)
    d = amb["c"].post("/verificar", headers=H, json={"execucao_id": eid}).json()
    assert d["melhor_de_n"] is not None and d["melhor_de_n"]["rodadas"] == 2
    assert set(d["melhor_de_n"]["perguntas"]) == set(falhas)
    assert all((r["escolhida"], r["tentativas"], r["falhas"]) == (0, 3, 2)
               for r in d["melhor_de_n"]["perguntas"].values())


def test_reverificar_leva_o_registro_do_melhor_de_n(amb, monkeypatch):
    """Revisão (28/09), item 5: o W30 (/reverificar) reaplica regras às respostas escolhidas; o rastro da escolha vai
    junto para a verificação nova, senão a nota "escolhida a 2ª de 3" some da tela na próxima mudança de regra."""
    eid = _execucao_simulada(amb)
    pid = sorted(_reforco(amb, eid)["ids"], key=lambda i: int(i[1:]))[0]
    _gravar_reforco(amb, eid, pid, 1)
    original = amb["c"].post("/verificar", headers=H, json={"execucao_id": eid}).json()["melhor_de_n"]
    from api import versao
    monkeypatch.setattr(versao, "versao_regras", lambda: "regras-da-proxima-versao")
    r = amb["c"].post("/reverificar", headers=H, json={"execucao_id": eid})
    assert r.status_code == 200, r.text
    with psycopg.connect(amb["url"]) as c:
        nova = c.execute("SELECT melhor_de_n FROM verificacoes WHERE id = %s",
                         (r.json()["verificacao_id"],)).fetchone()[0]
    assert nova == original and nova["perguntas"][pid]["escolhida"] == 1


def test_gravado_nao_repete_chamada_de_reforco(amb):
    """Revisão (28/09), item 4: o replay da demo (/gravado) procurava a última chamada com os mesmos ids — e pegava uma
    de reforço, inclusive uma que falhou (529), quando o lote de reforço coincidia com um lote normal."""
    from api.tests.test_worker_extracao import C2, _prompt
    lote = _prompt(amb)["lotes"][1]
    with psycopg.connect(amb["url"]) as c:
        eid = c.execute("SELECT execucao_id FROM verificacoes WHERE controle = %s AND vigente", (C2,)).fetchone()[0]
        c.execute("INSERT INTO chamadas_modelo (execucao_id, lote_ids, dados, stop_reason, http_status, tentativas,"
                  " request_sha256, rodada) VALUES (%s, %s, %s, NULL, 529, 3, 'x', 1)",
                  (eid, lote["ids"], json.dumps({"type": "error", "error": {"type": "overloaded_error"}})))
    r = amb["c"].post("/gravado/v1/messages?controle=" + C2, headers=H, json={"body": lote["body"]})
    assert r.status_code == 200, r.text
    dados = json.loads(r.json()["content"][0]["text"])
    assert dados["respostas"][0]["trecho_literal"].startswith("Conforme o item Q7")
