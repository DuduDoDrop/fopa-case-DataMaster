---
tipo: referencia
familia: entrada
status: verificado
atualizado: 2026-09-28
fontes:
  - enunciado do case "Engenheiro de IA" (Academia Santander), páginas 2, 3 e 4
tags: [entrada, requisitos, rastreabilidade]
---

# Requisitos do case — onde cada um está atendido

> [!abstract] Em uma frase
> Cada item do enunciado do case — a missão, os tópicos necessários, os entregáveis, as recomendações, a reprodutibilidade e a apresentação — com o lugar exato onde a solução o atende, neste vault, no repositório ou na versão no ar.

## Papel na solução

É a rastreabilidade entre o que foi pedido e o que foi entregue: um requisito sem linha nesta nota é um requisito sem entrega. As notas citadas têm, cada uma, o detalhe e as fontes no código.

## 1. A missão (página 2)

| O enunciado pede | Onde está atendido | Situação |
|---|---|---|
| uma **solução funcional de IA generativa** para um caso real de negócio | o FOPA, no ar em https://licitacaofopa.com.br: descobre, lê e responde as 17 perguntas de cada licitação de folha de pagamento pública, com evidência ([[Visão geral da solução]], [[Problema de negócio]]) | atendido |
| **desenhar, validar e implementar** | desenho: [[Arquitetura]]; validação: [[MOC Avaliação]]; implementação: [[Linha do tempo da construção]] | atendido |
| funcionamento **completo, de ponta a ponta** | a versão no ar ([[Como acessar a versão no ar]]); um caso real da descoberta ao e-mail, com horário de cada passo ([[Visão geral da solução]]) | atendido |
| explicar a **arquitetura** e **justificar as escolhas tecnológicas** | [[Arquitetura]], [[Stack e justificativa tecnológica]] | atendido |
| **exemplos práticos** de como cada aspecto é implementado | cada fluxo descrito nó a nó, com um caso real ([[MOC Fluxos n8n]]); cada página do site com captura de tela ([[MOC Site]]) | atendido |
| **diagramas, documentação e explicação de cada componente** | o [[Mapa mental]] da solução, fluxogramas em todas as notas de fluxo, o diagrama de sequência da [[Arquitetura]], a máquina de estados em [[Ciclo de vida de uma licitação]]; os 15 fluxos e seus 368 nós (cada passo com uma nota explicativa no canvas do n8n), o worker, a API, as 13 páginas do site, o banco, a IA e a infraestrutura, cada um com nota própria | atendido |
| um **plano de implementação** | as fases F0 a F8, com objetivo e prova de pronto ([[Linha do tempo da construção]]); a implantação no banco ([[Próximos passos]]) | atendido |
| **desafios e melhorias futuras** | [[Desafios enfrentados]], [[Próximos passos]] | atendido |
| solução **escalável** | [[Escalabilidade]] | atendido |
| solução **segura** | [[MOC Segurança e Ética]], [[Segurança do servidor]], [[Controle de acesso e segredos]], [[Injeção de prompt e defesas]] | atendido |
| solução **eficiente** | custo medido por edital e na fatura ([[Custo por edital]]); a v3.1 com −32,5% de custo e a mesma acurácia ([[Antes e depois da v3.1]]); regras antes de IA ([[Regras antes de IA]]) | atendido |
| tema de dados de livre escolha | compras públicas: as licitações de folha de pagamento publicadas no PNCP ([[Fontes de dados — PNCP]]) | atendido |

## 2. O tema e os tópicos necessários (página 3)

| O enunciado pede | Onde está atendido | Situação |
|---|---|---|
| um dos temas propostos | **2 — Automação e Extração de Conhecimento**: workflows que leem, organizam, classificam e resumem, para reduzir o trabalho manual de análise de documentos ([[Enquadramento no tema do case]]) | atendido |
| **um ou mais modelos de IA** que solucionem a dor | Claude Opus 5.5 na extração, com Claude Sonnet 5 e Claude Haiku 4.5 disponíveis, GPT-5.6 Sol como segundo provedor e o Jev como segundo sinal de escopo e de sustentação ([[Modelos e provedores]], [[Comparação de modelos]], [[ADR-009 Modelo de extração]], [[ADR-012 Segundo provedor de modelo]]) | atendido |
| a **escolha dos prompts** e a **dinâmica de orquestração** para respostas **consistentes e controladas** | o questionário fechado, a instrução de sistema e o esquema de resposta ([[Questionário — as 17 perguntas]], [[Prompt do extrator]]); a orquestração no n8n com a trava de fila e de gasto no banco ([[MOC Fluxos n8n]]); o Best-of-N e o verificador sem IA ([[Best-of-N]], [[Verificador determinístico]]); versões de prompt e de regras em cada resultado ([[Controles de consistência]]) | atendido |
| o **uso de dados** — como são preparados ou produzidos, armazenados e utilizados | dados reais e públicos do PNCP, sem dado de cliente: coleta, conversão, OCR, texto congelado, respostas e verificações ([[Pipeline de dados]]); o banco ([[Modelo de dados]]); os arquivos no S3 ([[Armazenamento de arquivos (S3)]]); o acervo anterior importado sem reprocessar ([[Acervo e migração da v2]]) | atendido, com dados reais em vez de fictícios |
| a **estratégia de uso ou ajuste** do modelo (RAG, fine-tuning ou outro) e **como avaliar** | contexto completo quando o documento cabe e RAG com BM25 quando não cabe; fine-tuning avaliado e descartado com motivo ([[RAG com BM25]], [[ADR-010 RAG vs contexto completo]], [[Técnicas avaliadas e descartadas]]); avaliação por gabarito humano, harness e métricas separadas de integridade e de qualidade ([[Métricas]], [[Harness de avaliação]], [[Gabaritos]], [[Resultados medidos]]) | atendido |
| o **desenho da arquitetura** com modelos ou agentes, com **decisões e trade-offs** | [[Arquitetura]]; 24 decisões com opções, trade-off, o que as reabre e, quando houve, a medição que decidiu ([[MOC Decisões]]); as decisões de implementação ([[Decisões de construção da v3]]) | atendido |
| **premissas, análises e técnicas de ética, privacidade e responsabilidade**, com os **cenários cobertos** | [[Premissas éticas e matriz de cenários]], [[Privacidade e LGPD]], [[Legalidade da automação]], [[Injeção de prompt e defesas]], [[Controle de acesso e segredos]]; na tela, a [[Página Governança]] | atendido |

## 3. Os entregáveis (página 4)

| O enunciado pede | Onde está atendido | Situação |
|---|---|---|
| um **projeto funcional — em execução, empacotado e reprodutível** | em execução: https://licitacaofopa.com.br ([[Como acessar a versão no ar]]); empacotado: containers e composição versionados ([[Containers e serviços]]); reprodutível: [[Como rodar em outra máquina]], [[Testes e CI]] | atendido |
| documentação: **explicação do case** | [[Problema de negócio]], [[Proposta de valor]], [[Visão geral da solução]] | atendido |
| documentação: **instruções de execução** no equipamento de quem avalia, **ou link para acessar** | as duas: [[Como rodar em outra máquina]] e [[Como acessar a versão no ar]] | atendido |
| documentação: **desenho e arquitetura** | [[Arquitetura]], [[Mapa mental]], [[MOC Solução]] | atendido |
| documentação: **decisões e trade-offs** | [[MOC Decisões]] | atendido |
| documentação: **próximos passos** | [[Próximos passos]] | atendido |

## 4. Recomendações, reprodutibilidade e apresentação (página 4)

| O enunciado pede | Onde está atendido | Situação |
|---|---|---|
| **justificativa tecnológica** com critérios sólidos e **exemplos concretos** | cada tecnologia com critério, alternativa e exemplo ([[Stack e justificativa tecnológica]]); cada decisão com as opções consideradas e, quando houve, a medição que decidiu ([[MOC Decisões]]) | atendido |
| a solução **reproduzida em outra máquina ou ambiente** | a mesma composição roda na máquina local e na produção; o CI roda as suítes numa cópia limpa, sem chave — em 28/09/2026, num clone limpo do repositório, 8 de 8 passos e 1.131 testes aprovados; no runner do GitHub, sem Tesseract, os testes de OCR saem desmarcados com o motivo e os oito passos passam ([[Testes e CI]]) | atendido |
| **todos os scripts de configuração, instalação e execução no repositório Git** | `docker/` (composição e imagem), `db/migrar.py` (banco), `n8n/bootstrap.py` e `n8n/importar.py` (orquestrador e fluxos), `setup.ps1` (máquina fora do container), `ci/rodar.py` e `Makefile` (testes) ([[Como rodar em outra máquina]]) | atendido |
| **instruções claras** de configuração e execução em outra máquina | [[Como rodar em outra máquina]], com os dois modos de execução e a extração com e sem chave | atendido |
| **demonstrar a solução em funcionamento**, parte por parte | a versão no ar e o editor do n8n, onde cada fluxo roda nó a nó ([[Como acessar a versão no ar]], [[MOC Fluxos n8n]]) | atendido |

## Relacionadas

[[Home]] · [[Enquadramento no tema do case]] · [[Visão geral da solução]] · [[MOC Decisões]] · [[MOC Reprodução]] · [[Próximos passos]]
