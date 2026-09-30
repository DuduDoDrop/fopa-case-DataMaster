# -*- coding: utf-8 -*-
"""
W23 — o laço do reforço do Best-of-N (v3.1; N=3, só as que
falham). Estático: lê o JSON versionado, sem instância e sem banco.

Depois dos lotes (saída "done" do `Loop lotes`), o W23 pede ao worker `POST /reforco` os lotes só das perguntas que
o verificador reprovou ou não localizou e volta ao laço com eles (rodada 1, 2 ...). Cada chamada grava a rodada em
`chamadas_modelo.rodada` (db/050_melhor_de_n.sql; 0 = o lote normal). O worker decide quando acabou (no máximo N-1
rodadas) e escolhe o melhor candidato no /verificar; o n8n só faz o laço e não guarda estado. O reforço é
best-effort: falha do /reforco (rede, não-200) ou de uma chamada do reforço nunca derruba a extração.

    python -m pytest n8n/tests/test_w23_reforco.py -v
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import importar  # noqa: E402

ARQ = importar.PASTA_WORKFLOWS / "W23.json"
PROVEDORES = ("Anthropic /v1/messages", "OpenAI /v1/responses", "Worker /responder-simulado",
              "Worker /gravado/v1/messages")
NOVOS = ("POST /reforco", "Reforço?", "Lotes do reforço", "Falha no reforço?")
# a rodada decide de onde vem o corpo: 0 = o lote do /prompt; > 0 = o lote do /reforco da rodada corrente
FONTE = ("(($json.rodada || 0) > 0 ? $('POST /reforco').last().json.body.lotes"
         " : $('POST /prompt').first().json.body.lotes)[$json.lote_idx]")


def _wf() -> dict:
    return json.loads(ARQ.read_text(encoding="utf-8"))


def _no(wf: dict, nome: str) -> dict:
    return next(n for n in wf["nodes"] if n["name"] == nome)


def _destinos(wf: dict, origem: str) -> list[list[str]]:
    return [[c["node"] for c in saida] for saida in wf["connections"][origem]["main"]]


def _origens(wf: dict, destino: str) -> list[tuple[str, int]]:
    """(nó, índice da saída) de toda conexão que chega em `destino`."""
    return sorted((de, i) for de, tipos in wf["connections"].items() for i, saida in enumerate(tipos.get("main") or [])
                  for c in saida or [] if c["node"] == destino)


def _condicao(wf: dict, nome: str) -> str:
    conds = _no(wf, nome)["parameters"]["conditions"]["conditions"]
    assert len(conds) == 1, nome
    return conds[0]["leftValue"]


def _elementos(expr: str) -> list[str]:
    """Os elementos do array JS de um queryReplacement `={{ [ a, f(b, c), ... ] }}`: vírgulas de fora só."""
    m = re.fullmatch(r"=\{\{\s*\[(.*)\]\s*\}\}", expr, re.S)
    assert m, expr
    elementos, atual, nivel, aspas = [], "", 0, ""
    for ch in m.group(1):
        if aspas:
            aspas = "" if ch == aspas else aspas
        elif ch in "'\"`":
            aspas = ch
        elif ch in "([{":
            nivel += 1
        elif ch in ")]}":
            nivel -= 1
        elif ch == "," and nivel == 0:
            elementos.append(atual.strip())
            atual = ""
            continue
        atual += ch
    elementos.append(atual.strip())
    return elementos


# ------------------------------------------------------------------ o laço
def test_done_do_laco_pede_o_reforco_e_volta_ao_laco_com_os_lotes_dele():
    wf = _wf()
    assert _destinos(wf, "Loop lotes") == [["POST /reforco"], ["Preparar chamada"]]      # done, loop
    # sucesso e erro de rede do /reforco caem no mesmo if: a falha vai para o false (best-effort)
    assert _destinos(wf, "POST /reforco") == [["Reforço?"], ["Reforço?"]]
    assert _destinos(wf, "Reforço?") == [["Lotes do reforço"], ["Transição → respondida"]]
    assert _destinos(wf, "Lotes do reforço") == [["Loop lotes"]]
    # a extração só termina pelo false do Reforço? (fim, /reforco em falha ou resposta sem lote)
    assert _origens(wf, "Transição → respondida") == [("Reforço?", 1)]
    assert _origens(wf, "Loop lotes") == [("Falha no reforço?", 0), ("Lote respondido?", 0), ("Lotes", 0),
                                          ("Lotes do reforço", 0)]


def test_loop_lotes_recomeca_o_conjunto_quando_os_lotes_vem_do_reforco():
    loop = _no(_wf(), "Loop lotes")
    assert (loop["type"], loop["typeVersion"], loop["parameters"]["batchSize"]) == (
        "n8n-nodes-base.splitInBatches", 3, 1)
    # splitInBatches v3 (n8n 2.37): `options.reset === true` trata a entrada como um conjunto novo. Sem isso os
    # lotes do reforço entram como itens já processados do conjunto esgotado: o "done" sai na hora, com os itens da
    # rodada 0 junto, e o modelo nunca é chamado para eles (visto numa instância 2.37.10 descartável)
    assert loop["parameters"]["options"] == {"reset": "={{ $prevNode.name === 'Lotes do reforço' }}"}


def test_post_reforco_e_o_post_prompt_com_execucao_id_uma_vez_so():
    wf = _wf()
    prompt, reforco = _no(wf, "POST /prompt"), _no(wf, "POST /reforco")
    assert (reforco["type"], reforco["typeVersion"]) == (prompt["type"], prompt["typeVersion"])
    p, q = reforco["parameters"], prompt["parameters"]
    assert p["url"] == "={{ $env.FOPA_WORKER_URL }}/reforco"
    for chave in ("method", "authentication", "genericAuthType", "sendBody", "specifyBody", "options"):
        assert p[chave] == q[chave], chave
    assert p["options"]["timeout"] == 60000
    assert p["options"]["response"]["response"] == {"fullResponse": True, "neverError": True}
    assert reforco["credentials"] == prompt["credentials"] == {"httpHeaderAuth": {"id": "{{CRED:worker}}",
                                                                                  "name": "worker"}}
    assert reforco["onError"] == prompt["onError"] == "continueErrorOutput"
    # a saída done traz um item por lote: sem executeOnce seriam N pedidos de reforço
    assert reforco.get("executeOnce") is True
    # o corpo é o do /prompt, campo a campo, mais a execução aberta (o worker calcula a rodada pelo banco)
    assert q["jsonBody"].endswith(" }) }}")
    assert p["jsonBody"] == q["jsonBody"][:-len(" }) }}")] + ", execucao_id: $('Abrir execução').first().json.id }) }}"


def test_reforco_so_segue_com_200_fim_false_rodada_e_lotes():
    wf = _wf()
    cond = _condicao(wf, "Reforço?")
    # rodada > 0: um lote do reforço gravado como rodada 0 entraria na fusão dos lotes normais do /verificar
    for trecho in ("$json.statusCode === 200", "$json.body.fim === false", "Number($json.body.rodada) > 0",
                   "Array.isArray($json.body.lotes)", "$json.body.lotes.length > 0"):
        assert trecho in cond, trecho
    js = _no(wf, "Lotes do reforço")["parameters"]["jsCode"]
    assert "$('POST /reforco').last().json.body" in js
    for trecho in ("lote_idx: i", "ids: l.ids", "request_sha256: l.request_sha256", "tentativa: 0",
                   "rodada: Number(r.rodada)"):
        assert trecho in js, trecho


def test_falha_de_chamada_do_reforco_segue_o_laco_e_a_do_lote_normal_falha_a_extracao():
    wf = _wf()
    assert _destinos(wf, "Lote respondido?") == [["Loop lotes"], ["Falha no reforço?"]]
    assert _destinos(wf, "Falha no reforço?") == [["Loop lotes"], ["Motivo da falha"]]
    assert "$('Interpretar resposta').first().json.rodada > 0" in _condicao(wf, "Falha no reforço?")
    assert _origens(wf, "Motivo da falha") == [("Falha no reforço?", 1), ("Prompt pronto?", 1)]


# ------------------------------------------------------------------ a rodada
def test_os_4_provedores_escolhem_o_corpo_pela_rodada():
    wf = _wf()
    # $json nos provedores é o item do Preparar chamada, que passa pelo switch Provedor sem mudar
    assert _destinos(wf, "Preparar chamada") == [["Provedor"]]
    assert _destinos(wf, "Provedor") == [[n] for n in PROVEDORES]
    for nome in PROVEDORES:
        corpo = _no(wf, nome)["parameters"]["jsonBody"]
        campo = ".body_openai" if nome.startswith("OpenAI") else ".body"
        assert FONTE + campo in corpo, nome
        assert "$('POST /prompt').first().json.body.lotes[" not in corpo, nome     # nada lê o /prompt direto
        assert corpo.startswith("={{ JSON.stringify(" + ("{ body: " if nome.startswith("Worker") else "(")), nome


def test_a_rodada_passa_por_lotes_preparar_e_interpretar_inclusive_na_retentativa():
    wf = _wf()

    def js(nome: str) -> str:
        return _no(wf, nome)["parameters"]["jsCode"]

    assert "tentativa: 0" in js("Lotes") and "rodada: 0" in js("Lotes")
    assert "rodada: i.rodada || 0" in js("Preparar chamada")
    interpretar = js("Interpretar resposta")
    assert "const lote = $('Preparar chamada').first().json;" in interpretar
    assert "rodada: lote.rodada || 0" in interpretar
    # a retentativa volta ao Preparar chamada com o item que saiu do Interpretar resposta, que carrega a rodada
    assert _destinos(wf, "Interpretar resposta") == [["Retentar?"]]
    assert _destinos(wf, "Retentar?") == [["Esperar para retentar"], ["POST /custo"]]
    assert _destinos(wf, "Esperar para retentar") == [["Preparar chamada"]]


def test_gravar_chamada_grava_a_rodada_em_16():
    p = _no(_wf(), "Gravar chamada")["parameters"]
    sql = re.sub(r"--[^\n]*", "", p["query"])
    colunas = [c.strip() for c in re.search(r"INSERT INTO chamadas_modelo \(([^)]*)\)", sql).group(1).split(",")]
    assert len(colunas) == 16 and colunas[-1] == "rodada"
    valores = re.search(r"VALUES \((.*)\)\s*RETURNING", sql, re.S).group(1)
    assert [int(m) for m in re.findall(r"\$(\d+)", valores)] == list(range(1, 17))
    assert "$16::int" in valores
    elementos = _elementos(p["options"]["queryReplacement"])
    assert len(elementos) == 16
    assert elementos[-1] == "$('Interpretar resposta').first().json.rodada ?? 0"


# ------------------------------------------------------------------ o arquivo
def test_nota_do_w23_conta_o_best_of_n():
    nota = _no(_wf(), "Sobre o W23")["parameters"]["content"]
    for trecho in ("Best-of-N", "28/09/2026", "N=3", "só as que falham",
                   "POST /reforco", "chamadas_modelo.rodada", "nunca derruba a extração", "db/050_melhor_de_n.sql"):
        assert trecho in nota, trecho


def test_nos_novos_com_id_unico_posicao_propria_e_conexoes_validas():
    wf = _wf()
    nomes = [n["name"] for n in wf["nodes"]]
    ids = [n["id"] for n in wf["nodes"]]
    assert len(nomes) == len(set(nomes)) and len(ids) == len(set(ids))
    for nome in NOVOS:
        n = _no(wf, nome)
        assert str(uuid.UUID(n["id"])) == n["id"], nome
        assert len(n["position"]) == 2 and all(isinstance(x, int) for x in n["position"]), nome
        # as chaves na ordem do molde do importar/exportar (o diff do git mostra só o que mudou)
        assert list(n) == [k for k in importar.CHAVES_NO if k in n], nome
        for c in n["parameters"].get("conditions", {}).get("conditions", []):
            assert str(uuid.UUID(c["id"])) == c["id"], nome
    posicoes = [tuple(n["position"]) for n in wf["nodes"] if n["type"] != "n8n-nodes-base.stickyNote"]
    assert len(posicoes) == len(set(posicoes)), "dois nós no mesmo lugar do canvas"
    for de, tipos in wf["connections"].items():
        assert de in nomes, de
        assert all(c["node"] in nomes for saida in tipos["main"] for c in saida), de


def test_arquivo_segue_o_formato_do_exportar():
    # exportar.py: json.dumps(wf, ensure_ascii=False, indent=2) + "\n" (o CRLF é do checkout no Windows)
    texto = ARQ.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert texto == json.dumps(json.loads(texto), ensure_ascii=False, indent=2) + "\n"


def test_interpretar_openai_desconta_gravacao_e_cobra_a_gravacao_como_cache():
    """O `input_tokens` da Responses API soma a entrada nova, a GRAVADA e a lida no cache (fatura de 23/09). A
    gravada custa 1,25× (US$ 5/M no gpt-5.6-sol): vai para `cache_creation_input_tokens`, nunca fica na entrada
    (achado da medição antes/depois da v3.1, 28/09)."""
    codigo = _no(_wf(), "Interpretar resposta")["parameters"]["jsCode"]
    assert "cache_write_tokens" in codigo
    assert "cache_creation_input_tokens: gravado" in codigo
    assert "- cache - gravado" in codigo
