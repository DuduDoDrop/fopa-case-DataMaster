-- 043 — OCR forçado por arquivo e rotação (Pacote B, 26/09/2026).
--
-- O RN-19 decide o OCR por caracteres/página, e três defeitos passam por ele com o texto ruim: a camada de texto
-- cortada à direita (Piraí/RJ, Blumenau/SC, Pomerode/SC), o carimbo de autenticação em texto por cima de uma página em
-- imagem (Cuiabá/MT, SEFAZ/MT, Mineiros/GO) e o contrato escaneado de cabeça para baixo (Timon/MA). O operador marca
-- o ARQUIVO (scripts/82_forcar_ocr.py) e a marcação fica gravada: toda releitura futura a respeita (api/leitura.py lê
-- o arquivo como imagem, girado, e põe a marcação na `versao_ocr` — outro OCR, outro texto). O `ON CONFLICT (controle,
-- nome) DO UPDATE` do download não lista estas colunas: baixar de novo não apaga a marcação.

ALTER TABLE arquivos
    ADD COLUMN forcar_ocr boolean NOT NULL DEFAULT false,
    ADD COLUMN girar smallint NOT NULL DEFAULT 0 CONSTRAINT arquivos_girar_check CHECK (girar IN (0, 90, 180, 270));

COMMENT ON COLUMN arquivos.forcar_ocr IS 'ler só pela imagem (OCR), ignorando a camada de texto — db/043';
COMMENT ON COLUMN arquivos.girar IS 'graus no sentido horário antes do OCR; implica OCR forçado — db/043';
