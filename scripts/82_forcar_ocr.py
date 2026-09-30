# -*- coding: utf-8 -*-
"""
Marca um arquivo de uma licitação para ser lido só pela imagem (OCR forçado) e, se preciso, girado — db/043, Pacote B
(26/09/2026). A marcação fica em `arquivos` e toda releitura a respeita (api/leitura.py); depois de marcar, relê com

    python scripts/81_reprocessar_lista.py saidas/_agente/_v3_ocr_forcado.txt

Uso:
    python scripts/82_forcar_ocr.py <controle>                                   (lista os arquivos e as marcações)
    python scripts/82_forcar_ocr.py <controle> --arquivo "Minuta do Contrato"    (força o OCR; trecho do nome)
    python scripts/82_forcar_ocr.py <controle> --arquivo "Minuta" --girar 180    (força e gira 180° no horário)
    python scripts/82_forcar_ocr.py <controle> --arquivo "Minuta" --desfazer     (volta ao texto nativo)

O trecho do nome (sem diferença de maiúsculas) tem de casar com UM arquivo `ok` da licitação; se casar com nenhum ou
com vários, o script não mexe em nada e lista os candidatos. Não chama W20 nem modelo: custo zero.
"""
from __future__ import annotations

import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "n8n"))
import cliente  # noqa: E402
import psycopg  # noqa: E402


def mostrar(conn, controle: str) -> None:
    for aid, nome, forcar, girar in conn.execute(
            "SELECT id, nome, forcar_ocr, girar FROM arquivos WHERE controle = %s AND status = 'ok' ORDER BY id",
            (controle,)).fetchall():
        marca = ("OCR forçado" + (", girar %d°" % girar if girar else "")) if (forcar or girar) else "texto nativo"
        print("  %6d  %-14s %s" % (aid, marca, nome))


def main() -> int:
    ap = argparse.ArgumentParser(description="Marca um arquivo para OCR forçado (e giro) nas próximas leituras.")
    ap.add_argument("controle")
    ap.add_argument("--arquivo", help="trecho do nome do arquivo (casa com um só)")
    ap.add_argument("--girar", type=int, choices=(0, 90, 180, 270), default=0,
                    help="graus no sentido horário antes do OCR")
    ap.add_argument("--desfazer", action="store_true", help="tira a marcação (volta ao texto nativo)")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    url = os.environ.get("FOPA_ADMIN_URL") or \
        "postgresql://postgres:%s@127.0.0.1:5433/fopa" % cliente.ler_env()["POSTGRES_PASSWORD"]

    with psycopg.connect(url) as conn:
        if not conn.execute("SELECT 1 FROM licitacoes WHERE controle = %s", (args.controle,)).fetchone():
            print("licitação %s não existe" % args.controle)
            return 2
        if not args.arquivo:
            mostrar(conn, args.controle)
            return 0
        casam = conn.execute(
            "SELECT id, nome FROM arquivos WHERE controle = %s AND status = 'ok' AND strpos(lower(nome), lower(%s)) > 0"
            " ORDER BY id", (args.controle, args.arquivo)).fetchall()
        if len(casam) != 1:
            print("%r casa com %d arquivos ok (tem de ser 1); nada mudou:" % (args.arquivo, len(casam)))
            mostrar(conn, args.controle)
            return 2
        aid, nome = casam[0]
        forcar, girar = (False, 0) if args.desfazer else (True, args.girar)
        conn.execute("UPDATE arquivos SET forcar_ocr = %s, girar = %s WHERE id = %s", (forcar, girar, aid))
        conn.commit()
        print("%s | %s -> %s" % (args.controle, nome,
                                 "texto nativo" if args.desfazer else "OCR forçado, girar %d°" % girar))
        mostrar(conn, args.controle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
