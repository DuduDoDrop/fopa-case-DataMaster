-- 005 — o veredito do verificador (ADR-004): verificacoes + verificacao_respostas.
--
-- Uma execução pode ter várias verificações (uma por `versao_regras`: ADR-014
-- manda reverificar em vez de consertar em silêncio). Só UMA por controle é
-- `vigente`, e é ela a pré-condição de `publicada`.

CREATE TABLE verificacoes (
    id                bigserial PRIMARY KEY,
    execucao_id       bigint NOT NULL REFERENCES execucoes_modelo (id),
    controle          text NOT NULL REFERENCES licitacoes (controle),
    leitura_id        bigint REFERENCES leituras (id),
    versao_regras     text NOT NULL,
    verificado_em     timestamptz NOT NULL DEFAULT now(),
    aprovadas         int,
    revisar           int,
    reprovadas        int,
    nao_localizado    int,
    ancoradas         int,
    respondidas       int,
    taxa_ancorada     numeric(5,4),
    alertas_globais   text[],
    tags              text[],
    degradada         bool,
    condicoes         jsonb,
    q13_estruturada   jsonb,
    itens_api_usados  bool,
    auditoria_json    jsonb,
    vigente           bool NOT NULL DEFAULT false,
    UNIQUE (execucao_id, versao_regras)
);

CREATE UNIQUE INDEX verif_vigente ON verificacoes (controle) WHERE vigente;
CREATE INDEX verificacoes_controle ON verificacoes (controle, id);

-- T15: uma execução `simulado`/`gravado` só pode virar verificação vigente
-- quando a licitação está marcada como ensaio. Sem isto, um "provedor
-- simulado" esquecido na fopa_config publicaria respostas de regex como se
-- fossem do modelo — e o site não teria como saber.
CREATE FUNCTION fn_vigente_exige_ensaio() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_origem text;
    v_ensaio bool;
BEGIN
    IF NOT NEW.vigente THEN
        RETURN NEW;
    END IF;
    SELECT origem INTO v_origem FROM execucoes_modelo WHERE id = NEW.execucao_id;
    IF v_origem IN ('simulado', 'gravado') THEN
        SELECT ensaio INTO v_ensaio FROM licitacoes WHERE controle = NEW.controle;
        IF NOT COALESCE(v_ensaio, false) THEN
            RAISE EXCEPTION 'verificação de execução % não pode ser vigente: licitação % não é ensaio (T15)',
                v_origem, NEW.controle USING ERRCODE = 'P0001';
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER vigente_exige_ensaio
    BEFORE INSERT OR UPDATE OF vigente ON verificacoes
    FOR EACH ROW EXECUTE FUNCTION fn_vigente_exige_ensaio();

-- Imutável. Um veredito por pergunta. `arquivo_canonico`/`arquivo_id` são o
-- nome resolvido pela mesma função que localiza a página (ajuste 2 da seção
-- 6), para o link `/api/pdf/{slug}/{arquivo_id}#page=N` nunca depender do
-- nome cru com `%`.
CREATE TABLE verificacao_respostas (
    verificacao_id   bigint NOT NULL REFERENCES verificacoes (id) ON DELETE CASCADE,
    pergunta_id      text NOT NULL REFERENCES perguntas (id),
    veredito         text NOT NULL CHECK (veredito IN ('APROVADO', 'REVISAR', 'REPROVADO')),
    arquivo_canonico text,
    arquivo_id       bigint REFERENCES arquivos (id),
    pagina_final     int,
    pagina_citada    int,
    alertas          text[],
    ausencia         text,
    PRIMARY KEY (verificacao_id, pergunta_id)
);
