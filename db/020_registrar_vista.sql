-- 020 — o W01 grava cada resultado da busca numa chamada só.
--
-- POR QUÊ. O W01 do plano ramificava por classificação (Switch → quatro nós
-- Postgres → Merge). No n8n, ramo que não recebe item não roda, e o Merge
-- depois dele fica esperando ou roda com metade; a contagem final saía torta.
-- E havia um defeito de verdade: `fn_classificar_vista` CARIMBA o
-- `atualizado_pncp` da conhecida. Um "Verificar agora" (seco) que só queria
-- listar engoliria a retificação: a rodada real seguinte veria "conhecida".
--
-- 1. fn_vista_pura(controle, payload, hoje): a classificação SEM escrever nada
--    (mesma regra de 013 + recorte de 018), devolvendo também se é preciso
--    carimbar.
-- 2. fn_classificar_vista passa a ser a pura + o carimbo (comportamento igual,
--    os testes antigos rodam de novo).
-- 3. fn_registrar_vista(controle, payload, hoje, seco, origem) -> (vista, acao):
--      ignorar             fora do recorte de 2026 (ADR-015)
--      inserir_nova        desconhecida, no escopo, aberta
--      inserir_fora_escopo desconhecida que a regra recusou (fica para o score
--                          do Jev e para o rótulo humano, nunca para a fila)
--      inserir_fora_janela desconhecida com sessão já passada (histórico)
--      retificar           conhecida com carimbo novo, estado que admite
--      visto               conhecida
--    Com seco = true nada é escrito: nem linha, nem carimbo, nem visto_em.

CREATE FUNCTION fn_vista_pura(p_controle text, p_payload jsonb, p_hoje date)
RETURNS TABLE (vista text, existia bool, carimbar bool, atualizado timestamp)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fim_prazo   date;
    v_publicado   date;
    v_atualizado  timestamp;
    v_dentro      bool;
    v_estado      estado_licitacao;
    v_gravado     timestamp;
    v_fim_gravado timestamptz;
    v_pub_gravado date;
    v_bruto       text;
BEGIN
    v_bruto := COALESCE(p_payload ->> 'fim_prazo', p_payload ->> 'data_fim_vigencia',
                        p_payload ->> 'dataEncerramentoProposta');
    BEGIN
        v_fim_prazo := left(v_bruto, 10)::date;
    EXCEPTION WHEN OTHERS THEN
        v_fim_prazo := NULL;
    END;
    v_bruto := COALESCE(p_payload ->> 'publicado_em', p_payload ->> 'data_publicacao_pncp',
                        p_payload ->> 'dataPublicacaoPncp');
    BEGIN
        v_publicado := left(v_bruto, 10)::date;
    EXCEPTION WHEN OTHERS THEN
        v_publicado := NULL;
    END;
    v_bruto := COALESCE(p_payload ->> 'atualizado_pncp', p_payload ->> 'data_atualizacao_pncp');
    BEGIN
        v_atualizado := left(v_bruto, 19)::timestamp;
    EXCEPTION WHEN OTHERS THEN
        v_atualizado := NULL;
    END;
    v_dentro := COALESCE((p_payload ->> 'escopo_dentro')::bool, (p_payload ->> 'dentro')::bool, true);

    SELECT l.estado, l.atualizado_pncp, l.fim_prazo, l.publicado_em
      INTO v_estado, v_gravado, v_fim_gravado, v_pub_gravado
      FROM licitacoes l WHERE l.controle = p_controle;

    IF NOT FOUND THEN
        IF NOT fn_no_recorte_data(v_fim_prazo, v_publicado) THEN
            RETURN QUERY SELECT 'fora_recorte'::text, false, false, v_atualizado; RETURN;
        END IF;
        IF v_fim_prazo IS NOT NULL AND v_fim_prazo < p_hoje THEN
            RETURN QUERY SELECT 'encerrada'::text, false, false, v_atualizado; RETURN;
        END IF;
        RETURN QUERY SELECT (CASE WHEN v_dentro THEN 'nova' ELSE 'conhecida' END)::text, false, false, v_atualizado;
        RETURN;
    END IF;

    IF v_atualizado IS NULL THEN
        RETURN QUERY SELECT 'conhecida'::text, true, false, v_atualizado; RETURN;
    END IF;
    IF v_gravado IS NULL THEN
        -- 20_monitor.py:148-153: registro de antes do carimbo; guarda agora.
        RETURN QUERY SELECT 'conhecida'::text, true, true, v_atualizado; RETURN;
    END IF;
    IF v_atualizado > v_gravado AND fn_transicao_permitida(v_estado, 'retificada') THEN
        IF NOT fn_no_recorte_data(
                COALESCE(v_fim_prazo, (v_fim_gravado AT TIME ZONE 'America/Sao_Paulo')::date),
                COALESCE(v_publicado, v_pub_gravado)) THEN
            -- ADR-015: retificação de antes de 2026 não reprocessa.
            RETURN QUERY SELECT 'conhecida'::text, true, true, v_atualizado; RETURN;
        END IF;
        RETURN QUERY SELECT 'retificada'::text, true, true, v_atualizado; RETURN;
    END IF;
    RETURN QUERY SELECT 'conhecida'::text, true, false, v_atualizado;
END $$;

CREATE OR REPLACE FUNCTION fn_classificar_vista(p_controle text, p_payload jsonb, p_hoje date)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE
    r record;
BEGIN
    PERFORM 1 FROM licitacoes WHERE controle = p_controle FOR UPDATE;
    SELECT * INTO r FROM fn_vista_pura(p_controle, p_payload, p_hoje);
    IF r.carimbar THEN
        UPDATE licitacoes SET atualizado_pncp = r.atualizado, visto_em = p_hoje WHERE controle = p_controle;
    END IF;
    RETURN r.vista;
END $$;

CREATE FUNCTION fn_registrar_vista(p_controle text, p_payload jsonb, p_hoje date,
                                   p_seco bool, p_origem text)
RETURNS TABLE (vista text, acao text) LANGUAGE plpgsql AS $$
DECLARE
    r        record;
    v_acao   text;
    v_estado estado_licitacao;
    v_fim    text := NULLIF(p_payload ->> 'fim_prazo', '');
BEGIN
    PERFORM 1 FROM licitacoes WHERE controle = p_controle FOR UPDATE;
    SELECT * INTO r FROM fn_vista_pura(p_controle, p_payload, p_hoje);
    v_acao := CASE
        WHEN r.vista = 'fora_recorte' THEN 'ignorar'
        WHEN NOT r.existia AND r.vista = 'encerrada' THEN 'inserir_fora_janela'
        WHEN NOT r.existia AND r.vista = 'nova' THEN 'inserir_nova'
        WHEN NOT r.existia THEN 'inserir_fora_escopo'
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
    ELSIF v_acao = 'retificar' THEN
        UPDATE licitacoes SET atualizado_pncp = r.atualizado, visto_em = p_hoje WHERE controle = p_controle;
        PERFORM fn_transicao(p_controle, 'retificada', p_origem || ': carimbo do PNCP mudou',
                             jsonb_build_object('atualizado_pncp', r.atualizado));
    ELSIF v_acao = 'visto' THEN
        UPDATE licitacoes SET visto_em = p_hoje,
               atualizado_pncp = CASE WHEN r.carimbar THEN r.atualizado ELSE atualizado_pncp END
         WHERE controle = p_controle;
    END IF;
    RETURN QUERY SELECT r.vista, v_acao;
END $$;

GRANT EXECUTE ON FUNCTION fn_vista_pura(text, jsonb, date),
                          fn_registrar_vista(text, jsonb, date, bool, text) TO n8n_rw, worker_rw;
