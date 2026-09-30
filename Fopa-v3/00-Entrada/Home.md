---
tipo: moc
familia: entrada
status: verificado
atualizado: 2026-09-28
tags: [moc, entrada, home]
---

# FOPA — Home

> [!abstract] Em uma frase
> O **FOPA** é a solução de IA generativa que acompanha, para um banco, as **licitações de folha de pagamento pública** do Brasil: descobre cada licitação no PNCP na manhã em que ela aparece, lê todos os documentos, responde as **17 perguntas** que decidem o lance com **arquivo, página e trecho literal**, confere cada resposta **sem IA**, publica tudo num site com revisão humana e mostra quem compra folha no país, por quanto e até quando — no ar em **https://licitacaofopa.com.br**.

## Papel neste vault

É a documentação completa da solução **como está em produção** (v3.1, no ar desde 28/09/2026 às 07:58): o problema, a arquitetura, cada fluxo nó a nó, cada página do site, os dados, as técnicas de IA com as medições que as escolheram, as decisões, a infraestrutura, a segurança, a base legal, a escalabilidade, como reproduzir e como a solução evolui.

## Ordem de leitura

| # | Leia | Para entender |
|---|---|---|
| 1 | [[Visão geral da solução]] | o que a solução faz em seis passos, os números de produção e um caso real de ponta a ponta |
| 2 | [[Problema de negócio]] e [[Ganho para o negócio]] | a dor informada pelo banco e o que muda com a solução |
| 3 | [[Mapa mental]] | a solução inteira numa figura |
| 4 | [[Arquitetura]] e [[Stack e justificativa tecnológica]] | os componentes, quem fala com quem e por que cada tecnologia |
| 5 | [[MOC Fluxos n8n]] | os 15 fluxos, nó a nó, com fluxograma e horário |
| 6 | [[MOC IA]] | modelos, prompt, RAG com BM25, cache, raciocínio, Best-of-N e o verificador sem IA |
| 7 | [[MOC Avaliação]] | como a qualidade foi medida e o que os números dizem |
| 8 | [[MOC Decisões]] | as 24 decisões, com as opções, o trade-off e, quando houve, a medição que decidiu |
| 9 | [[MOC Site]] | cada página do site e o que cada botão faz |
| 10 | [[MOC Reprodução]] | como acessar a versão no ar e como rodar em outra máquina |
| 11 | [[Requisitos do case — onde cada um está atendido]] | cada item do enunciado e onde ele está atendido |

## O mapa

![[Mapa mental#O fluxo inteiro]]

A versão navegável, em que cada caixa abre a nota, é o canvas [[Mapa da solução.canvas|Mapa da solução]].

## A solução em números (produção, 28/09/2026)

| | |
|---|---|
| licitações de folha em andamento no painel | **71** |
| licitações no histórico, com extração | **2.020**, das quais **2.019** extraídas |
| respostas com o trecho conferido na página citada | **99,96%** no histórico · **98,67%** nas ativas |
| mercado de folha no histórico do PNCP | **726** compras, **R$ 5,56 bi**, **79** instituições |
| custo de uma extração | de **R$ 0,20** a cerca de **R$ 5** |
| fluxos de automação | **15**, com **368** nós |

Detalhe e fontes em [[Visão geral da solução]] e [[Resultados medidos]].

## As famílias

| Pasta | Família | Porta de entrada |
|---|---|---|
| `00-Entrada` | Entrada | esta nota · [[Mapa mental]] · [[Glossário]] · [[Requisitos do case — onde cada um está atendido]] |
| `01-Negocio` | Negócio | [[MOC Negócio]] |
| `02-Solucao` | Solução | [[MOC Solução]] |
| `03-Fluxos-n8n` | Fluxos n8n | [[MOC Fluxos n8n]] |
| `04-Worker-e-API` | Worker e API | [[MOC Worker e API]] |
| `05-Site` | Site | [[MOC Site]] |
| `06-Dados` | Dados | [[MOC Dados]] |
| `07-IA` | IA | [[MOC IA]] |
| `08-Avaliacao` | Avaliação | [[MOC Avaliação]] |
| `09-Decisoes` | Decisões | [[MOC Decisões]] |
| `10-Infra` | Infraestrutura | [[MOC Infra]] |
| `11-Seguranca-e-Etica` | Segurança e ética | [[MOC Segurança e Ética]] |
| `12-Legal` | Legal | [[MOC Legal]] |
| `13-Escalabilidade` | Escalabilidade | [[Escalabilidade]] |
| `14-Reproducao` | Reprodução | [[MOC Reprodução]] |
| `15-Evolucao` | Evolução | [[MOC Evolução]] |
| `98-Anexos` | capturas de tela do site | — |
| `99-Templates` | modelos de nota | — |

No grafo, cada família tem a sua cor. Toda nota termina em **Relacionadas**, que a liga ao MOC da família e às notas de outras famílias com que ela conversa: fluxo ↔ endpoint ↔ tabela ↔ página ↔ decisão ↔ lei.

## Convenções

- Toda nota abre com **Em uma frase**. As notas descritivas seguem com **Papel na solução**; as decisões seguem o formato **Problema → Opções → Escolha → O que custa → O que reabriria a decisão**, com a medição que decidiu e o lugar onde a decisão vive em produção sempre que houver. Termos técnicos estão no [[Glossário]].
- Propriedades: `tipo`, `familia`, `status`, `atualizado` e `tags`; quando cabe, `fonte_codigo` (os arquivos do repositório que sustentam a nota), `fontes`, `adr`, `workflow`, `nos`, `gatilho` e `rota`.
- Todo número tem data e fonte; **"informado pelo banco"** marca o dado interno do banco.
- O que está descrito é o que roda: o worker e a API do site no commit `ab55f75` (imagem `fopa/worker:ab55f759efcc`, desde 30/09/2026 às 05:38) e os 15 fluxos importados do mesmo código, com uma nota explicativa ao lado de cada passo no canvas do n8n.

## Relacionadas

[[Visão geral da solução]] · [[Mapa mental]] · [[Glossário]] · [[Requisitos do case — onde cada um está atendido]] · [[Linha do tempo da construção]]
