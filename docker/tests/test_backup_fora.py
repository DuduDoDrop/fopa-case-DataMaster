# -*- coding: utf-8 -*-
"""
`docker/backup_fora.py` — a cópia dos backups para o bucket (D9, 28/09/2026), sem AWS de verdade.

  - a assinatura SigV4 em miniatura é a MESMA de `api/storage.py` (o host não tem httpx, então o script não
    pode importar o storage; o teste é o que impede as duas de divergirem);
  - contra um S3 de mentira local: sobe só backup `ok`, com o checksum do manifesto, o manifesto por último;
    não repete o que já subiu; recusa arquivo que mudou no disco.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "docker"))

import backup_fora  # noqa: E402


def test_assina_igual_ao_storage_do_app():
    from api import storage
    quando = datetime(2026, 9, 28, 3, 35, 7, tzinfo=timezone.utc)
    url = "https://s3.sa-east-1.amazonaws.com/fopa-editais-1/backups/2026-09-28_031500/n8n/workflows/W01.json"
    extra = {"x-amz-checksum-sha256": "q1w2e3==", "x-amz-storage-class": "STANDARD_IA"}
    a = backup_fora.assinar("PUT", url, extra, "UNSIGNED-PAYLOAD", "AKIAFALSA", "segredo/falso", "sa-east-1", quando)
    b = storage.assinar_cabecalhos("PUT", url, extra, "UNSIGNED-PAYLOAD", "AKIAFALSA", "segredo/falso",
                                   "sa-east-1", quando)
    assert a == b


class _S3Falso(BaseHTTPRequestHandler):
    objetos: dict = {}
    ordem: list = []

    def log_message(self, *a):
        pass

    def do_HEAD(self):
        corpo = self.objetos.get(self.path)
        self.send_response(404 if corpo is None else 200)
        self.send_header("Content-Length", "0" if corpo is None else str(len(corpo)))
        self.end_headers()

    def do_PUT(self):
        assert self.headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIAFALSA/")
        assert self.headers["x-amz-content-sha256"] == "UNSIGNED-PAYLOAD"
        corpo = self.rfile.read(int(self.headers["Content-Length"]))
        esperado = base64.b64encode(hashlib.sha256(corpo).digest()).decode()
        if self.headers["x-amz-checksum-sha256"] != esperado:      # o que o S3 faz: BadDigest
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<Error><Code>BadDigest</Code></Error>")
            return
        self.objetos[self.path] = corpo
        self.ordem.append(self.path)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


@pytest.fixture
def s3():
    _S3Falso.objetos, _S3Falso.ordem = {}, []
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _S3Falso)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield backup_fora.Bucket({"S3_ENDPOINT": "http://127.0.0.1:%d" % servidor.server_port,
                              "S3_BUCKET": "fopa-editais-1", "S3_REGION": "sa-east-1",
                              "S3_KEY": "AKIAFALSA", "S3_SECRET": "segredo"})
    servidor.shutdown()


def _backup(destino: Path, nome: str, status: str = "ok") -> Path:
    pasta = destino / nome
    (pasta / "n8n" / "workflows").mkdir(parents=True)
    arquivos = {"fopa.dump": b"dump do fopa" * 1000, "n8n.dump": b"dump do n8n", "globais.sql": b"-- papeis",
                "n8n/workflows/W01.json": b'{"id": "W01"}'}
    for nome_arq, dados in arquivos.items():
        (pasta / nome_arq).write_bytes(dados)
    manifesto = {"status": status, "arquivos": {k: {"bytes": len(v), "sha256": hashlib.sha256(v).hexdigest()}
                                                for k, v in arquivos.items()}}
    (pasta / "manifesto.json").write_text(json.dumps(manifesto), encoding="utf-8")
    return pasta


def test_sobe_so_o_que_falta_com_o_manifesto_por_ultimo(tmp_path, s3):
    _backup(tmp_path, "2026-09-27_031500")
    _backup(tmp_path, "2026-09-28_031500")
    _backup(tmp_path, "2026-09-28_040000", status="parcial")      # backup quebrado nunca sai da máquina
    (tmp_path / ".parcial-2026-09-28_050000").mkdir()             # rodada em andamento também não

    assert [p.name for p in backup_fora.pendentes(tmp_path, s3)] == ["2026-09-27_031500", "2026-09-28_031500"]
    for pasta in backup_fora.pendentes(tmp_path, s3):
        backup_fora.enviar_pasta(pasta, s3)
    chaves = _S3Falso.ordem
    assert "/fopa-editais-1/backups/2026-09-28_031500/n8n/workflows/W01.json" in chaves
    assert _S3Falso.objetos["/fopa-editais-1/backups/2026-09-27_031500/fopa.dump"] == b"dump do fopa" * 1000
    # o manifesto fecha cada pasta: no bucket, pasta com manifesto é cópia completa
    assert chaves[4].endswith("2026-09-27_031500/manifesto.json")
    assert chaves[-1].endswith("2026-09-28_031500/manifesto.json")
    assert backup_fora.pendentes(tmp_path, s3) == []              # a segunda rodada não repete nada


def test_retomada_nao_reenvia_o_que_ja_subiu_e_recusa_arquivo_mudado(tmp_path, s3):
    pasta = _backup(tmp_path, "2026-09-28_031500")
    _S3Falso.objetos["/fopa-editais-1/backups/2026-09-28_031500/fopa.dump"] = b"dump do fopa" * 1000
    backup_fora.enviar_pasta(pasta, s3)
    assert not any(c.endswith("fopa.dump") for c in _S3Falso.ordem)   # já estava lá, do mesmo tamanho

    outra = _backup(tmp_path, "2026-09-29_031500")
    (outra / "n8n.dump").write_bytes(b"dump do n8x")                  # mesmo tamanho, outro conteúdo
    with pytest.raises(backup_fora.Falha, match="mudou no disco"):
        backup_fora.enviar_pasta(outra, s3)
    assert not any("2026-09-29_031500/manifesto.json" in c for c in _S3Falso.ordem)


def test_sem_credencial_diz_o_nome_do_que_falta(tmp_path):
    with pytest.raises(backup_fora.Falha, match="S3_KEY, S3_SECRET"):
        backup_fora.Bucket({"S3_ENDPOINT": "https://s3.sa-east-1.amazonaws.com", "S3_BUCKET": "b"})
