-- 016 — configuração de execução no Postgres e um papel próprio para o site.
--
-- CONFIGURAÇÃO. O plano (seção 4) punha provedor/modelo/lote/k_rag numa Data
-- Table do n8n (`fopa_config`), editada pelo admin do site. Isso deixava a
-- configuração em dois donos: o site teria de escrever no n8n pela API dele e
-- o n8n de ler a própria tabela. Aqui ela mora onde todo o resto mora: o site
-- edita, o n8n lê com um nó Postgres, e o histórico de quem mudou o provedor
-- fica no banco. `provedor` nasce `simulado` — "API só em produção".
--
-- PAPEL DO SITE. A seção 7 diz que a API escreve usuarios, sessoes,
-- revisoes_humanas, rotulos_escopo, orcamento e termos, e ao mesmo tempo dá à
-- API o papel `api_ro` (só leitura). As duas coisas não cabem juntas. `api_ro`
-- continua existindo para quem só lê; o site passa a entrar como `api_rw`, que
-- escreve SÓ as tabelas dele — nunca respostas, verificações ou o estado da
-- licitação (esses são do worker e do n8n).

CREATE TABLE configuracao (
    chave        text PRIMARY KEY,
    valor        jsonb NOT NULL,
    descricao    text,
    alterado_por text,
    em           timestamptz NOT NULL DEFAULT now()
);

INSERT INTO configuracao (chave, valor, descricao, alterado_por) VALUES
    ('provedor',      '"simulado"',       'simulado | gravado | claude | openai — só claude/openai gastam', 'seed'),
    ('modelo',        '"claude-opus-5"',  'ADR-009: modelo do extrator', 'seed'),
    ('modelo_openai', '"gpt-5.6-sol"',    'ADR-012: plano B', 'seed'),
    ('effort',        '"high"',           'ADR-009', 'seed'),
    ('lote',          '6',                'perguntas por chamada (3 chamadas por edital)', 'seed'),
    ('k_rag',         '6',                'ADR-010: páginas por pergunta no modo RAG', 'seed'),
    ('max_tokens',    '16000',            'teto de saída por chamada', 'seed'),
    ('max_extracoes', '4',                'ADR-009: extrações simultâneas (fn_tomar_vaga_extracao)', 'seed');

-- Quem mudou e quando: o site grava `alterado_por`, o banco carimba `em`.
CREATE FUNCTION fn_carimbar_em() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.em := now();
    RETURN NEW;
END $$;

CREATE TRIGGER configuracao_em
    BEFORE UPDATE ON configuracao
    FOR EACH ROW EXECUTE FUNCTION fn_carimbar_em();

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_rw') THEN
        CREATE ROLE api_rw LOGIN;
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO api_rw', current_database());
END $$;

GRANT USAGE ON SCHEMA public TO api_rw;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO api_rw;
GRANT INSERT, UPDATE ON usuarios, revisoes_humanas, rotulos_escopo, orcamento, termos, configuracao
    TO api_rw;
GRANT INSERT, UPDATE, DELETE ON sessoes TO api_rw;
-- Reservar para a demo e priorizar é decisão do admin do site (seção 8); o
-- estado da licitação, não.
GRANT UPDATE (reserva_demo, fim_prazo, prioridade, solicitante) ON licitacoes TO api_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO api_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO api_rw;

-- O n8n lê a configuração (SELECT já vem do default privileges); o worker também.
