-- 044 — sem documento na fonte (Pacote C, 26/09/2026).
--
-- Requisito (26/09): o número de licitações tem de bater com o número de editais extraídos. Há licitação de folha que
-- nunca vai ser extraída porque o PNCP não entrega documento que se leia: nenhum arquivo, o JSON da própria publicação
-- no lugar do PDF, o edital de outra compra (Gurinhatã/MG: combustível). Conferidas uma a uma em
-- `saidas/_agente/_v3_TRABALHO_C_RESULTADO.md`. A marcação tira a licitação da lista e dos contadores do site
-- (api/consultas.py:SEM_DOCUMENTO) e ela aparece à parte, "sem documento na fonte (N)". `duplicata_de` é a outra
-- compra que já tem o edital (Paulo Afonso/BA 000145 = 000104): essa nem aparece à parte, porque a outra já conta.
-- Nada é apagado; tirar a linha desfaz. Se o órgão anexar depois (scripts/81), a licitação volta a ser extraída e sai
-- daqui à mão.

CREATE TABLE sem_documento_fonte (
    controle     text PRIMARY KEY REFERENCES licitacoes (controle),
    motivo       text NOT NULL,
    duplicata_de text REFERENCES licitacoes (controle),
    marcado_em   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sem_documento_fonte_nao_e_ela_mesma CHECK (duplicata_de IS DISTINCT FROM controle)
);

COMMENT ON TABLE sem_documento_fonte IS 'licitações sem documento legível no PNCP, fora da conta do site — db/044';

GRANT SELECT ON sem_documento_fonte TO api_ro, api_rw, worker_rw, n8n_rw;
