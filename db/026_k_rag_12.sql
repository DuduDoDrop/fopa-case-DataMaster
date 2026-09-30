-- 026 — RAG de produção com 12 páginas por pergunta (24/09/2026).
--
-- ADR-010: k=12 teve 100% de recall em todas as medições; k=6 só chegou a 100%
-- depois dos termos novos de 23/09, numa amostra única (n>=3 ainda pendente). A
-- página que o RAG perde vira "Não localizado" — que desde a política da v3
-- (api/politica.py) vai para REVISAR. O custo extra é só de contexto, e só nas
-- extrações em modo RAG (editais grandes).
--
-- Troca apenas a SEMENTE: um valor que o admin já editou no site fica como está.
UPDATE configuracao
   SET valor = '12',
       descricao = 'ADR-010: páginas por pergunta no modo RAG (12 desde 24/09/2026)',
       alterado_por = 'db/026 (24/09/2026)'
 WHERE chave = 'k_rag' AND alterado_por = 'seed' AND valor = '6'::jsonb;
