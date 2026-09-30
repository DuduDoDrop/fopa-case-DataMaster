-- 014 — o que a importação do acervo v2 (plano, seção 9) precisa do banco.
--
-- A importação tem de ser idempotente: rodar `importar` duas vezes não muda
-- nada, e rodar de novo sobre um snapshot maior só acrescenta. Para isso cada
-- coisa importada precisa de uma chave natural; as que o esquema da seção 7
-- não tinha entram aqui.

-- Execuções não tinham chave natural (várias por controle, de várias origens).
-- `chave_migracao` = 'agente:<pasta>', 'api:<pasta>', 'harness:<arquivo>:<i>',
-- 'experimento:<pasta>'. Execuções da v3 deixam NULL (UNIQUE aceita vários NULL).
ALTER TABLE execucoes_modelo ADD COLUMN chave_migracao text UNIQUE;

-- O log legado (_execucoes.jsonl) entra uma linha por (script, instante).
CREATE UNIQUE INDEX execucoes_workflow_legado
    ON execucoes_workflow (script_legado, iniciado_em) WHERE script_legado IS NOT NULL;

-- Cinco arquivos do acervo estão no inventário e não estão no disco do
-- snapshot. Nenhum dos status da seção 7 diz isso sem mentir: não é falha de
-- rede, não é recusa, não está corrompido. É ausência, e fica com o nome dela.
ALTER TABLE arquivos DROP CONSTRAINT arquivos_status_check;
ALTER TABLE arquivos ADD CONSTRAINT arquivos_status_check CHECK (status IN (
    'ok', 'recusado_politica', 'formato_nao_suportado', 'corrompido', 'falha_rede',
    'zip_container', 'alias_duplicado', 'fora_inventario', 'procedencia_incerta',
    'ausente_no_disco'));

-- Um registro por passe de importação: de qual snapshot, com qual manifesto,
-- o que entrou, o que ficou para decisão do gestor do projeto (seção 9, passo 8).
CREATE TABLE importacoes (
    id               bigserial PRIMARY KEY,
    snapshot         text NOT NULL,
    manifesto_sha256 char(64),
    iniciado_em      timestamptz NOT NULL DEFAULT now(),
    finalizado_em    timestamptz,
    contagens        jsonb,
    avisos           jsonb,
    decisoes         jsonb,
    relatorio        text
);

GRANT INSERT, UPDATE ON importacoes TO worker_rw;
