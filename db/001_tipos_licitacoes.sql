-- 001 — tipos e a tabela-mãe: licitacoes (+ pastas_legado).
--
-- PK de tudo é `controle` = numero_controle_pncp (ADR-013). O nome da pasta
-- nunca é chave: foi assim que a v2 acumulou 5 controles em 2 pastas cada e
-- 648/803 entradas do _livro.json que são nome de pasta, não controle.
-- `slug` e `cnpj` são GERADOS a partir do controle para que ninguém consiga
-- gravar um slug que não bate com a identidade.

CREATE TYPE estado_licitacao AS ENUM (
    'nova', 'fora_escopo', 'fora_janela',
    'baixando', 'baixada_ok', 'sem_pdf_legivel', 'formato_nao_suportado', 'falha_rede',
    'lendo', 'erro_leitura', 'preparada',
    'extraindo', 'respondida', 'erro_extracao', 'aguardando_orcamento',
    'verificada', 'publicada', 'retificada',
    'erro_definitivo', 'legado_suspeito'
);

CREATE TABLE licitacoes (
    controle              text PRIMARY KEY CHECK (controle ~ '^\d{14}-\d+-\d+/\d{4}$'),
    -- `/` não pode ir para URL nem para chave de storage; o slug é o controle
    -- com `/` trocado por `-`, e é único porque o controle é único.
    slug                  text GENERATED ALWAYS AS (replace(controle, '/', '-')) STORED UNIQUE,
    cnpj                  char(14) GENERATED ALWAYS AS (substr(controle, 1, 14)) STORED,
    ano                   int,
    seq                   int,
    orgao                 text,
    uf                    char(2),
    municipio             text,
    modalidade            text,
    objeto                text,
    situacao              text,
    publicado_em          date,
    fim_prazo             timestamptz,
    fim_prazo_tem_hora    bool,
    link                  text,
    -- `data_atualizacao_pncp` vem na própria busca (20_monitor.py:121-129):
    -- comparar com este carimbo custa zero chamada extra e é o que torna a
    -- detecção de retificação viável num job diário. Naive de propósito: é a
    -- string do PNCP truncada em 19 chars, sem fuso declarado.
    atualizado_pncp       timestamp,
    escopo_dentro         bool NOT NULL,
    escopo_motivo         text,
    escopo_versao         text,
    rotulo                text,
    estado                estado_licitacao NOT NULL DEFAULT 'nova',
    estado_motivo         text,
    estado_desde          timestamptz NOT NULL DEFAULT now(),
    estado_anterior_lease estado_licitacao,
    tentativas            int NOT NULL DEFAULT 0,
    proxima_tentativa_em  timestamptz,
    lease_por             text,
    lease_ate             timestamptz,
    prioridade            int NOT NULL DEFAULT 0,
    gemea_de              text REFERENCES licitacoes (controle),
    leitura_vigente_id    bigint,          -- FK adicionada em 003 (leituras nasce lá)
    reserva_demo          bool NOT NULL DEFAULT false,
    ensaio                bool NOT NULL DEFAULT false,
    procedencia_incerta   bool NOT NULL DEFAULT false,
    origem                text CHECK (origem IN ('corpus', 'monitor', 'manual', 'legado', 'n8n')),
    solicitante           text,
    visto_em              date,
    anotacoes_analista    text,
    criado_em             timestamptz NOT NULL DEFAULT now(),
    atualizado_em         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX licitacoes_estado_prazo ON licitacoes (estado, fim_prazo);
-- O W10 libera leases vencidos a cada 10 min; só interessa quem tem lease.
CREATE INDEX licitacoes_lease ON licitacoes (lease_ate) WHERE lease_por IS NOT NULL;

-- `atualizado_em` mantido pelo banco: n8n, worker e API escrevem nesta tabela
-- e nenhum deles deveria ter de lembrar de carimbar.
CREATE FUNCTION fn_carimbar_atualizado_em() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.atualizado_em := now();
    RETURN NEW;
END $$;

CREATE TRIGGER licitacoes_atualizado_em
    BEFORE UPDATE ON licitacoes
    FOR EACH ROW EXECUTE FUNCTION fn_carimbar_atualizado_em();

-- Pastas do acervo v2 (amostras/<nome>) apontando para o controle dono.
-- Todas entram, inclusive as duplicadas; `canonica` diz de qual delas veio a
-- execução escolhida (seção 9, passo 1).
CREATE TABLE pastas_legado (
    pasta            text PRIMARY KEY,
    controle         text NOT NULL REFERENCES licitacoes (controle),
    canonica         bool NOT NULL DEFAULT false,
    motivo           text,
    manifesto_sha256 char(64)
);

CREATE INDEX pastas_legado_controle ON pastas_legado (controle);
