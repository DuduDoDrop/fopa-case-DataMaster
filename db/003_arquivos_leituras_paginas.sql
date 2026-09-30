-- 003 — o que foi baixado (arquivos), o texto congelado (leituras + paginas).
--
-- `paginas` é a peça central da ADR-011: reverificar nunca faz OCR novo, lê
-- o texto exatamente como estava quando o modelo respondeu. Por isso a
-- tabela é imutável e versionada por `leituras.vigente`.

CREATE TABLE arquivos (
    id               bigserial PRIMARY KEY,
    controle         text NOT NULL REFERENCES licitacoes (controle),
    seq              int,                 -- sequencialDocumento do PNCP
    tipo             text,
    titulo           text,
    -- O nome original é o marcador de citação ("=== ARQUIVO x | PÁGINA n ===");
    -- a chave de storage é content-addressed e não carrega nome.
    nome             text NOT NULL,
    sha256           char(64),
    bytes            bigint,
    bytes_aproximado bool NOT NULL DEFAULT false,   -- legado em kb*1024
    origem_url       text,
    baixado_em       timestamptz,
    formato_real     text,
    status           text NOT NULL CHECK (status IN (
                         'ok', 'recusado_politica', 'formato_nao_suportado', 'corrompido',
                         'falha_rede', 'zip_container', 'alias_duplicado', 'fora_inventario',
                         'procedencia_incerta')),
    motivo           text,
    pai_id           bigint REFERENCES arquivos (id),   -- ZIP de onde saiu
    alias_de         bigint REFERENCES arquivos (id),   -- mesmo sha no mesmo controle
    paginas          int,
    chars            int,
    requer_ocr       bool,
    storage_key      text,
    ativo_pncp       bool,
    proveniencia     jsonb,
    UNIQUE (controle, nome)
);

CREATE INDEX arquivos_sha256 ON arquivos (sha256);

CREATE TABLE leituras (
    id                  bigserial PRIMARY KEY,
    controle            text NOT NULL REFERENCES licitacoes (controle),
    preparado_em        timestamptz NOT NULL DEFAULT now(),
    segundos            numeric(10,3),
    -- Tesseract 5.4.0 é a versão das medições (ADR-008); leitura sem versão
    -- declarada não existe.
    versao_ocr          text NOT NULL,
    tessdata_sha256     char(64),
    condicoes           jsonb,
    hashes_bytes        jsonb,
    assinatura          jsonb,
    assinatura_conjunto char(64),
    modo_sugerido       text,
    chars_total         int,
    procedencia_texto   text CHECK (procedencia_texto IN ('worker', 'legado_paginas_json')),
    vigente             bool NOT NULL DEFAULT false,
    UNIQUE (controle, assinatura_conjunto, versao_ocr)
);

CREATE UNIQUE INDEX leituras_vigente ON leituras (controle) WHERE vigente;
CREATE INDEX leituras_assinatura ON leituras (assinatura_conjunto);

ALTER TABLE licitacoes
    ADD CONSTRAINT licitacoes_leitura_vigente_fk
    FOREIGN KEY (leitura_vigente_id) REFERENCES leituras (id);

-- TEXTO CONGELADO. `numero` é a página FÍSICA do PDF (RN-08, ADR-005), a que o
-- leitor mostra e a que o link `#page=N` abre. `ordem` é a precedência de
-- documento (extrator.PRECEDENCIA) com que o texto foi montado no prompt.
CREATE TABLE paginas (
    leitura_id   bigint NOT NULL REFERENCES leituras (id) ON DELETE CASCADE,
    arquivo_id   bigint REFERENCES arquivos (id),
    arquivo_nome text NOT NULL,
    numero       int NOT NULL,
    ordem        int NOT NULL,
    texto        text NOT NULL,
    via_ocr      bool NOT NULL DEFAULT false,
    PRIMARY KEY (leitura_id, arquivo_nome, numero)
);
