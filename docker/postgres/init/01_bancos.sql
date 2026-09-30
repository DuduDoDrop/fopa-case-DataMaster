-- Roda UMA vez, na primeira subida do fopa-postgres (volume vazio), pelo
-- docker-entrypoint-initdb.d. O banco `fopa` já existe (POSTGRES_DB); aqui
-- nasce o segundo banco do mesmo container, `n8n`, com um usuário próprio —
-- o n8n nunca entra como superusuário e nunca enxerga o banco de negócio por
-- esta credencial (para o banco `fopa` ele usa o papel `n8n_rw`, criado pela
-- migração com os grants restritos de db/011_papeis.sql).
--
-- A senha vem da env N8N_DB_PASSWORD do container (o compose a passa) via
-- \getenv, para não haver segredo em arquivo versionado. Se a env não existir,
-- :'n8n_db_password' fica sem expandir, o CREATE ROLE falha e o entrypoint
-- aborta com ON_ERROR_STOP — melhor do que um usuário sem senha.
--
-- Se o init falhar, o volume já foi inicializado e o script NÃO roda de novo:
-- `docker compose down -v` (apenas numa stack recém-criada) e subir outra vez.
\getenv n8n_db_password N8N_DB_PASSWORD

CREATE ROLE n8n LOGIN PASSWORD :'n8n_db_password';
CREATE DATABASE n8n OWNER n8n;
