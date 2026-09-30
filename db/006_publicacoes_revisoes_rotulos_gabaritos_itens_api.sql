-- 006 — publicações, revisão humana, rótulos de escopo, gabaritos e itens da API.
--
-- `revisoes_humanas` e `rotulos_escopo` são camadas PRÓPRIAS: nunca alteram
-- `respostas` nem `verificacoes` (T25). O humano corrige por cima, com nome e
-- data, e o histórico do modelo fica intacto.

CREATE TABLE publicacoes (
    id             bigserial PRIMARY KEY,
    controle       text NOT NULL REFERENCES licitacoes (controle),
    verificacao_id bigint NOT NULL REFERENCES verificacoes (id),
    html_uri       text,
    publicado_em   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (controle, verificacao_id)
);

CREATE TABLE revisoes_humanas (
    id                 bigserial PRIMARY KEY,
    controle           text NOT NULL REFERENCES licitacoes (controle),
    verificacao_id     bigint REFERENCES verificacoes (id),
    pergunta_id        text REFERENCES perguntas (id),
    motivo             text,
    status             text NOT NULL DEFAULT 'aberta'
                       CHECK (status IN ('aberta', 'aceita', 'corrigida', 'rejeitada')),
    resposta_corrigida text,
    nota               text,
    decidido_por       text,
    decidido_em        timestamptz,
    criado_em          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX revisoes_humanas_abertas ON revisoes_humanas (controle) WHERE status = 'aberta';

CREATE TABLE rotulos_escopo (
    id       bigserial PRIMARY KEY,
    controle text NOT NULL REFERENCES licitacoes (controle),
    veredito text NOT NULL CHECK (veredito IN ('dentro', 'fora')),
    por_que  text,
    por      text,
    em       timestamptz NOT NULL DEFAULT now()
);

-- Respostas de referência escritas à mão (_gabarito.json): medem acurácia,
-- nunca alimentam o modelo.
CREATE TABLE gabaritos (
    controle            text NOT NULL REFERENCES licitacoes (controle),
    pergunta_id         text NOT NULL REFERENCES perguntas (id),
    critica             bool NOT NULL DEFAULT false,
    resposta_referencia text,
    fatos_obrigatorios  text[],
    fatos_desejaveis    text[],
    fonte               jsonb,
    PRIMARY KEY (controle, pergunta_id)
);

-- Payload de /itens do PNCP, usado pelo verificador como guarda numérica
-- (preço x fatura). Guardado inteiro porque a API já provou cair.
CREATE TABLE itens_api (
    controle  text PRIMARY KEY REFERENCES licitacoes (controle),
    payload   jsonb NOT NULL,
    obtido_em timestamptz NOT NULL DEFAULT now()
);
