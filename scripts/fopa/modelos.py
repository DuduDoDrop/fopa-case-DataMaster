# -*- coding: utf-8 -*-
"""
Camada de modelo — configuração, provedores e contabilidade de custo.

POR QUE UM PROVEDOR ABSTRATO
  Duas razões, ambas de engenharia:
  1. Testar o encanamento (montagem de prompt, parsing, verificação, planilha) sem
     gastar token. O `ProvedorSimulado` é determinístico e roda em CI.
  2. Trocar de modelo por agente sem tocar no código do agente. A ADR-009 define
     modelo diferente por criticidade; isso só é barato se a escolha for injetada.

Escolha por agente (ADR-009): o custo do modelo é irrelevante frente ao valor em jogo,
então otimiza-se por acurácia no extrator e por custo onde o erro é barato e recuperável.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

from . import segredos

segredos.carregar()          # o .env vale para todos os provedores, e antes deles

# ---------------------------------------------------------------- catálogo
# Preços de tabela, USD por milhão de tokens.
#
# Os três da Claude são preço de tabela conferido. Os do OpenAI NÃO estão aqui
# com número inventado: o projeto tem uma regra explícita de não escrever valor
# sem fonte, e um preço errado no catálogo é pior que preço nenhum — ele
# contamina a planilha de custo, o benchmark e a apresentação dos resultados.
# Rode `26_modelos_openai.py` para listar os modelos que a conta de fato tem e
# preencha `FOPA_PRECO_OPENAI_ENTRADA` / `_SAIDA` no `.env` com a tabela oficial.
PRECOS = {
    # O Opus 5.5 entrou em 26/09/2026 pela tabela
    # oficial da Anthropic (US$ 4 / 20 por milhao, cache a 0,20): sem preco, o custo
    # sairia "preco nao configurado" e o teto do dia nao protegeria nada. Ainda nao ha
    # fatura dele -- o `32_custo_real.py` confere na primeira (cost_report por modelo).
    "claude-opus-5-5":  {"entrada": 4.00, "saida": 20.00, "contexto": 1_000_000},
    "claude-opus-5":    {"entrada": 5.00, "saida": 25.00, "contexto": 1_000_000},
    "claude-sonnet-5":  {"entrada": 2.00, "saida": 10.00, "contexto": 1_000_000},
    "claude-haiku-4-5": {"entrada": 1.00, "saida":  5.00, "contexto":   200_000},
    # OpenAI. Entraram em 23/09/2026 com DUAS fontes concordando:
    #   tabela  https://developers.openai.com/api/docs/pricing
    #   fatura  /v1/organization/costs dividido por /v1/organization/usage,
    #           conferido pelo 58_preco_openai.py (bate dentro de 0,01%).
    # O contexto nao esta aqui porque nao foi medido nem conferido -- e o
    # catalogo nao usa esse campo para nada hoje.
    "gpt-5.6-sol": {"entrada": 4.00, "saida": 20.00},
    "gpt-6-sol":   {"entrada": 2.00, "saida": 10.00},
    "gpt-6-astra": {"entrada": 10.00, "saida": 50.00},
    "gpt-6-luna":  {"entrada": 0.10, "saida":  0.50},
}

# Multiplicadores do cache sobre o preco de entrada. Os dois provedores
# cobram igual, e os dois numeros tem fonte:
#   escrita 1,25x -- Anthropic: platform.claude.com/docs/en/build-with-claude/
#                    prompt-caching (janela de 5 min); OpenAI: derivado da
#                    fatura pelo 58_preco_openai.py, 1,25x nos QUATRO modelos.
#   leitura 0,10x -- Anthropic: mesma pagina; OpenAI: tabela oficial
#                    (US$ 0,40 de leitura contra US$ 4,00 de entrada).
# Ate 23/09/2026 o `usd` cobrava a escrita a 1,00x, e portanto SUBESTIMAVA
# todo custo com cache em 25%.
CACHE_ESCRITA = 1.25
CACHE_LEITURA = 0.10

# Preço do modelo OpenAI, quando informado. Sem isso o custo sai 0,00 e o
# relatório diz "preço não configurado" em vez de mentir um número.
_PRECO_OPENAI_ENTRADA = os.environ.get("FOPA_PRECO_OPENAI_ENTRADA")
_PRECO_OPENAI_SAIDA = os.environ.get("FOPA_PRECO_OPENAI_SAIDA")

USD_BRL = float(os.environ.get("FOPA_USD_BRL", "5.10"))

# ADR-009 — modelo por agente
MODELO_EXTRATOR = os.environ.get("FOPA_MODELO_EXTRATOR", "claude-opus-5")
MODELO_CLASSIFICADOR = os.environ.get("FOPA_MODELO_CLASSIFICADOR", "claude-haiku-4-5")
MODELO_REVISOR = os.environ.get("FOPA_MODELO_REVISOR", "claude-sonnet-5")
# O Verificador não usa modelo. É determinístico por princípio (ADR-004).

# Plano B: se a Claude API cair no meio de uma janela de prazo, o pipeline não
# pode parar — licitação tem data de sessão e ela não espera fornecedor de API.
#
# O identificador saiu da CONTA, via `26_modelos_openai.py` (/v1/models), e não
# de memória. Valeu a pena: o identificador presumido era `gpt-5.6`, que NÃO existe — a conta tem
# `gpt-5.6-sol`, `-luna` e `-terra`. Um identificador presumido falha com
# "model not found", que não sugere o certo, e custa uma hora de quem for usar.
MODELO_OPENAI = os.environ.get("FOPA_MODELO_OPENAI", "gpt-5.6-sol")


@dataclass
class Uso:
    entrada: int = 0
    saida: int = 0
    cache_escrita: int = 0
    cache_leitura: int = 0
    # Subconjunto de `saida`, não parcela adicional: já está cobrado ali. Fica
    # visível porque é o único gasto que não aparece no texto da resposta.
    raciocinio: int = 0
    chamadas: int = 0
    segundos: float = 0.0
    modelo: str = ""

    def somar(self, outro: "Uso") -> None:
        self.entrada += outro.entrada
        self.saida += outro.saida
        self.cache_escrita += outro.cache_escrita
        self.cache_leitura += outro.cache_leitura
        self.raciocinio += outro.raciocinio
        self.chamadas += outro.chamadas
        self.segundos += outro.segundos
        self.modelo = self.modelo or outro.modelo

    @property
    def preco_conhecido(self) -> bool:
        """
        False quando o custo sai 0,00 por FALTA DE TABELA, não por ser grátis.

        A distincao existe porque as duas situacoes gravam o mesmo 0,00 e
        significam o oposto. O simulado entra como conhecido: ele custa zero de
        verdade, e registrar `null` ali seria dizer "desconhecido" sobre a unica
        execucao cujo custo e conhecido com certeza.
        """
        if self.modelo == "simulado":
            return True
        return self.modelo in PRECOS or (
            self.modelo.startswith("gpt") and _PRECO_OPENAI_ENTRADA is not None)

    @property
    def usd(self) -> float:
        p = PRECOS.get(self.modelo)
        if not p and self.modelo.startswith("gpt") and _PRECO_OPENAI_ENTRADA:
            p = {"entrada": float(_PRECO_OPENAI_ENTRADA),
                 "saida": float(_PRECO_OPENAI_SAIDA or _PRECO_OPENAI_ENTRADA)}
        if not p:
            return 0.0
        return (self.entrada * p["entrada"]
                + self.cache_escrita * p["entrada"] * CACHE_ESCRITA
                + self.cache_leitura * p["entrada"] * CACHE_LEITURA
                + self.saida * p["saida"]) / 1_000_000

    @property
    def brl(self) -> float:
        return self.usd * USD_BRL

    def __str__(self) -> str:
        custo = ("US$ %.4f (R$ %.3f)" % (self.usd, self.brl) if self.preco_conhecido
                 else "custo: preço não configurado para %s" % self.modelo)
        raciocinio = (" (raciocínio %s)" % f"{self.raciocinio:,}".replace(",", ".")
                      if self.raciocinio else "")
        return ("%s | %d chamada(s) | entrada %s tok (cache %s) | saída %s tok%s | "
                "%.1fs | %s"
                % (self.modelo or "?", self.chamadas, f"{self.entrada:,}".replace(",", "."),
                   f"{self.cache_leitura:,}".replace(",", "."),
                   f"{self.saida:,}".replace(",", "."), raciocinio, self.segundos, custo))


class ErroModelo(RuntimeError):
    pass


# ---------------------------------------------------------------- mensagem do usuário
def texto_usuario(usuario) -> str:
    """A mensagem como texto único: `(prefixo, sufixo)` da ordem nova (extrator.montar_partes) ou a string."""
    if isinstance(usuario, (tuple, list)):
        return "\n\n".join(usuario)
    return usuario


def conteudo_claude(usuario):
    """
    O `content` da mensagem na Claude API — o mesmo no SDK e no corpo que o n8n manda (api/extracao.py).

    Em duas partes (v3.1), o prefixo — licitação + documentos, igual nos lotes — leva `cache_control`: o 1º lote
    grava o documento no cache e os outros o leem. É o segundo breakpoint (o primeiro é o sistema). Texto único
    segue como sempre, só com o sistema em cache.
    """
    if isinstance(usuario, (tuple, list)):
        prefixo, sufixo = usuario
        return [{"type": "text", "text": prefixo, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": sufixo}]
    return usuario


# ---------------------------------------------------------------- provedores
class Provedor:
    """Contrato mínimo: recebe sistema + usuário + esquema, devolve dict + uso."""

    nome = "abstrato"

    def responder_json(self, sistema: str, usuario: str, esquema: dict,
                       modelo: str, max_tokens: int = 16000,
                       effort: str = "high") -> tuple[dict, Uso]:
        raise NotImplementedError


class ProvedorClaude(Provedor):
    """
    Claude API com structured outputs.

    Decisões de configuração, com motivo:
      - thinking adaptativo: a tarefa exige raciocinar sobre documentos que se
        contradizem (RN-14) e decidir precedência. Sem raciocínio o modelo tende a
        pegar a primeira ocorrência.
      - effort high: extração com citação literal é sensível a qualidade; o custo
        extra é irrelevante frente ao valor da resposta (ADR-009).
      - structured outputs: garante o JSON do esquema sem pós-processamento frágil.
      - prompt caching no prefixo: a instrução de sistema é estável e o documento é
        o que varia; o breakpoint fica entre os dois.
      - streaming: 17 respostas com trecho literal é saída longa; sem stream, o
        timeout do SDK pode estourar.
    """

    nome = "claude"

    def __init__(self, api_key: str | None = None):
        try:
            import anthropic
        except ImportError as e:
            raise ErroModelo("SDK não instalado: pip install anthropic") from e
        chave = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not chave:
            raise ErroModelo(
                "ANTHROPIC_API_KEY não definida. Defina a variável de ambiente ou use "
                "--simulado para rodar o pipeline sem chamar o modelo.")
        self._anthropic = anthropic
        self.cliente = anthropic.Anthropic(api_key=chave)

    def responder_json(self, sistema: str, usuario: str, esquema: dict,
                       modelo: str, max_tokens: int = 16000,
                       effort: str = "high") -> tuple[dict, Uso]:
        t0 = time.time()
        # Haiku 4.5 é de geração anterior: não aceita thinking adaptativo nem effort.
        # Mantê-lo no harness exige tratar essa diferença aqui, não no chamador.
        moderno = not modelo.startswith("claude-haiku-4-5")
        extras: dict = {}
        if moderno:
            extras["thinking"] = {"type": "adaptive"}
            extras["output_config"] = {
                "effort": effort,
                "format": {"type": "json_schema", "schema": esquema}}
        else:
            extras["output_config"] = {
                "format": {"type": "json_schema", "schema": esquema}}
        try:
            with self.cliente.messages.stream(
                model=modelo,
                max_tokens=max_tokens,
                system=[{
                    "type": "text",
                    "text": sistema,
                    "cache_control": {"type": "ephemeral"},   # prefixo estável
                }],
                messages=[{"role": "user", "content": conteudo_claude(usuario)}],
                **extras,
            ) as fluxo:
                msg = fluxo.get_final_message()
        except Exception as e:                                  # noqa: BLE001
            raise ErroModelo("falha na chamada ao modelo: %s" % e) from e

        if getattr(msg, "stop_reason", None) == "refusal":
            raise ErroModelo("o modelo recusou a requisição (stop_reason=refusal)")

        texto = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            dados = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ErroModelo("resposta não é JSON válido: %s" % texto[:400]) from e

        u = msg.usage
        uso = Uso(
            entrada=getattr(u, "input_tokens", 0) or 0,
            saida=getattr(u, "output_tokens", 0) or 0,
            cache_escrita=getattr(u, "cache_creation_input_tokens", 0) or 0,
            cache_leitura=getattr(u, "cache_read_input_tokens", 0) or 0,
            chamadas=1, segundos=time.time() - t0, modelo=modelo)
        return dados, uso


_ESPERA = re.compile(r"try again in (\d+(?:\.\d+)?)(ms|s)\b", re.I)


def _segundos_sugeridos(mensagem: str) -> float | None:
    """
    O provedor DIZ quanto esperar ("Please try again in 20s"). Obedecer o número
    dele é melhor que inventar um: backoff exponencial cego ou dorme demais, ou
    volta cedo e queima outra tentativa do mesmo minuto.
    """
    m = _ESPERA.search(mensagem or "")
    if not m:
        return None
    valor = float(m.group(1))
    return valor / 1000 if m.group(2).lower() == "ms" else valor


class ProvedorOpenAI(Provedor):
    """
    OpenAI como provedor alternativo — mesmo contrato, mesmo esquema JSON.

    POR QUE EXISTE
      Redundância de fornecedor. O pipeline responde a prazo de licitação, que
      não se move porque uma API está fora do ar; foi exatamente o que aconteceu
      com a API de documentos do PNCP durante dias deste projeto. Um segundo
      provedor transforma uma indisponibilidade em degradação, não em parada.

    POR QUE A RESPONSES API, E NÃO CHAT COMPLETIONS
      Os modelos de raciocínio da família gpt-5 vivem em `/v1/responses`. Ali o
      limite de saída se chama `max_output_tokens` — `max_tokens` simplesmente
      não existe, e mandá-lo devolve 400. O esforço de raciocínio entra em
      `reasoning.effort`, e o structured output em `text.format`, não em
      `response_format`. São quatro nomes diferentes do que a Claude API usa;
      é para isolar essas quatro diferenças que esta classe existe.

    O QUE MUDA NA PRÁTICA, E O QUE NÃO MUDA
      Não muda nada para o resto do pipeline: entra o mesmo `ESQUEMA_LOTE`, sai o
      mesmo dicionário de respostas, e o Verificador continua determinístico —
      ele confere o trecho literal contra a página, e não tem a menor ideia de
      qual modelo escreveu. Essa é a propriedade que torna a troca de fornecedor
      barata: a validação nunca dependeu de quem respondeu.

      Muda o cache: aqui ele é automático por prefixo, sem `cache_control`. Por
      isso não há breakpoint a declarar — só a leitura de `cached_tokens` na
      contabilidade, para que a comparação de custo continue honesta.
    """

    nome = "openai"

    def __init__(self, api_key: str | None = None):
        try:
            import openai
        except ImportError as e:
            raise ErroModelo("SDK não instalado: pip install openai") from e
        chave = api_key or segredos.obter("OPENAI_API_KEY")
        if not chave:
            raise ErroModelo(
                "OPENAI_API_KEY não definida. Grave-a em projeto-fopa/.env (o arquivo "
                "está no .gitignore) ou exporte a variável de ambiente.")
        self._openai = openai
        # `max_retries=0`: o retry fica AQUI, onde se pode distinguir ritmo de
        # crédito e obedecer ao tempo que o provedor sugere. Deixar os dois
        # ligados multiplicaria as tentativas sem que nenhum dos dois soubesse
        # do outro.
        self.cliente = openai.OpenAI(api_key=chave, max_retries=0)
        self.tentativas = int(os.environ.get("FOPA_OPENAI_TENTATIVAS", "6"))

    def responder_json(self, sistema: str, usuario: str, esquema: dict,
                       modelo: str, max_tokens: int = 16000,
                       effort: str = "high") -> tuple[dict, Uso]:
        t0 = time.time()
        # DOIS 429 DIFERENTES, e confundi-los custa caro nas duas direções.
        #
        #   rate_limit_exceeded     ritmo. Passa sozinho. Esperar RESOLVE.
        #   insufficient_quota      crédito. Não passa. Esperar só queima tempo
        #                           e, num lote de 11 licitações, transforma uma
        #                           falha imediata em meia hora de nada.
        #
        # A conta usada no desenvolvimento está em 3 RPM, e uma licitação gasta
        # exatamente 3 requisições — o limite é atingido na segunda licitação,
        # sempre. Sem isto aqui o provedor não serve para lote nenhum.
        espera_padrao = 20.0
        for tentativa in range(1, self.tentativas + 1):
            try:
                resp = self.cliente.responses.create(
                    model=modelo,
                    instructions=sistema,
                    input=texto_usuario(usuario),
                    max_output_tokens=max_tokens,
                    reasoning={"effort": effort},
                    text={"format": {"type": "json_schema",
                                     "name": "respostas_fopa",
                                     "schema": esquema,
                                     "strict": True}},
                )
                break
            except self._openai.RateLimitError as e:            # noqa: PERF203
                texto_erro = str(e)
                if "insufficient_quota" in texto_erro or "credit_balance" in texto_erro:
                    raise ErroModelo(
                        "a conta está sem crédito — esperar não resolve: %s"
                        % texto_erro) from e
                if tentativa == self.tentativas:
                    raise ErroModelo(
                        "limite de ritmo persistiu por %d tentativas: %s"
                        % (self.tentativas, texto_erro)) from e
                # O provedor diz quanto esperar; só se ele não disser é que
                # a espera dobra por conta própria.
                pausa = _segundos_sugeridos(texto_erro)
                if pausa is None:
                    pausa = espera_padrao
                    espera_padrao *= 2
                pausa += 1.0                                     # margem do relógio
                print("   limite de ritmo — aguardando %.0fs (tentativa %d de %d)"
                      % (pausa, tentativa, self.tentativas), flush=True)
                time.sleep(pausa)
            except Exception as e:                              # noqa: BLE001
                raise ErroModelo("falha na chamada ao modelo: %s" % e) from e

        # Truncar por limite de saída é silencioso: devolve JSON pela metade, e
        # JSON pela metade vira "resposta não é JSON válido" — um erro que aponta
        # para o lugar errado. Detectar aqui custa três linhas.
        if getattr(resp, "status", None) == "incomplete":
            motivo = getattr(getattr(resp, "incomplete_details", None), "reason", "?")
            raise ErroModelo("resposta truncada pelo provedor (motivo: %s); "
                             "aumente max_tokens" % motivo)

        texto = (getattr(resp, "output_text", None) or "").strip()
        if not texto:
            raise ErroModelo("o modelo não devolveu texto (status=%s)"
                             % getattr(resp, "status", "?"))
        try:
            dados = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ErroModelo("resposta não é JSON válido: %s" % texto[:400]) from e

        # A resposta NÃO traz preço — conferido: `ResponseUsage` tem apenas
        # input_tokens, output_tokens, total_tokens e os dois blocos de detalhe;
        # e o objeto `Model` de /v1/models traz só id, created, object, owned_by
        # e shutdown_date. Nenhum dos dois carrega custo. O preço por milhão de
        # tokens continua vindo do `.env`, da tabela oficial do fornecedor.
        u = getattr(resp, "usage", None)
        entradas = getattr(u, "input_tokens_details", None)
        saidas = getattr(u, "output_tokens_details", None)
        cache = getattr(entradas, "cached_tokens", 0) or 0
        escrita = getattr(entradas, "cache_write_tokens", 0) or 0
        entrada = getattr(u, "input_tokens", 0) or 0
        uso = Uso(
            # `input_tokens` do OpenAI JÁ inclui os lidos E os gravados no cache; a
            # Claude API os reporta à parte. Descontar os dois é o que mantém as
            # colunas da planilha comparáveis entre provedores — e o que impede a
            # gravação de ser cobrada duas vezes (1,0× na entrada + 1,25× no cache).
            # A fatura de 23/09 decompõe assim: 321 novos + 122.407 gravados +
            # 54.376 lidos (achado da medição antes/depois da v3.1, 28/09).
            entrada=max(entrada - cache - escrita, 0),
            # `output_tokens` já inclui os de raciocínio, e eles são cobrados
            # como saída — então NÃO se soma nada aqui. O número fica à
            # parte só para a análise: token de raciocínio é invisível no texto
            # e, quando o custo sobe sem a resposta crescer, é ele o motivo.
            saida=getattr(u, "output_tokens", 0) or 0,
            raciocinio=getattr(saidas, "reasoning_tokens", 0) or 0,
            cache_escrita=escrita,
            cache_leitura=cache,
            chamadas=1, segundos=time.time() - t0, modelo=modelo)
        return dados, uso


class ProvedorSimulado(Provedor):
    """
    Provedor determinístico, sem rede.

    NÃO é um modelo: é um localizador de trechos por regex sobre o próprio contexto.
    Serve para (a) exercitar todo o encanamento em CI e (b) dar um PISO de comparação
    no harness de avaliação — se o modelo real não superar o regex, o modelo não está
    agregando valor e isso precisa aparecer na medição.
    """

    nome = "simulado"

    def __init__(self, respostas: dict | None = None):
        self.respostas = respostas or {}

    def responder_json(self, sistema: str, usuario: str, esquema: dict,
                       modelo: str, max_tokens: int = 16000,
                       effort: str = "high") -> tuple[dict, Uso]:
        import re
        from .questionario import PERGUNTAS, NAO_LOCALIZADO

        t0 = time.time()
        # A última página termina no fim do bloco de documentos, não no fim da mensagem: na ordem nova (v3.1) as
        # perguntas vêm depois, e o simulado as leria como texto da página.
        paginas = re.findall(
            r"=== ARQUIVO (.+?) \| PÁGINA (\d+) ===\n(.*?)(?=\n=== ARQUIVO |\n+=== FIM DOS DOCUMENTOS ===|\Z)",
            texto_usuario(usuario), re.S)
        respostas = []
        for p in PERGUNTAS:
            if p.id in self.respostas:
                respostas.append(dict(self.respostas[p.id], id=p.id))
                continue
            achou = None
            for arq, num, txt in paginas:
                baixo = txt.lower()
                if sum(1 for t in p.termos if t.lower() in baixo) >= 2:
                    idx = min((baixo.find(t.lower()) for t in p.termos
                               if t.lower() in baixo), default=-1)
                    if idx >= 0:
                        trecho = re.sub(r"\s+", " ", txt[idx:idx + 220]).strip()
                        achou = (arq, int(num), trecho)
                        break
            if achou:
                respostas.append({
                    "id": p.id, "resposta": achou[2][:180], "arquivo": achou[0],
                    "pagina": achou[1], "trecho_literal": achou[2],
                    "conflito": None, "confianca": "baixa"})
            else:
                respostas.append({
                    "id": p.id, "resposta": NAO_LOCALIZADO, "arquivo": None,
                    "pagina": None, "trecho_literal": None,
                    "conflito": None, "confianca": "baixa"})
        return ({"respostas": respostas},
                Uso(chamadas=1, segundos=time.time() - t0, modelo="simulado"))


PROVEDORES = {"claude": ProvedorClaude,
              "openai": ProvedorOpenAI,
              "simulado": ProvedorSimulado}


def modelo_padrao(provedor: str) -> str:
    """O modelo do extrator para cada provedor — o chamador não precisa saber."""
    return {"openai": MODELO_OPENAI, "simulado": "simulado"}.get(
        provedor, MODELO_EXTRATOR)


def obter_provedor(simulado: bool = False, api_key: str | None = None,
                   provedor: str = "claude") -> Provedor:
    """
    Fábrica. `simulado=True` continua valendo e vence — os scripts antigos e o
    Dockerfile passam esse argumento, e quebrá-los para ganhar simetria de API
    seria trocar utilidade por estética.
    """
    if simulado:
        return ProvedorSimulado()
    classe = PROVEDORES.get(provedor)
    if classe is None:
        raise ErroModelo("provedor desconhecido: %r (use %s)"
                         % (provedor, ", ".join(sorted(PROVEDORES))))
    if classe is ProvedorSimulado:
        return ProvedorSimulado()
    return classe(api_key=api_key)


__all__ = ["Provedor", "ProvedorClaude", "ProvedorOpenAI", "ProvedorSimulado",
           "obter_provedor", "modelo_padrao", "PROVEDORES",
           "Uso", "ErroModelo", "PRECOS", "USD_BRL",
           "CACHE_ESCRITA", "CACHE_LEITURA",
           "MODELO_EXTRATOR", "MODELO_CLASSIFICADOR", "MODELO_REVISOR",
           "MODELO_OPENAI"]
