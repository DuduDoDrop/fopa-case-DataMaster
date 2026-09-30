-- 028 — o texto furtivo, com o TEXTO, e se ele é mesmo suspeito (24/09/2026).
--
-- A condição da leitura só guardava "arquivo p.N: motivo". Conferido à mão em 24/09: das 481 extrações
-- do agente, 135 levavam a tag "Prompt Injection" e NENHUMA tinha instrução — era timbre branco em
-- faixa colorida, a camada de OCR (alpha 0) de página escaneada, planta baixa em letra minúscula e
-- metadado de impressão fora da página. A correção: só o trecho com cara de instrução é
-- suspeito, e o texto identificado passa a aparecer num "ver mais" abaixo do aviso.
--
-- O detector (scripts/fopa/furtivo.py) acha LINHA a linha; aqui cada linha da tabela é um trecho:
-- as linhas escondidas de uma mesma página e do mesmo tipo, juntas (api/injecao.py). Junto porque uma
-- instrução quebrada em duas linhas continua sendo uma instrução, e porque a camada de OCR de um PDF
-- escaneado são centenas de linhas por página. A tag só nasce de trecho `suspeito` (cara de instrução
-- para IA); o resto fica registrado e visível no "ver mais", sem degradar a leitura.

CREATE TABLE furtivos_achados (
    id          bigserial PRIMARY KEY,
    leitura_id  bigint NOT NULL REFERENCES leituras (id),
    arquivo     text NOT NULL,
    pagina      int NOT NULL,
    motivo      text NOT NULL,          -- o do detector: texto branco, alpha 0, corpo < 3pt, fora da página
    texto       text NOT NULL,          -- as linhas juntas, cortado em api/injecao.py:LIMITE_TEXTO
    linhas      int NOT NULL DEFAULT 1, -- quantas linhas do detector este trecho junta
    caracteres  int NOT NULL DEFAULT 0, -- o tamanho do texto inteiro, antes do corte
    tamanho     numeric(6, 2),          -- o menor corpo (pt) entre as linhas
    classe      text NOT NULL,          -- por que é (ou não é) suspeito, em português
    suspeito    bool NOT NULL,
    varrido_em  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX furtivos_achados_leitura ON furtivos_achados (leitura_id);

-- Leitura já varrida de novo (mesmo sem achado): sem esta marca, "nenhuma linha" não diria se o
-- detector rodou e não achou nada ou se nunca rodou.
CREATE TABLE furtivos_varreduras (
    leitura_id  bigint PRIMARY KEY REFERENCES leituras (id),
    arquivos    int NOT NULL,
    achados     int NOT NULL,
    suspeitos   int NOT NULL,
    erro        text,
    em          timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE ON furtivos_achados, furtivos_varreduras TO worker_rw;
GRANT USAGE, SELECT ON SEQUENCE furtivos_achados_id_seq TO worker_rw;
GRANT SELECT ON furtivos_achados, furtivos_varreduras TO api_ro, api_rw, n8n_rw;
