# -*- coding: utf-8 -*-
"""
Congela o acervo num snapshot: `acervo/{AAAA-MM-DD_HHMM}/` + manifesto.

    python migracao/congelar.py [--destino acervo] [--seco]

POR QUE ISTO EXISTE
  A v3 importa o que a v2 ja produziu e NUNCA reprocessa (Plano, secao 9,
  passo 0; ADR-014). Mas `amostras/` e `saidas/` sao escritos por outros
  terminais (`70 preparar`, `13_reverificar.py`) enquanto a v3 e construida,
  e um importador que le a arvore viva importa um estado que ninguem
  consegue reproduzir depois. O snapshot e o unico estado que o importador
  enxerga; o manifesto e o que permite dizer "o disco divergiu do que foi
  importado" em vez de descobrir isso pela contagem que nao bate.

O QUE ENTRA
  - `saidas/` inteiro (~298 MB): auditorias, RELATORIOs, `_agente/` com
    `paginas.json` / `finalizado.json` / `respostas.json`, os `_*.json`.
  - de `amostras/<pasta>/`, so a EVIDENCIA: `_inventario.json`, `_metadados.md`,
    `RELATORIO.html`, `_gabarito.json`, `_itens_api.json`. Arquivos soltos
    na raiz de `amostras/` (`_resumo_geral.json` etc.) nao sao pasta e ficam.
  - PDFs (~3,6 GB) NAO sao copiados: entram no manifesto por
    `{caminho, bytes, sha256, mtime}`. Copiar dobraria o disco para
    proteger algo que o sha256 ja protege -- o importador confere o hash e
    aborta se o disco divergir.

O QUE FICA DE FORA, E POR QUE
  - mtime ha menos de 60 s: outro terminal pode estar no meio da escrita;
    copiar agora seria congelar um arquivo pela metade. Pulado e listado;
    repetir o passe pega na proxima.
  - `.json` que nao parseia: e destroco ou escrita em andamento. O
    importador teria que tratar o erro de qualquer jeito; melhor que o
    snapshot ja diga qual e.
  Tudo que foi pulado esta em `manifesto.json:pulados` e em `relatorio.md`.

IDEMPOTENCIA
  Dois passes sobre o mesmo disco produzem manifestos identicos fora do
  bloco `execucao` (carimbo e caminho). Listas sao ordenadas por caminho
  posix e os hashes vem do conteudo -- e assim que o teste confere.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent

# O pacote `scripts/fopa` e reaproveitado, nunca reimplementado: quem sabe
# ler os 13 esquemas de `_inventario.json` e `fopa.inventario`.
if str(RAIZ / "scripts") not in sys.path:
    sys.path.insert(0, str(RAIZ / "scripts"))
from fopa import inventario  # noqa: E402

# Os cinco nomes que constituem "evidencia" numa pasta de amostra. Tudo o mais
# (PDFs, `.txt` de OCR, ZIPs desempacotados) ou e reproduzivel ou e pesado.
EVIDENCIA = frozenset({
    "_inventario.json", "_metadados.md", "RELATORIO.html",
    "_gabarito.json", "_itens_api.json",
})
JANELA_S = 60          # mtime mais novo que isto = "ainda sendo escrito"
BLOCO = 1 << 20        # 1 MiB por leitura: PDFs de 60 MB nao cabem na RAM x threads


# ---------------------------------------------------------------- arquivos
def _rel(raiz: Path, p: Path) -> str:
    # Caminho posix relativo a raiz: e a CHAVE do manifesto, e precisa ser a
    # mesma no Windows local e no Linux do worker.
    return p.relative_to(raiz).as_posix()


def _longo(p: Path) -> str:
    r"""
    Caminho pronto para abrir no Windows sem o teto de 260 caracteres.

    O acervo tem pastas de 250 caracteres (Capep-Saude-SP, com o nome
    repetido no .xlsx); somar `acervo/AAAA-MM-DD_HHMM/` estoura o MAX_PATH e
    o `open` devolve um FileNotFoundError enganoso. O prefixo `\\?\` desliga o
    limite sem depender da politica de registro da maquina.
    """
    s = str(p)
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        # o prefixo so vale com caminho absoluto; relativo vira "nao existe"
        return "\\\\?\\" + os.path.abspath(s)
    return s


def _mtime_iso(st: os.stat_result) -> str:
    # Com o fuso da maquina: sem ele o manifesto dizia "03:12" sem dizer de onde. O importador (_ts)
    # aceita os dois formatos, e os manifestos antigos, sem fuso, seguem valendo como -03:00.
    return datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds")


def _hash(p: Path) -> str:
    h = hashlib.sha256()
    with io.open(_longo(p), "rb") as f:
        for bloco in iter(lambda: f.read(BLOCO), b""):
            h.update(bloco)
    return h.hexdigest()


def _copia_com_hash(origem: Path, destino: Path | None) -> str:
    """
    Copia em blocos calculando o sha256 do que PASSOU pelo cano. Assim o hash
    do manifesto e o do byte gravado, nao o de uma segunda leitura da origem
    (que poderia ja ter mudado). `destino=None` so calcula (modo seco).
    """
    h = hashlib.sha256()
    if destino is not None:
        os.makedirs(_longo(destino.parent), exist_ok=True)
        saida = io.open(_longo(destino), "wb")
    else:
        saida = None
    try:
        with io.open(_longo(origem), "rb") as f:
            for bloco in iter(lambda: f.read(BLOCO), b""):
                h.update(bloco)
                if saida is not None:
                    saida.write(bloco)
    finally:
        if saida is not None:
            saida.close()
    if destino is not None:
        # preserva o mtime da origem: e ele que o importador compara
        st = origem.stat()
        os.utime(_longo(destino), (st.st_atime, st.st_mtime))
    return h.hexdigest()


def _motivo_para_pular(p: Path, st: os.stat_result, agora_ts: float, janela_s: int) -> str | None:
    idade = agora_ts - st.st_mtime
    if idade < janela_s:
        return "mtime ha %.0f s (< %d s): possivelmente em escrita" % (max(idade, 0), janela_s)
    if p.suffix.lower() == ".json":
        try:
            with io.open(_longo(p), encoding="utf-8") as f:
                json.load(f)
        except (OSError, ValueError, UnicodeDecodeError) as e:
            return "JSON invalido: %s" % str(e)[:80]
    return None


# ---------------------------------------------------------------- selecao
def _arquivos_saidas(raiz: Path) -> list[Path]:
    base = raiz / "saidas"
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*") if p.is_file())


def _pastas_amostras(raiz: Path) -> list[Path]:
    base = raiz / "amostras"
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir())


def _evidencia_amostras(pastas: list[Path]) -> list[Path]:
    # `rglob` e nao `iterdir`: `_fixture/` guarda pastas dentro de pasta, e o
    # plano diz `amostras/**/{...}`.
    out: list[Path] = []
    for pasta in pastas:
        out.extend(p for p in pasta.rglob("*") if p.is_file() and p.name in EVIDENCIA)
    return sorted(out)


def _pdfs_amostras(pastas: list[Path]) -> list[Path]:
    # `.PDF.pdf` e `.PDF` existem no acervo: compara o sufixo em minusculas.
    out: list[Path] = []
    for pasta in pastas:
        out.extend(p for p in pasta.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    return sorted(out)


# ---------------------------------------------------------------- contagens
def _provedor(auditoria: Path) -> str:
    """
    Chave de provedor de uma auditoria: `uso.provedor/uso.modelo`, ou so o
    modelo quando o provedor esta vazio. Medido em 24/09/2026 nas 106
    auditorias: `uso.provedor` e "claude-code" nas 93 do agente e "" nas 13
    da API (11 `claude-opus-5`, 2 `gpt-5.6-sol`), onde so `uso.modelo` fala.
    """
    try:
        with io.open(auditoria, encoding="utf-8") as f:
            uso = json.load(f).get("uso") or {}
    except (OSError, ValueError, AttributeError):
        return "(ilegivel)"
    prov = (uso.get("provedor") or "").strip()
    modelo = (uso.get("modelo") or "").strip() or "(sem modelo)"
    return "%s/%s" % (prov, modelo) if prov else modelo


def _contagens(raiz: Path, pastas: list[Path], copiados: list[dict], pdfs: list[dict]) -> dict:
    caminhos = [c["caminho"] for c in copiados]
    nomes = Counter(Path(c).name for c in caminhos)

    # "Canonica" e a auditoria em `saidas/<pasta>/auditoria.json` -- a conta
    # que o plano usa (106 em 24/09: 93 + 11 + 2; inclui `_openai_*` e
    # `_injecao_furtiva`, que a secao 9 passo 4 depois rotula de experimento).
    # As de nivel mais fundo (`_varredura_*/<modelo>/`, `_ensaio_simulado/`)
    # ficam em conta separada; misturadas, 106 viraria 115 e ninguem saberia
    # por que o numero do manifesto nao bate com o do plano.
    def _canonica(c: str) -> bool:
        partes = c.split("/")
        return len(partes) == 3 and partes[0] == "saidas"

    auditorias = Counter(
        _provedor(raiz / c) for c in caminhos
        if _canonica(c) and Path(c).name == "auditoria.json"
    )
    experimentais = sum(
        1 for c in caminhos
        if c.startswith("saidas/") and Path(c).name == "auditoria.json" and not _canonica(c)
    )

    # Inventario "valido" = o que `fopa.inventario.ler` aceita; e o mesmo leitor
    # que o importador vai usar, entao a contagem daqui e a que ele vera.
    sem_inventario, pdf_fora = [], []
    pdfs_por_pasta: dict[str, set[str]] = {}
    for p in pdfs:
        partes = p["caminho"].split("/")
        pdfs_por_pasta.setdefault(partes[1], set()).add("/".join(partes[2:]))
    for pasta in pastas:
        inv = inventario.ler(str(pasta))
        if inv is None:
            sem_inventario.append(pasta.name)
        # Pasta sem inventario com PDF dentro tambem conta como "PDF fora do
        # inventario": para o importador da secao 9 passo 2 e a mesma coisa,
        # um PDF que nenhum inventario reivindica (`fora_inventario`).
        # 'arquivo' e o nome no disco; 'nome' e 'titulo' sao aliases antigos.
        listados = set()
        for a in (inv or {}).get("arquivos") or []:
            if isinstance(a, dict):
                for k in ("arquivo", "nome", "titulo"):
                    if a.get(k):
                        listados.add(str(a[k]).replace("\\", "/"))
        if pdfs_por_pasta.get(pasta.name, set()) - listados:
            pdf_fora.append(pasta.name)

    return {
        "pastas_amostras": len(pastas),
        "pastas_amostras_especiais": sum(1 for p in pastas if p.name.startswith("_")),
        "pastas_saidas": len([p for p in (raiz / "saidas").iterdir() if p.is_dir()])
        if (raiz / "saidas").is_dir() else 0,
        # so `amostras/<pasta>/_inventario.json`: os de dentro de `_fixture/`
        # sao copiados, mas nao sao pastas do acervo
        "inventarios": sum(
            1 for c in caminhos if len(c.split("/")) == 3 and c.startswith("amostras/")
            and Path(c).name == "_inventario.json"
            and inventario.ler(str((raiz / c).parent)) is not None
        ),
        "pdfs": len(pdfs),
        "pdfs_bytes": sum(p["bytes"] for p in pdfs),
        "auditorias": sum(auditorias.values()),
        "auditorias_por_provedor": dict(sorted(auditorias.items())),
        "auditorias_experimentais": experimentais,
        "finalizados": nomes.get("finalizado.json", 0),
        "paginas": nomes.get("paginas.json", 0),
        "respostas_agente": nomes.get("respostas.json", 0),
        "relatorios_html": nomes.get("RELATORIO.html", 0),
        "pastas_sem_inventario": len(sem_inventario),
        "pastas_sem_inventario_lista": sem_inventario,
        "pastas_pdf_fora_inventario": len(pdf_fora),
        "pastas_pdf_fora_inventario_lista": pdf_fora,
        "copias": len(copiados),
        "copias_bytes": sum(c["bytes"] for c in copiados),
    }


# ---------------------------------------------------------------- relatorio
def _relatorio_md(man: dict) -> str:
    c = man["contagens"]
    ex = man["execucao"]
    linhas = [
        "# Snapshot do acervo — %s" % ex["carimbo"],
        "",
        "- gerado em: %s%s" % (ex["gerado_em"], "  (modo seco: nada gravado)" if ex["seco"] else ""),
        "- raiz: `%s`" % ex["raiz"],
        "- janela de escrita: arquivos com mtime < %d s foram pulados" % ex["janela_s"],
        "",
        "## Contagens",
        "",
        "- %d pastas em amostras (%d especiais, prefixo `_`)" % (
            c["pastas_amostras"], c["pastas_amostras_especiais"]),
        "- %d inventarios (`_inventario.json` legiveis por `fopa.inventario.ler`)" % c["inventarios"],
        "- %d PDFs no disco, %s bytes (nao copiados; sha256 no manifesto)" % (
            c["pdfs"], format(c["pdfs_bytes"], ",").replace(",", ".")),
        "- %d auditoria.json canonicas (`saidas/<pasta>/`) por provedor:" % c["auditorias"],
    ]
    for prov, n in c["auditorias_por_provedor"].items():
        linhas.append("    - %s: %d" % (prov, n))
    linhas += [
        "- %d auditoria.json experimentais (mais fundo que `saidas/<pasta>/`)" % c["auditorias_experimentais"],
        "- %d finalizado.json" % c["finalizados"],
        "- %d paginas.json" % c["paginas"],
        "- %d respostas.json (agente)" % c["respostas_agente"],
        "- %d RELATORIO.html" % c["relatorios_html"],
        "- %d pastas de amostras sem inventario" % c["pastas_sem_inventario"],
        "- %d pastas com PDF fora do inventario" % c["pastas_pdf_fora_inventario"],
        "- %d arquivos copiados, %s bytes" % (
            c["copias"], format(c["copias_bytes"], ",").replace(",", ".")),
        "",
        "## Pulados (%d)" % len(man["pulados"]),
        "",
    ]
    if man["pulados"]:
        linhas += ["- `%s` — %s" % (p["caminho"], p["motivo"]) for p in man["pulados"]]
    else:
        linhas.append("nenhum")
    if c["pastas_sem_inventario_lista"]:
        linhas += ["", "## Pastas sem inventario", ""]
        linhas += ["- %s" % n for n in c["pastas_sem_inventario_lista"]]
    if c["pastas_pdf_fora_inventario_lista"]:
        linhas += ["", "## Pastas com PDF fora do inventario", ""]
        linhas += ["- %s" % n for n in c["pastas_pdf_fora_inventario_lista"]]
    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------- principal
def _pasta_snapshot(raiz: Path, destino: str, agora: datetime) -> Path:
    base = raiz / destino
    nome = agora.strftime("%Y-%m-%d_%H%M")
    alvo = base / nome
    # Dois passes no mesmo minuto nao podem se misturar: o segundo ganha sufixo.
    n = 2
    while alvo.exists():
        alvo = base / ("%s_%d" % (nome, n))
        n += 1
    return alvo


def congelar(raiz: Path | str = RAIZ, destino: str = "acervo", seco: bool = False,
             agora: datetime | None = None, janela_s: int = JANELA_S,
             workers: int | None = None, log=None) -> dict:
    """
    Gera o snapshot e devolve o manifesto (com `snapshot` = caminho da pasta).

    `agora` existe para os testes fixarem o carimbo; `janela_s` para nao
    esperar 60 s numa arvore recem-criada.
    """
    raiz = Path(raiz).resolve()
    agora = agora or datetime.now()
    agora_ts = datetime.now().timestamp()
    snap = _pasta_snapshot(raiz, destino, agora)
    log = log or (lambda *_: None)
    workers = workers or min(8, (os.cpu_count() or 2) * 2)

    pastas = _pastas_amostras(raiz)
    candidatos = _arquivos_saidas(raiz) + _evidencia_amostras(pastas)
    pdfs_disco = _pdfs_amostras(pastas)
    log("%d arquivos para copiar, %d PDFs para hashear, %d threads"
        % (len(candidatos), len(pdfs_disco), workers))

    pulados: list[dict] = []
    copiar: list[tuple[Path, os.stat_result]] = []
    for p in candidatos:
        st = p.stat()
        motivo = _motivo_para_pular(p, st, agora_ts, janela_s)
        if motivo:
            pulados.append({"caminho": _rel(raiz, p), "motivo": motivo})
        else:
            copiar.append((p, st))
    hashear: list[tuple[Path, os.stat_result]] = []
    for p in pdfs_disco:
        st = p.stat()
        if agora_ts - st.st_mtime < janela_s:
            pulados.append({"caminho": _rel(raiz, p),
                            "motivo": "mtime ha %.0f s (< %d s): possivelmente em escrita"
                            % (max(agora_ts - st.st_mtime, 0), janela_s)})
        else:
            hashear.append((p, st))

    def copia(item):
        p, st = item
        dest = None if seco else snap / p.relative_to(raiz)
        return {"caminho": _rel(raiz, p), "bytes": st.st_size,
                "sha256": _copia_com_hash(p, dest), "mtime": _mtime_iso(st)}

    def hasheia(item):
        p, st = item
        return {"caminho": _rel(raiz, p), "bytes": st.st_size,
                "sha256": _hash(p), "mtime": _mtime_iso(st)}

    # 3,6 GB de PDF em disco: o gargalo e I/O, e threads bastam para
    # sobrepor leitura e hash sem o custo de processos.
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            copiados = list(pool.map(copia, copiar))
            pdfs = list(pool.map(hasheia, hashear))
    except BaseException:
        # Um snapshot pela metade e pior que nenhum: sem manifesto ele parece
        # inteiro para quem olha a pasta. Apaga e deixa a excecao subir.
        if not seco and snap.exists():
            shutil.rmtree(_longo(snap), ignore_errors=True)
        raise
    copiados.sort(key=lambda c: c["caminho"])
    pdfs.sort(key=lambda c: c["caminho"])
    pulados.sort(key=lambda c: c["caminho"])

    man = {
        "versao": 1,
        "execucao": {
            "carimbo": snap.name,
            "gerado_em": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "raiz": str(raiz),
            "snapshot": str(snap),
            "janela_s": janela_s,
            "seco": seco,
        },
        "evidencia_amostras": sorted(EVIDENCIA),
        "contagens": _contagens(raiz, pastas, copiados, pdfs),
        "pastas": {
            "amostras": [p.name for p in pastas],
            "saidas": sorted(p.name for p in (raiz / "saidas").iterdir() if p.is_dir())
            if (raiz / "saidas").is_dir() else [],
        },
        "copias": copiados,
        "pdfs": pdfs,
        "pulados": pulados,
    }
    man["relatorio_md"] = _relatorio_md(man)
    if not seco:
        snap.mkdir(parents=True, exist_ok=True)
        with io.open(snap / "manifesto.json", "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in man.items() if k != "relatorio_md"},
                      f, ensure_ascii=False, indent=1)
        with io.open(snap / "relatorio.md", "w", encoding="utf-8") as f:
            f.write(man["relatorio_md"])
    man["snapshot"] = str(snap)
    return man


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Congela amostras/ e saidas/ num snapshot com manifesto.")
    ap.add_argument("--destino", default="acervo", help="pasta (relativa a raiz) onde nasce o snapshot")
    ap.add_argument("--seco", action="store_true", help="so conta e relata; nao grava nada")
    ap.add_argument("--raiz", default=str(RAIZ), help=argparse.SUPPRESS)  # para testes
    ap.add_argument("--janela", type=int, default=JANELA_S, help="segundos de mtime para considerar 'em escrita'")
    ap.add_argument("--threads", type=int, default=None)
    args = ap.parse_args(argv)

    # Console do Windows em cp1252 engasga no travessao do relatorio; o mesmo
    # remedio dos scripts 10/11/12.
    for _f in (sys.stdout, sys.stderr):
        if hasattr(_f, "reconfigure"):
            _f.reconfigure(encoding="utf-8", errors="replace")

    def log(msg):
        print(msg, flush=True)

    man = congelar(args.raiz, destino=args.destino, seco=args.seco,
                   janela_s=args.janela, workers=args.threads, log=log)
    print(man["relatorio_md"])
    if not args.seco:
        print("snapshot: %s" % man["snapshot"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
