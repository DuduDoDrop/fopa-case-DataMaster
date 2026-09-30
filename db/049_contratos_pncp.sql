-- 049 — os contratos da folha, direto do PNCP (27/09/2026).
--
-- Motivação (27/09): a API do PNCP tem mais dados financeiros do que o projeto coletava, e eles são necessários
-- para o analytics. A 027 guarda a compra, os itens e os
-- resultados (quem venceu e por quanto); o PNCP publica também o CONTRATO assinado com o banco — valor inicial, global
-- e acumulado (com os aditivos), parcelas, a data da assinatura e a VIGÊNCIA, isto é, até quando aquele banco fica com
-- a folha daquele órgão — e os termos aditivos (prorrogação, acréscimo, reajuste). Nada disso vinha.
--
-- De onde vem (api/contratos_pncp.py, como worker_rw; o site só lê): a busca do PNCP (tipos_documento=contrato) com
-- os termos da descoberta acha os contratos de folha do país inteiro, inclusive os de licitação que o FOPA não tem; o
-- detalhe traz o vínculo com a compra (`numeroControlePncpCompra`) e o fornecedor; /termos, os aditivos.
--
-- ESCOPO: o contrato de uma licitação do acervo herda o escopo dela (fn_escopo_efetivo, na leitura); o que não tem
-- licitação no acervo é julgado pela mesma regra das licitações (api/escopo_ajuste.avaliar) sobre o objeto do
-- contrato — a busca por "folha de pagamento" também traz o sistema de RH e o consignado. `escopo_dentro` e
-- `escopo_motivo` guardam esse julgamento.

CREATE TABLE pncp_contratos (
    controle         text PRIMARY KEY,          -- numeroControlePNCP do contrato: CNPJ-2-SEQ/ANO
    controle_compra  text,                      -- numeroControlePncpCompra: a licitação de origem
    payload          jsonb NOT NULL,
    orgao_cnpj       text,
    orgao            text,
    uf               text,
    municipio        text,
    ni_fornecedor    text,
    fornecedor       text,
    objeto           text,
    tipo             text,
    valor_inicial    numeric,
    valor_global     numeric,
    valor_acumulado  numeric,
    valor_parcela    numeric,
    parcelas         int,
    receita          bool,
    assinado_em      date,
    vigencia_inicio  date,
    vigencia_fim     date,
    publicado_em     timestamptz,
    atualizado_pncp  timestamptz,
    escopo_dentro    bool NOT NULL,
    escopo_motivo    text,
    termo_busca      text,
    buscado_em       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX pncp_contratos_compra ON pncp_contratos (controle_compra);
CREATE INDEX pncp_contratos_vigencia ON pncp_contratos (vigencia_fim);
CREATE INDEX pncp_contratos_fornecedor ON pncp_contratos (ni_fornecedor);

CREATE TABLE pncp_contrato_termos (
    controle_contrato   text NOT NULL REFERENCES pncp_contratos (controle),
    sequencial          int NOT NULL,
    payload             jsonb NOT NULL,
    tipo                text,
    objeto              text,
    valor_acrescido     numeric,
    valor_global        numeric,
    prazo_aditado_dias  int,
    assinado_em         date,
    vigencia_fim        date,
    buscado_em          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (controle_contrato, sequencial)
);

GRANT SELECT, INSERT, UPDATE ON pncp_contratos, pncp_contrato_termos TO worker_rw;
GRANT SELECT ON pncp_contratos, pncp_contrato_termos TO api_ro, api_rw, n8n_rw;

COMMENT ON TABLE pncp_contratos IS
    'contratos de folha publicados no PNCP (busca + detalhe): valores, parcelas, assinatura e vigência — db/049';
COMMENT ON COLUMN pncp_contratos.escopo_dentro IS
    'a regra de escopo (api/escopo_ajuste.avaliar) sobre o objeto do contrato; o ligado a licitação do acervo herda o dela';
