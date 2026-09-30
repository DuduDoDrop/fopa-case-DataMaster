# -*- coding: utf-8 -*-
"""
Cliente da API do PNCP — endpoints validados ao vivo em 22/09/2026.

Regras que este módulo faz cumprir (ver Fopa-v2/00-Case/Regras de negócio.md):
  RN-24  deduplicação por numero_controle_pncp; o ano dele NÃO é o da publicação
  RN-25  ordenacao=-data NÃO ordena por data de publicação — não confiar
  RN-26  registrar SHA-256, origem e timestamp de cada arquivo
  RN-27  conduta: User-Agent identificável, rate limit conservador, backoff
  RN-07  sequencialDocumento tem buracos — nunca iterar de 1 a N

A API é pública, gratuita, sem cadastro (art. 54 da Lei 14.133/2021 + LAI).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass, field

BASE_BUSCA = "https://pncp.gov.br/api/search/"
BASE_PNCP = "https://pncp.gov.br/api/pncp/v1"
BASE_CONSULTA = "https://pncp.gov.br/api/consulta/v1"

# RN-27 — identificável, com propósito declarado. Nada de fingir ser navegador.
# Com contato (RN-27): um operador do PNCP que precise avisar algo tem para onde escrever.
USER_AGENT = "FOPA/0.1 (monitoramento de licitacoes de folha; estudo de viabilidade; contato: contato@exemplo.com)"

PAUSA = 0.5          # RN-27 — rate limit conservador
TENTATIVAS = 3
TIMEOUT = 60


class ErroPNCP(RuntimeError):
    """
    Falha de rede ou de HTTP contra o PNCP.

    Carrega `itens`: o que JA tinha sido lido quando a falha aconteceu. Uma
    busca que morre na pagina 4 leu tres paginas de verdade, e jogar as tres
    fora e perder dado que ja foi pago -- e que, no caso do monitor, pode ser
    a licitacao cujo prazo fecha amanha. Quem captura decide o que fazer com
    o parcial; o que nao pode e o parcial sumir em silencio.
    """

    def __init__(self, *args, itens: list | None = None, pagina: int = 0):
        super().__init__(*args)
        self.itens = itens or []
        self.pagina = pagina


# O `consulta/v1` TEM rate limit, e a espera que ele aceita foi medida.
#
# Durante 23/09/2026 o projeto registrou so `RemoteDisconnected` e
# `TimeoutError`, e a hipotese de rate limit foi retratada por escrito -- "nunca
# um 429, nunca um Retry-After". Sondando com pausa curta, o 429 apareceu:
#
#     pausa 0,5s  ->  9 chamadas OK, depois 429
#     pausa 1,5s  ->  7 chamadas OK, depois 429
#     pausa 3,0s  -> 12 chamadas OK, ZERO falha
#
# Entao ha limite, ele so nao se comunica de forma consistente: as vezes
# derruba a conexao, as vezes devolve 429, e NUNCA manda `Retry-After`. A
# retratacao estava certa sobre a evidencia daquele momento e errada sobre o
# mundo -- o que muda a conduta e sondar de novo, nao escolher entre as duas.
PAUSA_VARREDURA = 3.0      # medido, nao estimado
ESPERA_429 = 30.0          # sem Retry-After, so resta esfriar de verdade


def _get(url: str, timeout: int = TIMEOUT, vazio_ok: bool = False):
    """
    GET com backoff exponencial, e espera LONGA quando o servidor diz 429.

    Tratar 429 como erro de rede qualquer -- backoff de 1,5s e desistir em 3
    tentativas -- foi o que matou tres varreduras de recall seguidas, nas
    paginas 13, 15 e 2. Um limite de taxa nao se resolve tentando de novo
    rapido; resolve-se esperando.

    `vazio_ok`: 204 (sem corpo) e resposta, nao falha -- devolve None. E como o
    PNCP diz "nenhum" nos /termos de um contrato sem aditivo; sem isto o 204
    virava JSON invalido, tres tentativas e ErroPNCP.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    ultimo = None
    for tentativa in range(TENTATIVAS):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if vazio_ok and r.status == 204:
                    return None
                return json.load(r)
        except urllib.error.HTTPError as e:
            ultimo = e
            if e.code == 429 and tentativa < TENTATIVAS - 1:
                ra = e.headers.get("Retry-After") if e.headers else None
                espera = float(ra) if (ra or "").strip().isdigit() else ESPERA_429
                time.sleep(espera * (tentativa + 1))
                continue
            if tentativa < TENTATIVAS - 1:
                time.sleep(1.5 * (2 ** tentativa))
        except Exception as e:                       # noqa: BLE001
            ultimo = e
            if tentativa < TENTATIVAS - 1:
                time.sleep(1.5 * (2 ** tentativa))   # backoff exponencial
    raise ErroPNCP("falhou após %d tentativas: %s — %s" % (TENTATIVAS, url, ultimo))


def _baixar(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- busca
def buscar(termo: str, paginas: int = 1, tam: int = 50,
           tipo: str = "edital", status: str = "todos") -> list[dict]:
    """
    Busca textual — a mesma do site.

    RN-25: `ordenacao=-data` NÃO ordena por data de publicação. Testado em
    22/09/2026: as datas voltaram crescentes. Não existe "página 1 = mais
    recentes". Para janela de data use `consultar_por_publicacao`.
    """
    itens, _ = buscar_com_info(termo, paginas, tam, tipo, status)
    return itens


def buscar_com_info(termo: str, paginas: int = 1, tam: int = 50,
                    tipo: str = "edital", status: str = "todos"):
    """
    Igual ao `buscar`, mas devolve tambem quanto do resultado ficou de fora.

    O `api/search` DECLARA o tamanho do conjunto, no campo `total` da resposta.
    Medido em 23/09/2026, o termo "folha de pagamento instituicao bancaria"
    declara **1.204** resultados -- e o corpus le 10 paginas de 50, ou seja
    500: **42%**. O teto de paginacao nunca foi cego; o numero que o mede
    estava na resposta e ninguem lia.

    Isto nao e o mesmo defeito do `consulta/v1` (pagina curta no meio). Aqui as
    paginas vem cheias e o corte e LOCAL, deliberado. O que faltava era saber
    o tamanho do que se corta -- a diferenca entre "paro na pagina 10" e
    "vejo 42% e sei disso".
    """
    itens = []
    total = None
    lidas = 0
    for p in range(1, paginas + 1):
        q = urllib.parse.urlencode({
            "q": termo, "tipos_documento": tipo, "ordenacao": "-data",
            "pagina": p, "tam_pagina": tam, "status": status})
        try:
            d = _get(BASE_BUSCA + "?" + q)
        except ErroPNCP as e:
            # O QUE JA FOI LIDO VAI JUNTO DA EXCECAO.
            # Ate 23/09/2026 a falha na pagina 4 descartava as paginas 1 a 3.
            # Em uma execucao real do monitor isso jogou fora ~10 paginas das
            # tres buscas, e o relatorio saiu como se nada tivesse sido visto.
            raise ErroPNCP(str(e), itens=itens, pagina=p) from e
        if total is None:
            total = d.get("total")
        lote = d.get("items", [])
        itens.extend(lote)
        lidas += 1
        if len(lote) < tam:
            break
        time.sleep(PAUSA)
    cobertura = (100.0 * len(itens) / total) if total else None
    return itens, {"total_declarado": total, "paginas_lidas": lidas,
                   "lidos": len(itens),
                   "cobertura_pct": round(cobertura, 1) if cobertura else None,
                   "teto_atingido": lidas >= paginas}


def consultar_por_publicacao(data_inicial: str, data_final: str,
                             codigo_modalidade: int, pagina: int = 1,
                             tamanho: int = 500) -> dict:
    """Varredura determinística por janela de data. Datas no formato AAAAMMDD."""
    q = urllib.parse.urlencode({
        "dataInicial": data_inicial, "dataFinal": data_final,
        "codigoModalidadeContratacao": codigo_modalidade,
        "pagina": pagina, "tamanhoPagina": tamanho})
    return _get(BASE_CONSULTA + "/contratacoes/publicacao?" + q)


def varrer_publicacao(data_inicial: str, data_final: str, codigo_modalidade: int,
                      tamanho: int = 50, pausa: float | None = None,
                      max_paginas: int = 200):
    """
    Varre TODAS as paginas de uma janela, e nao para na primeira pagina curta.

    A ARMADILHA, MEDIDA EM 23/09/2026
      O `consulta/v1` devolve PAGINA CURTA NO MEIO do conjunto. Dispensas
      publicadas em 24/08/2026, `tamanhoPagina=50`:

          pag  1 ->  50 itens   (totalRegistros=3008, totalPaginas=61)
          pag  2 ->  20 itens   <- curta, e NAO e o fim
          pag  3 ->  50 itens
          ...
          pag 16, 22, 27, 28 -> curtas tambem

      Toda paginacao do mundo para na primeira pagina curta, porque e assim
      que uma API normal sinaliza o fim. Aqui isso entregava **70 de 3.008
      registros** -- 2,3%. Lendo ate a pagina 61: **2.878 distintos**, 41
      vezes mais.

      Pior: o numero de paginas entregues variava entre execucoes identicas
      (70 numa, 210 noutra), porque as curtas caem em lugares diferentes. Uma
      medicao que depende disso nao e reprodutivel.

      E o `totalPaginas` estava na resposta o tempo todo. O codigo nunca leu.

    QUANDO PARAR
      Pelo `totalPaginas` que a propria API declara; e, se ele nao vier, so
      depois de DUAS paginas vazias seguidas -- nunca por pagina curta.

    Devolve `(itens, info)`. `info` traz `total_registros`, `total_paginas`,
    `paginas_lidas`, `paginas_curtas` e `completa` -- quem consome PRECISA
    saber se leu tudo, porque denominador incompleto infla recall.
    """
    pausa = PAUSA_VARREDURA if pausa is None else pausa
    itens, vistos, curtas = [], set(), []
    total_reg = total_pag = None
    vazias, pag, erro = 0, 1, None
    while pag <= max_paginas:
        try:
            r = consultar_por_publicacao(data_inicial, data_final,
                                         codigo_modalidade, pagina=pag,
                                         tamanho=tamanho)
        except ErroPNCP as e:
            erro = str(e)
            break
        lote = (r or {}).get("data") or []
        if total_reg is None:
            total_reg = (r or {}).get("totalRegistros")
            total_pag = (r or {}).get("totalPaginas")
        if not lote:
            vazias += 1
            if vazias >= 2 or (total_pag and pag >= total_pag):
                break
        else:
            vazias = 0
            if len(lote) < tamanho:
                curtas.append(pag)
            for it in lote:
                c = it.get("numeroControlePNCP")
                if c and c in vistos:
                    continue
                if c:
                    vistos.add(c)
                itens.append(it)
        if total_pag and pag >= total_pag:
            break
        pag += 1
        time.sleep(pausa)
    lidas = pag - 1 if vazias else pag
    completa = bool(total_pag) and lidas >= total_pag and erro is None
    return itens, {"total_registros": total_reg, "total_paginas": total_pag,
                   "paginas_lidas": lidas, "paginas_curtas": curtas,
                   "completa": completa, "erro": erro}


def dedup(itens: list[dict]) -> list[dict]:
    """RN-24 — chave é numero_controle_pncp."""
    vistos = {}
    for it in itens:
        vistos[it.get("numero_controle_pncp")] = it
    return list(vistos.values())


# ---------------------------------------------------------------- identificação
RE_ITEM_URL = re.compile(r"/compras/(\d+)/(\d+)/(\d+)")


RE_CONTROLE = re.compile(r"^(\d{14})-\d+-(\d+)/(\d{4})$")


@dataclass
class Licitacao:
    cnpj: str
    ano: str
    seq: str
    bruto: dict = field(repr=False, default_factory=dict)

    @classmethod
    def de_item(cls, item: dict) -> "Licitacao | None":
        m = RE_ITEM_URL.match(item.get("item_url") or "")
        if not m:
            return None
        return cls(*m.groups(), bruto=item)

    @classmethod
    def de_controle(cls, controle: str) -> "Licitacao":
        """
        A partir de `07654321000199-1-000048/2026`.

        O numero de controle e a IDENTIDADE da licitacao (ADR-013), entao
        precisa haver um caminho direto dele para a API. Sem isto, qualquer
        script que parte do inventario tinha que re-descobrir a URL pelo
        `item_url` do resultado de busca — que nem sempre foi guardado.
        """
        m = RE_CONTROLE.match((controle or "").strip())
        if not m:
            raise ValueError("numero de controle fora do formato: %r" % controle)
        cnpj, seq, ano = m.groups()
        return cls(cnpj, ano, str(int(seq)), bruto={"numero_controle_pncp": controle})

    @property
    def controle(self) -> str:
        return self.bruto.get("numero_controle_pncp", "")

    @property
    def rotulo(self) -> str:
        return "%s/%s" % (self.bruto.get("municipio_nome"), self.bruto.get("uf"))

    @property
    def link(self) -> str:
        return "https://pncp.gov.br/app/editais/%s/%s/%s" % (self.cnpj, self.ano, self.seq)

    def _u(self, sufixo: str) -> str:
        return "%s/orgaos/%s/compras/%s/%s%s" % (BASE_PNCP, self.cnpj, self.ano, self.seq, sufixo)

    def arquivos(self) -> list[dict]:
        """RN-07 — devolve a lista da API; nunca iterar de 1 a N."""
        return _get(self._u("/arquivos"))

    def itens(self) -> list[dict]:
        r = _get(self._u("/itens"))
        return [r] if isinstance(r, dict) else r

    def resultados(self, numero_item: int) -> list[dict]:
        """O retorno pode vir objeto OU lista — normalizado aqui."""
        r = _get(self._u("/itens/%s/resultados" % numero_item))
        if r is None:
            return []
        return [r] if isinstance(r, dict) else r


# ---------------------------------------------------------------- download
@dataclass
class ArquivoBaixado:
    seq: int
    tipo: str
    titulo: str
    caminho: str
    bytes: int
    sha256: str
    baixado_em: str
    origem: str


def baixar_arquivo(doc: dict, destino: str) -> ArquivoBaixado:
    """RN-26 — todo arquivo baixado registra hash, origem e timestamp."""
    dados = _baixar(doc["url"])
    with open(destino, "wb") as f:
        f.write(dados)
    return ArquivoBaixado(
        seq=doc.get("sequencialDocumento"),
        tipo=doc.get("tipoDocumentoNome"),
        titulo=doc.get("titulo"),
        caminho=destino,
        bytes=len(dados),
        sha256=hashlib.sha256(dados).hexdigest(),
        baixado_em=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        origem=doc["url"])


def documento_vigente(arquivos: list[dict], tipo: str = "Edital") -> dict | None:
    """
    RN-04 — o vigente é o de MAIOR sequencialDocumento dentro do mesmo tipo.

    Caso real: São Lourenço do Sul tinha 3 arquivos 'Edital', todos ativos,
    e dois divergiam na Q5 ('valor estimado' × 'valor mínimo').
    """
    candidatos = [a for a in arquivos
                  if (a.get("tipoDocumentoNome") or "").strip() == tipo
                  and a.get("statusAtivo")]
    if not candidatos:
        return None
    return max(candidatos, key=lambda a: a.get("sequencialDocumento") or 0)


__all__ = ["buscar", "buscar_com_info", "consultar_por_publicacao",
           "varrer_publicacao",
           "dedup", "Licitacao",
           "PAUSA_VARREDURA", "baixar_arquivo", "documento_vigente", "ArquivoBaixado", "ErroPNCP",
           "USER_AGENT"]
