-- 038 — o produto manda DOIS e-mails (25/09/2026), parte 1: o destinatário e os dois tipos novos.
--
--   Um avisa da licitação nova que passou no filtro; o outro entrega o resultado da extração a quem a pediu
--   no site, depois que o site é atualizado. Só esses dois.
--
--   licitacao_nova : W01 — licitação NOVA que passou no filtro (dentro do escopo e da janela); vai para os admins.
--   extracao       : W24 — a extração pedida no botão do site (pedidos_extracao, db/033); vai para QUEM pediu.
--
-- `para` é o destinatário (um ou mais e-mails separados por vírgula); NULL = os admins ativos, resolvido pelo
-- W50 na hora do envio, como sempre foi. Os tipos antigos continuam aceitos AQUI só para a troca não quebrar os
-- fluxos ainda publicados: a 039 os tira do CHECK depois que os fluxos novos estiverem no n8n.

ALTER TABLE emails ADD COLUMN para text;

ALTER TABLE emails DROP CONSTRAINT emails_tipo_check;
ALTER TABLE emails ADD CONSTRAINT emails_tipo_check CHECK (tipo IN (
    'carregada', 'processada', 'erro', 'alerta_diario', 'orcamento', 'cego', 'furtivo',
    'republicada', 'reverificacao', 'licitacao_nova', 'extracao'));
