-- 050 — Best-of-N: a rodada de cada chamada e o registro da escolha (28/09/2026, v3.1).
--
-- Decisão (28/09): Best-of-N com N=3, aplicado só às respostas que falham. Depois dos lotes, o W23 pede ao worker
-- (POST /reforco) os lotes só das perguntas que o verificador reprovou ou não localizou e chama o modelo de novo —
-- até N-1 rodadas. Cada chamada guarda a RODADA: 0 = o lote normal (tudo o que existia até aqui); 1..N-1 = reforço.
-- O /verificar funde as chamadas da rodada 0 como sempre e, para cada pergunta com candidatos do reforço, escolhe
-- pelo veredito do próprio verificador (scripts/fopa/melhor_de_n.py); o que ele decidiu fica na verificação.
--
-- Quem grava: o n8n (W23, n8n_rw) insere a chamada com a rodada (INSERT em chamadas_modelo, 011); o worker
-- (worker_rw) grava `verificacoes.melhor_de_n` (UPDATE em verificacoes, 011). Nenhum GRANT novo.

ALTER TABLE chamadas_modelo ADD COLUMN rodada int NOT NULL DEFAULT 0;
ALTER TABLE chamadas_modelo ADD CONSTRAINT chamadas_modelo_rodada_check CHECK (rodada >= 0);

-- {"n": 3, "rodadas": 1, "perguntas": {"Q7": {"tentativas": 2, "escolhida": 1, "pontos": [[-1, 0.41], [2, 1.0]]}}}
-- NULL = execução sem Best-of-N (as de antes da v3.1, o agente, o gravado).
ALTER TABLE verificacoes ADD COLUMN melhor_de_n jsonb;

INSERT INTO configuracao (chave, valor, descricao, alterado_por) VALUES
    ('melhor_de_n', '3',
     'Best-of-N (v3.1): tentativas por pergunta que falha no verificador (1 = desligado); o reforço só pede as que falham',
     'migracao-050')
ON CONFLICT (chave) DO NOTHING;
