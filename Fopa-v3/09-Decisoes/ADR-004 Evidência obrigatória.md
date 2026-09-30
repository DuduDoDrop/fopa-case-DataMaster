---
tipo: decisao
familia: decisoes
adr: 4
data: 2026-09-22
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, antialucinacao, verificador, nucleo]
---

# ADR-004 — Evidência obrigatória

> [!abstract] Em uma frase
> **Nenhuma resposta é publicada sem arquivo, página e trecho literal**, e um verificador **sem IA** confere que o trecho existe naquela página; "não localizado" é resposta correta, e quem gera a resposta nunca é quem a verifica.

## Problema

O entregável são respostas usadas para decidir lances de valor alto. Uma resposta alucinada é **indistinguível** de uma correta: mesmo formato, mesma confiança, página citada. O modo de falha perigoso não é o erro visível — é o erro plausível, que nenhuma revisão por amostragem detecta de forma confiável.

## Opções

| Opção | Avaliação |
|---|---|
| Confiar no modelo | é exatamente o risco que inviabiliza o uso no banco |
| Verificar com um segundo modelo | herda o mesmo modo de falha que deveria detectar: uma alucinação plausível confirmada por outra |
| Revisão humana por amostragem | não escala e não detecta erro plausível |
| **Evidência obrigatória + verificação determinística** | transforma alucinação de risco invisível em falha detectável |

## O que foi medido

- **Ancoragem em produção:** 99,96% das respostas do histórico (25.114 de 25.122) com o trecho conferido na página citada ([[Métricas]]).
- **A guarda numérica:** a primeira versão da ancoragem aprovava citações com um algarismo trocado (similaridade 0,98). A folga passou a valer só para letra; todo número citado precisa estar na página — sem regressão em 190 respostas reais ([[Verificador determinístico]]).
- **Os dois caminhos de injeção de prompt** foram testados contra o próprio verificador:

| Caminho | Situação |
|---|---|
| o modelo obedece a uma instrução plantada e **inventa** um trecho misturando valor falso com frase verdadeira | **fechado** pela guarda numérica |
| a instrução maliciosa está **impressa** no edital e o modelo cita o texto dela | a ancoragem aprova, e está certa: o trecho existe. É limite do método — verificar a existência do texto não verifica a veracidade dele. A defesa é detectar o texto escondido com cara de instrução, marcar a licitação e mandar para olho humano ([[Injeção de prompt e defesas]]) |

## Escolha

- Toda resposta carrega `arquivo`, `pagina` (física) e `trecho_literal`; o esquema de saída exige os campos.
- O [[Verificador determinístico]] confere cada trecho contra a página congelada; o que não confere é REPROVADO, o que confere em outra página é corrigido e vai para revisão.
- "Não localizado" é resposta correta e preferível a uma tentativa — e, na v3, toda ausência vai para revisão humana.
- **Quem gera não verifica:** nenhum modelo participa da verificação. O Jev, que é um modelo, só dá sinal e nunca escreve veredito.

## O que custa

- Mais campos, mais armazenamento, pipeline mais lento.
- Mais "não localizado" — e isso é desejável: um sistema que responde 12 de 17 e admite as outras 5 é melhor que um que responde 17 com 3 erradas.
- A ancoragem é piso de integridade, não métrica de qualidade: uma resposta ancorada pode não responder à pergunta — por isso existem o gabarito e o sinal "sustenta?" ([[Métricas]]).

## Onde vive em produção

`scripts/fopa/verificador.py` (rodado pelo worker no `/verificar` e no `/reverificar`); as tabelas `verificacoes` e `verificacao_respostas`; o relatório com link para a página exata; o teste de guarda que impede o Jev de escrever veredito.

## O que reabriria a decisão

Nada no horizonte: é o princípio que torna a solução utilizável num banco. O que pode mudar são as regras do verificador — sempre com versão nova e reverificação comparável ([[ADR-011 Uma regra precisa saber quando falhou em ler]]).

## Relacionadas

[[MOC Decisões]] · [[Verificador determinístico]] · [[Prompt do extrator]] · [[Injeção de prompt e defesas]] · [[ADR-005 Info é arquivo mais página física]] · [[ADR-011 Uma regra precisa saber quando falhou em ler]] · [[Proposta de valor]]
