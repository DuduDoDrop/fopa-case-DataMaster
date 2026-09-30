# -*- coding: utf-8 -*-
"""
Backend `s3` do storage (`api/storage.py`, F8) e o que o site faz com ele:
`GET /api/pdf/...` vira 302 para URL assinada de 10 min; o RELATORIO continua
passando pela API (a CSP sandbox só vale servida da origem do site).

Nada de rede e nada instalado além do que a api já usa: o bucket é um
`httpx.MockTransport` em memória (`S3Falso`) que CONFERE a assinatura de cada
pedido e o sha256 do corpo, como o S3/R2 fazem. Como o S3Falso confere com o
mesmo código que assina, a assinatura em si é provada contra os exemplos
publicados pela AWS ("Signature Calculations for the Authorization Header" e
"Authenticating Requests: Using Query Parameters", com a credencial de
exemplo da própria documentação) — não só contra ela mesma.

As rotas do site rodam SEM Postgres: a sessão e as duas consultas são
substituídas (dependency_overrides / monkeypatch). O 401 sem sessão roda com a
dependência de verdade — é ele que prova que nada toca no bucket antes do login.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from api import config, storage
from api import site as site_mod

ENDPOINT = "https://conta-teste.r2.cloudflarestorage.com"
BUCKET = "fopa-teste"
CHAVE_ACESSO = "chave-de-acesso-teste"
SEGREDO = "segredo-s3-de-teste-nunca-impresso"
REGIAO = "auto"
AGORA = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
PDF = b"%PDF-1.4 edital de teste\n%%EOF"
SHA_PDF = hashlib.sha256(PDF).hexdigest()
CHAVE_PDF = storage.chave_pdf("12345678000199", 2026, 7, SHA_PDF)
SLUG = "12345678000199-1-000007-2026"
HTML = b"<!doctype html><title>RELATORIO</title><a href='/api/pdf/x/1#page=3'>p. 3</a>"
CHAVE_HTML = storage.chave_html(SLUG, 42)

# Exemplos oficiais da AWS (examplebucket, 24/05/2013, us-east-1). A chave de
# exemplo é montada em partes: inteira, ela tem a cara de uma chave AWS de
# verdade e a guarda de CI (ci/tests/test_guardas_texto.py) a recusa.
AWS_CHAVE = "AKIA" + "IOSFODNN7" + "EXAMPLE"
AWS_SEGREDO = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
AWS_QUANDO = datetime(2013, 5, 24, tzinfo=timezone.utc)
AWS_HOST = "https://examplebucket.s3.amazonaws.com"
RE_AUTH = re.compile(r"^AWS4-HMAC-SHA256 Credential=([^/]+)/(\d{8})/([^/]+)/s3/aws4_request, "
                     r"SignedHeaders=([a-z0-9;-]+), Signature=([0-9a-f]{64})$")


# ====================================================================== bucket falso
def _erro(codigo: str, status: int, metodo: str) -> httpx.Response:
    # HEAD não tem corpo no S3: um 404 de HEAD não diz se faltou a chave ou o bucket.
    corpo = "" if metodo == "HEAD" else "<Error><Code>%s</Code><Message>x</Message></Error>" % codigo
    return httpx.Response(status, text=corpo)


class S3Falso:
    """Bucket em memória atrás de `httpx.MockTransport`, com as recusas que o S3 faz."""

    def __init__(self, relogio=None):
        self.objetos: dict[str, tuple[bytes, str]] = {}
        self.pedidos: list[tuple[str, str]] = []
        self.falhas: list = []          # forçadas, em ordem: status HTTP ou exceção do httpx
        self.relogio = relogio or (lambda: datetime.now(timezone.utc))

    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.pedidos.append((req.method, req.url.path))
        if self.falhas:
            f = self.falhas.pop(0)
            if isinstance(f, Exception):
                raise f
            return _erro("InternalError", f, req.method)
        recusa = self._conferir(req)
        if recusa:
            return _erro(recusa, 403, req.method)
        bucket, _, chave = req.url.path.lstrip("/").partition("/")
        chave = unquote(chave)
        if bucket != BUCKET:
            return _erro("NoSuchBucket", 404, req.method)
        if req.method == "PUT":
            if hashlib.sha256(req.content).hexdigest() != req.headers["x-amz-content-sha256"]:
                return _erro("XAmzContentSHA256Mismatch", 400, "PUT")
            self.objetos[chave] = (req.content, req.headers.get("content-type", "binary/octet-stream"))
            return httpx.Response(200)
        if chave not in self.objetos:
            return _erro("NoSuchKey", 404, req.method)
        dados, tipo = self.objetos[chave]
        params = dict(req.url.params)
        cab = {"content-type": params.get("response-content-type", tipo)}
        if "response-content-disposition" in params:
            cab["content-disposition"] = params["response-content-disposition"]
        return httpx.Response(200, headers=cab, content=b"" if req.method == "HEAD" else dados)

    def _conferir(self, req: httpx.Request) -> str | None:
        """None = assinatura válida; senão o <Code> que o S3 devolveria."""
        params = dict(req.url.params)
        # O servidor nunca recebe o fragmento; o httpx o guarda no objeto, mas não o envia.
        base = str(req.url.copy_with(query=None, fragment=None))
        if "X-Amz-Signature" in params:                                # URL assinada
            quando = datetime.strptime(params["X-Amz-Date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            if self.relogio() > quando + timedelta(seconds=int(params["X-Amz-Expires"])):
                return "AccessDenied"                                  # "Request has expired"
            if params["X-Amz-Credential"] != "%s/%s/%s/s3/aws4_request" % (
                    CHAVE_ACESSO, quando.strftime("%Y%m%d"), REGIAO):
                return "InvalidAccessKeyId"
            extras = {k: v for k, v in params.items() if not k.startswith("X-Amz-")}
            refeita = storage.presign_url(base, CHAVE_ACESSO, SEGREDO, REGIAO, quando,
                                          int(params["X-Amz-Expires"]), extras)
            ok = parse_qs(urlsplit(refeita).query)["X-Amz-Signature"][0] == params["X-Amz-Signature"]
            return None if ok else "SignatureDoesNotMatch"
        m = RE_AUTH.match(req.headers.get("authorization", ""))
        if not m:
            return "AccessDenied"
        chave, _, regiao, assinados, assinatura = m.groups()
        if chave != CHAVE_ACESSO or regiao != REGIAO:
            return "InvalidAccessKeyId"
        quando = datetime.strptime(req.headers["x-amz-date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        if abs(self.relogio() - quando) > timedelta(minutes=15):
            return "RequestTimeTooSkewed"
        nomes = assinados.split(";")
        # O Host que o S3 lê é o do cabeçalho enviado, não o que o cliente achou que mandou.
        if "host" not in nomes or req.headers["host"] != storage._host(str(req.url)):
            return "SignatureDoesNotMatch"
        outros = {n: req.headers[n] for n in nomes if n not in ("host", "x-amz-date", "x-amz-content-sha256")}
        refeita = storage.assinar_cabecalhos(req.method, str(req.url), outros, req.headers["x-amz-content-sha256"],
                                             CHAVE_ACESSO, SEGREDO, REGIAO, quando)["authorization"]
        return None if refeita.endswith("Signature=" + assinatura) else "SignatureDoesNotMatch"


@pytest.fixture
def s3():
    return S3Falso(relogio=lambda: AGORA)


def _st(s3: S3Falso, **kw) -> storage.StorageS3:
    args = dict(endpoint=ENDPOINT, bucket=BUCKET, chave_acesso=CHAVE_ACESSO, segredo=SEGREDO, regiao=REGIAO)
    args.update(kw)
    return storage.StorageS3(transporte=s3.transporte(), relogio=lambda: AGORA, **args)


@pytest.fixture(autouse=True)
def _sem_espera(monkeypatch):
    monkeypatch.setattr(storage, "ESPERAS_S3", (0, 0))


# ====================================================================== SigV4 × AWS
def test_url_assinada_reproduz_o_exemplo_da_aws():
    url = storage.presign_url(AWS_HOST + "/test.txt", AWS_CHAVE, AWS_SEGREDO, "us-east-1", AWS_QUANDO, 86400)
    q = parse_qs(urlsplit(url).query)
    assert q["X-Amz-Credential"] == [AWS_CHAVE + "/20130524/us-east-1/s3/aws4_request"]
    assert q["X-Amz-Signature"] == ["aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"]


@pytest.mark.parametrize("metodo, caminho, extra, corpo, assinados, assinatura", [
    ("GET", "/test.txt", {"Range": "bytes=0-9"}, b"",
     "host;range;x-amz-content-sha256;x-amz-date",
     "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"),
    ("PUT", "/test$file.text", {"Date": "Fri, 24 May 2013 00:00:00 GMT",
                                "x-amz-storage-class": "REDUCED_REDUNDANCY"}, b"Welcome to Amazon S3.",
     "date;host;x-amz-content-sha256;x-amz-date;x-amz-storage-class",
     "98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd"),
    ("GET", "/?lifecycle", {}, b"", "host;x-amz-content-sha256;x-amz-date",
     "fea454ca298b7da1c68078a5d1bdbfbbe0d65c699e0f91ac7a200a0136783543"),
    ("GET", "/?max-keys=2&prefix=J", {}, b"", "host;x-amz-content-sha256;x-amz-date",
     "34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7"),
])
def test_cabecalho_authorization_reproduz_os_exemplos_da_aws(metodo, caminho, extra, corpo, assinados, assinatura):
    cab = storage.assinar_cabecalhos(metodo, AWS_HOST + caminho, extra, hashlib.sha256(corpo).hexdigest(),
                                     AWS_CHAVE, AWS_SEGREDO, "us-east-1", AWS_QUANDO)
    assert cab["authorization"] == ("AWS4-HMAC-SHA256 Credential=%s/20130524/us-east-1/s3/"
                                    "aws4_request, SignedHeaders=%s, Signature=%s"
                                    % (AWS_CHAVE, assinados, assinatura))
    assert cab["x-amz-date"] == "20130524T000000Z" and cab["host"] == "examplebucket.s3.amazonaws.com"


def test_host_assinado_leva_a_porta_quando_nao_e_a_padrao():
    assert storage._host("http://minio:9000/b/k") == "minio:9000"
    assert storage._host("https://x.r2.cloudflarestorage.com:443/b/k") == "x.r2.cloudflarestorage.com"


# ====================================================================== put / get / existe
def test_put_get_existe_com_as_mesmas_chaves_do_fs(s3):
    st = _st(s3)
    assert st.existe(CHAVE_PDF) is False
    assert st.put(CHAVE_PDF, PDF) == SHA_PDF
    assert st.existe(CHAVE_PDF) is True
    assert st.get(CHAVE_PDF) == PDF
    # path-style e chave sem encoding nenhum: é a mesma string de arquivos.storage_key
    assert ("PUT", "/%s/%s" % (BUCKET, CHAVE_PDF)) in s3.pedidos
    assert s3.objetos[CHAVE_PDF][1] == "application/pdf"
    st.put(CHAVE_HTML, HTML)
    assert s3.objetos[CHAVE_HTML][1].startswith("text/html")


def test_get_de_chave_inexistente_e_objeto_inexistente(s3):
    with pytest.raises(storage.ObjetoInexistente):
        _st(s3).get(CHAVE_PDF)


def test_put_recusa_conteudo_divergente_e_chave_invalida_antes_da_rede(s3):
    st = _st(s3)
    with pytest.raises(storage.ConteudoDivergente):
        st.put(CHAVE_PDF, b"outro conteudo")
    for chave in ("../fora.pdf", "pdf/a b.pdf", "/abs.pdf"):
        for chamada in (lambda: st.put(chave, b"x"), lambda: st.get(chave), lambda: st.existe(chave),
                        lambda: st.presign(chave)):
            with pytest.raises(storage.ChaveInvalida):
                chamada()
    assert s3.pedidos == []


def test_credencial_errada_503_com_dica_e_sem_segredo(s3):
    st = _st(s3, segredo="segredo-errado")
    with pytest.raises(storage.StorageIndisponivel) as e:
        st.get(CHAVE_PDF)
    msg = str(e.value)
    assert "403" in msg and "SignatureDoesNotMatch" in msg and "S3_SECRET" in msg
    assert "segredo-errado" not in msg and SEGREDO not in msg


def test_5xx_passageiro_e_repetido(s3):
    s3.objetos[CHAVE_PDF] = (PDF, "application/pdf")
    s3.falhas = [503, httpx.ConnectError("caiu")]
    assert _st(s3).get(CHAVE_PDF) == PDF
    assert [m for m, _ in s3.pedidos] == ["GET", "GET", "GET"]


def test_bucket_fora_do_ar_vira_storage_indisponivel(s3):
    s3.falhas = [httpx.ConnectError("caiu")] * 3
    with pytest.raises(storage.StorageIndisponivel, match="3 tentativas"):
        _st(s3).put(CHAVE_PDF, PDF)
    s3.falhas = [httpx.ConnectTimeout("lento")]
    with pytest.raises(storage.StorageIndisponivel, match="ConnectTimeout"):
        _st(s3).existe(CHAVE_PDF)          # HEAD: uma tentativa só (quem clicou prefere 503 rápido)


def test_sem_configuracao_diz_o_nome_nunca_o_valor(s3):
    st = _st(s3, segredo=None, bucket=None)
    with pytest.raises(storage.StorageIndisponivel) as e:
        st.put(CHAVE_PDF, PDF)
    assert "S3_SECRET" in str(e.value) and "S3_BUCKET" in str(e.value) and CHAVE_ACESSO not in str(e.value)
    ruim = _st(s3, endpoint="conta.r2.cloudflarestorage.com")        # sem esquema
    assert any("S3_ENDPOINT" in p for p in ruim.problemas())
    assert any("S3_BUCKET" in p for p in _st(s3, bucket="Bucket_Com_Maiuscula").problemas())
    assert s3.pedidos == []


# ====================================================================== presign
def test_presign_de_10_minutos_abre_o_pdf_inline(s3):
    st = _st(s3)
    st.put(CHAVE_PDF, PDF)
    url = st.presign(CHAVE_PDF, tipo="application/pdf", disposicao='inline; filename="Edital.pdf"')
    partes = urlsplit(url)
    q = parse_qs(partes.query)
    assert "%s://%s" % (partes.scheme, partes.netloc) == ENDPOINT
    assert partes.path == "/%s/%s" % (BUCKET, CHAVE_PDF) and not partes.fragment
    assert q["X-Amz-Expires"] == ["600"] and q["X-Amz-SignedHeaders"] == ["host"]
    assert q["X-Amz-Credential"] == ["%s/20260924/auto/s3/aws4_request" % CHAVE_ACESSO]
    assert SEGREDO not in url
    # o navegador segue o Location: o bucket confere a assinatura e responde com os overrides
    r = httpx.Client(transport=s3.transporte()).get(url)
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == 'inline; filename="Edital.pdf"'


def test_presign_expira(s3):
    st = _st(s3)
    st.put(CHAVE_PDF, PDF)
    url = st.presign(CHAVE_PDF)
    s3.relogio = lambda: AGORA + timedelta(seconds=601)
    assert httpx.Client(transport=s3.transporte()).get(url).status_code == 403
    with pytest.raises(ValueError):
        st.presign(CHAVE_PDF, expira=8 * 24 * 3600)      # acima do teto da SigV4
    with pytest.raises(ValueError):
        st.presign(CHAVE_PDF, expira=0)


def test_presign_adulterado_e_recusado(s3):
    st = _st(s3)
    st.put(CHAVE_PDF, PDF)
    url = st.presign(CHAVE_PDF).replace("X-Amz-Expires=600", "X-Amz-Expires=86400")
    assert httpx.Client(transport=s3.transporte()).get(url).status_code == 403


# ====================================================================== /health
def test_descrever_ok_com_bucket_de_pe(s3):
    d = _st(s3).descrever()
    assert d == {"backend": "s3", "raiz": "s3://" + BUCKET, "regiao": REGIAO, "ok": True,
                 "endpoint": ENDPOINT}
    assert s3.pedidos == [("GET", "/%s/%s" % (BUCKET, storage.CHAVE_SONDA))]


@pytest.mark.parametrize("kw, trecho", [
    ({"bucket": "outro-bucket"}, "não existe"),
    ({"segredo": "errado"}, "S3_SECRET"),
    ({"segredo": None}, "S3_SECRET"),
])
def test_descrever_diz_o_que_esta_errado_sem_segredo(s3, kw, trecho):
    d = _st(s3, **kw).descrever()
    assert d["ok"] is False and trecho in d["erro"]
    assert SEGREDO not in repr(d) and "errado" not in repr(d).replace("S3_SECRET", "")


def test_descrever_nunca_passa_do_prazo(s3, monkeypatch):
    import threading
    solta = threading.Event()

    def travado(req):
        solta.wait(5)
        return httpx.Response(404)
    monkeypatch.setattr(storage, "TIMEOUT_SONDA_S3", 0.2)
    st = storage.StorageS3(ENDPOINT, BUCKET, CHAVE_ACESSO, SEGREDO, REGIAO, transporte=httpx.MockTransport(travado))
    try:
        d = st.descrever()
    finally:
        solta.set()
    assert d["ok"] is False and "não respondeu" in d["erro"]


def test_abrir_pelo_config_com_as_variaveis_s3(monkeypatch):
    for k, v in {"STORAGE_BACKEND": "s3", "S3_ENDPOINT": ENDPOINT + "/", "S3_BUCKET": BUCKET,
                 "S3_KEY": CHAVE_ACESSO, "S3_SECRET": SEGREDO}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("S3_REGION", raising=False)
    cfg = config.carregar()
    assert SEGREDO not in repr(cfg) and CHAVE_ACESSO not in repr(cfg)
    st = storage.abrir(cfg)
    assert isinstance(st, storage.StorageS3) and st.problemas() == []
    assert (st.endpoint, st.bucket, st.regiao) == (ENDPOINT, BUCKET, "auto")


# ====================================================================== site
LEITOR = {"email": "leitor@teste.br", "papel": "leitor", "nome": "Leitor"}
ARQUIVOS = {(SLUG, 7): {"id": 7, "nome": "01 - Edital nº 7.pdf", "storage_key": CHAVE_PDF, "status": "ok"}}


class _BancoFalso:
    conn = object()          # as consultas estão substituídas: nada executa SQL


@pytest.fixture
def site_s3(monkeypatch):
    """Site com STORAGE_BACKEND=s3 apontando para o S3Falso; relógio de verdade (o site assina agora)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    for k, v in {"FOPA_ENV": "prod", "SESSION_SECRET": "segredo-de-sessao", "STORAGE_BACKEND": "s3",
                 "S3_ENDPOINT": ENDPOINT, "S3_BUCKET": BUCKET, "S3_KEY": CHAVE_ACESSO, "S3_SECRET": SEGREDO,
                 "S3_REGION": REGIAO}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    falso = S3Falso()
    falso.objetos[CHAVE_PDF] = (PDF, "binary/octet-stream")      # como um sync sem tipo deixaria
    falso.objetos[CHAVE_HTML] = (HTML, "text/html")
    monkeypatch.setattr(site_mod.consultas, "arquivo_do_slug", lambda conn, slug, i: ARQUIVOS.get((slug, i)))
    monkeypatch.setattr(site_mod.consultas, "publicacao_vigente",
                        lambda conn, slug: {"controle": "c", "verificacao_id": 42, "html_uri": CHAVE_HTML}
                        if slug == SLUG else None)
    site_mod.app.state.transporte_s3 = falso.transporte()
    cli = TestClient(site_mod.app)
    try:
        yield cli, falso
    finally:
        site_mod.app.dependency_overrides.clear()
        site_mod.app.state.transporte_s3 = None


def _entrar():
    site_mod.app.dependency_overrides[site_mod.usuario_atual] = lambda: LEITOR
    site_mod.app.dependency_overrides[site_mod.banco] = lambda: _BancoFalso()


def test_pdf_sem_sessao_401_sempre_e_o_bucket_nem_e_tocado(site_s3):
    cli, falso = site_s3
    for rota in ("/api/pdf/%s/7" % SLUG, "/api/pdf/%s/999" % SLUG, "/api/pdf/nao-existe/1",
                 "/api/licitacoes/%s/relatorio" % SLUG):
        r = cli.get(rota, follow_redirects=False)
        assert r.status_code == 401, rota
        assert "location" not in r.headers and b"%PDF" not in r.content
    assert falso.pedidos == []


def test_pdf_302_para_url_assinada_e_o_page_sobrevive(site_s3):
    cli, falso = site_s3
    _entrar()
    # O navegador nunca manda o fragmento; o httpx também não.
    r = cli.get("/api/pdf/%s/7#page=5" % SLUG, follow_redirects=False)
    assert r.status_code == 302
    destino = r.headers["location"]
    partes = urlsplit(destino)
    assert "%s://%s" % (partes.scheme, partes.netloc) == ENDPOINT          # absoluta, no bucket
    assert partes.path == "/%s/%s" % (BUCKET, CHAVE_PDF)
    assert "#" not in destino and parse_qs(partes.query)["X-Amz-Expires"] == ["600"]
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert SEGREDO not in destino
    # RFC 9110, 10.2.2: Location sem fragmento herda o da URL pedida. É assim
    # que "/api/pdf/...#page=5" termina em "<url assinada>#page=5".
    herdado = destino + "#" + urlsplit("/api/pdf/%s/7#page=5" % SLUG).fragment
    assert herdado.endswith("#page=5")
    # Seguindo o redirect (o httpx tira o fragmento, como o navegador): o bucket
    # entrega o PDF para abrir no leitor, com o nome original.
    pdf = httpx.Client(transport=falso.transporte()).get(herdado)
    assert pdf.status_code == 200 and pdf.content == PDF
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"] == "inline; filename*=utf-8''01%20-%20Edital%20n%C2%BA%207.pdf"
    assert [m for m, _ in falso.pedidos] == ["HEAD", "GET"]


def test_pdf_ausente_do_bucket_404_e_de_outra_licitacao_404(site_s3):
    cli, falso = site_s3
    _entrar()
    del falso.objetos[CHAVE_PDF]
    r = cli.get("/api/pdf/%s/7" % SLUG, follow_redirects=False)
    assert r.status_code == 404 and "bucket" in r.json()["detail"]
    n = len(falso.pedidos)
    assert cli.get("/api/pdf/outro-slug/7", follow_redirects=False).status_code == 404
    assert len(falso.pedidos) == n                    # id de outra licitação nem consulta o bucket


def test_pdf_com_bucket_fora_503_nunca_500(site_s3):
    cli, falso = site_s3
    _entrar()
    falso.falhas = [httpx.ConnectError("caiu")]
    r = cli.get("/api/pdf/%s/7" % SLUG, follow_redirects=False)
    assert r.status_code == 503 and "ConnectError" in r.json()["detail"]


def test_pdf_com_s3_sem_configuracao_503_com_o_nome(site_s3, monkeypatch):
    cli, falso = site_s3
    _entrar()
    monkeypatch.delenv("S3_SECRET")
    r = cli.get("/api/pdf/%s/7" % SLUG, follow_redirects=False)
    assert r.status_code == 503 and "S3_SECRET" in r.json()["detail"]
    assert falso.pedidos == []


def test_relatorio_no_s3_passa_pela_api_com_a_csp(site_s3):
    cli, falso = site_s3
    _entrar()
    r = cli.get("/api/licitacoes/%s/relatorio" % SLUG, follow_redirects=False)
    assert r.status_code == 200 and r.content == HTML
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["content-security-policy"] == site_mod.CSP_RELATORIO
    del falso.objetos[CHAVE_HTML]
    assert cli.get("/api/licitacoes/%s/relatorio" % SLUG).status_code == 404
    falso.falhas = [httpx.ConnectError("caiu")] * 3
    r = cli.get("/api/licitacoes/%s/relatorio" % SLUG)
    assert r.status_code == 503 and "3 tentativas" in r.json()["detail"]
