-- 025 — dois W01 ao mesmo tempo não inserem (nem pontuam) a mesma licitação duas vezes.
--
-- Achado do W01 (24/09/2026): as duas rodadas viam a licitação como
-- desconhecida (MVCC), a segunda esperava o INSERT da primeira e, com o
-- ON CONFLICT DO NOTHING, ainda devolvia 'inserir_nova' — o W01 chamava o Jev
-- duas vezes para a mesma linha e contava duas novas. Agora, se o INSERT não
-- gravou nada, a ação vira 'visto_concorrente'. O resto da função é o da 023.

CREATE OR REPLACE FUNCTION fn_registrar_vista(p_controle text, p_payload jsonb, p_hoje date,
                                              p_seco bool, p_origem text)
RETURNS TABLE (vista text, acao text) LANGUAGE plpgsql AS $$
DECLARE
    r           record;
    v_acao      text;
    v_estado    estado_licitacao;
    v_reservada bool;
    v_fim       text := NULLIF(p_payload ->> 'fim_prazo', '');
    v_n         int;
BEGIN
    SELECT l.reserva_demo INTO v_reservada FROM licitacoes l WHERE l.controle = p_controle FOR UPDATE;
    SELECT * INTO r FROM fn_vista_pura(p_controle, p_payload, p_hoje);
    v_acao := CASE
        WHEN r.vista = 'fora_recorte' THEN 'ignorar'
        WHEN NOT r.existia AND r.vista = 'encerrada' THEN 'inserir_fora_janela'
        WHEN NOT r.existia AND r.vista = 'nova' THEN 'inserir_nova'
        WHEN NOT r.existia THEN 'inserir_fora_escopo'
        WHEN r.vista = 'retificada' AND COALESCE(v_reservada, false) THEN 'visto_reservada'
        WHEN r.vista = 'retificada' THEN 'retificar'
        ELSE 'visto' END;
    IF p_seco THEN
        RETURN QUERY SELECT r.vista, v_acao; RETURN;
    END IF;

    IF v_acao LIKE 'inserir_%' THEN
        v_estado := CASE v_acao WHEN 'inserir_nova' THEN 'nova'
                                WHEN 'inserir_fora_janela' THEN 'fora_janela'
                                ELSE 'fora_escopo' END;
        INSERT INTO licitacoes (controle, ano, seq, orgao, uf, municipio, modalidade, objeto, situacao,
                                publicado_em, fim_prazo, fim_prazo_tem_hora, link, atualizado_pncp,
                                escopo_dentro, escopo_motivo, escopo_versao, estado, visto_em, origem)
        VALUES (p_controle,
                NULLIF(p_payload ->> 'ano', '')::int, NULLIF(p_payload ->> 'seq', '')::int,
                p_payload ->> 'orgao', left(p_payload ->> 'uf', 2), p_payload ->> 'municipio',
                p_payload ->> 'modalidade', p_payload ->> 'objeto', p_payload ->> 'situacao',
                left(NULLIF(p_payload ->> 'publicado_em', ''), 10)::date,
                CASE WHEN v_fim IS NULL THEN NULL
                     WHEN length(v_fim) > 10
                         THEN left(replace(v_fim, 'T', ' '), 19)::timestamp AT TIME ZONE 'America/Sao_Paulo'
                     ELSE v_fim::date::timestamp AT TIME ZONE 'America/Sao_Paulo' END,
                CASE WHEN v_fim IS NULL THEN NULL
                     ELSE length(v_fim) > 10 AND substr(v_fim, 12, 5) <> '00:00' END,
                p_payload ->> 'link', r.atualizado,
                COALESCE((p_payload ->> 'escopo_dentro')::bool, true),
                p_payload ->> 'escopo_motivo', p_payload ->> 'escopo_versao',
                v_estado, p_hoje, 'n8n')
        ON CONFLICT (controle) DO NOTHING;
        GET DIAGNOSTICS v_n = ROW_COUNT;
        IF v_n = 0 THEN
            -- Outra rodada inseriu primeiro (o INSERT dela foi aguardado): para esta
            -- é uma vista de licitação conhecida — nada de pontuar de novo.
            v_acao := 'visto_concorrente';
            UPDATE licitacoes SET visto_em = p_hoje WHERE controle = p_controle;
        END IF;
    ELSIF v_acao = 'retificar' THEN
        UPDATE licitacoes SET atualizado_pncp = r.atualizado, visto_em = p_hoje WHERE controle = p_controle;
        PERFORM fn_transicao(p_controle, 'retificada', p_origem || ': carimbo do PNCP mudou',
                             jsonb_build_object('atualizado_pncp', r.atualizado));
    ELSIF v_acao = 'visto_reservada' THEN
        -- sem carimbo de propósito: solta a reserva, a próxima vista retifica
        UPDATE licitacoes SET visto_em = p_hoje WHERE controle = p_controle;
    ELSIF v_acao = 'visto' THEN
        UPDATE licitacoes SET visto_em = p_hoje,
               atualizado_pncp = CASE WHEN r.carimbar THEN r.atualizado ELSE atualizado_pncp END
         WHERE controle = p_controle;
    END IF;
    RETURN QUERY SELECT r.vista, v_acao;
END $$;

