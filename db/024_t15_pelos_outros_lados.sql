-- 024 — T15 fechada pelos outros dois lados.
--
-- T15: execução `simulado`/`gravado` nunca vira a verificação vigente de uma
-- licitação que não é de ensaio. O gatilho da 005 (`vigente_exige_ensaio`)
-- só olhava `verificacoes` — o momento em que a vigente é marcada. O CI
-- (api/tests/test_invariantes_sql.py, 24/09/2026) achou os dois contornos:
--
--   1. a vigente é de uma execução real, e DEPOIS a execução troca de origem
--      para simulado/gravado;
--   2. a vigente é simulada numa licitação de ensaio, e DEPOIS o ensaio é
--      desligado.
--
-- Nos dois a licitação ficava publicada com resposta de regex como se fosse
-- de modelo, e só o invariante pegava, depois do fato. Agora o banco recusa na
-- hora. (O `demo_reservar --soltar` já mantém `ensaio` quando a vigente é
-- simulada/gravada — ele não é afetado.)

CREATE FUNCTION fn_t15_origem_da_execucao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.origem IN ('simulado', 'gravado') AND OLD.origem IS DISTINCT FROM NEW.origem
       AND EXISTS (SELECT 1 FROM verificacoes v JOIN licitacoes l ON l.controle = v.controle
                    WHERE v.execucao_id = NEW.id AND v.vigente AND NOT l.ensaio) THEN
        RAISE EXCEPTION 'execução % tem verificação vigente em licitação que não é ensaio: não pode virar % (T15)',
            NEW.id, NEW.origem USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER t15_origem_da_execucao
    BEFORE UPDATE OF origem ON execucoes_modelo
    FOR EACH ROW EXECUTE FUNCTION fn_t15_origem_da_execucao();

CREATE FUNCTION fn_t15_ensaio_da_licitacao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.ensaio AND NOT NEW.ensaio
       AND EXISTS (SELECT 1 FROM verificacoes v JOIN execucoes_modelo e ON e.id = v.execucao_id
                    WHERE v.controle = NEW.controle AND v.vigente AND e.origem IN ('simulado', 'gravado')) THEN
        RAISE EXCEPTION 'licitação % tem verificação vigente simulada/gravada: o ensaio não pode ser desligado (T15)',
            NEW.controle USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER t15_ensaio_da_licitacao
    BEFORE UPDATE OF ensaio ON licitacoes
    FOR EACH ROW EXECUTE FUNCTION fn_t15_ensaio_da_licitacao();
