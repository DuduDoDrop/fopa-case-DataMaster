---
tipo: referencia
familia: ia
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/modelos.py
  - api/modelos_ia.py
  - api/consultas.py
  - api/rotas_extracao.py
  - db/004_perguntas_execucoes_chamadas_respostas.sql
  - db/035_trava_ia_com_edital.sql
  - db/045_gastos_ia.sql
  - n8n/workflows/W23.json
tags: [ia, custo, orcamento, fatura, finops]
---

# Custo por edital

> [!abstract] Em uma frase
> Uma extração completa custa **de menos de R$ 1 a cerca de R$ 5** conforme o modelo, o tamanho do edital e o cache; o custo de cada chamada é calculado **na hora** a partir dos tokens informados pelo provedor, um **teto diário** configurável impede que a automação gaste além do combinado, e o gasto real é conferido na **fatura** dos fornecedores.

## Papel na solução

O custo de modelo é pequeno perto do que cada licitação decide, mas precisa ser **previsível, conferível e limitado**: previsível para escolher o modelo, conferível para não haver número inventado, e limitado para que uma fila grande nunca vire uma conta surpresa. A solução otimiza contra trabalho humano, não contra centavos de API — um modelo mais fraco que gere mais revisão aumenta o custo total —, mas nunca gasta sem teto.

## De onde vem o custo de uma extração

| Componente | Peso medido | Alavanca |
|---|---|---|
| **Entrada** (o documento) | 76% a 86% do custo | quanto texto se manda ([[RAG com BM25]]) e quantas vezes se paga cheio ([[Cache de prompt e ordem do prompt]]) |
| Saída (resposta + raciocínio) | 14% a 24% | o esforço de raciocínio — cortar pela metade corta ~11% ([[Chain-of-thought e esforço de raciocínio]]) |
| Reforço do [[Best-of-N]] | só quando há resposta que falhou | quase grátis com o documento em cache; custo cheio no RAG |

## Quanto custa, medido

| Situação medida | Custo |
|---|---|
| Itapecuru Mirim/MA, produção, 28/09/2026 — GPT-6 Luna (esforço `medium`), contexto completo, 60 páginas, 5 chamadas (3 lotes + 2 de reforço, R$ 0,08) | **R$ 0,20** |
| Itapecuru Mirim/MA, produção, 28/09/2026 — Claude Haiku 4.5, contexto completo, 60 páginas, 5 chamadas (3 lotes + 2 de reforço) | **R$ 0,78** |
| Pirapó/RS, 38 páginas — Claude Opus 5.5, contexto completo, v3.1 (com cache e reforço) | **R$ 2,50** |
| Bertioga/SP, 115 páginas — Claude Opus 5.5, RAG, v3.1 | R$ 2,52 |
| Pirapó/RS — GPT-5.6 Sol, contexto completo, v3.1 | R$ 4,03 |
| Bertioga/SP — GPT-5.6 Sol, RAG, v3.1 | R$ 2,63 |
| Pirapó/RS — Claude Opus 5, contexto completo, sem cache no documento (22/09) | R$ 4,79 |
| Bertioga/SP — Claude Opus 5, RAG (22/09) | R$ 2,91 |

As medições de 28/09 usaram esforço `high`; produção usa `medium`, que reduz a saída. A tela do botão "Extrair com IA" mostra uma estimativa por modelo antes do clique — US$ 0,65 para o Claude Opus 5.5 num edital de referência, sem contar o cache ([[Modelos e provedores#O catálogo]]).

> [!fato] A licitação maior custou menos
> Bertioga tem três vezes as páginas de Pirapó e custou 39% menos no mesmo modelo (22/09), porque passou do limite e foi em RAG. Não é o tamanho do edital que governa a conta — é a política de recuperação.

## Como o custo é calculado e gravado

1. **Na hora de cada chamada**, o W23 manda ao worker (`POST /custo`) o modelo e os tokens que o provedor informou: entrada nova, gravação de cache, leitura de cache e saída.
2. O worker aplica a tabela de preços do código: `custo = entrada × preço + gravação × preço × 1,25 + leitura × preço × 0,10 + saída × preço de saída`, e converte para reais pelo câmbio configurado (`FOPA_USD_BRL`, 5,10 por padrão).
3. Cada chamada vira uma linha de `chamadas_modelo` com os tokens, US$, R$ e `preco_conhecido`. É sobre essa tabela que a view `gasto_diario` soma o gasto do dia — inclusive os lotes pagos de uma execução que falhou no meio, que nunca somem da conta.
4. A execução (`execucoes_modelo`) guarda o total, e o [[Página Detalhe da licitação|detalhe]] e o e-mail mostram "R$ 0,78".

**Regras que evitam número falso:**

- **Preço desconhecido é nulo, nunca zero.** Uma execução de modelo sem preço na tabela grava `usd` e `brl` nulos e aparece como "n/d". R$ 0,00 só existe quando o custo é zero de verdade (os provedores de ensaio).
- **Respostas importadas do agente** não passaram pela API: aparecem como "sem preço de API", nunca como R$ 0,00 nem como estimativa ([[ADR-014 Extração por agente, sem API]]).
- **O preço veio de fonte conferida:** tabela oficial do Claude; tabela e fatura da OpenAI, que bateram dentro de 0,01%. Uma conferência da fatura da Anthropic pegou uma unidade enganosa — o valor vinha em **centavos** com a moeda "USD" —, e o relatório teria mostrado 100 vezes o gasto real se o custo não fosse ancorado em `tokens × preço`.

## O teto do dia

| Controle | Onde | Como funciona |
|---|---|---|
| **Teto de R$ por dia** | [[Página Admin]] → Orçamento (`orcamento.teto_brl_dia`; em produção, **R$ 25,00**) | a vaga de extração só é dada se couber no teto **o gasto do dia + R$ 6,56 por extração em curso e pela nova** — R$ 6,56 é o pior caso medido por edital, fixado como reserva |
| **Limite de simultaneidade** | `configuracao.max_extracoes` (4) | no máximo 4 licitações em `extraindo` ao mesmo tempo |
| **Máximo por execução da fila** | Orçamento (vazio em produção = sem limite extra) | quantas licitações uma rodada do [[W10 Fila]] pode reivindicar |
| **Reforço dentro do teto** | `POST /reforco` | com o gasto do dia já no teto, não há reforço: fica o original e a extração segue |

- A vaga é tomada por uma função do banco sob **trava exclusiva** (`pg_advisory_xact_lock`), para que duas extrações simultâneas não passem juntas pelo mesmo teto ([[Funções e views do banco]]).
- **Sem orçamento**, a licitação vai para `aguardando_orcamento` e é tentada de novo uma hora depois — não conta como falha ([[Ciclo de vida de uma licitação]]).
- Com o teto de R$ 25 e a reserva de R$ 6,56, cabem até três extrações novas em paralelo num dia sem gasto; a quarta espera.
- **Limite conhecido:** a reserva cobre a extração sem reforço; com várias extrações em curso, as rodadas de reforço já iniciadas podem passar um pouco do teto.

## O gasto real, pela fatura

O [[Página Painel|Painel]] mostra o gasto com IA **cobrado**, não estimado:

- **OpenAI e Anthropic:** a leitura mais recente da **fatura** pela API administrativa de cada fornecedor (`scripts/82_gastos_ia.py`, gravada em `gastos_ia`).
- **Jev:** a última leitura do painel da TypeSafe (ela não tem API de faturamento) somada ao que o sistema mediu depois dela (`sinais_jev.usd`).
- Provedor sem leitura aparece "sem leitura", nunca US$ 0.

Em 28/09/2026: **US$ 47,82 ≈ R$ 243,89 desde 21/09** — Claude US$ 24,06, Jev US$ 17,85, GPT US$ 5,91. É a organização inteira no período: construção, medições e produção.

E os quadros de custo das licitações, no mesmo dia:

| Recorte | Extraídas | Custo das extrações | Observação |
|---|---|---|---|
| Painel (licitações ativas) | 59 de 71 | R$ 37,02 | 49 rodaram fora da API (importação do agente) |
| Histórico | 2.019 de 2.020 | R$ 15,54 | 2.011 rodaram fora da API; 1 sem preço |

## Custo de operação além do modelo

O custo de modelo é por extração; a infraestrutura é fixa (servidor, armazenamento, domínio, e-mail) e está em [[Custo de infraestrutura]]. Coleta, download, OCR, verificação, reverificação e a regra de escopo custam **R$ 0,00** em modelo — só a extração e o Jev são pagos por uso.

## Relacionadas

[[MOC IA]] · [[Modelos e provedores]] · [[Cache de prompt e ordem do prompt]] · [[RAG com BM25]] · [[Best-of-N]] · [[W23 Extrair]] · [[Página Admin]] · [[Página Painel]] · [[Custo de infraestrutura]] · [[Escalabilidade]] · [[ADR-012 Segundo provedor de modelo]]
