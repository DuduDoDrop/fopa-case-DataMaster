---
tipo: decisao
familia: decisoes
adr: 7
data: 2026-09-22
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, cobertura, risco, legal]
---

# ADR-007 — Cobertura de municípios pequenos

> [!abstract] Em uma frase
> Municípios de até 20 mil habitantes **podem** publicar só em diário oficial até **01/04/2027** (Lei 14.133, art. 176); a solução continua no PNCP, **declara a cobertura em vez de presumi-la**, e mediu que o buraco é menor do que parecia — metade dos municípios que ela já enxerga está nessa faixa e publica no PNCP assim mesmo.

## Problema

> [!fato] Art. 176 da Lei 14.133/2021
> Os municípios com até 20 mil habitantes têm seis anos, contados da publicação da lei (01/04/2021), para cumprir as regras de divulgação em sítio eletrônico oficial; enquanto não adotarem o PNCP, publicam em diário oficial — **admitida a publicação de extrato** — e mantêm a versão física dos documentos na repartição.

98% do mercado de folha é municipal (amostra de 100, 22/09/2026), e municípios pequenos licitam folha: Pirapó/RS, um dos gabaritos, tem 2.260 habitantes. A fonte primária poderia não alcançar parte do mercado até abril de 2027.

## Opções

| Opção | Avaliação |
|---|---|
| ignorar e prometer cobertura total | falso, e verificável por qualquer jurista |
| começar pelos diários oficiais | fonte suja, sem estrutura, e que traz o **extrato**, não o edital |
| esperar abril de 2027 | perderia a série histórica de preços desse período |
| **PNCP como fonte, cobertura declarada, diário oficial avaliado como canal de descoberta** | honesto e medido |

## O que foi medido (23/09/2026)

| Medida | Resultado |
|---|---|
| municípios do corpus na faixa do art. 176 | **70 de 138 (50,7%)** — publicam no PNCP mesmo sendo dispensados |
| os menores já no PNCP | Flora Rica/SP, 1.487 habitantes; Tapiraí/MG, 1.690 |
| cobertura do agregador de diários (Querido Diário) na faixa de até 20 mil | **246 de 3.861 municípios (6,4%)** — é o **teto** do que uma segunda fonte recuperaria |
| cobertura dele nos municípios do corpus | 17 de 139 (12,2%) |
| estabilidade do agregador | ruim: fora do ar no dia da apuração, migração de domínio sem aviso |
| o que o diário oficial entrega | **o extrato** (objeto, data, onde retirar o edital) — nunca as respostas das 17 perguntas |

> [!important] O que o número diz, e o que ele não diz
> A amostra só contém quem publicou: quem **usou** a dispensa é invisível por definição, então não dá para medir quantos ficaram de fora. O que o número mostra é que o art. 176 **não torna o município pequeno invisível por si só** — o buraco é menor do que a premissa original supunha.

## Escolha

1. **O PNCP continua sendo a fonte** ([[ADR-002 PNCP como fonte primária]]).
2. **A cobertura é declarada, nunca presumida:** a solução não promete achar todas as licitações do país; cada rodada da descoberta registra o que conseguiu consultar, e a que não conseguiu é marcada **cega**.
3. **O diário oficial fica como canal de descoberta avaliado e não construído:** com teto de 6,4% da faixa, fonte instável, e o prazo de 01/04/2027 fechando o buraco sozinho, a integração não se paga — está em [[Próximos passos]] com os números para quem for decidir.

## O que custa

Licitações de municípios pequenos que publicam só em diário oficial não aparecem até abril de 2027 — e, mesmo descobertas por diário, exigiriam obter o edital no site do município ou no balcão, o que não se automatiza.

## Onde vive em produção

- `buscas.cobertura_pct` e o marcador `cego` das rodadas do [[W01 Descoberta]]; a [[Página Saúde]] mostra a última coleta; a [[Página Execuções]] mostra cada rodada com os contadores.

## O que reabriria a decisão

Um requisito do banco de cobrir os municípios pequenos antes de 01/04/2027, ou uma fonte de diários estável com cobertura relevante da faixa.

## Relacionadas

[[MOC Decisões]] · [[ADR-002 PNCP como fonte primária]] · [[Fontes de dados — PNCP]] · [[Lei 14.133-2021 - visão geral]] · [[Próximos passos]]
