-- 031 — o rótulo humano de escopo PREVALECE na tela (24/09/2026): os casos que a revisão humana
-- confirma como fora do escopo saem das telas.
--
-- Até aqui o rótulo era só gabarito (006, api/site.py:rotular_escopo): media a regra e o Jev, e a licitação
-- que a revisão humana dizia "não é folha" continuava no painel, no histórico e no analytics. Agora a tela usa o ESCOPO
-- EFETIVO: o rótulo humano mais recente, se houver; senão, a regra. A regra continua gravada e intocada em
-- `licitacoes.escopo_dentro` (ADR-003, T25 — o Jev não escreve escopo, e o rótulo não reescreve a regra);
-- rotular de novo desfaz. A fila paga (W10) ainda olha só a regra.

CREATE INDEX rotulos_escopo_controle_em ON rotulos_escopo (controle, em DESC, id DESC);

CREATE FUNCTION fn_escopo_efetivo(p_controle text, p_regra bool)
RETURNS bool LANGUAGE sql STABLE AS $$
    SELECT COALESCE((SELECT r.veredito = 'dentro' FROM rotulos_escopo r
                      WHERE r.controle = p_controle ORDER BY r.em DESC, r.id DESC LIMIT 1), p_regra)
$$;

GRANT EXECUTE ON FUNCTION fn_escopo_efetivo(text, bool) TO api_ro, api_rw, worker_rw, n8n_rw;
