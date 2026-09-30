-- 046 — o admin supremo e o usuário comum (26/09/2026).
--
-- Requisito (26/09): quem faz login é cadastrado automaticamente como usuário; um único admin supremo concede e
-- remove o papel de admin; o admin comum não pode remover o acesso do supremo.
--
-- O supremo é um ADMIN com a marca `supremo` — não um papel novo: tudo que já pergunta "papel = 'admin'" (o login
-- local da demo, os destinatários do W50) continua valendo sem mudança. Só ele muda papel e acesso dos outros
-- (api/site.py: so_supremo), e o banco garante o resto: ele é admin e ativo, e há um só. O usuário que entra pelo
-- Google sem cadastro vira `leitor` (o "usuário" da tela) no próprio login.

ALTER TABLE usuarios ADD COLUMN supremo boolean NOT NULL DEFAULT false;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_supremo_e_admin_ativo CHECK (NOT supremo OR (papel = 'admin' AND ativo));
CREATE UNIQUE INDEX usuarios_um_so_supremo ON usuarios (supremo) WHERE supremo;

UPDATE usuarios SET supremo = true WHERE email = 'admin@exemplo.com';

COMMENT ON COLUMN usuarios.supremo IS
    'o admin supremo (um só, admin e ativo): o único que muda papel e acesso dos outros; o site não o altera — db/046';
