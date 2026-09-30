-- 047 — data de sessão absurda no PNCP vira "sem data" no card (27/09/2026).
--
-- Problema (27/09): licitações no histórico exibiam "X dias até a sessão" (Brasília/DF: 3.522 dias), e o
-- histórico deve conter apenas o passado. Medido no acervo: Brasília
-- foi publicada em 18/05/2026 com sessão em 19/05/2036 (2026 digitado 2036) e JÁ tem vencedor homologado; as 10 com
-- "sessão futura" no histórico eram todas assim (datas de 2035 a 2202; 9 homologadas, 1 revogada). Levar ao painel
-- como "3.522 dias" mostraria como aberta o que já aconteceu — a decisão foi tratar a data absurda.
--
-- A régua (distribuição de sessão − publicação no acervo de 27/09): até 6 meses, 3.923; 6-12 meses, 81; 12-13 meses,
-- 54 (credenciamento aberto por 12 meses: 366 dias exatos); 13-24 meses, 11; depois, um vão até 2 anos ou mais (50) e
-- mais de 8 anos (20). Absurda = MAIS DE 730 DIAS depois da publicação. A de 1 ano pegaria 65 credenciamentos legítimos.
--
-- Só o card muda: `licitacoes.fim_prazo` guarda o que o PNCP mandou, e a fila (fn_reivindicar etc.) não é tocada. Com
-- a data absurda fora, a licitação segue a regra das sem data (api/consultas.py): com vencedor ou revogada, histórico;
-- sem resultado, painel se publicada há até 60 dias, histórico depois.

CREATE OR REPLACE FUNCTION fn_prazo_plausivel(p_fim timestamptz, p_publicado date) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT p_fim IS NULL OR p_publicado IS NULL
        OR (p_fim AT TIME ZONE 'America/Sao_Paulo')::date - p_publicado <= 730
$$;

GRANT EXECUTE ON FUNCTION fn_prazo_plausivel(timestamptz, date) TO api_ro, api_rw, worker_rw, n8n_rw;

CREATE OR REPLACE VIEW v_card AS
SELECT l.controle,
       l.slug,
       l.orgao,
       l.uf,
       l.municipio,
       -- "Município/UF", ou o que houver (painel.py:385-386).
       CASE WHEN l.municipio IS NOT NULL AND l.municipio <> '' AND l.uf IS NOT NULL
            THEN l.municipio || '/' || l.uf
            ELSE COALESCE(NULLIF(l.municipio, ''), l.orgao, l.controle) END AS local,
       l.modalidade,
       l.objeto,
       l.situacao,
       -- data de sessão absurda (mais de 2 anos depois da publicação) vira sem data no card
       CASE WHEN fn_prazo_plausivel(l.fim_prazo, l.publicado_em) THEN l.fim_prazo END AS fim_prazo,
       l.fim_prazo_tem_hora,
       l.publicado_em,
       l.link,
       l.estado,
       l.estado_motivo,
       l.estado_desde,
       l.escopo_dentro,
       l.escopo_motivo,
       l.ensaio,
       l.reserva_demo,
       l.procedencia_incerta,
       l.gemea_de,
       l.prioridade,
       l.tentativas,
       l.proxima_tentativa_em,
       l.atualizado_pncp,
       l.visto_em,
       l.criado_em,
       l.atualizado_em,
       (v.id IS NOT NULL)                                AS extraida,
       v.id                                              AS verificacao_id,
       v.verificado_em,
       v.versao_regras,
       COALESCE(v.respondidas, 0)                        AS respondidas,
       COALESCE(v.ancoradas, 0)                          AS ancoradas,
       COALESCE(v.aprovadas, 0)                          AS aprovadas,
       COALESCE(v.revisar, 0)                            AS revisar,
       COALESCE(v.reprovadas, 0)                         AS reprovadas,
       COALESCE(v.nao_localizado, 0)                     AS nao_localizado,
       v.taxa_ancorada,
       -- conflitos = respostas cruas com `conflito` preenchido (painel.py:351)
       (SELECT count(*) FROM respostas r
          WHERE r.execucao_id = v.execucao_id AND r.conflito IS NOT NULL AND r.conflito <> '')
                                                         AS conflitos,
       COALESCE(v.alertas_globais, '{}'::text[])         AS alertas_globais,
       COALESCE(v.tags, '{}'::text[])                    AS tags,
       COALESCE(v.degradada, false)                      AS degradada,
       'Prompt Injection - Conteúdo Suspeito' = ANY (COALESCE(v.tags, '{}'::text[]))
                                                         AS injecao_suspeita,
       e.id                                              AS execucao_id,
       e.origem                                          AS procedencia,
       e.provedor,
       e.modelo,
       -- Custo NULL vira "preço não configurado" no site, nunca R$ 0,00.
       e.brl,
       e.brl_legado,
       e.preco_conhecido,
       e.procedencia_completa,
       (SELECT count(*) FROM arquivos a WHERE a.controle = l.controle)             AS n_arquivos,
       (SELECT count(*) FROM arquivos a WHERE a.controle = l.controle AND a.status = 'ok') AS n_arquivos_ok,
       EXISTS (SELECT 1 FROM publicacoes p WHERE p.verificacao_id = v.id)          AS tem_relatorio,
       EXISTS (SELECT 1 FROM revisoes_humanas h
                WHERE h.controle = l.controle AND h.status = 'aberta'
                  AND (h.verificacao_id IS NULL OR h.verificacao_id = v.id))        AS revisao_pendente,
       -- Texto de busca do painel (painel.py:442-444), minúsculo.
       lower(concat_ws(' ', l.municipio, l.uf, l.modalidade, l.controle, l.orgao,
                       l.objeto, l.rotulo))                                          AS busca,
       -- a data que o PNCP mandou, só quando ela é absurda: o card diz "data inválida no PNCP" (coluna nova, no fim —
       -- exigência do CREATE OR REPLACE VIEW)
       CASE WHEN NOT fn_prazo_plausivel(l.fim_prazo, l.publicado_em) THEN l.fim_prazo END AS fim_prazo_pncp_invalido
  FROM licitacoes l
  LEFT JOIN verificacoes v ON v.controle = l.controle AND v.vigente
  LEFT JOIN execucoes_modelo e ON e.id = v.execucao_id;
