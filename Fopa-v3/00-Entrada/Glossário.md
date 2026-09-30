---
tipo: referencia
familia: entrada
status: verificado
atualizado: 2026-09-28
tags: [entrada, glossario]
---

# Glossário

> [!abstract] Em uma frase
> Os termos de negócio, de licitação, de dados, de IA, de verificação e de operação usados no vault, cada um com a definição curta e a nota onde ele é explicado por inteiro.

## Papel na solução

Deixa o vault legível para quem vem do negócio e para quem vem da engenharia: o termo técnico é explicado uma vez, aqui, e as notas apontam para cá.

## Negócio e base legal

| Termo | O que é | Onde |
|---|---|---|
| **cessão onerosa da folha** | o órgão público concede a uma instituição financeira o direito de processar e pagar a folha dos servidores, em geral com exclusividade e por prazo determinado, e **recebe** por isso | [[Cessão onerosa da folha - fundamentos]] |
| **conta-salário e portabilidade** | a conta aberta para o crédito do salário e o direito do servidor de transferi-lo para outro banco — o que decide quanto uma folha vale depois de comprada | [[Regulação bancária - conta-salário e portabilidade]] |
| **consignado** | crédito com desconto direto na folha — parte do valor que o banco compra | [[Consignado em folha - regras]] |
| **pirâmide salarial** | quantos servidores há em cada faixa de remuneração (pergunta Q13) | [[Questionário — as 17 perguntas]] |
| **ágio** | a razão entre o valor homologado e o valor mínimo do edital (1,00× = arrematada no mínimo) | [[Concorrência e mercado]] |
| **informado pelo banco** | marca do dado interno do banco usado no vault, diferente de medição da solução | [[Problema de negócio]] |
| **Lei 14.133/2021** | a lei de licitações; obriga a publicar o inteiro teor do edital no PNCP | [[Lei 14.133-2021 - visão geral]] |
| **LGPD, LAI, RIPD, encarregado (DPO)** | a lei de proteção de dados, a lei de acesso à informação, o relatório de impacto e o responsável pelos dados na instituição | [[Privacidade e LGPD]] |

## Licitação e PNCP

| Termo | O que é | Onde |
|---|---|---|
| **PNCP** | o Portal Nacional de Contratações Públicas, onde os órgãos publicam editais, documentos, resultados e contratos; tem API pública | [[Fontes de dados — PNCP]] |
| **número de controle** | o identificador único de uma compra no PNCP — CNPJ do órgão, tipo e sequencial/ano, como `05648696000180-1-000088/2026`; é a identidade da licitação em toda a solução | [[ADR-013 Identidade de licitação é o número de controle]] |
| **modalidade** | a forma da licitação: pregão, concorrência, credenciamento — ou contratação direta, por **dispensa** ou **inexigibilidade** | [[Lei 14.133-2021 - visão geral]] |
| **edital, termo de referência, anexos** | os documentos da licitação; as respostas podem estar em qualquer um | [[W21 Baixar]] |
| **retificação** | documento novo que altera a licitação; o vigente é o de maior sequencial | [[ADR-006 Documento vigente é o de maior sequencial]], [[W70 Retificações]] |
| **escopo** | se a compra é, de fato, compra de folha; o **escopo efetivo** combina a regra e o rótulo humano | [[Escopo — o que é licitação de folha]] |
| **recorte de 2026** | o produto acompanha só licitações de 2026 e só compra de folha | [[ADR-015 Acervo só de 2026 e só compra de folha]] |
| **histórico do PNCP** | as compras, itens, resultados e contratos de folha já encerrados, coletados todo dia | [[W41 Histórico do PNCP]] |

## Processamento e dados

| Termo | O que é | Onde |
|---|---|---|
| **n8n, fluxo, nó** | o orquestrador; cada fluxo (W00 a W90) é uma sequência de nós visível no canvas | [[MOC Fluxos n8n]] |
| **worker** | o serviço em Python que faz o trabalho pesado: OCR, conversão, prompt, verificação e relatório | [[Worker — visão geral e jobs]] |
| **job** | um trabalho longo do worker (baixar, ler, histórico), numa fila própria, acompanhado pelo n8n até terminar | [[Worker — visão geral e jobs]] |
| **webhook** | o endereço que o site chama para disparar um fluxo | [[W11 Ações do site]] |
| **estado da licitação** | a etapa em que ela está — nova, baixada, lendo, preparada, extraindo, respondida, verificada, publicada, entre os 20 estados da máquina | [[Ciclo de vida de uma licitação]] |
| **lease** | reserva com prazo (2 h): enquanto vale, nenhum outro processo pega a mesma licitação | [[W10 Fila]] |
| **backoff** | a espera crescente entre tentativas: 15 min, 2 h, 12 h; na 4ª falha, erro definitivo | [[Funções e views do banco]] |
| **disjuntor** | 3 ou mais erros do W20 em 30 minutos, sem nenhum sucesso, param a fila | [[W10 Fila]] |
| **coleta cega** | rodada que não conseguiu consultar a fonte — registrada como diferente de "não há nada novo" | [[Disponibilidade do PNCP]] |
| **texto congelado** | o texto de cada página guardado no banco na leitura; extração e verificação usam sempre ele | [[W22 Ler]] |
| **OCR** | leitura de texto em página digitalizada; aqui, o Tesseract 5.4.0 compilado na imagem | [[OCR]] |
| **texto escondido** | texto que a máquina lê e uma pessoa não vê na página (branco, transparente, minúsculo ou fora da página) — detectado e marcado | [[Injeção de prompt e defesas]] |
| **acervo** | as licitações e documentos processados pela versão anterior, importados sem reprocessar | [[Acervo e migração da v2]] |
| **armazenamento pelo conteúdo** | cada arquivo guardado no S3 pelo seu hash: o mesmo arquivo é guardado uma vez | [[Armazenamento de arquivos (S3)]] |
| **migração** | arquivo SQL numerado, aplicado em ordem, com o hash conferido | [[Migrações do banco]] |
| **invariante** | consulta que deve voltar vazia; cada linha é uma violação da integridade | [[Modelo de dados]] |

## IA

| Termo | O que é | Onde |
|---|---|---|
| **as 17 perguntas** | o questionário que decide o lance; 7 são **críticas** (Q1, Q5, Q9, Q12, Q13, Q14, Q17) | [[Questionário — as 17 perguntas]] |
| **provedor** | quem responde: `claude` ou `openai` (modelos pagos), `simulado` (expressões regulares, sem modelo, só em ensaio) ou `gravado` (repete respostas já gravadas) | [[Modelos e provedores]] |
| **lote** | 6 perguntas por chamada: as 17 perguntas saem em 3 chamadas | [[Prompt do extrator]] |
| **contexto completo × RAG** | até 180 mil caracteres, o modelo lê o documento inteiro; acima disso, lê só as páginas recuperadas para cada pergunta | [[RAG com BM25]] |
| **BM25** | ranking de páginas por palavras (sem embeddings), usado para recuperar as 12 páginas mais relevantes por pergunta | [[RAG com BM25]] |
| **cache de prompt** | o trecho repetido entre chamadas é gravado uma vez e relido a 10% do preço (a gravação custa 1,25×) | [[Cache de prompt e ordem do prompt]] |
| **esforço de raciocínio** | quanto o modelo raciocina antes de responder (a cadeia de raciocínio, *chain-of-thought*); fixo em `medium` | [[Chain-of-thought e esforço de raciocínio]] |
| **Best-of-N e reforço** | até 3 tentativas só para as perguntas que falharam; o verificador escolhe a melhor | [[Best-of-N]] |
| **Jev** | modelo de decisão tipada com probabilidade, usado como segundo sinal de escopo e de sustentação; nunca decide | [[Jev — score de escopo e sustentação]] |
| **sustentação** | a nota do Jev para "o trecho citado sustenta a resposta?", mostrada como "sustenta N%" | [[Jev — score de escopo e sustentação]] |
| **injeção de prompt** | instrução maliciosa escondida num documento para desviar o modelo | [[Injeção de prompt e defesas]] |
| **versão do prompt, das regras e do escopo** | hashes que dizem com que prompt, regras de verificação e regra de escopo cada resultado foi produzido | [[Controles de consistência]] |

## Verificação e avaliação

| Termo | O que é | Onde |
|---|---|---|
| **ancoragem** | a prova de que o trecho citado está na página citada — contido nela, ou com similaridade ≥ 0,90 e todos os números presentes | [[Verificador determinístico]] |
| **veredito** | o resultado da verificação de cada resposta: **APROVADO**, **REVISAR** ou **REPROVADO** | [[Verificador determinístico]] |
| **RN-nn** | as regras de negócio numeradas do verificador — por exemplo, a RN-09 compara a soma da pirâmide com o total de servidores | [[Verificador determinístico]] |
| **verificação vigente** | a verificação que o site mostra; as anteriores ficam guardadas | [[Controles de consistência]] |
| **reverificação** | aplicar as regras atuais às respostas já gravadas, sem chamar modelo e a custo zero | [[W30 Reverificar em lote]] |
| **ensaio** | licitação marcada para aceitar resultado simulado; o banco recusa resultado simulado como vigente fora de ensaio | [[Controles de consistência]] |
| **gabarito** | as respostas certas de uma licitação, conferidas por pessoa, página a página — Pirapó/RS e Bertioga/SP | [[Gabaritos]] |
| **harness** | o conjunto que roda uma configuração contra os gabaritos e guarda a evidência de cada resposta | [[Harness de avaliação]] |
| **acurácia, completude, integridade** | acertar o fato, trazer tudo o que a resposta pede e citar um trecho que existe | [[Métricas]] |

## Operação, infraestrutura e segurança

| Termo | O que é | Onde |
|---|---|---|
| **EC2, S3, sa-east-1** | a máquina virtual e o armazenamento de arquivos da AWS, na região de São Paulo | [[Hospedagem na AWS]] |
| **Docker Compose** | a descrição dos containers da solução, a mesma na máquina local e na produção | [[Containers e serviços]] |
| **Caddy** | o servidor na frente de tudo, com HTTPS automático; do n8n, só o caminho dos webhooks fica público | [[Domínio, DNS e HTTPS]] |
| **SPF, DKIM, DMARC** | os registros que autenticam os e-mails enviados pelo domínio | [[E-mails do produto]] |
| **OAuth 2.0, OpenID Connect, PKCE** | o protocolo do login com Google e a proteção do código de autorização | [[Login com Google]] |
| **papéis** | usuário, operador, administrador e administrador supremo | [[Papéis e acesso]] |
| **ponto de restauração** | banco verificado, imagens e manifesto guardados antes de uma troca de versão | [[Backup e restauração]] |
| **camadas do CI** | a (a), sem acervo e sem infraestrutura, que roda em qualquer lugar; a (b), que confere a instalação local | [[Testes e CI]] |

## Relacionadas

[[Home]] · [[Mapa mental]] · [[Visão geral da solução]] · [[Requisitos do case — onde cada um está atendido]]
