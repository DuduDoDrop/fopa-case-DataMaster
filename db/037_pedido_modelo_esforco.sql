-- 037 — o pedido do botão carrega o modelo, o esforço e o teto de saída (25/09/2026): o usuário escolhe o
-- provedor (Claude ou OpenAI), o modelo (filtrado pelo provedor) e o esforço de raciocínio (o padrão de cada
-- fornecedor), como numa interface de IDE.
--
-- Quem valida é a API (api/modelos_ia.py: só modelo com preço conferido, só o esforço que o modelo aceita, pelo que
-- as páginas oficiais dizem); aqui só se guarda a escolha. O W23 usa a do pedido e, na falta, a configuração geral.
-- `max_tokens` sobe com o esforço: o raciocínio conta no limite de saída (xhigh 32 mil, max 64 mil por chamada).

ALTER TABLE pedidos_extracao
    ADD COLUMN modelo     text,
    ADD COLUMN effort     text,
    ADD COLUMN max_tokens int CHECK (max_tokens IS NULL OR max_tokens BETWEEN 1000 AND 128000);

-- O pedido pendente mais recente da licitação, com a escolha inteira (fn_provedor_pedido, db/033, só o provedor).
CREATE FUNCTION fn_pedido_ia(p_controle text)
RETURNS TABLE (provedor text, modelo text, effort text, max_tokens int) LANGUAGE sql STABLE AS $$
    SELECT p.provedor, p.modelo, p.effort, p.max_tokens FROM pedidos_extracao p
     WHERE p.controle = p_controle AND p.usado_em IS NULL
     ORDER BY p.pedido_em DESC, p.id DESC LIMIT 1
$$;

GRANT EXECUTE ON FUNCTION fn_pedido_ia(text) TO n8n_rw, worker_rw, api_ro, api_rw;
