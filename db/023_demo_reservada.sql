-- 023 — a licitação reservada para a demo fica de pé.
--
-- Achados do preparo da F7 (api/demo_reservar.py, docs/DEMO.md):
--
-- 1. REARMAR. O plano B sem rede repete (provedor `gravado`) a execução da
--    verificação vigente, e o ensaio roda 3 vezes. Depois da 1ª passada a
--    reservada está `publicada` e não voltava a `preparada`. A transição
--    publicada -> preparada passa a existir, mas um gatilho a recusa para
--    quem NÃO tem reserva_demo: fora da demo, republicar é W24/W30, não isto.
--
-- 2. SEM RETIFICAÇÃO NO DIA. O W01 das 06:00 (e o W70 de domingo) viam o
--    carimbo novo do PNCP e tiravam a reservada de `preparada` — o "sem PNCP"
--    da demo quebrava. Reservada com carimbo novo vira 'visto_reservada': não
--    muda de estado e NÃO carimba, para a retificação ser vista quando a
--    reserva for solta.

INSERT INTO transicoes (de, para, nota) VALUES
    ('publicada', 'preparada', 'demo: rearmar reservada (api/demo_reservar.py --rearmar); só com reserva_demo')
ON CONFLICT DO NOTHING;

CREATE FUNCTION fn_guarda_rearmar() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.estado = 'publicada' AND NEW.estado = 'preparada' AND NOT NEW.reserva_demo THEN
        RAISE EXCEPTION 'publicada -> preparada só para licitação reservada para a demo (%)', NEW.controle;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER licitacoes_guarda_rearmar
    BEFORE UPDATE OF estado ON licitacoes
    FOR EACH ROW EXECUTE FUNCTION fn_guarda_rearmar();

CREATE OR REPLACE FUNCTION fn_registrar_vista(p_controle text, p_payload jsonb, p_hoje date,
                                              p_seco bool, p_origem text)
RETURNS TABLE (vista text, acao text) LANGUAGE plpgsql AS $$
DECLARE
    r           record;
    v_acao      text;
    v_estado    estado_licitacao;
    v_reservada bool;
    v_fim       text := NULLIF(p_payload ->> 'fim_prazo', '');
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
