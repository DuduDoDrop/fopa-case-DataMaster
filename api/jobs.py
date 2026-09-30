# -*- coding: utf-8 -*-
"""
A máquina dos jobs longos do worker (plano, seção 6, parágrafo "Jobs").

POR QUE JOB E NÃO UMA CHAMADA SÍNCRONA
  Ler uma licitação com OCR levou até 183,5 s no acervo, e baixar 400 MB do
  PNCP pode levar mais. O HTTP Request do n8n tem timeout de 30 s para o
  worker, e o Cloudflare da nuvem corta em 100 s. Então `POST /jobs/*` só
  enfileira e devolve `202 {job_id}`; o n8n volta com `GET /jobs/{id}` num
  laço Wait → GET (seção 5, "Jobs longos"), nunca `resumeUrl`.

O ESTADO MORA NO BANCO, NÃO NA MEMÓRIA
  A fila em si é um `ThreadPoolExecutor` de `FOPA_JOBS_CONCORRENCIA` threads
  (OCR é CPU: mais threads que núcleos só disputaria o processador), mas o
  que o n8n consulta é a tabela `jobs`. Se o processo morrer, a memória some
  e a linha fica: por isso existe `recuperar_orfaos()`.

  DUAS FILAS (28/09): `ocr` (a de sempre, `FOPA_JOBS_CONCORRENCIA`) e `rede`,
  de 1 thread, para a rodada do histórico do W41. Ela passa quase o tempo
  todo esperando o PNCP; na mesma fila, ocupava a única vaga da EC2 e a
  esteira das 6h esperava atrás dela.

ARRANQUE: TODO JOB ATIVO É ÓRFÃO
  O worker é um processo só (um uvicorn, sem --workers). Quando ele nasce,
  nenhum job `queued`/`running` da tabela pode ser dele: todos são do
  processo que morreu. Até 28/09 o arranque só declarava os parados há mais
  de 30 min, e quem estava vivo no reinício ficava `running` para sempre
  (os 3 zumbis de 27/09 06:10). Enquanto a limpeza não termina, `submeter`
  espera, para ela nunca pegar um job do processo novo.

  Os status são os do CHECK da 008: queued → running → done | error. `done`,
  não `ok`: o banco é quem manda no vocabulário.

ERRO NUNCA SOME
  Exceção dentro do job vira `erro = {tipo, mensagem, rastro}` na linha e
  status `error`. Se nem isso der para gravar (banco caiu no meio), o erro vai
  para o stderr do container — um job "running" para sempre é pior que um
  órfão declarado, e o próximo arranque o declara.
"""
from __future__ import annotations

import datetime as _dt
import decimal
import json
import sys
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import banco, config

# Um job sem sinal de vida há 30 min foi abandonado por um reinício (plano,
# seção 6). O progresso de cada arquivo renova `atualizado_em`, então só um
# arquivo de mais de 30 min parado num passo só cairia aqui por engano — o
# teto de 600 páginas do 28 mantém isso longe.
ORFAO_MINUTOS = 30

STATUS_ATIVOS = ("queued", "running")

FILA_OCR = "ocr"
FILA_REDE = "rede"
FILAS = (FILA_OCR, FILA_REDE)

_trava = threading.Lock()
_executores: dict[str, ThreadPoolExecutor] = {}

# Aberto (set) fora da limpeza do arranque; `submeter` espera por ele. O prazo
# é folga para um banco lento, não para um travado: passado dele, enfileira.
_arranque_livre = threading.Event()
_arranque_livre.set()
ARRANQUE_ESPERA_S = 60.0


def _json_padrao(obj):
    # O resultado de um job vem de linhas do Postgres (Decimal, datetime) e do
    # pacote fopa (date). Virar texto é melhor que o job morrer na última linha
    # por não conseguir gravar o próprio resultado.
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    return str(obj)


def _jsonb(obj):
    if obj is None:
        return None
    return Jsonb(obj, dumps=lambda o: json.dumps(o, ensure_ascii=False, default=_json_padrao))


def _conectar():
    # autocommit: cada atualização de estado vale sozinha. O trabalho do job
    # abre a própria conexão; misturar os dois faria o progresso só aparecer
    # quando a transação do trabalho fechasse — tarde demais para o n8n.
    conn = banco.conectar()
    conn.autocommit = True
    conn.row_factory = dict_row
    return conn


def _executor_ativo(fila: str = FILA_OCR) -> ThreadPoolExecutor:
    if fila not in FILAS:
        raise ValueError("fila desconhecida: %r (use %s)" % (fila, ", ".join(FILAS)))
    with _trava:
        ex = _executores.get(fila)
        if ex is None:
            n = config.carregar().jobs_concorrencia if fila == FILA_OCR else 1
            ex = _executores[fila] = ThreadPoolExecutor(max_workers=n, thread_name_prefix="fopa-job-" + fila)
        return ex


def encerrar() -> None:
    """Desliga as filas (fim do processo). O que estava rodando vira órfão no próximo arranque."""
    with _trava:
        executores = list(_executores.values())
        _executores.clear()
    for ex in executores:
        ex.shutdown(wait=False, cancel_futures=True)


class Contexto:
    """O que a função do job recebe: o próprio id e um jeito de dar sinal de vida."""

    def __init__(self, job_id: str):
        self.job_id = job_id

    def progresso(self, **campos) -> None:
        """Grava o progresso e renova `atualizado_em`. Falhar aqui não derruba o job."""
        try:
            with _conectar() as conn:
                conn.execute("UPDATE jobs SET progresso = %s, atualizado_em = now() WHERE id = %s",
                             (_jsonb(campos), self.job_id))
        except Exception as e:                                    # noqa: BLE001
            print("[jobs] progresso de %s não gravado: %s" % (self.job_id, e), file=sys.stderr)


def _descrever_erro(e: BaseException) -> dict:
    rastro = traceback.format_exception(type(e), e, e.__traceback__)
    return {"tipo": type(e).__name__, "mensagem": str(e)[:4000] or repr(e)[:4000],
            "rastro": "".join(rastro)[-6000:]}


def _rodar(job_id: str, funcao: Callable[[Contexto], dict]) -> None:
    try:
        with _conectar() as conn:
            conn.execute("UPDATE jobs SET status = 'running', atualizado_em = now() WHERE id = %s",
                         (job_id,))
    except Exception as e:                                        # noqa: BLE001
        print("[jobs] %s não passou a running: %s" % (job_id, e), file=sys.stderr)
        return
    try:
        resultado = funcao(Contexto(job_id))
        status, result, erro = "done", resultado, None
    except BaseException as e:                                    # noqa: BLE001
        # BaseException também: SystemExit dentro de um script importado (o 28
        # tem `raise SystemExit`) não pode deixar a linha em `running`.
        status, result, erro = "error", None, _descrever_erro(e)
    try:
        with _conectar() as conn:
            # Sem `AND status = 'running'`: se outro processo declarou este job
            # órfão enquanto ele terminava, o resultado real vale mais que a
            # suposição.
            conn.execute("UPDATE jobs SET status = %s, result = %s, erro = %s, atualizado_em = now()"
                         " WHERE id = %s", (status, _jsonb(result), _jsonb(erro), job_id))
    except Exception as e:                                        # noqa: BLE001
        print("[jobs] %s terminou %s e não foi gravado: %s | erro do job: %s"
              % (job_id, status, e, erro), file=sys.stderr)


def submeter(tipo: str, controle: str | None, funcao: Callable[[Contexto], dict],
             deduplicar: bool = False, fila: str = FILA_OCR) -> tuple[str, bool]:
    """
    Grava o job como `queued` e o põe na fila. Devolve `(job_id, reaproveitado)`.

    `deduplicar=True`: se já há um job ativo do mesmo tipo para a mesma
    licitação, devolve o dele. O W20 pode redisparar uma licitação cujo job
    ainda roda (lease vencido, retentativa do n8n); duas leituras simultâneas
    fariam o mesmo OCR duas vezes para produzir a mesma leitura. Sem licitação
    (a rodada do histórico do W41), o job ativo do mesmo tipo é o mesmo job.

    `fila`: `ocr` (padrão) ou `rede` (ver a docstring do módulo).
    """
    ex = _executor_ativo(fila)                 # fila errada falha antes de gravar a linha
    if not _arranque_livre.wait(ARRANQUE_ESPERA_S):
        print("[jobs] a limpeza do arranque passou de %.0f s; enfileirando assim mesmo" % ARRANQUE_ESPERA_S,
              file=sys.stderr)
    with _conectar() as conn:
        with conn.transaction():
            if deduplicar:
                # A trava transacional por (tipo, controle) fecha a corrida de
                # dois POSTs no mesmo instante; ela se solta no COMMIT.
                conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("jobs:%s:%s" % (tipo, controle or ""),))
                ativo = conn.execute(
                    "SELECT id::text AS id FROM jobs WHERE tipo = %s AND controle IS NOT DISTINCT FROM %s"
                    " AND status IN ('queued', 'running')"
                    " AND atualizado_em > now() - make_interval(mins => %s)"
                    " ORDER BY criado_em DESC LIMIT 1", (tipo, controle, ORFAO_MINUTOS)).fetchone()
                if ativo:
                    return ativo["id"], True
            job_id = str(uuid.uuid4())
            conn.execute("INSERT INTO jobs (id, tipo, controle, status, progresso) VALUES (%s, %s, %s, 'queued', %s)",
                         (job_id, tipo, controle, _jsonb({"etapa": "na fila"})))
    ex.submit(_rodar, job_id, funcao)
    return job_id, False


def obter(job_id: str) -> dict | None:
    """A linha do job no formato do `GET /jobs/{id}`; None se não existe (ou não é uuid)."""
    try:
        uuid.UUID(str(job_id))
    except ValueError:
        return None
    with _conectar() as conn:
        return conn.execute(
            "SELECT id::text AS job_id, tipo, controle, status, progresso, result, erro,"
            " criado_em, atualizado_em FROM jobs WHERE id = %s", (str(job_id),)).fetchone()


def recuperar_orfaos(minutos: int | None = ORFAO_MINUTOS) -> int:
    """
    Declara `error` os jobs ativos sem sinal de vida há `minutos` (plano, seção 6);
    `minutos=None` declara todos os ativos — é o que o arranque usa.

    `queued` também: a fila é memória do processo; um job na fila de um
    processo que morreu nunca vai rodar. Devolve quantos foram declarados.
    """
    if minutos is None:
        mensagem = ("o processo do worker reiniciou com o job em andamento (todo job ativo no arranque é "
                    "de um processo que morreu); reenviar o POST")
        condicao, args = "", ()
    else:
        mensagem = ("sem sinal de vida há mais de %d min: o processo do worker reiniciou "
                    "com o job em andamento; reenviar o POST" % minutos)
        condicao, args = " AND atualizado_em < now() - make_interval(mins => %s)", (minutos,)
    erro = {"tipo": "JobOrfao", "mensagem": mensagem}
    with _conectar() as conn:
        linhas = conn.execute(
            "UPDATE jobs SET status = 'error', erro = %s, atualizado_em = now()"
            " WHERE status IN ('queued', 'running')" + condicao + " RETURNING id",
            (_jsonb(erro), *args)).fetchall()
    return len(linhas)


def recuperar_orfaos_no_arranque(espera_s: float = 10.0) -> None:
    """
    Declara órfão todo job ativo (ver "ARRANQUE" no topo), sem nunca impedir o worker de subir.

    Numa thread com prazo: o `/health` tem de responder mesmo com o banco fora
    (é ele que diz ao W00 o que caiu), e um `connect` para um host que não
    responde pode travar pelo timeout de TCP do sistema. Se o prazo passar, o
    worker sobe e `submeter` segura os jobs novos até a limpeza acabar.
    """
    def alvo():
        try:
            n = recuperar_orfaos(None)
            if n:
                print("[jobs] %d job(s) órfão(s) declarado(s) error no arranque" % n, file=sys.stderr)
        except banco.BancoIndisponivel:
            pass                                   # sem DATABASE_URL: worker só de /health
        except Exception as e:                                    # noqa: BLE001
            print("[jobs] recuperação de órfãos falhou: %s" % e, file=sys.stderr)
        finally:
            _arranque_livre.set()

    _arranque_livre.clear()
    t = threading.Thread(target=alvo, name="fopa-jobs-orfaos", daemon=True)
    t.start()
    t.join(espera_s)


__all__ = ["Contexto", "submeter", "obter", "recuperar_orfaos", "recuperar_orfaos_no_arranque",
           "encerrar", "ORFAO_MINUTOS", "STATUS_ATIVOS", "FILA_OCR", "FILA_REDE", "FILAS"]
