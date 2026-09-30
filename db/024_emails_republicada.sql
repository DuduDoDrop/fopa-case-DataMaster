-- 024 — dois tipos de e-mail da reverificação (W24 modo republicar e W30).
--
-- O plano (seção 5) manda o W30 reverificar em lote e o W24 republicar o que
-- mudou, cada um com o seu aviso na fila. O CHECK da 008 só conhecia os tipos
-- da extração: 'processada' para uma republicação mentiria (nenhum modelo
-- respondeu de novo — só as regras mudaram, ADR-011/014).
--
--   republicada   : W24 modo republicar — uma verificação nova (mesmas
--                   respostas, regras novas) virou a vigente; o e-mail leva o
--                   diff de vereditos e de alertas contra a vigente anterior.
--   reverificacao : W30 — UM resumo por rodada (quantas reverificadas, quantas
--                   mudaram, quantas pendentes de leitura), custo R$ 0.
--
-- Os fluxos só inserem 'pendente'; quem envia continua sendo o W50.

ALTER TABLE emails DROP CONSTRAINT emails_tipo_check;
ALTER TABLE emails ADD CONSTRAINT emails_tipo_check CHECK (tipo IN (
    'carregada', 'processada', 'erro', 'alerta_diario', 'orcamento', 'cego', 'furtivo',
    'republicada', 'reverificacao'));
