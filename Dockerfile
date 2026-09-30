# FOPA — imagem reprodutível
#
# Existe por um motivo específico: o Tesseract é dependência de SISTEMA, não de pip,
# e o tessdata padrão NÃO inclui português. Essa é a única barreira real de
# reprodutibilidade do projeto, e aqui ela fica resolvida e explícita.
#
#   docker build -t fopa .
#   docker run --rm fopa                                   # verifica o ambiente
#   docker run --rm -e ANTHROPIC_API_KEY=sk-ant-... \
#       -v "$(pwd)/amostras:/app/amostras" \
#       -v "$(pwd)/saidas:/app/saidas" \
#       fopa python 10_extrair_edital.py "<pasta da licitação>"
#
# Sem chave, o pipeline roda com --simulado e exercita tudo menos a chamada ao modelo.

FROM python:3.12-slim-bookworm

# tesseract-ocr-por é o pacote que carrega por.traineddata.
# Sem ele o OCR roda em inglês e perde 6,4 pontos de acurácia — em silêncio.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-por \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FOPA_TESSERACT=/usr/bin/tesseract \
    FOPA_TESSDATA=/usr/share/tesseract-ocr/5/tessdata \
    # O container usa o tessdata do apt, nao o `tessdata/` do projeto:
    # aqui o `tesseract-ocr-por` ja instalou o idioma, e baixar de novo
    # seria buscar na internet o que o build ja trouxe. \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# dependências antes do código: camada estável, cache de build aproveitado
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# A estrutura do repositório é preservada de propósito: o código resolve
# `amostras/` e `saidas/` relativo ao diretório PAI de scripts/. Achatar tudo em
# /app quebraria essa resolução — e quebrou, no primeiro build.
COPY scripts/ ./scripts/
COPY amostras/_fixture/ ./amostras/_fixture/

WORKDIR /app/scripts

# Falha o BUILD se o português não estiver disponível.
# Preferível descobrir aqui do que numa extração que devolve página vazia sem avisar.
RUN python -c "from fopa import ocr; a = ocr.checar_ambiente(); \
assert 'por' in a['idiomas'], 'tessdata sem portugues: %s' % a; \
print('OCR pronto:', a['tesseract'], a['idiomas'])"

# Teste de fumaça 1: o pipeline inteiro sobre o fixture, sem chamar o modelo.
RUN python 10_extrair_edital.py \
        "_fixture/Concorrencia - Eletronica - Sao Lourenco do Sul-RS" \
        --simulado --saida /tmp/fumaca >/dev/null \
    && test -f "/tmp/fumaca/auditoria.json" \
    && echo "teste de fumaca 1 (pipeline sobre fixture): OK"

# Teste de fumaça 2: a bateria adversarial.
#
# Vale mais que o primeiro como garantia de máquina limpa, por um motivo
# específico: ela NÃO depende de dado externo. Os editais são gerados em
# memória, então o teste exercita o gerador sintético, o extrator, a recuperação
# e TODAS as regras do verificador sem precisar de um único PDF no disco.
#
# Se o build passa, a superfície nova do projeto está de pé na imagem.
RUN python 21_adversarial.py --simulado >/dev/null \
    && test -f "/app/saidas/_adversarial_simulado.json" \
    && echo "teste de fumaca 2 (bateria adversarial): OK"

CMD ["python", "-c", "from fopa import ocr; import json; \
print(json.dumps(ocr.checar_ambiente(), ensure_ascii=False, indent=1)); \
print('\\nFOPA pronto. Exemplos:'); \
print('  python 10_extrair_edital.py \"<pasta>\" --simulado'); \
print('  python 10_extrair_edital.py \"<pasta>\"      (requer ANTHROPIC_API_KEY)'); \
print('  python demo.py --rapido')"]
