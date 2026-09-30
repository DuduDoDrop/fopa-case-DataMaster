-- 015 — a identidade de uma leitura inclui os NOMES dos arquivos.
--
-- A seção 7 do plano pôs UNIQUE (controle, assinatura_conjunto, versao_ocr), e
-- `assinatura_conjunto` é o hash do TEXTO sem os nomes — o critério de gêmea
-- do 70_. A importação do acervo real achou o caso que o plano não previu:
-- Capep tem duas pastas do mesmo controle com o mesmo texto e nomes de arquivo
-- diferentes ("…__A.pdf", cortado pelo downloader antigo, e
-- "…__AGOSTO_2026_Retificado.pdf"). A chave juntava as duas numa leitura só,
-- com os nomes de uma delas, e a execução canônica passava a citar arquivos
-- que não existem no seu texto congelado — 15 respostas APROVADAS apontando
-- para o nada, pegas pelo invariante `aprovada_sem_pagina`.
--
-- A resposta cita pelo NOME ("=== ARQUIVO x | PÁGINA n ==="), então o nome faz
-- parte da leitura. `assinatura_conjunto` continua existindo para as gêmeas.

-- Mesmo cálculo de migracao.regras.assinatura_nomes: sha256 das linhas
-- "nome<TAB>hash" em ordem de code point (COLLATE "C" = ordem de bytes UTF-8),
-- unidas por "\n". Sem arquivo nenhum, é o sha256 da string vazia, como no
-- Python. db/tests confere a paridade com acentos e ordem embaralhada.
CREATE FUNCTION fn_assinatura_nomes(p_assinatura jsonb) RETURNS char(64)
LANGUAGE sql IMMUTABLE AS $$
    SELECT encode(sha256(convert_to(COALESCE(
               string_agg(e.key || E'\t' || e.value, E'\n'
                          ORDER BY (e.key || E'\t' || e.value) COLLATE "C"), ''), 'UTF8')), 'hex')
      FROM jsonb_each_text(COALESCE(p_assinatura, '{}'::jsonb)) e
$$;

ALTER TABLE leituras ADD COLUMN assinatura_nomes char(64);
UPDATE leituras SET assinatura_nomes = fn_assinatura_nomes(assinatura) WHERE assinatura_nomes IS NULL;
ALTER TABLE leituras ALTER COLUMN assinatura_nomes SET NOT NULL;

ALTER TABLE leituras DROP CONSTRAINT leituras_controle_assinatura_conjunto_versao_ocr_key;
ALTER TABLE leituras ADD CONSTRAINT leituras_identidade UNIQUE (controle, assinatura_nomes, versao_ocr);
