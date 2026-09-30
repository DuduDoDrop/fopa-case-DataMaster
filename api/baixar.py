# -*- coding: utf-8 -*-
"""
`POST /jobs/baixar` — baixa os documentos de uma licitação (W21 Baixar, plano seções 5 e 6).

A política é a do `28_baixar_licitacao`, importada, não reescrita: o nome do
arquivo, `pncp.baixar_arquivo` (sem retry: quem espera 30 s e repete é o n8n),
e `avaliar_baixado` — tetos de 120/400 MB e 600 páginas, "PDF de 0 páginas →
tentar ZIP", ZIP aninhado, recusa por formato. A medida de páginas/texto/OCR
é a `medir` do `41_censo_pdf`. O que muda é só ONDE o resultado mora: em vez
de `amostras/<pasta>/_inventario.json`, o storage content-addressed e a
tabela `arquivos`.

QUEM DECIDE O ESTADO É O n8n
  O job devolve `estado_sugerido` e não chama `fn_transicao`: a máquina de
  estados é do fluxo (W21 passo 8), e um worker que também transicionasse
  seria um segundo dono do mesmo estado.

POR QUE IMPORTLIB
  Os scripts começam com dígito (`28_...`, `41_...`), então `import` não os
  alcança. O plano (seção 6) manda importar por `importlib` — nunca copiar a
  regra para cá.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from fopa import pncp
from migracao import regras

from . import CAMINHO_SCRIPTS, banco, converter
from .storage import Storage, chave_pdf

# A MESMA frase que `migracao.regras.arquivos_da_pasta` grava no container do
# acervo: o site mostra as duas origens lado a lado.
MOTIVO_CONTAINER = "ZIP entregue como .pdf; o conteúdo foi extraído no download"

_trava = threading.Lock()
_scripts: dict[str, object] = {}


def _script(arquivo: str, nome_modulo: str):
    """Carrega um script de `scripts/` uma vez por processo (e o mesmo objeto sempre)."""
    with _trava:
        if nome_modulo not in _scripts:
            spec = importlib.util.spec_from_file_location(nome_modulo, os.path.join(CAMINHO_SCRIPTS, arquivo))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _scripts[nome_modulo] = mod
        return _scripts[nome_modulo]


def m28():
    return _script("28_baixar_licitacao.py", "fopa_script_28_baixar_licitacao")


def m41():
    return _script("41_censo_pdf.py", "fopa_script_41_censo_pdf")


# ------------------------------------------------------------------ regras do 28
def nome_do_documento(doc: dict) -> str:
    """
    "%02d - <tipo> - <título>.pdf", sem os caracteres que o Windows recusa.

    COPIADA de `28_baixar_licitacao.baixar()` (28:549-552), linha a linha: ela
    vive dentro do laço do 28, que imprime e grava em `amostras/`, e não há
    função para chamar. `test_nome_do_arquivo_e_o_mesmo_do_28` roda o 28 de
    verdade e compara — se alguém mudar lá, o teste daqui acusa. O nome é o
    marcador de citação: um nome diferente para o mesmo documento separaria
    a leitura da v3 da do acervo.
    """
    seq = doc.get("sequencialDocumento")
    tipo = (doc.get("tipoDocumentoNome") or "Documento").strip()
    titulo = (doc.get("titulo") or "sem-titulo").strip()
    base = re.sub(r'[<>:"/\\|?*]', "", "%02d - %s - %s" % (seq, tipo, titulo))
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base


_SO_FORMATO = {"formato_nao_suportado", "zip_container"}
_TEM_PDF = {"ok", "alias_duplicado"}


def estado_sugerido(status: list[str]) -> str:
    """
    O estado da licitação depois do download (W21 passo 7, `28:562-602`).

    A MESMA leitura da regra que `migracao.plano._estado` aplicou ao acervo:
    ≥1 PDF bom → baixada_ok; só formato (e containers) → formato_nao_suportado,
    que não se retenta; alguma falha de rede → falha_rede, que o backoff do W10
    retenta; senão sem_pdf_legivel. `alias_duplicado` conta como PDF bom: o
    conteúdo está no controle sob outro nome.
    """
    if any(s in _TEM_PDF for s in status):
        return "baixada_ok"
    if status and all(s in _SO_FORMATO for s in status):
        return "formato_nao_suportado"
    if "falha_rede" in status:
        return "falha_rede"
    return "sem_pdf_legivel"


# ------------------------------------------------------------------ linhas
@dataclass
class Linha:
    """Uma linha de `arquivos` antes de ter id. `pai` é NOME (o container do ZIP)."""

    nome: str
    status: str
    seq: int | None = None
    tipo: str | None = None
    titulo: str | None = None
    sha256: str | None = None
    bytes: int | None = None
    origem_url: str | None = None
    baixado_em: datetime | None = None
    formato_real: str | None = None
    motivo: str | None = None
    pai: str | None = None
    paginas: int | None = None
    chars: int | None = None
    requer_ocr: bool | None = None
    storage_key: str | None = None
    ativo_pncp: bool | None = None
    proveniencia: dict = field(default_factory=dict)


def _guardar_pdf(ab, doc: dict, storage: Storage, cnpj: str, ano: int, seq_lic: int,
                 quando: datetime, pai: str | None = None, convertido_de: str | None = None) -> Linha:
    """PDF aceito: bytes no storage, medida do 41, linha `ok`."""
    with open(ab.caminho, "rb") as f:
        dados = f.read()
    sha = hashlib.sha256(dados).hexdigest()
    # a chave é da LICITAÇÃO (seq do controle), como no importador; o
    # sequencial do documento fica em `arquivos.seq`
    chave = chave_pdf(cnpj, ano, seq_lic, sha)
    if not storage.existe(chave):
        storage.put(chave, dados)
    medida = m41().medir(ab.caminho) or {}
    prov = {"origem": "worker:/jobs/baixar"}
    if convertido_de:
        # o fluxo de exceção (api/converter.py): este PDF foi gerado a partir do arquivo `pai`
        prov["convertido_de"] = convertido_de
        prov["de"] = pai
    elif pai:
        prov["de_zip"] = pai
    return Linha(
        nome=os.path.basename(ab.caminho), status="ok", seq=ab.seq, tipo=ab.tipo, titulo=ab.titulo,
        sha256=sha, bytes=len(dados), origem_url=ab.origem, baixado_em=quando,
        formato_real=m28().formato_real(ab.caminho), pai=pai,
        paginas=medida.get("pag"), chars=medida.get("chars"), requer_ocr=medida.get("requer_ocr"),
        # Filho de ZIP não passa por `avaliar_baixado` no 28 (entra como veio);
        # se nem o 41 abre, o motivo fica escrito em vez de sumir.
        motivo=("medida do 41 falhou: %s" % medida["erro"]) if medida.get("erro") else None,
        storage_key=chave, ativo_pncp=doc.get("statusAtivo"), proveniencia=prov)


def _le_como_pdf(caminho: str) -> bool:
    """A mesma regra da leitura (`extrator._e_pdf`): o cabeçalho %PDF no primeiro KB — a especificação tolera bytes arbitrários antes."""
    try:
        with open(caminho, "rb") as f:
            return b"%PDF" in f.read(1024)
    except OSError:
        return False


def e_folha(controle: str) -> bool:
    """
    Confirmada como folha: a regra de escopo com o rótulo humano mandando (`fn_escopo_efetivo`, db/031) — a mesma
    que o site e a fila usam. Licitação que o banco não conhece não está confirmada: para ela os tetos valem.
    """
    with banco.conectar() as conn:
        r = conn.execute("SELECT fn_escopo_efetivo(controle, coalesce(escopo_dentro, false)) FROM licitacoes"
                         " WHERE controle = %s", (controle,)).fetchone()
    return bool(r and r[0])


def _baixar_todos(controle: str, docs: list[dict], storage: Storage, pasta: str, avisar,
                  sem_teto: bool = False) -> tuple[list, list, list]:
    """
    O laço do `28.baixar()` (28:539-616), sem print e sem `amostras/`. `sem_teto`: licitação de folha pega TODOS os
    arquivos — nenhum teto de páginas ou de MB recusa documento dela.
    """
    mod28 = m28()
    cnpj, ano, seq_lic = regras.partes_controle(controle)
    linhas: list[Linha] = []
    recusados: list[dict] = []
    falhas: list[dict] = []
    total_bytes = 0
    for i, doc in enumerate(docs, start=1):
        seq = doc.get("sequencialDocumento")
        tipo = (doc.get("tipoDocumentoNome") or "Documento").strip()
        base = nome_do_documento(doc)
        avisar(etapa="baixando", arquivo=base, i=i, n=len(docs))
        destino = os.path.join(pasta, base)
        try:
            ab = pncp.baixar_arquivo(doc, destino)
        except Exception as e:                                    # noqa: BLE001
            # Falha de rede vai para o registro (28:555-576): recusa local não
            # se retenta, falha de rede sim — e a diferença decide o estado.
            erro = "%s: %s" % (type(e).__name__, str(e)[:160])
            falhas.append({"arquivo": base, "seq": seq, "tipo": tipo, "erro": erro, "origem": doc.get("url")})
            linhas.append(Linha(nome=base, status="falha_rede", seq=seq, tipo=doc.get("tipoDocumentoNome"),
                                titulo=doc.get("titulo"), origem_url=doc.get("url"), motivo=erro,
                                ativo_pncp=doc.get("statusAtivo"),
                                proveniencia={"origem": "worker:/jobs/baixar"}))
            continue
        quando = datetime.now(timezone.utc)
        # Lido ANTES de avaliar: se for ZIP, o `desempacotar` apaga o container.
        formato = mod28.formato_real(destino)
        recusa, dentro_zip = mod28.avaliar_baixado(destino, ab, doc, total_bytes, sem_teto=sem_teto)
        if dentro_zip:
            linhas.append(Linha(nome=base, status="zip_container", seq=seq, tipo=ab.tipo, titulo=ab.titulo,
                                sha256=ab.sha256, bytes=ab.bytes, origem_url=ab.origem, baixado_em=quando,
                                formato_real=formato, motivo=MOTIVO_CONTAINER, ativo_pncp=doc.get("statusAtivo"),
                                proveniencia={"origem": "worker:/jobs/baixar",
                                              "extraidos": [os.path.basename(x.caminho) for x in dentro_zip]}))
            for extra in dentro_zip:
                total_bytes += extra.bytes
                linhas.append(_guardar_pdf(extra, doc, storage, cnpj, ano, seq_lic, quando, pai=base))
            continue
        # O PyMuPDF abre DOCX, XLSX e imagem como documento: o teto de páginas passa e o arquivo ficava 'ok', mas a leitura
        # só lê o que tem %PDF no começo (extrator._e_pdf) e pulava ele — 98 Word/Excel e 62 do acervo v2 nunca lidos, 34
        # licitações de folha sem texto (25/09 noite). O download aceita como PDF o que a leitura lê como PDF.
        if not recusa and os.path.exists(destino) and not _le_como_pdf(destino):
            recusa = "abre, mas não é PDF — o arquivo é %s" % formato
        if recusa and regras._status_da_recusa(recusa) == "formato_nao_suportado" and os.path.exists(destino):
            # O FLUXO DE EXCEÇÃO: antes de recusar pelo formato, tenta virar PDF (api/converter.py) — RTF, DOC, DOCX,
            # XLS, HTML, imagem, RAR. O original fica `convertido` e cada PDF gerado entra como filho, como no ZIP.
            try:
                gerados = converter.para_pdf(destino, formato, pasta, base)
            except converter.NaoConverteu as e:
                recusa = "%s — a conversão para PDF falhou: %s" % (recusa, e)
            except Exception as e:                                # noqa: BLE001
                # Um erro que o conversor não previu não derruba o download da licitação inteira: o arquivo fica como
                # ficava antes do fluxo de exceção (formato_nao_suportado), com o erro escrito no motivo.
                recusa = "%s — a conversão para PDF quebrou: %s: %s" % (recusa, type(e).__name__, str(e)[:120])
            else:
                linhas.append(Linha(nome=base, status="convertido", seq=seq, tipo=ab.tipo, titulo=ab.titulo,
                                    sha256=ab.sha256, bytes=ab.bytes, origem_url=ab.origem, baixado_em=quando,
                                    formato_real=formato,
                                    motivo="convertido para PDF (%s)" % ", ".join(sorted({g.de for g in gerados})),
                                    ativo_pncp=doc.get("statusAtivo"),
                                    proveniencia={"origem": "worker:/jobs/baixar",
                                                  "convertidos": [os.path.basename(g.caminho) for g in gerados]}))
                for g in gerados:
                    extra = pncp.ArquivoBaixado(seq=ab.seq, tipo=ab.tipo, titulo=ab.titulo, caminho=g.caminho,
                                                bytes=os.path.getsize(g.caminho), sha256="",
                                                baixado_em=ab.baixado_em, origem=ab.origem)
                    total_bytes += extra.bytes
                    linhas.append(_guardar_pdf(extra, doc, storage, cnpj, ano, seq_lic, quando, pai=base,
                                               convertido_de=g.de))
                continue
        if recusa:
            try:
                os.remove(destino)
            except OSError:
                pass
            # O sequencial vai junto (28:599-605): sem ele o W70 acusaria o
            # mesmo arquivo recusado como novo para sempre.
            recusados.append({"seq": seq, "arquivo": base, "motivo": recusa, "bytes": ab.bytes,
                              "origem": doc.get("url")})
            linhas.append(Linha(nome=base, status=regras._status_da_recusa(recusa), seq=seq, tipo=ab.tipo,
                                titulo=ab.titulo, sha256=ab.sha256, bytes=ab.bytes, origem_url=ab.origem,
                                baixado_em=quando, formato_real=formato, motivo=recusa,
                                ativo_pncp=doc.get("statusAtivo"),
                                proveniencia={"origem": "worker:/jobs/baixar"}))
            continue
        total_bytes += ab.bytes
        linhas.append(_guardar_pdf(ab, doc, storage, cnpj, ano, seq_lic, quando))
    return linhas, recusados, falhas


_UPSERT = (
    "INSERT INTO arquivos (controle, seq, tipo, titulo, nome, sha256, bytes, origem_url, baixado_em,"
    " formato_real, status, motivo, pai_id, alias_de, paginas, chars, requer_ocr, storage_key, ativo_pncp,"
    " proveniencia)"
    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    " ON CONFLICT (controle, nome) DO UPDATE SET seq = EXCLUDED.seq, tipo = EXCLUDED.tipo,"
    " titulo = EXCLUDED.titulo, sha256 = EXCLUDED.sha256, bytes = EXCLUDED.bytes,"
    " bytes_aproximado = false, origem_url = EXCLUDED.origem_url, baixado_em = EXCLUDED.baixado_em,"
    " formato_real = EXCLUDED.formato_real, status = EXCLUDED.status, motivo = EXCLUDED.motivo,"
    " pai_id = EXCLUDED.pai_id, alias_de = EXCLUDED.alias_de, paginas = EXCLUDED.paginas,"
    " chars = EXCLUDED.chars, requer_ocr = EXCLUDED.requer_ocr, storage_key = EXCLUDED.storage_key,"
    " ativo_pncp = EXCLUDED.ativo_pncp, proveniencia = EXCLUDED.proveniencia"
    # Uma retentativa que tropeça na rede não apaga o que já se baixou: o PDF
    # bom continua `ok` (e no storage); a falha fica em `falhas_download`.
    " WHERE arquivos.status <> 'ok' OR EXCLUDED.status <> 'falha_rede'"
    " RETURNING id")

_COLUNAS_SAIDA = ("id, seq, tipo, titulo, nome, bytes, sha256, paginas AS pag, chars, requer_ocr, status,"
                  " storage_key, formato_real, pai_id, alias_de, motivo")


def _gravar(conn, controle: str, linhas: list[Linha]) -> dict[str, int]:
    """Upsert das linhas por (controle, nome), com alias por sha. Devolve {nome: id}."""
    if not conn.execute("SELECT 1 FROM licitacoes WHERE controle = %s FOR UPDATE", (controle,)).fetchone():
        raise LookupError("licitação %s não existe" % controle)
    ids: dict[str, int] = {}
    for ln in linhas:
        alias_de = None
        status = ln.status
        if status == "ok":
            # Mesmo conteúdo já no controle sob OUTRO nome: um objeto só no
            # storage e uma leitura só do texto (storage.py, "POR QUE CHAVES
            # CONTENT-ADDRESSED"). `nome <> ` para que rebaixar o mesmo
            # documento não o declare alias de si mesmo.
            outro = conn.execute(
                "SELECT id FROM arquivos WHERE controle = %s AND sha256 = %s AND status = 'ok'"
                " AND nome <> %s ORDER BY id LIMIT 1", (controle, ln.sha256, ln.nome)).fetchone()
            if outro:
                status, alias_de = "alias_duplicado", outro["id"]
        r = conn.execute(_UPSERT, (
            controle, ln.seq, ln.tipo, ln.titulo, ln.nome, ln.sha256, ln.bytes, ln.origem_url, ln.baixado_em,
            ln.formato_real, status, ln.motivo, ids.get(ln.pai) if ln.pai else None, alias_de, ln.paginas,
            ln.chars, ln.requer_ocr, ln.storage_key, ln.ativo_pncp, Jsonb(ln.proveniencia))).fetchone()
        if r is None:          # o WHERE do upsert preservou um `ok` anterior
            r = conn.execute("SELECT id FROM arquivos WHERE controle = %s AND nome = %s",
                             (controle, ln.nome)).fetchone()
        ids[ln.nome] = r["id"]
    return ids


def baixar_licitacao(controle: str, docs: list[dict], storage: Storage, progresso=None) -> dict:
    """
    O corpo do job. `docs` é a lista do PNCP `/arquivos` já filtrada por
    `statusAtivo` e ordenada por `sequencialDocumento` pelo n8n (W21 passo 4).

    Tudo o que se baixou vai para o banco numa transação só, no fim: um job
    que morre no meio não deixa metade das linhas (os objetos no storage que
    sobrarem são content-addressed e inofensivos; o próximo download os reusa).
    """
    avisar = progresso or (lambda **_: None)
    sem_teto = e_folha(controle)
    pasta = tempfile.mkdtemp(prefix="fopa-baixar-")
    try:
        linhas, recusados, falhas = _baixar_todos(controle, docs, storage, pasta, avisar, sem_teto)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)

    avisar(etapa="gravando", linhas=len(linhas))
    with banco.conectar() as conn:
        conn.row_factory = dict_row
        with conn.transaction():
            ids = _gravar(conn, controle, linhas)
            finais = conn.execute("SELECT %s FROM arquivos WHERE id = ANY(%%s) ORDER BY id" % _COLUNAS_SAIDA,
                                  (list(ids.values()),)).fetchall()
    por_nome = {f["nome"]: f for f in finais}
    for r in recusados:
        r["id"] = ids.get(r["arquivo"])
    for f in falhas:
        f["id"] = ids.get(f["arquivo"])
    arquivos = [f for f in finais if f["status"] in ("ok", "alias_duplicado", "zip_container", "convertido")]
    return {"arquivos": arquivos, "recusados": recusados, "falhas_download": falhas,
            "estado_sugerido": estado_sugerido([por_nome[ln.nome]["status"] for ln in linhas]),
            "total_bytes": sum(f["bytes"] or 0 for f in arquivos if f["status"] == "ok")}


__all__ = ["baixar_licitacao", "nome_do_documento", "estado_sugerido", "e_folha", "m28", "m41", "MOTIVO_CONTAINER"]
