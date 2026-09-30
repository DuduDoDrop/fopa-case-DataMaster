-- 048 — o site remove usuário (27/09/2026).
--
-- Requisito (27/09): um botão para remover usuário e outro para bloquear; o removido pode criar a conta de novo.
-- Remover apaga o cadastro (quem entrar de novo com o Google volta como usuário); bloquear é o `ativo = false`
-- de sempre. Só o supremo remove, e nunca a si mesmo (api/site.py: usuario_remover). O que o usuário fez fica: o
-- histórico guarda o e-mail como texto, sem chave estrangeira — a única é a de `sessoes`, que a API apaga antes.

GRANT DELETE ON usuarios TO api_rw;
