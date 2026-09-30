#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ponto de restauração da produção FOPA.

Um ponto é TUDO o que a produção precisa para voltar a um instante, numa pasta só:

    pontos/<AAAA-MM-DD_HHMMSS>-<rotulo>/
        banco/<carimbo>/          backup.py completo (fopa + n8n + export do n8n) — e verificado
                                  (restaurado num Postgres efêmero, contagens iguais) antes de o ponto valer
        imagens.tar.gz            `docker save` das imagens que estão rodando (api e worker; camadas em comum
                                  guardadas uma vez)
        PONTO.json                commit do git, tag do .env, imagem de cada container, crontab, sha256 de tudo
        RESTAURAR.md              os comandos exatos para voltar a ESTE ponto

A pasta nasce `.parcial-…` e só ganha o nome final quando tudo deu certo. **Retenção: `--manter 1`** — o ponto novo
só apaga os antigos DEPOIS de completo e verificado; se qualquer passo falhar, o anterior continua lá. Os segredos
(docker/.env, N8N_ENCRYPTION_KEY) NÃO entram: continuam na máquina e no cofre, como no backup.py.

Só biblioteca padrão e o `docker`/`git`/`crontab` da máquina, como o backup.py.

Uso (na EC2, em /srv/projeto-fopa):
    python3 docker/ponto.py criar v3-estavel          # cria, verifica, e só então apaga o anterior
    python3 docker/ponto.py listar
Na máquina local (a cópia fora da AWS, também com um ponto só):
    python docker/ponto.py puxar                       # traz o ponto mais novo da EC2 para ~/FOPA-pontos/

Saída: 0 ok; 1 falha (nada é apagado).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO_PADRAO = RAIZ / "pontos"
LOCAL_PADRAO = Path.home() / "FOPA-pontos"
RE_PONTO = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}-[a-z0-9-]+$")
CONTAINERS = ("fopa-api", "fopa-worker")
LIVRE_MIN_GB = 3.0


class Falha(RuntimeError):
    pass


def _rodar(args: list[str], cwd: Path | None = None) -> str:
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise Falha("%s falhou (%d): %s" % (" ".join(args[:3]), r.returncode, (r.stderr or r.stdout).strip()[-800:]))
    return r.stdout


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _pontos(destino: Path) -> list[Path]:
    """Os pontos completos (nome certo e PONTO.json), do mais novo ao mais velho."""
    if not destino.is_dir():
        return []
    return sorted((p for p in destino.iterdir() if p.is_dir() and RE_PONTO.match(p.name)
                   and (p / "PONTO.json").is_file()), key=lambda p: p.name, reverse=True)


def _reter(destino: Path, manter: int) -> list[str]:
    apagados = []
    for p in _pontos(destino)[manter:]:
        shutil.rmtree(p)
        apagados.append(p.name)
    for p in destino.glob(".parcial-*"):            # sobra de uma rodada que morreu no meio
        shutil.rmtree(p, ignore_errors=True)
        apagados.append(p.name)
    return apagados


def _imagem(container: str) -> str:
    return _rodar(["docker", "inspect", "--format", "{{.Config.Image}}", container]).strip()


def _restaurar_md(nome: str, info: dict) -> str:
    tag = info["env_imagem_tag"]
    banco = info["banco"]["pasta"]
    return """# Voltar ao ponto `{nome}`

Criado em {criado}. Commit `{commit}` (tag git `{tag_git}`). Imagens: {imagens}.

> Antes de voltar, tire um backup do estado atual (`python3 docker/backup.py`): voltar **substitui** o banco.

```bash
cd /srv/projeto-fopa
python3 docker/backup.py                                        # o estado de agora, por garantia
git fetch --tags 2>/dev/null; git checkout {commit}               # o código do ponto (a VPS recebe por `git push vps`)
gunzip -c pontos/{nome}/imagens.tar.gz | docker load            # as imagens do ponto
sed -i "s/^FOPA_IMAGEM_TAG=.*/FOPA_IMAGEM_TAG={tag}/" docker/.env
cd docker
docker compose stop fopa-n8n fopa-worker fopa-api
docker exec -i fopa-postgres psql -U postgres -c "DROP DATABASE fopa WITH (FORCE)" -c "CREATE DATABASE fopa"
docker exec -i fopa-postgres psql -U postgres -c "DROP DATABASE n8n WITH (FORCE)" -c "CREATE DATABASE n8n OWNER n8n"
docker exec -i fopa-postgres pg_restore -U postgres -d fopa --exit-on-error < ../pontos/{nome}/banco/{banco}/fopa.dump
docker exec -i fopa-postgres pg_restore -U postgres -d n8n  --exit-on-error < ../pontos/{nome}/banco/{banco}/n8n.dump
docker compose --profile migrate run --rm fopa-migrate           # 0 aplicadas; reaplica as senhas dos papéis
docker compose up -d                                             # a MESMA N8N_ENCRYPTION_KEY do docker/.env
```

Se o worker e a api estavam em imagens diferentes neste ponto ({imagens}), suba cada um na sua:
`FOPA_IMAGEM_TAG=<tag> docker compose up -d --no-deps <serviço>`.

Conferir: `curl -s https://licitacaofopa.com.br/api/saude` e as contagens do `banco/{banco}/manifesto.json`.
""".format(nome=nome, criado=info["criado_em"], commit=info["git"]["commit"], tag_git=info["git"].get("tag") or "—",
           imagens=", ".join("%s = `%s`" % kv for kv in info["imagens"].items()), tag=tag, banco=banco)


def criar(rotulo: str, destino: Path, manter: int, tag_git: str | None) -> int:
    if not re.fullmatch(r"[a-z0-9-]+", rotulo):
        raise Falha("rótulo só com a-z, 0-9 e '-': %r" % rotulo)
    inicio = time.monotonic()
    livre = shutil.disk_usage(RAIZ).free / 1e9
    if livre < LIVRE_MIN_GB:
        raise Falha("só %.1f GB livres (mínimo %.1f): nada foi feito" % (livre, LIVRE_MIN_GB))
    nome = "%s-%s" % (datetime.now().strftime("%Y-%m-%d_%H%M%S"), rotulo)
    destino.mkdir(parents=True, exist_ok=True)
    parcial, final = destino / (".parcial-" + nome), destino / nome
    parcial.mkdir()
    try:
        imagens = {c: _imagem(c) for c in CONTAINERS}
        commit = _rodar(["git", "rev-parse", "HEAD"], cwd=RAIZ).strip()
        env = (RAIZ / "docker" / ".env").read_text(encoding="utf-8")
        tag_env = re.search(r"^FOPA_IMAGEM_TAG=(\S+)", env, re.M)

        print("[ponto] banco (backup.py + verificação)…", flush=True)
        _rodar([sys.executable, str(RAIZ / "docker" / "backup.py"), "--destino", str(parcial / "banco"), "--manter", "1"])
        pasta_banco = next(p for p in (parcial / "banco").iterdir() if p.is_dir() and (p / "manifesto.json").is_file())
        verif = _rodar([sys.executable, str(RAIZ / "docker" / "backup.py"), "--verificar", str(pasta_banco)])

        print("[ponto] imagens %s…" % ", ".join(sorted(set(imagens.values()))), flush=True)
        arq = parcial / "imagens.tar.gz"
        with open(arq, "wb") as saida:
            save = subprocess.Popen(["docker", "save", *sorted(set(imagens.values()))], stdout=subprocess.PIPE)
            gz = subprocess.Popen(["gzip", "-1"], stdin=save.stdout, stdout=saida)
            save.stdout.close()
            if gz.wait() != 0 or save.wait() != 0:
                raise Falha("docker save | gzip falhou")

        crontab = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        (parcial / "crontab.txt").write_text(crontab, encoding="utf-8")
        info = {"nome": nome, "rotulo": rotulo, "criado_em": datetime.now().isoformat(timespec="seconds"),
                "git": {"commit": commit, "tag": tag_git}, "env_imagem_tag": tag_env.group(1) if tag_env else None,
                "imagens": imagens, "banco": {"pasta": pasta_banco.name,
                                              "verificacao": verif.strip().splitlines()[0] if verif.strip() else None},
                "arquivos": {p.relative_to(parcial).as_posix(): {"bytes": p.stat().st_size, "sha256": _sha256(p)}
                             for p in sorted(parcial.rglob("*")) if p.is_file()}}
        (parcial / "RESTAURAR.md").write_text(_restaurar_md(nome, info), encoding="utf-8")
        (parcial / "PONTO.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        parcial.rename(final)
    except BaseException:
        shutil.rmtree(parcial, ignore_errors=True)
        raise
    apagados = _reter(destino, manter)
    total = sum(a["bytes"] for a in info["arquivos"].values())
    print("[ponto] %s: %.2f GB em %.0f s -> %s" % (nome, total / 1e9, time.monotonic() - inicio, final))
    print("[ponto] banco: %s" % info["banco"]["verificacao"])
    if apagados:
        print("[ponto] retenção (%d): apagados %s" % (manter, ", ".join(apagados)))
    return 0


def listar(destino: Path) -> int:
    for p in _pontos(destino):
        info = json.loads((p / "PONTO.json").read_text(encoding="utf-8"))
        total = sum(a["bytes"] for a in info["arquivos"].values())
        print("%s  %.2f GB  commit %s  imagens %s" % (p.name, total / 1e9, info["git"]["commit"][:7],
                                                      ", ".join(sorted(set(info["imagens"].values())))))
    return 0


def puxar(host: str, remoto: str, local: Path, manter: int) -> int:
    """Traz o ponto mais novo da EC2 (tar pelo ssh), confere os sha256 e só então aplica a retenção local."""
    nomes = _rodar(["ssh", host, "ls -1 %s" % remoto]).split()
    candidatos = sorted((n for n in nomes if RE_PONTO.match(n)), reverse=True)
    if not candidatos:
        raise Falha("nenhum ponto em %s:%s" % (host, remoto))
    nome = candidatos[0]
    local.mkdir(parents=True, exist_ok=True)
    if (local / nome / "PONTO.json").is_file():
        print("[ponto] %s já está em %s" % (nome, local))
        return 0
    parcial = local / (".parcial-" + nome)
    shutil.rmtree(parcial, ignore_errors=True)
    parcial.mkdir()
    try:
        with subprocess.Popen(["ssh", host, "tar -C %s/%s -cf - ." % (remoto, nome)], stdout=subprocess.PIPE) as p:
            r = subprocess.run(["tar", "-xf", "-"], stdin=p.stdout, cwd=parcial)
            if p.wait() != 0 or r.returncode != 0:
                raise Falha("tar pelo ssh falhou")
        info = json.loads((parcial / "PONTO.json").read_text(encoding="utf-8"))
        for rel, a in info["arquivos"].items():
            if _sha256(parcial / rel) != a["sha256"]:
                raise Falha("%s chegou diferente (sha256)" % rel)
        parcial.rename(local / nome)
    except BaseException:
        shutil.rmtree(parcial, ignore_errors=True)
        raise
    apagados = _reter(local, manter)
    print("[ponto] %s -> %s (sha256 conferido)%s" % (nome, local / nome,
                                                     "; apagados %s" % ", ".join(apagados) if apagados else ""))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ponto de restauração da produção FOPA (um só, o mais novo).")
    sub = p.add_subparsers(dest="acao", required=True)
    c = sub.add_parser("criar")
    c.add_argument("rotulo")
    c.add_argument("--tag-git", default=None, help="tag git que marca o código deste ponto")
    c.add_argument("--manter", type=int, default=1)
    c.add_argument("--destino", type=Path, default=DESTINO_PADRAO)
    lst = sub.add_parser("listar")
    lst.add_argument("--destino", type=Path, default=DESTINO_PADRAO)
    px = sub.add_parser("puxar")
    px.add_argument("--host", default="fopa")
    px.add_argument("--remoto", default="/srv/projeto-fopa/pontos")
    px.add_argument("--local", type=Path, default=LOCAL_PADRAO)
    px.add_argument("--manter", type=int, default=1)
    a = p.parse_args(argv)
    try:
        if a.acao == "criar":
            return criar(a.rotulo, a.destino, a.manter, a.tag_git)
        if a.acao == "listar":
            return listar(a.destino)
        return puxar(a.host, a.remoto, a.local, a.manter)
    except Falha as e:
        print("[ponto] FALHOU: %s (nada foi apagado)" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
