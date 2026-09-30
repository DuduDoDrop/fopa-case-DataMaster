---
tipo: negocio
familia: negocio
status: verificado
atualizado: 2026-09-28
tags: [negocio, ganho, tempo, eficiencia]
---

# Ganho para o negócio

> [!abstract] Em uma frase
> Três ganhos, cada um com a evidência que o sustenta: **tempo** (a informação chega na manhã da descoberta em vez de D+3 — o prazo interno de 5 dias volta a ser inteiro), **trabalho** (a área deixa de procurar a resposta no edital e passa a conferir uma fila curta, com o trecho e a página na mão) e **qualidade** (as divergências que mudam o lance aparecem sozinhas).

## Papel na solução

Liga o que a solução faz ao que o banco ganha, sem número que não tenha fonte: o que é medição da solução está marcado como medido; o que é dado interno do banco está marcado como informado pelo banco.

## O que está em jogo

O banco investe cerca de **R$ 1,05 bilhão por ano** na compra de folhas de pagamento (informado pelo banco). Nessa escala, o ganho não está no custo de ler editais: está em **não perder** uma licitação por falta de tempo de análise e em **não calibrar um lance** sobre um dado errado — uma data suspensa, uma pirâmide lida pela metade, vínculos contados como pessoas.

## Tempo

| | Hoje (informado pelo banco) | Com a solução |
|---|---|---|
| quando a informação chega | D+3 da publicação | na primeira rodada da descoberta depois do registro no PNCP — às 06:00 de cada dia útil, ou a qualquer hora pelo "Verificar agora" |
| dias úteis para analisar, dos 5 da regra interna | **2** | **os 5** — o que a descoberta encontra na manhã seguinte à publicação chega com o prazo interno praticamente inteiro |
| quando o documento está lido | junto com o PDF do fornecedor | minutos depois da descoberta (Itapecuru Mirim/MA: e-mail às 06:04, documento baixado e lido às 06:20) |
| quando as 17 respostas estão prontas | depois da leitura manual | cerca de 2 minutos depois do clique em "Extrair com IA" (Itapecuru: pedido às 10:22, publicado às 10:24, e-mail às 10:25) |

E o PNCP disponibiliza a licitação pela API **antes** da data oficial de publicação em vários casos (informado pelo banco): lendo o portal diretamente, a solução passa a jogar no mesmo tempo dos concorrentes que já fazem isso.

## Trabalho

- **De procurar para conferir.** Cada resposta chega com o trecho literal e o link para a página exata; a pessoa confere um parágrafo, não lê o edital inteiro.
- **Uma fila curta e justificada.** Nas extrações do histórico, cerca de **16%** das respostas ficaram para revisão (5.473 de ~34 mil), cada uma com o motivo — conflito entre documentos, regra que não fechou, ausência, citação em outra página ([[Métricas]]). Quase toda licitação tem ao menos um item para olho humano — é o desenho: a máquina resolve a maior parte e entrega o resto com o motivo.
- **Sem retrabalho por retificação.** O acompanhamento de documentos novos devolve a licitação à fila quando o edital muda.

## Qualidade

| Erro que passaria | O que a solução faz |
|---|---|
| data vencida (sessão suspensa por aviso) | lê todos os documentos com precedência; o aviso de retificação entra sempre no contexto |
| "valor estimado" lido como "valor mínimo" | transcreve o rótulo como está e relata a divergência |
| pirâmide lida pela metade | confere a soma das faixas com o total declarado |
| vínculos contados como pessoas | exige a unidade da contagem |
| objeto do contrato diferente do edital | compara as definições de objeto entre documentos |
| resposta inventada, plausível | reprova: o trecho precisa existir na página, com os números exatos |

Na produção, **99,96%** das respostas do histórico têm o trecho conferido na página citada ([[Resultados medidos]]).

## Custo

- **IA:** de menos de R$ 1 a cerca de R$ 5 por edital, conforme o modelo e o tamanho, com **teto diário** e o gasto conferido na fatura ([[Custo por edital]]).
- **Infraestrutura:** uma instância pequena e armazenamento no Brasil ([[Custo de infraestrutura]]).
- **O contrato com o fornecedor atual**, de cerca de **R$ 100 mil por ano** (informado pelo banco), é custo que a solução substitui. Com o volume real — mediana de 2 licitações de folha por dia, cerca de 60 por mês —, extrair todas no modelo padrão ficaria em torno de **R$ 150 por mês** em IA, mais a infraestrutura ([[Escalabilidade]], [[Custo de infraestrutura]]).

## Inteligência de mercado

O que hoje não existe consolidado: quem comprou cada folha, por quanto, com qual contrato e até quando; o que voltou ao portal depois de deserta ou fracassada; e os contratos que vencem nos próximos meses — o sinal de quando o órgão licita de novo ([[Concorrência e mercado]]).

## Relacionadas

[[MOC Negócio]] · [[Problema de negócio]] · [[Proposta de valor]] · [[Métricas]] · [[Resultados medidos]] · [[Escalabilidade]]
