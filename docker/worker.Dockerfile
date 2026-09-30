# syntax=docker/dockerfile:1
# FOPA v3 — imagem do worker (e da api, e da migração: é UMA imagem)
#
# Por que esta imagem compila o Tesseract em vez de instalar o do apt:
# todos os números de OCR do projeto saíram do Tesseract 5.4.0 (ADR-008), e o
# Debian bookworm traz a 5.3.0 — que em 23/09 deu 0 de 6 páginas idênticas e
# leu o fio de uma tabela como o algarismo `1` (BACKLOG.md:427-463). A guarda
# numérica da ADR-004 reprova qualquer algarismo que não esteja na página, então
# "quase a mesma versão" muda veredito. A versão é fixa, o build confere.
#
# Tudo que a imagem baixa tem versão E sha256 pinados: tarballs de leptonica e
# Tesseract, e o `por.traineddata` (que não está no git, .gitignore "tessdata/").
# `sha256sum -c` falha o build se um byte divergir — nunca instala outra coisa
# em silêncio. Os shas foram calculados dos tarballs baixados em 24/09/2026.
#
#   docker compose -f docker/compose.yml build fopa-worker
#   docker compose -f docker/compose.yml up -d fopa-postgres fopa-worker fopa-api
#
# Esta imagem NUNCA recebe ANTHROPIC_API_KEY (plano, seção 4): quem chama o
# modelo é o n8n, com a Credential. O `/health` do worker informa
# `anthropic_key_presente`, e o compose garante que é `false`.

# A versão do Tesseract tem UMA fonte: este ARG global, redeclarado sem valor
# nos estágios que o usam (compilar e conferir). O estágio final repetia "5.4.0"
# à mão no ENV e no portão — trocar o ARG compilaria uma versão e conferiria outra.
ARG TESSERACT_VERSAO=5.4.0

# ============================================================ stage 1: compilar
# Só ferramentas de build; nada daqui vai para a imagem final além de
# /usr/local/{bin,lib,share}. Mudar um .py do projeto não invalida esta camada.
FROM debian:bookworm-slim AS build

ARG LEPTONICA_VERSAO=1.84.1
ARG LEPTONICA_SHA256=2b3e1254b1cca381e77c819b59ca99774ff43530209b9aeb511e1d46588a64f6
ARG TESSERACT_VERSAO
ARG TESSERACT_SHA256=30ceffd9b86780f01cbf4eaf9b7fc59abddfcbaf5bbd52f9a633c6528cb183fd

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
        build-essential autoconf automake libtool pkg-config \
        libpng-dev libjpeg62-turbo-dev libtiff-dev zlib1g-dev \
        libwebp-dev libopenjp2-7-dev libgif-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# leptonica: o tarball de release já traz o `configure` gerado.
RUN curl -fsSL -o leptonica.tar.gz \
        "https://github.com/DanBloomberg/leptonica/releases/download/${LEPTONICA_VERSAO}/leptonica-${LEPTONICA_VERSAO}.tar.gz" \
    && echo "${LEPTONICA_SHA256}  leptonica.tar.gz" | sha256sum -c - \
    && tar xzf leptonica.tar.gz \
    && cd "leptonica-${LEPTONICA_VERSAO}" \
    && ./configure --prefix=/usr/local --disable-static \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    && cd /src && rm -rf leptonica.tar.gz "leptonica-${LEPTONICA_VERSAO}"

# Tesseract: o tarball da tag do GitHub NÃO traz `configure` — daí autoconf,
# automake e libtool no apt acima e o `autogen.sh` aqui. Sem as ferramentas de
# treino (`make training`): a imagem só reconhece, nunca treina.
# PKG_CONFIG_PATH aponta para o `lept.pc` recém-instalado, senão o configure
# procura a leptonica do sistema (que não existe) e falha.
RUN curl -fsSL -o tesseract.tar.gz \
        "https://github.com/tesseract-ocr/tesseract/archive/refs/tags/${TESSERACT_VERSAO}.tar.gz" \
    && echo "${TESSERACT_SHA256}  tesseract.tar.gz" | sha256sum -c - \
    && tar xzf tesseract.tar.gz \
    && cd "tesseract-${TESSERACT_VERSAO}" \
    && ./autogen.sh \
    && PKG_CONFIG_PATH=/usr/local/lib/pkgconfig ./configure --prefix=/usr/local --disable-static \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    && cd /src && rm -rf tesseract.tar.gz "tesseract-${TESSERACT_VERSAO}" \
    && test "$(tesseract --version 2>&1 | head -1 | awk '{print $2}')" = "${TESSERACT_VERSAO}"

# ============================================================ stage 1b: site
# O front React (web/) é construído AQUI, não no host: o host não tem Node, e
# o que vai para a imagem é só `dist/` (HTML + JS + CSS estáticos) — nem o Node
# nem o node_modules entram na imagem final. `npm ci` segue o
# package-lock.json à risca; lock divergente do package.json falha o build.
# `npm test` roda antes do build: card com custo NULL dizendo R$ 0,00 ou
# "urgentes" com encerrada não chegam à imagem.
# Os COPY são por arquivo, não `COPY web/`: um `web/node_modules` do host (de
# um `npm install` rodado em container com bind mount) não pode sobrescrever
# o que o `npm ci` instalou aqui, e o .dockerignore da raiz não é deste stage.
FROM node:22-alpine AS web

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/index.html web/vite.config.ts web/tsconfig.json ./
COPY web/design/ ./design/
COPY web/src/ ./src/
RUN npm test && npm run build

# ============================================================ stage 2: runtime
FROM python:3.12-slim-bookworm

# Bibliotecas que o binário compilado precisa em tempo de execução (as `-dev`
# do stage 1 ficam lá). libgomp1 é o OpenMP do Tesseract; poppler-utils é o
# `pdftoppm`/`pdfinfo` que alguns scripts do pacote chamam. A conferência
# `ldd ... not found` abaixo é o que pega uma biblioteca esquecida aqui, no
# build, e não no primeiro OCR em produção.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
        libpng16-16 libjpeg62-turbo libtiff6 libwebp7 libwebpmux3 \
        libopenjp2-7 libgif7 libgomp1 poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# O python:3.12-slim já usa /usr/local (python3, pip...): o COPY soma o
# tesseract e a leptonica aos diretórios, não substitui nada. A leptonica
# 1.84 chama a biblioteca de `libleptonica.so.6` (o nome `liblept.so` acabou
# na 1.83) — um glob errado aqui não falha o COPY, só o `ldd` abaixo.
COPY --from=build /usr/local/bin/tesseract /usr/local/bin/tesseract
COPY --from=build /usr/local/lib/libtesseract.so* /usr/local/lib/libleptonica.so* /usr/local/lib/
COPY --from=build /usr/local/share/tessdata /usr/local/share/tessdata
RUN ldconfig \
    && ! ldd /usr/local/bin/tesseract | grep -q "not found"

# por.traineddata de um COMMIT fixo do tessdata_fast, com sha256 conferido.
# O sha é o do arquivo local que gerou todas as medições (1.982.756 bytes,
# ledger F0); o mesmo arquivo está em 4.0.0, 4.1.0 e main, e o commit pinado é
# o que impede "main" de mudar debaixo da imagem. O build FALHA se divergir.
ARG TESSDATA_COMMIT=923915d4ced2a7235221788285785a29c4a42d4a
ARG FOPA_TESSDATA_SHA256=c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb
RUN curl -fsSL -o /usr/local/share/tessdata/por.traineddata \
        "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/${TESSDATA_COMMIT}/por.traineddata" \
    && echo "${FOPA_TESSDATA_SHA256}  /usr/local/share/tessdata/por.traineddata" | sha256sum -c -

# A mesma versão que o stage 1 compilou (ARG global): é o que o ENV e o portão abaixo conferem.
ARG TESSERACT_VERSAO

# FOPA_TESSERACT/FOPA_TESSDATA são o que `fopa.ocr` lê (o padrão dele é o
# caminho do Windows); TESSDATA_PREFIX é o que o binário lê. Os três apontam
# para o mesmo lugar de propósito: divergência entre eles foi o bug do
# tessdata "emprestado" de outro projeto (ver docstring de fopa/ocr.py).
ENV TESSDATA_PREFIX=/usr/local/share/tessdata \
    FOPA_TESSERACT=/usr/local/bin/tesseract \
    FOPA_TESSDATA=/usr/local/share/tessdata \
    FOPA_TESSERACT_ESPERADO=${TESSERACT_VERSAO} \
    FOPA_TESSDATA_SHA256=${FOPA_TESSDATA_SHA256} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Portões de build do binário: versão exata e português disponível. Antes de
# qualquer COPY do código, para que uma falha aqui seja atribuída ao OCR sem ambiguidade.
RUN test "$(tesseract --version 2>&1 | head -1 | awk '{print $2}')" = "${TESSERACT_VERSAO}" \
    && tesseract --list-langs 2>/dev/null | grep -qx por

WORKDIR /app

# Dependências antes do código: camada estável, cache de build aproveitado.
# Os três requirements somam-se (pacote fopa + api + db); a imagem é uma só.
COPY requirements.txt ./requirements.txt
COPY api/requirements.txt ./api/requirements.txt
COPY db/requirements.txt ./db/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r api/requirements.txt -r db/requirements.txt

# O fluxo de exceção do download (api/converter.py, 25/09/2026): o arquivo do PNCP que não é PDF vira PDF aqui.
# LibreOffice sem tela — writer para RTF, DOC, DOCX, ODT e HTML; calc para XLS, XLSX e ODS — e o bsdtar do
# libarchive para RAR (o `7zip` do bookworm vem sem o código do RAR, que não é livre). As fontes têm a métrica das
# do Office (Liberation = Arial/Times/Courier; Carlito/Caladea = Calibri/Cambria): sem elas a paginação do .doc
# muda. Camada própria antes do código: mexer no conversor não reinstala o LibreOffice. O build falha se os dois
# programas não responderem.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui libreoffice-calc-nogui \
        fonts-liberation2 fonts-crosextra-carlito fonts-crosextra-caladea fonts-dejavu-core \
        libarchive-tools \
    && rm -rf /var/lib/apt/lists/* \
    && soffice --version \
    && bsdtar --version

# A estrutura do repositório é preservada de propósito: o pacote resolve
# `amostras/` e `saidas/` relativo ao PAI de scripts/, e `api/__init__.py` põe
# `<raiz>/scripts` no sys.path. Achatar tudo em /app quebraria a resolução —
# e quebrou, no primeiro build da v2. Nunca bind mount por cima disto: o
# código é congelado no build e o `/health` devolve o git sha.
COPY scripts/ ./scripts/
COPY api/ ./api/
COPY db/ ./db/
# O importador do acervo v2 (plano, seção 9) roda nesta mesma imagem, pelo
# serviço `fopa-importar` do compose; o snapshot vem montado, nunca copiado.
COPY migracao/ ./migracao/
COPY tests/ocr_baseline/ ./tests/ocr_baseline/
COPY amostras/_fixture/ ./amostras/_fixture/

# Portão pelo caminho de código do pipeline (não só pelo binário): é o
# `checar_ambiente` que o `/health` chama. Rodado de dentro de scripts/, como o
# pacote é usado.
RUN cd scripts && python -c "from fopa import ocr; a = ocr.checar_ambiente(); \
assert 'por' in a['idiomas'], 'tessdata sem portugues: %s' % a; \
print('OCR pronto:', a['tesseract'], a['idiomas'])"

# Medição de equivalência de OCR com o host das medições (6 páginas de São
# Lourenço do Sul, 150 dpi). NUNCA falha o build: "OCR idêntico" entre o build
# MSVC/AVX512 do host e o gcc/Linux daqui é hipótese, e o que se garante é que
# a diferença seja VISTA e registrada (plano, seção 6 "Imagem"; README do
# baseline: "a imagem é a referência" se não reproduzir). O compose copia o
# JSON para docs/ocr-equivalencia-<sha>.json.
RUN mkdir -p /app/docs \
    && python tests/ocr_baseline/medir.py --saida /app/docs/ocr-equivalencia-imagem.json

# O site (stage `web`): a fopa-api roda nesta mesma imagem e serve
# /app/web/dist na mesma origem do /api (plano §8: sem CORS, cookie de sessão
# same-origin). Depois da medição de OCR de propósito: mexer no front não
# refaz o OCR das 6 páginas.
COPY --from=web /web/dist/ ./web/dist/

# Sha do commit que gerou a imagem, gravado por último para não invalidar as
# camadas acima a cada commit. `api.versao.git_sha()` lê a env (não há .git aqui).
ARG FOPA_GIT_SHA=desconhecido
ENV FOPA_GIT_SHA=${FOPA_GIT_SHA}

EXPOSE 8000
CMD ["uvicorn", "api.worker:app", "--host", "0.0.0.0", "--port", "8000"]
