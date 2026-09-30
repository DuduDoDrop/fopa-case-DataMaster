# -*- coding: utf-8 -*-
"""
Baixa e lê de novo, uma a uma pelo W20, as licitações de uma lista — para rodar num terminal à parte
(as 36 da 4ª passada, interrompida por falta de memória da máquina).

    python scripts/81_reprocessar_lista.py saidas/_agente/_v3_reprocesso4_faltam.txt --conferir   (só mostra)
    python scripts/81_reprocessar_lista.py saidas/_agente/_v3_reprocesso4_faltam.txt              (roda)
    python scripts/81_reprocessar_lista.py saidas/_agente/_v3_reprocesso4_faltam.txt --limite 5   (só 5 desta vez)

Para cada licitação, o caminho da 4ª passada: volta a `nova` (db/042), zera as tentativas e chama o W20 com `forcar`.
Com o provedor `simulado` o W20 só baixa e lê (para em `preparada`): nenhum modelo, custo zero de API. Se o provedor
deixar de ser `simulado`, o script PARA antes da próxima licitação — a extração é do agente, depois.

O log fica ao lado da lista (`<lista>.log`, só acrescenta) e é ele que permite RETOMAR: rodar de novo o mesmo comando
pula o que já tem linha de resultado. A trava (`<lista>.trava`) impede duas rodadas da mesma lista ao mesmo tempo; se
uma rodada morreu sem apagá-la, apague o arquivo à mão.

Pula, dizendo por quê: a reservada para o teste em produção, a que tem pedido de extração paga pendente, a que está
fora do escopo (rótulo "fora" ou a regra) e o estado que não volta a `nova`.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "n8n"))
import cliente  # noqa: E402
import psycopg  # noqa: E402

RESERVADAS = os.path.join(RAIZ, "saidas", "_agente", "_reservadas_prod.txt")
NOTA = "coleta completa: baixar e ler de novo (scripts/81_reprocessar_lista.py)"
RE_FEITA = re.compile(r"\[\d+/\d+\] (\S+) ")
# O W22 espera a leitura até 40 min (160 voltas de 15 s, 26/09); o W20 inteiro cabe em 45.
TEMPO_W20 = 2700


def ler_lista(caminho: str) -> list[str]:
    vistos, out = set(), []
    for linha in io.open(caminho, encoding="utf-8"):
        c = linha.split("#", 1)[0].strip()
        if c and c not in vistos:
            vistos.add(c)
            out.append(c)
    return out


def ler_reservadas() -> set[str]:
    # Só a linha que COMEÇA com o controle, como `_v3.py` e `_v3_baixar.py`: o comentário que cita uma licitação ("ficou
    # de fora", "liberada em 26/09") não é reserva.
    if not os.path.exists(RESERVADAS):
        return set()
    return {linha.split()[0] for linha in io.open(RESERVADAS, encoding="utf-8") if re.match(r"^\d{14}-", linha)}


def provedor(conn) -> str | None:
    linha = conn.execute("SELECT valor FROM configuracao WHERE chave = 'provedor'").fetchone()
    return str(linha[0]).strip('"') if linha else None


def por_que_pular(conn, c: str, permitidas: set[str], reservadas: set[str]) -> tuple[str | None, tuple | None]:
    """(motivo para pular ou None, (estado, órgão, uf))."""
    if c in reservadas:
        return "reservada para o teste em produção", None
    linha = conn.execute("SELECT estado::text, fn_escopo_efetivo(controle, COALESCE(escopo_dentro, false)), orgao, uf"
                         " FROM licitacoes WHERE controle = %s", (c,)).fetchone()
    if linha is None:
        return "não existe no banco", None
    estado, dentro, orgao, uf = linha
    if not dentro:
        return "fora do escopo (rótulo ou regra)", (estado, orgao, uf)
    if conn.execute("SELECT count(*) FROM pedidos_extracao WHERE controle = %s AND usado_em IS NULL", (c,)).fetchone()[0]:
        return "tem pedido de extração paga pendente", (estado, orgao, uf)
    # `nova` é o que sobra de uma rodada que morreu entre a volta e o W20: roda o W20 direto
    if estado != "nova" and estado not in permitidas:
        return "estado %s não volta a nova" % estado, (estado, orgao, uf)
    return None, (estado, orgao, uf)


def main() -> int:
    ap = argparse.ArgumentParser(description="Baixa e lê de novo, pelo W20, as licitações de uma lista.")
    ap.add_argument("lista", help="arquivo com um controle por linha (# comenta)")
    ap.add_argument("--conferir", action="store_true", help="só mostra o que faria, sem mexer em nada")
    ap.add_argument("--limite", type=int, default=None, help="no máximo N licitações nesta rodada")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    lista = os.path.abspath(args.lista)
    base = os.path.splitext(lista)[0]
    caminho_log, caminho_trava = base + ".log", base + ".trava"
    alvos = ler_lista(lista)
    feitas = set(RE_FEITA.findall(io.open(caminho_log, encoding="utf-8").read())) if os.path.exists(caminho_log) else set()
    faltam = [c for c in alvos if c not in feitas]
    if args.limite is not None:
        faltam = faltam[:max(0, args.limite)]
    reservadas = ler_reservadas()
    url = "postgresql://postgres:%s@127.0.0.1:5433/fopa" % cliente.ler_env()["POSTGRES_PASSWORD"]

    if args.conferir:
        with psycopg.connect(url) as conn:
            permitidas = {r[0] for r in conn.execute("SELECT de::text FROM transicoes WHERE para = 'nova'").fetchall()}
            print("%d na lista, %d já feitas no log, %d a fazer nesta rodada; provedor: %s" % (
                len(alvos), len(feitas & set(alvos)), len(faltam), provedor(conn)))
            for c in faltam:
                motivo, info = por_que_pular(conn, c, permitidas, reservadas)
                onde = "%s/%s %s" % ((info[1] or "")[:40], info[2], info[0]) if info else ""
                print(("PULARIA %s: %s" % (c, motivo)) if motivo else ("FARIA   %s %s" % (c, onde)))
        return 0

    def log(msg: str) -> None:
        linha = time.strftime("%d/%m %H:%M:%S ") + msg
        print(linha, flush=True)
        with io.open(caminho_log, "a", encoding="utf-8") as f:
            f.write(linha + "\n")

    try:
        fd = os.open(caminho_trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("Outra rodada desta lista está em curso (%s). Se não estiver, apague a trava e rode de novo." % caminho_trava)
        return 2
    os.write(fd, ("pid %d desde %s\n" % (os.getpid(), time.strftime("%d/%m %H:%M:%S"))).encode())
    os.close(fd)
    resultado: dict[str, int] = {}
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            permitidas = {r[0] for r in conn.execute("SELECT de::text FROM transicoes WHERE para = 'nova'").fetchall()}
            log("lista %s: %d licitações, %d já feitas no log, %d a fazer nesta rodada" % (
                os.path.basename(lista), len(alvos), len(feitas & set(alvos)), len(faltam)))
            for i, c in enumerate(faltam, 1):
                prov = provedor(conn)
                if prov != "simulado":
                    log("PAREI antes de %s: o provedor é %r, não 'simulado' — o W20 extrairia com modelo pago. Volte o"
                        " provedor a 'simulado' no Admin e rode de novo." % (c, prov))
                    return 3
                motivo, info = por_que_pular(conn, c, permitidas, reservadas)
                if motivo:
                    log("PULADA %s: %s" % (c, motivo))
                    continue
                estado, orgao, uf = info
                if estado != "nova":
                    conn.execute("SELECT fn_transicao(%s, 'nova', %s, %s::jsonb)",
                                 (c, NOTA, json.dumps({"de": estado, "solicitante": "coleta completa"})))
                conn.execute("UPDATE licitacoes SET tentativas = 0, proxima_tentativa_em = NULL, lease_por = NULL,"
                             " lease_ate = NULL WHERE controle = %s", (c,))
                t0 = time.time()
                p = subprocess.run([sys.executable, os.path.join("n8n", "executar.py"), "W20", "--itens",
                                    json.dumps({"controle": c, "forcar": True}), "--timeout", str(TEMPO_W20)],
                                   cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
                novo, motivo_estado = conn.execute("SELECT estado::text, estado_motivo FROM licitacoes WHERE controle = %s",
                                                   (c,)).fetchone()
                arqs = conn.execute("SELECT status, count(*) FROM arquivos WHERE controle = %s GROUP BY 1 ORDER BY 1",
                                    (c,)).fetchall()
                resultado[novo] = resultado.get(novo, 0) + 1
                log("[%d/%d] %s %s/%s %s -> %s (%s) em %ds | arquivos: %s | W20 rc=%d" % (
                    i, len(faltam), c, (orgao or "")[:40], uf, estado, novo, (motivo_estado or "")[:90], time.time() - t0,
                    ", ".join("%s=%d" % a for a in arqs), p.returncode))
                if p.returncode != 0:
                    saida = (p.stderr or p.stdout or "").strip().splitlines()
                    log("   W20: %s" % (saida[-1][:200] if saida else "(sem saída)"))
            log("fim: %s" % (", ".join("%s=%d" % kv for kv in sorted(resultado.items())) or "nada a fazer"))
            return 0
    except KeyboardInterrupt:
        log("interrompido (Ctrl+C) — rode o mesmo comando para continuar de onde parou")
        return 130
    finally:
        try:
            os.remove(caminho_trava)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
