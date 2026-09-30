# -*- coding: utf-8 -*-
"""
Extração SEM API: um agente (sessão Claude Code) faz o papel do provedor.

    python 70_extracao_por_agente.py fila                 o que falta, por prazo
    python 70_extracao_por_agente.py preparar <pasta>     páginas -> texto com marcadores
    python 70_extracao_por_agente.py preparar --fila 50   as 50 primeiras da fila
    python 70_extracao_por_agente.py finalizar <pasta>    respostas -> verificação -> saídas
    python 70_extracao_por_agente.py finalizar <pasta> --de <outra>
    python 70_extracao_por_agente.py status

O QUE MUDA E O QUE NÃO MUDA EM RELAÇÃO AO `10_extrair_edital.py`
  Muda UMA coisa: quem escreve o JSON das 17 respostas. Em vez de uma chamada à
  API, um agente lê as mesmas páginas e grava `respostas.json` no mesmo esquema
  (`questionario.ESQUEMA_LOTE`), sob as mesmas regras (`instrucao_sistema()`).

  O resto é o pipeline de sempre, chamado pelas mesmas funções: `extrator.extrair`
  monta a `Extracao`, o `verificador` confere cada trecho contra a página citada
  sem IA, e `saida`, `metadados` e `pagina` escrevem os mesmos arquivos. Um
  relatório feito por aqui é indistinguível de um feito pela API — exceto pelo
  provedor, que fica gravado como `claude-code` para que ninguém confunda os dois.

AS PÁGINAS QUE O AGENTE LÊ SÃO AS QUE O VERIFICADOR CONFERE
  O `preparar` usa `extrator.carregar_paginas` — o mesmo OCR, a mesma limpeza de
  assinatura — e grava o texto com os marcadores `=== ARQUIVO x | PÁGINA n ===`.
  Se o agente lesse o PDF por outro caminho, copiaria um trecho que o verificador
  não encontraria na página, e a reprovação seria do encanamento, não da resposta.

UMA PASSADA, COMO A API
  `finalizar` roda uma vez e não aceita segunda sem `--refazer`. Usar o
  verificador como juiz de tentativas repetidas é a técnica Best-of-N que está no
  BACKLOG esperando decisão; ela não entra aqui pela porta dos fundos.

DOCUMENTOS IDÊNTICOS
  Há licitações republicadas no PNCP com outro número e os MESMOS PDFs (mesmo
  SHA-256). As respostas dependem só dos documentos, então `--de <pasta>`
  reaproveita as da gêmea, remapeando o nome do arquivo pelo hash — e o
  verificador confere tudo de novo contra as páginas DESTA pasta.

CUSTO EM API: R$ 0,00. O custo existe, mas é da sessão do agente, e não há
tabela que o converta por edital — por isso `brl` fica `null` na auditoria.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import (condicoes as cond, execucao, extrator, metadados,  # noqa: E402
                  pagina, recuperacao as rec, saida, verificador)
from fopa.modelos import Provedor, Uso                            # noqa: E402
from fopa.questionario import (ESQUEMA_LOTE, NAO_LOCALIZADO, PERGUNTAS,  # noqa: E402
                               instrucao_sistema)

# TRAVA: ESTE SCRIPT EXISTE PARA NÃO GASTAR API.
#
# Nenhum caminho daqui chama modelo — o provedor devolve o JSON do disco. Mas
# "nenhum caminho chama" é uma afirmação sobre o código de hoje, e o código
# muda. Então a garantia é física: os dois clientes pagos deixam de existir
# neste processo, e o SDK não importa. Se algum dia uma função do pipeline
# passar a chamar a API por conta própria, isto quebra alto em vez de cobrar
# em silêncio.
from fopa import modelos as _modelos                             # noqa: E402


def _proibido(*_a, **_k):
    raise RuntimeError("70_extracao_por_agente.py não chama API de modelo")


_modelos.ProvedorClaude = _modelos.ProvedorOpenAI = _proibido
_modelos.obter_provedor = _proibido
_modelos.PROVEDORES = {}
sys.modules["anthropic"] = None       # `import anthropic` -> ImportError
sys.modules["openai"] = None

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")
AGENTE = os.path.join(SAIDAS, "_agente")

PROVEDOR = "claude-code"
MODELO = os.environ.get("FOPA_MODELO_AGENTE", "claude-opus-5-5")
# Pedaços pequenos o bastante para o agente ler cada um de uma vez só.
PEDACO = 50_000
IDS = [p.id for p in PERGUNTAS]


# ------------------------------------------------------------------ util
def _pasta(arg: str) -> str:
    return arg if os.path.isdir(arg) else os.path.join(AMOSTRAS, arg)


def _trabalho(nome: str) -> str:
    return os.path.join(AGENTE, nome)


def _ler_json(caminho: str):
    with io.open(caminho, encoding="utf-8") as f:
        return json.load(f)


def _gravar_json(caminho: str, dados) -> None:
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def _inventario(pasta: str) -> dict:
    f = os.path.join(pasta, "_inventario.json")
    try:
        return _ler_json(f) if os.path.isfile(f) else {}
    except (ValueError, OSError):
        return {}


def _pdfs(pasta: str) -> list[str]:
    return sorted(f for f in os.listdir(pasta) if f.lower().endswith(".pdf"))


def _hashes(pasta: str, inv: dict) -> dict[str, str]:
    """arquivo -> SHA-256. Usa o do inventário quando o tamanho confere."""
    conhecidos = {a.get("arquivo"): a for a in inv.get("arquivos") or []}
    fora = {}
    for nome in _pdfs(pasta):
        caminho = os.path.join(pasta, nome)
        a = conhecidos.get(nome)
        if a and a.get("sha256") and a.get("bytes") == os.path.getsize(caminho):
            fora[nome] = a["sha256"]
            continue
        h = hashlib.sha256()
        with open(caminho, "rb") as f:
            for bloco in iter(lambda: f.read(1 << 20), b""):
                h.update(bloco)
        fora[nome] = h.hexdigest()
    return fora


def _incompleta(pasta: str, inv: dict) -> list[str]:
    """Arquivos que o inventário promete e o disco ainda não tem.

    O download roda em paralelo com a extração. Extrair uma pasta pela metade
    produziria um relatório sem o documento que talvez carregue a resposta.
    """
    # Sem diferenciar maiúsculas: o inventário grava "CAPA-LICITACAO.pdf" e o
    # disco tem "Capa-Licitacao.pdf" — o mesmo arquivo para o Windows. A
    # comparação exata marcava 10 licitações ABERTAS como incompletas.
    no_disco = {n.casefold() for n in _pdfs(pasta)}

    def presente(nome: str) -> bool:
        baixo = nome.casefold()
        if baixo in no_disco:
            return True
        # ZIP entregue como ".ZIP.pdf": o download extrai o conteúdo como
        # "<nome do zip> -- <arquivo interno>.pdf" e às vezes apaga o ZIP.
        # O documento está lá, só com outro nome.
        if ".zip" in baixo:
            raiz = baixo[:baixo.index(".zip")] + " -- "
            return any(n.startswith(raiz) for n in no_disco)
        return False

    return [a["arquivo"] for a in inv.get("arquivos") or []
            if a.get("arquivo") and a["arquivo"].lower().endswith(".pdf")
            and not presente(a["arquivo"])]


def _e_pdf(caminho: str) -> bool:
    """O arquivo é PDF pelo conteúdo, não pela extensão.

    O PNCP entrega ZIP e DOCX com nome terminado em `.pdf`. O conteúdo do ZIP
    já é extraído ao lado pelo download; o ZIP em si derruba a leitura da pasta
    inteira (`FileDataError`), e com ele as páginas que se leriam bem.
    """
    try:
        with open(caminho, "rb") as f:
            return b"%PDF" in f.read(1024)
    except OSError:
        return False


def _carregar(pasta: str, observador) -> tuple[list, list[str]]:
    """`extrator.carregar_paginas`, só com o que é PDF de verdade.

    O que não é PDF fica de fora e é DEVOLVIDO, para constar como não lido.
    A leitura continua sendo a do pipeline: os PDFs legítimos são ligados numa
    pasta temporária (hardlink, sem cópia) com o mesmo nome, e é ela que o
    `carregar_paginas` lê.
    """
    nomes = _pdfs(pasta)
    falsos = [n for n in nomes if not _e_pdf(os.path.join(pasta, n))]
    if not falsos:
        return extrator.carregar_paginas(pasta, observador=observador), []
    os.makedirs(AGENTE, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=AGENTE) as tmp:
        for n in nomes:
            if n in falsos:
                continue
            origem, destino = os.path.join(pasta, n), os.path.join(tmp, n)
            try:
                os.link(origem, destino)
            except OSError:
                shutil.copy2(origem, destino)
        return extrator.carregar_paginas(tmp, observador=observador), falsos


# ------------------------------------------------------------------ fila
def fila() -> list[dict]:
    """
    Tudo o que ainda não foi extraído, na ordem em que vale a pena extrair.

    Abertas primeiro, pela sessão mais próxima: é nelas que o banco ainda pode
    dar lance. Depois as encerradas, da mais recente para a mais antiga — são
    dado de mercado, e o dado recente vale mais.
    """
    hoje = datetime.date.today().isoformat()
    itens = []
    for nome in sorted(os.listdir(AMOSTRAS)):
        p = os.path.join(AMOSTRAS, nome)
        if nome.startswith("_") or not os.path.isdir(p) or not _pdfs(p):
            continue
        inv = _inventario(p)
        if (inv.get("escopo") or {}).get("dentro") is False:
            continue
        # Já extraída pela API: não se sobrescreve. Bertioga está sem
        # `auditoria.json` desde o ensaio simulado de 23/09, mas o RELATORIO.html
        # e o `_gabarito.json` dela continuam sendo a referência do projeto.
        if (os.path.isfile(os.path.join(SAIDAS, nome, "auditoria.json"))
                or os.path.isfile(os.path.join(p, "RELATORIO.html"))
                or os.path.isfile(os.path.join(p, "_gabarito.json"))):
            continue
        prazo = (inv.get("fim_prazo") or "")[:16]
        arqs = inv.get("arquivos") or []
        itens.append(dict(
            nome=nome, prazo=prazo, aberta=bool(prazo) and prazo[:10] >= hoje,
            paginas=sum(a.get("pag") or 0 for a in arqs),
            chars=sum(a.get("chars") or 0 for a in arqs),
            ocr=any(a.get("requer_ocr") for a in arqs),
            faltando=_incompleta(p, inv),
            preparada=os.path.isfile(os.path.join(_trabalho(nome), "paginas.json")),
            respondida=os.path.isfile(os.path.join(_trabalho(nome), "respostas.json"))))
    abertas = sorted((i for i in itens if i["aberta"]), key=lambda i: i["prazo"])
    fechadas = sorted((i for i in itens if not i["aberta"] and i["prazo"]),
                      key=lambda i: i["prazo"], reverse=True)
    sem_data = [i for i in itens if not i["prazo"]]
    ordem = abertas + fechadas + sem_data

    # GÊMEAS: MESMO TEXTO LIDO, NÃO SÓ MESMOS BYTES.
    # O hash dos bytes deixava passar a republicação: Passagem/RN aparece em três
    # pastas do PNCP (49, 52 e a sem número) com PDFs de bytes diferentes e o
    # mesmo PE 011/2026 dentro — três agentes leram o mesmo edital. O que as
    # respostas usam é o texto, então é o texto que decide. O hash dos bytes fica
    # para as pastas ainda não preparadas, que não têm texto para comparar.
    # As já finalizadas entram primeiro: podem ser a original de uma da fila.
    vistos: dict[tuple, str] = {}
    if os.path.isdir(AGENTE):
        for nome in sorted(os.listdir(AGENTE)):
            f = os.path.join(AGENTE, nome, "finalizado.json")
            if os.path.isfile(f) and not _ler_json(f).get("reaproveitado_de"):
                sig = _assinatura_texto(nome)
                if sig:
                    vistos.setdefault(("texto", frozenset(sig.values())), nome)
    for i in ordem:
        sig = _assinatura_texto(i["nome"]) if i["preparada"] else None
        if sig:
            chave = ("texto", frozenset(sig.values()))
        else:
            p = os.path.join(AMOSTRAS, i["nome"])
            chave = ("bytes", frozenset(_hashes(p, _inventario(p)).values()))
        i["gemea_de"] = vistos.get(chave)
        vistos.setdefault(chave, i["nome"])
    return ordem


def _assinatura_texto(nome: str) -> dict[str, str] | None:
    """arquivo -> SHA-256 do texto que o pipeline leu dele (espaços colapsados).

    Fica num arquivo pequeno ao lado do cache: reler o `paginas.json` de 700
    pastas a cada consulta da fila custaria centenas de MB de leitura.
    """
    dest = _trabalho(nome)
    f = os.path.join(dest, "assinatura.json")
    if os.path.isfile(f):
        return _ler_json(f)
    cache = os.path.join(dest, "paginas.json")
    if not os.path.isfile(cache):
        return None
    return _gravar_assinatura(dest, _ler_json(cache)["paginas"])


def _gravar_assinatura(dest: str, paginas: list[dict]) -> dict[str, str]:
    por_arquivo: dict[str, list[str]] = {}
    for p in paginas:
        por_arquivo.setdefault(p["arquivo"], []).append(
            re.sub(r"\s+", " ", p["texto"]).strip())
    sig = {a: hashlib.sha256("\f".join(t).encode("utf-8")).hexdigest()
           for a, t in por_arquivo.items()}
    _gravar_json(os.path.join(dest, "assinatura.json"), sig)
    return sig


def cmd_fila(a) -> int:
    itens = fila()
    _gravar_json(os.path.join(AGENTE, "_fila.json"), itens)
    for n, i in enumerate(itens[:a.n], start=1):
        print("%4d  %-16s %4dp %8dch %-3s %-4s %s%s%s"
              % (n, i["prazo"] or "-", i["paginas"], i["chars"],
                 "OCR" if i["ocr"] else "", "PREP" if i["preparada"] else "",
                 i["nome"],
                 "  [gêmea de %s]" % i["gemea_de"] if i["gemea_de"] else "",
                 "  [INCOMPLETA: faltam %d]" % len(i["faltando"]) if i["faltando"] else ""))
    print("\n  %d na fila · %d abertas · %d gêmeas · %d incompletas"
          % (len(itens), sum(i["aberta"] for i in itens),
             sum(1 for i in itens if i["gemea_de"]),
             sum(1 for i in itens if i["faltando"])))
    return 0


# ------------------------------------------------------------------ preparar
def _tarefa(nome: str, pedacos: list[tuple[str, str]]) -> str:
    lista = "\n".join("- `%s` — %s" % (f, faixa) for f, faixa in pedacos)
    return """# Tarefa — extrair as 17 respostas

LICITAÇÃO: %s

Você faz aqui o papel do modelo que a API chamaria. Leia os documentos abaixo e
grave `respostas.json` NESTA pasta. O arquivo será conferido por um verificador
determinístico: cada `trecho_literal` precisa existir, caractere a caractere
(tolerância só para espaço e hifenização), na página citada.

## Documentos (texto já extraído, com OCR onde precisou)

%s

Cada página começa com o marcador `=== ARQUIVO <nome> | PÁGINA <n> ===`.
`arquivo` = o <nome> exatamente como está no marcador; `pagina` = o <n>.

## Instruções do extrator (as mesmas que a API recebe)

%s

## Perguntas

%s

## Saída — `respostas.json`

```json
{"respostas": [
  {"id": "Q1", "resposta": "...", "arquivo": "01 - Edital - ....pdf", "pagina": 3,
   "trecho_literal": "...copiado do texto...", "conflito": null, "confianca": "alta"},
  ...  (Q1 a Q17, todas)
]}
```

Esquema: %s
""" % (nome, lista, instrucao_sistema(), extrator._bloco_perguntas(IDS),
       json.dumps(ESQUEMA_LOTE["properties"]["respostas"]["items"]["properties"],
                  ensure_ascii=False))


def preparar(pasta: str, forcar: bool = False) -> str:
    nome = os.path.basename(pasta.rstrip("\\/"))
    dest = _trabalho(nome)
    cache = os.path.join(dest, "paginas.json")
    if os.path.isfile(cache) and not forcar:
        return dest
    c = cond.Condicoes()
    t0 = time.time()
    paginas, nao_pdf = _carregar(pasta, observador=c)
    if not paginas:
        raise ValueError("nenhuma página legível em %s" % pasta)
    os.makedirs(dest, exist_ok=True)

    pedacos, atual, tam, primeira = [], [], 0, None

    def fechar():
        if not atual:
            return
        arq = "contexto_%02d.txt" % (len(pedacos) + 1)
        with io.open(os.path.join(dest, arq), "w", encoding="utf-8") as f:
            f.write(rec.montar_contexto(atual))
        ult = atual[-1]
        pedacos.append((arq, "%s p.%d  →  %s p.%d  (%d págs)"
                        % (primeira.arquivo[:50], primeira.numero,
                           ult.arquivo[:50], ult.numero, len(atual))))

    for pg in paginas:
        n = len(pg.texto) + len(pg.marcador) + 2
        if atual and tam + n > PEDACO:
            fechar()
            atual, tam = [], 0
        if not atual:
            primeira = pg
        atual.append(pg)
        tam += n
    fechar()

    with io.open(os.path.join(dest, "TAREFA.md"), "w", encoding="utf-8") as f:
        f.write(_tarefa(nome, pedacos))
    _gravar_assinatura(dest, [{"arquivo": p.arquivo, "texto": p.texto} for p in paginas])
    # o cache vai por ÚLTIMO: é a presença dele que diz "preparada"
    _gravar_json(cache, {
        "licitacao": nome, "preparado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "segundos": round(time.time() - t0, 1),
        "condicoes": {"arquivos_ocr": c.arquivos_ocr, "paginas_ocr": c.paginas_ocr,
                      "furtivos": c.furtivos, "nao_pdf": nao_pdf},
        "hashes": _hashes(pasta, _inventario(pasta)),
        "pedacos": [f for f, _ in pedacos],
        "paginas": [{"arquivo": p.arquivo, "numero": p.numero, "texto": p.texto}
                    for p in paginas]})
    return dest


def cmd_preparar(a) -> int:
    if a.fila:
        alvos = [i["nome"] for i in fila()
                 if not i["preparada"] and not i["faltando"]][:a.fila]
    else:
        alvos = [a.pasta]
    falhas = 0
    for n, nome in enumerate(alvos, start=1):
        pasta = _pasta(nome)
        t0 = time.time()
        try:
            dest = preparar(pasta, forcar=a.refazer)
            cache = _ler_json(os.path.join(dest, "paginas.json"))
            print("[%d/%d] %-70s %4d págs  %d pedaço(s)  %.0fs"
                  % (n, len(alvos), os.path.basename(pasta)[:70],
                     len(cache["paginas"]), len(cache["pedacos"]), time.time() - t0),
                  flush=True)
        except Exception as e:                                   # noqa: BLE001
            falhas += 1
            print("[%d/%d] %s  FALHOU: %r" % (n, len(alvos), nome, e), flush=True)
    return 1 if falhas else 0


# ------------------------------------------------------------------ finalizar
class ProvedorAgente(Provedor):
    """Devolve o JSON que o agente gravou. Não chama rede nem modelo."""

    nome = PROVEDOR

    def __init__(self, dados: dict, modelo: str):
        self.dados, self.modelo = dados, modelo

    def responder_json(self, sistema, usuario, esquema, modelo,
                       max_tokens=16000, effort="high"):
        return self.dados, Uso(chamadas=1, modelo=self.modelo)


def _validar(dados) -> list[str]:
    """O que o esquema exige e o agente pode ter esquecido. Vazio = ok."""
    if not isinstance(dados, dict) or not isinstance(dados.get("respostas"), list):
        return ["respostas.json precisa ser {\"respostas\": [...]}"]
    erros = []
    ids = [r.get("id") for r in dados["respostas"] if isinstance(r, dict)]
    faltam = [i for i in IDS if i not in ids]
    if faltam:
        erros.append("faltam: %s" % ", ".join(faltam))
    for r in dados["respostas"]:
        if not isinstance(r, dict):
            erros.append("item que não é objeto")
            continue
        if r.get("pagina") is not None and not isinstance(r.get("pagina"), int):
            erros.append("%s: pagina precisa ser inteiro" % r.get("id"))
        if r.get("confianca") not in ("alta", "media", "baixa"):
            erros.append("%s: confianca fora de alta/media/baixa" % r.get("id"))
    return erros


def _reaproveitar(origem: str, destino: str) -> dict:
    """Respostas da gêmea, com o nome de arquivo trocado pelo desta pasta.

    O casamento é pelo hash do TEXTO de cada arquivo, que é o critério que fez
    das duas pastas gêmeas. Nome que não casa fica como está — e aí é o
    verificador, conferindo contra as páginas DESTA pasta, quem decide.
    """
    dados = _ler_json(os.path.join(_trabalho(origem), "respostas.json"))
    sig_origem = _assinatura_texto(origem) or {}
    por_hash = {h: n for n, h in (_assinatura_texto(destino) or {}).items()}
    for r in dados["respostas"]:
        if r.get("arquivo"):
            h = sig_origem.get(r["arquivo"])
            r["arquivo"] = por_hash.get(h, r["arquivo"])
    return dados


def finalizar(pasta: str, de: str | None = None, refazer: bool = False) -> dict:
    nome = os.path.basename(pasta.rstrip("\\/"))
    dest = _trabalho(nome)
    marca = os.path.join(dest, "finalizado.json")
    if os.path.isfile(marca) and not refazer:
        raise RuntimeError("já finalizada (uma passada, como a API); use --refazer")
    t0 = time.time()
    cache = _ler_json(os.path.join(dest, "paginas.json"))
    if de:
        dados = _reaproveitar(de, nome)
        _gravar_json(os.path.join(dest, "respostas.json"), dados)
    else:
        dados = _ler_json(os.path.join(dest, "respostas.json"))
    erros = _validar(dados)
    if erros:
        raise ValueError("respostas.json inválido: " + "; ".join(erros))

    paginas = [rec.Pagina(arquivo=p["arquivo"], numero=p["numero"], texto=p["texto"])
               for p in cache["paginas"]]
    ext = extrator.extrair(pasta, ProvedorAgente(dados, MODELO), modelo=MODELO,
                           modo="contexto-completo", lote=len(IDS), effort="agente",
                           paginas_prontas=paginas)
    ext.modo = "agente"
    c = ext.condicoes
    c.arquivos_ocr = cache["condicoes"]["arquivos_ocr"]
    c.paginas_ocr = cache["condicoes"]["paginas_ocr"]
    c.furtivos = cache["condicoes"]["furtivos"]
    # `extrair` marca como secundário todo provedor que não se chama "claude".
    # A marca existe para o plano B de OUTRO fornecedor; aqui o modelo é Claude,
    # só a porta de entrada é outra. O provedor fica gravado como `claude-code`,
    # e é por ele que se separa uma execução da outra.
    c.secundario = False

    rel = verificador.verificar(ext)
    saidas = os.path.join(SAIDAS, nome)
    try:
        saida.escrever_xlsx(ext, rel, os.path.join(saidas, "%s.xlsx" % nome))
    except RuntimeError:
        pass
    saida.escrever_nota(ext, rel, os.path.join(saidas, "%s.md" % nome))
    aud_p = saida.escrever_json(ext, rel, os.path.join(saidas, "auditoria.json"))
    aud = _ler_json(aud_p)
    aud["agente"] = {"provedor": PROVEDOR, "modelo": MODELO,
                     "reaproveitado_de": de,
                     "finalizado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    _gravar_json(aud_p, aud)
    metadados.atualizar(pasta, ext, rel)
    pagina.escrever(ext, rel, os.path.join(pasta, "RELATORIO.html"))

    resumo = {"licitacao": nome, "aprovadas": rel.aprovadas, "revisar": rel.revisar,
              "reprovadas": rel.reprovadas, "nao_localizado": rel.nao_localizado,
              "taxa_ancorada": round(rel.taxa_ancorada, 4), "reaproveitado_de": de,
              "em": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    _gravar_json(marca, resumo)
    execucao.registrar("70_extracao_por_agente.py", t0, extraidas=1,
                       reprovadas=rel.reprovadas, custo_brl=0.0)
    return {"ext": ext, "rel": rel, "resumo": resumo}


def cmd_finalizar(a) -> int:
    pasta = _pasta(a.pasta)
    try:
        r = finalizar(pasta, de=a.de, refazer=a.refazer)
    except Exception as e:                                       # noqa: BLE001
        print("FALHOU: %s" % e)
        return 1
    ext, rel = r["ext"], r["rel"]
    print("%s\n  %s" % (ext.licitacao, rel))
    for x in ext.respostas:
        print("  %-9s %-4s %-60s %s" % (x.veredito, x.id,
                                        x.resposta.replace("\n", " ")[:60], x.info[:40]))
    for g in rel.alertas_globais:
        print("  ⚠ %s" % g[:160])
    return 0


def cmd_status(a) -> int:
    feitas = []
    if os.path.isdir(AGENTE):
        for nome in sorted(os.listdir(AGENTE)):
            f = os.path.join(AGENTE, nome, "finalizado.json")
            if os.path.isfile(f):
                feitas.append(_ler_json(f))
    print("%d finalizadas por agente" % len(feitas))
    if feitas:
        print("  aprovadas %d · revisar %d · reprovadas %d · não localizado %d"
              % tuple(sum(x[k] for x in feitas) for k in
                      ("aprovadas", "revisar", "reprovadas", "nao_localizado")))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fila")
    f.add_argument("--n", type=int, default=100)
    p = sub.add_parser("preparar")
    p.add_argument("pasta", nargs="?")
    p.add_argument("--fila", type=int, default=0)
    p.add_argument("--refazer", action="store_true")
    z = sub.add_parser("finalizar")
    z.add_argument("pasta")
    z.add_argument("--de", default=None, help="pasta gêmea cujas respostas reaproveitar")
    z.add_argument("--refazer", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args()
    return {"fila": cmd_fila, "preparar": cmd_preparar,
            "finalizar": cmd_finalizar, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
