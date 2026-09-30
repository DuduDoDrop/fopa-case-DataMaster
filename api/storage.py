# -*- coding: utf-8 -*-
"""
Storage de objetos (PDFs baixados e RELATORIO.html renderizado) — plano, seção 4.

POR QUE CHAVES CONTENT-ADDRESSED
  O nome original do arquivo do PNCP tem acento, espaço, `%` e às vezes `#`
  — foi o que obrigou `pagina._link_pdf` a trocar caracteres à mão. Aqui o nome
  original fica só em `arquivos.nome` (é o marcador de citação que o modelo vê)
  e a chave do objeto é o sha256 do conteúdo: `pdf/{cnpj}/{ano}/{seq}/{sha}.pdf`.
  Dois arquivos idênticos sob nomes diferentes viram um objeto só
  (`alias_duplicado`), e a invariante T24 ("todo `arquivos.status='ok'` tem
  objeto no storage com o sha gravado") é verificável por SQL + `existe()`.

POR QUE A CHAVE É TÃO RESTRITA
  Sem `%`, espaço ou não-ASCII, a mesma chave funciona igual em disco (Windows
  e Linux), em URL sem encoding e como key de S3/R2 sem surpresa de
  normalização Unicode. Sem `..`, sem barra inicial e sem `\\`, `caminho()`
  nunca sai da raiz — a chave vem do banco, e o banco é escrito por três
  papéis diferentes.

BACKENDS
  `fs`  — `Storage`. Raiz `STORAGE_ROOT` (volume `fopa_dados` no compose).
  `s3`  — `StorageS3` (R2/MinIO/S3, F8). Mesmas chaves: a migração é um
          `rclone sync` do volume para o bucket e o banco não muda. Além de
          put/get/existe tem `presign()`, que o site usa para responder o PDF
          com 302 para uma URL assinada de 10 min (plano, seção 8).
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import hmac
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, unquote, urlsplit

import httpx

from .config import S3_REGIAO_PADRAO, Config

RE_CHAVE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$")
RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
RE_CNPJ = re.compile(r"^\d{14}$")


class ChaveInvalida(ValueError):
    """Chave fora do alfabeto permitido ou que escaparia da raiz."""


class ObjetoInexistente(FileNotFoundError):
    """`get()` de chave que nunca foi gravada."""


class ConteudoDivergente(ValueError):
    """Bytes cujo sha256 não é o sha256 embutido na chave `pdf/...`."""


def validar_chave(chave: str) -> str:
    if not isinstance(chave, str) or not chave or not RE_CHAVE.match(chave):
        raise ChaveInvalida("chave inválida: %r (só [A-Za-z0-9._-] e '/', sem '..', "
                            "sem barra inicial, sem espaço, '%%' ou não-ASCII)" % (chave,))
    if any(seg in ("..", ".") for seg in chave.split("/")):
        raise ChaveInvalida("chave com segmento relativo: %r" % chave)
    # O Windows apaga o ponto final de um nome ("abc." vira "abc"): no fs do host duas chaves diferentes
    # cairiam no mesmo arquivo. Nenhuma chave do plano termina segmento em ponto (minor da revisão da F0).
    if any(seg.endswith(".") for seg in chave.split("/")):
        raise ChaveInvalida("chave com segmento terminado em ponto: %r" % chave)
    return chave


def chave_pdf(cnpj: str, ano: int, seq: int, sha256: str) -> str:
    if not RE_CNPJ.match(str(cnpj)):
        raise ChaveInvalida("cnpj deve ter 14 dígitos: %r" % (cnpj,))
    if not RE_SHA256.match(str(sha256)):
        raise ChaveInvalida("sha256 deve ter 64 hex minúsculos: %r" % (sha256,))
    return validar_chave("pdf/%s/%d/%d/%s.pdf" % (cnpj, int(ano), int(seq), sha256))


def chave_html(slug: str, verificacao_id: int | str) -> str:
    return validar_chave("html/%s/%s.html" % (slug, verificacao_id))


def _sha_da_chave_pdf(chave: str) -> str | None:
    """Sha embutido numa chave `pdf/.../{sha}.pdf`; None para os outros prefixos."""
    partes = chave.split("/")
    if partes[0] == "pdf" and partes[-1].endswith(".pdf"):
        sha = partes[-1][:-4]
        if RE_SHA256.match(sha):
            return sha
    return None


class Storage:
    """Backend `fs`: objetos em `<raiz>/<chave>`, escrita atômica (tmp + rename)."""

    backend = "fs"

    def __init__(self, raiz: str):
        self.raiz = os.path.abspath(raiz)

    # -- utilitários ------------------------------------------------------
    def caminho(self, chave: str) -> str:
        validar_chave(chave)
        destino = os.path.abspath(os.path.join(self.raiz, *chave.split("/")))
        # Conferência redundante de propósito: a regex já barra `..`, e conferir de novo não custa nada.
        if os.path.commonpath([self.raiz, destino]) != self.raiz:
            raise ChaveInvalida("chave escaparia da raiz: %r" % chave)
        return destino

    def existe(self, chave: str) -> bool:
        return os.path.isfile(self.caminho(chave))

    def get(self, chave: str) -> bytes:
        caminho = self.caminho(chave)
        try:
            with open(caminho, "rb") as f:
                return f.read()
        except FileNotFoundError:
            raise ObjetoInexistente(chave) from None

    def put(self, chave: str, dados: bytes) -> str:
        """Grava e devolve o sha256 hex do conteúdo (o que vai para `arquivos.sha256`)."""
        caminho = self.caminho(chave)
        sha = hashlib.sha256(dados).hexdigest()
        esperado = _sha_da_chave_pdf(chave)
        if esperado and esperado != sha:
            raise ConteudoDivergente("chave %s diz %s..., conteúdo tem sha %s..."
                                     % (chave, esperado[:12], sha[:12]))
        pasta = os.path.dirname(caminho)
        os.makedirs(pasta, exist_ok=True)
        # Escrita atômica: um leitor (o site servindo o PDF) nunca vê arquivo
        # pela metade, e uma queda no meio do put não deixa objeto corrompido
        # sob a chave definitiva — só um temporário fácil de reconhecer.
        fd, temporario = tempfile.mkstemp(prefix=".put-", suffix=".tmp", dir=pasta)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(dados)
            os.replace(temporario, caminho)
        except BaseException:
            try:
                os.unlink(temporario)
            except OSError:
                pass
            raise
        return sha

    def descrever(self) -> dict:
        """
        O que o `/health` mostra: backend, raiz, se ela já existe e se o
        primeiro `put` vai conseguir gravar.

        Não cria nada. Antes criava a raiz para poder dizer "gravável", e no
        host sem STORAGE_ROOT um simples GET deixava uma pasta `/dados` (C: do Windows) para trás
        (minor da revisão final da F0). A pergunta que importa continua
        respondida sem efeito colateral: `ok` é a raiz — ou, se ela ainda não
        existe, o ancestral mais próximo que existe — ser pasta gravável, que é
        o que o `put` precisa para criar o resto.
        """
        existe = os.path.isdir(self.raiz)
        alvo = os.path.abspath(self.raiz)
        while not os.path.exists(alvo):
            pai = os.path.dirname(alvo)
            if pai == alvo:
                break
            alvo = pai
        ok = os.path.isdir(alvo) and os.access(alvo, os.W_OK)
        return {"backend": self.backend, "raiz": self.raiz, "ok": bool(ok), "existe": existe}


# ====================================================================== s3
# SigV4 à mão sobre o httpx (que a imagem já tem) em vez do boto3: são quatro
# operações (PUT, GET, HEAD e URL assinada), e o boto3 traria outro cliente
# HTTP e dezenas de MB para a imagem. A assinatura é conferida contra os
# exemplos publicados pela AWS (test_storage_s3.py), não só contra ela mesma.
ALGORITMO = "AWS4-HMAC-SHA256"
HASH_VAZIO = hashlib.sha256(b"").hexdigest()
PRESIGN_PADRAO_S = 600                   # plano, seção 8: URL assinada de 10 min
PRESIGN_MAX_S = 7 * 24 * 3600            # teto da SigV4 para X-Amz-Expires
TIMEOUT_S3 = httpx.Timeout(60.0, connect=5.0)
# Sonda do /health: relógio de parede (o timeout do httpx não cobre o DNS; ver
# `site.checar_n8n`). O /api/saude espera o worker 5 s: a sonda tem de caber.
TIMEOUT_SONDA_S3 = 2.5
CHAVE_SONDA = "saude/sonda-inexistente"
# PUT e GET tentam 3 vezes contra 5xx/429/rede (esperas entre elas). O HEAD do
# site tenta uma vez só: quem clicou no PDF prefere um 503 rápido.
ESPERAS_S3 = (0.5, 1.0)
RE_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_TIPOS_S3 = {".pdf": "application/pdf", ".html": "text/html; charset=utf-8", ".json": "application/json"}
_SONDA_S3 = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="sonda-s3")


class StorageIndisponivel(RuntimeError):
    """S3 sem configuração, fora do ar ou recusando a credencial. O site responde 503."""


def _uri(texto: str, seguro: str = "-_.~") -> str:
    """URI-encode da SigV4: só os não reservados da RFC 3986 (e `seguro`) ficam como estão."""
    return quote(texto, safe=seguro)


def _hmac(chave: bytes, texto: str) -> bytes:
    return hmac.new(chave, texto.encode("utf-8"), hashlib.sha256).digest()


def _carimbo(quando: datetime) -> str:
    return quando.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escopo(amz_data: str, regiao: str) -> str:
    return "%s/%s/s3/aws4_request" % (amz_data[:8], regiao)


def _host(url: str) -> str:
    """Host como vai no cabeçalho `Host`: minúsculo, sem usuário e sem a porta padrão."""
    partes = urlsplit(url)
    host = (partes.hostname or "").lower()
    if partes.port and partes.port != {"http": 80, "https": 443}.get(partes.scheme):
        host += ":%d" % partes.port
    return host


def _requisicao_canonica(metodo: str, url: str, cabecalhos: dict, hash_corpo: str,
                         params: dict | None = None) -> tuple[str, str]:
    """(requisição canônica, SignedHeaders). `params` None = a query que já está na URL."""
    partes = urlsplit(url)
    caminho = _uri(unquote(partes.path or "/"), "/-_.~")
    pares = parse_qsl(partes.query, keep_blank_values=True) if params is None else params.items()
    query = "&".join("%s=%s" % kv for kv in sorted((_uri(k), _uri(str(v))) for k, v in pares))
    normal = {k.lower().strip(): " ".join(str(v).split()) for k, v in cabecalhos.items()}
    nomes = sorted(normal)
    canonicos = "".join("%s:%s\n" % (n, normal[n]) for n in nomes)
    assinados = ";".join(nomes)
    return "\n".join((metodo, caminho, query, canonicos, assinados, hash_corpo)), assinados


def _assinatura(segredo: str, regiao: str, amz_data: str, canonica: str) -> str:
    texto = "\n".join((ALGORITMO, amz_data, _escopo(amz_data, regiao),
                       hashlib.sha256(canonica.encode("utf-8")).hexdigest()))
    chave = _hmac(("AWS4" + segredo).encode("utf-8"), amz_data[:8])
    for parte in (regiao, "s3", "aws4_request"):
        chave = _hmac(chave, parte)
    return hmac.new(chave, texto.encode("utf-8"), hashlib.sha256).hexdigest()


def assinar_cabecalhos(metodo: str, url: str, cabecalhos: dict | None, hash_corpo: str,
                       chave_acesso: str, segredo: str, regiao: str, quando: datetime) -> dict:
    """
    Cabeçalhos a enviar numa requisição assinada (SigV4 por `Authorization`):
    os dados + `host`, `x-amz-date`, `x-amz-content-sha256` e `authorization`.
    Todos os que entram são assinados; o httpx acrescenta só os que o S3 ignora.
    """
    amz_data = _carimbo(quando)
    enviar = {"host": _host(url), "x-amz-content-sha256": hash_corpo, "x-amz-date": amz_data}
    enviar.update({k.lower(): v for k, v in (cabecalhos or {}).items()})
    canonica, assinados = _requisicao_canonica(metodo, url, enviar, hash_corpo)
    enviar["authorization"] = "%s Credential=%s/%s, SignedHeaders=%s, Signature=%s" % (
        ALGORITMO, chave_acesso, _escopo(amz_data, regiao), assinados,
        _assinatura(segredo, regiao, amz_data, canonica))
    return enviar


def presign_url(url: str, chave_acesso: str, segredo: str, regiao: str, quando: datetime,
                expira: int, extras: dict | None = None) -> str:
    """URL GET assinada na query (só o `host` é assinado; corpo UNSIGNED-PAYLOAD)."""
    amz_data = _carimbo(quando)
    params = {"X-Amz-Algorithm": ALGORITMO,
              "X-Amz-Credential": "%s/%s" % (chave_acesso, _escopo(amz_data, regiao)),
              "X-Amz-Date": amz_data, "X-Amz-Expires": str(int(expira)), "X-Amz-SignedHeaders": "host"}
    params.update(extras or {})
    canonica, _ = _requisicao_canonica("GET", url, {"host": _host(url)}, "UNSIGNED-PAYLOAD", params)
    params["X-Amz-Signature"] = _assinatura(segredo, regiao, amz_data, canonica)
    return url + "?" + "&".join("%s=%s" % kv for kv in sorted((_uri(k), _uri(v)) for k, v in params.items()))


def _codigo_erro(r: httpx.Response) -> str:
    """O `<Code>` do XML de erro do S3 (NoSuchKey, SignatureDoesNotMatch...), se houver."""
    m = re.search(r"<Code>([A-Za-z0-9.]{1,64})</Code>", r.text) if r.content else None
    return m.group(1) if m else ""


class StorageS3(Storage):
    """
    Backend `s3`: mesmas chaves do `fs`, em `S3_ENDPOINT`/`S3_BUCKET` (path-style,
    `https://endpoint/bucket/chave`, que R2 e MinIO atendem sem DNS por bucket).

    Construir nunca falha: faltando variável, cada operação levanta
    `StorageIndisponivel` com o NOME do que falta (nunca valor), e o
    `descrever()` do /health diz o mesmo — o worker e o site sobem e explicam.

    - `caminho()` não existe em S3: quem precisa de arquivo local (o scratch
      de `leitura.materializar`) usa `get()` e grava no tmp;
    - `presign()` não usa rede: é a conta da SigV4 com a hora de agora;
    - a credencial precisa de leitura, escrita e listagem no bucket (R2:
      token "Object Read & Write" restrito a ele). Sem listagem, o S3 da AWS
      responde 403 em vez de 404 para objeto que não existe.
    """

    backend = "s3"

    def __init__(self, endpoint: str | None = None, bucket: str | None = None,
                 chave_acesso: str | None = None, segredo: str | None = None,
                 regiao: str | None = S3_REGIAO_PADRAO, *,
                 transporte: httpx.BaseTransport | None = None, relogio=None):
        self.endpoint = (endpoint or "").rstrip("/") or None
        self.bucket = bucket or None
        self._chave_acesso = chave_acesso or None
        self._segredo = segredo or None
        self.regiao = regiao or S3_REGIAO_PADRAO
        self._transporte = transporte          # httpx.MockTransport nos testes; None = rede
        self._relogio = relogio or (lambda: datetime.now(timezone.utc))
        self.raiz = "s3://%s" % (self.bucket or "?")

    # -- configuração -----------------------------------------------------
    def problemas(self) -> list[str]:
        """O que impede de usar o bucket, por NOME de variável (nunca o valor)."""
        faltam = [n for n, v in (("S3_ENDPOINT", self.endpoint), ("S3_BUCKET", self.bucket),
                                 ("S3_KEY", self._chave_acesso), ("S3_SECRET", self._segredo)) if not v]
        erros = ["faltam %s no ambiente deste serviço" % ", ".join(faltam)] if faltam else []
        if self.endpoint:
            p = urlsplit(self.endpoint)
            if p.scheme not in ("http", "https") or not p.hostname or p.path or p.query or p.username:
                erros.append("S3_ENDPOINT deve ser só esquema://host[:porta] "
                             "(ex.: https://<conta>.r2.cloudflarestorage.com)")
        if self.bucket and not RE_BUCKET.match(self.bucket):
            erros.append("S3_BUCKET fora do padrão de nome de bucket (3-63 de a-z, 0-9, '.', '-')")
        return erros

    def _exigir_configuracao(self) -> None:
        erros = self.problemas()
        if erros:
            raise StorageIndisponivel("STORAGE_BACKEND=s3 sem configuração: %s" % "; ".join(erros))

    def _url(self, chave: str) -> str:
        return "%s/%s/%s" % (self.endpoint, self.bucket, _uri(chave, "/-_.~"))

    # -- transporte -------------------------------------------------------
    def _pedir(self, metodo: str, chave: str, corpo: bytes = b"", extra: dict | None = None,
               esperas: tuple = (), timeout: httpx.Timeout = TIMEOUT_S3) -> httpx.Response:
        """Uma requisição assinada; repete (após cada espera) em 5xx, 429 e erro de rede."""
        self._exigir_configuracao()
        url = self._url(chave)
        hash_corpo = hashlib.sha256(corpo).hexdigest()
        motivo = ""
        for espera in (0.0,) + tuple(esperas):
            if espera:
                time.sleep(espera)
            # Assinada a cada tentativa: `x-amz-date` velho demais o S3 recusa.
            cabecalhos = assinar_cabecalhos(metodo, url, extra, hash_corpo, self._chave_acesso,
                                            self._segredo, self.regiao, self._relogio())
            try:
                with httpx.Client(timeout=timeout, transport=self._transporte) as cliente:
                    r = cliente.request(metodo, url, content=corpo if metodo == "PUT" else None,
                                        headers=cabecalhos)
            except httpx.HTTPError as e:
                # Só o tipo: a mensagem pode trazer o host da conta, e nunca há
                # segredo na URL (a assinatura vai no cabeçalho).
                motivo = "sem resposta (%s)" % type(e).__name__
                continue
            if r.status_code == 429 or r.status_code >= 500:
                motivo = ("HTTP %d %s" % (r.status_code, _codigo_erro(r))).strip()
                continue
            return r
        tentativas = 1 + len(esperas)
        raise StorageIndisponivel("S3 %s em %s: %s%s" % (metodo, self.raiz, motivo,
                                                          " em %d tentativas" % tentativas if tentativas > 1 else ""))

    def _recusa(self, metodo: str, r: httpx.Response) -> StorageIndisponivel:
        codigo = _codigo_erro(r)
        dica = (": confira S3_KEY, S3_SECRET, S3_REGION e a permissão da credencial no bucket"
                if r.status_code in (401, 403) else "")
        return StorageIndisponivel("S3 %s em %s recusou: HTTP %d%s%s"
                                   % (metodo, self.raiz, r.status_code, " " + codigo if codigo else "", dica))

    # -- operações --------------------------------------------------------
    def caminho(self, chave: str) -> str:
        validar_chave(chave)
        raise NotImplementedError("STORAGE_BACKEND=s3 não tem caminho local: use get() e grave no tmp")

    def existe(self, chave: str) -> bool:
        validar_chave(chave)
        r = self._pedir("HEAD", chave)
        if r.status_code == 200:
            return True
        if r.status_code == 404:
            return False
        raise self._recusa("HEAD", r)

    def get(self, chave: str) -> bytes:
        validar_chave(chave)
        r = self._pedir("GET", chave, esperas=ESPERAS_S3)
        if r.status_code == 200:
            return r.content
        if r.status_code == 404:
            raise ObjetoInexistente(chave)
        raise self._recusa("GET", r)

    def put(self, chave: str, dados: bytes) -> str:
        """Grava e devolve o sha256. O S3 confere o corpo contra `x-amz-content-sha256`."""
        validar_chave(chave)
        sha = hashlib.sha256(dados).hexdigest()
        esperado = _sha_da_chave_pdf(chave)
        if esperado and esperado != sha:
            raise ConteudoDivergente("chave %s diz %s..., conteúdo tem sha %s..."
                                     % (chave, esperado[:12], sha[:12]))
        tipo = _TIPOS_S3.get(os.path.splitext(chave)[1].lower(), "application/octet-stream")
        r = self._pedir("PUT", chave, dados, {"content-type": tipo}, esperas=ESPERAS_S3)
        if r.status_code == 200:
            return sha
        raise self._recusa("PUT", r)

    def presign(self, chave: str, expira: int = PRESIGN_PADRAO_S, *, tipo: str | None = None,
                disposicao: str | None = None) -> str:
        """
        URL GET assinada, válida por `expira` segundos (padrão 600). Sem rede.

        `tipo`/`disposicao` viram `response-content-type` e
        `response-content-disposition`: o bucket responde com eles mesmo que o
        objeto tenha sido gravado (ou sincronizado pelo rclone) com outro tipo
        — é o que faz o navegador ABRIR o PDF, e não baixar.
        """
        validar_chave(chave)
        self._exigir_configuracao()
        expira = int(expira)
        if not 1 <= expira <= PRESIGN_MAX_S:
            raise ValueError("expira=%d fora de 1..%d s (limite da SigV4)" % (expira, PRESIGN_MAX_S))
        extras = {}
        if tipo:
            extras["response-content-type"] = tipo
        if disposicao:
            extras["response-content-disposition"] = disposicao
        return presign_url(self._url(chave), self._chave_acesso, self._segredo, self.regiao,
                           self._relogio(), expira, extras)

    # -- saúde ------------------------------------------------------------
    def _sondar(self) -> str | None:
        """
        GET de uma chave que não precisa existir: `404 NoSuchKey` prova endpoint,
        bucket e assinatura de uma vez. (HEAD não serve: sem corpo, um 404 de
        bucket inexistente seria igual ao de chave inexistente.)
        """
        try:
            r = self._pedir("GET", CHAVE_SONDA, timeout=httpx.Timeout(TIMEOUT_SONDA_S3))
        except StorageIndisponivel as e:
            return str(e)
        if r.status_code == 200 or (r.status_code == 404 and _codigo_erro(r) in ("NoSuchKey", "")):
            return None
        if r.status_code == 404:
            return "o bucket %s não existe no S3_ENDPOINT (%s)" % (self.bucket, _codigo_erro(r))
        return str(self._recusa("GET", r))

    def descrever(self) -> dict:
        """O que o `/health` mostra. Nunca levanta e nunca passa de ~2,5 s."""
        corpo = {"backend": self.backend, "raiz": self.raiz, "regiao": self.regiao, "ok": False}
        erros = self.problemas()
        if erros:
            corpo["erro"] = "; ".join(erros)
            return corpo
        corpo["endpoint"] = "%s://%s" % (urlsplit(self.endpoint).scheme, _host(self.endpoint))
        futuro = _SONDA_S3.submit(self._sondar)
        try:
            erro = futuro.result(timeout=TIMEOUT_SONDA_S3 + 0.25)
        except concurrent.futures.TimeoutError:
            erro = "o bucket não respondeu em %g s (DNS ou rede)" % TIMEOUT_SONDA_S3
        except Exception as e:  # noqa: BLE001 — sonda: qualquer falha é "não ok", nunca exceção
            erro = "falha na sonda do S3: %s" % type(e).__name__
        if erro:
            corpo["erro"] = erro
        else:
            corpo["ok"] = True
        return corpo


def abrir(cfg: Config, transporte: httpx.BaseTransport | None = None) -> Storage:
    """Instancia o backend que `STORAGE_BACKEND` pede (`transporte` só vale para o s3)."""
    if cfg.storage_backend == "s3":
        return StorageS3(cfg.s3_endpoint, cfg.s3_bucket, cfg.s3_key, cfg.s3_secret, cfg.s3_region,
                         transporte=transporte)
    return Storage(cfg.storage_root)


__all__ = ["Storage", "StorageS3", "abrir", "validar_chave", "chave_pdf", "chave_html",
           "ChaveInvalida", "ObjetoInexistente", "ConteudoDivergente", "StorageIndisponivel",
           "assinar_cabecalhos", "presign_url", "PRESIGN_PADRAO_S"]
