# -*- coding: utf-8 -*-
"""
Enriquece o corpus com metadados das APIs do PNCP que ESTÃO de pé.

    python 31_enriquecer_corpus.py            enriquece o que passa no filtro
    python 31_enriquecer_corpus.py --esperar 3600
    python 31_enriquecer_corpus.py --limite 5   ensaio curto

POR QUE ISTO EXISTE
  O corpus guarda o mínimo que a coleta trouxe: órgão, UF, modalidade, objeto e
  número de controle. Falta o que decide prioridade — **prazo**, valor estimado,
  situação — e sem prazo o mapa não ordena por urgência, que é como a área de
  negócio olha.

  E esses campos NÃO dependem da API de documentos. O PNCP tem três APIs
  independentes, e a que vive caindo é a `api/pncp/v1`, dos arquivos. Enquanto
  ela está fora, `api/consulta/v1` e `api/search` continuam respondendo — foi o
  que permitiu diagnosticar a queda como banco de dados, e não bloqueio.
  Ver [[Disponibilidade do PNCP]].

O QUE ELE NÃO FAZ
  Não baixa PDF. Não chama modelo. Só metadados, R$ 0,00 de API paga.
  O download dos documentos é o `28_baixar_licitacao.py`, e esse sim depende da
  API frágil.

IDEMPOTENTE
  Grava em `saidas/_corpus_enriquecido.json`, chaveado pelo número de controle.
  Rodar de novo só busca o que ainda não tem.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import escopo, pncp                                     # noqa: E402

SAIDAS = os.path.join(RAIZ, "saidas")
CORPUS = os.path.join(SAIDAS, "_corpus_escopo.json")
DESTINO = os.path.join(SAIDAS, "_corpus_enriquecido.json")

RE_CONTROLE = re.compile(r"^(\d{14})-\d+-(\d+)/(\d{4})$")

# Campos que interessam, e por quê. A lista é curta de propósito: guardar o
# retorno inteiro encheria o arquivo de coisa que ninguém lê e esconderia o
# que importa.
CAMPOS = {
    "dataEncerramentoProposta": "prazo",        # ordena o painel
    "dataAberturaProposta": "abertura",
    "valorTotalEstimado": "valor_estimado",     # dimensiona o lance
    "situacaoCompraNome": "situacao",           # aberta, revogada, anulada
    "processo": "processo",
    "numeroCompra": "numero",
    "linkSistemaOrigem": "link_origem",
    "informacaoComplementar": "complemento",
}


def barra(t: str) -> None:
    print("\n" + "=" * 92 + "\n  %s\n" % t + "=" * 92)


class LimiteExcedido(RuntimeError):
    """429 da consulta/v1 — passa sozinho, ao contrário do 503."""


def buscar(controle: str, timeout: int = 40) -> dict | None:
    """
    Metadados de uma contratação pela `consulta/v1`.

    O endpoint por órgão/ano/sequencial vive na MESMA base da API de documentos,
    então cai junto. Este usa a base de consulta, que é serviço separado.
    """
    m = RE_CONTROLE.match(controle.strip())
    if not m:
        return None
    cnpj, seq, ano = m.group(1), str(int(m.group(2))), m.group(3)
    url = ("https://pncp.gov.br/api/consulta/v1/orgaos/%s/compras/%s/%s"
           % (cnpj, ano, seq))
    req = urllib.request.Request(
        url, headers={"User-Agent": pncp.USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # A `consulta/v1` TEM limite de ritmo — e não diz qual.
        #
        # O 429 vem como PÁGINA HTML ("Limite de requisições excedido. Aguarde
        # alguns instantes"), sem `Retry-After` e sem nenhum `X-RateLimit-*`.
        # Então não há número a obedecer: só recuar e tentar de novo.
        #
        # Distinguir 429 de 503 importa: o 503 é o banco fora e pode durar dias;
        # o 429 passa em segundos. Tratar os dois igual faria o script desistir
        # de algo que ia funcionar na tentativa seguinte.
        if e.code == 429:
            raise LimiteExcedido("limite de requisições da consulta/v1") from e
        raise


def enxugar(bruto: dict) -> dict:
    saida = {}
    for origem, destino in CAMPOS.items():
        v = bruto.get(origem)
        if v not in (None, "", []):
            saida[destino] = v
    org = bruto.get("orgaoEntidade") or {}
    if org.get("razaoSocial"):
        saida["orgao_razao_social"] = org["razaoSocial"]
    uni = bruto.get("unidadeOrgao") or {}
    if uni.get("municipioNome"):
        saida["municipio"] = uni["municipioNome"]
    if uni.get("ufSigla"):
        saida["uf"] = uni["ufSigla"]
    return saida


def main() -> int:
    ap = argparse.ArgumentParser(description="Enriquece o corpus pelas APIs vivas")
    ap.add_argument("--limite", type=int, default=None)
    ap.add_argument("--pausa", type=float, default=1.0)
    ap.add_argument("--esperar", type=int, default=0,
                    help="segundos insistindo enquanto a API estiver fora")
    ap.add_argument("--intervalo", type=int, default=300)
    a = ap.parse_args()

    corpus = json.load(io.open(CORPUS, encoding="utf-8"))
    alvos = [r for r in corpus["registros"]
             if escopo.avaliar(r.get("objeto") or "")[0]]

    feito = {}
    if os.path.isfile(DESTINO):
        feito = json.load(io.open(DESTINO, encoding="utf-8")).get("registros", {})

    faltam = [r for r in alvos if (r.get("controle") or "") not in feito]
    if a.limite:
        faltam = faltam[:a.limite]

    barra("ENRIQUECIMENTO — %d de folha, %d já feitas, %d a buscar"
          % (len(alvos), len(feito), len(faltam)))
    print("  fonte: api/consulta/v1 (independente da api/pncp/v1, que está fora)")
    print("  custo: R$ 0,00 — metadados, sem download e sem modelo\n")

    if not faltam:
        print("  nada a fazer.")
        return 0

    # Sonda: se a API está fora, descobrir AGORA e não em 112 erros seguidos.
    limite = time.time() + a.esperar
    while True:
        try:
            buscar(faltam[0]["controle"], timeout=30)
            break
        except LimiteExcedido:
            print("  limite de ritmo na sonda — 10s", flush=True)
            time.sleep(10)
        except (urllib.error.URLError, OSError, ValueError) as e:
            if time.time() >= limite:
                print("  API de consulta indisponível: %s" % e)
                print("  Nada gravado. Rode de novo quando ela voltar —")
                print("  o arquivo é idempotente e retoma de onde parou.")
                return 1
            print("  consulta fora — nova tentativa em %ds" % a.intervalo, flush=True)
            time.sleep(a.intervalo)

    seguidas = 0
    pausa = a.pausa
    for i, r in enumerate(faltam, 1):
        ctrl = r.get("controle")
        for tentativa in range(1, 6):
            try:
                bruto = buscar(ctrl)
                dados = enxugar(bruto or {})
                feito[ctrl] = dados
                seguidas = 0
                prazo = dados.get("prazo", "—")
                print("  [%3d/%d] %-40s prazo %s"
                      % (i, len(faltam), (r.get("orgao") or "")[:40], str(prazo)[:19]))
                break
            except LimiteExcedido:
                # Recuo exponencial E pausa maior daqui em diante: se bateu no
                # limite uma vez, o ritmo atual está errado para o resto do lote.
                espera = 5 * (2 ** (tentativa - 1))
                pausa = min(pausa * 1.5, 5.0)
                print("  [%3d/%d] limite de ritmo — %ds (ritmo novo: %.1fs)"
                      % (i, len(faltam), espera, pausa), flush=True)
                time.sleep(espera)
            except Exception as e:                                # noqa: BLE001
                seguidas += 1
                print("  [%3d/%d] %-40s FALHOU: %s"
                      % (i, len(faltam), (r.get("orgao") or "")[:40], str(e)[:40]))
                break
        if seguidas >= 8:
            print("\n  DISJUNTOR: 8 falhas seguidas — a API caiu. Gravando o parcial.")
            break
        # Gravar a cada volta: um lote de 104 contra API instável não pode
        # perder 100 acertos porque o 101 falhou.
        if i % 10 == 0:
            json.dump({"proposito": "parcial", "registros": feito},
                      io.open(DESTINO, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        time.sleep(pausa)

    json.dump({"proposito": "Metadados do PNCP por número de controle. "
                            "Fonte: api/consulta/v1. Complementa _corpus_escopo.json.",
               "atualizado": time.strftime("%Y-%m-%d %H:%M"),
               "registros": feito},
              io.open(DESTINO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    com_prazo = sum(1 for v in feito.values() if v.get("prazo"))
    print("\n  gravado: %s" % os.path.relpath(DESTINO, RAIZ))
    print("  %d registros, %d com prazo" % (len(feito), com_prazo))
    print("\n  Depois: python 30_mapa_editais.py  (o mapa passa a ordenar por prazo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
