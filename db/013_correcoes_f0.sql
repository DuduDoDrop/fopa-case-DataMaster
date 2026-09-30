-- 013 — correções da revisão da F0 (revisão do banco, 24/09/2026).
--
-- As migrações 001-012 já estavam aplicadas quando a revisão chegou, e o
-- migrar.py recusa migração aplicada que mudou. Por isso a correção vem aqui,
-- como migração nova, e não editando o 002/009/011: o histórico mostra o
-- defeito e a correção, como manda a regra 5 do vault ("registre o erro junto
-- da correção"). Cada item tem um teste em db/tests/test_migracoes.py.

-- ------------------------------------------------------------------ 1. retificação
-- Quem não chegou a ler também pode ser retificado: uma `sem_pdf_legivel` que
-- ganhou documento novo é justamente o caso que importa. Em curso (baixando,
-- lendo, extraindo, respondida) continua fora: o carimbo não é gravado e a
-- retificação é pega na rodada seguinte. Fora de escopo, fora da janela e
-- legado suspeito também ficam de fora.
INSERT INTO transicoes (de, para, nota) VALUES
    ('sem_pdf_legivel',       'retificada', 'W01 / W70: documento novo pode ser legível'),
    ('formato_nao_suportado', 'retificada', 'W01 / W70: documento novo pode vir em PDF'),
    ('falha_rede',            'retificada', 'W01 / W70'),
    ('erro_leitura',          'retificada', 'W01 / W70: relê a partir do download novo'),
    ('erro_extracao',         'retificada', 'W01 / W70: relê a partir do download novo'),
    ('aguardando_orcamento',  'retificada', 'W01 / W70: a leitura em espera ficou velha'),
    ('erro_definitivo',       'retificada', 'W01 / W70: retificação é motivo novo para tentar')
ON CONFLICT (de, para) DO NOTHING;

-- ------------------------------------------------------------------ 2. fn_transicao
-- (a) Mesmo estado é no-op para TODO estado, não só publicada: o W23 sem vaga
--     deixa `preparada` em `preparada`, e o W24 republica a partir de
--     `verificada`. Antes o caminho normal do W23 estourava a tabela.
-- (b) `publicada` exige verificação vigente (ADR-004, seção 3 do plano). Antes
--     só o invariantes.sql pegava, e depois do fato.
CREATE OR REPLACE FUNCTION fn_transicao(p_controle text, p_para estado_licitacao,
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

    IF v_de = p_para THEN
        RETURN NULL;
    END IF;

    IF NOT fn_transicao_permitida(v_de, p_para) THEN
        RAISE EXCEPTION 'transição inválida: % -> % (controle %)', v_de, p_para, p_controle
            USING ERRCODE = 'P0001';
    END IF;

    IF p_para = 'publicada'
       AND NOT EXISTS (SELECT 1 FROM verificacoes WHERE controle = p_controle AND vigente) THEN
        RAISE EXCEPTION 'licitação % não pode ser publicada sem verificação vigente (ADR-004)',
            p_controle USING ERRCODE = 'P0001';
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

-- ------------------------------------------------------------ 3. fn_classificar_vista
-- A ordem do 20_monitor.py:454-475: a CONHECIDA é olhada primeiro (retificada
-- ou conhecida) e só a DESCONHECIDA com prazo vencido é "encerrada". Antes, uma
-- publicada com sessão passada voltava "encerrada" — e a busca usa
-- status=todos, então isso era quase toda licitação publicada.
-- Quais estados admitem retificação sai da tabela `transicoes`: uma regra, um lugar.
CREATE OR REPLACE FUNCTION fn_classificar_vista(p_controle text, p_payload jsonb, p_hoje date)
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

    SELECT estado, atualizado_pncp INTO v_estado, v_gravado
      FROM licitacoes WHERE controle = p_controle FOR UPDATE;

    IF NOT FOUND THEN
        IF v_fim_prazo IS NOT NULL AND v_fim_prazo < p_hoje THEN
            RETURN 'encerrada';          -- esta_aberto(), :108-117: histórico, não oportunidade
        END IF;
        RETURN CASE WHEN v_dentro THEN 'nova' ELSE 'conhecida' END;
    END IF;

    IF v_atualizado IS NULL THEN
        RETURN 'conhecida';
    END IF;

    IF v_gravado IS NULL THEN
        -- :148-153 — registro de antes do carimbo: guarda agora, compara da próxima vez.
        UPDATE licitacoes SET atualizado_pncp = v_atualizado, visto_em = p_hoje
         WHERE controle = p_controle;
        RETURN 'conhecida';
    END IF;

    IF v_atualizado > v_gravado AND fn_transicao_permitida(v_estado, 'retificada') THEN
        UPDATE licitacoes SET atualizado_pncp = v_atualizado, visto_em = p_hoje
         WHERE controle = p_controle;
        RETURN 'retificada';
    END IF;

    RETURN 'conhecida';
END $$;

-- ------------------------------------------------------ 4. fn_tomar_vaga_extracao
-- Reservar orçamento é contar TAMBÉM a extração que pede a vaga: com teto 5 e
-- nada em curso, ela sozinha pode gastar até R$ 6,56. É o que o teste 7 da
-- seção 11 espera ("teto 1 -> a próxima vai para aguardando_orcamento"); a
-- fórmula da seção 5 contava só as já em curso.
CREATE OR REPLACE FUNCTION fn_tomar_vaga_extracao(p_controle text, p_max int, p_teto_brl_dia numeric)
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
        IF v_gasto + (v_em_curso + 1) * c_pior_caso_brl > p_teto_brl_dia THEN
            RETURN QUERY SELECT false, 'sem_orcamento';
            RETURN;
        END IF;
    END IF;

    PERFORM fn_transicao(p_controle, 'extraindo', 'W23: vaga tomada',
                         jsonb_build_object('em_curso', v_em_curso, 'teto', p_teto_brl_dia));
    RETURN QUERY SELECT true, 'ok';
END $$;

-- ------------------------------------------------------------------ 5. grants
-- DELETE em leituras/verificacoes deixava o worker apagar `paginas` e
-- `verificacao_respostas` pelo CASCADE — contornando a imutabilidade do texto
-- congelado (ADR-011). A leitura nasce numa transação só: se aborta, nem chega
-- a existir, e o worker não precisa apagar nada.
REVOKE DELETE ON leituras, verificacoes FROM worker_rw;
