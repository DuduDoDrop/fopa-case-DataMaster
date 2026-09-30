# -*- coding: utf-8 -*-
"""
Ajuste da regra de escopo — os falsos positivos resolvidos já no filtro (25/09/2026).

A regra de escopo (`scripts/fopa/escopo.py`, ADR-003) fica como está: não se mexe nela. Esta camada
roda DEPOIS dela e só pode tirar do escopo o que ela aceitou — nunca pôr para dentro. Cada exclusão tem nome e vira
o motivo gravado, e o texto deste arquivo entra na `escopo_versao` (api/versao.py): mudar uma linha aqui reavalia o
acervo pelo caminho de sempre.

DE ONDE VIERAM OS PADRÕES (25/09): os 27 rótulos humanos "fora" em que a regra dizia dentro e os 57 casos em que a
regra diz dentro e o Jev (v3.1) recusa com convicção — sistemas e TI de folha, empresa de RH/contabilidade que
"processa a folha", tarifas bancárias que o órgão paga, termo de fomento, compra de bens "para a folha", obra
("folhas de brasilit"), recrutamento de temporários, recuperação de imposto, estudo técnico, eventos sobre folha.

A GUARDA: qualquer sinal de folha de banco (instituição financeira, cessão onerosa, exclusividade, pagamento da
folha, créditos da folha, credenciamento de instituição, nomes de bancos) e as exclusões BRANDAS não valem — "Contratação de instituição financeira para processamento e gerenciamento de créditos provenientes da folha"
é folha, mesmo com o Jev em 0,25. As DURAS são frases exatas que folha de banco não diz: o objeto que COMEÇA com
"Despesas com tarifas bancárias", e "exceto folha". A 1ª versão (mais dura) tiraria 12 folhas publicadas (80_).

Medido em scripts/80_escopo_ajuste.py antes de entrar.
"""
from __future__ import annotations

import re
import unicodedata

VERSAO = "ajuste-1"


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", t).lower()


# A GUARDA: qualquer sinal de folha de banco protege das exclusões BRANDAS (a 1ª versão, com só "banco E folha",
# tiraria 12 folhas publicadas: "cessão onerosa do direito de pagamento da folha" não cita banco).
# Sem nomes de banco: "certidões federais e Caixa Econômica" (serviço de RH) passava por folha; a folha de verdade
# sempre traz outro sinal daqui. E `\bcessao`: "con-cessão onerosa do canal de consignações" casava com "cessão".
PROTEGE = re.compile(
    r"instituic(ao|oes) (financeira|bancaria)|\bbancos?\b|cooperativas? de credito|servicos? bancari"
    r"|servicos financeiros|\bcessao onerosa|convenio com (a |o )?(caixa|banco)"
    r"|exclusividade|pagamento d[ao]s? (valores (liquidos )?d[ao]s? )?folha|folha salarial"
    r"|creditos (provenientes|oriundos|decorrentes) d|processamento (e gerenciamento )?d[eo]s? (creditos|pagamentos)"
    r"|centraliza(cao|r) (e process|d[ao]s? (creditos|folha|pagamento))|credenci(amento|ar) (de )?(instituic|banc)")

# (nome, padrão, dura?) — dura vale mesmo com a guarda: só frases exatas, que folha de banco não diz.
EXCLUSOES = [
    ("tarifa paga pelo órgão", re.compile(r"^\W*(\[[^\]]*\]\s*-\s*)?(despesas?|pagamento) (com|de) tarifas? bancari"), True),
    ("exceto folha", re.compile(r"exceto (a )?folha"), True),
    # APAE e Pestalozzi "com pagamento da folha da equipe": a parceria (Lei 13.019) nunca é folha de banco
    ("termo de fomento ou parceria", re.compile(r"termo de fomento|termo de colaboracao|lei 13\.?019|mutua cooperacao"
                                                r"|organizac(ao|oes) da sociedade civil"), True),
    # o imóvel "destinado ... à centralização das folhas de pagamento": o objeto COMEÇA com a locação
    ("locação de imóvel", re.compile(r"^\W*(\[[^\]]*\]\s*-\s*)?(locacao|aluguel) de (um )?imovel"), True),
    # "recrutamento, seleção, contratação, pagamento da folha ... de jovens" (entidade de aprendizagem)
    ("recrutamento ou temporários", re.compile(r"recrutamento|selecao de pessoal|agenciamento de estag"
                                               r"|profissionais temporarios|mao de obra temporaria|jovem aprendiz"), True),
    ("recuperação de imposto", re.compile(r"recuperacao de (imposto|tributo|credito tributario|iss)"), True),
    ("estudo técnico sobre a folha", re.compile(
        r"^\W*(\[[^\]]*\]\s*-\s*)?contratacao de (servicos|empresa) (especializad[ao]s? )?(de|em|para) "
        r"(elaboracao de )?estudo tecnico"), True),
    ("estudo ou consultoria sobre a folha", re.compile(r"estudo tecnico|viabilidade economic|consultoria|valuation"), False),
    ("obra ou manutenção predial", re.compile(r"telhad|brasilit|\bcalhas?\b|\breforma (d|e)|construcao de|\bobras? de\b"), False),
    ("compra de bens", re.compile(r"^\W*(aquisicao|compra) de (?!servic)"), False),
    ("sistema ou TI de folha", re.compile(
        r"\bsistemas? (de|do|da|para) (informatica|informacao|folha|processamento|gestao|recursos humanos)"
        r"|licenciamento de uso|licenca de uso|\bsoftware|locacao (e manutencao )?(de|do) sistema"
        r"|arrendamento (e manutencao )?(de|do|dos) sistema|tecnologia da informacao|servicos de informatica"
        r"|execucao de sistemas|\bprodam\b|\bprodesp\b|business intelligence|plataforma (modular|integrada|web)"
        r"|implantacao,? (locacao )?(e )?(manutencao )?(de|do) sistema|operacionalizacao (de|do) sistema"
        r"|gerenciamento do si[s]?tema|fornecimento de sistema"), False),
    ("serviço de RH ou contábil", re.compile(
        r"escritorio de contabilidade|assessor(ia|amento)|apoio (administrativo|operacional)"
        r"|rotinas de (pessoal|recursos humanos)|area de recursos humanos|e-?social|\bgfip\b|\bsefip\b|\bsagres\b|\bdctf"
        r"|obrigacoes acessorias|reprocessamento de folha|elaboracao (e processamento )?d[ae] folha|calculo d[ae] folha"
        r"|empresa (ou pessoa fisica )?especializada (na|em|no|para) (a )?(prestacao de servicos (tecnicos )?(de|na|no) )?"
        r"(processamento|elaboracao|gestao|gerenciamento)"), False),
    ("apoio a APAE ou associação", re.compile(r"associacao de pais|\bapae\b|pestalozzi"), False),
    ("evento ou curso sobre folha", re.compile(r"inscric(ao|oes)|encontro nacional|congresso|seminario|\bcurso\b"
                                               r"|capacitacao|treinamento"), False),
    ("pesquisa e desenvolvimento", re.compile(r"pesquisa e desenvolvimento"), False),
    ("só o canal de consignações", re.compile(r"canal de consignac|consignataria facultativa"), False),
]


def excluir(texto: str) -> str | None:
    """O nome da exclusão que vale para este texto, ou None."""
    t = _norm(texto)
    protegido = bool(PROTEGE.search(t))
    for nome, padrao, dura in EXCLUSOES:
        if padrao.search(t) and (dura or not protegido):
            return nome
    return None


def ajustar(texto: str, dentro: bool, motivo: str) -> tuple[bool, str]:
    """Depois da regra: só tira do escopo (nunca põe), e diz por quê."""
    if not dentro:
        return dentro, motivo
    nome = excluir(texto)
    if nome is None:
        return dentro, motivo
    return False, "fora (%s: %s) — a regra dizia: %s" % (VERSAO, nome, motivo)


def avaliar(texto: str) -> tuple[bool, str]:
    """A regra de escopo (ADR-003) e depois este ajuste — o que os quatro lugares da regra chamam: o /escopo do worker
    (W01), a reavaliação do acervo, a descoberta histórica e a "regra" que o Jev contesta."""
    from fopa import escopo as escopo_mod
    return ajustar(texto or "", *escopo_mod.avaliar(texto or ""))


__all__ = ["VERSAO", "excluir", "ajustar", "avaliar"]
