-- 034 — o que a IA não reconhece como FOPA (25/09/2026): um guardrail que interrompe a extração do que a IA
-- não identifica como folha, tira a licitação do painel e a leva ao histórico; e o filtro "apenas FOPA" no
-- histórico e no analytics.
--
-- A nota da IA é a do Jev de escopo que a tela já mostra (api/consultas.py:JEV_ESCOPO): a MÉDIA do sinal mais
-- recente só com o objeto e do mais recente com o edital (73_). Dois usos, dois limiares:
--   * a TRAVA (fila do W10, W22, painel): p(folha) <= 0,25 — convicção; medido em 73_, nenhuma folha de verdade
--     teve nota assim (a trava não barra folha por dúvida);
--   * o FILTRO "apenas FOPA" (histórico e analytics): p(folha) < 0,5 — o que a IA estima que não é.
-- O rótulo humano "dentro" (db/031) prevalece sobre a IA. Nada é apagado; a regra (`escopo_dentro`) não muda.

CREATE INDEX sinais_jev_controle_tipo ON sinais_jev (controle, tipo, em DESC, id DESC);

-- p(é folha) pela IA: média do mais recente de cada tipo de contexto (só objeto × objeto + edital). NULL = sem nota.
CREATE FUNCTION fn_ia_p_folha(p_controle text) RETURNS numeric LANGUAGE sql STABLE AS $$
    SELECT avg(x.p_sim) FROM (
        SELECT DISTINCT ON (left(coalesce(s.contexto_enviado, ''), 6) = 'edital') s.p_sim
          FROM sinais_jev s
         WHERE s.controle = p_controle AND s.tipo = 'escopo' AND s.p_sim IS NOT NULL
         ORDER BY left(coalesce(s.contexto_enviado, ''), 6) = 'edital', s.em DESC, s.id DESC) x
$$;

CREATE FUNCTION fn_ia_nao_fopa(p_controle text, p_limiar numeric) RETURNS bool LANGUAGE sql STABLE AS $$
    SELECT (SELECT r.veredito FROM rotulos_escopo r WHERE r.controle = p_controle
             ORDER BY r.em DESC, r.id DESC LIMIT 1) IS DISTINCT FROM 'dentro'
       AND COALESCE(fn_ia_p_folha(p_controle) <= p_limiar, false)
$$;

-- A de db/033, com a trava: o que a IA recusa com convicção não vai à fila (a linha marcada).
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
           AND NOT fn_ia_nao_fopa(l.controle, 0.25)                                              -- 034
           AND (v_real OR l.ensaio OR fn_provedor_pedido(l.controle) IS NOT NULL
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

-- A de db/019 com duas mudanças, no ÚNICO freio de toda extração (fila do W10, "Processar" do site, botão do GPT):
--   * o escopo é o EFETIVO (db/031): o rótulo humano "dentro" libera o que a regra recusou, e "fora" barra;
--   * a TRAVA da IA: o que ela recusa com convicção (<= 0,25) não extrai: a extração é interrompida. Nenhum
--     provedor é chamado e nada é gravado; o W23 devolve "recusada" com o motivo, e a licitação aparece no
--     histórico (api/consultas.py:HISTORICO), não no painel. O rótulo humano "dentro" destrava.
CREATE OR REPLACE FUNCTION fn_tomar_vaga_extracao(p_controle text, p_max int, p_teto_brl_dia numeric)
RETURNS TABLE (ok bool, motivo text) LANGUAGE plpgsql AS $$
DECLARE
    v_estado   estado_licitacao;
    v_dentro   bool;
    v_fim      timestamptz;
    v_pub      date;
    v_em_curso int;
    v_gasto    numeric;
    c_pior_caso_brl constant numeric := 6.56;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('fopa.extracao'));

    SELECT estado, escopo_dentro, fim_prazo, publicado_em INTO v_estado, v_dentro, v_fim, v_pub
      FROM licitacoes WHERE controle = p_controle FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT false, 'licitação não existe';
        RETURN;
    END IF;
    IF NOT COALESCE(fn_escopo_efetivo(p_controle, v_dentro), false) THEN
        RETURN QUERY SELECT false, 'fora do escopo de folha (ADR-003/015): extração recusada';
        RETURN;
    END IF;
    IF fn_ia_nao_fopa(p_controle, 0.25) THEN
        RETURN QUERY SELECT false, 'a IA não reconhece como folha (nota <= 0,25; db/034): extração parada, a licitação vai para o histórico';
        RETURN;
    END IF;
    IF NOT fn_no_recorte(v_fim, v_pub) THEN
        RETURN QUERY SELECT false, format('fora do recorte de %s (ADR-015): extração recusada', fn_ano_minimo());
        RETURN;
    END IF;
    IF NOT fn_transicao_permitida(v_estado, 'extraindo') THEN
        RETURN QUERY SELECT false, format('estado %s não permite extrair', v_estado);
        RETURN;
    END IF;

    SELECT count(*) INTO v_em_curso FROM licitacoes WHERE estado = 'extraindo';
    IF v_em_curso >= COALESCE(p_max, 4) THEN
        RETURN QUERY SELECT false, 'sem_vaga';
        RETURN;
    END IF;

    IF p_teto_brl_dia IS NOT NULL THEN
        SELECT COALESCE(sum(brl), 0) INTO v_gasto
          FROM chamadas_modelo
         WHERE (em AT TIME ZONE 'America/Sao_Paulo')::date
               = (now() AT TIME ZONE 'America/Sao_Paulo')::date;
        IF v_gasto + (v_em_curso + 1) * c_pior_caso_brl > p_teto_brl_dia THEN
            RETURN QUERY SELECT false, 'sem_orcamento';
            RETURN;
        END IF;
    END IF;

    PERFORM fn_transicao(p_controle, 'extraindo', 'W23: vaga tomada',
                         jsonb_build_object('em_curso', v_em_curso, 'teto', p_teto_brl_dia));
    RETURN QUERY SELECT true, 'ok';
END $$;

GRANT EXECUTE ON FUNCTION fn_ia_p_folha(text), fn_ia_nao_fopa(text, numeric) TO n8n_rw, worker_rw, api_ro, api_rw;
