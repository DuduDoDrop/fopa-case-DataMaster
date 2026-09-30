-- 045 — gastos com IA por provedor (26/09/2026).
--
-- Requisito (26/09): a home do painel mostra o gasto somado do Jev, do Claude e do GPT, lido nas APIs de
-- administração dos provedores. Uma linha por leitura, gravada por scripts/82_gastos_ia.py:
--   admin-api  a OpenAI e a Anthropic pela Admin API — o que foi COBRADO (organização inteira, desde `desde`);
--   painel     o Jev, lido à mão no painel da TypeSafe (ela não tem API de faturamento). A home soma a essa leitura o
--              que o sistema mediu depois dela (sinais_jev.usd: tokens de entrada × preço) — api/consultas.py:gastos_ia.
-- A home mostra a leitura mais recente de cada provedor; as antigas ficam, para ver a evolução. Nada aqui é estimado
-- pelo site: sem leitura, o provedor aparece "sem leitura", nunca US$ 0 (ADR-012).

CREATE TABLE gastos_ia (
    id        bigserial PRIMARY KEY,
    provedor  text NOT NULL CHECK (provedor IN ('openai', 'anthropic', 'jev')),
    usd       numeric(12, 4) NOT NULL CHECK (usd >= 0),
    desde     date NOT NULL,
    fonte     text NOT NULL CHECK (fonte IN ('admin-api', 'painel')),
    detalhe   jsonb,
    lido_em   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX gastos_ia_recente ON gastos_ia (provedor, lido_em DESC);

COMMENT ON TABLE gastos_ia IS 'gastos com IA por provedor: fatura (Admin API) ou painel do Jev, lidos por scripts/82 — db/045';
COMMENT ON COLUMN gastos_ia.detalhe IS 'por dia/linha da fatura, quando a fonte dá';

GRANT SELECT ON gastos_ia TO api_ro, api_rw;
