-- 036 — a fila pega o que parou entre baixar e ler (25/09/2026).
--
-- O ACHADO: um pedido "Extrair com GPT" em Poá não teve efeito. Poá estava em `baixada_ok` — baixada às 00h30
-- e nunca lida (o W20 daquela hora parou depois do W21). O W11 aceitou o pedido e o fn_pedir_processamento deu
-- prioridade, mas a fila (fn_reivindicar) não tinha `baixada_ok` nem `erro_leitura` na lista de estados: o W20 sabe
-- continuar deles (vai direto à leitura, W22), e ninguém os entregava — a licitação ficava órfã, e o W10 levava
-- quatro outras no lugar dela.
--
-- A CORREÇÃO: os dois entram na fila; e, como ler é de graça (R$ 0), entram também sem provedor real, como
-- nova/retificada/falha_rede. `respondida` continua fora: verificar/publicar sem provedor real seria recusado (T15).

-- A de db/035, com os dois estados (as linhas marcadas).
CREATE OR REPLACE FUNCTION fn_reivindicar(p_por text, p_max_por_execucao int)
RETURNS TABLE (controle text, estado text, ordem int) LANGUAGE plpgsql AS $$
DECLARE
    v_limite int;
    v_real   bool := fn_provedor_real();
BEGIN
    SELECT 4 - count(*) INTO v_limite FROM licitacoes WHERE licitacoes.estado = 'extraindo';
    v_limite := LEAST(v_limite, COALESCE(p_max_por_execucao, v_limite));
    IF v_limite <= 0 THEN
        RETURN;
    END IF;
    RETURN QUERY
    WITH candidatas AS (
        SELECT l.controle, l.prioridade, (l.estado = 'retificada') AS retificada, l.fim_prazo
          FROM licitacoes l
         WHERE l.estado IN ('nova', 'retificada', 'falha_rede', 'baixada_ok', 'erro_leitura',     -- 036
                            'erro_extracao', 'aguardando_orcamento', 'preparada', 'verificada')
           AND (l.proxima_tentativa_em IS NULL OR l.proxima_tentativa_em <= now())
           AND l.tentativas < 4
           AND NOT l.reserva_demo
           AND (l.fim_prazo IS NULL OR l.fim_prazo >= current_date)
           AND (l.lease_por IS NULL OR l.lease_ate < now())
           AND fn_escopo_efetivo(l.controle, l.escopo_dentro)
           AND NOT fn_ia_trava(l.controle)                                                       -- 035
           AND (v_real OR l.ensaio OR fn_provedor_pedido(l.controle) IS NOT NULL
                OR l.estado IN ('nova', 'retificada', 'falha_rede', 'baixada_ok', 'erro_leitura'))   -- 036
           AND fn_no_recorte(l.fim_prazo, l.publicado_em)
         ORDER BY l.prioridade DESC, (l.estado = 'retificada') DESC, l.fim_prazo NULLS LAST, l.controle
         LIMIT v_limite
           FOR UPDATE OF l SKIP LOCKED
    ), ordenadas AS (
        SELECT c.controle,
               row_number() OVER (ORDER BY c.prioridade DESC, c.retificada DESC,
                                  c.fim_prazo NULLS LAST, c.controle)::int AS ordem
          FROM candidatas c
    ), marcadas AS (
        UPDATE licitacoes l
           SET lease_por = p_por, lease_ate = now() + interval '2 hours'
          FROM ordenadas c
         WHERE l.controle = c.controle
        RETURNING l.controle, l.estado::text AS estado, c.ordem
    )
    SELECT m.controle, m.estado, m.ordem FROM marcadas m ORDER BY m.ordem;
END $$;
