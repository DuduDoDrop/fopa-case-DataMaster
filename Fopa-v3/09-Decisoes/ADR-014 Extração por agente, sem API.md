---
tipo: decisao
familia: decisoes
adr: 14
data: 2026-09-23
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, extracao, custo, acervo]
---

# ADR-014 — Extração por agente, sem API

> [!abstract] Em uma frase
> O **acervo histórico** foi extraído por um **agente de IA fora da API paga** (o mesmo modelo Claude Opus 5.5, lendo o **mesmo texto congelado** com os mesmos marcadores e o mesmo esquema), e as respostas entram pelo **mesmo verificador** que a extração por API — a única coisa trocada é quem escreve o JSON; a procedência fica gravada, e essas execuções nunca aparecem com custo de API.

## Problema

Com 13 licitações, a extração por API custou R$ 55,48. Com um acervo de centenas de licitações de folha baixadas, a mesma conta passaria de R$ 3 mil — e o dado continua necessário: é a base do histórico, do Analytics e da calibragem de preço.

## Opções

| Opção | Avaliação |
|---|---|
| extrair o acervo inteiro pela API | milhares de reais para dado histórico |
| não extrair o histórico | sem base de preço nem de mercado |
| **um agente produz as respostas sobre a leitura congelada; o verificador decide** | custo de API zero, garantia igual |

## O que garante que a troca não abre brecha

| Etapa | Quem faz | Igual à API? |
|---|---|---|
| ler PDFs, OCR, limpar assinatura | o mesmo código de leitura | **sim** |
| responder as 17 perguntas | o agente, lendo o contexto com os marcadores `=== ARQUIVO x \| PÁGINA n ===` | é a troca |
| regras e esquema de saída | a mesma instrução de sistema e o mesmo esquema | **sim** |
| conferir trecho contra página | o **mesmo verificador**, sem IA | **sim** |

- **O agente lê o texto que o verificador confere** — um trecho lido por outro caminho não ancoraria.
- **A procedência fica gravada:** `execucoes_modelo.origem = 'agente'`; nunca se passa por execução de API, e o custo aparece como **"sem preço de API"**, nunca R$ 0,00 ([[Custo por edital]]).
- **Uma passada, sem Best-of-N:** o reforço usa o verificador como juiz de tentativas repetidas — técnica reservada ao caminho da API, para não entrar pela porta dos fundos ([[Best-of-N]]).
- **Gêmeas pelo texto:** uma republicação com o mesmo edital reaproveita as respostas pelo hash do texto lido, e o verificador confere tudo de novo contra as páginas da licitação nova.

## O que foi medido

- Primeiras 71 licitações (23/09/2026): 1.031 respostas com trecho citado, **1.029 ancoradas (99,8%)**, 0 chamadas de API.
- Em produção (28/09/2026): no Histórico, **2.011 das 2.019 extrações** vieram por esse caminho, com ancoragem de **99,96%** (25.114 de 25.122); no Painel, 49 das 59.
- A ancoragem do agente **não é comparável 1:1** com a da API: o agente pode conferir o próprio trecho por busca literal antes de gravar; a API não pode. O número mede o pipeline, não prova que o agente "acerta mais".

## Escolha

As respostas produzidas pelo agente entram pelo `POST /importar-respostas` do worker — acionado pelo botão "Importar respostas do agente" da [[Página Admin]] ([[W11 Ações do site]]) — e seguem o caminho normal: verificação ([[W24 Verificar e publicar]]), publicação, revisão.

## O que custa

- O custo mudou de lugar, não sumiu: cada licitação consome de 100 a 470 mil tokens do agente, e o ritmo é limitado pela conta dele.
- Números de extração precisam ser comparados pela **origem**: API, agente, simulado, gravado ou legado.

## O que reabriria a decisão

O volume do acervo crescer a ponto de a extração por agente não acompanhar — aí a API, com cache e teto diário, passa a ser o caminho também para o histórico.

## Relacionadas

[[MOC Decisões]] · [[Modelos e provedores]] · [[Verificador determinístico]] · [[W11 Ações do site]] · [[Acervo e migração da v2]] · [[ADR-004 Evidência obrigatória]]
