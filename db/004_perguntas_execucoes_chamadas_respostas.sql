-- 004 — o questionário, as execuções de modelo, as chamadas e as respostas cruas.
--
-- Procedência é o tema deste arquivo. `execucoes_modelo` diz QUEM respondeu
-- (api / agente / harness / experimento / simulado / gravado / legado) e
-- quanto custou; `chamadas_modelo` guarda cada ida ao modelo com o custo
-- calculado NA HORA (via /custo) — é sobre ela que a view gasto_diario soma,
-- para que lotes pagos de execuções `parcial` nunca sumam da conta.

CREATE TABLE perguntas (
    id                   text PRIMARY KEY CHECK (id ~ '^Q\d+$'),
    texto                text NOT NULL,
    orienta              text,
    formato              text,
    critico              bool NOT NULL DEFAULT false,
    versao_questionario  text
);

CREATE TABLE execucoes_modelo (
    id                   bigserial PRIMARY KEY,
    controle             text NOT NULL REFERENCES licitacoes (controle),
    leitura_id           bigint REFERENCES leituras (id),
    origem               text NOT NULL CHECK (origem IN (
                             'api', 'agente', 'harness', 'experimento', 'simulado', 'gravado', 'legado')),
    provedor             text,
    modelo               text,
    modo                 text,
    effort               text,
    lote                 int,
    k_rag                int,
    rotulo               text,
    versao_prompt        text,
    chamadas             int,
    tok_entrada          bigint,
    tok_saida            bigint,
    tok_cache_escrita    bigint,
    tok_cache_leitura    bigint,
    tok_raciocinio       bigint,
    segundos             numeric(10,3),
    usd                  numeric(12,4),
    brl                  numeric(12,3),
    usd_brl              numeric(6,3),
    -- Preço desconhecido é NULL, nunca 0 (ADR-012, saida.py:169-173).
    preco_conhecido      bool,
    status               text NOT NULL CHECK (status IN ('em_curso', 'parcial', 'ok', 'erro')),
    erro                 text,
    canonica             bool NOT NULL DEFAULT true,
    procedencia_completa bool NOT NULL DEFAULT true,
    -- Legado: custo e tokens como vieram, nunca recalculados (seção 9, passo 4).
    brl_legado           numeric(12,3),
    custo_formula        text,
    fonte_migracao       jsonb,
    reaproveitado_de     bigint REFERENCES execucoes_modelo (id),
    respostas_sha256     char(64),
    iniciado_em          timestamptz NOT NULL DEFAULT now(),
    finalizado_em        timestamptz,
    workflow_execucao_id bigint,      -- FK em 007 (execucoes_workflow nasce lá)
    -- T15 / ADR-014: provedor simulado ou replay nunca é a execução canônica
    -- de uma licitação; só existe para o fluxo rodar sem gastar.
    CONSTRAINT execucoes_modelo_simulado_nao_canonica
        CHECK (origem NOT IN ('simulado', 'gravado') OR canonica = false)
);

CREATE INDEX execucoes_modelo_controle ON execucoes_modelo (controle, id);
CREATE INDEX execucoes_modelo_status ON execucoes_modelo (status) WHERE status IN ('em_curso', 'parcial');

-- Imutável. Uma linha por ida ao modelo; `dados` é a resposta bruta (o
-- envelope da Anthropic), que o /gravado/v1/messages reproduz na demo.
CREATE TABLE chamadas_modelo (
    id                bigserial PRIMARY KEY,
    execucao_id       bigint NOT NULL REFERENCES execucoes_modelo (id),
    lote_ids          text[],
    dados             jsonb,
    stop_reason       text,
    http_status       int,
    tentativas        int,
    tok_entrada       bigint,
    tok_saida         bigint,
    tok_cache_escrita bigint,
    tok_cache_leitura bigint,
    segundos          numeric(10,3),
    request_sha256    char(64),
    usd               numeric(12,4),
    brl               numeric(12,3),
    preco_conhecido   bool,
    em                timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX chamadas_modelo_execucao ON chamadas_modelo (execucao_id);
CREATE INDEX chamadas_modelo_em ON chamadas_modelo (em);

-- Imutável. A resposta CRUA do modelo, antes do verificador. `pagina_citada`
-- é o único rastro da página que o modelo disse: a fusão do extrator não a
-- repõe, e é por ela que o reverificar mantém REVISAR como REVISAR
-- (verificador.py:150-158; seção 6, /reverificar).
CREATE TABLE respostas (
    execucao_id    bigint NOT NULL REFERENCES execucoes_modelo (id),
    pergunta_id    text NOT NULL REFERENCES perguntas (id),
    resposta       text NOT NULL,
    arquivo_citado text,
    pagina_citada  int,
    trecho_literal text,
    conflito       text,
    confianca      text CHECK (confianca IN ('alta', 'media', 'baixa')),
    completada     bool NOT NULL DEFAULT false,
    PRIMARY KEY (execucao_id, pergunta_id)
);
