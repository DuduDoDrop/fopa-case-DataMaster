---
tipo: pagina
familia: site
rota: "/licitacao/:slug"
papel_minimo: usuario
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - web/src/paginas/Detalhe.tsx
  - web/src/componentes/TabelaRespostas.tsx
  - web/src/componentes/Condicoes.tsx
  - web/src/componentes/MelhorDeN.tsx
  - web/src/componentes/Documentos.tsx
  - web/src/componentes/DistribuicaoQ13.tsx
  - web/src/componentes/EscolhaIa.tsx
  - api/site.py
  - api/consultas.py
tags: [site, pagina, detalhe, nucleo, antialucinacao]
---

# Página Detalhe da licitação

> [!abstract] Em uma frase
> Tudo sobre uma licitação numa página: quem compra e quando, de onde vieram as respostas e quanto custaram, as **17 respostas com veredito e evidência** — cada uma com o link "arquivo · p. N" que abre o PDF **na página citada** —, os alertas do verificador, os documentos, o histórico de verificações, as revisões e a linha do tempo completa.

## Papel na solução

É onde a promessa do produto se cumpre: **nenhuma resposta sem prova**. O analista não precisa procurar a informação no PDF — ele **confere** a informação já localizada, com a página na mão ([[ADR-004 Evidência obrigatória]], [[ADR-005 Info é arquivo mais página física]]).

> [!example] Os prints desta nota são da licitação real Itapecuru Mirim/MA (Pregão Eletrônico `05648696000180-1-000088/2026`), extraída em produção em 28/09/2026 duas vezes pelo botão "Extrair com IA": às 10:22 com Claude Haiku 4.5 e, depois do reprocessamento pedido às 17:14, com GPT-6 Luna. Os prints mostram a extração vigente, a do GPT-6 Luna.

![[site-detalhe-topo.jpg]]

## O que a página mostra, de cima para baixo

### 1. Cabeçalho
- Local, modalidade, controle, órgão e objeto.
- **Estado** e o motivo da última transição (por exemplo, "publicada — W24: publicada a verificação 3777"), número de arquivos e de páginas (quantas por OCR).
- **Prazo** até a sessão, com a cor da urgência.
- Avisos, quando for o caso: **"Sem PDF válido"** (o edital não virou PDF legível), **pedido de extração pendente** (quem pediu, quando e com qual modelo).

### 2. Procedência
Uma linha que diz **como** as respostas foram obtidas: origem (`API`, local, simulado), provedor, modelo, esforço, modo (contexto completo ou RAG), número de chamadas, tokens de entrada e de saída, tempo, custo e as versões do prompt e das regras (hashes). No caso real: "openai · gpt-6-luna · effort medium · modo contexto-completo · 5 chamadas · 15 tokens de entrada · 15.820 de saída · 2 min 44 s · R$ 0,20 · prompt f224a746b51a · regras b32b66ede7f6" — a contagem de entrada não inclui os tokens do edital gravados em cache ([[Cache de prompt e ordem do prompt]]). Na extração local, feita por agente, o provedor aparece como "agente de IA" e a linha diz que tokens, tempo e custo não são medidos ([[ADR-014 Extração por agente, sem API]]).

### 3. Botões (só administradores)

| Botão | O que faz | Custo |
|---|---|---|
| **Abrir no PNCP** | abre o edital no portal oficial | — |
| **Reverificar** | aplica as regras atuais do verificador às respostas vigentes, sobre o texto congelado, e republica ([[W11 Ações do site]] → [[W24 Verificar e publicar]]) | R$ 0 |
| **Processar** / **Processar novamente** | coloca a licitação na fila com o provedor vigente da esteira; "novamente" recomeça do download | só se o provedor for pago |
| **Extrair com IA** | abre a escolha de **provedor** (Claude ou OpenAI) e **modelo**, mostra o esforço fixo do modelo e a **estimativa de custo**; confirma e extrai **só esta licitação** com o serviço pago escolhido — o provedor geral não muda | o do modelo escolhido |

Cada ação pede confirmação, e a página acompanha o processamento sozinha ("Pedido aceito… Esta página acompanha o processamento sozinha").

### 4. Quadros da verificação
**Ancoragem verificada** (respostas com trecho encontrado na página citada / respostas com trecho), **aprovadas sem ressalva**, **para revisão**, **reprovadas**, **críticas aprovadas** (das 7 perguntas que movem o lance) e **custo da extração**. No caso real: 16/16 · 13 · 4 · 0 · 4/7 · R$ 0,20.

### 5. "Como conferir"
Um lembrete fixo: cada resposta cita arquivo e página física; o link abre o PDF naquela página; o trecho literal (em "Ver evidência") foi conferido por comparação de texto, **sem IA**; perguntas marcadas **crítica** movem o lance; vermelho é sempre defeito.

### 6. Alertas
Os alertas globais do verificador — por exemplo, **RN-09** (a soma das faixas salariais não bate com o total declarado), **RN-13** (a abrangência do objeto muda entre documentos), **RN-15** (perguntas sem resposta nos documentos), datas fora do formato.

### 7. Condições desta execução
O que o sistema sabe sobre **como** leu: documentos que faltaram, páginas com OCR, uso de provedor secundário, **texto escondido** encontrado (com "ver mais" dos trechos), e em quantas perguntas ele **se absteve** ("não localizado") — [[Consciência operacional]]. No print, a leitura aparece em **condição degradada** por ter rodado no provedor secundário (o GPT-6 Luna), e o sistema se absteve em uma pergunta (Q16).

![[site-detalhe-questionario.jpg]]

### 8. Questionário — as 17 respostas
Para cada pergunta ([[Questionário — as 17 perguntas]]):
- o número, o texto da pergunta e a marca **CRÍTICA** quando for o caso;
- a **resposta**;
- **Ver evidência** — o trecho literal citado;
- **origem** — "arquivo · p. N", link que abre o PDF na página física;
- **verificação** — o veredito (APROVADO, REVISAR, REPROVADO) e os alertas da pergunta;
- o sinal do Jev **"sustenta N%"** — a chance de o trecho de fato sustentar a resposta (só um sinal; não muda o veredito);
- quando houve reforço do **Best-of-N**: "escolhida a 2ª de 3 tentativas" ou "3 tentativas; prevaleceu a primeira".

![[site-detalhe-best-of-n.jpg]]

No print, o reforço do Best-of-N nas duas perguntas que não ancoraram na primeira passada: a Q11, "escolhida a 3ª de 3 tentativas", e a Q12, "escolhida a 2ª de 2 tentativas" — as duas aprovadas ([[Best-of-N#Caso real — Itapecuru Mirim/MA (28/09/2026)]]).

A barra à esquerda de cada linha usa a cor do veredito (verde conferido, âmbar revisar, vermelho não localizado ou reprovado).

### 9. Divergências entre documentos
As respostas em que o modelo apontou **conflito** entre documentos (por exemplo, a data da sessão no edital e no aviso de suspensão), com a descrição.

### 10. Pirâmide salarial (Q13)
Quando a Q13 traz distribuição por faixa salarial, um quadro estruturado com as faixas e as quantidades.

### 11. Documentos
Cada arquivo: nome, tipo, páginas, se precisou de OCR, SHA-256, status (ok, convertido, recusado e o motivo) e o link para o PDF.

### 12. Histórico de verificações
Todas as verificações da licitação, a vigente marcada, com o que mudou de uma para outra (vereditos antes → depois, versão das regras).

![[site-detalhe-revisoes.jpg]]

### 13. Revisões humanas
As revisões abertas para esta licitação (reprovadas, REVISAR em pergunta crítica, injeção), com a **decisão** (aceita, corrigida — com a resposta corrigida —, rejeitada), uma **nota** e o botão **Registrar decisão**; cada linha leva também à fila de revisão. No print, as três revisões abertas pela extração vigente — Q13, Q14 e Q5, todas "REVISAR em pergunta crítica".

![[site-detalhe-linha-do-tempo.jpg]]

### 14. Linha do tempo
Cada transição de estado com data, de → para, o **motivo** e a **execução do n8n** que a fez — o registro de `licitacao_eventos`. Abaixo, as rodadas de fluxo (W20) com duração, custo e resultado. Nos dois últimos prints, a história de Itapecuru: a primeira extração (Claude Haiku 4.5, às 10:22, R$ 0,78), o reprocessamento pedido pelo site às 17:14 e a segunda extração (GPT-6 Luna, às 17:15, R$ 0,20), que ficou vigente.

## De onde vêm os dados

| Parte | Rota da API | Fonte |
|---|---|---|
| tudo da licitação | `GET /api/licitacoes/{slug}` | `v_detalhe`, `respostas`, `verificacao_respostas`, `verificacoes`, `arquivos`, `leituras`, `licitacao_eventos`, `revisoes_humanas`, `execucoes_workflow`, `sinais_jev`, `pedidos_extracao`, `furtivos_achados` |
| o PDF na página | `GET /api/pdf/{slug}/{arquivo_id}#page=N` | redirecionamento (302) para uma **URL assinada de 10 minutos** do S3 ([[Armazenamento de arquivos (S3)]]) |
| catálogo do "Extrair com IA" | `GET /api/modelos-ia` | catálogo e estimativa do servidor |
| ações | `POST /api/acoes/reverificar`, `/processar`, `/extrair-ia` | chamam o [[W11 Ações do site]] |
| decisão de revisão | `POST /api/revisoes` | grava em `revisoes_humanas` (camada à parte; a resposta e o veredito originais não mudam) |

## Quem vê

Todo usuário logado vê a página e pode registrar decisões de revisão de respostas; os botões de ação aparecem só para administradores ([[Papéis e acesso]]).

## Relacionadas

[[MOC Site]] · [[Página Relatório]] · [[Página Revisão]] · [[Verificador determinístico]] · [[Best-of-N]] · [[Jev — score de escopo e sustentação]] · [[Consciência operacional]] · [[W24 Verificar e publicar]] · [[Ciclo de vida de uma licitação]] · [[ADR-004 Evidência obrigatória]]
