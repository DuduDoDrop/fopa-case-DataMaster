-- 032 — a fila do W10 respeita o rótulo humano e o provedor (24/09/2026): a fila de extração roda sozinha
-- todo dia às 6h, e o rótulo de escopo (db/031) vale também para ela.
--
-- 1. Rótulo "dentro" numa licitação que a regra mandou para `fora_escopo`: a rota do rótulo
--    (api/site.py:rotular_escopo) a devolve a `nova` pela transição que a reaplicação da regra já usa (019).
--    E a fila olha o escopo EFETIVO: o que a revisão humana tirou nunca é reivindicado; o que ela incluiu, é.
-- 2. Sem provedor real (`simulado`/`gravado`), a fila só leva adiante o que ainda falta BAIXAR e LER (R$ 0) —
--    e o que é de ensaio. Licitação real nunca vai à extração simulada: o banco recusaria publicá-la (T15,
--    db/005) e as tentativas terminariam em `erro_definitivo`. O W22 para em `preparada` pelo mesmo motivo
--    (n8n/workflows/W22.json, "Conferir leitura vigente"). Com o provedor real, tudo segue como antes — e o
--    teto do dia (`orcamento`) continua mandando no que se gasta.

CREATE FUNCTION fn_provedor_real() RETURNS bool LANGUAGE sql STABLE AS $$
    SELECT COALESCE((SELECT valor #>> '{}' FROM configuracao WHERE chave = 'provedor'), 'simulado')
           NOT IN ('simulado', 'gravado')
$$;

-- A de db/021, com o escopo efetivo e o provedor (as duas linhas marcadas).
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
           AND fn_escopo_efetivo(l.controle, l.escopo_dentro)                                   -- 032
           AND (v_real OR l.ensaio OR l.estado IN ('nova', 'retificada', 'falha_rede'))       -- 032
           AND fn_no_recorte(l.fim_prazo, l.publicado_em)
         ORDER BY l.prioridade DESC, (l.estado = 'retificada') DESC, l.fim_prazo NULLS LAST, l.controle
         LIMIT v_limite
           FOR UPDATE OF l SKIP LOCKED
    ), ordenadas AS (
        -- FOR UPDATE não convive com função de janela: trava primeiro, numera depois.
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

GRANT EXECUTE ON FUNCTION fn_provedor_real() TO n8n_rw, worker_rw, api_ro, api_rw;

-- O rótulo "dentro" é gravado pelo site (api_rw, que não escreve em licitacoes). Esta função, e só ela, devolve à
-- fila o que a regra mandou para fora_escopo — conferindo o próprio rótulo: estreita de propósito.
CREATE FUNCTION fn_rotulo_dentro_volta_a_fila(p_controle text) RETURNS bool
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    IF NOT fn_escopo_efetivo(p_controle, false) THEN
        RETURN false;                                  -- o rótulo mais recente não é "dentro"
    END IF;
    IF (SELECT l.estado FROM licitacoes l WHERE l.controle = p_controle) IS DISTINCT FROM 'fora_escopo' THEN
        RETURN false;
    END IF;
    PERFORM fn_transicao(p_controle, 'nova', 'rótulo humano: é folha (db/032)', '{}'::jsonb);
    RETURN true;
END $$;

GRANT EXECUTE ON FUNCTION fn_rotulo_dentro_volta_a_fila(text) TO api_rw, worker_rw;
