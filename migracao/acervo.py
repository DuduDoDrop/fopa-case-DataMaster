# -*- coding: utf-8 -*-
"""
Leitura de um snapshot do acervo v2 (`acervo/<carimbo>/`, feito por congelar.py).

SÓ LÊ. Nenhum método escreve, e nenhum lê `amostras/` ou `saidas/` vivos — a
não ser `ler_pdf`, que busca os bytes de um PDF no disco vivo e CONFERE o sha
contra o manifesto antes de devolver. Os PDFs não entram no snapshot (3,8 GB);
o manifesto guarda o sha de cada um, e é essa conferência que faz o snapshot
valer como fotografia: um PDF que mudou depois do congelamento aborta a
importação em vez de entrar calado (seção 9, passo 0).
"""
from __future__ import annotations

import glob
import hashlib
import io
import json
import os

from fopa import inventario


class DivergenciaManifesto(RuntimeError):
    """O disco vivo não bate com o que o manifesto viu no congelamento."""


def _json(caminho: str):
    with io.open(caminho, encoding="utf-8") as f:
        return json.load(f)


def _json_ou_none(caminho: str):
    try:
        return _json(caminho)
    except (OSError, ValueError):
        return None


class Acervo:
    def __init__(self, snapshot: str, amostras_vivo: str | None = None):
        self.raiz = os.path.abspath(snapshot)
        self.amostras = os.path.join(self.raiz, "amostras")
        self.saidas = os.path.join(self.raiz, "saidas")
        caminho_manifesto = os.path.join(self.raiz, "manifesto.json")
        with open(caminho_manifesto, "rb") as f:
            bruto = f.read()
        self.manifesto_sha256 = hashlib.sha256(bruto).hexdigest()
        self.manifesto = json.loads(bruto.decode("utf-8"))
        self.carimbo = (self.manifesto.get("execucao") or {}).get("carimbo") or os.path.basename(self.raiz)
        self.amostras_vivo = os.path.abspath(amostras_vivo) if amostras_vivo else None
        self._pdfs: dict[str, dict] = {}
        self._mtimes = {c["caminho"].replace("\\", "/"): c.get("mtime")
                        for c in self.manifesto.get("copias") or []}
        for p in self.manifesto.get("pdfs") or []:
            partes = p["caminho"].replace("\\", "/").split("/", 2)
            if len(partes) == 3 and partes[0] == "amostras":
                self._pdfs.setdefault(partes[1], {})[partes[2]] = p

    def mtime(self, caminho_relativo: str) -> str | None:
        """Quando o arquivo copiado foi escrito (hora local, como o manifesto grava).

        Serve de data para o que o v2 não carimbou — a auditoria da API não
        grava quando terminou; o mtime do arquivo é o melhor indício, e entra
        marcado como inferido.
        """
        return self._mtimes.get(caminho_relativo.replace("\\", "/"))

    # ------------------------------------------------------------ amostras
    def pastas_com_inventario(self) -> list[tuple[str, dict]]:
        """(pasta, inventário normalizado), pastas especiais `_*` de fora."""
        return list(inventario.todos(self.amostras))

    def disco(self, pasta: str) -> dict:
        """{nome: {"sha256", "bytes", "caminho"}} dos PDFs que o manifesto viu na pasta."""
        return self._pdfs.get(pasta, {})

    def ler_pdf(self, pasta: str, nome: str) -> bytes:
        """Bytes do PDF no disco vivo, conferidos contra o sha do manifesto."""
        if not self.amostras_vivo:
            raise DivergenciaManifesto("amostras vivo não informado: não há de onde ler PDF")
        d = self.disco(pasta).get(nome)
        if d is None:
            raise DivergenciaManifesto("%s/%s não está no manifesto" % (pasta, nome))
        caminho = os.path.join(self.amostras_vivo, pasta, nome)
        try:
            with open(caminho, "rb") as f:
                dados = f.read()
        except OSError as e:
            raise DivergenciaManifesto("%s/%s sumiu do disco depois do snapshot: %s"
                                       % (pasta, nome, e)) from e
        sha = hashlib.sha256(dados).hexdigest()
        if sha != d["sha256"]:
            raise DivergenciaManifesto("%s/%s mudou depois do snapshot: manifesto %s…, disco %s…"
                                       % (pasta, nome, d["sha256"][:12], sha[:12]))
        return dados

    def gabarito(self, pasta: str) -> dict | None:
        return _json_ou_none(os.path.join(self.amostras, pasta, "_gabarito.json"))

    def itens_api(self, pasta: str):
        return _json_ou_none(os.path.join(self.amostras, pasta, "_itens_api.json"))

    def tem_itens_api(self, pasta: str) -> bool:
        return os.path.isfile(os.path.join(self.amostras, pasta, "_itens_api.json"))

    # ------------------------------------------------------------ saidas
    def auditoria(self, pasta: str) -> tuple[dict, str] | None:
        """(auditoria, sha256 dos bytes) da execução canônica da pasta."""
        caminho = os.path.join(self.saidas, pasta, "auditoria.json")
        if not os.path.isfile(caminho):
            return None
        with open(caminho, "rb") as f:
            bruto = f.read()
        return json.loads(bruto.decode("utf-8")), hashlib.sha256(bruto).hexdigest()

    def _agente(self, pasta: str, arquivo: str):
        return _json_ou_none(os.path.join(self.saidas, "_agente", pasta, arquivo))

    def tem_leitura(self, pasta: str) -> bool:
        return os.path.isfile(os.path.join(self.saidas, "_agente", pasta, "paginas.json"))

    def leitura(self, pasta: str) -> dict | None:
        """O `paginas.json` inteiro (com texto). Pesado: carregar uma de cada vez."""
        return self._agente(pasta, "paginas.json")

    def assinatura(self, pasta: str) -> dict | None:
        return self._agente(pasta, "assinatura.json")

    def respostas_agente(self, pasta: str) -> tuple[list, str] | None:
        caminho = os.path.join(self.saidas, "_agente", pasta, "respostas.json")
        if not os.path.isfile(caminho):
            return None
        with open(caminho, "rb") as f:
            bruto = f.read()
        return json.loads(bruto.decode("utf-8")).get("respostas") or [], hashlib.sha256(bruto).hexdigest()

    def finalizado(self, pasta: str) -> dict | None:
        return self._agente(pasta, "finalizado.json")

    def corpus(self) -> list[dict]:
        d = _json_ou_none(os.path.join(self.saidas, "_corpus_escopo.json")) or {}
        return d.get("registros") or []

    def livro(self) -> dict:
        d = _json_ou_none(os.path.join(self.saidas, "_livro.json")) or {}
        return d.get("licitacoes") or {}

    def livro_download(self) -> dict:
        d = _json_ou_none(os.path.join(self.saidas, "_livro_download.json")) or {}
        return d.get("registros") or {}

    def lote(self, modelo: str = "claude-opus-5") -> dict | None:
        return _json_ou_none(os.path.join(self.saidas, "_lote_%s.json" % modelo))

    def harness(self) -> list[tuple[str, dict]]:
        """(nome do arquivo, conteúdo) de cada `_harness_*.json`."""
        saida = []
        for f in sorted(glob.glob(os.path.join(self.saidas, "_harness_*.json"))):
            d = _json_ou_none(f)
            if isinstance(d, dict):
                saida.append((os.path.basename(f), d))
        return saida

    def experimentos(self) -> list[tuple[str, dict, str]]:
        """(pasta, auditoria, sha) das saídas experimentais `saidas/_*/auditoria.json`."""
        saida = []
        for f in sorted(glob.glob(os.path.join(self.saidas, "_*", "auditoria.json"))):
            pasta = os.path.basename(os.path.dirname(f))
            if pasta == "_agente":
                continue
            with open(f, "rb") as h:
                bruto = h.read()
            try:
                saida.append((pasta, json.loads(bruto.decode("utf-8")),
                              hashlib.sha256(bruto).hexdigest()))
            except ValueError:
                continue
        return saida

    def execucoes_legado(self) -> list[dict]:
        caminho = os.path.join(self.saidas, "_execucoes.jsonl")
        saida = []
        if not os.path.isfile(caminho):
            return saida
        with io.open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    saida.append(json.loads(linha))
                except ValueError:
                    continue
        return saida


__all__ = ["Acervo", "DivergenciaManifesto"]
