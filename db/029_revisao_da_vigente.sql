-- 029 — "revisão pendente" é a da verificação VIGENTE (24/09/2026, noite).
--
-- Cada W30 cria verificação nova e o W24 reabre a revisão da mesma pergunta (o "idempotente" dele é por
-- verificação). Depois da re-verificação da noite de 24/09 eram 2.936 revisões abertas para 1.542 perguntas:
-- 1.532 presas a verificação já substituída, 140 delas da tag de injeção que a regra nova (api/injecao.py) não
-- dá mais. A fila (api/consultas.py:fila_revisao) e o contador do resumo passaram a olhar só a vigente; aqui o
-- card (`revisao_pendente`, o filtro "Revisão pendente") e o detalhe (`revisoes_abertas`) fazem o mesmo.
-- Nada é apagado: as antigas continuam no banco, abertas.
--
-- As duas views são as de db/010_views.sql, idênticas, fora das duas expressões (mesmas colunas, mesma ordem —
-- exigência do CREATE OR REPLACE VIEW; as permissões ficam).

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
                WHERE h.controle = l.controle AND h.status = 'aberta'
                  AND (h.verificacao_id IS NULL OR h.verificacao_id = v.id))        AS revisao_pendente,
       -- Texto de busca do painel (painel.py:442-444), minúsculo.
       lower(concat_ws(' ', l.municipio, l.uf, l.modalidade, l.controle, l.orgao,
                       l.objeto, l.rotulo))                                          AS busca
  FROM licitacoes l
  LEFT JOIN verificacoes v ON v.controle = l.controle AND v.vigente
  LEFT JOIN execucoes_modelo e ON e.id = v.execucao_id;

CREATE OR REPLACE VIEW v_detalhe AS
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
         WHERE h.controle = l.controle AND h.status = 'aberta'
           AND (h.verificacao_id IS NULL OR h.verificacao_id = v.id))                 AS revisoes_abertas,
       EXISTS (SELECT 1 FROM itens_api i WHERE i.controle = l.controle)             AS tem_itens_api
  FROM v_card c
  JOIN licitacoes l ON l.controle = c.controle
  LEFT JOIN verificacoes v ON v.id = c.verificacao_id
  LEFT JOIN execucoes_modelo e ON e.id = v.execucao_id
  LEFT JOIN leituras le ON le.id = v.leitura_id;
