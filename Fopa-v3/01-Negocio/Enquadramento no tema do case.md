---
tipo: negocio
familia: negocio
status: verificado
atualizado: 2026-09-28
tags: [negocio, case, tema]
---

# Enquadramento no tema do case

> [!abstract] Em uma frase
> A solução se enquadra no tema **"Automação e Extração de Conhecimento"** do case — workflows que **leem, organizam, classificam e resumem** informações para **reduzir o trabalho manual de análise de documentos e contratos** —: ela lê editais públicos, classifica o que é compra de folha, extrai as respostas que decidem o lance com prova conferida e organiza tudo num produto com alertas, revisão e análise de mercado.

## Papel na solução

Situa a entrega no enunciado: o tema escolhido, como cada verbo do tema aparece na solução e os dados usados. O mapa completo de requisito → onde está atendido fica em [[Requisitos do case — onde cada um está atendido]].

## O tema, verbo a verbo

| O tema pede | Na solução |
|---|---|
| **workflows** | 15 fluxos no n8n, agendados e acionados pelo site, com o processamento pesado num worker ([[MOC Fluxos n8n]]) |
| que **leem** | download de todos os documentos, conversão para PDF, leitura com OCR local, texto congelado por página ([[W21 Baixar]], [[W22 Ler]]) |
| **organizam** | banco com a máquina de estados de cada licitação, o painel, o histórico e o mercado ([[MOC Dados]], [[MOC Site]]) |
| **classificam** | regra de escopo com motivo e versão, segunda opinião probabilística e rótulo humano ([[Regras antes de IA]]) |
| **resumem** | as 17 respostas, com a Q11 resumindo as obrigações e a Q13 consolidando a pirâmide de várias tabelas — sempre com o trecho literal que sustenta ([[Questionário — as 17 perguntas]]) |
| foco: **reduzir o trabalho manual de análise de documentos e contratos** | a área passa de ler o edital a conferir uma fila curta com a evidência na mão ([[Ganho para o negócio]]) |

## Os dados

O enunciado permite usar dados de uma empresa fictícia. A solução usa **dados reais e públicos** — os editais, itens, resultados e contratos do PNCP — e os dados que ela mesma produz (texto lido, respostas, verificações, decisões humanas). A dor de negócio vem do banco ([[Problema de negócio]]). Como os dados são preparados, armazenados e usados está em [[Pipeline de dados]] e [[Modelo de dados]].

## Relacionadas

[[MOC Negócio]] · [[Requisitos do case — onde cada um está atendido]] · [[Visão geral da solução]] · [[Problema de negócio]]
