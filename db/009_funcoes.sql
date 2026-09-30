-- 009 — as três funções que o n8n chama em vez de carregar regra no canvas.
--
-- fn_transicao          : muda o estado validando a tabela `transicoes` e grava o evento.
-- fn_classificar_vista  : a regra do monitor (20_monitor.py:97-154) para uma licitação vista na busca.
-- fn_tomar_vaga_extracao: o ÚNICO freio de extrações simultâneas e de orçamento (W23, passo 2).

-- ---------------------------------------------------------------- fn_transicao
-- Devolve o id do evento gravado; NULL quando a transição é o no-op
-- publicada->publicada (permitido para o ramo de erro pós-publicação não
-- estourar a tabela). `dados.n8n_execution_id`, se vier, vai para a coluna
-- própria do evento para o site linkar a execução do n8n.
CREATE FUNCTION fn_transicao(p_controle text, p_para estado_licitacao,
                             p_motivo text DEFAULT NULL, p_dados jsonb DEFAULT NULL)
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE
    v_de estado_licitacao;
    v_id bigint;
BEGIN
    SELECT estado INTO v_de FROM licitacoes WHERE controle = p_controle FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'licitação % não existe', p_controle USING ERRCODE = 'P0002';
    END IF;

    IF v_de = 'publicada' AND p_para = 'publicada' THEN
        RETURN NULL;
    END IF;

    IF NOT fn_transicao_permitida(v_de, p_para) THEN
        RAISE EXCEPTION 'transição inválida: % -> % (controle %)', v_de, p_para, p_controle
            USING ERRCODE = 'P0001';
    END IF;

    UPDATE licitacoes
       SET estado = p_para,
           estado_motivo = p_motivo,
           estado_desde = now(),
           estado_anterior_lease = v_de
     WHERE controle = p_controle;

    INSERT INTO licitacao_eventos (controle, de, para, motivo, dados, n8n_execution_id)
    VALUES (p_controle, v_de, p_para, p_motivo, p_dados, p_dados ->> 'n8n_execution_id')
    RETURNING id INTO v_id;

    RETURN v_id;
END $$;

-- -------------------------------------------------------- fn_classificar_vista
-- Devolve nova | conhecida | retificada | encerrada para um item da busca.
--
-- O payload é o item já normalizado pelo W01 (passo 10): `fim_prazo`,
-- `atualizado_pncp` ([:19]) e `escopo_dentro` (do /escopo). Aceita também os
-- nomes crus do PNCP (`data_fim_vigencia`, `data_atualizacao_pncp`) porque é
-- assim que o 20_monitor.py os lê, e ninguém deveria ter de traduzir duas vezes.
--
-- Regras, na ordem do monitor:
--   1. sessão encerrada (fim_prazo < hoje) é histórico, não oportunidade
--      (esta_aberto, :108-117) -> encerrada. Sem prazo = aberta.
--   2. desconhecida + dentro do escopo -> nova.
--   3. conhecida sem carimbo gravado: registro de antes do campo existir;
--      não dá para saber se mudou e marcar retificada reprocessaria as 90 de
--      uma vez. Guarda o carimbo agora e compara a partir da próxima
--      execução (:148-153) -> conhecida.
--   4. conhecida com carimbo do PNCP maior que o gravado -> retificada, mas
--      só se o estado admite retificação (publicada, verificada, preparada,
--      baixada_ok). Em curso (baixando/lendo/extraindo/...) o carimbo NÃO é
--      atualizado, para a retificação ser detectada na próxima rodada.
--   5. senão -> conhecida.
CREATE FUNCTION fn_classificar_vista(p_controle text, p_payload jsonb, p_hoje date)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE
    v_fim_prazo   date;
    v_atualizado  timestamp;
    v_dentro      bool;
    v_estado      estado_licitacao;
    v_gravado     timestamp;
    v_bruto       text;
BEGIN
    v_bruto := COALESCE(p_payload ->> 'fim_prazo', p_payload ->> 'data_fim_vigencia',
                        p_payload ->> 'dataEncerramentoProposta');
    BEGIN
        v_fim_prazo := left(v_bruto, 10)::date;
    EXCEPTION WHEN OTHERS THEN
        v_fim_prazo := NULL;    -- prazo ilegível conta como "sem prazo" (prazo_de, :97-105)
    END;

    v_bruto := COALESCE(p_payload ->> 'atualizado_pncp', p_payload ->> 'data_atualizacao_pncp');
    BEGIN
        v_atualizado := left(v_bruto, 19)::timestamp;
    EXCEPTION WHEN OTHERS THEN
        v_atualizado := NULL;
    END;

    v_dentro := COALESCE((p_payload ->> 'escopo_dentro')::bool, (p_payload ->> 'dentro')::bool, true);

    IF v_fim_prazo IS NOT NULL AND v_fim_prazo < p_hoje THEN
        RETURN 'encerrada';
    END IF;

    SELECT estado, atualizado_pncp INTO v_estado, v_gravado
      FROM licitacoes WHERE controle = p_controle FOR UPDATE;

    IF NOT FOUND THEN
        RETURN CASE WHEN v_dentro THEN 'nova' ELSE 'conhecida' END;
    END IF;

    IF v_atualizado IS NULL THEN
        RETURN 'conhecida';
    END IF;

    IF v_gravado IS NULL THEN
        UPDATE licitacoes SET atualizado_pncp = v_atualizado, visto_em = p_hoje
         WHERE controle = p_controle;
        RETURN 'conhecida';
    END IF;

    IF v_atualizado > v_gravado
       AND v_estado IN ('publicada', 'verificada', 'preparada', 'baixada_ok') THEN
        UPDATE licitacoes SET atualizado_pncp = v_atualizado, visto_em = p_hoje
         WHERE controle = p_controle;
        RETURN 'retificada';
    END IF;

    RETURN 'conhecida';
END $$;

-- ------------------------------------------------------ fn_tomar_vaga_extracao
-- Conta quantas estão em `extraindo` (<= p_max) E reserva orçamento na MESMA
-- transação, sob um advisory lock: sem isso até 4 extrações leem o mesmo
-- gasto antes de qualquer uma fechar (W23, passo 2).
--
-- Orçamento: gasto do dia (chamadas_modelo, que já contabiliza lotes de
-- execuções parciais) + em_curso x R$ 6,56 (pior caso medido por edital)
-- > teto -> recusa. `>` e não `>=`, como no 20_monitor.py:546. Teto NULL =
-- sem teto (decisão de produto). Se aceita, muda o estado para `extraindo` aqui
-- mesmo, para que a próxima chamada já enxergue a vaga tomada.
CREATE FUNCTION fn_tomar_vaga_extracao(p_controle text, p_max int, p_teto_brl_dia numeric)
RETURNS TABLE (ok bool, motivo text) LANGUAGE plpgsql AS $$
DECLARE
    v_estado   estado_licitacao;
    v_em_curso int;
    v_gasto    numeric;
    c_pior_caso_brl constant numeric := 6.56;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('fopa.extracao'));

    SELECT estado INTO v_estado FROM licitacoes WHERE controle = p_controle FOR UPDATE;
    IF NOT FOUND THEN
        RETURN QUERY SELECT false, 'licitação não existe';
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
        IF v_gasto + v_em_curso * c_pior_caso_brl > p_teto_brl_dia THEN
            RETURN QUERY SELECT false, 'sem_orcamento';
            RETURN;
        END IF;
    END IF;

    PERFORM fn_transicao(p_controle, 'extraindo', 'W23: vaga tomada',
                         jsonb_build_object('em_curso', v_em_curso, 'teto', p_teto_brl_dia));
    RETURN QUERY SELECT true, 'ok';
END $$;
