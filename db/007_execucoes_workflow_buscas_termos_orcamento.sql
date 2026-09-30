-- 007 — o que o n8n fez: execuções de workflow, buscas no PNCP, termos e orçamento.
--
-- ADR-007: cobertura declarada. Cada página lida do PNCP é persistida ANTES
-- da próxima (`buscas_paginas`), para que um 429 no meio do termo nunca apague
-- o parcial; `buscas` agrega por termo e `execucoes_workflow.cego` diz quando
-- NADA foi visto — que é diferente de "nada a fazer".

CREATE TABLE execucoes_workflow (
    id               bigserial PRIMARY KEY,
    workflow         text NOT NULL,          -- 'W01', 'W10', ... ou o script legado
    n8n_execution_id text,
    script_legado    text,
    gatilho          text,
    iniciado_em      timestamptz NOT NULL DEFAULT now(),
    duracao_s        numeric(10,3),
    argumentos       jsonb,
    -- Mantido para o legado (_execucoes.jsonl) e para fluxos sem chamada de
    -- modelo (W01 custa 0). Para W20/W23 a verdade é a view
    -- v_execucoes_workflow_custo, somada de chamadas_modelo.
    custo_brl        numeric(12,3) NOT NULL DEFAULT 0,
    contadores       jsonb,
    cego             bool,
    status           text,
    erro             text,
    controle         text REFERENCES licitacoes (controle)
);

CREATE INDEX execucoes_workflow_recentes ON execucoes_workflow (workflow, iniciado_em DESC);

ALTER TABLE execucoes_modelo
    ADD CONSTRAINT execucoes_modelo_workflow_fk
    FOREIGN KEY (workflow_execucao_id) REFERENCES execucoes_workflow (id);

-- Uma linha por página consultada, gravada antes de pedir a próxima (W01, passo 7).
CREATE TABLE buscas_paginas (
    id                   bigserial PRIMARY KEY,
    workflow_execucao_id bigint REFERENCES execucoes_workflow (id),
    termo                text NOT NULL,
    pagina               int NOT NULL,
    itens                jsonb,
    status               int,
    falhou               bool NOT NULL DEFAULT false,
    motivo               text,
    em                   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX buscas_paginas_execucao ON buscas_paginas (workflow_execucao_id, termo, pagina);

-- Imutável: o resumo por termo de uma rodada (pncp.py:150-154).
CREATE TABLE buscas (
    id                   bigserial PRIMARY KEY,
    workflow_execucao_id bigint REFERENCES execucoes_workflow (id),
    termo                text NOT NULL,
    paginas_lidas        int,
    total_declarado      int,
    lidos                int,
    cobertura_pct        numeric(5,1),
    teto_atingido        bool,
    falhou               bool NOT NULL DEFAULT false,
    pagina_falha         int,
    em                   timestamptz NOT NULL DEFAULT now()
);

-- Os termos de busca do monitor (20_monitor.py:58-78), editáveis no admin.
-- `densidade_pct` é a medida de 56_densidade_termos.py: quantos itens
-- devolvidos são de folha de verdade.
CREATE TABLE termos (
    termo         text PRIMARY KEY,
    paginas       int NOT NULL DEFAULT 10,
    ativo         bool NOT NULL DEFAULT true,
    prioridade    int NOT NULL DEFAULT 0,
    densidade_pct numeric(5,1),
    medido_em     date
);

-- Histórico de orçamento; só uma linha vigente. NULL = sem teto (decisão de
-- produto: automático, sem teto; o admin mostra "~R$ 3-4 por edital").
CREATE TABLE orcamento (
    id               bigserial PRIMARY KEY,
    teto_brl_dia     numeric(12,2),
    max_por_execucao int,
    auto_processar   bool NOT NULL DEFAULT true,
    vigente          bool NOT NULL DEFAULT true,
    alterado_por     text,
    em               timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX orcamento_vigente ON orcamento ((true)) WHERE vigente;
