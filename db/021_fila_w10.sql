-- 021 — a fila do W10 no banco: claim, falha com backoff, lease vencido, disjuntor.
--
-- O W10 do plano (seção 5) é SQL do começo ao fim; aqui ele vira funções com
-- teste, e o canvas do W10 fica com quatro nós Postgres legíveis.
--
-- fn_reivindicar(por, max_por_execucao): o claim da seção 5 com três
--   correções:
--   * `lease_por IS NULL OR lease_ate < now()` — o SELECT ... FOR UPDATE SKIP
--     LOCKED só pula o que está travado AGORA; sem isto, um segundo W10 logo
--     depois do primeiro (schedule + W01 + W11 coexistem) reivindicaria de novo
--     o que já tem lease;
--   * escopo e recorte de 2026 (ADR-015): a fila nunca leva adiante o que a
--     regra recusou ou o que é de antes de 2026;
--   * a ordem da devolução é a do ORDER BY (UPDATE ... RETURNING não garante).
-- fn_registrar_falha(controle, estado_erro, motivo, cega): o ramo de erro do
--   W20 — transição para o estado de erro, tentativas+1 (não quando a coleta
--   foi cega), backoff 15 min -> 2 h -> 12 h, e `erro_definitivo` na 4ª;
--   devolve o lease.
-- fn_liberar_leases_vencidos(): worker morto no meio de um job; quem estava
--   em passo transitório (baixando/lendo/extraindo) vira a falha daquele passo
--   pelo mesmo caminho (tentativa + backoff); o resto só perde o lease.
-- fn_disjuntor_w20_aberto(): >= 3 erros do W20 em 30 min e nenhum sucesso no
--   período (20_monitor.py:600-617) -> o W10 não reivindica nada.

CREATE FUNCTION fn_backoff(p_tentativas int) RETURNS interval LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN p_tentativas <= 1 THEN interval '15 minutes'
                WHEN p_tentativas = 2 THEN interval '2 hours'
                ELSE interval '12 hours' END
$$;

CREATE FUNCTION fn_registrar_falha(p_controle text, p_estado_erro estado_licitacao,
                                   p_motivo text, p_cega bool)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE
    v_tent int;
BEGIN
    PERFORM fn_transicao(p_controle, p_estado_erro, p_motivo,
                         jsonb_build_object('cega', p_cega));
    UPDATE licitacoes
       SET tentativas = tentativas + CASE WHEN p_cega THEN 0 ELSE 1 END,
           lease_por = NULL, lease_ate = NULL
     WHERE controle = p_controle
    RETURNING tentativas INTO v_tent;
    IF v_tent >= 4 AND fn_transicao_permitida(p_estado_erro, 'erro_definitivo') THEN
        PERFORM fn_transicao(p_controle, 'erro_definitivo',
                             format('%s tentativas; última: %s', v_tent, p_motivo), NULL);
        UPDATE licitacoes SET proxima_tentativa_em = NULL WHERE controle = p_controle;
        RETURN 'erro_definitivo';
    END IF;
    UPDATE licitacoes SET proxima_tentativa_em = now() + fn_backoff(GREATEST(v_tent, 1))
     WHERE controle = p_controle;
    RETURN p_estado_erro::text;
END $$;

CREATE FUNCTION fn_liberar_leases_vencidos()
RETURNS TABLE (controle text, estado_antes text, resultado text) LANGUAGE plpgsql AS $$
DECLARE
    r record;
    v_erro estado_licitacao;
BEGIN
    FOR r IN SELECT l.controle, l.estado FROM licitacoes l
              WHERE l.lease_por IS NOT NULL AND l.lease_ate < now()
              ORDER BY l.controle FOR UPDATE SKIP LOCKED LOOP
        v_erro := CASE r.estado WHEN 'baixando' THEN 'falha_rede'::estado_licitacao
                                WHEN 'lendo' THEN 'erro_leitura'::estado_licitacao
                                WHEN 'extraindo' THEN 'erro_extracao'::estado_licitacao
                                ELSE NULL END;
        IF v_erro IS NOT NULL THEN
            RETURN QUERY SELECT r.controle, r.estado::text,
                fn_registrar_falha(r.controle, v_erro, 'W10: lease vencido no meio do passo', false);
        ELSE
            UPDATE licitacoes SET lease_por = NULL, lease_ate = NULL WHERE licitacoes.controle = r.controle;
            RETURN QUERY SELECT r.controle, r.estado::text, 'lease_devolvido'::text;
        END IF;
    END LOOP;
END $$;

CREATE FUNCTION fn_disjuntor_w20_aberto() RETURNS bool LANGUAGE sql STABLE AS $$
    SELECT count(*) FILTER (WHERE status = 'erro') >= 3
       AND count(*) FILTER (WHERE status = 'ok') = 0
      FROM execucoes_workflow
     WHERE workflow = 'W20' AND iniciado_em > now() - interval '30 minutes'
$$;

CREATE FUNCTION fn_reivindicar(p_por text, p_max_por_execucao int)
RETURNS TABLE (controle text, estado text, ordem int) LANGUAGE plpgsql AS $$
DECLARE
    v_limite int;
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
           AND l.escopo_dentro
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

GRANT EXECUTE ON FUNCTION fn_backoff(int), fn_registrar_falha(text, estado_licitacao, text, bool),
                          fn_liberar_leases_vencidos(), fn_disjuntor_w20_aberto(),
                          fn_reivindicar(text, int) TO n8n_rw, worker_rw;
