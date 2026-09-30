-- 017 — os sinais do Jev ficam numa tabela própria, fora do pipeline.
--
-- O Jev (System One Model da TypeSafe) entra na v3 como SEGUNDO SINAL: não é
-- motivo de decisão, e sim um adendo de assertividade (definido em 23/09/2026).
-- Ver Fopa-v2/11-Produto-v3/Jev na v3.md. Por isso nada dele toca as tabelas
-- que decidem: `licitacoes.escopo_dentro` é da regra (ADR-003),
-- `verificacao_respostas.veredito` é do verificador (ADR-004) e
-- `respostas.confianca` é do extrator. Aqui mora tudo o que o Jev disse, com o
-- custo e o contexto que ele recebeu; o que tiver convicção vira CANDIDATA para
-- olho humano, e só isso.

CREATE TABLE sinais_jev (
    id               bigserial PRIMARY KEY,
    tipo             text NOT NULL CHECK (tipo IN ('escopo', 'sustenta')),
    controle         text NOT NULL REFERENCES licitacoes (controle),
    verificacao_id   bigint REFERENCES verificacoes (id),
    pergunta_id      text REFERENCES perguntas (id),
    criterio_versao  text NOT NULL,          -- o texto do critério É a variável (16,7% com critério vago)
    regra            text,                   -- o que a regra determinística disse (dentro/fora) ou o veredito
    resposta         text,                   -- escopo: sim/nao; sustenta: sustenta/contradiz/nada_diz
    p_sim            numeric(5,4),           -- Noul: probabilidade de SIM
    confianca        numeric(5,4),
    probabilidades   jsonb,
    contexto_enviado text,                   -- 'objeto', 'pagina', 'janela Np (de M)'
    candidata        bool NOT NULL DEFAULT false,   -- discordância COM convicção: vai para a fila humana
    usd              numeric(12,8),
    tok_entrada      int,
    modelo_jev       text,
    em               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX sinais_jev_candidatas ON sinais_jev (tipo, controle) WHERE candidata;

-- Quem grava é o worker (interpretando a resposta que o n8n trouxe); o site lê
-- a fila; ninguém edita um sinal depois de gravado.
GRANT INSERT ON sinais_jev TO worker_rw;
GRANT USAGE, SELECT ON SEQUENCE sinais_jev_id_seq TO worker_rw;

-- Discordância com convicção no "sustenta?" abre revisão humana (a fila do
-- /revisao); o veredito continua o do verificador.
GRANT INSERT ON revisoes_humanas TO worker_rw;
GRANT USAGE, SELECT ON SEQUENCE revisoes_humanas_id_seq TO worker_rw;
