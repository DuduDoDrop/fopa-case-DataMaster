-- 011 — papéis e grants: n8n_rw, worker_rw, api_ro.
--
-- Os papéis são criados aqui SEM senha: a senha vem de variável de ambiente
-- (N8N_RW_PASSWORD, WORKER_RW_PASSWORD, API_RO_PASSWORD) e é o migrar.py que
-- faz o ALTER ROLE, para que nenhum segredo entre no git.
--
-- Imutáveis (só INSERT): licitacao_eventos, paginas, respostas, chamadas_modelo,
-- verificacao_respostas, buscas. `emails` é fila: os fluxos inserem e o W50
-- (também n8n) marca enviado/falhou, por isso recebe UPDATE — é a única
-- exceção, registrada aqui e no ledger.
--
-- Papéis são cluster-wide: CREATE ROLE não aceita IF NOT EXISTS, daí o DO.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'n8n_rw') THEN
        CREATE ROLE n8n_rw LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'worker_rw') THEN
        CREATE ROLE worker_rw LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_ro') THEN
        CREATE ROLE api_ro LOGIN;
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO n8n_rw, worker_rw, api_ro', current_database());
END $$;

GRANT USAGE ON SCHEMA public TO n8n_rw, worker_rw, api_ro;

-- api_ro: só lê. Inclui as views.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO api_ro;

-- worker_rw: escreve arquivos, leituras, paginas, respostas, execucoes_modelo
-- (fechamento), verificacoes, verificacao_respostas, jobs. Nas imutáveis, só
-- INSERT. O worker precisa apagar leituras abortadas (CASCADE em paginas) e
-- jobs velhos, por isso DELETE nas versionadas e em jobs.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO worker_rw;
GRANT INSERT, UPDATE, DELETE ON arquivos, leituras, execucoes_modelo, verificacoes, jobs, saude
    TO worker_rw;
GRANT INSERT, UPDATE ON licitacoes TO worker_rw;
GRANT INSERT ON paginas, respostas, chamadas_modelo, verificacao_respostas, licitacao_eventos,
    publicacoes, itens_api, pastas_legado, gabaritos, execucoes_workflow, emails TO worker_rw;
GRANT UPDATE ON publicacoes, itens_api, pastas_legado, gabaritos, execucoes_workflow TO worker_rw;

-- n8n_rw: estado/lease, eventos, buscas, execuções de workflow, abertura de
-- execucoes_modelo, chamadas_modelo (INSERT), publicacoes, emails. Sem
-- UPDATE/DELETE em respostas, paginas, chamadas_modelo e nas imutáveis.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO n8n_rw;
GRANT INSERT, UPDATE ON licitacoes, execucoes_modelo, execucoes_workflow, publicacoes,
    itens_api, revisoes_humanas, emails, verificacoes, saude TO n8n_rw;
GRANT INSERT ON licitacao_eventos, chamadas_modelo, buscas, buscas_paginas TO n8n_rw;
GRANT UPDATE ON buscas_paginas TO n8n_rw;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO n8n_rw, worker_rw;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO n8n_rw, worker_rw;

-- O que for criado depois por migrações futuras já nasce legível pelo site.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO api_ro, n8n_rw, worker_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO n8n_rw, worker_rw;
