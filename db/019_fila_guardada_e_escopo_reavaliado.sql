-- 019 — a fila de extração guardada pelo escopo e pelo recorte, e o caminho
-- para reaplicar a regra de escopo quando ela muda.
--
-- POR QUÊ. A regra de escopo ficou mais estrita (ADR-015: só entra a compra
-- da folha de pagamento; qualquer outro objeto fica fora), e 13 das 14
-- licitações que ela passou a recusar estavam em `preparada` na stack — ou
-- seja, na fila da extração paga. O veredito gravado era o da regra antiga
-- (escopo_versao = 'legado'): um cache do resultado de uma regra morre quando
-- a regra muda (40_fumaca, teste 12).
--
-- 1. fn_tomar_vaga_extracao recusa o que está fora do escopo ou fora do
--    recorte de 2026, antes de qualquer outra conta. É onde o dinheiro sai.
-- 2. fn_aplicar_escopo(controle, dentro, motivo, versao, origem): o worker
--    (dono da regra, ADR-003) grava o veredito novo e, se ele mudou, move o
--    estado: o que ainda não tem evidência sai para `fora_escopo`; o que a
--    regra voltou a aceitar recomeça em `nova`; publicada/verificada e o que
--    está em curso só trocam a marca (o relatório já existe; a fila, pelo
--    item 1, não pega a marcada).
-- O Jev não chama nada daqui (T25): rótulo e sinal nunca escrevem escopo.

INSERT INTO transicoes (de, para, nota) VALUES
    ('baixada_ok',            'fora_escopo', 'W01: regra de escopo reaplicada'),
    ('sem_pdf_legivel',       'fora_escopo', 'W01: regra de escopo reaplicada'),
    ('formato_nao_suportado', 'fora_escopo', 'W01: regra de escopo reaplicada'),
    ('falha_rede',            'fora_escopo', 'W01: regra de escopo reaplicada'),
    ('erro_leitura',          'fora_escopo', 'W01: regra de escopo reaplicada'),
    ('preparada',             'fora_escopo', 'W01: regra de escopo reaplicada'),
    ('erro_extracao',         'fora_escopo', 'W01: regra de escopo reaplicada'),
    ('aguardando_orcamento',  'fora_escopo', 'W01: regra de escopo reaplicada'),
    ('erro_definitivo',       'fora_escopo', 'W01: regra de escopo reaplicada'),
    ('fora_escopo',           'nova',        'W01: a regra de escopo voltou a aceitar')
ON CONFLICT DO NOTHING;

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
    IF v_dentro IS DISTINCT FROM true THEN
        RETURN QUERY SELECT false, 'fora do escopo de folha (ADR-003/015): extração recusada';
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

CREATE FUNCTION fn_aplicar_escopo(p_controle text, p_dentro bool, p_motivo text,
                                  p_versao text, p_origem text)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE
    v_estado estado_licitacao;
    v_antes  bool;
    v_det    jsonb := jsonb_build_object('motivo', p_motivo, 'escopo_versao', p_versao);
BEGIN
    SELECT estado, escopo_dentro INTO v_estado, v_antes
      FROM licitacoes WHERE controle = p_controle FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'licitação % não existe', p_controle;
    END IF;

    UPDATE licitacoes SET escopo_dentro = p_dentro, escopo_motivo = p_motivo, escopo_versao = p_versao
     WHERE controle = p_controle;

    IF v_antes IS NOT DISTINCT FROM p_dentro THEN
        RETURN 'mesma_decisao';
    END IF;
    IF NOT p_dentro AND fn_transicao_permitida(v_estado, 'fora_escopo') THEN
        PERFORM fn_transicao(p_controle, 'fora_escopo', p_origem, v_det);
        RETURN 'fora_escopo';
    END IF;
    IF p_dentro AND v_estado = 'fora_escopo' THEN
        PERFORM fn_transicao(p_controle, 'nova', p_origem, v_det);
        RETURN 'nova';
    END IF;
    RETURN 'so_marcada';
END $$;

GRANT EXECUTE ON FUNCTION fn_aplicar_escopo(text, bool, text, text, text) TO n8n_rw, worker_rw;
