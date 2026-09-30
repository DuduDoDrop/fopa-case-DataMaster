-- 022 — o pedido "Processar" do site (W11 fopa/processar) numa função.
--
-- O plano (seção 5, W11) fazia um INSERT ... ON CONFLICT DO UPDATE SET
-- estado = CASE ... THEN 'nova' — um UPDATE de estado por fora de
-- fn_transicao, sem evento, sem conferir a tabela de transições. Aqui o mesmo
-- pedido passa pelo caminho auditado:
--
--   desconhecida                       -> (false, NULL, 'desconhecida'): o W11 busca
--                                         a compra no PNCP, registra pela
--                                         fn_registrar_vista (020) e pede de novo
--   fora do escopo pela regra          -> recusa; o rótulo humano vai para /revisao,
--                                         a regra é quem decide (T25)
--   fora do recorte de 2026            -> recusa (ADR-015)
--   em curso (baixando/lendo/extraindo)-> aceito, "já em curso"
--   terminal (fora_janela, erro_definitivo, publicada, sem_pdf_legivel,
--   formato_nao_suportado)             -> só com forcar: volta para `nova` com
--                                         evento, tentativas zeradas
--   o resto                            -> prioridade 1 e solicitante; com forcar,
--                                         tentativas e backoff zerados
-- O W10 reivindica depois (prioridade primeiro). O que custa dinheiro continua
-- guardado pela fn_tomar_vaga_extracao (019).

INSERT INTO transicoes (de, para, nota) VALUES
    ('fora_janela',           'nova', 'W11: operador forçou o reprocessamento'),
    ('erro_definitivo',       'nova', 'W11: operador forçou o reprocessamento'),
    ('publicada',             'nova', 'W11: operador forçou o reprocessamento'),
    ('sem_pdf_legivel',       'nova', 'W11: operador forçou o reprocessamento'),
    ('formato_nao_suportado', 'nova', 'W11: operador forçou o reprocessamento')
ON CONFLICT DO NOTHING;

CREATE FUNCTION fn_pedir_processamento(p_controle text, p_forcar bool, p_solicitante text)
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
    IF v_dentro IS DISTINCT FROM true THEN
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

GRANT EXECUTE ON FUNCTION fn_pedir_processamento(text, bool, text) TO n8n_rw, worker_rw;
