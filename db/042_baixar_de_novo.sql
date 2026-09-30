-- 042 — baixar de novo uma licitação que já tinha PDF (fluxo de exceção, ADR-017, 25/09/2026).
--
-- Com o fluxo de exceção, o arquivo que o download recusou pelo formato (RTF, .doc, RAR...) agora vira PDF. A
-- licitação presa por inteiro (formato_nao_suportado, sem_pdf_legivel) já voltava a `nova` (022). A que tinha ALGUM
-- PDF e ficou `baixada_ok`/`preparada` sem o anexo — Barra do Garças/MT com o edital em RTF ao lado de um aviso,
-- Dom Cavati/MG com o edital num .doc ao lado da ata de outro pregão — só voltava ao download por `retificada`, que a
-- marcaria como retificada no PNCP sem ela ter mudado. Só o operador usa (fn_transicao direto): o "forçar" do site
-- continua como era (fn_pedir_processamento só reinicia os estados terminais).

INSERT INTO transicoes (de, para, nota) VALUES
    ('baixada_ok', 'nova', 'operador: baixar de novo — o arquivo recusado pelo formato agora vira PDF (ADR-017)'),
    ('preparada',  'nova', 'operador: baixar de novo — o arquivo recusado pelo formato agora vira PDF (ADR-017)')
ON CONFLICT DO NOTHING;
