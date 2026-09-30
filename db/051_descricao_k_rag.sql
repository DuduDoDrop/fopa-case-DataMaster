-- 051 — descrição da configuração k_rag sem citação pessoal (29/09/2026).
--
-- A 026 gravou na descrição e em alterado_por da chave k_rag um texto com o nome de quem pediu a mudança, e a página
-- Admin mostra essa descrição. Troca só o texto; o valor (12) não muda. Cada coluna só é trocada se ainda tem o texto
-- da 026: uma descrição ou um valor editados depois pelo site ficam como estão.
UPDATE configuracao
   SET descricao = 'ADR-010: páginas por pergunta no modo RAG (12 desde 24/09/2026)'
 WHERE chave = 'k_rag'
   AND descricao LIKE 'ADR-010: páginas por pergunta no modo RAG (12 desde 24/09/2026, %';

UPDATE configuracao
   SET alterado_por = 'db/026'
 WHERE chave = 'k_rag'
   AND alterado_por LIKE 'db/026 (%';
