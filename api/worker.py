# -*- coding: utf-8 -*-
"""
Worker da FOPA v3 — FastAPI/uvicorn, porta interna 8000 (plano, seções 4 e 6).

Esqueleto: `GET /health` (sem auth) e `GET /versao` (Bearer). As rotas de
trabalho (`/escopo`, `/jobs/*`, `/prompt`, `/verificar`, ...) entram em cima
deste arquivo, sempre reaproveitando o pacote `fopa` — nunca reimplementando.

O QUE O /health PROMETE
  Ele é o contrato que o build da imagem e o W00 (Saúde) do n8n conferem:
  - Tesseract exatamente `FOPA_TESSERACT_ESPERADO` (5.4.0, ADR-008) com `por`,
    senão 503 — um worker com OCR errado não pode ser "saudável", porque
    produziria leituras não comparáveis às medições;
  - `tessdata_sha256` do `por.traineddata` em uso, para bater com
    `FOPA_TESSDATA_SHA256` (o arquivo não está no git);
  - os três hashes de código (`api.versao`) e o `git_sha`, porque `scripts/`
    é congelado no build e nunca montado por bind;
  - `anthropic_key_presente`: tem de ser `false`. O worker nunca recebe a
    chave; quem chama o modelo é o n8n. Só informa presença, nunca o valor.

Rodar local: `uvicorn api.worker:app --port 8000` a partir da raiz do repositório.
"""
from __future__ import annotations

import hashlib
import os

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from fopa import ocr

from . import auth, config, storage, versao

app = FastAPI(title="fopa-worker", docs_url=None, redoc_url=None)


@app.exception_handler(config.ConfigInvalida)
async def _config_invalida(request, exc):
    # A config é lida por requisição; variável inválida não é "erro interno" (500 opaco): é 503 dizendo
    # qual variável e o que ela aceita (achado da revisão final da F0). Os valores validados são escolhas
    # e números — nunca segredo.
    return JSONResponse({"detail": "configuração inválida: %s" % exc}, status_code=503)


def _versao_bate(obtida: str, esperada: str) -> bool:
    """
    Compara só os componentes que a esperada declara.

    O host das medições reporta `5.4.0.20240606`; o quarto campo é data de build
    do instalador Windows, não versão. `5.4.0` tem de casar com ele e NÃO com
    `5.3.0` (o que o Debian bookworm traz) nem com `5.4.1`.
    """
    partes_obtida = str(obtida).split(".")
    partes_esperada = str(esperada).split(".")
    return partes_obtida[:len(partes_esperada)] == partes_esperada


def _sha256_arquivo(caminho: str) -> str | None:
    if not os.path.isfile(caminho):
        return None
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _tessdata_sha256() -> str | None:
    # `ocr.TESSDATA` é o que o pytesseract usa de fato (TESSDATA_PREFIX): é o
    # arquivo em uso que interessa, não o que a env diz que deveria existir.
    return _sha256_arquivo(os.path.join(ocr.TESSDATA, "por.traineddata"))


def _diagnostico_ocr(esperada: str) -> tuple[dict, str | None]:
    """Devolve (ambiente do OCR, motivo da falha ou None). Nunca levanta."""
    try:
        amb = ocr.checar_ambiente()
    except ocr.OcrIndisponivel as e:
        return {"tesseract": None, "idiomas": []}, str(e)
    except Exception as e:  # pytesseract pode falhar de outros jeitos (binário quebrado)
        return {"tesseract": None, "idiomas": []}, "falha ao consultar o Tesseract: %s" % e
    erro = None
    if not _versao_bate(amb["tesseract"], esperada):
        erro = ("tesseract %s difere do esperado %s (ADR-008: versão fixa das medições)"
                % (amb["tesseract"], esperada))
    elif "por" not in amb.get("idiomas", []):
        erro = "tessdata sem 'por' (tem: %s)" % ", ".join(amb.get("idiomas", []))
    return amb, erro


@app.get("/health")
def health():
    try:
        cfg = config.carregar()
    except config.ConfigInvalida as e:
        # No formato do /health: o healthcheck do compose cai dizendo o que corrigir.
        return JSONResponse({"ok": False, "git_sha": versao.git_sha(), "erro": "configuração inválida: %s" % e},
                            status_code=503)
    amb, erro = _diagnostico_ocr(cfg.tesseract_esperado)
    corpo = {
        "ok": erro is None,
        "git_sha": versao.git_sha(),
        "tesseract": amb.get("tesseract"),
        "tessdata_sha256": _tessdata_sha256(),
        "idiomas": amb.get("idiomas", []),
        "storage": storage.abrir(cfg).descrever(),
        # Presença, nunca valor: é a prova de que o compose não passou a chave.
        "anthropic_key_presente": "ANTHROPIC_API_KEY" in os.environ,
        **versao.resumo(),
    }
    if erro:
        corpo["erro"] = erro
        return JSONResponse(corpo, status_code=503)
    return corpo


@app.get("/versao", dependencies=[Depends(auth.exigir_token)])
def versao_():
    try:
        versao_ocr = ocr.checar_ambiente()["tesseract"]
    except Exception:
        versao_ocr = None   # /versao é informativo; quem decide saúde é o /health
    return {**versao.resumo(), "versao_ocr": versao_ocr}


# ------------------------------------------------------------------ núcleo (F1)
# Tudo abaixo exige o Bearer do worker. Nada aqui chama modelo: o verificador,
# o escopo, o questionário e o custo são o pacote `fopa`, determinístico.

from fastapi import Body, HTTPException  # noqa: E402

from fopa import escopo as escopo_mod  # noqa: E402
from fopa import extrator as extrator_mod  # noqa: E402
from fopa import questionario as questionario_mod  # noqa: E402
from fopa import verificador  # noqa: E402
from fopa.modelos import Uso  # noqa: E402

from . import banco, escopo_ajuste, persistencia, politica, reconstrucao, render as render_mod  # noqa: E402

_AUTH = [Depends(auth.exigir_token)]


def _base_da_reverificacao(conn, corpo: dict) -> tuple[int, int | None]:
    """(execução, verificação-base). Por controle: a vigente; por execução: a mais recente."""
    if corpo.get("execucao_id"):
        eid = int(corpo["execucao_id"])
        v = conn.execute("SELECT id FROM verificacoes WHERE execucao_id = %s"
                         " ORDER BY vigente DESC, id DESC LIMIT 1", (eid,)).fetchone()
        return eid, (v[0] if v else None)
    if corpo.get("controle"):
        v = conn.execute("SELECT execucao_id, id FROM verificacoes WHERE controle = %s AND vigente",
                         (corpo["controle"],)).fetchone()
        if not v:
            raise HTTPException(404, "licitação sem verificação vigente: %s" % corpo["controle"])
        return v[0], v[1]
    raise HTTPException(422, "informe controle ou execucao_id")


@app.post("/reverificar", dependencies=_AUTH)
def reverificar(corpo: dict = Body(...)):
    """
    Reaplica as regras ATUAIS ao texto congelado (ADR-011/014). Sem modelo, sem
    OCR. Grava uma verificação nova, NÃO vigente, e devolve o diff contra a
    base — quem troca a vigente é o fluxo (W24/W30), porque mudar números é decisão.
    """
    from . import versao
    with banco.conectar() as conn:
        eid, base_vid = _base_da_reverificacao(conn, corpo)
        vr = versao.versao_regras()
        if conn.execute("SELECT 1 FROM verificacoes WHERE execucao_id = %s AND versao_regras = %s",
                        (eid, vr)).fetchone():
            raise HTTPException(409, "a execução %s já foi verificada na versão %s" % (eid, vr[:12]))
        try:
            ext, ctx = reconstrucao.extracao_para_verificar(conn, eid, base_vid, storage=storage.abrir(config.carregar()))
        except reconstrucao.SemLeitura as e:
            raise HTTPException(409, str(e))
        linha = conn.execute("SELECT payload FROM itens_api WHERE controle = %s", (ctx["controle"],)).fetchone()
        itens = linha["payload"] if linha else None
        rel = politica.aplicar(ext, verificador.verificar(ext, itens, modalidade=ctx["modalidade"]))
        vid = persistencia.gravar_verificacao(conn, execucao_id=eid, controle=ctx["controle"],
                                             leitura_id=ctx["leitura_id"], ext=ext, rel=rel,
                                             versao_regras=vr, itens_api_usados=bool(itens))
        # Best-of-N (v3.1): a escolha foi feita na verificação de origem, e a reverificação reaplica regras às mesmas
        # respostas (as escolhidas, em `respostas`) — o rastro da escolha vai junto, senão a nota "escolhida a 2ª de
        # 3" some da tela na próxima mudança de regra (revisão da v3.1, 28/09).
        conn.execute("UPDATE verificacoes SET melhor_de_n = (SELECT o.melhor_de_n FROM verificacoes o"
                     " WHERE o.execucao_id = %s AND o.melhor_de_n IS NOT NULL AND o.id <> %s"
                     " ORDER BY o.id DESC LIMIT 1) WHERE id = %s", (eid, vid, vid))
        antes = {}
        if base_vid:
            antes = {r["pergunta_id"]: r["veredito"] for r in conn.execute(
                "SELECT pergunta_id, veredito FROM verificacao_respostas WHERE verificacao_id = %s",
                (base_vid,)).fetchall()}
            base_alertas = set(conn.execute("SELECT alertas_globais FROM verificacoes WHERE id = %s",
                                            (base_vid,)).fetchone()["alertas_globais"] or [])
        else:
            base_alertas = set()
        conn.commit()
    depois = {r.id: r.veredito for r in ext.respostas}
    mudou = {pid: [antes.get(pid), v] for pid, v in depois.items() if antes and antes.get(pid) != v}
    novos = set(rel.alertas_globais or [])
    return {"verificacao_id": vid, "versao_regras": vr, "base_verificacao_id": base_vid,
            "resumo": persistencia.resumo(ext, rel),
            "respostas": [{"id": r.id, "veredito": r.veredito, "alertas": r.alertas,
                           "pagina_final": r.pagina, "pagina_citada": r.pagina_citada,
                           "arquivo_canonico": r.arquivo_canonico} for r in ext.respostas],
            "diff_vs_anterior": {"vereditos": mudou,
                                 "alertas_entraram": sorted(novos - base_alertas),
                                 "alertas_sairam": sorted(base_alertas - novos)}}


@app.post("/render", dependencies=_AUTH)
def render(corpo: dict = Body(...)):
    """Gera o RELATORIO.html da verificação e grava no storage. Não publica: o W24 publica."""
    vid = corpo.get("verificacao_id")
    if not vid:
        raise HTTPException(422, "informe verificacao_id")
    cfg = config.carregar()
    with banco.conectar() as conn:
        try:
            return render_mod.renderizar(conn, storage.abrir(cfg), int(vid))
        except reconstrucao.NaoEncontrado as e:
            raise HTTPException(404, str(e))


@app.post("/escopo", dependencies=_AUTH)
def escopo(corpo: dict = Body(...)):
    """A regra de escopo (ADR-003) para uma lista de objetos. Roda ANTES de qualquer IA."""
    from . import versao
    objetos = corpo.get("objetos")
    if not isinstance(objetos, list):
        raise HTTPException(422, "objetos deve ser uma lista de textos")
    resultados = []
    for o in objetos:
        dentro, motivo = escopo_ajuste.avaliar(o or "")
        resultados.append({"dentro": dentro, "motivo": motivo,
                           "objeto_efetivo": escopo_mod.so_o_objeto(o or "")})
    return {"resultados": resultados, "escopo_versao": versao.escopo_versao()}


@app.get("/questionario", dependencies=_AUTH)
def questionario():
    """As 17 perguntas, o esquema e a instrução de sistema — o contrato do prompt."""
    from . import versao
    q = questionario_mod
    return {"versao_prompt": versao.versao_prompt(), "sistema": q.instrucao_sistema(),
            "esquema_lote": q.ESQUEMA_LOTE,
            "perguntas": [{"id": p.id, "texto": p.texto, "orienta": p.orienta, "formato": p.formato,
                           "critico": p.critico, "termos": list(p.termos)} for p in q.PERGUNTAS],
            "nao_se_aplica": {k: sorted(v) for k, v in q.NAO_SE_APLICA.items()},
            "marcador": "=== ARQUIVO %s | PÁGINA %d ===",
            "precedencia": list(extrator_mod.PRECEDENCIA),
            "sempre_incluir": list(extrator_mod.SEMPRE_INCLUIR)}


@app.post("/custo", dependencies=_AUTH)
def custo(corpo: dict = Body(...)):
    """
    O custo de UMA chamada, pelo preço de `modelos.PRECOS` (a única tabela, T17).
    Preço desconhecido devolve null, nunca 0 (ADR-012).
    """
    u = corpo.get("usage") or {}
    uso = Uso(entrada=u.get("input_tokens") or 0, saida=u.get("output_tokens") or 0,
              cache_escrita=u.get("cache_creation_input_tokens") or 0,
              cache_leitura=u.get("cache_read_input_tokens") or 0, chamadas=1,
              modelo=corpo.get("modelo") or "")
    if not uso.preco_conhecido:
        return {"usd": None, "brl": None, "preco_conhecido": False}
    return {"usd": round(uso.usd, 6), "brl": round(uso.brl, 6), "preco_conhecido": True}


# ------------------------------------------------------------------ rotas por área
# Cada área tem seu módulo e seu APIRouter, para que o caminho da extração e os
# jobs longos evoluam sem disputar este arquivo.
from .rotas_extracao import router as _rotas_extracao  # noqa: E402
from .rotas_jev import router as _rotas_jev  # noqa: E402
from .rotas_escopo import router as _rotas_escopo  # noqa: E402
from .rotas_jobs import router as _rotas_jobs  # noqa: E402

app.include_router(_rotas_extracao)
app.include_router(_rotas_jobs)
app.include_router(_rotas_jev)
app.include_router(_rotas_escopo)


__all__ = ["app"]
