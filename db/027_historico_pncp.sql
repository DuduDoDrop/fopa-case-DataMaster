-- 027 — histórico de compra e venda da folha, direto da API do PNCP (24/09/2026).
--
-- O histórico de compra e venda (datas de publicação, itens, resultados) não depende do edital: vem da
-- API, com tudo o que ela disponibiliza. É a base do analytics: quem comprou cada folha, por quanto e quando, e o que foi
-- a deserto e voltou a ser publicado.
--
-- Guarda o PAYLOAD inteiro de cada resposta (nada do que a API dá se perde) e extrai as colunas que o
-- analytics consulta. Não referencia `licitacoes`: o histórico pode crescer além do acervo das 17
-- perguntas. Quem escreve é o coletor (api/historico_pncp.py, como worker_rw); o site só lê.

CREATE TABLE pncp_compras (
    controle          text PRIMARY KEY,
    payload           jsonb NOT NULL,        -- cabeçalho da compra, como veio (api/consulta/v1)
    orgao_cnpj        text,
    orgao             text,
    uf                text,
    municipio         text,
    modalidade        text,
    objeto            text,
    valor_estimado    numeric(18, 2),
    valor_homologado  numeric(18, 2),
    situacao          text,                  -- situacaoCompraNome: Divulgada / Revogada / Anulada / Suspensa
    publicado_em      timestamptz,
    abertura_em       timestamptz,
    encerramento_em   timestamptz,
    existe_resultado  bool,
    atualizado_pncp   timestamptz,
    buscado_em        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE pncp_itens (
    controle        text NOT NULL,
    numero_item     int NOT NULL,
    payload         jsonb NOT NULL,
    descricao       text,
    situacao        text,                    -- situacaoCompraItemNome: Em andamento / Homologado / Deserto / Fracassado...
    valor_total     numeric(18, 2),
    tem_resultado   bool,
    criterio        text,
    buscado_em      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (controle, numero_item)
);

CREATE TABLE pncp_resultados (
    controle           text NOT NULL,
    numero_item        int NOT NULL,
    sequencial         int NOT NULL,
    payload            jsonb NOT NULL,
    ni_fornecedor      text,
    fornecedor         text,
    natureza_juridica  text,
    porte              text,
    valor_homologado   numeric(18, 2),
    data_resultado     date,
    situacao           text,                 -- situacaoCompraItemResultadoNome
    cancelado_em       timestamptz,          -- homologação desfeita (Triunfo Potiguar/RN): não é vencedor
    buscado_em         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (controle, numero_item, sequencial)
);

-- A última coleta de cada controle, deu certo ou não: "parcial ≠ nada" (ADR-007) vale aqui também.
CREATE TABLE pncp_coletas (
    controle   text PRIMARY KEY,
    ok         bool NOT NULL,
    erro       text,
    chamadas   int NOT NULL DEFAULT 0,
    em         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX pncp_compras_orgao ON pncp_compras (orgao_cnpj, publicado_em);
CREATE INDEX pncp_resultados_fornecedor ON pncp_resultados (ni_fornecedor);

GRANT SELECT, INSERT, UPDATE ON pncp_compras, pncp_itens, pncp_resultados, pncp_coletas TO worker_rw;
GRANT SELECT ON pncp_compras, pncp_itens, pncp_resultados, pncp_coletas TO api_ro, api_rw, n8n_rw;
