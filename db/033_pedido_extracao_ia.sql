-- 033 — o botão "Extrair com GPT" do site (25/09/2026): um administrador pede a extração de uma licitação
-- pela API do modelo e acompanha o resultado no site.
--
-- O pedido vale para UMA licitação e UMA execução: o provedor global (`configuracao.provedor`, hoje `simulado`)
-- não muda, e a fila das 6h (db/032) continua só baixando e lendo o resto. O W23 usa o provedor do pedido
-- pendente (fn_provedor_pedido) e o marca como usado na MESMA transação em que abre a execução — se a extração
-- falhar no meio, ninguém tenta de novo com o GPT sozinho: é outro clique.

CREATE TABLE pedidos_extracao (
    id          bigserial PRIMARY KEY,
    controle    text NOT NULL REFERENCES licitacoes (controle),
    provedor    text NOT NULL CHECK (provedor IN ('openai', 'claude')),
    pedido_por  text NOT NULL,
    pedido_em   timestamptz NOT NULL DEFAULT now(),
    usado_em    timestamptz,
    execucao_id bigint REFERENCES execucoes_modelo (id)
);
CREATE INDEX pedidos_extracao_pendentes ON pedidos_extracao (controle) WHERE usado_em IS NULL;

CREATE FUNCTION fn_provedor_pedido(p_controle text) RETURNS text LANGUAGE sql STABLE AS $$
    SELECT p.provedor FROM pedidos_extracao p
     WHERE p.controle = p_controle AND p.usado_em IS NULL
     ORDER BY p.pedido_em DESC, p.id DESC LIMIT 1
$$;

-- Esta licitação vai à extração de verdade? Provedor global real OU um pedido pendente para ela.
CREATE FUNCTION fn_extrai_com_ia(p_controle text) RETURNS bool LANGUAGE sql STABLE AS $$
    SELECT fn_provedor_real() OR fn_provedor_pedido(p_controle) IS NOT NULL
$$;

-- A de db/032, com o pedido pendente liberando a licitação para a extração (a linha marcada).
CREATE OR REPLACE FUNCTION fn_reivindicar(p_por text, p_max_por_execucao int)
RETURNS TABLE (controle text, estado text, ordem int) LANGUAGE plpgsql AS $$
DECLARE
    v_limite int;
    v_real   bool := fn_provedor_real();
BEGIN
    SELECT 4 - count(*) INTO v_limite FROM licitacoes WHERE licitacoes.estado = 'extraindo';
    v_limite := LEAST(v_limite, COALESCE(p_max_por_execucao, v_limite));
    IF v_limite <= 0 THEN
        RETURN;
    END IF;
    RETURN QUERY
    WITH candidatas AS (
        SELECT l.controle, l.prioridade, (l.estado = 'retificada') AS retificada, l.fim_prazo
          FROM licitacoes l
         WHERE l.estado IN ('nova', 'retificada', 'falha_rede', 'erro_extracao',
                            'aguardando_orcamento', 'preparada', 'verificada')
           AND (l.proxima_tentativa_em IS NULL OR l.proxima_tentativa_em <= now())
           AND l.tentativas < 4
           AND NOT l.reserva_demo
           AND (l.fim_prazo IS NULL OR l.fim_prazo >= current_date)
           AND (l.lease_por IS NULL OR l.lease_ate < now())
           AND fn_escopo_efetivo(l.controle, l.escopo_dentro)
           AND (v_real OR l.ensaio OR fn_provedor_pedido(l.controle) IS NOT NULL                 -- 033
                OR l.estado IN ('nova', 'retificada', 'falha_rede'))
           AND fn_no_recorte(l.fim_prazo, l.publicado_em)
         ORDER BY l.prioridade DESC, (l.estado = 'retificada') DESC, l.fim_prazo NULLS LAST, l.controle
         LIMIT v_limite
           FOR UPDATE OF l SKIP LOCKED
    ), ordenadas AS (
        SELECT c.controle,
               row_number() OVER (ORDER BY c.prioridade DESC, c.retificada DESC,
                                  c.fim_prazo NULLS LAST, c.controle)::int AS ordem
          FROM candidatas c
    ), marcadas AS (
        UPDATE licitacoes l
           SET lease_por = p_por, lease_ate = now() + interval '2 hours'
          FROM ordenadas c
         WHERE l.controle = c.controle
        RETURNING l.controle, l.estado::text AS estado, c.ordem
    )
    SELECT m.controle, m.estado, m.ordem FROM marcadas m ORDER BY m.ordem;
END $$;

-- A de db/022, com o escopo EFETIVO: o que a regra recusou e a revisão humana rotulou "dentro" pode ser processado.
CREATE OR REPLACE FUNCTION fn_pedir_processamento(p_controle text, p_forcar bool, p_solicitante text)
RETURNS TABLE (aceito bool, estado text, motivo text) LANGUAGE plpgsql AS $$
DECLARE
    v_estado estado_licitacao;
    v_dentro bool;
    v_fim    timestamptz;
    v_pub    date;
BEGIN
    SELECT l.estado, l.escopo_dentro, l.fim_prazo, l.publicado_em INTO v_estado, v_dentro, v_fim, v_pub
      FROM licitacoes l WHERE l.controle = p_controle FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT false, NULL::text, 'desconhecida'::text; RETURN;
    END IF;
    IF NOT fn_escopo_efetivo(p_controle, COALESCE(v_dentro, false)) THEN   -- 033: o rótulo humano manda
        RETURN QUERY SELECT false, v_estado::text,
            'fora do escopo de folha pela regra (ADR-003/015); se a regra errou, rotule em /revisao'::text;
        RETURN;
    END IF;
    IF NOT fn_no_recorte(v_fim, v_pub) THEN
        RETURN QUERY SELECT false, v_estado::text,
            format('fora do recorte de %s (ADR-015): ajuste ano_minimo no admin para processar', fn_ano_minimo());
        RETURN;
    END IF;
    IF v_estado IN ('baixando', 'lendo', 'extraindo') THEN
        UPDATE licitacoes SET prioridade = GREATEST(prioridade, 1), solicitante = p_solicitante
         WHERE controle = p_controle;
        RETURN QUERY SELECT true, v_estado::text, 'já em curso'::text; RETURN;
    END IF;
    IF v_estado IN ('fora_janela', 'erro_definitivo', 'publicada', 'sem_pdf_legivel', 'formato_nao_suportado') THEN
        IF NOT p_forcar THEN
            RETURN QUERY SELECT false, v_estado::text,
                format('estado %s: reenvie com forcar=true para reprocessar do zero', v_estado);
            RETURN;
        END IF;
        PERFORM fn_transicao(p_controle, 'nova', 'W11: ' || COALESCE(p_solicitante, '?') || ' forçou o reprocessamento',
                             jsonb_build_object('de', v_estado, 'solicitante', p_solicitante));
        UPDATE licitacoes SET tentativas = 0, proxima_tentativa_em = NULL, prioridade = GREATEST(prioridade, 1),
                              solicitante = p_solicitante, lease_por = NULL, lease_ate = NULL
         WHERE controle = p_controle;
        RETURN QUERY SELECT true, 'nova'::text, 'reprocessamento forçado: recomeça do download'::text;
        RETURN;
    END IF;
    UPDATE licitacoes
       SET prioridade = GREATEST(prioridade, 1), solicitante = p_solicitante,
           tentativas = CASE WHEN p_forcar THEN 0 ELSE tentativas END,
           proxima_tentativa_em = CASE WHEN p_forcar THEN NULL ELSE proxima_tentativa_em END
     WHERE controle = p_controle;
    RETURN QUERY SELECT true, v_estado::text, 'na fila, com prioridade'::text;
END $$;

GRANT SELECT, INSERT ON pedidos_extracao TO api_rw;
GRANT USAGE, SELECT ON SEQUENCE pedidos_extracao_id_seq TO api_rw;
GRANT SELECT ON pedidos_extracao TO api_ro;
GRANT SELECT, UPDATE ON pedidos_extracao TO n8n_rw, worker_rw;
GRANT EXECUTE ON FUNCTION fn_provedor_pedido(text), fn_extrai_com_ia(text) TO n8n_rw, worker_rw, api_ro, api_rw;
