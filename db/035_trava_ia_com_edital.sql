-- 035 — a trava da IA só com o EDITAL (correção da 034 na mesma madrugada, 25/09/2026).
--
-- O ERRO: a 034 travava pela nota da IA fosse ela qual fosse. Só o W01 chama o Jev, e só com o OBJETO; a nota com
-- o edital (73_) existia só onde o 74_ rodou à mão. Na fila, uma licitação nova tinha apenas a nota só-objeto — e
-- ela tem o ponto cego medido desde o início: CREDENCIAMENTO de banco para os créditos da folha (as 5 discordâncias
-- do painel eram todas credenciamento, p = 0,27-0,45; no histórico, "instituição financeira ... administração e
-- processamento" com 0,24). A trava barraria folha legítima ANTES de ler o edital, e ela nunca seria lida. Nenhuma
-- das 76 ativas foi atingida (medido ao aplicar a 034); valeria para as próximas.
--
-- A CORREÇÃO, pelo que foi medido (73_, 75_): a média só-objeto + objeto+edital não recusou nenhuma folha com
-- convicção em 124; o só-objeto recusou. Então a TRAVA exige a nota com o edital:
--   * a fila (fn_reivindicar) não barra por nota só-objeto — a leitura é de graça e vem antes;
--   * o W22 pede a nota com o edital logo depois da leitura (n8n/workflows/W22.json);
--   * a vaga (fn_tomar_vaga_extracao), que vem depois, trava com as duas notas.
-- O FILTRO "apenas FOPA" (< 0,5, histórico e analytics) segue com a nota que houver: é consulta, não decisão.

CREATE FUNCTION fn_ia_tem_edital(p_controle text) RETURNS bool LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM sinais_jev s
                    WHERE s.controle = p_controle AND s.tipo = 'escopo' AND s.p_sim IS NOT NULL
                      AND left(coalesce(s.contexto_enviado, ''), 6) = 'edital')
$$;

-- A TRAVA: a IA recusa com convicção (<= 0,25) E já viu o edital; o rótulo humano "dentro" manda (fn_ia_nao_fopa).
CREATE FUNCTION fn_ia_trava(p_controle text) RETURNS bool LANGUAGE sql STABLE AS $$
    SELECT fn_ia_tem_edital(p_controle) AND fn_ia_nao_fopa(p_controle, 0.25)
$$;

-- A de db/034, com a trava que exige o edital.
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
           AND NOT fn_ia_trava(l.controle)                                                       -- 035
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

-- A de db/034, idem.
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
    IF fn_ia_trava(p_controle) THEN
        RETURN QUERY SELECT false, 'a IA não reconhece como folha (nota com o edital <= 0,25; db/035): extração parada, a licitação vai para o histórico';
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

GRANT EXECUTE ON FUNCTION fn_ia_tem_edital(text), fn_ia_trava(text) TO n8n_rw, worker_rw, api_ro, api_rw;
