-- 041 — o fluxo de exceção do download (25/09/2026): o que fazer quando o arquivo que vem da API não é PDF.
--
-- O arquivo que o PNCP entrega em RTF, DOC, DOCX, XLS, HTML, imagem ou RAR vira PDF no worker (api/converter.py). O
-- ORIGINAL fica registrado com o status `convertido` e cada PDF gerado entra como filho dele (`pai_id`), com a origem
-- em `proveniencia.convertido_de` — como o `zip_container` e os PDFs de dentro do ZIP. Se a conversão falhar, o
-- arquivo continua `formato_nao_suportado`, com o motivo. (A 040 é a trava do Jev, no branch jev-teto.)

ALTER TABLE arquivos DROP CONSTRAINT arquivos_status_check;
ALTER TABLE arquivos ADD CONSTRAINT arquivos_status_check CHECK (status IN (
    'ok', 'recusado_politica', 'formato_nao_suportado', 'corrompido', 'falha_rede',
    'zip_container', 'alias_duplicado', 'fora_inventario', 'procedencia_incerta',
    'ausente_no_disco', 'convertido'));
