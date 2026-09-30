-- 018 — o recorte de 2026 (ADR-015) no banco, para o W01, o site e quem vier.
--
-- Requisito de negócio: só interessam as licitações de 2026, e o recorte tem de
-- estar no filtro da própria consulta à API, que devolve muito resultado fora dele.
-- A regra é a do `saidas/_agente/_proximas.py:de_2026()`, que já decidiu a
-- fila de extração: entra se a SESSÃO for em `ano_minimo` ou depois
-- (credenciamento com janela até 2027/2028 conta); sem data de sessão, entra
-- se foi PUBLICADA em `ano_minimo` ou depois; sem data nenhuma, fica fora.
--
-- O ano mora em `configuracao` (016): o admin muda sem migração. O dia é o
-- civil de São Paulo, o mesmo do painel (`painel._dias`) e do site.

INSERT INTO configuracao (chave, valor, descricao, alterado_por) VALUES
    ('ano_minimo', '2026',
     'ADR-015: só licitações com sessão neste ano ou depois; sem data de sessão, publicadas neste ano ou depois',
     'migracao-018')
ON CONFLICT (chave) DO NOTHING;

CREATE FUNCTION fn_ano_minimo() RETURNS int LANGUAGE sql STABLE AS $$
    SELECT COALESCE((SELECT (valor #>> '{}')::int FROM configuracao WHERE chave = 'ano_minimo'), 2026)
$$;

-- Por data (o W01 recebe datas locais do PNCP em texto).
CREATE FUNCTION fn_no_recorte_data(p_sessao date, p_publicado date) RETURNS bool
LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN p_sessao IS NOT NULL THEN p_sessao >= make_date(fn_ano_minimo(), 1, 1)
        WHEN p_publicado IS NOT NULL THEN p_publicado >= make_date(fn_ano_minimo(), 1, 1)
        ELSE false
    END
$$;

-- Pelas colunas de `licitacoes` (fim_prazo é timestamptz).
CREATE FUNCTION fn_no_recorte(p_fim_prazo timestamptz, p_publicado date) RETURNS bool
LANGUAGE sql STABLE AS $$
    SELECT fn_no_recorte_data((p_fim_prazo AT TIME ZONE 'America/Sao_Paulo')::date, p_publicado)
$$;

-- fn_classificar_vista (013) ganha o recorte, sem mudar mais nada:
--   * desconhecida fora do recorte -> 'fora_recorte' (o W01 não grava);
--   * conhecida fora do recorte com carimbo novo -> guarda o carimbo e fica
--     'conhecida': retificação de edital de 2025 não gasta extração.
-- As datas do payload valem mais que as gravadas (são a vista de agora).
CREATE OR REPLACE FUNCTION fn_classificar_vista(p_controle text, p_payload jsonb, p_hoje date)
RETURNS text LANGUAGE plpgsql AS $$
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
        v_fim_prazo := NULL;    -- prazo ilegível conta como "sem prazo" (prazo_de, :97-105)
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

    SELECT estado, atualizado_pncp, fim_prazo, publicado_em
      INTO v_estado, v_gravado, v_fim_gravado, v_pub_gravado
      FROM licitacoes WHERE controle = p_controle FOR UPDATE;

    IF NOT FOUND THEN
        IF NOT fn_no_recorte_data(v_fim_prazo, v_publicado) THEN
            RETURN 'fora_recorte';       -- ADR-015: nem entra no banco
        END IF;
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
        IF NOT fn_no_recorte_data(
                COALESCE(v_fim_prazo, (v_fim_gravado AT TIME ZONE 'America/Sao_Paulo')::date),
                COALESCE(v_publicado, v_pub_gravado)) THEN
            RETURN 'conhecida';          -- ADR-015: retificação de antes de 2026 não reprocessa
        END IF;
        RETURN 'retificada';
    END IF;

    RETURN 'conhecida';
END $$;

GRANT EXECUTE ON FUNCTION fn_ano_minimo(), fn_no_recorte_data(date, date),
                          fn_no_recorte(timestamptz, date) TO n8n_rw, worker_rw, api_ro, api_rw;
