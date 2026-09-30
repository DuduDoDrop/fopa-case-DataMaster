-- 002 — máquina de estados: tabela de transições permitidas + eventos.
--
-- A tabela de transições é DADO, não código, para que o site e quem avalia possam
-- ler no banco exatamente o que o plano (seção 7) descreve. `fn_transicao`
-- (009) e o trigger de licitacao_eventos validam contra ela; um estado que
-- muda por fora fica sem evento, e é isso que o invariante do W90 caça.

CREATE TABLE transicoes (
    de   estado_licitacao NOT NULL,
    para estado_licitacao NOT NULL,
    nota text,
    PRIMARY KEY (de, para)
);

INSERT INTO transicoes (de, para, nota) VALUES
    ('nova',        'baixando',              'W21'),
    ('nova',        'fora_escopo',           'ADR-003: regex antes de qualquer IA'),
    ('nova',        'fora_janela',           'W01: sessão já encerrada, sem custo'),
    ('baixando',    'baixada_ok',            'W21'),
    ('baixando',    'sem_pdf_legivel',       'W21'),
    ('baixando',    'formato_nao_suportado', 'W21'),
    ('baixando',    'falha_rede',            'W21 / W90'),
    ('baixada_ok',  'lendo',                 'W22'),
    ('lendo',       'preparada',             'W22'),
    ('lendo',       'sem_pdf_legivel',       'W22: n_paginas = 0'),
    ('lendo',       'erro_leitura',          'W22 / W90'),
    ('preparada',   'extraindo',             'W23 via fn_tomar_vaga_extracao'),
    ('preparada',   'aguardando_orcamento',  'W23: teto do dia'),
    ('extraindo',   'respondida',            'W23'),
    ('extraindo',   'erro_extracao',         'W23 / W90'),
    ('extraindo',   'aguardando_orcamento',  'W23'),
    ('respondida',  'verificada',            'W24'),
    ('verificada',  'publicada',             'W24'),
    ('publicada',   'publicada',             'no-op permitido: ramo de erro pós-publicação'),
    ('publicada',   'verificada',            'W24 modo republicar / W30: nova verificação'),
    -- Retificação: o PNCP mexeu no documento; volta a baixar.
    ('publicada',   'retificada',            'W01 / W70'),
    ('verificada',  'retificada',            'W01 / W70'),
    ('preparada',   'retificada',            'W01 / W70'),
    ('baixada_ok',  'retificada',            'W01 / W70'),
    ('retificada',  'baixando',              'W21'),
    -- erro_* -> estado anterior (retentativa do W10 com backoff).
    ('falha_rede',           'baixando',   'retentativa'),
    ('erro_leitura',         'lendo',      'retentativa'),
    ('erro_extracao',        'extraindo',  'retentativa (ids_pendentes)'),
    ('erro_extracao',        'preparada',  'W23: sem vaga, volta para a fila'),
    ('aguardando_orcamento', 'extraindo',  'retentativa quando o teto libera'),
    ('aguardando_orcamento', 'preparada',  'W23: sem vaga'),
    -- Quatro tentativas esgotadas (W10).
    ('falha_rede',           'erro_definitivo', 'W10: tentativas >= 4'),
    ('erro_leitura',         'erro_definitivo', 'W10: tentativas >= 4'),
    ('erro_extracao',        'erro_definitivo', 'W10: tentativas >= 4'),
    ('aguardando_orcamento', 'erro_definitivo', 'W10: tentativas >= 4');

CREATE FUNCTION fn_transicao_permitida(p_de estado_licitacao, p_para estado_licitacao)
RETURNS bool LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM transicoes WHERE de = p_de AND para = p_para);
$$;

-- Imutável: só INSERT (grants em 011). É a linha do tempo que o site mostra.
CREATE TABLE licitacao_eventos (
    id               bigserial PRIMARY KEY,
    controle         text NOT NULL REFERENCES licitacoes (controle),
    de               estado_licitacao,
    para             estado_licitacao NOT NULL,
    motivo           text,
    dados            jsonb,
    n8n_execution_id text,
    em               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX licitacao_eventos_controle ON licitacao_eventos (controle, id);

-- `de` NULL é o nascimento (importação/UPSERT do W01): não há de onde vir.
CREATE FUNCTION fn_valida_transicao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.de IS NOT NULL AND NOT fn_transicao_permitida(NEW.de, NEW.para) THEN
        RAISE EXCEPTION 'transição inválida: % -> % (controle %)', NEW.de, NEW.para, NEW.controle
            USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER valida_transicao
    BEFORE INSERT ON licitacao_eventos
    FOR EACH ROW EXECUTE FUNCTION fn_valida_transicao();
