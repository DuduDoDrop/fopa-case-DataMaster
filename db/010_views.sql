-- 010 — views que o site (api_ro) lê.
--
-- gasto_diario                : SUM(chamadas_modelo.brl) por dia local + quantas sem preço.
-- v_execucoes_workflow_custo  : custo real de uma rodada do n8n, somado das chamadas.
-- v_card                      : os campos do card do painel (painel.py:342-467), sem `dias`.
-- v_detalhe                   : v_card + procedência, leitura e verificação vigente.
--
-- `dias` fica de fora de propósito: o painel v2 congelava o número na geração
-- (painel.py:318) e mostrava "3 dias" uma semana depois. Na v3 o navegador
-- calcula a partir de `fim_prazo` em America/Sao_Paulo.

-- Soma por dia LOCAL: o teto é "por dia" no relógio de quem opera, não em UTC.
-- Cobre execuções parcial/em_curso porque a chamada já foi paga.
CREATE VIEW gasto_diario AS
SELECT (em AT TIME ZONE 'America/Sao_Paulo')::date       AS dia,
       COALESCE(sum(brl), 0)                             AS brl,
       COALESCE(sum(usd), 0)                             AS usd,
       count(*)                                          AS chamadas,
       count(*) FILTER (WHERE NOT COALESCE(preco_conhecido, false)) AS sem_preco
  FROM chamadas_modelo
 GROUP BY 1;

CREATE VIEW v_execucoes_workflow_custo AS
SELECT w.id                                              AS workflow_execucao_id,
       COALESCE(sum(c.brl), 0)                           AS custo_brl,
       count(c.id)                                       AS chamadas,
       count(c.id) FILTER (WHERE NOT COALESCE(c.preco_conhecido, false)) AS sem_preco
  FROM execucoes_workflow w
  LEFT JOIN execucoes_modelo e ON e.workflow_execucao_id = w.id
  LEFT JOIN chamadas_modelo c ON c.execucao_id = e.id
 GROUP BY w.id;

CREATE VIEW v_card AS
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
       l.fim_prazo,
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
                WHERE h.controle = l.controle AND h.status = 'aberta')              AS revisao_pendente,
       -- Texto de busca do painel (painel.py:442-444), minúsculo.
       lower(concat_ws(' ', l.municipio, l.uf, l.modalidade, l.controle, l.orgao,
                       l.objeto, l.rotulo))                                          AS busca
  FROM licitacoes l
  LEFT JOIN verificacoes v ON v.controle = l.controle AND v.vigente
  LEFT JOIN execucoes_modelo e ON e.id = v.execucao_id;

CREATE VIEW v_detalhe AS
SELECT c.*,
       l.ano, l.seq, l.cnpj,
       l.rotulo,
       l.escopo_versao,
       l.origem,
       l.solicitante,
       l.lease_por,
       l.lease_ate,
       l.leitura_vigente_id,
       l.anotacoes_analista,
       e.modo,
       e.effort,
       e.lote,
       e.k_rag,
       e.versao_prompt,
       e.chamadas,
       e.tok_entrada,
       e.tok_saida,
       e.tok_cache_escrita,
       e.tok_cache_leitura,
       e.tok_raciocinio,
       e.segundos,
       e.usd,
       e.usd_brl,
       e.custo_formula,
       e.fonte_migracao,
       e.canonica,
       e.status                                          AS execucao_status,
       e.iniciado_em                                     AS execucao_iniciada_em,
       e.finalizado_em                                   AS execucao_finalizada_em,
       v.leitura_id,
       le.versao_ocr,
       le.tessdata_sha256,
       le.procedencia_texto,
       le.modo_sugerido,
       le.chars_total,
       le.condicoes                                      AS leitura_condicoes,
       le.assinatura_conjunto,
       (SELECT count(*) FROM paginas p WHERE p.leitura_id = le.id)                  AS n_paginas,
       (SELECT count(*) FROM paginas p WHERE p.leitura_id = le.id AND p.via_ocr)    AS n_paginas_ocr,
       v.condicoes,
       v.q13_estruturada,
       v.itens_api_usados,
       (SELECT p.html_uri FROM publicacoes p
         WHERE p.verificacao_id = v.id ORDER BY p.publicado_em DESC LIMIT 1)         AS html_uri,
       (SELECT max(p.publicado_em) FROM publicacoes p WHERE p.verificacao_id = v.id) AS publicado_em_site,
       (SELECT count(*) FROM verificacoes x WHERE x.controle = l.controle)          AS n_verificacoes,
       (SELECT count(*) FROM revisoes_humanas h
         WHERE h.controle = l.controle AND h.status = 'aberta')                       AS revisoes_abertas,
       EXISTS (SELECT 1 FROM itens_api i WHERE i.controle = l.controle)             AS tem_itens_api
  FROM v_card c
  JOIN licitacoes l ON l.controle = c.controle
  LEFT JOIN verificacoes v ON v.id = c.verificacao_id
  LEFT JOIN execucoes_modelo e ON e.id = v.execucao_id
  LEFT JOIN leituras le ON le.id = v.leitura_id;
