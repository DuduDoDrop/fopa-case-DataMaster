-- 008 — fila de e-mails, usuários e sessões do site, jobs do worker, saúde.
--
-- E-mail nunca é efeito colateral de um fluxo: W21/W24/W90/W40 só INSEREM
-- aqui com status 'pendente'; o W50 é o único que fala com o Gmail/SMTP e
-- marca enviado/falhou. Assim um SMTP fora do ar não derruba o processamento,
-- e o site mostra o e-mail como foi enviado sem precisar do Gmail aberto.

CREATE TABLE emails (
    id         bigserial PRIMARY KEY,
    tipo       text NOT NULL CHECK (tipo IN (
                   'carregada', 'processada', 'erro', 'alerta_diario', 'orcamento', 'cego', 'furtivo')),
    controle   text REFERENCES licitacoes (controle),
    assunto    text NOT NULL,
    corpo_html text,
    status     text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'enviado', 'falhou')),
    canal      text CHECK (canal IN ('gmail', 'smtp')),
    tentativas int NOT NULL DEFAULT 0,
    enviado_em timestamptz,
    erro       text,
    em         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX emails_fila ON emails (em) WHERE status = 'pendente';

-- Allowlist do login Google: fora daqui, 403 "peça acesso".
CREATE TABLE usuarios (
    email text PRIMARY KEY,
    nome  text,
    papel text NOT NULL DEFAULT 'leitor' CHECK (papel IN ('leitor', 'operador', 'admin')),
    ativo bool NOT NULL DEFAULT true
);

CREATE TABLE sessoes (
    id        text PRIMARY KEY,
    email     text NOT NULL REFERENCES usuarios (email),
    criado_em timestamptz NOT NULL DEFAULT now(),
    expira_em timestamptz NOT NULL
);

CREATE INDEX sessoes_expira ON sessoes (expira_em);

-- Jobs longos do worker (baixar, paginas, importar). O reinício do worker
-- marca `running` órfão como `error` após 30 min; o n8n só faz polling.
CREATE TABLE jobs (
    id            uuid PRIMARY KEY,
    tipo          text NOT NULL,
    controle      text REFERENCES licitacoes (controle),
    status        text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'error')),
    progresso     jsonb,
    result        jsonb,
    erro          jsonb,
    criado_em     timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX jobs_ativos ON jobs (atualizado_em) WHERE status IN ('queued', 'running');

-- O que o W00 mede de hora em hora. `tesseract` tem de ser '5.4.0' (ADR-008).
CREATE TABLE saude (
    id              bigserial PRIMARY KEY,
    worker_ok       bool,
    tesseract       text,
    tessdata_sha256 char(64),
    git_sha         text,
    email_ok        bool,
    n8n_ok          bool,
    postgres_ok     bool,
    detalhes        jsonb,
    em              timestamptz NOT NULL DEFAULT now()
);
