#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cópia dos backups para FORA da máquina (D9 do docs/DEPLOY.md, decidido em 28/09/2026).

O `backup.py` grava em `backups/<carimbo>/` no MESMO disco do banco: perder a EC2 era perder os dois. Este
script manda cada backup completo para o bucket do próprio app, no prefixo `backups/<carimbo>/`, com a
credencial `fopa-app` — que não tem `s3:DeleteObject`. Um erro, um script ou um invasor na máquina conseguem
gravar lá, mas não apagar: as cópias só saem por quem tem o console da AWS.

Como o `backup.py`, só usa a biblioteca padrão (o host não tem httpx nem aws/rclone). A assinatura SigV4 é a
de `api/storage.py`, repetida aqui em miniatura — `docker/tests/test_backup_fora.py` confere que as duas
assinam igual. O arquivo sobe direto do disco (`UNSIGNED-PAYLOAD`, sem carregar 500 MB na memória de uma
máquina de 2 GB) e o S3 confere a integridade pelo `x-amz-checksum-sha256`, o mesmo sha256 do manifesto.

O QUE SOBE
  Todo backup `ok` de `backups/` que ainda não está no bucket. O `manifesto.json` sobe por ÚLTIMO: no bucket,
  pasta com manifesto é cópia completa; sem ele, a rodada seguinte recomeça a pasta. Classe STANDARD_IA
  (~US$ 0,02/GB-mês em sa-east-1; ~640 MB por dia). Uma regra de ciclo de vida no prefixo `backups/`
  (console da AWS) é quem apaga as antigas.

Credenciais: S3_ENDPOINT, S3_BUCKET, S3_REGION, S3_KEY e S3_SECRET do `docker/.env` (ou do ambiente).

Uso:
    python3 docker/backup_fora.py                  # sobe o que falta
    python3 docker/backup_fora.py --listar         # só diz o que subiria
Cron (depois do backup das 03:15):
    35 3 * * *  cd /srv/projeto-fopa && python3 docker/backup_fora.py >> backups/backup_fora.log 2>&1

Saída: 0 ok (ou nada a fazer); 1 falha.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.client
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

RAIZ = Path(__file__).resolve().parents[1]
DESTINO_PADRAO = RAIZ / "backups"
ENV_PADRAO = RAIZ / "docker" / ".env"
RE_PASTA = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")
PREFIXO = "backups"
ALGORITMO = "AWS4-HMAC-SHA256"
CLASSE = "STANDARD_IA"
TIMEOUT_S = 600
TENTATIVAS = 3


class Falha(RuntimeError):
    pass


# ------------------------------------------------------------------ SigV4 (a mesma de api/storage.py)
def _uri(texto: str, seguro: str = "-_.~") -> str:
    return quote(texto, safe=seguro)


def _hmac(chave: bytes, texto: str) -> bytes:
    return hmac.new(chave, texto.encode("utf-8"), hashlib.sha256).digest()


def _host(url: str) -> str:
    partes = urlsplit(url)
    host = (partes.hostname or "").lower()
    if partes.port and partes.port != {"http": 80, "https": 443}.get(partes.scheme):
        host += ":%d" % partes.port
    return host


def assinar(metodo: str, url: str, cabecalhos: dict, hash_corpo: str, chave_acesso: str, segredo: str,
            regiao: str, quando: datetime) -> dict:
    """Os cabeçalhos a enviar, `authorization` incluído. Sem query: o script só faz HEAD e PUT de objeto."""
    amz_data = quando.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    escopo = "%s/%s/s3/aws4_request" % (amz_data[:8], regiao)
    enviar = {"host": _host(url), "x-amz-content-sha256": hash_corpo, "x-amz-date": amz_data}
    enviar.update({k.lower(): v for k, v in cabecalhos.items()})
    normal = {k.lower().strip(): " ".join(str(v).split()) for k, v in enviar.items()}
    nomes = sorted(normal)
    assinados = ";".join(nomes)
    canonica = "\n".join((metodo, _uri(unquote(urlsplit(url).path or "/"), "/-_.~"), "",
                          "".join("%s:%s\n" % (n, normal[n]) for n in nomes), assinados, hash_corpo))
    texto = "\n".join((ALGORITMO, amz_data, escopo, hashlib.sha256(canonica.encode("utf-8")).hexdigest()))
    chave = _hmac(("AWS4" + segredo).encode("utf-8"), amz_data[:8])
    for parte in (regiao, "s3", "aws4_request"):
        chave = _hmac(chave, parte)
    enviar["authorization"] = "%s Credential=%s/%s, SignedHeaders=%s, Signature=%s" % (
        ALGORITMO, chave_acesso, escopo, assinados, hmac.new(chave, texto.encode("utf-8"), hashlib.sha256).hexdigest())
    return enviar


# ------------------------------------------------------------------ bucket
def ler_env(caminho: Path) -> dict:
    env = {}
    if caminho.is_file():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k.startswith("S3_")})
    return env


class Bucket:
    def __init__(self, env: dict):
        faltam = [k for k in ("S3_ENDPOINT", "S3_BUCKET", "S3_KEY", "S3_SECRET") if not env.get(k)]
        if faltam:
            raise Falha("faltam no docker/.env: %s" % ", ".join(faltam))
        self.endpoint = env["S3_ENDPOINT"].rstrip("/")
        self.bucket = env["S3_BUCKET"]
        self.regiao = env.get("S3_REGION") or "us-east-1"
        self._chave, self._segredo = env["S3_KEY"], env["S3_SECRET"]

    def url(self, chave: str) -> str:
        return "%s/%s/%s" % (self.endpoint, self.bucket, _uri(chave, "/-_.~"))

    def _pedir(self, metodo: str, chave: str, extra: dict, corpo=None, tamanho: int = 0):
        url = self.url(chave)
        partes = urlsplit(url)
        classe = http.client.HTTPSConnection if partes.scheme == "https" else http.client.HTTPConnection
        cab = assinar(metodo, url, extra, "UNSIGNED-PAYLOAD", self._chave, self._segredo, self.regiao,
                      datetime.now(timezone.utc))
        if metodo == "PUT":
            cab["content-length"] = str(tamanho)
        conexao = classe(partes.netloc, timeout=TIMEOUT_S)
        try:
            conexao.request(metodo, partes.path, body=corpo, headers=cab)
            r = conexao.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            conexao.close()

    def tamanho(self, chave: str) -> int | None:
        """Bytes do objeto, ou None se ele não existe."""
        status, cab, _ = self._pedir("HEAD", chave, {})
        if status == 404:
            return None
        if status != 200:
            raise Falha("HEAD %s: HTTP %d" % (chave, status))
        return int({k.lower(): v for k, v in cab.items()}.get("content-length", -1))

    def enviar(self, chave: str, caminho: Path, sha256_hex: str) -> None:
        tamanho = caminho.stat().st_size
        extra = {"x-amz-checksum-sha256": base64.b64encode(bytes.fromhex(sha256_hex)).decode(),
                 "x-amz-storage-class": CLASSE}
        motivo = ""
        for tentativa in range(TENTATIVAS):
            if tentativa:
                time.sleep(15 * tentativa)
            try:
                with open(caminho, "rb") as f:
                    status, _, corpo = self._pedir("PUT", chave, extra, corpo=f, tamanho=tamanho)
            except OSError as e:
                motivo = "sem resposta (%s)" % type(e).__name__
                continue
            if status == 200:
                return
            codigo = re.search(rb"<Code>([^<]+)</Code>", corpo or b"")
            motivo = "HTTP %d %s" % (status, codigo.group(1).decode() if codigo else "")
            if status < 500 and status != 429:
                break                           # 403 (sem permissão), 400 BadDigest: repetir não resolve
        raise Falha("PUT %s: %s" % (chave, motivo.strip()))


# ------------------------------------------------------------------ o que sobe
def pendentes(destino: Path, bucket: Bucket) -> list[Path]:
    """Backups `ok` locais, do mais antigo ao mais novo, cujo manifesto ainda não está no bucket."""
    pastas = []
    for p in sorted(destino.iterdir()) if destino.is_dir() else []:
        manifesto = p / "manifesto.json"
        if not (p.is_dir() and RE_PASTA.match(p.name) and manifesto.is_file()):
            continue
        if json.loads(manifesto.read_text(encoding="utf-8")).get("status") != "ok":
            continue
        if bucket.tamanho("%s/%s/manifesto.json" % (PREFIXO, p.name)) is None:
            pastas.append(p)
    return pastas


def enviar_pasta(pasta: Path, bucket: Bucket) -> int:
    """Sobe os arquivos do manifesto (conferindo o sha256 no disco) e o manifesto por último. Devolve bytes."""
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    total = 0
    for nome, info in sorted(manifesto["arquivos"].items()):
        caminho = pasta / nome
        chave = "%s/%s/%s" % (PREFIXO, pasta.name, nome)
        if bucket.tamanho(chave) == info["bytes"]:
            continue                            # subiu numa rodada interrompida; o S3 já conferiu o sha256
        h = hashlib.sha256()
        with open(caminho, "rb") as f:
            for bloco in iter(lambda: f.read(1 << 20), b""):
                h.update(bloco)
        if h.hexdigest() != info["sha256"]:
            raise Falha("%s mudou no disco depois do backup (sha256 não bate com o manifesto)" % caminho)
        bucket.enviar(chave, caminho, info["sha256"])
        total += info["bytes"]
    caminho = pasta / "manifesto.json"
    bucket.enviar("%s/%s/manifesto.json" % (PREFIXO, pasta.name), caminho,
                  hashlib.sha256(caminho.read_bytes()).hexdigest())
    return total


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Copia os backups da stack FOPA para o bucket (prefixo backups/).")
    p.add_argument("--destino", type=Path, default=DESTINO_PADRAO, help="pasta dos backups (padrão backups/)")
    p.add_argument("--env", type=Path, default=ENV_PADRAO, help="arquivo com as S3_* (padrão docker/.env)")
    p.add_argument("--listar", action="store_true", help="só lista o que subiria")
    a = p.parse_args(argv)
    inicio = time.monotonic()
    carimbo = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        bucket = Bucket(ler_env(a.env))
        fila = pendentes(a.destino, bucket)
        if not fila:
            print("%s backup_fora: nada a subir (s3://%s/%s/ em dia)" % (carimbo, bucket.bucket, PREFIXO))
            return 0
        if a.listar:
            print("%s backup_fora: subiria %s" % (carimbo, ", ".join(x.name for x in fila)))
            return 0
        for pasta in fila:
            t = time.monotonic()
            total = enviar_pasta(pasta, bucket)
            print("%s backup_fora: %s -> s3://%s/%s/%s/ (%.1f MB em %.0f s)" % (
                carimbo, pasta.name, bucket.bucket, PREFIXO, pasta.name, total / 1e6, time.monotonic() - t))
    except Falha as e:
        print("%s backup_fora FALHOU: %s" % (carimbo, e), file=sys.stderr)
        return 1
    print("%s backup_fora: ok em %.0f s" % (carimbo, time.monotonic() - inicio))
    return 0


if __name__ == "__main__":
    sys.exit(main())
