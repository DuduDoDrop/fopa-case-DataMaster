-- 012 — seed: questionário, termos de busca, orçamento e o admin.
--
-- As 17 perguntas vêm de scripts/fopa/questionario.py (PERGUNTAS), que é a
-- fonte única da verdade; este arquivo é uma cópia gerada, não uma segunda
-- fonte. `versao_questionario` = sha256 do módulo no momento da geração
-- (4d8fd378d13631cd4a1868594cf2c845d7283b7b1afa1669748ffedc5b67e9bd), para que uma mudança nas perguntas
-- apareça como versão nova em vez de sobrescrever esta. O teste
-- test_seed_perguntas_bate_com_o_modulo confere id/texto/critico/formato
-- contra o módulo: se divergirem, o seed é que está velho.
--
-- Os `termos` são os 6 do 20_monitor.py:58-78, na ordem em que o monitor os
-- consulta (prioridade). Orçamento: teto NULL (sem teto), auto_processar
-- true — decisão de produto (seção 2). Usuário admin: o administrador do projeto.

INSERT INTO perguntas (id, texto, orienta, formato, critico, versao_questionario) VALUES
    ('Q1', 'Qual a Data da Licitação ?', 'Data e hora da sessão pública. Se houver aviso de retificação, suspensão ou redesignação, a data válida é a DELE, não a do edital.', 'DD/MM/AAAA às HHhMM (horário de Brasília)', true, 'sha256:4d8fd378d136'),
    ('Q2', 'O que diz o Objeto do Edital ?', 'Texto integral do objeto, sem resumir.', NULL, false, 'sha256:4d8fd378d136'),
    ('Q3', 'Qual a Modalidade de Contratação ?', 'Ex.: PREGÃO ELETRÔNICO, CONCORRÊNCIA, CREDENCIAMENTO, DISPENSA, INEXIGIBILIDADE.', NULL, false, 'sha256:4d8fd378d136'),
    ('Q4', 'Qual o Tipo do Pregão ?', 'Critério de julgamento. Em folha costuma ser Maior Lance ou Maior Oferta. Em credenciamento e contratação direta pode não se aplicar.', NULL, false, 'sha256:4d8fd378d136'),
    ('Q5', 'Qual o Valor Mínimo de Contratação ?', 'Transcreva o rótulo COMO ESTÁ no documento: ''valor mínimo'', ''valor estimado'' e ''valor de referência'' são conceitos distintos em leilão de maior oferta. Não normalize o rótulo.', 'R$ X (VALOR POR EXTENSO), com o rótulo literal usado no documento', true, 'sha256:4d8fd378d136'),
    ('Q6', 'Qual o valor dos Lances Mínimos ?', 'Intervalo mínimo entre lances, em % ou R$.', NULL, false, 'sha256:4d8fd378d136'),
    ('Q7', 'Qual é o Prazo de Assinatura do Contrato ?', 'Prazo e a partir de quando conta.', NULL, false, 'sha256:4d8fd378d136'),
    ('Q8', 'Qual é o Prazo de Pagamento ?', 'Prazo para o banco pagar o valor ofertado ao ente.', NULL, false, 'sha256:4d8fd378d136'),
    ('Q9', 'Qual o prazo de vigência do contrato ?', 'Em meses ou anos, com prorrogação se houver.', NULL, true, 'sha256:4d8fd378d136'),
    ('Q10', 'Qual o prazo de início de serviços ?', 'Prazo e prorrogação, se houver.', NULL, false, 'sha256:4d8fd378d136'),
    ('Q11', 'Quais são as obrigações do banco vencedor ?', 'Obrigações principais, resumidas sem perder números e prazos.', NULL, false, 'sha256:4d8fd378d136'),
    ('Q12', 'Qual é a infraestrutura solicitada ?', 'Agência, PAB, posto de atendimento, caixas eletrônicos e prazo de instalação. Registre se é obrigatória ou facultativa.', NULL, true, 'sha256:4d8fd378d136'),
    ('Q13', 'Qual a quantidade de servidores aberta por faixa salarial ?', 'PIRÂMIDE COMPLETA. Há quase sempre MAIS DE UMA TABELA, separada por vínculo (contratos, estatutários, ativos, inativos, pensionistas, temporários). Capture todas, some cada uma e confira com o total impresso DELA. Declare qual população a pirâmide cobre e qual ela exclui.', '"Vínculo X — Até R$ A: n; R$ A,01 a R$ B: m; Acima de R$ B: k (total N)" por tabela, mais a população coberta', true, 'sha256:4d8fd378d136'),
    ('Q14', 'Qual a Quantidade total de servidores ?', 'Número total E A UNIDADE: vínculos ou pessoas físicas. Um servidor pode acumular mais de um vínculo. Se o documento não disser, registre que não diz.', '"N vínculos" ou "N pessoas", explicitando qual', true, 'sha256:4d8fd378d136'),
    ('Q15', 'Quais são as condições do consignado ?', 'Margem consignável, taxa-teto, exclusividade, prazos e quem faz a averbação.', NULL, false, 'sha256:4d8fd378d136'),
    ('Q16', 'Existe necessidade do vencedor realizar prova de vida dos servidores ?', 'Sim/Não e em que condição. Recadastramento de beneficiários conta como prova de vida.', NULL, false, 'sha256:4d8fd378d136'),
    ('Q17', 'Existe necessidade do vencedor apresentar alguma garantia ?', 'Sim/Não, percentual, modalidade e A BASE DE CÁLCULO declarada. Pode estar em documento de esclarecimento, não só no edital. Nunca calcule o valor.', NULL, true, 'sha256:4d8fd378d136')
ON CONFLICT (id) DO NOTHING;

INSERT INTO termos (termo, paginas, ativo, prioridade) VALUES
    ('cessão onerosa folha de pagamento',                    10, true, 1),
    ('folha de pagamento servidores instituição financeira', 10, true, 2),
    ('folha de pagamento instituição bancária',              10, true, 3),
    ('créditos da folha de pagamento',                       10, true, 4),
    ('créditos provenientes da folha de pagamento',          10, true, 5),
    ('folha salarial instituição financeira',                10, true, 6)
ON CONFLICT (termo) DO NOTHING;

INSERT INTO orcamento (teto_brl_dia, max_por_execucao, auto_processar, vigente, alterado_por)
SELECT NULL, NULL, true, true, 'seed'
 WHERE NOT EXISTS (SELECT 1 FROM orcamento WHERE vigente);

INSERT INTO usuarios (email, nome, papel, ativo) VALUES
    ('admin@exemplo.com', 'Admin', 'admin', true)
ON CONFLICT (email) DO NOTHING;
