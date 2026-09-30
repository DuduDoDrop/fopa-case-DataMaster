---
tipo: negocio
familia: negocio
status: verificado
atualizado: 2026-09-28
tags: [negocio, valor, produto]
---

# Proposta de valor

> [!abstract] Em uma frase
> A solução entrega, **na manhã em que a licitação aparece no PNCP**, o aviso por e-mail, os documentos baixados e lidos, as **17 respostas com arquivo, página e trecho conferidos sem IA** a partir de um clique, a fila curta do que precisa de olho humano e o mapa de quem compra folha no país — o que o fornecedor atual entrega, **mais cedo, com prova e com inteligência de mercado**.

## Papel na solução

É o porquê de cada parte existir. A proposta tem três camadas: fazer o que o fornecedor faz, fazer melhor e fazer o que ele não faz.

## 1. Paridade — o que o fornecedor faz

| Entrega do fornecedor | Na solução |
|---|---|
| a lista de licitações de folha | a **descoberta** roda às 06:00 de cada dia útil, com regra de escopo e segunda opinião de IA; o botão "Verificar agora" consulta a qualquer hora ([[W01 Descoberta]]) |
| o documento | todos os documentos da licitação baixados, convertidos para PDF e lidos, com OCR onde é imagem ([[W21 Baixar]], [[W22 Ler]]) |
| o questionário preenchido | as 17 respostas, extraídas por IA a pedido, com o custo mostrado antes ([[W23 Extrair]]) |

## 2. Superioridade — fazer melhor

| Dimensão | Fornecedor (informado pelo banco) | Solução |
|---|---|---|
| **quando chega** | D+3 da publicação, por e-mail | aviso na manhã da descoberta (Itapecuru Mirim/MA: rodada às 06:00, e-mail às 06:04, documentos lidos às 06:20) |
| **prova** | resposta sem fonte | **trecho literal, arquivo e página** em cada resposta, conferidos por código sem IA; o link abre o PDF na página ([[Verificador determinístico]]) |
| **consistência** | conferência manual | regras automáticas: pirâmide que não soma, total deslocado, unidade da contagem, objeto divergente entre documentos, valor e critério cruzados com o PNCP |
| **contradições** | resolvidas em silêncio | relatadas em `conflito` e mandadas para revisão |
| **retificações** | não informado | acompanhadas diariamente e aos domingos ([[W70 Retificações]]) |
| **cobertura** | não declarada | declarada por rodada; rodada que não conseguiu consultar é marcada **cega** |
| **custo** | cerca de R$ 100 mil por ano (informado pelo banco) | de menos de R$ 1 a cerca de R$ 5 por edital em IA, com teto diário — com o volume real, em torno de R$ 150 por mês ([[Custo por edital]], [[Escalabilidade]]) |

O ganho não é só de eficiência: é de **preço**. Uma pirâmide lida pela metade, vínculos contados como pessoas ou uma data suspensa mudam o lance.

## 3. Vantagem — o que o fornecedor não faz

- **Quem compra folha, por quanto e até quando:** o Analytics mostra as 726 compras do histórico do PNCP por instituição, com o valor homologado, o ticket médio, o contrato e a **vigência** — até quando cada folha fica presa a cada banco ([[Página Analytics de Mercado]]).
- **O que volta:** licitações desertas ou fracassadas costumam ser republicadas; a solução liga cada republicação à anterior (437 republicadas; 236 compradas depois de republicar — [[Página Analytics Histórico FOPA]]).
- **O histórico com evidência:** 2.019 licitações do histórico extraídas e verificadas, a base para calibrar preço ([[Página Histórico]]).
- **Auditoria:** cada resposta publicada pode ser reconstruída — documento, página, prompt, regras e código ([[Pipeline de dados]]).

## O que torna a proposta confiável

- a IA **gera**; o código **confere**; a pessoa **decide** o que ficou em dúvida ([[ADR-004 Evidência obrigatória]]);
- cada técnica de IA foi escolhida por **medição** contra gabarito ([[MOC Avaliação]]);
- custo com teto e conferido na fatura; dados no Brasil; acesso por papéis ([[MOC Segurança e Ética]]).

## Relacionadas

[[MOC Negócio]] · [[Problema de negócio]] · [[Ganho para o negócio]] · [[Visão geral da solução]] · [[Concorrência e mercado]]
