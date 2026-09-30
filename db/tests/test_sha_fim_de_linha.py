# -*- coding: utf-8 -*-
"""
O sha256 de uma migração não pode depender do fim de linha do checkout.

POR QUE ISTO EXISTE
  O repositório roda com `core.autocrlf=true` e sem `.gitattributes`: o Git
  guarda LF e reescreve o arquivo com CRLF no próximo checkout no Windows. Um
  clone no Linux fica com LF. Com o sha calculado sobre os bytes crus, a mesma
  migração tinha dois shas conforme a máquina — e o `migrar.py`, que ABORTA
  quando o sha de uma migração já aplicada muda, recusaria um banco íntegro
  depois de um simples `git checkout`.

  Normalizar para LF antes de calcular mantém o sha dos arquivos que já foram
  aplicados com LF (os de hoje), então nenhum banco migrado precisa de ajuste.

Não precisa de Postgres: é só a função de hash.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import migrar  # noqa: E402

SQL_LF = b"CREATE TABLE a (x int);\nSELECT 1;\n"
SQL_CRLF = b"CREATE TABLE a (x int);\r\nSELECT 1;\r\n"


def test_crlf_e_lf_tem_o_mesmo_sha(tmp_path):
    lf, crlf = tmp_path / "001_lf.sql", tmp_path / "001_crlf.sql"
    lf.write_bytes(SQL_LF)
    crlf.write_bytes(SQL_CRLF)
    assert migrar.sha256(lf) == migrar.sha256(crlf)


def test_arquivo_lf_mantem_o_sha_de_sempre(tmp_path):
    # Compatibilidade: bancos migrados com os arquivos LF de hoje continuam
    # casando, porque o sha de um arquivo LF não muda com a normalização.
    p = tmp_path / "001.sql"
    p.write_bytes(SQL_LF)
    assert migrar.sha256(p) == hashlib.sha256(SQL_LF).hexdigest()


def test_mudanca_de_conteudo_continua_mudando_o_sha(tmp_path):
    # A normalização não pode afrouxar a guarda: editar a migração ainda aborta.
    a, b = tmp_path / "001_a.sql", tmp_path / "001_b.sql"
    a.write_bytes(SQL_LF)
    b.write_bytes(SQL_LF.replace(b"SELECT 1", b"SELECT 2"))
    assert migrar.sha256(a) != migrar.sha256(b)
