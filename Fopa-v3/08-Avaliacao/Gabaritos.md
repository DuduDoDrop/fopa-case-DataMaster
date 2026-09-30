---
tipo: referencia
familia: avaliacao
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/15_acuracia.py
  - scripts/22_recall.py
tags: [avaliacao, gabarito, acuracia, caso-de-teste]
---

# Gabaritos

> [!abstract] Em uma frase
> Duas licitações reais — **Pirapó/RS** (38 páginas, contexto completo) e **Bertioga/SP** (115 páginas, RAG) — foram lidas integralmente e transformadas em gabaritos de **fatos**: para cada pergunta, os fatos que a resposta certa precisa conter, os que a enriquecem e a página onde cada um foi conferido; é contra eles que a acurácia de modelos e configurações é medida, sem nenhum modelo como juiz.

## Papel na solução

A ancoragem prova que o trecho citado existe na página; **não prova que a resposta responde à pergunta**. Um extrator pode citar um trecho verdadeiro e irrelevante: ancoragem 100%, acurácia zero. Os gabaritos existem para medir a segunda coisa ([[Métricas]]).

Comparar texto livre com texto livre exigiria um juiz — e usar um modelo como juiz devolveria à avaliação a subjetividade que a solução existe para eliminar. Por isso o gabarito **não guarda a redação certa**: guarda fatos verificáveis.

| Campo do gabarito | Para que serve | Métrica |
|---|---|---|
| `fatos_obrigatorios` | sem eles a resposta está errada | **acurácia** (a pergunta conta como certa se todos aparecem) |
| `fatos_desejaveis` | contexto, ressalva, divergência | **completude** (quantos aparecem, do total) |
| `fonte` | arquivo e página onde o fato foi conferido | auditoria do próprio gabarito |
| `observacao` | a armadilha daquela pergunta | leitura humana |

A comparação normaliza a grafia **sem** destruir números: tira acentos e caixa, trata "09h00" e "09:00" como o mesmo horário e "21 de setembro de 2026" como "21/09/2026", tira o zero à esquerda ("05 dias") — e preserva vírgula e ponto, para que "2.500,00" nunca case com "250.000,00".

> [!important] O que um gabarito assim é, e o que não é
> É **auditável**: todo item pode ser reconferido pela citação e pela página. **Não** é um gabarito validado por um especialista de folha, que julgaria também a relevância comercial de cada resposta. E são dois: n = 2 licitações com gabarito.

## Por que estas duas

Foram escolhidas para variar o que importa: **tamanho** (38 × 115 páginas), **modo** (contexto completo × RAG) e **contraditório** (Bertioga tem 4 pedidos de esclarecimento e 3 respostas oficiais — bancos concorrentes perguntando e o município respondendo por escrito). Se a acurácia caísse no caminho do RAG, é em Bertioga que apareceria.

## Pirapó/RS — Concorrência Eletrônica 012/2026

3 documentos, 38 páginas. 24 fatos obrigatórios e 41 desejáveis.

| # | Resposta de referência (resumo) | Onde | A armadilha |
|---|---|---|---|
| Q1 ✦ | 08/10/2026 — propostas até 07:59, abertura às 08:00, disputa às 09:00 | Edital p. 1 | três horários na mesma página; quem envia proposta precisa do 07:59 |
| Q2 | cessão onerosa do direito de pagar a folha (Prefeitura, Câmara e fundo de previdência), 60 meses | Edital p. 1 | a abrangência muda entre o edital e a minuta — a resposta ideal registra a divergência |
| Q3 | Concorrência Eletrônica, Lei 14.133/2021 | Edital p. 1 | — |
| Q4 | maior lance por item, disputa aberta | Edital p. 1 | — |
| Q5 ✦ | R$ 250.000,00 | Edital p. 3; ETP p. 4; TR p. 1 e 8 | o mesmo valor tem **quatro rótulos** ("valor mínimo total aceitável", "valor de referência para fins de negociação", "quantia mínima", "preço mínimo"); é piso de lance, não teto |
| Q6 | intervalo mínimo de 0,5% entre lances | Edital p. 9 | — |
| Q7 | 5 dias úteis da convocação, prorrogável uma vez | Edital p. 12 | — |
| Q8 | o município não desembolsa; o banco paga o lance em até 48 horas da assinatura, corrigido pelo IGPM se atrasar | Edital p. 14 e 18 | "48 horas corridos" no edital, "48 horas" na minuta |
| Q9 ✦ | 60 meses, contados do primeiro dia útil após a divulgação no PNCP | Edital p. 14 e 18 | a minuta não declara termo inicial |
| Q10 | **não há prazo definido**: a instituição deve estar apta "no prazo estabelecido pelo Município" | TR p. 6 | prazo em aberto é risco; a resposta ideal diz que não está fixado |
| Q11 | agência ou posto com caixa e ATM, sistema compatível às custas do banco, cesta gratuita aos servidores, sem tarifa, lance em 48 h | Edital p. 13 e 19 | — |
| Q12 ✦ | **obrigatória** desde a assinatura: agência ou posto no município, com caixa presencial e autoatendimento; e, como condição para assinar, ao menos uma agência física com gerente local | Edital p. 12 e 19 | duas exigências de presença física em lugares diferentes, com redações distintas |
| Q13 ✦ | tabela única: até R$ 2.000 = 32; até 3.000 = 93; até 4.000 = 56; até 5.000 = 72; até 7.000 = 27; até 10.000 = 14; acima = 3 — **soma 297**, igual ao total | Edital p. 2; ETP p. 2; TR p. 2 | a pirâmide está **íntegra** (ao contrário de Bertioga) |
| Q14 ✦ | 297 **matrículas** — o documento não diz se são pessoas distintas | Edital p. 2; TR p. 2 | matrícula não é pessoa |
| Q15 | **não localizado** — não há consignado; a única ocorrência da palavra é "valor consignado no registro" do lance | — | armadilha de busca literal: responder "sim, item 8.7.1" seria erro grave **e ancoraria perfeitamente** |
| Q16 | **não localizado** — nenhuma prova de vida, apesar de o objeto incluir inativos e pensionistas | — | o silêncio do edital é risco de escopo |
| Q17 ✦ | não há cláusula exigindo garantia — **mas** duas cláusulas de penalidade pressupõem que ela exista (perda da "garantia de proposta" e desconto da "garantia prestada") | Edital p. 13 e 16 | contradição interna do edital; dizer só "não localizado" é incompleto, dizer "existe garantia" é errado |

✦ pergunta crítica.

## Bertioga/SP — Pregão Eletrônico 48/2026

9 documentos, 115 páginas. 18 fatos obrigatórios e 49 desejáveis.

| # | Resposta de referência (resumo) | Onde | A armadilha |
|---|---|---|---|
| Q1 ✦ | a sessão de 21/09/2026 às 10h00 foi **suspensa** por comunicado de 18/09/2026, sem nova data | Edital p. 1; Comunicado de suspensão p. 1 | a data vigente **não está no edital** — é o caso que justifica a inclusão forçada de avisos no RAG |
| Q2 | cessão onerosa, com exclusividade, do processamento da folha | Edital p. 2 | — |
| Q3 | Pregão Eletrônico | Edital p. 1 | — |
| Q4 | maior lance global | Edital p. 4 | — |
| Q5 ✦ | R$ 3.208.032,00 | Edital p. 2 e 11 | três rótulos: "valor de referência", "valor mínimo estabelecido", "oferta mínima" |
| Q6 | aumento mínimo de 1% sobre o valor global | Edital p. 13 | — |
| Q7 | 5 dias úteis do recebimento do chamamento | Edital p. 27; Resposta p. 9 | — |
| Q8 | outorga paga em parcela única, em até 30 dias corridos | Edital p. 11; Resposta p. 4 | — |
| Q9 ✦ | 60 meses, prorrogável — e a minuta traz a vigência **em branco** | Edital p. 3 | defeito real do documento a assinar |
| Q10 | 60 dias para **começar a executar** os serviços | Edital p. 3 | "60" aqui são dias; na Q9, meses |
| Q11 | manter autorização do Banco Central, ao menos uma agência, recadastramento dos beneficiários, central 24×7, crédito antecipado em dia não útil, consignado sem exclusividade | Edital p. 43 e 62 | — |
| Q12 ✦ | ao menos uma agência no município, mais central telefônica e canais digitais 24×7 | Edital p. 44; Resposta p. 6 | — |
| Q13 ✦ | pirâmide só da Administração Direta (exclui aposentados e pensionistas) e **truncada**: as faixas somam 1.408 contra 1.896 — faltam 488 vínculos, nas faixas acima de R$ 7.000 | Edital p. 48 | os que faltam são os de maior renda, os que mais valem para o banco |
| Q14 ✦ | **1.896 vínculos**, não pessoas; o edital não informa CPFs | Edital p. 48; Resposta p. 8 | tratar vínculos como clientes superestima o mercado |
| Q15 | consignado **sem exclusividade**; proibida a aplicação automática de proventos sem autorização | Respostas p. 10 e 8 | a receita de crédito não é cativa |
| Q16 | **sim** — recadastramento de todos os beneficiários (item 5.4) | Edital p. 43 | única das 13 licitações da amostra em que a Q16 não é "não localizado" |
| Q17 ✦ | não há exigência expressa de garantia; os 10% citados aparecem num **pedido de esclarecimento** de licitante, não em cláusula do órgão | Edital p. 31 | a primeira leitura humana registrou os 10% como exigência e estava errada; quem corrigiu foi o extrator |

> [!fato] O gabarito também foi conferido
> As citações do gabarito de Bertioga foram reconferidas uma a uma por busca literal do trecho contra o texto da página, e a pirâmide foi transcrita e somada à mão (1.554 + 124 + 120 + 98 = 1.896 na tabela por vínculo). O gabarito é tratado com a mesma exigência de evidência que as respostas.

## O que se aprendeu com os gabaritos

- **O instrumento literal demais reprova acerto.** "05 (cinco) dias úteis" contra "5", "21 de setembro de 2026" contra "21/09/2026", "Total 1.896." com ponto final — as três vezes, a resposta estava certa e o comparador errado. Cada caso virou normalização com teste de controle ("5" continua não casando com "25" nem com "R$ 3.500,00") ([[A medição que mediu o medidor]]).
- **As armadilhas são o teste.** Um extrator que acerta as 17 de Bertioga — suspensão fora do edital, três rótulos, unidade errada, população truncada, garantia citada só em esclarecimento — lida com o que aparece numa licitação real de porte.

## Relacionadas

[[MOC Avaliação]] · [[Métricas]] · [[Harness de avaliação]] · [[Resultados medidos]] · [[Comparação de modelos]] · [[Questionário — as 17 perguntas]] · [[Verificador determinístico]]
