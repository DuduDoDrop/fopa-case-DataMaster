-- 039 — o produto manda DOIS e-mails (25/09/2026), parte 2: só eles cabem na tabela.
--
-- Depois da 038 e dos fluxos novos no n8n, nenhum fluxo enfileira mais carregada, processada, erro,
-- alerta_diario, orcamento, cego, furtivo, republicada nem reverificacao: só o W01 (licitacao_nova) e o W24
-- (extracao). O CHECK passa a garantir isso no banco. A fila antiga foi apagada por decisão do gestor do projeto
-- (25/09: 2.698 linhas, nenhuma chegou a sair, porque o SMTP
-- nunca foi configurado); o DELETE abaixo leva o que um fluxo antigo tenha enfileirado entre a 038 e a troca.

DELETE FROM emails WHERE tipo NOT IN ('licitacao_nova', 'extracao');

ALTER TABLE emails DROP CONSTRAINT emails_tipo_check;
ALTER TABLE emails ADD CONSTRAINT emails_tipo_check CHECK (tipo IN ('licitacao_nova', 'extracao'));
