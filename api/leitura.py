# -*- coding: utf-8 -*-
"""
`POST /jobs/paginas` — congela o texto de uma licitação (W22 Ler, plano seções 5 e 6).

É o `70_extracao_por_agente preparar` sem o disco do v2: mesma leitura
(`extrator.carregar_paginas` com `Condicoes` de observador, que já roda
`furtivo.varrer`, OCR e `ocr.limpar_assinatura`), mesma assinatura de texto,
mesmas condições — gravadas em `leituras` + `paginas` numa transação só.

POR QUE MATERIALIZAR UMA PASTA
  `carregar_paginas(pasta)` lê "todos os PDFs de uma pasta", e é essa função,
  intocada, que produziu as 741 leituras do acervo. No storage os objetos são
  content-addressed (`pdf/.../{sha}.pdf`), sem nome; o nome é o marcador de
  citação ("=== ARQUIVO x | PÁGINA n ===") e mora em `arquivos.nome`. Então
  cada leitura monta um scratch `{tmp}/{slug}/` com os bytes do storage sob o
  nome original e chama a função sobre ele. Mudar a assinatura dela para
  receber bytes criaria uma segunda leitura "equivalente" — e equivalência é
  hipótese, não medição.

IDENTIDADE DA LEITURA (db/015)
  (controle, assinatura_nomes, versao_ocr): o mesmo texto sob os mesmos nomes,
  lido pelo mesmo OCR, é a mesma leitura — reusa, não duplica. Outro OCR
  (host × imagem) é outra leitura, visível lado a lado (ADR-008), nunca
  sobrescrita.

OCR FORÇADO E ROTAÇÃO (db/043, Pacote B, 26/09/2026)
  O RN-19 decide o OCR por caracteres/página, e três defeitos passam por ele
  com texto ruim: a camada de texto cortada à direita, o carimbo de
  autenticação em texto por cima de uma página em imagem e o escaneado de
  cabeça para baixo. O operador marca o ARQUIVO (`arquivos.forcar_ocr`,
  `arquivos.girar`, scripts/82_forcar_ocr.py) e a marcação vale para toda
  releitura. Aqui o arquivo marcado é trocado, NA PASTA TEMPORÁRIA, por uma
  cópia só de imagem com o mesmo nome e o mesmo número de páginas: o
  `carregar_paginas` intocado vê página sem texto e faz o OCR sozinho, a
  citação continua apontando o arquivo e a página originais, e o arquivo
  aparece em `condicoes.arquivos_ocr`. A marcação entra na `versao_ocr`
  (`versao_com_marcas`): outro OCR, outro texto — sem isso o ON CONFLICT do
  `_gravar` devolveria a leitura antiga sempre que o texto se repetisse.
"""
from __future__ import annotations

import functools
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time

import pymupdf
from PIL import Image
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from fopa import condicoes as cond
from fopa import extrator, ocr
from fopa import recuperacao as rec
from migracao import regras

from . import banco
from .storage import ConteudoDivergente, Storage

RE_LEPTONICA = re.compile(r"leptonica-([0-9][0-9.]*)")


class NomeInseguro(ValueError):
    """`arquivos.nome` que escaparia do scratch se virasse caminho."""


# ------------------------------------------------------------------ assinatura
def assinatura_texto(paginas) -> dict[str, str]:
    """
    arquivo -> SHA-256 do texto lido dele (espaços colapsados, páginas unidas por \\f).

    COPIADA de `70_extracao_por_agente._gravar_assinatura` (70:308-316), não
    reescrita e não importada: importar o 70_ desliga `ProvedorClaude` e
    envenena `sys.modules["anthropic"]` no processo inteiro (70:81-92). É o
    critério de gêmea do acervo; um cálculo "parecido" separaria gêmeas que o
    v2 juntou. `test_paginas_reproduz_a_leitura_do_70` confere contra o
    `assinatura.json` que o 70_ gravou.
    """
    por_arquivo: dict[str, list[str]] = {}
    for p in paginas:
        por_arquivo.setdefault(p.arquivo, []).append(re.sub(r"\s+", " ", p.texto).strip())
    return {a: hashlib.sha256("\f".join(t).encode("utf-8")).hexdigest()
            for a, t in por_arquivo.items()}


# ------------------------------------------------------------------ versão do OCR
def _sha256_arquivo(caminho: str) -> str | None:
    if not os.path.isfile(caminho):
        return None
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


@functools.lru_cache(maxsize=4)
def _leptonica(exe: str) -> str:
    # O pytesseract só expõe a versão do Tesseract; a da leptonica está na
    # segunda linha de `tesseract --version` (1.84.1 na imagem e no host).
    r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
    m = RE_LEPTONICA.search((r.stdout or "") + (r.stderr or ""))
    if not m:
        raise ocr.OcrIndisponivel("`%s --version` não informa a leptonica" % exe)
    return m.group(1)


def versao_ocr() -> tuple[str, str]:
    """
    (versao_ocr, tessdata_sha256) do OCR que VAI ler — medidos, não declarados.

    Formato do plano (seção 9, passo 3): na imagem, que compila o Tesseract,
    `linux-5.4.0-src+leptonica-1.84.1+tessdata_fast:<12 hex>+x86_64`. Fora do
    Linux (o host Windows das medições, build MSVC do instalador) o prefixo é
    `<sistema>-<versão completa>` — `windows-5.4.0.20240606...` — e NUNCA
    `linux-...-src`: a ADR-008 mediu que os dois não leem igual, e é a
    `versao_ocr` que separa uma leitura da outra. Também não é o `host-...
    (inferida)` do legado, que é inferência sobre o passado.

    O sha é o do `por.traineddata` em uso, como `api.worker._tessdata_sha256`
    (`ocr.TESSDATA` é o que o pytesseract lê via TESSDATA_PREFIX).
    """
    amb = ocr.checar_ambiente()                   # levanta OcrIndisponivel: falha alto, antes de ler
    tessdata = _sha256_arquivo(os.path.join(ocr.TESSDATA, "por.traineddata"))
    if not tessdata:
        raise ocr.OcrIndisponivel("por.traineddata ausente em %s" % ocr.TESSDATA)
    tesseract = str(amb["tesseract"])
    sistema = platform.system().lower() or "desconhecido"
    base = ("linux-%s-src" % tesseract) if sistema == "linux" else ("%s-%s" % (sistema, tesseract))
    versao = "%s+leptonica-%s+tessdata_fast:%s+%s" % (
        base, _leptonica(ocr.TESSERACT_EXE), tessdata[:12], platform.machine() or "desconhecida")
    return versao, tessdata


def versao_com_marcas(versao: str, marcas: dict[str, int]) -> str:
    """
    A `versao_ocr` da leitura com OCR forçado: `<versão>+forcado:<12 hex>` do conjunto {arquivo: giro}.

    Sem marcação, a versão fica como era — as leituras de antes continuam reusáveis. Com marcação, cada
    configuração tem a sua chave: forçar outro arquivo ou girar outro ângulo é outra leitura, lado a lado.
    """
    if not marcas:
        return versao
    cfg = json.dumps(sorted([n, int(g)] for n, g in marcas.items()), ensure_ascii=False, separators=(",", ":"))
    return "%s+forcado:%s" % (versao, hashlib.sha256(cfg.encode("utf-8")).hexdigest()[:12])


# ------------------------------------------------------------------ scratch
def _nome_seguro(nome: str) -> str:
    # O nome vem do banco, escrito por três papéis e pelo importador do acervo.
    # Um "../x.pdf" viraria escrita fora do scratch; recusar é mais barato que
    # descobrir depois.
    if (not nome or nome in (".", "..") or "/" in nome or "\\" in nome or "\x00" in nome
            or os.path.basename(nome) != nome):
        raise NomeInseguro("nome de arquivo inseguro para o scratch: %r" % (nome,))
    return nome


def materializar(arquivos: list[dict], storage: Storage, pasta: str) -> dict[str, str]:
    """
    Escreve cada arquivo do storage em `pasta/<arquivos.nome>`. Devolve {nome: sha256 dos bytes}.

    Confere o sha dos bytes contra `arquivos.sha256`: o texto congelado tem de
    ser do arquivo que o banco diz, e objeto trocado no volume aborta a
    leitura em vez de congelar o texto errado com a procedência certa.
    """
    os.makedirs(pasta, exist_ok=True)
    hashes: dict[str, str] = {}
    for a in arquivos:
        nome = _nome_seguro(a["nome"])
        dados = storage.get(a["storage_key"])
        sha = hashlib.sha256(dados).hexdigest()
        if a.get("sha256") and a["sha256"].strip() != sha:
            raise ConteudoDivergente("%s: storage tem sha %s..., arquivos.sha256 diz %s..."
                                     % (nome, sha[:12], a["sha256"][:12]))
        with open(os.path.join(pasta, nome), "wb") as f:
            f.write(dados)
        hashes[nome] = sha
    return hashes


DPI_FORCADO = 300   # o OCR renderiza a 150 dpi (PERFIL_TEXTO); a imagem tem folga para isso


def so_imagem(caminho: str, girar: int = 0, dpi: int = DPI_FORCADO) -> int:
    """
    Reescreve o PDF em `caminho` como PDF só de imagem, página a página, girando `girar` graus no sentido horário.

    Tons de cinza em PNG (sem perda: o OCR lê o que o scanner viu, não um JPEG dele). Mesmo número de páginas, na
    mesma ordem — a página N da cópia é a página N do original. Devolve o número de páginas.
    """
    if girar not in (0, 90, 180, 270):
        raise ValueError("girar tem de ser 0, 90, 180 ou 270 (veio %r)" % (girar,))
    with pymupdf.open(caminho) as src, pymupdf.open() as out:
        for pg in src:
            pix = pg.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
            img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            del pix
            if girar:
                img = img.rotate(-girar, expand=True)          # PIL gira no anti-horário
            w, h = pg.rect.width, pg.rect.height
            if girar in (90, 270):
                w, h = h, w
            buf = io.BytesIO()
            img.save(buf, "PNG", optimize=False)
            nova = out.new_page(width=w, height=h)
            nova.insert_image(nova.rect, stream=buf.getvalue())
        n = len(out)
        dados = out.tobytes(garbage=3, deflate=True)
    with open(caminho, "wb") as f:
        f.write(dados)
    return n


# ------------------------------------------------------------------ o job
def _gravar(conn, controle: str, meta: dict, paginas, ids_arquivo: dict, arquivos_ocr: set) -> tuple[int, bool]:
    """Leitura + páginas + vigência, na transação de quem chama. Devolve (leitura_id, reusada)."""
    # Serializa leituras da mesma licitação: o índice parcial `leituras_vigente`
    # só admite uma vigente, e duas transações trocando a vigência ao mesmo
    # tempo morreriam uma na outra.
    if not conn.execute("SELECT 1 FROM licitacoes WHERE controle = %s FOR UPDATE", (controle,)).fetchone():
        raise LookupError("licitação %s não existe" % controle)
    r = conn.execute(
        "INSERT INTO leituras (controle, segundos, versao_ocr, tessdata_sha256, condicoes, hashes_bytes,"
        " assinatura, assinatura_conjunto, assinatura_nomes, modo_sugerido, chars_total,"
        " procedencia_texto, vigente)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'worker', false)"
        " ON CONFLICT (controle, assinatura_nomes, versao_ocr) DO NOTHING RETURNING id",
        (controle, meta["segundos"], meta["versao_ocr"], meta["tessdata_sha256"], Jsonb(meta["condicoes"]),
         Jsonb(meta["hashes_bytes"]), Jsonb(meta["assinatura"]), meta["assinatura_conjunto"],
         meta["assinatura_nomes"], meta["modo_sugerido"], meta["chars_total"])).fetchone()
    if r:
        lid, reusada = r["id"], False
        linhas = []
        for ordem, p in enumerate(paginas):
            # `ordem` é a posição na lista que `carregar_paginas` devolveu — a
            # precedência de documento com que o texto entra no prompt. O NUL
            # sai como no importador: o Postgres não guarda NUL em text, e
            # nenhum trecho citável tem NUL. A assinatura já foi calculada
            # sobre o texto cru, como o 70_ fazia.
            linhas.append((lid, ids_arquivo.get(p.arquivo), p.arquivo, p.numero, ordem,
                           p.texto.replace("\x00", ""), p.arquivo in arquivos_ocr))
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO paginas (leitura_id, arquivo_id, arquivo_nome, numero, ordem, texto,"
                            " via_ocr) VALUES (%s, %s, %s, %s, %s, %s, %s)", linhas)
    else:
        lid = conn.execute("SELECT id FROM leituras WHERE controle = %s AND assinatura_nomes = %s"
                           " AND versao_ocr = %s", (controle, meta["assinatura_nomes"],
                                                    meta["versao_ocr"])).fetchone()["id"]
        reusada = True
    # A leitura mais recente é a vigente, mesmo quando é uma reusada: ler de
    # novo e obter o texto de antes quer dizer que o de antes é o atual. A
    # anterior perde a vigência mas fica — `paginas` é imutável (ADR-011) e
    # execuções antigas continuam apontando para ela.
    conn.execute("UPDATE leituras SET vigente = false WHERE controle = %s AND vigente AND id <> %s",
                 (controle, lid))
    conn.execute("UPDATE leituras SET vigente = true WHERE id = %s AND NOT vigente", (lid,))
    conn.execute("UPDATE licitacoes SET leitura_vigente_id = %s WHERE controle = %s", (lid, controle))
    return lid, reusada


def ler_licitacao(controle: str, storage: Storage, progresso=None) -> dict:
    """
    O corpo do job: materializa, lê, grava. Sem página legível não grava nada
    (o W22 leva a `sem_pdf_legivel` por `n_paginas == 0`): uma leitura vigente
    vazia apagaria a vigência de uma leitura boa em troca de nada.
    """
    avisar = progresso or (lambda **_: None)
    versao, tessdata = versao_ocr()
    with banco.conectar() as conn:
        conn.row_factory = dict_row
        arquivos = conn.execute(
            "SELECT id, nome, sha256, storage_key, forcar_ocr, girar FROM arquivos WHERE controle = %s"
            " AND status = 'ok'"
            " AND storage_key IS NOT NULL ORDER BY id", (controle,)).fetchall()
    ids_arquivo = {a["nome"]: a["id"] for a in arquivos}
    # girar sem forçar não existe: girar a imagem só muda algo se o texto vier do OCR
    marcas = {a["nome"]: int(a["girar"]) for a in arquivos if a["forcar_ocr"] or a["girar"]}

    raiz = tempfile.mkdtemp(prefix="fopa-leitura-")
    try:
        # O scratch leva o slug (controle com `/` trocado por `-`, como a
        # coluna gerada de licitacoes) só para quem inspecionar o /tmp saber
        # de quem é; o que importa para a leitura são os nomes dos arquivos.
        pasta = os.path.join(raiz, controle.replace("/", "-"))
        avisar(etapa="materializando", arquivos=len(arquivos))
        hashes = materializar(arquivos, storage, pasta)
        # O que termina em .pdf e não é PDF (DOCX, ZIP com nome de PDF) o
        # carregar_paginas pula sozinho; o 70_ registrava a lista em
        # `nao_pdf` para constar como não lido. Mesma regra, mesmo campo.
        nao_pdf = sorted(n for n in hashes if not extrator._e_pdf(os.path.join(pasta, n)))
        # A marcação vale só para o que é PDF: o que não é, o carregar_paginas pula de qualquer jeito.
        marcas = {n: g for n, g in marcas.items() if n in hashes and n not in nao_pdf}
        for i, (nome, girar) in enumerate(sorted(marcas.items()), start=1):
            avisar(etapa="rasterizando", arquivo=nome, i=i, n=len(marcas), girar=girar)
            so_imagem(os.path.join(pasta, nome), girar=girar)
        versao = versao_com_marcas(versao, marcas)

        lidos = []

        def por_arquivo(nome, diag):
            lidos.append(nome)
            avisar(etapa="lendo", arquivo=nome, i=len(lidos), n=len(hashes) - len(nao_pdf),
                   paginas=diag.paginas, ocr=diag.requer_ocr)

        c = cond.Condicoes()
        t0 = time.time()
        paginas = extrator.carregar_paginas(pasta, progresso=por_arquivo, observador=c)
        segundos = round(time.time() - t0, 3)
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    condicoes = {"arquivos_ocr": c.arquivos_ocr, "paginas_ocr": c.paginas_ocr,
                 "furtivos": c.furtivos, "nao_pdf": nao_pdf}
    if marcas:
        # Só quando há: a leitura sem marcação tem as mesmas condições de sempre (e as do 70_).
        condicoes["ocr_forcado"] = {n: {"girar": g} for n, g in sorted(marcas.items())}
    if not paginas:
        return {"leitura_id": None, "n_paginas": 0, "chars_total": 0, "modo_sugerido": None,
                "condicoes": condicoes, "assinatura_conjunto": None, "versao_ocr": versao,
                "reusada": False, "segundos": segundos, "furtivos_suspeitos": 0, "furtivos_suspeitos_textos": []}

    assinatura = assinatura_texto(paginas)
    meta = {"segundos": segundos, "versao_ocr": versao, "tessdata_sha256": tessdata,
            "condicoes": condicoes, "hashes_bytes": hashes, "assinatura": assinatura,
            "assinatura_conjunto": regras.assinatura_conjunto(assinatura),
            "assinatura_nomes": regras.assinatura_nomes(assinatura),
            "modo_sugerido": rec.escolher_modo(paginas),
            "chars_total": sum(len(p) for p in paginas)}
    avisar(etapa="gravando", paginas=len(paginas))
    with banco.conectar() as conn:
        conn.row_factory = dict_row
        with conn.transaction():
            lid, reusada = _gravar(conn, controle, meta, paginas, ids_arquivo, set(c.arquivos_ocr))
    # O detector acha texto escondido em quase todo PDF (timbre branco, camada de OCR): aqui ele é classificado
    # e guardado com o texto (api/injecao.py, db/028), e o que sobe ao W22 — e ao aviso — são só os SUSPEITOS.
    suspeitos: list[str] = []
    if c.furtivos:
        from . import injecao
        with banco.conectar() as conn:
            conn.row_factory = dict_row
            injecao.varrer_leitura(conn, storage, lid)
            conn.commit()
            suspeitos = injecao.furtivos_para_condicoes(conn, lid) or []
    return {"leitura_id": lid, "n_paginas": len(paginas), "chars_total": meta["chars_total"],
            "modo_sugerido": meta["modo_sugerido"], "condicoes": condicoes,
            "assinatura_conjunto": meta["assinatura_conjunto"], "versao_ocr": versao,
            "reusada": reusada, "segundos": segundos,
            "furtivos_suspeitos": len(suspeitos), "furtivos_suspeitos_textos": suspeitos[:20]}


__all__ = ["ler_licitacao", "assinatura_texto", "versao_ocr", "versao_com_marcas", "materializar", "so_imagem",
           "NomeInseguro"]
