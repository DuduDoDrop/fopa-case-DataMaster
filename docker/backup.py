#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backup operacional da stack FOPA v3 (plano, seção 10, F7: "pg_dump + n8n
export:workflow --backup no cron"; seção 4: "credenciais reimportadas com a
mesma N8N_ENCRYPTION_KEY").

Só usa a biblioteca padrão e o `docker` da máquina: roda igual no Windows (Git
Bash, PowerShell, Agendador de Tarefas) e no Linux (cron). Mexe SÓ nos
containers do projeto compose `fopa` (confere o rótulo antes de tocar): o n8n
de outro projeto da máquina (container `n8n`, porta 5678) nunca entra aqui.

O que sai, numa pasta datada `backups/AAAA-MM-DD_HHMMSS/` (gitignorada):
    fopa.dump                 pg_dump -Fc do banco de negócio
    n8n.dump                  pg_dump -Fc do banco do n8n (fluxos, execuções, credenciais cifradas)
    globais.sql               papéis do cluster, SEM senha (pg_dumpall --globals-only --no-role-passwords)
    n8n/workflows/*.json      n8n export:workflow --backup
    n8n/credenciais/*.json    n8n export:credentials --backup — CIFRADAS com a N8N_ENCRYPTION_KEY.
                              Nunca --decrypted: o script confere arquivo a arquivo e aborta se
                              alguma sair em texto aberto.
    manifesto.json            tamanho e sha256 de cada arquivo, contagens antes/depois do dump,
                              versões, duração de cada passo
A pasta nasce como `.parcial-<carimbo>` e só ganha o nome final quando tudo deu
certo: a retenção (últimas N, padrão 7) nunca conta backup quebrado.

A N8N_ENCRYPTION_KEY NÃO vai no backup (é segredo; guarde-a fora, num cofre).
Sem ela as credenciais exportadas e as do n8n.dump não abrem. O manifesto
guarda só os 12 primeiros hex do sha256 dela, para conferir a chave certa na
hora de restaurar sem revelar nada.

Uso:
    python docker/backup.py                     # backup + retenção (7)
    python docker/backup.py --manter 14
    python docker/backup.py --verificar         # restaura o mais recente num Postgres efêmero e compara
    python docker/backup.py --verificar backups/2026-09-24_031500

Cron sugerido (Linux, no host da stack; o log cai dentro de backups/, ignorado):
    15 3 * * *  cd /srv/projeto-fopa && python3 docker/backup.py >> backups/backup.log 2>&1
    45 3 * * 0  cd /srv/projeto-fopa && python3 docker/backup.py --verificar >> backups/backup.log 2>&1
Windows (Agendador de Tarefas):
    schtasks /Create /TN "FOPA backup" /SC DAILY /ST 03:15 /TR "python C:\\Users\\Nome\\Projetos\\projeto-fopa\\docker\\backup.py"
    schtasks /Create /TN "FOPA backup verificar" /SC WEEKLY /D SUN /ST 03:45 /TR "python C:\\Users\\Nome\\Projetos\\projeto-fopa\\docker\\backup.py --verificar"

Restaurar de verdade (volume novo; a ordem importa):
    cd docker && docker compose up -d fopa-postgres     # o init cria o banco n8n e o papel n8n
    docker exec -i fopa-postgres psql -U postgres < ../backups/<pasta>/globais.sql
        (erros "role ... already exists" para postgres e n8n são esperados)
    docker exec -i fopa-postgres pg_restore -U postgres -d fopa --exit-on-error < ../backups/<pasta>/fopa.dump
    docker exec -i fopa-postgres pg_restore -U postgres -d n8n  --exit-on-error < ../backups/<pasta>/n8n.dump
    docker compose --profile migrate run --rm fopa-migrate   # 0 aplicadas; reaplica as senhas dos papéis
    docker compose up -d                                     # com a MESMA N8N_ENCRYPTION_KEY no docker/.env
Os PDFs e RELATORIOs ficam no volume `fopa_dados`, que este script NÃO copia
(o acervo importado se refaz de acervo/; o que o W21 baixar depois, não).

Saída: 0 ok; 2 backup parcial (n8n parado: sem o export, mas com o n8n.dump) ou
verificação divergente; 1 falha.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO_PADRAO = RAIZ / "backups"
PROJETO = "fopa"                         # rótulo com.docker.compose.project exigido
PG = "fopa-postgres"
N8N = "fopa-n8n"
MANTER_PADRAO = 7
RE_PASTA = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")
TMP_N8N = "/tmp/fopa-backup"
IMAGEM_EFEMERA = "postgres:16-alpine"    # a mesma major do fopa-postgres
TABELAS_FOPA = ("licitacoes", "leituras", "paginas", "arquivos", "execucoes_modelo", "chamadas_modelo",
                "respostas", "verificacoes", "verificacao_respostas", "licitacao_eventos", "emails",
                "execucoes_workflow", "sinais_jev", "schema_migracoes")
TABELAS_N8N = ("workflow_entity", "credentials_entity", "execution_entity")
# O n8n poda as próprias execuções (EXECUTIONS_DATA_PRUNE): perto do teto a tabela cresce e encolhe durante o backup,
# e a foto do pg_dump pode sair do intervalo antes/depois — no máximo pelas execuções criadas enquanto o backup roda
# (o W50 cria uma por minuto). Só ela tem folga; as demais tabelas conferem sem folga.
FOLGA_PODADA = {("n8n", "execution_entity"): 50}


def contagem_confere(banco: str, tabela: str, n: int, antes: int | None, depois: int | None) -> bool:
    """A contagem restaurada bate com o manifesto: igual à de antes ou à de depois, ou entre elas (mais a folga)."""
    if n in (antes, depois):
        return True
    if antes is None or depois is None:
        return False
    folga = FOLGA_PODADA.get((banco, tabela), 0)
    return min(antes, depois) - folga <= n <= max(antes, depois) + folga


# ------------------------------------------------------------------ docker
class Falha(RuntimeError):
    pass


def _docker(args: list[str], entrada: str | None = None, cwd: Path | None = None, checar: bool = True) -> str:
    r = subprocess.run(["docker", *args], input=entrada, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=cwd)
    if checar and r.returncode != 0:
        raise Falha("docker %s falhou (%d): %s" % (" ".join(args[:3]), r.returncode, r.stderr.strip()[-800:]))
    return r.stdout


def _docker_para_arquivo(args: list[str], caminho: Path) -> None:
    with open(caminho, "wb") as f:
        r = subprocess.run(["docker", *args], stdout=f, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise Falha("docker %s falhou (%d): %s" % (" ".join(args[:4]), r.returncode,
                                                   r.stderr.decode("utf-8", "replace").strip()[-800:]))


def _rodando(nome: str) -> bool:
    return _docker(["inspect", "-f", "{{.State.Running}}", nome], checar=False).strip() == "true"


def _exigir_do_projeto(nome: str) -> None:
    """Nunca toca container fora do compose `fopa` (o n8n de outro projeto da máquina é intocável)."""
    projeto = _docker(["inspect", "-f", '{{index .Config.Labels "com.docker.compose.project"}}', nome],
                      checar=False).strip()
    if projeto != PROJETO:
        raise Falha("o container %s não é do projeto compose '%s' (rótulo: %r): recuso tocar nele"
                    % (nome, PROJETO, projeto))


def _psql(container: str, banco: str, sql: str) -> str:
    return _docker(["exec", "-i", container, "psql", "-U", "postgres", "-d", banco, "-At", "-v",
                    "ON_ERROR_STOP=1"], entrada=sql)


def _contagens(container: str, banco: str, tabelas) -> dict:
    lista = ",".join("'%s'" % t for t in tabelas)
    existem = set(_psql(container, banco, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                                          " AND tablename IN (%s);" % lista).split())
    if not existem:
        return {}
    sql = " UNION ALL ".join("SELECT '%s', count(*) FROM public.%s" % (t, t) for t in tabelas if t in existem)
    return {a: int(b) for a, b in (l.split("|") for l in _psql(container, banco, sql + ";").splitlines() if "|" in l)}


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _arquivos(pasta: Path) -> dict:
    return {p.relative_to(pasta).as_posix(): {"bytes": p.stat().st_size, "sha256": _sha256(p)}
            for p in sorted(pasta.rglob("*")) if p.is_file() and p.name != "manifesto.json"
            and not p.name.startswith("verificacao_")}


def _mb(n: int) -> str:
    return "%.1f MB" % (n / 1e6)


# ------------------------------------------------------------------ backup
def _exportar_n8n(pasta: Path) -> dict:
    """export:workflow e export:credentials --backup dentro do fopa-n8n; copia; apaga o temporário."""
    _docker(["exec", N8N, "sh", "-c", "rm -rf {t} && mkdir -p {t}/workflows {t}/credenciais".format(t=TMP_N8N)])
    try:
        _docker(["exec", N8N, "n8n", "export:workflow", "--backup", "--output=%s/workflows/" % TMP_N8N])
        _docker(["exec", N8N, "n8n", "export:credentials", "--backup", "--output=%s/credenciais/" % TMP_N8N])
        pasta.mkdir(parents=True, exist_ok=True)
        # cwd + caminho relativo: no Windows, "C:\..." viraria "container C" para o docker cp.
        _docker(["cp", "%s:%s/workflows" % (N8N, TMP_N8N), "workflows"], cwd=pasta)
        _docker(["cp", "%s:%s/credenciais" % (N8N, TMP_N8N), "credenciais"], cwd=pasta)
    finally:
        _docker(["exec", N8N, "rm", "-rf", TMP_N8N], checar=False)
    credenciais = sorted((pasta / "credenciais").glob("*.json"))
    for arq in credenciais:
        d = json.loads(arq.read_text(encoding="utf-8"))
        for item in d if isinstance(d, list) else [d]:
            if not isinstance(item.get("data"), str):
                raise Falha("a credencial %s saiu SEM cifra (campo data não é texto cifrado): backup abortado"
                            % arq.name)
    return {"workflows": len(list((pasta / "workflows").glob("*.json"))), "credenciais": len(credenciais)}


def _impressao_da_chave() -> str | None:
    chave = _docker(["exec", N8N, "printenv", "N8N_ENCRYPTION_KEY"], checar=False).strip()
    return hashlib.sha256(chave.encode()).hexdigest()[:12] if chave else None


def _reter(destino: Path, manter: int) -> list[str]:
    """Apaga só pastas com o nome datado E manifesto (as deste script), além das `manter` mais novas."""
    nossas = sorted((p for p in destino.iterdir() if p.is_dir() and RE_PASTA.match(p.name)
                     and (p / "manifesto.json").is_file()), key=lambda p: p.name, reverse=True)
    apagadas = []
    for p in nossas[manter:]:
        shutil.rmtree(p)
        apagadas.append(p.name)
    limite = time.time() - 86400
    for p in destino.glob(".parcial-*"):          # sobra de uma rodada morta no meio
        if p.is_dir() and p.stat().st_mtime < limite:
            shutil.rmtree(p, ignore_errors=True)
            apagadas.append(p.name)
    return apagadas


def fazer_backup(destino: Path, manter: int) -> int:
    inicio = time.monotonic()
    carimbo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    destino.mkdir(parents=True, exist_ok=True)
    parcial, final = destino / (".parcial-" + carimbo), destino / carimbo
    parcial.mkdir()
    avisos, passos = [], {}

    def passo(nome, fn, *a):
        t = time.monotonic()
        r = fn(*a)
        passos[nome] = round(time.monotonic() - t, 2)
        return r

    try:
        _exigir_do_projeto(PG)
        if not _rodando(PG):
            raise Falha("%s não está rodando" % PG)
        antes = {"fopa": _contagens(PG, "fopa", TABELAS_FOPA), "n8n": _contagens(PG, "n8n", TABELAS_N8N)}
        for banco in ("fopa", "n8n"):
            passo("pg_dump %s" % banco, _docker_para_arquivo,
                  ["exec", PG, "pg_dump", "-U", "postgres", "-d", banco, "-Fc", "-Z", "6"], parcial / ("%s.dump" % banco))
        passo("pg_dumpall globais", _docker_para_arquivo,
              ["exec", PG, "pg_dumpall", "-U", "postgres", "--globals-only", "--no-role-passwords"],
              parcial / "globais.sql")
        depois = {"fopa": _contagens(PG, "fopa", TABELAS_FOPA), "n8n": _contagens(PG, "n8n", TABELAS_N8N)}
        exportados, chave, versao_n8n = None, None, None
        if _rodando(N8N):
            _exigir_do_projeto(N8N)
            exportados = passo("n8n export", _exportar_n8n, parcial / "n8n")
            chave = _impressao_da_chave()
            versao_n8n = _docker(["exec", N8N, "n8n", "--version"], checar=False).strip().splitlines()[-1:] or None
        else:
            avisos.append("%s parado: export:workflow/credentials pulado (o n8n.dump tem os mesmos dados)" % N8N)
        manifesto = {
            "versao": 1, "carimbo": carimbo, "status": "parcial" if avisos else "ok", "avisos": avisos,
            "containers": {"postgres": PG, "n8n": N8N, "projeto": PROJETO},
            "pg_dump": _docker(["exec", PG, "pg_dump", "--version"]).strip(),
            "n8n_versao": versao_n8n[0] if versao_n8n else None,
            "n8n_exportados": exportados, "n8n_chave_sha256_12": chave,
            "contagens": {"antes": antes, "depois": depois}, "passos_s": passos,
            "arquivos": _arquivos(parcial), "duracao_s": round(time.monotonic() - inicio, 2)}
        (parcial / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
        parcial.rename(final)
    except BaseException:
        shutil.rmtree(parcial, ignore_errors=True)
        raise
    apagadas = _reter(destino, manter)
    total = sum(a["bytes"] for a in manifesto["arquivos"].values())
    print("backup %s: %s em %.1f s -> %s" % (manifesto["status"], _mb(total), manifesto["duracao_s"], final))
    for nome in ("fopa.dump", "n8n.dump", "globais.sql"):
        print("  %-12s %10s  sha256 %s…" % (nome, _mb(manifesto["arquivos"][nome]["bytes"]),
                                            manifesto["arquivos"][nome]["sha256"][:16]))
    if exportados:
        print("  n8n export   %d fluxos, %d credenciais (cifradas; chave sha256 %s…)"
              % (exportados["workflows"], exportados["credenciais"], chave))
    print("  passos: %s" % ", ".join("%s %.1fs" % kv for kv in passos.items()))
    print("  licitacoes: %s (antes) / %s (depois)" % (antes["fopa"].get("licitacoes"),
                                                       depois["fopa"].get("licitacoes")))
    for a in avisos:
        print("  aviso: %s" % a)
    if apagadas:
        print("  retenção (%d): apagadas %s" % (manter, ", ".join(apagadas)))
    return 2 if avisos else 0


# ------------------------------------------------------------------ verificar
def _esperar_pronto(nome: str, limite_s: int = 120) -> None:
    """O entrypoint sobe um servidor temporário (só socket) e reinicia: só vale o de depois do init."""
    fim = time.time() + limite_s
    while time.time() < fim:
        logs = subprocess.run(["docker", "logs", nome], capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        if "init process complete" in (logs.stdout + logs.stderr):
            if subprocess.run(["docker", "exec", nome, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                              capture_output=True).returncode == 0:
                return
        time.sleep(1)
    raise Falha("Postgres efêmero %s não ficou pronto em %d s" % (nome, limite_s))


def _mais_recente(destino: Path) -> Path:
    nossas = sorted((p for p in destino.iterdir() if p.is_dir() and RE_PASTA.match(p.name)
                     and (p / "manifesto.json").is_file()), key=lambda p: p.name)
    if not nossas:
        raise Falha("nenhum backup em %s" % destino)
    return nossas[-1]


def verificar(pasta: Path) -> int:
    """Restaura o backup num Postgres 16 efêmero (sem porta publicada) e compara com o manifesto."""
    inicio = time.monotonic()
    m = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    problemas = []
    for nome, info in m["arquivos"].items():
        arq = pasta / nome
        if not arq.is_file():
            problemas.append("falta %s" % nome)
        elif _sha256(arq) != info["sha256"]:
            problemas.append("sha256 de %s não bate com o manifesto" % nome)
    nome = "fopa-backup-verif-" + secrets.token_hex(4)
    senha = secrets.token_hex(16)           # nunca impressa; o container morre no fim
    _docker(["run", "-d", "--rm", "--name", nome, "-e", "POSTGRES_PASSWORD=" + senha,
             "-e", "POSTGRES_DB=fopa", IMAGEM_EFEMERA])
    passos, restaurado = {}, {}
    try:
        t = time.monotonic()
        _esperar_pronto(nome)
        passos["subir efêmero"] = round(time.monotonic() - t, 2)
        for arq in ("globais.sql", "fopa.dump", "n8n.dump"):
            _docker(["cp", arq, "%s:/tmp/%s" % (nome, arq)], cwd=pasta)
        # Papéis primeiro (os dumps têm dono e GRANT); "postgres already exists" é esperado.
        _docker(["exec", nome, "psql", "-U", "postgres", "-q", "-f", "/tmp/globais.sql"], checar=False)
        _docker(["exec", nome, "createdb", "-U", "postgres", "-O", "n8n", "n8n"])
        for banco in ("fopa", "n8n"):
            t = time.monotonic()
            _docker(["exec", nome, "pg_restore", "-U", "postgres", "-d", banco, "--exit-on-error",
                     "/tmp/%s.dump" % banco])
            passos["pg_restore %s" % banco] = round(time.monotonic() - t, 2)
        restaurado = {"fopa": _contagens(nome, "fopa", TABELAS_FOPA), "n8n": _contagens(nome, "n8n", TABELAS_N8N)}
    finally:
        # `-v`: o `--rm` do `run` só apaga o volume anônimo do Postgres quando o container sai sozinho; o `rm -f`
        # sem `-v` deixava 2,5 GB órfãos por verificação na EC2 (28/09: dois volumes, o disco de 7,5 GB livres
        # para 4,0 GB — a prova semanal do cron encheria o disco em semanas).
        _docker(["rm", "-f", "-v", nome], checar=False)
    comparacao = {}
    for banco in ("fopa", "n8n"):
        for tabela, n in restaurado[banco].items():
            a = m["contagens"]["antes"][banco].get(tabela)
            d = m["contagens"]["depois"][banco].get(tabela)
            ok = contagem_confere(banco, tabela, n, a, d)
            comparacao["%s.%s" % (banco, tabela)] = {"restaurado": n, "antes": a, "depois": d, "ok": ok}
            if not ok:
                problemas.append("%s.%s: restaurado %s, manifesto %s/%s" % (banco, tabela, n, a, d))
    exp = m.get("n8n_exportados")
    if exp:
        for tabela, chave in (("workflow_entity", "workflows"), ("credentials_entity", "credenciais")):
            if restaurado["n8n"].get(tabela) != exp[chave]:
                problemas.append("n8n: %s restaurado %s × %d arquivos exportados"
                                 % (tabela, restaurado["n8n"].get(tabela), exp[chave]))
    resultado = {"backup": pasta.name, "em": datetime.now().isoformat(timespec="seconds"),
                 "ok": not problemas, "problemas": problemas, "passos_s": passos,
                 "duracao_s": round(time.monotonic() - inicio, 2), "comparacao": comparacao}
    (pasta / ("verificacao_%s.json" % datetime.now().strftime("%Y-%m-%d_%H%M%S"))).write_text(
        json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print("verificação de %s: %s em %.1f s (%s)" % (pasta.name, "OK" if not problemas else "DIVERGE",
                                                    resultado["duracao_s"],
                                                    ", ".join("%s %.1fs" % kv for kv in passos.items())))
    for chave in ("fopa.licitacoes", "fopa.paginas", "fopa.verificacoes", "fopa.schema_migracoes",
                  "n8n.workflow_entity", "n8n.credentials_entity"):
        c = comparacao.get(chave)
        if c:
            print("  %-26s restaurado %8d | manifesto %s/%s" % (chave, c["restaurado"], c["antes"], c["depois"]))
    for p in problemas:
        print("  PROBLEMA: %s" % p)
    return 0 if not problemas else 2


# ------------------------------------------------------------------ CLI
def main(argv=None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Backup da stack FOPA (bancos fopa e n8n + export do n8n).")
    p.add_argument("--destino", type=Path, default=DESTINO_PADRAO, help="pasta dos backups (padrão backups/)")
    p.add_argument("--manter", type=int, default=MANTER_PADRAO, help="quantos backups guardar (padrão 7)")
    p.add_argument("--verificar", nargs="?", const="", metavar="PASTA",
                   help="restaura num Postgres efêmero e compara (padrão: o mais recente)")
    a = p.parse_args(argv)
    if a.manter < 1:
        p.error("--manter precisa ser >= 1")
    try:
        if a.verificar is not None:
            pasta = Path(a.verificar) if a.verificar else _mais_recente(a.destino)
            return verificar(pasta.resolve())
        return fazer_backup(a.destino.resolve(), a.manter)
    except Falha as e:
        print("erro: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
