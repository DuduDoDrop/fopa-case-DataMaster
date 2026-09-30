# -*- coding: utf-8 -*-
"""
Agente 4 — Verificador.

NÃO USA MODELO DE LINGUAGEM. Por princípio, não por economia.

Se a verificação também fosse feita por LLM, ela herdaria exatamente o modo de falha
que deveria detectar: uma alucinação plausível confirmada por outra alucinação
plausível. Aqui só há comparação de strings e aritmética — coisas que não inventam.

Regras (Fopa-v2/00-Case/Regras de negócio.md):
  RN-01 ancoragem obrigatória      RN-03 quem gera não verifica
  RN-09 somar todas as tabelas     RN-10 total deslocado para linha de faixa
  RN-11 população coberta          RN-12 unidade da contagem
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

from .extrator import Extracao, Resposta
from . import distribuicao
from .questionario import NAO_LOCALIZADO, POR_ID, modalidade_chave, nao_se_aplica

APROVADO, REVISAR, REPROVADO = "APROVADO", "REVISAR", "REPROVADO"

# tolerância da ancoragem: PDF quebra palavra com hífen, troca ligaduras e insere
# espaços fantasmas. Exigir igualdade exata geraria falso alarme em massa.
LIMIAR_ANCORAGEM = 0.90
TRECHO_MINIMO = 12          # abaixo disso o trecho não prova nada


def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = s.replace("-\n", "").replace("­", "")      # hifenização de quebra
    return re.sub(r"\s+", " ", s.lower()).strip()


def _similar(a: str, b: str) -> float:
    # autojunk=False: com ele ligado, o difflib trata letras comuns como ruído em
    # sequências longas e a similaridade colapsa. Já custou uma medição errada.
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _numeros(texto: str) -> set[str]:
    """
    Os números de um texto, como conjunto de dígitos puros.

    `R$ 1.250.000,00` vira `125000000`; `60 (sessenta) meses` vira `{60}`.
    Separador de milhar e vírgula decimal somem, porque edital não é
    consistente com eles e a diferença que importa nunca está aí.
    """
    return {re.sub(r"\D", "", t) for t in re.findall(r"\d[\d.,]*", texto or "")
            if re.sub(r"\D", "", t)}


def _numeros_confirmados(alvo: str, fonte: str) -> list[str]:
    """
    Os números que o trecho citado afirma e a página NÃO contém.

    POR QUE ISTO EXISTE — O LIMIAR PERDOA EXATAMENTE O QUE IMPORTA
      A ancoragem aproximada usa `difflib`, que compara caracteres sem saber o
      que cada um significa. Num trecho de 49 caracteres, trocar `1.250.000,00`
      por `2.250.000,00` muda UM caractere: similaridade 0,98, bem acima do
      limiar de 0,90. Aprovado, sem nota.

      Medido em 23/09/2026, com o limiar em vigor:

        | citação falsa                        | similaridade | veredito |
        |--------------------------------------|--------------|----------|
        | R$ 1.250.000,00 -> R$ 2.250.000,00   | 0,98         | APROVADO |
        | R$ 1.250.000,00 -> R$ 1.250.000,01   | 0,98         | APROVADO |
        | R$ 1.250.000,00 -> R$ 125.000,00     | 0,98         | APROVADO |
        | R$ 1.250.000,00 -> R$ 10,00          | 0,93         | APROVADO |
        | 60 (sessenta) meses -> 6 (seis) meses| 0,92         | APROVADO |

      O mecanismo central do projeto era cego justamente para a classe de erro
      que mais importa num documento financeiro. A folga de 10% existe para
      absorver ruído de extração de PDF — hifenização, espaço duplo, ligadura —
      e ruído de PDF não troca algarismo.

      Então a folga passa a valer só para LETRA. Todo número que a citação
      afirma tem que estar na página, sem aproximação. É determinístico, não
      usa modelo, e custa uma varredura de regex.

    Devolve a lista dos números não confirmados — vazia quando está tudo certo.
    """
    na_pagina = _numeros(fonte)
    return sorted(n for n in _numeros(alvo) if n not in na_pagina)


def nao_encontrou(resposta: str) -> bool:
    """
    Reconhece "não localizado" em qualquer das formas que o modelo usa.

    A checagem era por igualdade exata com a string canônica, e isso reprovava a
    forma MAIS útil: `"Não localizado. Os documentos não tratam de consignado — não
    há margem, taxa-teto nem exclusividade."` O modelo explicava por que não achou,
    e era punido por isso, porque a resposta deixava de casar e caía na regra que
    exige trecho literal.

    Encontrado ao rodar o lote nas 13 licitações: 4 de 4 reprovações eram este caso.
    Um bug que uma execução isolada não revelaria.
    """
    return _normalizar(resposta).startswith(_normalizar(NAO_LOCALIZADO))




def ausencia_real(r: Resposta) -> bool:
    """Ausência de verdade: nem trecho, nem arquivo, nem página.

    "Não localizado" nem sempre quer dizer que não há nada. Fruta de Leite/MG
    responde à Q13 com *"Não localizado como pirâmide por faixa salarial. O
    Termo de Referência traz apenas os quantitativos por vínculo: Efetivos 201;
    Contratados 214; ..."* — e cita o Edital, página 20, com trecho literal.

    O modelo achou o dado e avisou que o formato é outro. Tratar isso como
    ausência fazia três coisas erradas de uma vez: a âncora nunca era conferida,
    a pergunta contava como não respondida, e o relatório escondia uma tabela
    completa e correta atrás de "não consta dos documentos".

    O critério é o mesmo do resto do projeto: **evidência citada é evidência**.
    Se há arquivo, página e trecho, há o que verificar.
    """
    if not nao_encontrou(r.resposta):
        return False
    return not (r.trecho_literal and r.trecho_literal.strip()
                and r.arquivo and r.pagina)


# ---------------------------------------------------------------- 1. ancoragem
def verificar_ancoragem(r: Resposta, ext: Extracao) -> tuple[str, list[str]]:
    """A checagem central: o trecho citado existe mesmo naquela página?"""
    if ausencia_real(r):
        return APROVADO, []
    if not r.trecho_literal or not r.trecho_literal.strip():
        return REPROVADO, ["sem trecho literal utilizável — RN-01"]
    if not r.arquivo or not r.pagina:
        return REPROVADO, ["resposta sem arquivo ou página — RN-08"]

    pg = ext.pagina(r.arquivo, r.pagina)
    if pg is None:
        return REPROVADO, ["página citada não existe: %s p.%s" % (r.arquivo, r.pagina)]

    alvo, fonte = _normalizar(r.trecho_literal), _normalizar(pg.texto)

    # Uma correção de página já aplicada continua sendo um fato sobre a citação.
    # Na reverificação o trecho agora bate — porque a página foi corrigida — e
    # sem esta marca o caso voltaria a APROVADO, apagando o rastro do ajuste.
    if r.pagina_citada is not None and r.pagina_citada != r.pagina:
        return REVISAR, [
            "página corrigida em verificação anterior: o modelo citou a p.%d e o "
            "trecho está na p.%d. O link aponta para a página certa; confirme que "
            "a resposta corresponde ao contexto dela."
            % (r.pagina_citada, r.pagina)]

    # Trecho curto: o comprimento não é a pergunta certa. A UNICIDADE é.
    #
    # Fruta de Leite/MG cita "R$ 500,00" para o intervalo mínimo de lances, e o
    # valor está numa célula do Anexo III — o rótulo fica no cabeçalho da tabela,
    # longe. Nove caracteres, abaixo do mínimo de doze, e a resposta correta era
    # reprovada por isso.
    #
    # Mas um trecho curto que aparece UMA única vez no conjunto inteiro prova
    # mais que uma frase longa e genérica: não há outro lugar de onde ele possa
    # ter vindo. Se aparece em várias páginas, aí sim não ancora nada.
    if len(alvo) < TRECHO_MINIMO:
        onde = [p for p in ext.paginas if alvo in _normalizar(p.texto)]
        if len(onde) == 1 and onde[0].arquivo == r.arquivo and onde[0].numero == r.pagina:
            return APROVADO, [
                "trecho curto (%d caracteres) aceito por ser único em todo o "
                "conjunto — típico de valor em célula de tabela" % len(alvo)]
        return REPROVADO, [
            "trecho de %d caracteres, abaixo do mínimo de %d, e %s — RN-01"
            % (len(alvo), TRECHO_MINIMO,
               "não encontrado" if not onde
               else "presente em %d página(s), o que não ancora nada" % len(onde))]

    if alvo in fonte:
        return APROVADO, []

    # janela deslizante: o melhor casamento local do tamanho do trecho
    n = len(alvo)
    melhor = 0.0
    passo = max(1, n // 4)
    for i in range(0, max(1, len(fonte) - n + 1), passo):
        melhor = max(melhor, _similar(alvo, fonte[i:i + n]))
        if melhor >= LIMIAR_ANCORAGEM:
            # A FOLGA DO LIMIAR VALE PARA LETRA, NÃO PARA ALGARISMO.
            # Ruído de extração de PDF não troca dígito; ele hifeniza, duplica
            # espaço e engole acento. Um número que a citação afirma e a página
            # não tem é invenção, não ruído — por mais parecido que o resto seja.
            faltando = _numeros_confirmados(alvo, fonte)
            if faltando:
                return REPROVADO, [
                    "ancoragem textual de %.2f, mas o(s) número(s) %s não "
                    "aparecem na página citada. Ruído de PDF não troca "
                    "algarismo — RN-01"
                    % (melhor, ", ".join(faltando[:4]))]
            return APROVADO, ["ancoragem aproximada (%.2f) — ruído de PDF" % melhor]

    # O trecho pode estar certo e a PÁGINA errada. Não é a mesma falha.
    #
    # Nas 13 licitações isso apareceu duas vezes, e nas duas o desvio foi de uma
    # página — Adrianópolis citou p.24 para texto da p.23, Fruta de Leite citou
    # p.23 para texto da p.24. Direções opostas, então não é confusão entre
    # numeração impressa e física: é a cláusula atravessando a virada de página.
    #
    # Tratar isso como "reprovado" junta duas coisas diferentes sob o mesmo
    # rótulo. Trecho inventado não existe em lugar nenhum; este existe, foi
    # localizado, e o sistema sabe exatamente onde. A citação é CORRIGIDA e o
    # caso vai para revisão humana — que é o que ele merece — em vez de ser
    # descartado junto com a alucinação, que é o que ele não é.
    for outra in ext.paginas:
        if outra.arquivo == r.arquivo and outra.numero == r.pagina:
            continue
        if alvo in _normalizar(outra.texto):
            citada, veio_de = r.pagina, "mesmo arquivo"
            if outra.arquivo != r.arquivo:
                veio_de = "OUTRO arquivo"
            r.pagina_citada = citada        # o rastro da correcao fica gravado
            r.pagina = outra.numero
            r.arquivo = outra.arquivo
            return REVISAR, [
                "página corrigida: o trecho não está na p.%d citada, está na "
                "p.%d (%s). O link já aponta para a página certa; confirme que "
                "a resposta corresponde ao contexto dela."
                % (citada, outra.numero, veio_de)]

    return REPROVADO, ["trecho não encontrado na página citada (melhor casamento %.2f)" % melhor]


# ---------------------------------------------------------------- 2. pirâmide
# Uma faixa pode ser escrita de várias formas, e a cobertura estreita custou caro:
# a versão anterior exigia "de R$ X até R$ Y" e os documentos escrevem
# "R$ X a R$ Y: N". Das sete faixas de Pirapó/RS só a última casava, a RN-09
# somava 3 contra 297 e acusava truncamento numa pirâmide íntegra — nos três
# modelos ao mesmo tempo, porque a falha era do parser, não da leitura.
RE_FAIXA = re.compile(
    r"(?:"
    r"(?:de\s*)?R\$\s*[\d.]+,\d{2}\s*(?:a|at[ée])\s*R\$\s*[\d.]+,\d{2}"   # R$ X a R$ Y
    r"|[\d.]+(?:,\d{2})?\s*>\s*[\d.]+,\d{2}"                               # 2.001,00 > 3.000,00
    r"|(?:acima\s*de|mais\s*de|a\s*partir\s*de)\s*R?\$?\s*[\d.]+,\d{2}"   # acima/a partir de R$ X
    # O (?!...) nao e refinamento: sem ele esta alternativa vence a corrida
    # contra a forma "R$ X a R$ Y" -- ela comeca antes, no "ate" -- e o grupo
    # de quantidade acaba capturando o INICIO DO LIMITE SUPERIOR.
    # "ate R$ 2.000,01 a R$ 3.000,00: 93" era lido como quantidade 3.
    # Em Pirapo/RS as sete faixas [32,93,56,72,27,14,3] viravam
    # [32,3,4,5,7,10,3]: soma 64 em vez de 297. A RN-09 entao acusava
    # "so parte das tabelas foi lida" numa piramide integra, e a RN-10
    # acusava total deslocado. Dois alarmes, zero problema no edital.
    r"|at[ée]\s*R\$\s*[\d.]+,\d{2}(?!\s*(?:a|at[ée]|>)\s*R?\$)"           # até R$ X
    r")"
    # O $ na classe negada NAO e detalhe. A cauda liga o fim da faixa a
    # quantidade, e sem o cifrao ela atravessa sem restrição um valor em reais:
    # "De R$ 10.001,00 ate 15.000,00: quantidade nao informada (R$ 37.127,86)"
    # daria quantidade 37 -- uma folha bruta lida como numero de servidores.
    # Hoje isso e no-op nas 14 extracoes do acervo (medido). Fica como guarda
    # para quem for alargar a RE_FAIXA depois: e a armadilha que espera.
    r"[^\d\n$]{0,40}(\d{1,5})", re.I)

# Sinais de que a Q13 realmente traz uma pirâmide. Servem para distinguir
# "não há pirâmide para conferir" de "há, e o parser não a reconheceu" — que
# eram indistinguíveis quando a regra simplesmente não dizia nada.
RE_TEM_PIRAMIDE = re.compile(r"faixa|p[ií]r[aâ]mide|salarial|sal[áa]rio", re.I)
RE_TOTAL_DECL = re.compile(r"total(?:\s+de)?\s*[:\-]?\s*(\d{1,3}(?:\.\d{3})*|\d+)", re.I)


def _inteiros_rotulados(texto: str) -> list[int]:
    return [int(m.group(1)) for m in RE_FAIXA.finditer(texto or "")]


def verificar_piramide(ext: Extracao) -> list[str]:
    """
    RN-09 e RN-10.

    Não tenta reconstruir a pirâmide — tenta detectar as duas falhas conhecidas:
    parar na primeira tabela, e total deslocado para uma linha de faixa.
    """
    alertas: list[str] = []
    q13, q14 = ext.por_id("Q13"), ext.por_id("Q14")
    if not q13:
        return alertas

    # "Não localizado" não encerra o assunto quando vem acompanhado de dado.
    #
    # Fruta de Leite/MG responde: "Não localizado COMO PIRÂMIDE POR FAIXA
    # SALARIAL. O Termo de Referência traz apenas os quantitativos por vínculo:
    # Efetivos 201; Contratados 214; Comissionados 85; Inativos 4 — total 504."
    #
    # A resposta é ótima e o aviso é preciso. Mas a saída antecipada aqui olhava
    # só as duas primeiras palavras e desistia, e com isso os 504 servidores
    # conferidos ficavam sem nenhuma marca — indistinguíveis de um edital que
    # não informou nada. São coisas bem diferentes para quem vai precificar.
    dist = distribuicao.ler(q13.resposta)
    if ausencia_real(q13):
        if dist.grupos:
            alertas.append(
                "RN-14: a Q13 diz \"não localizado\" para a pirâmide por faixa "
                "salarial, mas a resposta traz distribuição por %s — %d linhas, "
                "%d no total. O dado existe em outro formato: sem faixa salarial "
                "não há ticket médio nem estimativa de consignado."
                % (dist.tipo, len(dist.linhas), dist.soma))
        return alertas

    faixas = _inteiros_rotulados(q13.resposta)
    soma = sum(faixas)

    # a Q14 declara um total?
    total_q14 = None
    if q14 and not nao_encontrou(q14.resposta):
        # Tirar os pontos ANTES de casar quebrava o numero: "1.896" virava "1896"
        # e a alternativa \d{1,3} casava so "189". A RN-09 entao comparava 1408
        # contra 189 e anunciava que as faixas somavam DEMAIS — a leitura oposta
        # da verdade, num edital cuja piramide esta truncada em 488 vinculos.
        # A forma com separador vem primeiro; os pontos saem depois do casamento.
        m = re.search(r"\d{1,3}(?:\.\d{3})+|\d+", q14.resposta)
        if m:
            try:
                total_q14 = int(m.group(0).replace(".", ""))
            except ValueError:
                total_q14 = None

    # Um alarme aritmético precisa saber quando NÃO conseguiu ler. Com uma faixa
    # só, "a soma não bate" descreve o parser, não o documento — e um falso
    # positivo no Verificador é pior que um silêncio: ele é a peça que a solução
    # pede para quem usa confiar sem reconferir à mão.
    if len(faixas) < 2 and RE_TEM_PIRAMIDE.search(q13.resposta or ""):
        alertas.append(
            "RN-09 não aplicada: a Q13 descreve faixas salariais mas só %d foi "
            "reconhecida, o que é insuficiente para conferir a soma. A pirâmide "
            "precisa de conferência humana — a regra não afirma nada sobre ela."
            % len(faixas))
    elif len(faixas) >= 2 and total_q14:
        if soma == total_q14:
            pass
        elif soma < total_q14 * 0.6:
            alertas.append(
                "RN-09: as faixas da Q13 somam %d contra %d declarados na Q14 — "
                "diferença de %d. Forte indício de que só parte das tabelas foi lida."
                % (soma, total_q14, total_q14 - soma))
        else:
            alertas.append("RN-09: faixas somam %d, Q14 declara %d, diferença de %d"
                           % (soma, total_q14, total_q14 - soma))

    # RN-10 — total deslocado para uma linha de faixa
    if faixas and len(faixas) > 2:
        maior = max(faixas)
        resto = soma - maior
        if maior >= resto and resto > 0:
            # A igualdade NAO e o caso fraco -- e a assinatura exata de um total
            # lido como faixa, porque total = soma das partes. A mensagem dizia
            # "maior que a soma das outras (32)" com maior=32: literalmente falsa
            # justamente no caso mais forte que a regra sabe detectar.
            como = "igual à" if maior == resto else "maior que a"
            forca = (" Os dois valores são iguais, que é a assinatura exata de um "
                     "total: total = soma das partes." if maior == resto else "")
            alertas.append(
                "RN-10: a quantidade %d numa linha de faixa é %s soma de todas "
                "as outras (%d).%s Possível total da tabela deslocado para a faixa — foi "
                "exatamente o que aconteceu com o 287 em São Lourenço do Sul."
                % (maior, como, resto, forca))

    # RN-11 — a resposta declara a população coberta?
    baixo = _normalizar(q13.resposta)
    if not any(t in baixo for t in ("ativo", "inativo", "pensionista", "estatutario",
                                    "celetista", "comissionado", "contrato",
                                    "temporario", "vinculo", "populacao")):
        alertas.append("RN-11: a Q13 não declara qual população a pirâmide cobre "
                       "(a de Bertioga exclui aposentados e pensionistas)")

    # RN-14 — veio distribuição, mas NÃO por faixa salarial?
    #
    # Fruta de Leite/MG responde com 504 servidores perfeitamente contados e
    # conferidos — por VÍNCULO. A resposta está certa e o edital é que não traz
    # pirâmide; a própria resposta nota que a cláusula 8.17 da minuta manda
    # observar "a pirâmide salarial" que não existe nos documentos.
    #
    # Sem esta regra o fato fica enterrado numa frase de quinze linhas, e quem
    # lê a planilha vê um número de servidores e supõe que tem a distribuição.
    # Não tem: sem faixa salarial não há ticket médio, não há estimativa de
    # consignado e não há como ver concentração da folha.
    dist = distribuicao.ler(q13.resposta)
    if dist.grupos and not dist.por_faixa:
        alertas.append(
            "RN-14: a Q13 NÃO traz pirâmide por faixa salarial — traz "
            "distribuição por %s (%d linhas, %d no total). Sem faixa salarial "
            "não dá para estimar ticket médio nem potencial de consignado; "
            "é candidata a pedido de esclarecimento ao órgão."
            % (dist.tipo, len(dist.linhas), dist.soma))
    elif dist.grupos and dist.parcial and not dist.completa:
        alertas.append(
            "RN-14: a pirâmide foi lida em parte — %d linha(s) em %d tabela(s), "
            "somando %d. A própria resposta declara que falta dado, então esta "
            "soma não representa a população: confira contra o anexo original."
            % (len(dist.linhas), len(dist.grupos), dist.soma))
    return alertas


# NÃO existe ausência "esperada" aqui, e a decisão é deliberada.
#
# Uma versão anterior desta regra isentava consignado, prova de vida e garantia,
# por serem as que mais faltam em edital de folha. O raciocínio parecia bom e
# estava errado: uma ausência que vira rotina para de ser olhada. Foi
# exatamente numa dessas — a garantia de Pirapó/RS — que o edital revelou punir
# a perda de uma garantia que nunca exigiu (D-010). Se "Q17 em branco é normal"
# estivesse valendo, o alerta não teria saído e ninguém teria conferido.
#
# Frequência não é justificativa. O sistema reporta todo branco da mesma forma e
# deixa o julgamento com quem lê — que é quem sabe se aquele edital deveria ou
# não trazer a informação.


def verificar_nao_localizados(ext: Extracao,
                              modalidade_explicita: str | None = None) -> list[str]:
    """RN-15 — todo "não localizado" é listado, sem exceção."""
    modalidade = modalidade_da(ext, modalidade_explicita)
    vazias, previstas = [], []
    for r in ext.respostas:
        if not ausencia_real(r):
            continue
        if nao_se_aplica(r.id, modalidade):
            previstas.append(r.id)
        else:
            vazias.append(r.id)

    if previstas:
        # Marca na própria resposta, para o relatório e a planilha distinguirem.
        for r in ext.respostas:
            if r.id in previstas:
                r.alertas.append(
                    "não se aplica a esta modalidade — %s"
                    % nao_se_aplica(r.id, modalidade))

    if not vazias:
        if previstas:
            return ["RN-15: %d pergunta(s) em branco, todas por não se aplicarem "
                    "à modalidade %s — %s. Nenhuma é lacuna do documento."
                    % (len(previstas), modalidade,
                       ", ".join(sorted(previstas, key=lambda q: int(q[1:]))))]
        return []

    ids = ", ".join(sorted(vazias, key=lambda q: int(q[1:])))
    aviso = ("RN-15: %d pergunta(s) sem resposta nos documentos — %s. Nenhuma "
             "ausência é tratada como esperada: cada uma é candidata a pedido de "
             "esclarecimento ao órgão, e antes disso vale conferir se o anexo foi "
             "baixado e se a página chegou à recuperação."
             % (len(vazias), ids))
    if previstas:
        aviso += (" Outras %d ficaram em branco por não se aplicarem à "
                  "modalidade %s (%s) e não contam como lacuna."
                  % (len(previstas), modalidade,
                     ", ".join(sorted(previstas, key=lambda q: int(q[1:])))))

    # Muitos brancos de uma vez raramente são o documento.
    if len(vazias) >= 5:
        aviso += (" Com %d de uma vez, a hipótese mais provável não é o edital "
                  "ser omisso: é falta de insumo." % len(vazias))
    return [aviso]


def verificar_unidade_q14(ext: Extracao) -> list[str]:
    """RN-12 — vínculos não são pessoas."""
    q14 = ext.por_id("Q14")
    if not q14 or nao_encontrou(q14.resposta):
        return []
    baixo = _normalizar(q14.resposta)
    if any(t in baixo for t in ("vinculo", "matricula", "pessoa", "cpf", "servidores ativos")):
        return []
    return ["RN-12: a Q14 não declara a unidade da contagem (vínculos ou pessoas). "
            "Em Bertioga, 1.896 eram vínculos, e o edital não informava o nº de CPFs."]


# ------------------------------------------- 2b. abrangência do objeto (RN-13)
# Frases que abrem uma definição de objeto. A cláusula da minuta e o item 1.1 do
# edital são as duas que divergiram em Pirapó/RS.
# O objeto de uma licitação é o que está no TÓPICO/CLÁUSULA OBJETO — quase sempre
# um dos primeiros itens do documento. O texto volta a mencionar o objeto dezenas
# de vezes depois disso, e nenhuma dessas menções o define.
#
# As duas versões anteriores desta regra erraram por não respeitar isso:
#   "do objeto" solto  -> engoliu cláusula de multa, de fiscalização e de dano,
#                         e acusou Santo Antônio do Pinhal/SP, que é consistente.
#   "tem por objeto"   -> engoliu a ATA DE CREDENCIAMENTO de Paulo Bento/RS, que
#                         recita o objeto no cabeçalho da sessão. Recital não é
#                         cláusula.
#
# Ficam só três formas, todas de abertura de tópico ou cláusula.
RE_OBJETO = re.compile(
    r"(?:\d\.\s*(?:do\s+)?objeto\b"                  # 1. DO OBJETO / 1.1. OBJETO:
    r"|cl[áa]usula\s+\w+\s*[-–—]\s*objeto"            # CLÁUSULA PRIMEIRA – OBJETO
    r"|constitui\s+objeto"                             # Constitui objeto ... (corpo do item)
    r")", re.I)

# Termos que definem QUEM a folha cobre. A ausência de um deles muda o preço.
#
# A fronteira de palavra não é detalhe: sem ela "ativo" casa dentro de
# "Legisl-ativo", e TODA cláusula que mencione o Poder Legislativo passa a
# declarar que cobre servidores ativos. A minuta de Pirapó, que não cita
# população nenhuma, era lida como se citasse.
#
# "inativo" e "aposentado" são a MESMA população numa folha pública: o RPPS paga
# os dois sob o mesmo rótulo. Tratá-los como conceitos distintos acusava
# Adrianópolis/PR, onde as duas definições do objeto são idênticas e a palavra
# "aposentados" só aparecia mais adiante na janela de uma delas. Pensionista é
# outra coisa — quem recebe por morte do servidor — e continua separado.
POPULACAO = {
    "ativos": r"\bativos?\b",
    "inativos/aposentados": r"\binativos?\b|\baposentad[oa]s?\b",
    "pensionistas": r"\bpensionistas?\b",
}
POPULACAO_RE = {nome: re.compile(p) for nome, p in POPULACAO.items()}

# A janela só conta como DEFINIÇÃO de objeto se falar da folha. Sem esta porta,
# "do objeto" casa em cláusula de multa ("1% sobre o valor do objeto") e em
# "DO RECEBIMENTO DO OBJETO", que não definem abrangência nenhuma.
RE_DEFINE_FOLHA = re.compile(r"folha")


def _populacao_declarada(trecho: str) -> frozenset:
    baixo = _normalizar(trecho)
    return frozenset(nome for nome, rx in POPULACAO_RE.items() if rx.search(baixo))


def verificar_objeto(ext: Extracao) -> list[str]:
    """RN-13 — a abrangência do objeto é a mesma em todos os documentos?

    Nasceu de um caso que passou por TODAS as outras checagens. Em Pirapó/RS o
    edital licita "ativos, inativos e pensionistas" (item 1.1) e a minuta de
    contrato, na mesma pasta, diz apenas "Poderes Executivo e Legislativo". Os
    inativos são 31,9% da folha.

    Quatro execuções — Opus, Sonnet, Haiku e a de produção — responderam a Q2
    com ancoragem perfeita. Cada uma citou UM dos dois documentos, nenhuma
    percebeu que o outro dizia coisa diferente, e nenhuma marcou conflito. A
    ancoragem não podia pegar isso: os dois trechos existem e os dois são
    literais. Só comparar os documentos ENTRE SI pega.
    """
    vistos: dict[frozenset, list[str]] = {}
    for p in ext.paginas:
        texto = p.texto or ""
        for m in RE_OBJETO.finditer(texto):
            janela = texto[m.start():m.start() + 600]
            if not RE_DEFINE_FOLHA.search(_normalizar(janela)):
                continue
            # O conjunto VAZIO é informação, não ausência de informação: a minuta
            # de Pirapó define o objeto sem citar população alguma, e é
            # exatamente essa omissão que vale 31,9% da folha. Descartar o vazio
            # apagaria o caso que a regra existe para pegar.
            pop = _populacao_declarada(janela)
            onde = "%s p.%d" % (p.arquivo, p.numero)
            lista = vistos.setdefault(pop, [])
            if onde not in lista:   # a mesma pagina casa "DO OBJETO" e "Constitui objeto"
                lista.append(onde)

    if len(vistos) < 2:
        return []

    # O conjunto mais amplo é a referência; o que falta nos outros é o risco.
    amplo = max(vistos, key=len)
    if not amplo:
        return []

    faltas = []
    for pop, ondes in sorted(vistos.items(), key=lambda kv: len(kv[0])):
        ausentes = amplo - pop
        if ausentes:
            faltas.append("%s omite %s"
                          % (", ".join(ondes), ", ".join(sorted(ausentes))))
    if not faltas:
        return []

    return ["RN-13: a abrangência do objeto NÃO é a mesma em todos os documentos. "
            "Mais amplo: %s (%s). %s. Confira qual redação vai para o contrato "
            "ASSINADO — é ela que define o que se recebe."
            % (", ".join(sorted(amplo)), ", ".join(vistos[amplo]),
               " · ".join(faltas[:4]))]


# ---------------------------------------------------------- famílias de critério
#
# "MAIOR OFERTA" e "Maior lance" sao a MESMA COISA: ganha quem oferece mais.
# O campo `criterioJulgamentoNome` do PNCP so aceita a nomenclatura do art. 33,
# e o edital escreve em portugues de licitacao -- "maior oferta", "maior preco
# ofertado", "maior percentual de repasse". Divergencia de PALAVRA nao e
# divergencia de CRITERIO.
#
# Isto existe porque as duas comparacoes que o projeto tinha estavam erradas,
# em direcoes opostas:
#
#   verificador.verificar_contra_api  exigia substring exata. "MAIOR OFERTA"
#                                     contra "Maior lance" -> ALERTA FALSO, em
#                                     3 das 11 extracoes do acervo.
#   43_cruzar_api.py                  comparava so a PRIMEIRA PALAVRA. "maior"
#                                     casa com lance, oferta, desconto e preco
#                                     indiferentemente -- entao "Maior lance"
#                                     contra "Maior desconto" dava OK. Foi essa
#                                     regra que produziu o "6 de 6 conferem".
#
# Estrito demais gera alarme falso; frouxo demais gera conforto falso. O que o
# dominio tem sao FAMILIAS, e a comparacao certa e entre familias.
FAMILIAS_CRITERIO = {
    "maior_oferta": (
        "maior lance", "maior oferta", "maior preco", "maior valor",
        "maior lanco", "maior percentual", "maior retorno", "maior remuneracao",
        "melhor oferta", "maior arrematacao", "maior repasse"),
    "maior_desconto": ("maior desconto", "maior taxa de desconto"),
    "menor_preco": ("menor preco", "menor valor", "menor lance"),
    "tecnica": ("melhor tecnica", "tecnica e preco", "conteudo artistico"),
    "nao_se_aplica": ("nao se aplica", "sem criterio", "nao ha criterio",
                      "nao ha julgamento"),
}


def familia_criterio(texto: str) -> str | None:
    """
    A qual familia de criterio este texto pertence, se a alguma.

    A ORDEM IMPORTA, e nao por acaso. Rio Branco/AC responde "Nao se aplica
    pregao; o criterio de julgamento da proposta e o maior retorno economico".
    O "nao se aplica" fala da MODALIDADE; o criterio de julgamento esta ali,
    explicito, logo depois. Entao um criterio real encontrado no texto manda
    sobre o "nao se aplica" -- e `nao_se_aplica` so vence quando nada mais
    aparece. Por isso ela e testada por ultimo.
    """
    t = _normalizar(texto or "")
    if not t:
        return None
    for fam, termos in FAMILIAS_CRITERIO.items():
        if fam == "nao_se_aplica":
            continue
        if any(x in t for x in termos):
            return fam
    if any(x in t for x in FAMILIAS_CRITERIO["nao_se_aplica"]):
        return "nao_se_aplica"
    return None


# ---------------------------------------------------------------- 3. cruzamento
def verificar_contra_api(ext: Extracao, itens: list[dict] | None) -> list[str]:
    """
    Confere Q5 e Q4 contra os campos estruturados da API. Custa zero e tem alto poder
    de detecção: divergência aqui costuma significar que se leu o documento ERRADO.
    """
    if not itens:
        return []
    alertas = []
    q5 = ext.por_id("Q5")
    if q5 and not nao_encontrou(q5.resposta):
        valores = {it.get("valorTotal") for it in itens if it.get("valorTotal")}
        nums = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", q5.resposta)
        extraidos = {float(n.replace(".", "").replace(",", ".")) for n in nums}
        if valores and extraidos and not (valores & extraidos):
            alertas.append(
                "Q5 diverge da API: documento diz %s, API informa %s. "
                "Suspeita de leitura do documento superado (RN-04)."
                % (sorted(extraidos), sorted(valores)))
    q4 = ext.por_id("Q4")
    if q4 and not nao_encontrou(q4.resposta):
        brutos = {(it.get("criterioJulgamentoNome") or "").strip() for it in itens}
        brutos.discard("")
        fam_api = {familia_criterio(c) for c in brutos} - {None}
        fam_doc = familia_criterio(q4.resposta)
        # AUSENCIA NAO E OPOSTO.
        #
        # Em contratacao direta o campo estruturado traz "Nao se aplica" --
        # correto, porque nao ha disputa formal. Mas o edital costuma dizer
        # COMO a proposta sera julgada mesmo assim. Acusar isso como
        # divergencia seria punir o documento por ser mais informativo que a
        # API, e encheria a fila de revisao com o oposto de um problema.
        so_ausencia = fam_api == {"nao_se_aplica"}
        if fam_api and fam_doc and fam_doc not in fam_api and not so_ausencia:
            alertas.append(
                "Q4 diverge da API: o documento julga por %s e a API declara %s "
                "(%s). Sao criterios OPOSTOS, nao sinonimos — confira qual vale."
                % (fam_doc, "/".join(sorted(fam_api)), ", ".join(sorted(brutos))))
        elif fam_api and not fam_doc:
            alertas.append(
                "Q4 nao encaixou em nenhuma familia de criterio conhecida: %r. "
                "A API declara %s. Pode ser redação nova — vale olhar e, se for o "
                "caso, somar o termo a FAMILIAS_CRITERIO."
                % (q4.resposta[:60], ", ".join(sorted(brutos))))
    return alertas


# ---------------------------------------------------------------- 4. sanidade
def verificar_sanidade(ext: Extracao) -> list[str]:
    alertas = []
    q1 = ext.por_id("Q1")
    if q1 and not nao_encontrou(q1.resposta):
        if not re.search(r"\d{2}/\d{2}/\d{4}", q1.resposta):
            alertas.append("Q1 não contém data no formato DD/MM/AAAA")
    q9 = ext.por_id("Q9")
    if q9 and not nao_encontrou(q9.resposta):
        m = re.search(r"(\d{1,3})\s*\(?[^)]{0,20}\)?\s*(?:meses|mes)", _normalizar(q9.resposta))
        if m and not (6 <= int(m.group(1)) <= 120):
            alertas.append("Q9: vigência de %s meses está fora da faixa plausível" % m.group(1))
    faltando = [p.id for p in POR_ID.values() if ext.por_id(p.id) is None]
    if faltando:
        alertas.append("perguntas sem resposta: %s" % ", ".join(sorted(faltando)))
    return alertas


# ---------------------------------------------------------------- relatório
@dataclass
class Relatorio:
    aprovadas: int = 0
    revisar: int = 0
    reprovadas: int = 0
    nao_localizado: int = 0
    ancoradas: int = 0            # trecho conferido na página citada
    alertas_globais: list[str] = None

    @property
    def total(self) -> int:
        return self.aprovadas + self.revisar + self.reprovadas

    @property
    def respondidas(self) -> int:
        return self.total - self.nao_localizado

    @property
    def taxa_ancorada(self) -> float:
        """
        Mede APENAS a ancoragem: o trecho existe na página citada?

        Deliberadamente separada do veredito. Uma resposta pode estar perfeitamente
        ancorada e ainda ir para revisão por conflito entre documentos ou confiança
        baixa — são coisas diferentes, e misturá-las escondia a métrica que importa.
        """
        return (self.ancoradas / self.respondidas) if self.respondidas else 0.0

    def __str__(self) -> str:
        return ("%d aprovadas · %d revisão · %d reprovadas · %d não localizado "
                "| ancoragem %d/%d (%.0f%%)"
                % (self.aprovadas, self.revisar, self.reprovadas, self.nao_localizado,
                   self.ancoradas, self.respondidas, 100 * self.taxa_ancorada))



def modalidade_da(ext: Extracao, explicita: str | None = None) -> str:
    """Descobre a modalidade a partir da Q3, da modalidade informada e do nome.

    Três fontes porque nenhuma é confiável sozinha: a Q3 é resposta de modelo,
    a explícita vem do portal (o campo estruturado do PNCP, quando quem chama
    o tem) e o nome da pasta vem do coletor e pode estar abreviado. Basta uma
    delas reconhecer.

    A explícita entra NO LUGAR do nome da pasta, nunca na frente da Q3. A Q3
    tem precedência desde sempre; invertê-la mudaria vereditos toda vez que
    modelo e portal discordam, e o acervo inteiro foi verificado nessa ordem.
    """
    q3 = ext.por_id("Q3")
    return (modalidade_chave(q3.resposta if q3 else "")
            or modalidade_chave(explicita or "")
            or modalidade_chave(ext.licitacao))


def verificar(ext: Extracao, itens_api: list[dict] | None = None,
              modalidade: str | None = None) -> Relatorio:
    """Roda todas as checagens e carimba cada resposta. Nada aqui usa IA.

    `modalidade` é a informada por quem chama (o portal, via API); ver
    `modalidade_da` para onde ela entra na ordem de precedência.
    """
    rel = Relatorio(alertas_globais=[])

    ancoradas = 0
    for r in ext.respostas:
        veredito, alertas = verificar_ancoragem(r, ext)
        r.veredito, r.alertas = veredito, list(alertas)
        # O nome canônico sai da MESMA resolução que localizou a página: se a
        # ancoragem aceitou "EDITAL.pdf" como apelido de "01 - Edital - EDITAL.pdf",
        # o link tem que apontar para o segundo. Fica None quando a citação não
        # resolve — e aí o relatório já mostra "não localizado" em vez de link.
        pg = ext.pagina(r.arquivo, r.pagina) if (r.arquivo and r.pagina) else None
        r.arquivo_canonico = pg.arquivo if pg is not None else None
        if veredito == APROVADO and not ausencia_real(r):
            ancoradas += 1        # registrado ANTES de rebaixar por conflito/confiança
        if r.conflito:
            r.alertas.append("conflito relatado pelo extrator: %s" % r.conflito)
            if r.veredito == APROVADO:
                r.veredito = REVISAR
        if r.confianca == "baixa" and r.veredito == APROVADO:
            r.veredito = REVISAR
            r.alertas.append("confiança baixa declarada pelo extrator")

    globais = (verificar_piramide(ext) + verificar_unidade_q14(ext)
               + verificar_objeto(ext) + verificar_nao_localizados(ext, modalidade)
               + verificar_contra_api(ext, itens_api) + verificar_sanidade(ext))
    rel.alertas_globais = globais

    # Alerta global recai sobre a pergunta pela REGRA que o gerou, nunca por
    # menção de texto.
    #
    # A versão anterior perguntava se a string "Q13" aparecia na mensagem, e a
    # RN-15 lista os IDs em branco — então "Q5, Q7, Q10, Q12, Q13, ..." fazia o
    # aviso GLOBAL sobre lacunas virar alerta da linha da pirâmide. A Q13 de Rio
    # Branco/AC ficava marcada por um alerta que não falava dela.
    #
    # Roteamento por regra também documenta a intenção: quem lê a tabela sabe
    # qual regra cobre qual pergunta, o que a busca por substring escondia.
    ROTA = {"RN-09": "Q13", "RN-10": "Q13", "RN-11": "Q13", "RN-14": "Q13",
            "RN-12": "Q14", "RN-13": "Q2"}
    for g in globais:
        prefixo = g.split(":", 1)[0].strip()
        alvo = ROTA.get(prefixo)
        if not alvo:
            continue          # RN-15 e outros avisos de conjunto ficam só no topo
        r = ext.por_id(alvo)
        if not r:
            continue
        if r.veredito == APROVADO:
            r.veredito = REVISAR
        r.alertas.append(g)

    rel.ancoradas = ancoradas
    for r in ext.respostas:
        if ausencia_real(r):
            rel.nao_localizado += 1
        if r.veredito == APROVADO:
            rel.aprovadas += 1
        elif r.veredito == REVISAR:
            rel.revisar += 1
        else:
            rel.reprovadas += 1
    return rel


__all__ = ["verificar", "modalidade_da", "nao_encontrou", "Relatorio",
           "verificar_ancoragem", "verificar_piramide",
           "verificar_unidade_q14", "verificar_contra_api", "verificar_sanidade",
           "familia_criterio", "FAMILIAS_CRITERIO",
           "APROVADO", "REVISAR", "REPROVADO", "LIMIAR_ANCORAGEM"]
