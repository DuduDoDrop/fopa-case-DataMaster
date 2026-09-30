# -*- coding: utf-8 -*-
"""
O que é, e o que NÃO é, uma licitação de folha de pagamento.

Este é o portão mais barato do pipeline e o mais fácil de errar. Cada objeto que
passa indevidamente custa uma extração inteira — e produz um relatório com
metade das 17 perguntas em branco, porque as perguntas não cabem num edital que
não é de folha.

O CRITÉRIO, TIRADO DOS DOCUMENTOS
Não de intuição: das 13 licitações reais da amostra. Doze são do escopo, e as
doze nomeiam QUEM É CONTRATADO como instituição financeira, banco ou cooperativa
de crédito — ou declaram cessão onerosa da folha:

    Pirapó          "instituição financeira publica ou privada e/ou cooperativa"
    Adrianópolis    "instituição financeira, pública ou privada"
    Fruta de Leite  "instituição financeira autorizada a funcionar pelo BACEN"
    São Lourenço    "instituição financeira pública ou privada, ou cooperativa"
    Rio Branco      "instituição financeira oficial"
    Jaboatão        "Instituição Credenciada Banco Bradesco"
    Bertioga        "cessão onerosa ... da folha de pagamento"
    Quevedos        "cessão onerosa do direito de realizar ... o pagamento da folha"
    Capão do Cipó   "cessão onerosa do direito de efetuar o pagamento da folha"

A décima terceira, Rio Azul/PR, é a única que diz:

    "CONTRATAÇÃO DE EMPRESA PARA PRESTAÇÃO DE SERVIÇOS DE IMPLANTAÇÃO E GESTÃO
     DE CONSIGNAÇÕES FACULTATIVAS EM FOLHA DE PAGAMENTO"

É terceirização de um serviço ligado à folha, não a compra da folha. Entrou na
amostra, custou uma extração e voltou com 6 de 17 em branco — sintoma correto de
um edital que não tem pirâmide salarial porque não precisa ter.

A DISTINÇÃO QUE ORGANIZA TUDO
Numa cessão de folha, o Município **recebe** dinheiro de um banco. Numa
terceirização, o Município **paga** uma empresa. São fluxos financeiros opostos,
e o objeto quase sempre denuncia qual é pelo tipo de contratado que nomeia.
"""
from __future__ import annotations

import re
import unicodedata

# O objeto precisa ser a FOLHA, não qualquer coisa que a mencione de passagem.
# "folha de servidores" (Capão do Cipó/RS) não casava com "folha DOS servidores":
# uma preposição derrubava uma licitação do escopo. A suíte pegou.
RE_FOLHA = re.compile(
    # PLURAL, NUMERO NO MEIO, E OS SINONIMOS DE "pagamento".
    #
    # Medido em 23/09/2026 lendo os 239 objetos que o filtro REJEITOU: cinco
    # eram folha de verdade, e a causa era sempre esta linha.
    #
    #   Vinhedo/SP   "CREDITOS DAS FOLHAS DE PAGAMENTO"   -> plural
    #   Vacaria/RS   "folha dos 2.210 servidores"         -> numero no meio
    #   Pontao/RS    "folha de remuneracao"               -> substantivo novo
    #
    # Sao Luiz do Paraitinga ("FOLHA DE VENCIMENTOS") e Rio de Janeiro
    # ("folha de pagamento" numa contratacao de contabilidade) passam a CASAR
    # aqui e continuam barrados pelas exclusoes, que e onde a decisao
    # pertence. Este regex responde "fala da folha?", nao "e a operacao dela?".
    r"folhas?\s+d[eoa]s?\s+(?:[\d.,]+\s+)?"
    # `pagamen` e não `pagamento`: o PNCP corta o objeto no meio da palavra
    # ("FOLHA DE PAGAMENT", Barra do Garças; "FOLHA DE PAGAMEN", Itu). Jev v3,
    # 24/09/2026. `benef[íi]cio`: a folha de benefícios do RPPS (Três Corações).
    r"(?:pagamen|sal[áa]rio|servidor|servidores|pessoal|funcion[áa]rio|"
    r"empregado|remunera[çc][ãa]o|vencimento|provento|pagto|benef[íi]cio)"
    r"|folhas?\s+salarial"
    # Jev v3 no W01: "gerenciamento folha pagamento servidores" (José de
    # Freitas 21/2026) — o objeto telegráfico, sem o "de".
    r"|folhas?\s+pagamen"
    r"|folhas?\s+de\s+pagto", re.I)

# A FOLHA DESCRITA SEM A PALAVRA "FOLHA".
#
# Duas licitacoes do acervo nunca dizem "folha" e sao folha do mesmo jeito:
#
#   Camacari/BA         "instituicao financeira ... para o pagamento de
#                        remuneracao proventos e beneficios de empregados"
#   Campo Belo do Sul   "instituicao Financeira ... prestacao de servicos de
#                        Pagamento, com exclusividade, de vencimentos e
#                        salarios dos servidores ativos, inativos ..."
#
# As duas pontas sao obrigatorias e e isso que segura o falso positivo: sem o
# VERBO de operacao vira qualquer mencao a salario; sem "dos servidores" pega
# pagamento a fornecedor. Medido contra os 416 objetos do corpus -- alcanca
# exatamente essas duas e mais nenhuma.
#
# Isto NAO decide escopo. So abre o portao para que as exclusoes por produto
# (consignado, consultoria, sistema) possam opinar, que e onde a decisao mora.
RE_FOLHA_SEM_A_PALAVRA = re.compile(
    r"(?:pagamento|creditamento|cr[ée]dito|processamento|centraliza[çc][ãa]o)"
    r"[^.;]{0,80}?"
    r"(?:vencimento|sal[áa]rio|remunera[çc][ãa]o|provento|subs[íi]dio|"
    r"vantagem|pens[ãa]o)"
    r"[^.;]{0,120}?"
    r"(?:servidor|empregado|funcion[áa]rio|agente[s]?\s+p[úu]blico|pensionista)",
    re.I)

# PAGAR OS SERVIDORES, dito sem "folha" (Jev v3, 24/09/2026).
#
#   Maravilhas/MG  "instituição financeira, com exclusividade, para prestação
#                   dos serviços de pagamento dos servidores municipais"
#   Cajuri/MG      "serviços bancários ... necessários ao pagamento de salários"
#   Itabuna/BA     "operacionalização do pagamento de vencimentos, salários"
#
# O lookbehind segura o consignado: ele diz "desconto em folha de pagamento DOS
# SERVIDORES" — "pagamento dos servidores" precedido de "folha de" não conta.
RE_PAGAR_SERVIDORES = re.compile(
    r"(?<!folha de )(?<!folhas de )(?<!folha\sde\s)(?<!folha )(?<!folhas )"
    r"\bpagamento\s+d[eoa]s?\s+(?:[\w-]+\s*,?\s+){0,3}?"
    r"(?:sal[áa]rios?|vencimentos?|remunera[çc](?:[ãa]o|[õo]es)|proventos?|"
    r"servidores|funcion[áa]rios|empregados)\b", re.I)

# O BANCO É O CONTRATADO — dito no começo do objeto. Quando o objeto ABRE
# contratando instituição financeira e descreve a operação da folha, "plataforma
# eletrônica para transmissão dos arquivos" (José de Freitas) e "suporte
# técnico-operacional à integração dos sistemas" (Ponte Serrada) são peças do
# serviço do banco, não o que se contrata. Consultoria e EVEF abrem contratando
# EMPRESA, e continuam fora.
RE_BANCO_NO_INICIO = re.compile(
    r"^[^.;]{0,90}?(?:institui[çc][ãa]o\s+(?:financeira|banc[áa]ria)|cooperativa\s+de\s+cr[ée]dito)",
    re.I)

# ------------------------------------------------------------------ fora
#
# Estas exclusões vêm PRIMEIRO e são decisivas, independentemente de quem é
# contratado. É a correção que 393 objetos reais impuseram: a primeira versão
# perguntava "empresa ou instituição financeira?", e isso descartava
# Carapicuíba/SP — "prestação de serviço de PAGAMENTO DE FOLHA DE SALÁRIO dos
# servidores ativos e aposentados" —, que é exatamente a operação procurada.
#
# O discriminador certo não é QUEM se contrata, é O QUE se contrata: operar a
# folha, ou vender um serviço de consignado em volta dela.
# "emprestimo PESSOAL consignado" (Uberlandia/MG) nao casava com
# "emprestimo consignado": uma palavra no meio. Como o portao `forte`
# protege quem opera a folha de verdade, o padrao pode ser amplo aqui —
# qualquer forma de "consignado" conta como sinal.
RE_CONSIGNADO = re.compile(
    r"consigna[çc][ãa]o|consigna[çc][õo]es|consignat[áa]ri|"
    r"consignad[oa]s?|margem\s+consign|averba[çc][ãa]o|"
    # ADR-015: Macaé credencia "empréstimo pessoal, compra de dívida ...
    # mediante desconto em folha" — é crédito ao servidor, sem dizer "consignado".
    r"empr[ée]stimo\s+pessoal|compra\s+de\s+d[íi]vida|desconto\s+em\s+folha", re.I)

RE_SISTEMA = re.compile(
    r"software|sistema\s+(?:digital|informatizad|integrad|de\s+gest[ãa]o|web)|"
    r"solu[çc][ãa]o\s+(?:informatizada|tecnol[óo]gica|digital)|"
    r"plataforma\s+(?:tecnol[óo]gica|web|digital|eletr[ôo]nica)|"
    r"licen[çc]a\s+de\s+uso|loca[çc][ãa]o\s+de\s+sistema|"
    r"cess[ãa]o\s+de\s+(?:uso\s+de\s+)?software|"
    # ADR-015: informática SOBRE a folha — migração de base (Fortim, Russas),
    # backup (SASSOM Franca), "banco de dados dos servidores" (Cametá) e
    # "cessão onerosa de SISTEMA de folha" (Serranos), que é software alugado,
    # não a folha cedida ao banco.
    r"migra[çc][ãa]o\s+de\s+dados|banco\s+de\s+dados|\bbackups?\b|"
    r"cess[ãa]o\s+(?:onerosa\s+)?de\s+sistema", re.I)

RE_OUTRO_SERVICO = re.compile(
    r"consultoria|assessoria|auditoria|suporte\s+t[ée]cnico|"
    r"escritura[çc][ãa]o|servi[çc]os?\s+(?:continuados\s+)?de\s+contabilidade|"
    r"treinamento|capacita[çc][ãa]o|\bcursos?\b|palestra|"
    r"estudo\s+de\s+viabilidade|\bEVEF\b|"
    # ADR-015: Açailândia contrata a "realização de Estudo Técnico Preliminar,
    # para estimar o melhor valor" da folha — o EVEF com outro nome.
    r"(?:realiza[çc][ãa]o|elabora[çc][ãa]o)\s+de\s+estudo|"
    r"vale[-\s]?(?:alimenta|refei|transporte)|"
    r"plano\s+de\s+sa[úu]de|seguro\s+de\s+vida|"
    # Jev v3 (24/09/2026): Confins contrata manutenção do PONTO ELETRÔNICO (a
    # folha aparece como consequência); Deodápolis, uma empresa que gere o
    # PROGRAMA DE ESTÁGIO (inclui "gestão de folha" das bolsas).
    r"ponto\s+eletr[ôo]nico|manuten[çc][ãa]o\s+(?:preventiva|corretiva)|"
    r"programa\s+de\s+est[áa]gio|agente\s+de\s+integra[çc][ãa]o|"
    r"c[áa]lculo\s+(?:e\s+\w+\s+)?d[ae]\s+folha", re.I)

# O núcleo do RE_OUTRO_SERVICO que NUNCA é peça do serviço do banco: vender
# trabalho intelectual ao órgão sobre a folha. "Suporte técnico" e "curso"
# podem ser acessórios da operação; consultoria, auditoria e estudo, não.
RE_ESTUDO_OU_CONSULTORIA = re.compile(
    r"consultoria|assessoria|auditoria|estudo\s+de\s+viabilidade|\bEVEF\b|"
    r"(?:realiza[çc][ãa]o|elabora[çc][ãa]o)\s+de\s+estudo|escritura[çc][ãa]o|"
    r"servi[çc]os?\s+(?:continuados\s+)?de\s+contabilidade|c[áa]lculo\s+(?:e\s+\w+\s+)?d[ae]\s+folha|"
    # Jev v3 (24/09/2026): Criciúma contrata "lançamentos contábeis" que incluem a
    # liquidação da folha; Sangão, "elaboração da parametrização e elaboração da folha".
    r"lan[çc]amentos?\s+cont[áa]beis|elabora[çc][ãa]o\s+(?:d[ao]s?\s+)?(?:folha|parametriza)|parametriza[çc][ãa]o|"
    # Jev v3: o CRPRS contrata "empresa de contabilidade ... para terceirização da
    # operacionalização da folha e departamento pessoal" — terceirizar o DP.
    r"empresa\s+de\s+contabilidade|departamento\s+(?:de\s+)?pessoal|"
    # Jev v3 no W01: Jaraguá do Sul contrata "gestão de Recursos Humanos, processamento
    # de folha de pagamento e apoio fiscal e tributário" — RH terceirizado.
    r"gest[ãa]o\s+de\s+recursos\s+humanos|apoio\s+fiscal", re.I)

# SERVIÇO BANCÁRIO QUE O ÓRGÃO PAGA — o contrário de vender a folha.
#
# ADR-015 (24/09/2026): Aguanil e Diorama contratam o banco para cobrar
# TARIFAS; Santa Cruz do Sul, para "envio/retorno de arquivos" de pagamento;
# a Câmara de Barra do Quaraí, uma conta institucional "exceto pagamento de
# despesas decorrentes da folha". Todas nomeiam instituição financeira e três
# descrevem "processamento da folha" — e em nenhuma o banco compra nada: é o
# órgão que paga pelo serviço. Quem quer COMPRAR a folha não tem lance aqui.
# Decisivo, salvo quando o objeto declara cessão onerosa (aí o banco paga).
RE_SERVICO_PAGO_PELO_ORGAO = re.compile(
    # Tarifa como OBJETO (o órgão paga), nunca "isenção de tarifas" (Olaria) nem
    # "cobrança de tarifas" como serviço correlato da folha (Jardim do Seridó).
    r"(?:pagamento|despesas\s+decorrentes)\s+de\s+tarifas|servi[çc]os?\s+relacionados?\s+a\s+tarifas|"
    r"respectivas\s+tarifas|"
    r"envio\s*/?\s*(?:e\s+)?retorno\s+de\s+arquivos|conta\s+(?:banc[áa]ria\s+)?institucional|"
    r"exceto\s+(?:o\s+)?pagamento\s+de\s+despesas\s+decorrentes\s+da\s+folha", re.I)

# ----------------------------------------------------------------- dentro
#
# Três caminhos, em ordem de especificidade. Qualquer um basta.
RE_CESSAO = re.compile(
    r"cess[ãa]o\s+onerosa|outorga\s+onerosa|"
    r"direito\s+de\s+(?:efetuar|realizar|execu[çc][ãa]o)\s+.{0,40}pagamento", re.I)

RE_CONTRATADO = re.compile(
    r"institui[çc][ãa]o\s+financeira|institui[çc][ãa]o\s+banc[áa]ria|"
    r"institui[çc][ãa]o\s+credenciada|cooperativa\s+de\s+cr[ée]dito|"
    r"\bbanco\b(?!\s+de\s+dados)|estabelecimento\s+banc[áa]rio", re.I)

# A OPERAÇÃO da folha, quando o objeto não usa "cessão" nem nomeia banco.
# Uberlândia diz "centralização dos negócios financeiros e Gestão da Folha";
# Várzea Paulista diz "gerenciamento da folha de aposentados e pensionistas e
# realização de prova de vida". As duas são do escopo e as duas eram perdidas.
RE_OPERACAO = re.compile(
    r"(?:pagamento|gerenciamento|gest[ãa]o|administra[çc][ãa]o|centraliza[çc][ãa]o|"
    r"processamento|operacionaliza[çc][ãa]o|manuten[çc][ãa]o|recebimento)\s+"
    r"(?:,?\s*(?:e\s+)?\w+\s+){0,4}?d[aeo]s?\s+folha|"
    r"cr[ée]ditos?\s+(?:provenientes\s+)?d[ao]\s+folha|"
    r"contas?[-\s]sal[áa]rios?|"
    r"folha\s+d[eoa]s?\s+\w+\s+(?:em|com)\s+exclusividade|"
    # Jev v3 (24/09/2026): "para operar, com exclusividade, a folha" (Xaxim,
    # Itajaí, Santa Terezinha) e "A operacionalização e o gerenciamento, com
    # exclusividade, da folha" (Piracuruca) — vírgulas no meio que o padrão de
    # cima não atravessa.
    r"\boperar\s*,?\s*(?:com\s+exclusividade\W{0,3}\s*)?(?:a|as)\s+folhas?\b|"
    r"(?:operacionaliza[çc][ãa]o|gerenciamento|processamento|gest[ãa]o)"
    r"(?:\s*,?\s+(?:e\s+)?(?:(?:o|a|os|as)\s+)?(?:operacionaliza[çc][ãa]o|gerenciamento|processamento|"
    r"gest[ãa]o|pagamento|com\s+exclusividade))*\s*,?\s+(?:d[ao]s?\s+)?folhas?\s+(?:d[eoa]s?\s+)?pagamen|"
    r"centraliza[çc][ãa]o\s+d[oe]s\s+neg[óo]cios\s+financeiros", re.I)

# Objeto curto demais não permite decidir. Passar custa uma extração; descartar
# custa uma licitação. O erro barato é passar — e a RN-15 vai sinalizar depois.
MINIMO_DECIDIVEL = 60


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip()


# O CAMPO `objetoCompra` NEM SEMPRE TRAZ SO O OBJETO.
#
# Ronda Alta/RS, Dispensa de 24/08/2026, campo de 1.598 caracteres:
#
#   "Aquisicao de relogios de ponto com reconhecimento facial e tela touch.
#    JUSTIFICATIVA: A presente aquisicao tem por finalidade [...] otimizando
#    o fluxo de processamento da folha de pagamento."
#
# O objeto e a PRIMEIRA frase: relogio de ponto. O resto e o Estudo Tecnico
# Preliminar colado no mesmo campo, e ele termina citando "processamento da
# folha de pagamento" como BENEFICIO da compra. O filtro lia o campo inteiro
# e aceitava -- verdade sobre o texto, falso sobre a licitacao.
#
# Cortar na marca da justificativa devolve a decisao ao objeto. So corta
# quando o que sobra ainda da para decidir: um campo que e so justificativa
# continua sendo avaliado inteiro, porque meio objeto e pior que nenhum.
RE_JUSTIFICATIVA = re.compile(
    r"(?:^|[\s.;])(?:JUSTIFICATIVA|JUSTIFICA[CÇ][AÃ]O|MOTIVA[CÇ][AÃ]O"
    r"|ESTUDO\s+T[EÉ]CNICO\s+PRELIMINAR|\bETP\b)\s*[:\-]", re.I)


def so_o_objeto(texto: str) -> str:
    """O objeto, sem a justificativa que o orgao colou no mesmo campo."""
    if not texto:
        return texto or ""
    m = RE_JUSTIFICATIVA.search(texto)
    if not m:
        return texto
    antes = texto[:m.start()].strip()
    return antes if len(antes) >= MINIMO_DECIDIVEL else texto


def avaliar(texto: str) -> tuple[bool, str]:
    """(é licitação de folha, motivo).

    A ordem é o desenho. Primeiro confirma que se fala de folha; depois descarta
    por PRODUTO, que é decisivo; só então procura o sinal de inclusão.
    """
    t = _norm(so_o_objeto(texto))
    if not t:
        return False, "objeto vazio"

    if not (RE_FOLHA.search(t) or RE_FOLHA_SEM_A_PALAVRA.search(t) or RE_OPERACAO.search(t)
            or (RE_PAGAR_SERVIDORES.search(t) and RE_CONTRATADO.search(t))):
        return False, "não é sobre folha de pagamento"

    # O SINAL FORTE é a OPERAÇÃO DA FOLHA, não quem é contratado.
    #
    # Esta distinção custou duas classificações erradas, e elas ficam
    # registradas em `saidas/_catalogo_escopo.json`. Uberlândia/MG e
    # Mangaratiba/RJ credenciam "instituições financeiras autorizadas pelo Banco
    # Central" — e o que contratam é **concessão de empréstimo consignado**. Se
    # "instituição financeira" valesse como sinal forte, as duas entrariam.
    #
    # O que separa é o verbo: operar a FOLHA (cessão, pagamento, processamento,
    # gerenciamento, créditos provenientes da folha, conta-salário) contra
    # conceder CRÉDITO ao servidor. Santa Efigênia/MG e Jaboatão/PE citam
    # consignado como acessório, mas dizem "gerenciamento de créditos
    # provenientes da Folha" — e é isso que as mantém dentro.
    forte = RE_CESSAO.search(t) or RE_OPERACAO.search(t) or RE_PAGAR_SERVIDORES.search(t)
    # Banco contratado (dito no começo) + operação da folha: sistema, plataforma
    # e suporte citados depois são peças do serviço do banco (Jev v3).
    banco_opera = bool(forte and RE_BANCO_NO_INICIO.search(t))

    # Sistema e software sao DECISIVOS, sem depender da trava `forte`.
    #
    # Uma licitacao de folha nunca contrata "licenca de uso" nem "cessao de
    # software": ela contrata quem paga os servidores. E um edital de sistema
    # quase sempre descreve gestao "da folha", o que acionava o sinal de
    # operacao e o fazia passar pela trava.
    if RE_SISTEMA.search(t) and not banco_opera:
        return False, "sistema ou plataforma que opera sobre a folha"

    # Servico SOBRE a folha tambem e decisivo, e pelo mesmo motivo do sistema.
    #
    # Quatro dos 117 positivos eram isto, e os quatro acionavam o sinal de
    # operacao porque dizem "gestao da folha", "processamento da folha":
    #   Uba/MG           estudo de viabilidade para a FUTURA contratacao
    #   Sobradinho/RS    contabilidade terceirizada que inclui a folha
    #   Mauriti/CE       assessoria e suporte tecnico na gestao da folha
    #   Montes Claros/MG treinamento em eSocial e EFD REINF
    #
    # Nenhum opera a folha: todos vendem trabalho ao orgao a respeito dela. Um
    # edital de cessao nunca contrata consultoria, curso ou escrituracao.
    if (RE_OUTRO_SERVICO.search(t) or RE_ESTUDO_OU_CONSULTORIA.search(t)) \
            and not (banco_opera and not RE_ESTUDO_OU_CONSULTORIA.search(t)):
        return False, "serviço SOBRE a folha (consultoria, contabilidade, curso, estudo)"

    # ADR-015: o órgão PAGA o banco (tarifas, arquivos, conta institucional).
    # Só a cessão onerosa inverte a direção do dinheiro.
    if RE_SERVICO_PAGO_PELO_ORGAO.search(t) and not RE_CESSAO.search(t):
        return False, "serviço bancário pago pelo órgão (tarifas, arquivos, conta), não compra da folha"

    if not forte:
        if RE_CONSIGNADO.search(t):
            return False, "consignado ou margem consignável, não a folha em si"

    if RE_CESSAO.search(t):
        return True, "cessão onerosa do direito de pagar a folha"
    if RE_OPERACAO.search(t) or RE_PAGAR_SERVIDORES.search(t):
        return True, "contrata a operação da folha (pagamento, gestão, créditos)"
    if RE_CONTRATADO.search(t):
        return True, "contrata instituição financeira, e nada indica consignado"

    if len(t) < MINIMO_DECIDIVEL:
        return True, "objeto curto demais para decidir — passa para revisão"

    return False, "fala de folha, mas não é a operação dela"


def e_folha(texto: str) -> bool:
    return avaliar(texto)[0]
