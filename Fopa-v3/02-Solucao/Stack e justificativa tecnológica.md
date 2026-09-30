---
tipo: arquitetura
familia: solucao
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - docker/compose.yml
  - docker/worker.Dockerfile
  - requirements.txt
  - api/requirements.txt
  - web/package.json
tags: [arquitetura, stack, tecnologia, decisao]
---

# Stack e justificativa tecnológica

> [!abstract] Em uma frase
> Cada tecnologia da solução foi escolhida por um **critério explícito** — confiabilidade, auditabilidade, custo, dados no Brasil, reprodutibilidade —, com a alternativa considerada e um **exemplo concreto** de como ela contribui para o resultado.

## Papel na solução

Uma escolha tecnológica sem critério é preferência. Aqui cada peça responde a um requisito do problema: ler documentos públicos com prova, sob prazo, com custo controlado, num banco regulado.

## A stack

| Camada | Tecnologia (versão em produção) |
|---|---|
| orquestração | **n8n** 2.37.10 |
| processamento | **Python 3.12** + **FastAPI** 0.141 + Uvicorn |
| OCR | **Tesseract 5.4.0** + Leptonica 1.84.1, compilados na imagem; PyMuPDF para texto nativo e rasterização |
| conversão de formatos | **LibreOffice** sem tela; **bsdtar** para RAR |
| modelos de IA | **Claude Opus 5.5** (padrão), Claude Sonnet 5 e Haiku 4.5; **GPT-5.6 Sol** (plano B) e GPT-6 Sol, Astra e Luna, pelo botão; **Jev** como segundo sinal |
| recuperação | **BM25 Okapi** em Python puro — sem banco vetorial |
| banco | **PostgreSQL 16** |
| site | **React 18** + TypeScript + Vite + TanStack Query, servido pela API FastAPI |
| entrada e HTTPS | **Caddy** 2.11 com Let's Encrypt |
| empacotamento | **Docker Compose** |
| nuvem | **AWS** — EC2 t3.small e S3 em São Paulo (sa-east-1) |
| e-mail | **Resend** (SMTP), domínio próprio |
| login | **Google** OAuth 2.0 / OpenID Connect |

## As escolhas, com critério, alternativa e exemplo

| Escolha | Critério | Alternativa considerada | Exemplo concreto |
|---|---|---|---|
| **n8n** para orquestrar | fluxos **visíveis e editáveis** num canvas, agenda, webhooks, credenciais cifradas num só lugar, histórico de cada execução nó a nó | um orquestrador em código (filas e *workers* próprios, ou um agendador de tarefas) | a chave do modelo vive só numa credencial do n8n; o W23 é o único fluxo que chama o modelo — um teste do CI garante isso ([[W23 Extrair]]) |
| **regras no PostgreSQL** (funções, gatilhos) | uma regra que vale para todos os escritores (n8n, worker, site) e é testada em SQL | regra no canvas de cada fluxo | a fila usa `FOR UPDATE SKIP LOCKED` numa função: duas rodadas simultâneas nunca pegam a mesma licitação ([[Funções e views do banco]]) |
| **worker em Python/FastAPI** | reaproveitar o **mesmo núcleo que foi medido** contra gabarito; OCR e PDF maduros em Python | reescrever as etapas como nós de código no n8n | o prompt de produção é montado pelas mesmas funções que produziram as medições de acurácia ([[Prompt do extrator]]) |
| **Tesseract local**, versão fixa | privacidade (o documento não sai do servidor), determinismo, custo zero; perfis **medidos** | OCR em nuvem; modelo de visão | o perfil de tabela (400 dpi) mediu **zero valores errados**; a produção reproduz a imagem de referência página a página ([[ADR-008 OCR — stack, configuração e limites]]) |
| **LibreOffice** para converter | manter a **página** como unidade de citação para qualquer formato | ler o texto cru do Word | 40 das 41 licitações presas por formato destravadas ([[ADR-017 O arquivo que não é PDF vira PDF]]) |
| **Claude Opus 5.5** no extrator | **acurácia e profundidade** medidas contra gabarito; o custo de modelo é pequeno perto do valor da licitação | modelos menores e o outro fornecedor | 17/17 no edital difícil, onde os GPT caíram para 10–15 ([[Comparação de modelos]]) |
| **dois fornecedores de modelo** | licitação tem prazo; um fornecedor fora não pode parar a operação | um fornecedor só | o GPT-5.6 Sol ancora 100% nos dois gabaritos e fica como plano B ([[ADR-012 Segundo provedor de modelo]]) |
| **BM25**, não embeddings | vocabulário jurídico fechado; nada sai do servidor; custo zero; recorte explicável | embeddings + banco vetorial | −36% de custo com a mesma acurácia no mesmo edital ([[RAG com BM25]]) |
| **verificador sem IA** | quem gera não verifica; reprodutível; custo zero | um modelo como juiz | 99,96% das respostas do histórico com o trecho conferido na página ([[Verificador determinístico]]) |
| **PostgreSQL 16** | transações, funções, gatilhos, JSON, índices parciais; um banco para o negócio e outro para o n8n no mesmo servidor | banco de documentos; planilhas | tabelas imutáveis só com inserção e uma verificação vigente garantida por índice único ([[Modelo de dados]]) |
| **React + Vite** | interface rica (gráficos, filtros, detalhe com links para a página) testada no build | páginas geradas no servidor | os testes do front rodam dentro da construção da imagem: um teste que falha impede a versão ([[Containers e serviços]]) |
| **Caddy** | HTTPS automático e configuração curta | Nginx + renovação manual | só `/webhook/*` do n8n é público; o resto pede senha antes do login do n8n ([[Domínio, DNS e HTTPS]]) |
| **Docker Compose numa instância** | reprodutível em qualquer máquina com Docker; simples de operar no volume atual | Kubernetes, serviços gerenciados | a mesma composição sobe o desenvolvimento e, com uma sobreposição, a produção ([[Como rodar em outra máquina]]) |
| **AWS em São Paulo** | dados (banco e documentos com dados pessoais) no Brasil; crédito inicial; crescer é trocar o tipo da instância | outras nuvens ou armazenamento fora do país | o bucket e o banco estão em sa-east-1 ([[Hospedagem na AWS]]) |
| **Resend** com domínio próprio | entrega confiável com autenticação do domínio (SPF, DKIM, DMARC) | e-mail pessoal com senha de aplicativo | os dois e-mails saem de `avisos@licitacaofopa.com.br` ([[E-mails do produto]]) |
| **Google OAuth** | nenhuma senha guardada; só nome e e-mail | cadastro com senha própria | a sessão guarda só o hash do identificador e cai ao bloquear o usuário ([[Login com Google]]) |

## O que ficou de fora de propósito

Banco vetorial, fine-tuning, OCR em nuvem, modelo como juiz, orquestrador próprio e Kubernetes — cada um com o motivo em [[Técnicas avaliadas e descartadas]] e nos ADRs ([[MOC Decisões]]).

## Relacionadas

[[MOC Solução]] · [[Arquitetura]] · [[Visão geral da solução]] · [[Containers e serviços]] · [[MOC Decisões]] · [[Escalabilidade]]
