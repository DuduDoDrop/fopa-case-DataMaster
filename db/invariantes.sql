-- Invariantes de integridade do acervo (plano, seção 3: T6/T18/T23/T24/T27 viram SQL).
--
-- UMA consulta, zero linhas = banco íntegro. Cada linha devolvida é uma
-- violação: (invariante, referência, detalhe). Serve ao CI do worker
-- (api/tests/test_invariantes_sql.py), ao passo 8 da migração e a quem
-- quiser rodar no psql.
--
-- "todo arquivos.status='ok' tem objeto no storage com o sha256 gravado": o
-- SQL só enxerga a chave; a existência do objeto e o sha são conferidos pelo
-- worker (GET /health.storage e o job de reconciliação).

SELECT 'publicada_sem_vigente' AS invariante, l.controle AS ref,
       format('estado=%s, vigentes=%s', l.estado,
              (SELECT count(*) FROM verificacoes v WHERE v.controle = l.controle AND v.vigente)) AS detalhe
  FROM licitacoes l
 WHERE l.estado = 'publicada'
   AND (SELECT count(*) FROM verificacoes v WHERE v.controle = l.controle AND v.vigente) <> 1

UNION ALL

-- Toda resposta APROVADA com evidência aponta para uma página que existe no
-- texto congelado da verificação (ADR-004 + ADR-005). A resposta CRUA do
-- modelo pode citar página inexistente — é justamente o que o verificador
-- pega e reprova —, então o invariante mora no veredito, não na resposta.
SELECT 'aprovada_sem_pagina', vr.verificacao_id::text || '/' || vr.pergunta_id,
       format('arquivo=%s pagina=%s leitura=%s', vr.arquivo_canonico, vr.pagina_final, v.leitura_id)
  FROM verificacao_respostas vr
  JOIN verificacoes v ON v.id = vr.verificacao_id
 WHERE vr.veredito = 'APROVADO'
   AND vr.ausencia IS NULL
   AND v.leitura_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM paginas p
                    WHERE p.leitura_id = v.leitura_id
                      AND p.numero = vr.pagina_final
                      AND p.arquivo_nome = vr.arquivo_canonico)

UNION ALL

-- ADR-012: preço desconhecido é NULL, nunca 0. Uma execução via API com
-- brl = 0 é um preço que alguém esqueceu de configurar.
SELECT 'api_com_brl_zero', e.id::text,
       format('provedor=%s modelo=%s brl=%s', e.provedor, e.modelo, e.brl)
  FROM execucoes_modelo e
 WHERE e.origem = 'api' AND e.brl = 0

UNION ALL

SELECT 'arquivo_ok_sem_storage', a.id::text,
       format('controle=%s nome=%s', a.controle, a.nome)
  FROM arquivos a
 WHERE a.status = 'ok' AND (a.storage_key IS NULL OR a.storage_key = '')

UNION ALL

-- Simulado/gravado vigente fora de ensaio (T15) — o trigger impede, mas a
-- importação e um UPDATE de superusuário não passam por ele.
SELECT 'simulado_vigente_sem_ensaio', v.controle,
       format('verificacao=%s origem=%s', v.id, e.origem)
  FROM verificacoes v
  JOIN execucoes_modelo e ON e.id = v.execucao_id
  JOIN licitacoes l ON l.controle = v.controle
 WHERE v.vigente AND e.origem IN ('simulado', 'gravado') AND NOT l.ensaio

ORDER BY 1, 2;
