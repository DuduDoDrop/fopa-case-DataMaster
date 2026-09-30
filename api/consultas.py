# -*- coding: utf-8 -*-
"""
SQL de leitura do site (plano, seções 7 e 8) — tudo sobre `v_card`,
`v_detalhe` e as tabelas; nenhuma escrita aqui (as poucas que o site faz
ficam em `site.py`, junto da regra de papel que as libera).

Cada função recebe uma conexão psycopg com `row_factory=dict_row` e devolve
dicts/listas prontos para JSON. Decimal e datetime saem como vêm: o
`jsonable_encoder` do FastAPI converte (Decimal → número, datetime → ISO).

RECORTE DE 2026 (ADR-015)
  Lista e resumo mostram, por padrão, só o que está no recorte; `todos`
  mostra tudo. A regra NÃO é reescrita aqui: é a `fn_no_recorte` da 018
  (sessão no `configuracao.ano_minimo` ou depois; sem sessão, a publicação;
  sem data nenhuma, fora) — a mesma com que o W01 decide não gravar e o
  `fn_tomar_vaga_extracao` recusa pagar. Mudar o ano é mudar a configuração.

JEV (db/017) É SINAL, NUNCA DECISÃO
  Nada daqui troca `escopo_dentro`, veredito ou confiança pelo que o Jev
  disse. O site só MOSTRA o sinal ao lado do que a regra/o verificador
  decidiram (`jev_filtro`, `jev`), e a aba "escopo" da revisão usa as
  candidatas dele como fila para o rótulo humano.

POR QUE `dias` NÃO SAI DAQUI
  O painel v2 congelava "faltam N dias" na geração (`painel.py:318`) e o
  número mentia uma semana depois. O front calcula no navegador a partir de
  `fim_prazo`, em America/Sao_Paulo. O SQL usa a MESMA conta (dia civil de
  São Paulo) só para filtrar e ordenar, para que "urgente" aqui e no card
  sejam a mesma coisa.
"""
from __future__ import annotations

import re
from datetime import date

# Diferença em dias CIVIS de São Paulo entre o fim do prazo e hoje — a conta
# de `painel._dias` (data do fim − data de hoje), sem hora.
DIAS = ("((c.fim_prazo AT TIME ZONE 'America/Sao_Paulo')::date"
        " - (now() AT TIME ZONE 'America/Sao_Paulo')::date)")

# Encerrada = o dia já passou, OU é hoje, tem hora e a hora passou — a mesma
# regra do card (web/src/lib/prazo.ts: calcularPrazo). Sem isto a sessão de
# hoje às 09:00 continuava em "urgentes" às 15:00, e o card dizia "encerrado".
ENCERRADA = ("(%s < 0 OR (%s = 0 AND c.fim_prazo_tem_hora AND c.fim_prazo <= now()))" % (DIAS, DIAS))

ESTADOS = ("nova", "fora_escopo", "fora_janela", "baixando", "baixada_ok", "sem_pdf_legivel",
           "formato_nao_suportado", "falha_rede", "lendo", "erro_leitura", "preparada", "extraindo",
           "respondida", "erro_extracao", "aguardando_orcamento", "verificada", "publicada",
           "retificada", "erro_definitivo", "legado_suspeito")

# Filtros da seção 8. "urgentes" exige dias >= 0: o painel v2 contava
# encerradas como urgentes (`painel.py:135`), defeito que não volta.
FILTROS = {
    "todas": "true",
    "urgentes": "(%s BETWEEN 0 AND 7 AND NOT %s)" % (DIAS, ENCERRADA),
    "alerta": "cardinality(c.alertas_globais) > 0",
    "conflito": "c.conflitos > 0",
    "extraidas": "c.extraida",
    # "Sem extração" é o que ESTÁ no escopo e ainda não foi extraído; o que o
    # regex descartou (ADR-003) nunca vai ser extraído e não é pendência.
    "sem_extracao": "NOT c.extraida AND fn_escopo_efetivo(c.controle, c.escopo_dentro)",
    "injecao": "c.injecao_suspeita",
    "retificadas": ("(c.estado = 'retificada' OR EXISTS (SELECT 1 FROM licitacao_eventos ev"
                    " WHERE ev.controle = c.controle AND ev.para = 'retificada'))"),
    "revisao": "c.revisao_pendente",
    "encerradas": ENCERRADA,
    "ensaio": "c.ensaio",
}

# Vencimento "até N dias": só as abertas, no mesmo dia civil de São Paulo do card — a regra do
# "urgentes" com o N da escolha. O "urgentes" (≤7) continua aceito pela API; o site passou a oferecer esta lista.
VENCIMENTOS = (7, 15, 30, 45, 60)


def cond_vence_em(dias: int) -> str:
    if dias not in VENCIMENTOS:
        raise ValueError("vence_em deve ser um de %s" % (VENCIMENTOS,))
    return "(%s BETWEEN 0 AND %d AND NOT %s)" % (DIAS, dias, ENCERRADA)

# Abertas por prazo (mais perto primeiro), depois encerradas, depois sem
# prazo — a chave de `painel.coletar()`: a lista serve para decidir onde
# entrar, e o que já fechou não é mais decisão.
ORDEM = ("CASE WHEN c.fim_prazo IS NULL THEN 2 WHEN %s THEN 1 ELSE 0 END,"
         " c.fim_prazo, c.controle" % ENCERRADA)

RE_PERGUNTA_ORDEM = "substring(%s from 2)::int"

# Recorte de 2026: a função da 018, sobre as colunas do card (alias `c`).
RECORTES = ("ano_minimo", "todos")
NO_RECORTE = "fn_no_recorte(c.fim_prazo, c.publicado_em)"


def _cond_recorte(recorte: str) -> str:
    return "true" if recorte == "todos" else NO_RECORTE


# Home × histórico: a sessão que já aconteceu vira LEGADO — sai da grade de
# trabalho e vai para o histórico (análise de quem ganhou), sem apagar nada. Sem data de sessão não é "passada"
# (não dá para dizer que acabou): fica na home. O histórico guarda TODO ano — o que é de antes de 2026 também é
# legado —, a sessão mais recente primeiro. `todas` é o padrão da API (o que ela sempre devolveu); o site pede
# `ativas` na home e `historico` na página do histórico. As duas PARTICIONAM o acervo (toda licitação cai em
# exatamente uma) e o recorte de ano não vale para nenhuma: o que é de antes de 2026 já é histórico, então
# `recorte=todos` na home traria de volta, em dobro, o que o histórico já mostra.
SITUACOES = ("todas", "ativas", "historico")
PASSADA = "(c.fim_prazo IS NOT NULL AND %s)" % ENCERRADA
# O painel mostra só as licitações ativas no momento. No acervo, 85 das 157 ativas eram
# dispensa/inexigibilidade SEM prazo, várias de janeiro e já com vencedor homologado no PNCP (db/027). Também
# deixa de estar valendo: a revogada/anulada, e a sem prazo publicada há mais de 60 dias (sem data de sessão e
# sem resultado, não há como dizer que ainda vale — e dispensa se resolve em semanas).
HOMOLOGADA = ("EXISTS (SELECT 1 FROM pncp_resultados r WHERE r.controle = c.controle"
              " AND r.cancelado_em IS NULL)")
DESFEITA = "coalesce(c.situacao, '') IN ('Revogada', 'Anulada')"
DIAS_SEM_PRAZO = 60
SEM_PRAZO_VELHA = ("(c.fim_prazo IS NULL AND c.publicado_em < (now() AT TIME ZONE 'America/Sao_Paulo')::date - %d)"
                   % DIAS_SEM_PRAZO)
# A IA não reconhece como FOPA (db/034): com CONVICÇÃO (nota <= 0,25) E depois de ver o edital (db/035 — o
# só-objeto tem o ponto cego do credenciamento) a licitação sai do painel e da fila e vai para o histórico — a trava;
# o filtro "apenas FOPA" (histórico e analytics) esconde o que a IA estima que não é (< 0,5), com a nota que houver.
# O rótulo humano "dentro" manda nos dois.
IA_NAO_FOPA_TRAVA = "fn_ia_trava(c.controle)"
IA_NAO_FOPA_FILTRO = "fn_ia_nao_fopa(c.controle, 0.5)"
# Credenciamento com a janela ainda aberta fica no painel mesmo homologado (Santa Cruz da Baixa
# Verde/PE e Montividiu do Norte/GO, homologados e abertos por mais 164 e 44 dias). No
# credenciamento o vencedor homologado não fecha a porta: outro banco se credencia até a data. O pregão homologado
# segue no histórico; o credenciamento revogado ou com a janela fechada também. A data absurda (db/047) o card já não
# tem: vale a regra das sem data.
CREDENCIAMENTO_ABERTO = "(c.modalidade = 'Credenciamento' AND c.fim_prazo IS NOT NULL AND NOT %s)" % ENCERRADA
VENCEDOR_ENCERRA = "(%s AND NOT %s)" % (HOMOLOGADA, CREDENCIAMENTO_ABERTO)
HISTORICO = "(%s OR NOT %s OR %s OR %s OR %s OR %s)" % (PASSADA, NO_RECORTE, VENCEDOR_ENCERRA, DESFEITA,
                                                        SEM_PRAZO_VELHA, IA_NAO_FOPA_TRAVA)


def _cond_datas(de: date | None, ate: date | None) -> str:
    """
    O filtro de datas do histórico: a PUBLICAÇÃO, com as duas pontas inclusas. Só entra
    data de verdade (a rota valida `date`), e ela vira literal ISO — nunca texto do usuário.
    """
    partes = []
    if de is not None:
        partes.append("c.publicado_em >= DATE '%s'" % date.fromisoformat(str(de)).isoformat())
    if ate is not None:
        partes.append("c.publicado_em <= DATE '%s'" % date.fromisoformat(str(ate)).isoformat())
    return " AND ".join(partes) or "true"


def _cond_situacao(situacao: str, recorte: str) -> str:
    if situacao == "historico":
        return HISTORICO
    if situacao == "ativas":
        return "NOT %s" % HISTORICO
    return _cond_recorte(recorte)


# Escopo (ADR-003/015): o painel abre só com o que a regra aceitou.
# `todos` mostra também o que a busca do
# PNCP trouxe e a regra recusou (é onde o Jev pode apontar um falso negativo).
#
# As telas de LICITAÇÕES só enxergam folha.
# Não há mais `escopo=todos` nem estado fora_escopo que traga o resto de volta: lista,
# filtros, contadores, detalhe, RELATORIO e PDF exigem `escopo_dentro`. Nada é apagado — o que a regra
# recusou continua no banco, na aba "escopo" da revisão (onde se corrige a regra) e no analytics.
# O ESCOPO EFETIVO (db/031):
# o rótulo humano mais recente prevalece na tela; sem rótulo, a regra. `escopo_dentro` continua sendo da regra.
SO_FOLHA = "fn_escopo_efetivo(c.controle, c.escopo_dentro)"
# Sem documento na fonte (db/044): o PNCP não entrega documento que se leia, então nunca vai ser extraída. Sai da
# lista e dos contadores e conta à parte em `sem_documento_fonte`; o detalhe continua abrindo pelo link (usa só
# SO_FOLHA).
SEM_DOCUMENTO = "EXISTS (SELECT 1 FROM sem_documento_fonte s WHERE s.controle = c.controle)"
NA_CONTA = "(%s AND NOT %s)" % (SO_FOLHA, SEM_DOCUMENTO)

# A flag "sem PDF válido" do card: os formatos que o sistema não lê (RTF, RAR, DOC antigo...), só onde a leitura parou
# por isso.
SEM_PDF = ("CASE WHEN c.estado IN ('formato_nao_suportado', 'sem_pdf_legivel') THEN coalesce("
           "(SELECT string_agg(DISTINCT CASE WHEN a.formato_real IS NULL OR a.formato_real LIKE 'desconhecido%%'"
           " THEN 'formato desconhecido' ELSE a.formato_real END, ', ')"
           " FROM arquivos a WHERE a.controle = c.controle AND a.status IN ('formato_nao_suportado', 'sem_pdf_legivel')),"
           " 'sem texto legível') END")

# Quantos trechos de texto escondido o detalhe leva (db/028). O suspeito vem primeiro e sempre cabe.
MAX_FURTIVOS_DETALHE = 60


# O sinal de ESCOPO mais recente de cada licitação que trouxe probabilidade:
# p_sim nulo é o Jev que não respondeu, e sem ela não há score. A discordância é
# com a regra de HOJE (licitacoes.escopo_dentro), não com a do dia da nota
# (sinais_jev.regra): quando a regra muda depois (a camada api/escopo_ajuste.py
# tirou 53 da folha em 25/09), o Jev que já dizia "não é folha" passa a concordar
# e sai da aba Escopo. As
# contas são as de `jev.interpretar_escopo`: p_filtro_ok = P(a regra acertou).
# O sinal de escopo que a tela mostra (24/09 noite, 73_): a MÉDIA do mais recente só-objeto com o mais recente
# com o edital (quando a licitação já foi lida), cada um cru em sinais_jev. A média derruba o alarme falso na
# folha de 4% para 0,8% e pega as mesmas recusas humanas. "Candidata" é a convicção (api/jev.py:CONVICCAO =
# 0,25) recalculada sobre a média.
# E a comparação é com o escopo que a TELA mostra — a regra de hoje com o rótulo humano mandando (db/031): a
# discordância que sobrava no painel e no histórico (Taquaraçu de Minas, Divinolândia de Minas) era o Jev
# concordando com o rótulo humano "é folha" e discordando só da regra que o rótulo já tinha vencido (25/09).
JEV_ESCOPO = (
    "SELECT u.controle,"
    " (CASE WHEN e.dentro THEN u.p ELSE 1 - u.p END)::float8 AS p_filtro_ok,"
    " u.p::float8 AS p_folha,"
    " ((u.p >= 0.5) <> e.dentro) AS discorda,"
    " (CASE WHEN e.dentro THEN u.p <= 0.25 ELSE u.p >= 0.75 END) AS candidata"
    " FROM (SELECT x.controle, avg(x.p_sim) AS p"
    "   FROM (SELECT DISTINCT ON (s.controle, left(coalesce(s.contexto_enviado, ''), 6) = 'edital')"
    "          s.id, s.controle, s.p_sim, s.em FROM sinais_jev s"
    "         WHERE s.tipo = 'escopo' AND s.p_sim IS NOT NULL"
    "         ORDER BY s.controle, left(coalesce(s.contexto_enviado, ''), 6) = 'edital', s.em DESC, s.id DESC) x"
    "   GROUP BY x.controle) u JOIN licitacoes l ON l.controle = u.controle"
    " CROSS JOIN LATERAL (SELECT fn_escopo_efetivo(l.controle, COALESCE(l.escopo_dentro, false)) AS dentro) e")
# O objeto `jev_filtro` do card (alias `j` = a CTE acima); NULL = nunca avaliada. `p_folha` é a chance de SER
# folha — o que a tela mostra desde 26/09; `p_filtro_ok` (a chance de o escopo estar certo) fica para as contas.
JEV_FILTRO = ("CASE WHEN j.controle IS NULL THEN NULL ELSE jsonb_build_object("
              "'p_filtro_ok', j.p_filtro_ok, 'p_folha', j.p_folha, 'discorda', j.discorda, 'candidata', j.candidata) END")


def _sem_busca(linha: dict) -> dict:
    linha.pop("busca", None)
    return linha


def _like(texto: str) -> str:
    """Termo de busca literal: `%`, `_` e `\\` do usuário não viram curinga."""
    return "%" + re.sub(r"([\\%_])", r"\\\1", texto.strip().lower()) + "%"


# ------------------------------------------------------------------ lista
def listar_licitacoes(conn, *, q=None, estado=None, uf=None, modalidade=None, filtro="todas", vence_em=None,
                      recorte="ano_minimo", situacao="todas", page=1, por_pagina=50, de=None, ate=None,
                      so_fopa_ia=False) -> dict:
    # `filtro`: uma chave ou várias — várias somam-se com E.
    filtros = [filtro] if isinstance(filtro, str) else (list(filtro) or ["todas"])
    # Nem pedir o estado fora_escopo de propósito traz o que a regra recusou: a tela é só de folha.
    where = [FILTROS[f] for f in filtros] + [_cond_situacao(situacao, recorte), NA_CONTA, _cond_datas(de, ate)]
    args = []
    if vence_em is not None:
        where.append(cond_vence_em(vence_em))
    if so_fopa_ia:
        where.append("NOT " + IA_NAO_FOPA_FILTRO)
    if q and q.strip():
        where.append(r"c.busca LIKE %s ESCAPE '\'")
        args.append(_like(q))
    if estado:
        where.append("c.estado = %s::estado_licitacao")
        args.append(estado)
    if uf:
        where.append("upper(c.uf) = upper(%s)")
        args.append(uf.strip())
    if modalidade:
        where.append("lower(c.modalidade) = lower(%s)")
        args.append(modalidade.strip())
    cond = " AND ".join("(%s)" % w for w in where)
    total = conn.execute("SELECT count(*) AS n FROM v_card c WHERE " + cond, args).fetchone()["n"]
    # MATERIALIZED: a nota do Jev de todo o acervo é calculada uma vez por consulta. Embutida (o padrão do Postgres),
    # com um filtro seletivo como o prazo ela era recalculada para cada card — em produção, 6 a 15 s em vez de 0,5 s.
    itens = conn.execute(
        "WITH jev AS MATERIALIZED (%s) SELECT c.*, %s AS no_recorte, %s AS jev_filtro, %s AS sem_pdf FROM v_card c"
        " LEFT JOIN jev j ON j.controle = c.controle WHERE %s ORDER BY %s LIMIT %%s OFFSET %%s"
        % (JEV_ESCOPO, NO_RECORTE, JEV_FILTRO, SEM_PDF, cond,
           "c.fim_prazo DESC NULLS LAST, c.controle" if situacao == "historico" else ORDEM),
        args + [por_pagina, (page - 1) * por_pagina]).fetchall()
    return {"total": total, "page": page, "por_pagina": por_pagina,
            "paginas": (total + por_pagina - 1) // por_pagina, "recorte": recorte,
            "situacao": situacao, "de": de.isoformat() if de else None, "ate": ate.isoformat() if ate else None,
            "itens": [_sem_busca(i) for i in itens]}


# ------------------------------------------------------------------ resumo
def resumo(conn, recorte="ano_minimo", situacao="todas", de=None, ate=None, so_fopa_ia=False) -> dict:
    """
    Tiles do painel. Todo contador sai do recorte e da situação pedidos, e só da folha
    (o que a regra recusou não conta em lugar nenhum); `fora_recorte` diz quantas o
    padrão esconde, e `historico` quantas já saíram da grade de trabalho.
    """
    ia = "NOT " + IA_NAO_FOPA_FILTRO if so_fopa_ia else "true"
    cond = "(%s) AND (%s) AND (%s) AND (%s)" % (_cond_situacao(situacao, recorte), NA_CONTA, _cond_datas(de, ate), ia)
    t = conn.execute(
        "SELECT count(*) AS licitacoes,"
        " count(*) FILTER (WHERE %(d)s >= 0 AND NOT %(e)s) AS abertas,"
        " count(*) FILTER (WHERE %(d)s BETWEEN 0 AND 7 AND NOT %(e)s) AS urgentes,"
        # a faixa âmbar da barra do "em andamento" (26/09): abertas de 8 a 20 dias — as faixas da barrinha dos cards
        " count(*) FILTER (WHERE %(d)s BETWEEN 8 AND 20 AND NOT %(e)s) AS aviso,"
        " count(*) FILTER (WHERE c.extraida) AS extraidas,"
        " COALESCE(sum(c.ancoradas) FILTER (WHERE c.extraida), 0) AS ancoradas,"
        " COALESCE(sum(c.respondidas) FILTER (WHERE c.extraida), 0) AS respondidas,"
        " COALESCE(sum(c.revisar) FILTER (WHERE c.extraida), 0) AS respostas_revisar,"
        # Custo conhecido = o gravado na execução, ou o legado da v2 quando é
        # só o que existe. Nenhum dos dois = "sem preço" (preço não configurado),
        # NUNCA R$ 0 (ADR-012). A extração que rodou LOCAL (agente, ADR-014) não
        # é "sem preço": não houve chamada de API — conta à parte, em
        # `extraidas_local` (saber se rodou local ou na API).
        " COALESCE(sum(COALESCE(c.brl, c.brl_legado)) FILTER (WHERE c.extraida), 0) AS custo_conhecido_brl,"
        " count(*) FILTER (WHERE c.extraida AND c.brl IS NULL AND c.brl_legado IS NULL"
        "                  AND c.procedencia IS DISTINCT FROM 'agente') AS custo_sem_preco,"
        " count(*) FILTER (WHERE c.extraida AND c.procedencia = 'agente') AS extraidas_local,"
        # Os motivos de estar no histórico, que os quadros de lá mostram ("abertas" e "≤7 dias" não dizem nada sobre o
        # que já passou).
        " count(*) FILTER (WHERE %(h)s) AS com_vencedor,"
        " count(*) FILTER (WHERE %(x)s) AS desfeitas,"
        " count(*) FILTER (WHERE NOT %(nr)s) AS antes_do_recorte"
        " FROM v_card c WHERE %(r)s" % {"d": DIAS, "e": ENCERRADA, "r": cond, "h": HOMOLOGADA, "x": DESFEITA,
                                         "nr": NO_RECORTE}).fetchone()
    t["para_revisar"] = conn.execute(
        "SELECT count(*) AS n FROM revisoes_humanas h JOIN licitacoes c ON c.controle = h.controle"
        " WHERE h.status = 'aberta' AND " + REVISAO_DA_VIGENTE + " AND " + cond).fetchone()["n"]
    t["ultima_coleta"] = ultima_coleta(conn)
    orc = orcamento_vigente(conn) or {}
    t["teto_brl_dia"] = orc.get("teto_brl_dia")
    t["auto_processar"] = orc.get("auto_processar")
    t["provedor"] = config_valor(conn, "provedor")
    t["recorte"] = recorte
    t["ano_minimo"] = conn.execute("SELECT fn_ano_minimo() AS a").fetchone()["a"]
    t["fora_recorte"] = conn.execute("SELECT count(*) AS n FROM licitacoes c WHERE %s AND NOT %s"
                                     % (NA_CONTA, NO_RECORTE)).fetchone()["n"]
    t["situacao"] = situacao
    # As que ficaram fora da conta por falta de documento na fonte, com os mesmos recortes; a duplicata de outra compra
    # (`duplicata_de`) não conta nem aqui — a outra compra já está nos números.
    cond_fonte = "(%s) AND (%s) AND (%s) AND (%s)" % (_cond_situacao(situacao, recorte), SO_FOLHA, _cond_datas(de, ate), ia)
    t["sem_documento_fonte"] = conn.execute(
        "SELECT count(*) AS n FROM v_card c JOIN sem_documento_fonte s ON s.controle = c.controle"
        " WHERE s.duplicata_de IS NULL AND " + cond_fonte).fetchone()["n"]
    # O link "N no histórico →" do painel leva à página do histórico: conta o que ela mostra, com o mesmo "só o que a
    # IA confirma" (26/09: o link dizia 2.045 e a página, 2.036).
    t["historico"] = conn.execute("SELECT count(*) AS n FROM v_card c WHERE %s AND %s AND (%s)"
                                  % (HISTORICO, NA_CONTA, ia)).fetchone()["n"]
    jev = conn.execute(
        "WITH jev AS (" + JEV_ESCOPO + ") SELECT count(*) AS escopo_avaliadas,"
        " count(*) FILTER (WHERE j.discorda) AS escopo_discordancias,"
        " round(avg(j.p_filtro_ok)::numeric, 4)::float8 AS p_filtro_ok_medio"
        " FROM licitacoes c JOIN jev j ON j.controle = c.controle WHERE " + cond).fetchone()
    # Sem nenhum sinal no recorte, "média 0" mentiria: null = o Jev não olhou.
    t["jev"] = jev if jev["escopo_avaliadas"] else None
    return t


def ultima_coleta(conn) -> dict | None:
    """
    A última DESCOBERTA no PNCP: W01 na v3, o monitor na v2. A linha que o W90
    grava quando o W01 falha (gatilho 'erro') não é coleta, é alerta — sai em
    `ultimo_alerta`; aqui fica a última rodada que de fato rodou.
    """
    return conn.execute(
        "SELECT id, workflow, script_legado, iniciado_em, duracao_s, cego, status"
        " FROM execucoes_workflow WHERE (workflow = 'W01' OR script_legado = '20_monitor.py')"
        " AND gatilho IS DISTINCT FROM 'erro'"
        " ORDER BY iniciado_em DESC, id DESC LIMIT 1").fetchone()


def ultimo_alerta(conn) -> dict | None:
    """
    A última falha registrada, `{em, workflow, mensagem}`. Duas fontes, porque
    são dois caminhos que avisam a operação:

    - `execucoes_workflow` com status 'erro' (007): o W90 grava UMA linha por
      falha de fluxo raiz, inclusive as que o anti-tempestade não mandou por
      e-mail — é o registro completo, com fluxo e mensagem;
    - `saude` (008) com o worker fora do contrato: o W00 não passa pelo W90
      (ele mesmo enfileira o e-mail) e deixa só a linha da medida, com os
      motivos em `detalhes.motivos`.

    Não sai de `emails`: o anti-tempestade segura repetidas (o último e-mail
    pode ser mais velho que a última falha) e o assunto é texto livre. Nem só
    de `saude`: ela é a medida horária do W00 e nunca vê falha de W01/W20
    (o W00 grava `n8n_ok`/`postgres_ok` fixos em true).
    """
    return conn.execute(
        "SELECT em, workflow, mensagem FROM ("
        " SELECT w.iniciado_em AS em, COALESCE(w.workflow, w.script_legado) AS workflow,"
        "        left(COALESCE(NULLIF(w.erro, ''), 'falhou sem mensagem'), 500) AS mensagem, w.id AS n"
        "   FROM execucoes_workflow w WHERE w.status = 'erro'"
        " UNION ALL"
        " SELECT s.em, 'W00',"
        "        left(COALESCE(NULLIF((SELECT string_agg(m.motivo, '; ' ORDER BY m.i)"
        "                                FROM jsonb_array_elements_text(s.detalhes -> 'motivos')"
        "                                     WITH ORDINALITY AS m(motivo, i)), ''),"
        "                      'worker fora do contrato do /health'), 500), s.id"
        "   FROM saude s"
        "  WHERE s.worker_ok IS FALSE OR (jsonb_typeof(s.detalhes -> 'motivos') = 'array'"
        "        AND jsonb_array_length(s.detalhes -> 'motivos') > 0)"
        ") a ORDER BY em DESC, n DESC LIMIT 1").fetchone()


def orcamento_vigente(conn) -> dict | None:
    return conn.execute("SELECT id, teto_brl_dia, max_por_execucao, auto_processar, alterado_por, em"
                        " FROM orcamento WHERE vigente").fetchone()


def config_valor(conn, chave: str):
    linha = conn.execute("SELECT valor FROM configuracao WHERE chave = %s", (chave,)).fetchone()
    return linha["valor"] if linha else None


# ------------------------------------------------------------------ detalhe
def detalhe(conn, slug: str) -> dict | None:
    # O endereço direto abre mesmo fora do recorte (só a LISTA filtra), marcado. Fora do escopo, não abre.
    lic = conn.execute("SELECT c.*, %s AS no_recorte FROM v_detalhe c WHERE c.slug = %%s AND %s"
                       % (NO_RECORTE, SO_FOLHA), (slug,)).fetchone()
    if lic is None:
        return None
    lic = _sem_busca(lic)
    controle, vid, eid = lic["controle"], lic["verificacao_id"], lic["execucao_id"]
    ordem = RE_PERGUNTA_ORDEM % "x.pergunta_id"

    respostas = conn.execute(
        "SELECT x.pergunta_id, p.texto AS pergunta, p.critico, x.resposta, x.arquivo_citado,"
        " x.pagina_citada, x.trecho_literal, x.conflito, x.confianca, x.completada"
        " FROM respostas x JOIN perguntas p ON p.id = x.pergunta_id"
        " WHERE x.execucao_id = %%s ORDER BY %s" % ordem, (eid,)).fetchall() if eid else []
    vrs = conn.execute(
        "SELECT x.pergunta_id, x.veredito, x.arquivo_canonico, x.arquivo_id, x.pagina_final,"
        " x.pagina_citada, x.alertas, x.ausencia"
        " FROM verificacao_respostas x WHERE x.verificacao_id = %%s ORDER BY %s" % ordem,
        (vid,)).fetchall() if vid else []
    # O sha inteiro não interessa ao leitor e a storage_key é detalhe interno:
    # o PDF sai por /api/pdf/{slug}/{id}, nunca pelo caminho no volume.
    arquivos = conn.execute(
        "SELECT id, seq, tipo, titulo, nome, status, motivo, paginas, chars, left(sha256, 16) AS sha256,"
        " bytes, bytes_aproximado, formato_real, requer_ocr, pai_id, alias_de, baixado_em,"
        " (storage_key IS NOT NULL) AS tem_pdf"
        " FROM arquivos WHERE controle = %s ORDER BY seq NULLS LAST, id", (controle,)).fetchall()
    execucao = None
    if eid:
        execucao = conn.execute(
            "SELECT id, origem, provedor, modelo, modo, effort, lote, k_rag, rotulo, versao_prompt,"
            " chamadas, tok_entrada, tok_saida, tok_cache_escrita, tok_cache_leitura, tok_raciocinio,"
            " segundos, usd, brl, usd_brl, preco_conhecido, status, erro, canonica,"
            " procedencia_completa, brl_legado, custo_formula, reaproveitado_de, iniciado_em,"
            " finalizado_em, workflow_execucao_id FROM execucoes_modelo WHERE id = %s",
            (eid,)).fetchone()
        execucao["chamadas_modelo"] = conn.execute(
            "SELECT id, lote_ids, stop_reason, http_status, tentativas, tok_entrada, tok_saida,"
            " tok_cache_escrita, tok_cache_leitura, segundos, usd, brl, preco_conhecido, em"
            " FROM chamadas_modelo WHERE execucao_id = %s ORDER BY id", (eid,)).fetchall()
    leitura_id = lic.get("leitura_id") or lic.get("leitura_vigente_id")
    leitura = conn.execute(
        "SELECT id, preparado_em, segundos, versao_ocr, tessdata_sha256, condicoes, modo_sugerido,"
        " chars_total, procedencia_texto, vigente, assinatura_conjunto,"
        " (SELECT count(*) FROM paginas p WHERE p.leitura_id = le.id) AS n_paginas"
        " FROM leituras le WHERE id = %s", (leitura_id,)).fetchone() if leitura_id else None
    # Injeção (db/028): cada trecho escondido COM o texto e a classe, o suspeito primeiro — é o "ver mais"
    # abaixo do aviso. Sem varredura, a lista vem vazia e `furtivos_varredura` diz que não houve. PDF
    # escaneado dá um trecho por página de OCR: vai um teto, o suspeito sempre dentro (vem primeiro), e o
    # total está em `furtivos_varredura.achados`.
    furtivos = conn.execute(
        "SELECT arquivo, pagina, motivo, texto, linhas, caracteres, classe, suspeito FROM furtivos_achados"
        " WHERE leitura_id = %s ORDER BY suspeito DESC, arquivo, pagina, id LIMIT %s",
        (leitura_id, MAX_FURTIVOS_DETALHE)).fetchall() if leitura_id else []
    furtivos_varredura = conn.execute(
        "SELECT arquivos, achados, suspeitos, erro, em FROM furtivos_varreduras WHERE leitura_id = %s",
        (leitura_id,)).fetchone() if leitura_id else None
    historico = conn.execute(
        "SELECT v.id, v.execucao_id, v.versao_regras, v.verificado_em, v.aprovadas, v.revisar,"
        " v.reprovadas, v.nao_localizado, v.ancoradas, v.respondidas, v.taxa_ancorada, v.tags,"
        " v.degradada, v.vigente, v.melhor_de_n, e.origem, e.provedor, e.modelo,"
        # Um mapa Q -> veredito por verificação: o front faz o diff entre elas.
        " (SELECT jsonb_object_agg(vr.pergunta_id, vr.veredito) FROM verificacao_respostas vr"
        "   WHERE vr.verificacao_id = v.id) AS vereditos"
        " FROM verificacoes v JOIN execucoes_modelo e ON e.id = v.execucao_id"
        " WHERE v.controle = %s ORDER BY v.verificado_em DESC NULLS LAST, v.id DESC",
        (controle,)).fetchall()
    for h in historico:
        h["vereditos"] = h["vereditos"] or {}
    # Best-of-N (v3.1, db/050): o que ele decidiu na verificação
    # vigente — a que a tela mostra —, por pergunta. None = execução sem Best-of-N, ou nenhuma verificação.
    melhor_de_n = next((h["melhor_de_n"] for h in historico if h["id"] == vid), None)
    eventos = conn.execute(
        "SELECT id, de, para, motivo, dados, n8n_execution_id, em FROM licitacao_eventos"
        " WHERE controle = %s ORDER BY em, id", (controle,)).fetchall()
    gabarito = conn.execute(
        "SELECT x.pergunta_id, x.critica, x.resposta_referencia, x.fatos_obrigatorios,"
        " x.fatos_desejaveis, x.fonte FROM gabaritos x WHERE x.controle = %%s ORDER BY %s" % ordem,
        (controle,)).fetchall()
    # Só a geração vigente, como a fila e o card. As da verificação substituída continuam no banco, auditáveis.
    revisoes = conn.execute(
        "SELECT h.id, h.verificacao_id, h.pergunta_id, h.motivo, h.status, h.resposta_corrigida, h.nota,"
        " h.decidido_por, h.decidido_em, h.criado_em FROM revisoes_humanas h WHERE h.controle = %s"
        " AND " + REVISAO_DA_VIGENTE + " ORDER BY h.criado_em, h.id", (controle,)).fetchall()
    workflows = conn.execute(
        "SELECT w.id, w.workflow, w.n8n_execution_id, w.script_legado, w.gatilho, w.iniciado_em,"
        " w.duracao_s, w.status, w.erro, w.cego, " + _CUSTO_W +
        " FROM execucoes_workflow w LEFT JOIN v_execucoes_workflow_custo k"
        " ON k.workflow_execucao_id = w.id WHERE w.controle = %s ORDER BY w.iniciado_em DESC, w.id DESC",
        (controle,)).fetchall()
    # O pedido do botão "Extrair com GPT" que ainda não foi usado (db/033): o W23 o gasta ao abrir a execução. Sem
    # isto o pedido de Vale de São Domingos (edital RTF, nunca lido) ficou pendente sem ninguém ver.
    pedido_ia = conn.execute(
        "SELECT provedor, pedido_por, pedido_em, modelo, effort FROM pedidos_extracao WHERE controle = %s AND usado_em IS NULL"
        " ORDER BY id DESC LIMIT 1", (controle,)).fetchone()
    return {"licitacao": lic, "respostas": respostas, "verificacao_respostas": vrs,
            "arquivos": arquivos, "execucao": execucao, "leitura": leitura, "historico": historico,
            "eventos": eventos, "gabarito": gabarito, "revisoes": revisoes,
            "execucoes_workflow": workflows, "jev": jev_da_licitacao(conn, controle, vid),
            "furtivos": furtivos, "furtivos_varredura": furtivos_varredura, "pedido_ia": pedido_ia,
            "melhor_de_n": melhor_de_n}


def jev_da_licitacao(conn, controle: str, verificacao_id) -> dict:
    """
    `{escopo: jev_filtro | None, sustenta: {Qn: {...}}}` — o sinal de escopo
    mais recente e, por pergunta, o "sustenta?" mais recente da EXECUÇÃO da
    verificação vigente (re-verificar não muda a resposta; outra execução, sim). O veredito
    continua o do verificador: isto é o adendo, lado a lado.
    """
    escopo = conn.execute("WITH jev AS (" + JEV_ESCOPO + ") SELECT " + JEV_FILTRO + " AS f"
                          " FROM jev j WHERE j.controle = %s", (controle,)).fetchone()
    sustenta = {}
    if verificacao_id:
        linhas = conn.execute(
            # Da EXECUÇÃO da verificação vigente, não só da verificação: re-verificar (W30, regras novas)
            # não muda resposta nem trecho, e o julgamento do Jev continua valendo. Outra execução = outra
            # resposta, e não entra.
            "SELECT DISTINCT ON (s.pergunta_id) s.pergunta_id, s.p_sim::float8 AS p_sustenta, s.resposta,"
            " s.confianca::float8 AS confianca, s.contexto_enviado FROM sinais_jev s"
            " JOIN verificacoes vs ON vs.id = s.verificacao_id"
            " WHERE s.tipo = 'sustenta' AND s.pergunta_id IS NOT NULL"
            "   AND vs.execucao_id = (SELECT execucao_id FROM verificacoes WHERE id = %s)"
            " ORDER BY s.pergunta_id, s.em DESC, s.id DESC", (verificacao_id,)).fetchall()
        for x in sorted(linhas, key=lambda x: int(x["pergunta_id"][1:])):
            sustenta[x.pop("pergunta_id")] = x
    return {"escopo": escopo["f"] if escopo else None, "sustenta": sustenta}


def publicacao_vigente(conn, slug: str) -> dict | None:
    """`{controle, verificacao_id, html_uri}` (html_uri pode ser None); None = slug inexistente."""
    return conn.execute(
        "SELECT l.controle, v.id AS verificacao_id,"
        " (SELECT p.html_uri FROM publicacoes p WHERE p.verificacao_id = v.id AND p.html_uri IS NOT NULL"
        "   ORDER BY p.publicado_em DESC, p.id DESC LIMIT 1) AS html_uri"
        " FROM licitacoes l LEFT JOIN verificacoes v ON v.controle = l.controle AND v.vigente"
        " WHERE l.slug = %s AND fn_escopo_efetivo(l.controle, l.escopo_dentro)", (slug,)).fetchone()


def arquivo_do_slug(conn, slug: str, arquivo_id: int) -> dict | None:
    # O JOIN pelo slug impede servir o PDF de uma licitação sob o endereço de outra.
    return conn.execute(
        "SELECT a.id, a.nome, a.storage_key, a.status FROM arquivos a"
        " JOIN licitacoes l ON l.controle = a.controle WHERE l.slug = %s AND a.id = %s AND fn_escopo_efetivo(l.controle, l.escopo_dentro)",
        (slug, arquivo_id)).fetchone()


# ------------------------------------------------------------------ execuções e custo
# Rodada com chamadas pagas: a verdade é a soma das chamadas (view). Rodada
# sem chamada (W01, legado): o valor gravado na própria linha.
_CUSTO_W = ("CASE WHEN COALESCE(k.chamadas, 0) > 0 THEN k.custo_brl ELSE w.custo_brl END AS custo_brl,"
            " COALESCE(k.chamadas, 0) AS chamadas, COALESCE(k.sem_preco, 0) AS sem_preco")


def listar_execucoes(conn, *, workflow=None, page=1, por_pagina=50) -> dict:
    where, args = "true", []
    if workflow:
        where, args = "(w.workflow = %s OR w.script_legado = %s)", [workflow, workflow]
    total = conn.execute("SELECT count(*) AS n FROM execucoes_workflow w WHERE " + where, args).fetchone()["n"]
    itens = conn.execute(
        "SELECT w.id, w.workflow, w.n8n_execution_id, w.script_legado, w.gatilho, w.iniciado_em,"
        " w.duracao_s, w.argumentos, w.contadores, w.cego, w.status, w.erro, w.controle, " + _CUSTO_W + ","
        " (SELECT count(*) FROM buscas b WHERE b.workflow_execucao_id = w.id) AS n_buscas,"
        " (SELECT min(b.cobertura_pct) FROM buscas b WHERE b.workflow_execucao_id = w.id) AS cobertura_min,"
        " (SELECT count(*) FROM buscas b WHERE b.workflow_execucao_id = w.id AND b.falhou) AS buscas_falhas"
        " FROM execucoes_workflow w LEFT JOIN v_execucoes_workflow_custo k ON k.workflow_execucao_id = w.id"
        " WHERE " + where + " ORDER BY w.iniciado_em DESC, w.id DESC LIMIT %s OFFSET %s",
        args + [por_pagina, (page - 1) * por_pagina]).fetchall()
    return {"total": total, "page": page, "por_pagina": por_pagina,
            "paginas": (total + por_pagina - 1) // por_pagina, "itens": itens}


def execucao(conn, wid: int) -> dict | None:
    w = conn.execute(
        "SELECT w.id, w.workflow, w.n8n_execution_id, w.script_legado, w.gatilho, w.iniciado_em,"
        " w.duracao_s, w.argumentos, w.contadores, w.cego, w.status, w.erro, w.controle,"
        " w.custo_brl AS custo_brl_gravado, " + _CUSTO_W + " FROM execucoes_workflow w"
        " LEFT JOIN v_execucoes_workflow_custo k ON k.workflow_execucao_id = w.id WHERE w.id = %s",
        (wid,)).fetchone()
    if w is None:
        return None
    buscas = conn.execute(
        "SELECT id, termo, paginas_lidas, total_declarado, lidos, cobertura_pct, teto_atingido,"
        " falhou, pagina_falha, em FROM buscas WHERE workflow_execucao_id = %s ORDER BY id",
        (wid,)).fetchall()
    # Página a página (ADR-007): o que foi lido antes de um 429 continua visível.
    paginas = conn.execute(
        "SELECT termo, pagina, status, falhou, motivo, em, jsonb_array_length("
        " CASE WHEN jsonb_typeof(itens) = 'array' THEN itens ELSE '[]'::jsonb END) AS n_itens"
        " FROM buscas_paginas WHERE workflow_execucao_id = %s ORDER BY termo, pagina", (wid,)).fetchall()
    modelos = conn.execute(
        "SELECT e.id, e.controle, l.slug, e.origem, e.provedor, e.modelo, e.status, e.brl,"
        " e.preco_conhecido, e.iniciado_em, e.finalizado_em FROM execucoes_modelo e"
        " JOIN licitacoes l ON l.controle = e.controle WHERE e.workflow_execucao_id = %s ORDER BY e.id",
        (wid,)).fetchall()
    return {"execucao": w, "buscas": buscas, "buscas_paginas": paginas, "execucoes_modelo": modelos}


def custo(conn) -> dict:
    por_dia = conn.execute("SELECT dia, brl, usd, chamadas, sem_preco FROM gasto_diario"
                           " ORDER BY dia DESC LIMIT 90").fetchall()
    por_modelo = conn.execute(
        "SELECT origem, provedor, modelo, count(*) AS execucoes, sum(brl) AS brl,"
        " sum(brl_legado) AS brl_legado,"
        " count(*) FILTER (WHERE brl IS NULL AND brl_legado IS NULL) AS sem_preco"
        " FROM execucoes_modelo GROUP BY 1, 2, 3 ORDER BY 1, 2, 3").fetchall()
    hoje = conn.execute("SELECT brl, chamadas, sem_preco FROM gasto_diario"
                        " WHERE dia = (now() AT TIME ZONE 'America/Sao_Paulo')::date").fetchone()
    if hoje is None:
        hoje_brl, hoje_sem_preco = 0, 0              # nenhuma chamada hoje: R$ 0 é verdade
    else:
        hoje_sem_preco = hoje["sem_preco"]
        # Só chamada sem preço no dia: a view soma 0 e o painel diria "R$ 0,00"
        # — o defeito que o ADR-012 proíbe. null = "sem preço", ao lado da contagem.
        so_sem_preco = hoje["chamadas"] > 0 and hoje["sem_preco"] == hoje["chamadas"]
        hoje_brl = None if so_sem_preco else hoje["brl"]
    orc = orcamento_vigente(conn) or {}
    return {"por_dia": por_dia, "por_modelo": por_modelo, "hoje_brl": hoje_brl,
            "hoje_sem_preco": hoje_sem_preco,
            "teto_brl_dia": orc.get("teto_brl_dia"), "auto_processar": orc.get("auto_processar")}


# Os gastos com IA da home, na
# ordem em que aparecem. O que cada fonte é está em db/045.
GASTOS_IA = (("jev", "Jev (TypeSafe)"), ("anthropic", "Claude (Anthropic)"), ("openai", "GPT (OpenAI)"))


def gastos_ia(conn) -> dict:
    """
    O gasto de cada provedor de IA, e a soma. OpenAI e Anthropic: a leitura mais recente da fatura (Admin API,
    scripts/82). Jev: a última leitura do painel da TypeSafe mais o que o sistema mediu depois dela (sinais_jev.usd);
    sem leitura do painel, só o medido. Provedor sem leitura nenhuma fica `usd: null` e vai em `sem_leitura` — nunca
    US$ 0 (ADR-012).
    """
    from fopa import modelos

    ultimas = {r["provedor"]: r for r in conn.execute(
        "SELECT DISTINCT ON (provedor) provedor, usd::float8 AS usd, desde, fonte, lido_em FROM gastos_ia"
        " ORDER BY provedor, lido_em DESC").fetchall()}
    provedores = []
    for chave, rotulo in GASTOS_IA:
        u = ultimas.get(chave)
        item = {"provedor": chave, "rotulo": rotulo, "usd": u["usd"] if u else None,
                "fonte": u["fonte"] if u else None, "desde": u["desde"] if u else None,
                "lido_em": u["lido_em"] if u else None}
        if chave == "jev":
            m = conn.execute("SELECT sum(usd)::float8 AS usd, min(em)::date AS desde, max(em) AS ate FROM sinais_jev"
                             " WHERE usd IS NOT NULL AND em > %s",
                             (u["lido_em"] if u else date(1970, 1, 1),)).fetchone()
            if u:
                item["medido_depois_usd"] = m["usd"] or 0.0
                item["usd"] = round(u["usd"] + item["medido_depois_usd"], 4)
            elif m["usd"] is not None:
                item.update(usd=m["usd"], fonte="medido", desde=m["desde"], lido_em=m["ate"])
        provedores.append(item)
    total = sum(p["usd"] for p in provedores if p["usd"] is not None)
    lidos = [p for p in provedores if p["usd"] is not None]
    return {"provedores": provedores,
            "total_usd": round(total, 4) if lidos else None,
            "total_brl": round(total * modelos.USD_BRL, 2) if lidos else None,
            "usd_brl": modelos.USD_BRL,
            "sem_leitura": [p["provedor"] for p in provedores if p["usd"] is None]}


def listar_emails(conn, *, tipo=None, status=None, page=1, por_pagina=50) -> dict:
    where, args = ["true"], []
    if tipo:
        where.append("m.tipo = %s")
        args.append(tipo)
    if status:
        where.append("m.status = %s")
        args.append(status)
    cond = " AND ".join(where)
    total = conn.execute("SELECT count(*) AS n FROM emails m WHERE " + cond, args).fetchone()["n"]
    itens = conn.execute(
        "SELECT m.id, m.tipo, m.controle, l.slug, m.assunto, m.corpo_html, m.status, m.canal,"
        " m.tentativas, m.enviado_em, m.erro, m.em,"
        # o destinatário que o W50 usa (db/038): o da linha (a extração vai para quem pediu) ou os admins ativos
        " COALESCE(m.para, (SELECT string_agg(u.email, ',' ORDER BY u.email) FROM usuarios u"
        "                   WHERE u.papel = 'admin' AND u.ativo)) AS para FROM emails m"
        " LEFT JOIN licitacoes l ON l.controle = m.controle WHERE " + cond +
        " ORDER BY m.em DESC, m.id DESC LIMIT %s OFFSET %s",
        args + [por_pagina, (page - 1) * por_pagina]).fetchall()
    return {"total": total, "page": page, "por_pagina": por_pagina,
            "paginas": (total + por_pagina - 1) // por_pagina, "itens": itens}


# ------------------------------------------------------------------ revisão
# A fila é a da verificação VIGENTE (ou revisão sem verificação). Cada W30 cria verificação nova e o W24 reabre a
# revisão da mesma pergunta: em 24/09 eram 2.936 abertas para 1.542 perguntas, 1.532 presas a verificação já
# substituída — e 140 da tag de injeção que a regra nova não dá mais. As antigas ficam no banco, abertas.
REVISAO_DA_VIGENTE = ("(h.verificacao_id IS NULL OR EXISTS (SELECT 1 FROM verificacoes vv"
                      " WHERE vv.id = h.verificacao_id AND vv.vigente))")


# A busca da fila é a do painel (a coluna `busca` da view de cards, db/029): município, UF, modalidade, controle,
# órgão, objeto e rótulo, em minúsculas.
BUSCA_LICITACAO = "lower(concat_ws(' ', l.municipio, l.uf, l.modalidade, l.controle, l.orgao, l.objeto, l.rotulo))"


BUSCA_LICITACAO_LIKE = " AND " + BUSCA_LICITACAO + r" LIKE %s ESCAPE '\'"
FILA_LIMITE_LICITACOES = 50


def licitacoes_em_revisao(conn, q: str | None = None) -> dict:
    """
    A lista LEVE da revisão: os totais
    sempre; as licitações com revisão aberta na vigente só com busca — até 50, com quantos campos cada uma tem (e
    quantos críticos). A que ainda está aberta vem primeiro, a de prazo mais perto na frente; depois a mais recente.
    """
    base = ("FROM revisoes_humanas h JOIN licitacoes l ON l.controle = h.controle"
            " WHERE h.status = 'aberta' AND " + REVISAO_DA_VIGENTE)
    tot = conn.execute("SELECT count(*) AS revisoes, count(DISTINCT h.controle) AS licitacoes " + base).fetchone()
    saida = {"total_revisoes": tot["revisoes"], "total_licitacoes": tot["licitacoes"],
             "encontradas": tot["licitacoes"], "itens": []}
    if not (q and q.strip()):
        return saida
    args = [_like(q)]
    saida["encontradas"] = conn.execute("SELECT count(DISTINCT h.controle) AS n " + base + BUSCA_LICITACAO_LIKE,
                                        args).fetchone()["n"]
    saida["itens"] = conn.execute(
        "SELECT l.controle, l.slug, l.orgao, l.uf, l.municipio, l.modalidade, l.fim_prazo,"
        " count(*) AS abertas, count(*) FILTER (WHERE p.critico) AS criticas"
        " FROM revisoes_humanas h JOIN licitacoes l ON l.controle = h.controle"
        " LEFT JOIN perguntas p ON p.id = h.pergunta_id"
        " WHERE h.status = 'aberta' AND " + REVISAO_DA_VIGENTE + BUSCA_LICITACAO_LIKE +
        " GROUP BY l.controle, l.slug, l.orgao, l.uf, l.municipio, l.modalidade, l.fim_prazo"
        " ORDER BY (l.fim_prazo >= now()) DESC NULLS LAST, CASE WHEN l.fim_prazo >= now() THEN l.fim_prazo END,"
        " l.fim_prazo DESC NULLS LAST, l.controle LIMIT %s", args + [FILA_LIMITE_LICITACOES]).fetchall()
    return saida


def fila_revisao(conn, q: str | None = None, controle: str | None = None) -> list[dict]:
    """Os campos em revisão: os de UMA licitação (`controle`, o clique na lista leve) ou os que a busca acha."""
    busca, args = "", []
    if controle:
        busca, args = " AND h.controle = %s", [controle]
    elif q and q.strip():
        busca, args = BUSCA_LICITACAO_LIKE, [_like(q)]
    return conn.execute(
        "SELECT h.id, h.controle, l.slug, l.orgao, l.uf, l.municipio, l.fim_prazo, h.verificacao_id,"
        " h.pergunta_id, p.texto AS pergunta, p.critico, h.motivo, h.criado_em,"
        " vr.veredito, vr.alertas, vr.arquivo_id, vr.pagina_final, vr.ausencia,"
        " r.resposta, r.arquivo_citado, r.pagina_citada, r.trecho_literal, r.conflito"
        " FROM revisoes_humanas h JOIN licitacoes l ON l.controle = h.controle"
        " LEFT JOIN perguntas p ON p.id = h.pergunta_id"
        " LEFT JOIN verificacoes v ON v.id = h.verificacao_id"
        " LEFT JOIN verificacao_respostas vr ON vr.verificacao_id = h.verificacao_id"
        "   AND vr.pergunta_id = h.pergunta_id"
        " LEFT JOIN respostas r ON r.execucao_id = v.execucao_id AND r.pergunta_id = h.pergunta_id"
        " WHERE h.status = 'aberta' AND " + REVISAO_DA_VIGENTE + busca +
        " ORDER BY l.fim_prazo NULLS LAST, h.criado_em, h.id", args).fetchall()


def rotulos_escopo(conn) -> dict:
    """
    Aba "escopo" da revisão: primeiro as CANDIDATAS do Jev ainda sem rótulo
    (o sinal de escopo mais recente tem `candidata`: discordou da regra com
    convicção), a de menor p_filtro_ok primeiro; depois as já rotuladas, o
    rótulo mais novo primeiro. Rótulo = o mais recente de `rotulos_escopo`.
    Candidata num sinal VELHO que o mais recente desmentiu não entra: a fila
    mostra o mesmo `jev_filtro` que o card.
    """
    itens = conn.execute(
        "WITH jev AS (" + JEV_ESCOPO + "),"
        " rot AS (SELECT DISTINCT ON (controle) controle, veredito, por_que, por, em"
        "         FROM rotulos_escopo ORDER BY controle, em DESC, id DESC)"
        " SELECT c.controle, c.slug, c.orgao, c.uf, c.municipio, c.modalidade, c.objeto, c.fim_prazo,"
        " c.estado, c.escopo_dentro, c.escopo_motivo, c.escopo_versao, " + JEV_FILTRO + " AS jev_filtro,"
        " (r.controle IS NOT NULL) AS rotulada, r.veredito, r.por_que, r.por, r.em AS rotulo_em"
        " FROM licitacoes c LEFT JOIN jev j ON j.controle = c.controle"
        " LEFT JOIN rot r ON r.controle = c.controle"
        " WHERE r.controle IS NOT NULL OR j.candidata"
        " ORDER BY (r.controle IS NOT NULL), CASE WHEN r.controle IS NULL THEN j.p_filtro_ok END NULLS LAST,"
        " r.em DESC NULLS LAST, c.controle").fetchall()
    for x in itens:
        rotulada, veredito = x.pop("rotulada"), x.pop("veredito")
        motivo, por, em = x.pop("por_que"), x.pop("por"), x.pop("rotulo_em")
        x["rotulo"] = ({"dentro": veredito == "dentro", "motivo": motivo, "por": por, "em": em}
                       if rotulada else None)
    pendentes = sum(1 for x in itens if x["rotulo"] is None)
    return {"itens": itens, "pendentes": pendentes, "rotuladas": len(itens) - pendentes}


__all__ = ["ESTADOS", "FILTROS", "RECORTES", "SITUACOES", "VENCIMENTOS", "cond_vence_em", "listar_licitacoes",
           "resumo", "ultima_coleta",
           "ultimo_alerta", "detalhe", "jev_da_licitacao", "publicacao_vigente", "arquivo_do_slug",
           "listar_execucoes", "execucao", "custo", "listar_emails", "fila_revisao", "rotulos_escopo",
           "orcamento_vigente", "config_valor"]
