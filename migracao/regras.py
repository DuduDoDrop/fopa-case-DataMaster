# -*- coding: utf-8 -*-
"""
O que cada peça do acervo v2 vira na v3 — funções puras, sem banco e sem disco.

POR QUE SEPARADO DO IMPORTADOR
  A migração tem dezenas de decisões pequenas ("este PDF é alias ou está fora
  do inventário?", "qual das duas pastas é a canônica?"), e cada uma nasceu de
  um caso real do acervo. Aqui elas são funções de dado para dado, testáveis
  com dicionários de três linhas. O importador só aplica o resultado.

  O acervo tem 14 esquemas de `_inventario.json` e 7 formatos de entrada de
  arquivo, escritos por três programas ao longo de dois dias. Nenhum é
  reescrito: `fopa.inventario.ler` normaliza os nomes, e o que falta aqui é
  decidir o STATUS de cada arquivo contra o que o manifesto viu no disco.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fopa import distribuicao
from fopa.extrator import _apelido, _casa
from fopa.verificador import nao_encontrou

RE_CONTROLE = re.compile(r"^(\d{14})-\d+-(\d+)/(\d{4})$")
RE_DATA = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2})(?::\d{2})?)?")

# Brasília sem horário de verão desde 2019: o PNCP publica hora local sem fuso,
# e -03:00 fixo é a leitura correta de toda data do acervo (2025-2026).
FUSO_BRASILIA = "-03:00"


# ------------------------------------------------------------- identidade
def partes_controle(controle: str) -> tuple[str, int, int]:
    """`CNPJ-1-SEQ/ANO` -> (cnpj, ano, seq). Levanta se não for controle (ADR-013)."""
    m = RE_CONTROLE.match((controle or "").strip())
    if not m:
        raise ValueError("não é número de controle do PNCP: %r" % (controle,))
    return m.group(1), int(m.group(3)), int(m.group(2))


def fim_prazo(bruto) -> tuple[str | None, bool | None]:
    """
    Fim do prazo como timestamptz ISO em Brasília, e se o PNCP declarou a hora.

    Só data (`2026-10-08`) vira meia-noite com `tem_hora=False`: o site mostra
    o dia e não inventa um horário. Texto que não é data vira (None, None) —
    "prazo não informado" é informação, não zero.
    """
    m = RE_DATA.match(str(bruto or "").strip())
    if not m:
        return None, None
    dia, hora = m.group(1), m.group(2)
    try:
        datetime.strptime(dia, "%Y-%m-%d")
    except ValueError:
        return None, None
    return "%sT%s:00%s" % (dia, hora or "00:00", FUSO_BRASILIA), bool(hora)


# ------------------------------------------------------------- arquivos
@dataclass
class ArquivoLegado:
    """Uma linha de `arquivos` antes de ter id. `pai`/`alias_de` são NOMES."""

    nome: str
    status: str
    seq: int | None = None
    tipo: str | None = None
    titulo: str | None = None
    sha256: str | None = None
    bytes: int | None = None
    bytes_aproximado: bool = False
    origem_url: str | None = None
    motivo: str | None = None
    paginas: int | None = None
    chars: int | None = None
    requer_ocr: bool | None = None
    ativo_pncp: bool | None = None
    pai: str | None = None
    alias_de: str | None = None
    proveniencia: dict = field(default_factory=dict)
    # Os bytes estão no disco com este sha: dá para copiar para o storage.
    tem_bytes: bool = False
    # Veio de `inventario.arquivos` (e não do disco ou das recusas): é o que
    # conta como "declarado" para saber se uma leitura é limpa.
    do_inventario: bool = False
    pasta: str | None = None


def _int(v) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _bool(v) -> bool | None:
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    if s in ("true", "sim", "1", "yes"):
        return True
    if s in ("false", "nao", "não", "0", "no"):
        return False
    return None


def _status_da_recusa(motivo: str) -> str:
    """A mesma frase que o `28` grava vira o status — sem reinterpretar."""
    m = (motivo or "").lower()
    if "o arquivo é" in m or "zip sem nenhum pdf" in m:
        return "formato_nao_suportado"
    if "corrompido" in m or "ilegível" in m:
        return "corrompido"
    return "recusado_politica"


def arquivos_da_pasta(inv: dict, disco: dict, contaminada: bool = False) -> list[ArquivoLegado]:
    """
    Os arquivos de UMA pasta do acervo, com status, a partir do inventário
    (já normalizado por `fopa.inventario.ler`) e do que o manifesto viu no
    disco (`{nome: {"sha256", "bytes"}}`).

    O disco manda no byte e no sha; o inventário manda no seq, no tipo e na
    origem. `contaminada=True` marca a pasta em que o monitor gravou PDFs de
    outra licitação: o que estiver fora do inventário ali não é "extra", é
    `procedencia_incerta` (seção 9, passo 2).
    """
    saida: list[ArquivoLegado] = []
    usados: set[str] = set()
    primeiro_por_sha: dict[str, str] = {}
    containers: dict[str, ArquivoLegado] = {}

    for a in inv.get("arquivos") or []:
        nome_inv = (a.get("arquivo") or "").strip() or None
        sha_inv = (a.get("sha256") or a.get("sha") or "").strip().lower() or None
        seq = _int(a.get("seq"))
        nome, d = None, None
        if nome_inv and nome_inv in disco:
            nome, d = nome_inv, disco[nome_inv]
        elif sha_inv:
            # Legado sem nome (só `sha` de 16 hex) ou nome que mudou no disco:
            # casa pelo conteúdo. Ambiguidade (dois arquivos com o mesmo
            # prefixo) fica com o primeiro em ordem de nome; o outro vira alias
            # adiante, pelo sha completo.
            cands = sorted(n for n, x in disco.items()
                           if n not in usados and x["sha256"].startswith(sha_inv))
            if cands:
                nome, d = cands[0], disco[cands[0]]
        prov = {}
        if nome_inv and nome and nome_inv != nome:
            prov["nome_no_inventario"] = nome_inv
        if a.get("de_zip"):
            prov["de_zip"] = a["de_zip"]
        for k in ("reconciliado_em", "origem_recuperada_em", "nota"):
            if a.get(k):
                prov[k] = a[k]
        kb = _int(a.get("kb"))
        arq = ArquivoLegado(
            nome=nome or nome_inv or a.get("titulo") or "sem nome (seq %s)" % seq,
            status="ok", seq=seq, tipo=a.get("tipo"), titulo=a.get("titulo"),
            origem_url=a.get("origem"), paginas=_int(a.get("pag")), chars=_int(a.get("chars")),
            requer_ocr=_bool(a.get("requer_ocr") if "requer_ocr" in a else a.get("ocr")),
            ativo_pncp=_bool(a.get("ativo")), pai=a.get("de_zip") or None, proveniencia=prov,
            do_inventario=True)
        if d is None:
            arq.status = "ausente_no_disco"
            arq.motivo = "listado no inventário e ausente do disco no snapshot"
            arq.sha256 = sha_inv if sha_inv and len(sha_inv) == 64 else None
            if _int(a.get("bytes")) is not None:
                arq.bytes = _int(a.get("bytes"))
            elif kb is not None:
                arq.bytes, arq.bytes_aproximado = kb * 1024, True
        else:
            usados.add(nome)
            arq.sha256, arq.bytes = d["sha256"], d["bytes"]
            if sha_inv and not d["sha256"].startswith(sha_inv):
                arq.status = "corrompido"
                arq.motivo = ("sha do inventário %s… difere do disco %s…"
                              % (sha_inv[:12], d["sha256"][:12]))
                arq.tem_bytes = True
            elif "zip sem nenhum pdf" in (a.get("nota") or "").lower():
                arq.status, arq.motivo = "formato_nao_suportado", a["nota"]
            elif d["sha256"] in primeiro_por_sha:
                arq.status, arq.alias_de = "alias_duplicado", primeiro_por_sha[d["sha256"]]
                arq.tem_bytes = True
            else:
                arq.tem_bytes = True
                primeiro_por_sha[d["sha256"]] = arq.nome
        saida.append(arq)
        if arq.pai and arq.pai not in containers:
            containers[arq.pai] = ArquivoLegado(
                nome=arq.pai, status="zip_container", seq=seq, tipo=arq.tipo,
                motivo="ZIP entregue como .pdf; o conteúdo foi extraído no download")

    nomes = {a.nome for a in saida}
    saida += [c for n, c in containers.items() if n not in nomes]
    nomes |= set(containers)

    for r in inv.get("recusados") or []:
        nome = (r.get("arquivo") or "").strip()
        if not nome or nome in nomes:
            continue
        motivo = r.get("motivo") or ""
        saida.append(ArquivoLegado(nome=nome, status=_status_da_recusa(motivo), seq=_int(r.get("seq")),
                                   tipo=r.get("tipo"), bytes=_int(r.get("bytes")),
                                   origem_url=r.get("origem"), motivo=motivo or None))
        nomes.add(nome)

    for f in inv.get("falhas_download") or []:
        nome = (f.get("arquivo") or "").strip()
        if not nome or nome in nomes:
            continue
        saida.append(ArquivoLegado(nome=nome, status="falha_rede", seq=_int(f.get("seq")),
                                   tipo=f.get("tipo"), origem_url=f.get("origem"),
                                   motivo=f.get("erro")))
        nomes.add(nome)

    for nome in sorted(set(disco) - usados):
        if nome in nomes:
            continue
        d = disco[nome]
        arq = ArquivoLegado(nome=nome, status="fora_inventario", sha256=d["sha256"],
                            bytes=d["bytes"], tem_bytes=True)
        if d["sha256"] in primeiro_por_sha:
            arq.status, arq.alias_de = "alias_duplicado", primeiro_por_sha[d["sha256"]]
        elif contaminada:
            arq.status = "procedencia_incerta"
            arq.motivo = "PDF na pasta sem estar no inventário, em pasta que recebeu arquivo de outra licitação"
        else:
            primeiro_por_sha[d["sha256"]] = nome
        saida.append(arq)
        nomes.add(nome)
    return saida


# ------------------------------------------------------------- canônica
def _quando(s) -> datetime:
    if not s:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)


def escolher_canonica(candidatos: list[dict]) -> tuple[str | None, str]:
    """
    Qual pasta dá a execução canônica de um controle com mais de uma pasta.

    Critérios, nesta ordem (seção 9, passo 1, adaptados para rodar sem rede):
      1. leitura sem PDF de fora do inventário — o sintoma da contaminação
         do monitor (Castro-PR, Passagem-RN): o agente leu tudo que estava
         na pasta, inclusive o edital de outra licitação;
      2. execução mais recente (`finalizado.em`);
      3. a original vence a que reaproveitou as respostas dela (Capep).
    Empate que sobra -> (None, motivo): vira `legado_suspeito` e vai para
    `migracao/decisoes.json`, nunca para uma escolha silenciosa.
    """
    com = [c for c in candidatos if c.get("tem_execucao")]
    if not com:
        return None, "nenhuma pasta com execução"
    if len(com) == 1:
        return com[0]["pasta"], "única pasta com execução"
    limpas = [c for c in com if c.get("leitura_limpa") is not False]
    if limpas and len(limpas) < len(com):
        if len(limpas) == 1:
            return limpas[0]["pasta"], "as outras pastas leram PDF fora do inventário"
        com = limpas
    mais = max(_quando(c.get("finalizado_em")) for c in com)
    topo = [c for c in com if _quando(c.get("finalizado_em")) == mais]
    if len(topo) == 1:
        return topo[0]["pasta"], "execução mais recente (finalizado.em)"
    pastas = {c["pasta"] for c in topo}
    originais = [c for c in topo if c.get("reaproveitado_de") not in pastas]
    if len(originais) == 1:
        return originais[0]["pasta"], "a outra pasta reaproveitou as respostas desta"
    return None, "empate entre %s" % ", ".join(sorted(pastas))


# ------------------------------------------------------------- leitura
def assinatura_conjunto(assinatura: dict) -> str:
    """
    Um hash do TEXTO lido, independente do nome dos arquivos.

    É o critério de gêmea do `70_` (mesmo texto, não só mesmos bytes): Caibi e
    Caibi - 724-2026 leram o mesmo conteúdo sob nomes diferentes.
    """
    return hashlib.sha256("\n".join(sorted(assinatura.values())).encode("utf-8")).hexdigest()


def assinatura_nomes(assinatura: dict) -> str:
    """
    Hash do texto COM o nome de cada arquivo: a identidade de uma leitura.

    A resposta cita pelo nome ("=== ARQUIVO x | PÁGINA n ==="), então o mesmo
    texto sob outro nome é outra leitura para a citação — Capep tem as duas.
    Mesmo cálculo da migração 015 (linhas "nome<TAB>hash" em ordem de code point).
    """
    linhas = sorted("%s\t%s" % (n, h) for n, h in assinatura.items())
    return hashlib.sha256("\n".join(linhas).encode("utf-8")).hexdigest()


def leitura_limpa(hashes_bytes: dict, shas_inventario: set) -> bool:
    """A leitura só contém arquivos que o inventário da licitação declara."""
    return all(sha in shas_inventario for sha in hashes_bytes.values())


# ------------------------------------------------------------- respostas
def ausencia(r: dict) -> str | None:
    """
    Os três motivos para não haver trecho, na mesma ordem do RELATORIO
    (`pagina.py`): há trecho -> None; "não localizado" com alerta de
    modalidade -> `nao_se_aplica`; "não localizado" -> `sem_evidencia` (a
    ausência é a resposta); respondeu sem trecho -> `falta_evidencia` (defeito).
    """
    if r.get("trecho_literal"):
        return None
    if nao_encontrou(r.get("resposta") or ""):
        if any((a or "").startswith("não se aplica a esta modalidade")
               for a in r.get("alertas") or []):
            return "nao_se_aplica"
        return "sem_evidencia"
    return "falta_evidencia"


def json_canonico(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def respostas_sha256(respostas: list[dict]) -> str:
    """Hash estável das respostas cruas, em ordem de pergunta."""
    ordem = sorted(respostas, key=lambda r: int(str(r.get("id", "Q0"))[1:] or 0))
    return hashlib.sha256(json_canonico(ordem)).hexdigest()


# ------------------------------------------------------------- nome citado
def resolver_nome(citado: str | None, nomes) -> str | None:
    """
    O arquivo que uma citação do modelo aponta, com a MESMA tolerância do
    verificador (`Extracao.pagina`): exato; senão sufixo ou rótulo colado,
    desde que resolva para um arquivo só. Ambíguo não resolve — o link não
    pode escolher por quem leu.
    """
    alvo = (citado or "").strip()
    if not alvo:
        return None
    nomes = set(nomes)
    if alvo in nomes:
        return alvo
    chave = _apelido(alvo)
    if not chave:
        return None
    cands = {n for n in nomes if _casa(_apelido(n), chave)}
    return cands.pop() if len(cands) == 1 else None


# ------------------------------------------------------------- Q13
def q13_estruturada(texto: str | None) -> dict:
    """A distribuição da Q13 (`fopa.distribuicao.ler`) como JSON, com os totais calculados."""
    d = distribuicao.ler(texto or "")
    return {
        "tipo": d.tipo, "parcial": d.parcial, "por_faixa": d.por_faixa,
        "soma": d.soma, "total_declarado": d.total_declarado, "confere": d.confere,
        "completa": d.completa, "rotulo_soma": d.rotulo_soma,
        "grupos": [{"nome": g.nome, "total_declarado": g.total_declarado, "soma": g.soma,
                    "confere": g.confere,
                    "linhas": [{"rotulo": l.rotulo, "quantidade": l.quantidade, "valor": l.valor}
                               for l in g.linhas]}
                   for g in d.grupos],
    }


# ------------------------------------------------------------- harness
def respostas_do_harness(execucao: dict) -> list[dict]:
    """
    As respostas de uma repetição do harness no formato da auditoria.

    O harness grava `respostas` como {Qn: texto} e a evidência à parte em
    `evidencia` ({Qn: {arquivo, pagina, trecho, veredito}}); a auditoria grava
    uma lista de dicionários. Aceita os dois.
    """
    rs = execucao.get("respostas") or []
    if isinstance(rs, list):
        return rs
    ev = execucao.get("evidencia") or {}
    saida = []
    for pid in sorted(rs, key=lambda k: int(str(k)[1:] or 0)):
        e = ev.get(pid) or {}
        saida.append({"id": pid, "resposta": rs[pid], "arquivo": e.get("arquivo"),
                      "pagina": e.get("pagina"), "trecho_literal": e.get("trecho"),
                      "conflito": None, "confianca": None})
    return saida


def casar_harness(aud: dict, harness: dict, modelo: str):
    """
    Qual repetição do harness virou a auditoria "promovida".

    Quevedos, Adrianópolis, Fruta de Leite e Rio Branco têm `chamadas=0` na
    auditoria: não saíram do lote, saíram de uma repetição do harness. Casa
    comparando Q1..Q17 texto a texto; sem casamento único -> "ambíguo", e o
    site diz isso em vez de apontar uma origem que não se pode provar.
    """
    prefixo = (modelo or "").replace("claude-", "")
    alvo = {r.get("id"): r.get("resposta") for r in aud.get("respostas") or []}
    achados = []
    for i, e in enumerate(harness.get("execucoes") or []):
        rot = e.get("rotulo") or ""
        if not (rot == prefixo or rot.startswith(prefixo + " ")):
            continue
        dele = {r.get("id"): r.get("resposta") for r in respostas_do_harness(e)}
        if dele == alvo:
            achados.append({"rotulo": rot, "repeticao": e.get("repeticao"), "indice": i})
    return achados[0] if len(achados) == 1 else "ambíguo"


__all__ = ["partes_controle", "fim_prazo", "ArquivoLegado", "arquivos_da_pasta",
           "escolher_canonica", "assinatura_conjunto", "assinatura_nomes", "leitura_limpa", "ausencia",
           "json_canonico", "respostas_sha256", "casar_harness", "resolver_nome",
           "q13_estruturada", "respostas_do_harness", "FUSO_BRASILIA"]
