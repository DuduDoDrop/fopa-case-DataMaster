# -*- coding: utf-8 -*-
"""
As 17 perguntas — especificação legível por máquina.

Fonte única da verdade do entregável. O vault (Fopa-v2/00-Case/Questionário de
extração.md) é a versão para humanos; este módulo é o que o código executa.
Mudou aqui, muda lá — e vice-versa.

Regras aplicadas (Fopa-v2/00-Case/Regras de negócio.md):
  RN-08  Info = arquivo + página física
  RN-09  Q13 captura TODAS as tabelas da pirâmide
  RN-11  Q13 declara a população coberta
  RN-12  Q14 declara a unidade (vínculos ou pessoas)
  RN-13  transcrever, nunca calcular

TERMOS DE RECUPERAÇÃO, REVISADOS CONTRA O CORPUS (22/09/2026)
Os `termos` de cada pergunta alimentam o BM25, e foram escritos a partir da
PERGUNTA. Auditados contra as 729 páginas das 13 licitações, dez deles não
apareciam em uma única página — "prazo para assinar", "prazo de implantação",
"obrigações do vencedor", "taxa de juros", "percentual entre lances", "art. 98".

Termo morto não recupera nada. É a falha clássica de RAG lexical, e ela é
silenciosa: a pergunta continua sendo respondida, porque as outras palavras
salvam, e ninguém descobre que um quarto dos sinais não fazia nada.

Foram trocados pelo que os editais de fato escrevem. A exceção deliberada é a
Q16: "prova de vida" e "recenseamento" também não aparecem em página nenhuma, e
ali isso é a RESPOSTA, não um defeito — o conceito não existe nestes editais.
Termo morto de conceito ausente é sonda negativa e fica como está.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Pergunta:
    id: str
    texto: str
    orienta: str
    termos: tuple[str, ...]          # sinais de recuperação (usados pelo RAG)
    formato: str = ""                # formato esperado da resposta
    critico: bool = False            # entra no cálculo do lance


PERGUNTAS: tuple[Pergunta, ...] = (
    Pergunta(
        "Q1", "Qual a Data da Licitação ?",
        "Data e hora da sessão pública. Se houver aviso de retificação, suspensão ou "
        "redesignação, a data válida é a DELE, não a do edital.",
        ("sessão pública", "abertura", "data", "hora", "retificação", "redesignação",
         "suspensão", "cronograma", "recebimento das propostas"),
        'DD/MM/AAAA às HHhMM (horário de Brasília)', critico=True),
    Pergunta(
        "Q2", "O que diz o Objeto do Edital ?",
        "Texto integral do objeto, sem resumir.",
        ("objeto", "constitui o objeto", "destina-se", "contratação de instituição")),
    Pergunta(
        "Q3", "Qual a Modalidade de Contratação ?",
        "Ex.: PREGÃO ELETRÔNICO, CONCORRÊNCIA, CREDENCIAMENTO, DISPENSA, INEXIGIBILIDADE.",
        ("modalidade", "pregão", "concorrência", "credenciamento", "dispensa",
         "inexigibilidade", "preâmbulo")),
    Pergunta(
        "Q4", "Qual o Tipo do Pregão ?",
        "Critério de julgamento. Em folha costuma ser Maior Lance ou Maior Oferta. "
        "Em credenciamento e contratação direta pode não se aplicar.",
        ("critério de julgamento", "maior lance", "maior oferta", "tipo", "julgamento")),
    Pergunta(
        "Q5", "Qual o Valor Mínimo de Contratação ?",
        "Transcreva o rótulo COMO ESTÁ no documento: 'valor mínimo', 'valor estimado' e "
        "'valor de referência' são conceitos distintos em leilão de maior oferta. "
        "Não normalize o rótulo.",
        ("valor mínimo", "valor estimado", "valor de referência", "R$", "orçamento",
         "valor da contratação"),
        'R$ X (VALOR POR EXTENSO), com o rótulo literal usado no documento', critico=True),
    Pergunta(
        "Q6", "Qual o valor dos Lances Mínimos ?",
        "Intervalo mínimo entre lances, em % ou R$.",
        ("intervalo mínimo", "lance", "diferença de valores",
         "intervalo mínimo de diferença de valores", "lances intermediários")),
    Pergunta(
        "Q7", "Qual é o Prazo de Assinatura do Contrato ?",
        "Prazo e a partir de quando conta.",
        ("assinatura do contrato", "convocação", "dias úteis",
         "assinar o termo de contrato", "convocado para assinar",
         "decair o direito à contratação",
         # AS TRES ABAIXO SAIRAM DO EDITAL, NAO DE SUPOSICAO DO ANALISTA.
         # Sao Lourenco do Sul/RS escreve: "esgotados todos os prazos
         # recursais, a Administracao convocara a empresa vencedora do
         # certame". Nenhum dos seis termos acima aparece ali -- todos falam
         # em "assinar" e o edital fala em "convocar a vencedora". A pagina
         # com a resposta ficava fora do top-6 do BM25, e isso e silencioso:
         # o modelo diria "nao localizado", e ausencia declarada ANCORA.
         "prazos recursais", "convocará a empresa vencedora",
         "convocado a assinar")),
    Pergunta(
        "Q8", "Qual é o Prazo de Pagamento ?",
        "Prazo para o banco pagar o valor ofertado ao ente.",
        ("prazo de pagamento", "pagamento do valor", "dias úteis após",
         "recursos financeiros", "realizar o pagamento",
         "pagamento do maior lance", "não realizará desembolso",
         "critérios de medição e pagamento")),
    Pergunta(
        "Q9", "Qual o prazo de vigência do contrato ?",
        "Em meses ou anos, com prorrogação se houver.",
        ("vigência", "meses", "prorrogado", "duração do contrato"), critico=True),
    Pergunta(
        "Q10", "Qual o prazo de início de serviços ?",
        "Prazo e prorrogação, se houver.",
        # "COMEÇAR" ENTROU DEPOIS, E POR MEDIÇÃO.
        # O BM25 é lexical: não atravessa `começar` <-> `iniciar`. Bertioga/SP
        # escreve "a contratada tem 60 (sessenta) dias para COMEÇAR A EXECUTAR
        # os serviços", e a página não entrava no top-12 — porque todos os
        # termos-sinal usavam a família de "iniciar".
        #
        # O que a lista de termos precisa carregar não é o vocabulário do
        # analista: é o vocabulário DO EDITAL.
        ("início da execução", "iniciar a operacionalização",
         "implantação dos serviços", "iniciar a prestação dos serviços",
         "apta a iniciar", "começar a executar", "dias para começar",
         "início efetivo", "prazo para início")),
    Pergunta(
        "Q11", "Quais são as obrigações do banco vencedor ?",
        "Obrigações principais, resumidas sem perder números e prazos.",
        ("obrigações da contratada", "obrigações da instituição",
         "são obrigações", "obrigações da vencedora", "caberá à instituição",
         "deverá a contratada")),
    Pergunta(
        "Q12", "Qual é a infraestrutura solicitada ?",
        "Agência, PAB, posto de atendimento, caixas eletrônicos e prazo de instalação. "
        "Registre se é obrigatória ou facultativa.",
        ("agência", "posto de atendimento", "PAB", "caixa eletrônico", "autoatendimento",
         "instalação", "infraestrutura"), critico=True),
    Pergunta(
        "Q13", "Qual a quantidade de servidores aberta por faixa salarial ?",
        "PIRÂMIDE COMPLETA. Há quase sempre MAIS DE UMA TABELA, separada por vínculo "
        "(contratos, estatutários, ativos, inativos, pensionistas, temporários). "
        "Capture todas, some cada uma e confira com o total impresso DELA. "
        "Declare qual população a pirâmide cobre e qual ela exclui.",
        ("faixa salarial", "pirâmide", "salário", "quantidade de servidores", "qtde",
         "até R$", "acima de R$", "inativos", "pensionistas", "ativos"),
        '"Vínculo X — Até R$ A: n; R$ A,01 a R$ B: m; Acima de R$ B: k (total N)" por tabela, '
        'mais a população coberta', critico=True),
    Pergunta(
        "Q14", "Qual a Quantidade total de servidores ?",
        "Número total E A UNIDADE: vínculos ou pessoas físicas. Um servidor pode acumular "
        "mais de um vínculo. Se o documento não disser, registre que não diz.",
        ("total de servidores", "número aproximado", "quantitativo", "vínculos", "servidores"),
        '"N vínculos" ou "N pessoas", explicitando qual', critico=True),
    Pergunta(
        "Q15", "Quais são as condições do consignado ?",
        "Margem consignável, taxa-teto, exclusividade, prazos e quem faz a averbação.",
        ("consignado", "consignação", "margem consignável", "averbação", "empréstimo",
         "empréstimo consignado", "cartão de crédito consignado",
         "consignação em folha")),
    Pergunta(
        "Q16", "Existe necessidade do vencedor realizar prova de vida dos servidores ?",
        "Sim/Não e em que condição. Recadastramento de beneficiários conta como prova de vida.",
        ("prova de vida", "recadastramento", "recenseamento", "comprovação de vida",
         "beneficiários")),
    Pergunta(
        "Q17", "Existe necessidade do vencedor apresentar alguma garantia ?",
        "Sim/Não, percentual, modalidade e A BASE DE CÁLCULO declarada. Pode estar em "
        "documento de esclarecimento, não só no edital. Nunca calcule o valor.",
        ("garantia", "caução", "seguro-garantia", "fiança bancária", "art. 96",
         "garantia prestada", "garantia de proposta", "garantia de execução",
         "garantia contratual",
         "art. 69"), critico=True),
)

POR_ID = {p.id: p for p in PERGUNTAS}


def pergunta(pid: str) -> Pergunta:
    return POR_ID[pid]


# --------------------------------------------------------------- esquema de saída
ESQUEMA_RESPOSTA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "identificador da pergunta, ex.: Q5"},
        "resposta": {
            "type": "string",
            "description": 'A resposta, transcrita do documento. "Não localizado" quando '
                           'a informação não estiver nos documentos fornecidos.'},
        "arquivo": {
            "type": ["string", "null"],
            "description": "nome do arquivo de onde veio a resposta; null se não localizado"},
        "pagina": {
            "type": ["integer", "null"],
            "description": "página FÍSICA do PDF (a que o leitor mostra); null se não localizado"},
        "trecho_literal": {
            "type": ["string", "null"],
            "description": "trecho copiado EXATAMENTE do documento que fundamenta a resposta. "
                           "Será conferido caractere a caractere contra a página citada."},
        "conflito": {
            "type": ["string", "null"],
            "description": "descrição do conflito quando documentos divergem; null se não houver"},
        "confianca": {"type": "string", "enum": ["alta", "media", "baixa"]},
    },
    "required": ["id", "resposta", "arquivo", "pagina", "trecho_literal",
                 "conflito", "confianca"],
    "additionalProperties": False,
}

ESQUEMA_LOTE = {
    "type": "object",
    "properties": {
        "respostas": {"type": "array", "items": ESQUEMA_RESPOSTA},
    },
    "required": ["respostas"],
    "additionalProperties": False,
}

NAO_LOCALIZADO = "Não localizado"

# ------------------------------------------------- perguntas por modalidade
#
# As 17 perguntas foram desenhadas para pregão e concorrência, que têm sessão,
# disputa e lance. Dispensa, Inexigibilidade e Credenciamento não têm nada
# disso — e ali "não localizado" é uma resposta enganosa: sugere que a
# informação deveria estar no documento e o sistema não achou.
#
# O caso que revelou isso: Rio Branco/AC, uma dispensa do TCE-AC, voltou com 11
# de 17 em branco. Nenhuma era falha de leitura. Uma dispensa não tem data de
# sessão de disputa porque não há disputa; não tem lance mínimo porque não há
# lance. O documento está completo — a pergunta é que não cabe.
#
# A lista é curta de propósito. Só entram as perguntas cuja inaplicabilidade é
# consequência DIRETA da modalidade. "Valor mínimo" continua valendo numa
# dispensa, porque há valor; só não há piso de lance.
NAO_SE_APLICA = {
    "dispensa": ("Q1", "Q4", "Q6"),
    "inexigibilidade": ("Q1", "Q4", "Q6"),
    "credenciamento": ("Q4", "Q6"),
}

_MOTIVO = {
    "dispensa": "contratação direta: não há sessão pública nem disputa de lances",
    "inexigibilidade": "contratação direta: o fornecedor já está definido, "
                       "não há sessão nem disputa",
    "credenciamento": "credenciamento habilita quem atende aos requisitos; "
                      "não há julgamento por preço nem lance",
}


def modalidade_chave(texto: str) -> str:
    """Reduz a modalidade a uma chave. Devolve "" quando não reconhece.

    Aceita tanto o nome da API ("Dispensa de Licitação") quanto o que o modelo
    escreve na Q3 ("Dispensa") e o nome da pasta — as três grafias circulam pelo
    pipeline e nenhuma é canônica.
    """
    baixo = (texto or "").lower()
    for chave in NAO_SE_APLICA:
        if chave in baixo:
            return chave
    return ""


def nao_se_aplica(pergunta_id: str, modalidade: str) -> str:
    """Motivo pelo qual a pergunta não cabe nesta modalidade, ou "" se cabe."""
    chave = modalidade_chave(modalidade)
    if chave and pergunta_id in NAO_SE_APLICA[chave]:
        return _MOTIVO[chave]
    return ""



def instrucao_sistema() -> str:
    """
    O prompt de sistema do Extrator.

    Escrito para ser estável: entra ANTES do documento na requisição, para que o
    prefixo possa ser cacheado (o documento é o que varia).
    """
    return """Você extrai respostas de editais de licitação de folha de pagamento do setor público brasileiro.

REGRAS ABSOLUTAS

1. Só afirme o que está escrito nos documentos fornecidos. Nunca infira, nunca calcule,
   nunca complete com conhecimento geral sobre licitações.

2. Toda resposta vem com `trecho_literal` copiado EXATAMENTE do texto, mais o `arquivo`
   e a `pagina` onde ele aparece. Esse trecho será conferido caractere a caractere contra
   a página citada. Se você parafrasear, a resposta será rejeitada.

3. Não encontrou? `resposta` = "Não localizado", `arquivo` = null, `pagina` = null,
   `trecho_literal` = null. Isso é uma resposta CORRETA e preferível a uma tentativa.

4. A `pagina` é a página FÍSICA do PDF — o número que aparece no marcador
   "=== ARQUIVO x | PÁGINA n ===", não a numeração impressa no rodapé do documento.

5. Os documentos podem se contradizer. Precedência:
   aviso de retificação/suspensão mais recente > termo de referência corrigido >
   edital de maior sequencial > editais anteriores.
   Ao usar o mais recente, descreva a divergência em `conflito`.

6. Transcreva rótulos como estão. "valor mínimo", "valor estimado" e "valor de referência"
   são conceitos DIFERENTES em leilão de maior oferta. Não normalize.

7. A pirâmide salarial costuma vir em VÁRIAS TABELAS, separadas por vínculo. Capture todas.
   Se a soma de uma tabela não bater com o total impresso dela, relate a diferença em
   `conflito` em vez de ajustar os números.

8. Ignore linhas de assinatura digital ("Assinado por N pessoas", "Para verificar a
   autenticidade", "Código para verificação"). Não são conteúdo do edital.

9. Nunca calcule percentuais, totais ou valores derivados. Transcreva o percentual e a
   base de cálculo que o documento declara."""


__all__ = ["Pergunta", "PERGUNTAS", "POR_ID", "pergunta", "ESQUEMA_RESPOSTA",
           "ESQUEMA_LOTE", "NAO_LOCALIZADO", "instrucao_sistema"]
