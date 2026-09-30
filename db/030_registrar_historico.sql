-- 030 — o histórico INTEIRO do PNCP para o analytics e o histórico (24/09/2026): o Analytics cobre todo o
-- histórico disponível, sempre dentro do escopo de licitação de folha.
--
-- O W01 ignora o que está fora do recorte de 2026 (ADR-015: `fn_registrar_vista` → 'ignorar'). A descoberta
-- histórica (api/descoberta_historica.py) lê a busca do PNCP ano a ano, desde 2021, e registra esse passado
-- SÓ como histórico: estado `fora_janela` (no escopo) ou `fora_escopo` (a regra recusou), origem
-- 'historico' — nunca vai para a fila paga, e o analytics/histórico passam a enxergá-lo. Dentro do recorte o
-- caminho é o do W01, sem tirar nem pôr. O que já está no banco NÃO é tocado: nem carimbo, nem visto_em, nem
-- retificação — isso é trabalho do W01, que roda com o acervo vivo.

ALTER TABLE licitacoes DROP CONSTRAINT licitacoes_origem_check;
ALTER TABLE licitacoes ADD CONSTRAINT licitacoes_origem_check
    CHECK (origem IN ('corpus', 'monitor', 'manual', 'legado', 'n8n', 'historico'));

CREATE FUNCTION fn_registrar_historico(p_controle text, p_payload jsonb, p_hoje date)
RETURNS TABLE (vista text, acao text) LANGUAGE plpgsql AS $$
DECLARE
    r        record;
    v_dentro bool;
    v_fim    text := NULLIF(p_payload ->> 'fim_prazo', '');
BEGIN
    PERFORM 1 FROM licitacoes WHERE controle = p_controle FOR UPDATE;
    IF FOUND THEN
        RETURN QUERY SELECT 'conhecida'::text, 'conhecida'::text; RETURN;
    END IF;
    SELECT * INTO r FROM fn_vista_pura(p_controle, p_payload, p_hoje);
    IF r.vista <> 'fora_recorte' THEN
        RETURN QUERY SELECT * FROM fn_registrar_vista(p_controle, p_payload, p_hoje, false, 'historico');
        RETURN;
    END IF;

    v_dentro := COALESCE((p_payload ->> 'escopo_dentro')::bool, true);
    -- As colunas e conversões de fn_registrar_vista (db/020), com o estado e a origem do histórico.
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
            v_dentro, p_payload ->> 'escopo_motivo', p_payload ->> 'escopo_versao',
            (CASE WHEN v_dentro THEN 'fora_janela' ELSE 'fora_escopo' END)::estado_licitacao, p_hoje, 'historico')
    ON CONFLICT (controle) DO NOTHING;
    RETURN QUERY SELECT r.vista, (CASE WHEN v_dentro THEN 'historico' ELSE 'historico_fora_escopo' END)::text;
END $$;

GRANT EXECUTE ON FUNCTION fn_registrar_historico(text, jsonb, date) TO worker_rw, n8n_rw;
