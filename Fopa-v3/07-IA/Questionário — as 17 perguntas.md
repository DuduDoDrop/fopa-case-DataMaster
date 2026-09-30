---
tipo: referencia
familia: ia
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/questionario.py
  - scripts/fopa/recuperacao.py
  - db/004_perguntas_execucoes_chamadas_respostas.sql
  - db/012_seed.sql
  - n8n/workflows/W24.json
tags: [ia, questionario, extracao, rag, nucleo]
---

# Questionário — as 17 perguntas

> [!abstract] Em uma frase
> As 17 perguntas que a solução responde para cada licitação de folha — com a orientação que o modelo recebe, o formato esperado, a marca das **7 críticas** (as que entram no cálculo do lance), as perguntas que **não se aplicam** a certas modalidades e os **termos de recuperação** que alimentam o BM25.

## Papel na solução

É o contrato do entregável. Um único módulo, `scripts/fopa/questionario.py`, define o que o [[Prompt do extrator]] pergunta, o que o [[Verificador determinístico]] confere, o que a [[Página Detalhe da licitação]] e a [[Página Relatório]] mostram e o que o [[RAG com BM25]] procura. O site lê a lista pelo `GET /api/questionario`, que vem do worker: não existe uma segunda cópia das perguntas. No banco, a tabela `perguntas` é semeada com o mesmo texto, e um teste confere que id, texto, formato e marca de crítica batem com o módulo.

Qualquer mudança aqui — texto, orientação, termo ou marca de crítica — muda a **`versao_prompt`**, o hash SHA-256 do que o modelo vê ([[Cache de prompt e ordem do prompt]]). Toda execução grava a versão com que rodou, e execuções de versões diferentes nunca se confundem.

## As 17 perguntas

| # | Pergunta (texto exato) | O que o modelo é orientado a responder | Formato exigido | Crítica |
|---|---|---|---|---|
| Q1 | Qual a Data da Licitação ? | data e hora da sessão pública; havendo aviso de retificação, suspensão ou redesignação, vale a data **dele**, não a do edital | `DD/MM/AAAA às HHhMM (horário de Brasília)` | ✅ |
| Q2 | O que diz o Objeto do Edital ? | o texto integral do objeto, sem resumir | livre | |
| Q3 | Qual a Modalidade de Contratação ? | pregão eletrônico, concorrência, credenciamento, dispensa, inexigibilidade | livre | |
| Q4 | Qual o Tipo do Pregão ? | o critério de julgamento (em folha, costuma ser maior lance ou maior oferta); em credenciamento e contratação direta pode não se aplicar | livre | |
| Q5 | Qual o Valor Mínimo de Contratação ? | o valor com o **rótulo como está** no documento: "valor mínimo", "valor estimado" e "valor de referência" são conceitos distintos em leilão de maior oferta, e o rótulo não é normalizado | `R$ X (VALOR POR EXTENSO)`, com o rótulo literal | ✅ |
| Q6 | Qual o valor dos Lances Mínimos ? | o intervalo mínimo entre lances, em % ou R$ | livre | |
| Q7 | Qual é o Prazo de Assinatura do Contrato ? | o prazo e a partir de quando ele conta | livre | |
| Q8 | Qual é o Prazo de Pagamento ? | o prazo para o banco pagar ao ente o valor ofertado | livre | |
| Q9 | Qual o prazo de vigência do contrato ? | em meses ou anos, com a prorrogação, se houver | livre | ✅ |
| Q10 | Qual o prazo de início de serviços ? | o prazo e a prorrogação, se houver | livre | |
| Q11 | Quais são as obrigações do banco vencedor ? | as principais, resumidas sem perder números e prazos | livre | |
| Q12 | Qual é a infraestrutura solicitada ? | agência, PAB, posto de atendimento, caixas eletrônicos e prazo de instalação; se é obrigatória ou facultativa | livre | ✅ |
| Q13 | Qual a quantidade de servidores aberta por faixa salarial ? | a **pirâmide completa**: quase sempre há mais de uma tabela, separada por vínculo (contratos, estatutários, ativos, inativos, pensionistas, temporários); capturar todas, somar cada uma e conferir com o total impresso dela; declarar qual população a pirâmide cobre e qual exclui | `"Vínculo X — Até R$ A: n; R$ A,01 a R$ B: m; Acima de R$ B: k (total N)"` por tabela, mais a população coberta | ✅ |
| Q14 | Qual a Quantidade total de servidores ? | o número total **e a unidade** — vínculos ou pessoas físicas, porque um servidor pode ter mais de um vínculo; se o documento não disser, registrar que não diz | `"N vínculos"` ou `"N pessoas"`, explicitando qual | ✅ |
| Q15 | Quais são as condições do consignado ? | margem consignável, taxa-teto, exclusividade, prazos e quem faz a averbação | livre | |
| Q16 | Existe necessidade do vencedor realizar prova de vida dos servidores ? | sim ou não, e em que condição; recadastramento de beneficiários conta como prova de vida | livre | |
| Q17 | Existe necessidade do vencedor apresentar alguma garantia ? | sim ou não, percentual, modalidade e **a base de cálculo declarada**; pode estar num documento de esclarecimento, não só no edital; nunca calcular o valor | livre | ✅ |

> [!info] O texto das perguntas é o do case
> As perguntas mantêm a redação original do enunciado, inclusive o espaço antes do ponto de interrogação. O que a solução acrescenta é a orientação, o formato e os termos — é ali que mora o conhecimento de domínio.

## Por que estas sete são críticas

A marca `critico` indica as perguntas que **entram no cálculo do lance**. Ela muda o tratamento em quatro lugares:

- **Revisão humana obrigatória:** uma crítica que termina em REVISAR abre revisão na fila, como toda REPROVADA ([[W24 Verificar e publicar]], passo "Abrir revisões").
- **E-mail da extração:** a crítica aparece marcada com `*` na tabela das 17 respostas ([[E-mails do produto]]).
- **Medição:** o placar de acurácia tem uma coluna só para as críticas ([[Métricas]]).
- **Site:** o detalhe da licitação destaca as críticas ([[Página Detalhe da licitação]]).

| Crítica | O que ela decide no negócio |
|---|---|
| Q1 — data | se ainda dá tempo de participar e até quando a proposta precisa estar pronta |
| Q5 — valor mínimo | o piso do lance; um rótulo trocado ("estimado" lido como "mínimo") muda a estratégia |
| Q9 — vigência | por quanto tempo o banco terá a folha — a base de todo cálculo de retorno |
| Q12 — infraestrutura | o custo de instalação (agência, PAB, caixas) que o lance precisa cobrir |
| Q13 — pirâmide | a renda por faixa: ticket médio e potencial de crédito consignado |
| Q14 — total de servidores | o tamanho da base de clientes; contar vínculos como pessoas superestima a base |
| Q17 — garantia | o capital imobilizado durante o contrato |

## Perguntas que não se aplicam a certas modalidades

As 17 perguntas foram desenhadas para pregão e concorrência, que têm sessão, disputa e lance. Em contratação direta e em credenciamento algumas **não cabem** — e ali "não localizado" seria uma resposta enganosa, porque sugeriria que a informação deveria estar no documento.

| Modalidade | Não se aplicam | Motivo registrado na resposta |
|---|---|---|
| Dispensa | Q1, Q4, Q6 | contratação direta: não há sessão pública nem disputa de lances |
| Inexigibilidade | Q1, Q4, Q6 | contratação direta: o fornecedor já está definido, não há sessão nem disputa |
| Credenciamento | Q4, Q6 | credenciamento habilita quem atende aos requisitos; não há julgamento por preço nem lance |

- **O caso que revelou isso:** uma dispensa do Tribunal de Contas do Acre (Rio Branco/AC) voltou com 11 de 17 perguntas em branco. Nenhuma era falha de leitura — a dispensa não tem data de disputa porque não há disputa.
- **A lista é curta de propósito:** só entra a pergunta cuja inaplicabilidade é consequência **direta** da modalidade. O valor mínimo continua valendo numa dispensa: há valor, só não há piso de lance.
- **Como a modalidade é descoberta:** pela Q3 respondida, pela modalidade que o PNCP informa ou pelo nome da licitação — basta uma das três reconhecer ([[Verificador determinístico]]).
- **O efeito no produto:** a resposta recebe a nota "não se aplica a esta modalidade" e não conta como lacuna do documento. Mesmo assim, pela política da v3, todo "Não localizado" vai para REVISAR: quem confirma que a ausência é esperada é uma pessoa. O [[Best-of-N]] não gasta reforço nessas perguntas.

## O formato da resposta

O modelo devolve JSON validado contra um esquema fechado (`additionalProperties: false`): uma lista `respostas` com um objeto por pergunta, todos os campos obrigatórios.

| Campo | Tipo | O que é |
|---|---|---|
| `id` | texto | a pergunta (`Q1` … `Q17`) |
| `resposta` | texto | a resposta transcrita do documento, ou `"Não localizado"` |
| `arquivo` | texto ou nulo | o arquivo de onde veio a resposta |
| `pagina` | inteiro ou nulo | a página **física** do PDF (a que o leitor mostra), não a numeração impressa no rodapé |
| `trecho_literal` | texto ou nulo | o trecho copiado **exatamente** do documento; será conferido caractere a caractere contra a página citada |
| `conflito` | texto ou nulo | a divergência entre documentos, quando houver |
| `confianca` | `alta`, `media` ou `baixa` | a confiança declarada pelo modelo, que só serve para **rebaixar** o veredito, nunca para promover |

`"Não localizado"` com arquivo, página e trecho nulos é uma resposta **correta** e preferível a uma tentativa. Se o modelo omitir uma pergunta do lote, o sistema a registra como "Não localizado" com confiança baixa: ausência nunca vira silêncio.

## Os termos de recuperação

Cada pergunta carrega **termos-sinal** que o [[RAG com BM25]] soma ao texto da pergunta para montar a consulta (`consulta = pergunta + termos`). Eles só atuam quando a licitação é grande demais para ir inteira ao modelo — mas, nesse caso, decidem quais páginas o modelo vê.

| # | Termos-sinal |
|---|---|
| Q1 | sessão pública · abertura · data · hora · retificação · redesignação · suspensão · cronograma · recebimento das propostas |
| Q2 | objeto · constitui o objeto · destina-se · contratação de instituição |
| Q3 | modalidade · pregão · concorrência · credenciamento · dispensa · inexigibilidade · preâmbulo |
| Q4 | critério de julgamento · maior lance · maior oferta · tipo · julgamento |
| Q5 | valor mínimo · valor estimado · valor de referência · R$ · orçamento · valor da contratação |
| Q6 | intervalo mínimo · lance · diferença de valores · intervalo mínimo de diferença de valores · lances intermediários |
| Q7 | assinatura do contrato · convocação · dias úteis · assinar o termo de contrato · convocado para assinar · decair o direito à contratação · prazos recursais · convocará a empresa vencedora · convocado a assinar |
| Q8 | prazo de pagamento · pagamento do valor · dias úteis após · recursos financeiros · realizar o pagamento · pagamento do maior lance · não realizará desembolso · critérios de medição e pagamento |
| Q9 | vigência · meses · prorrogado · duração do contrato |
| Q10 | início da execução · iniciar a operacionalização · implantação dos serviços · iniciar a prestação dos serviços · apta a iniciar · começar a executar · dias para começar · início efetivo · prazo para início |
| Q11 | obrigações da contratada · obrigações da instituição · são obrigações · obrigações da vencedora · caberá à instituição · deverá a contratada |
| Q12 | agência · posto de atendimento · PAB · caixa eletrônico · autoatendimento · instalação · infraestrutura |
| Q13 | faixa salarial · pirâmide · salário · quantidade de servidores · qtde · até R$ · acima de R$ · inativos · pensionistas · ativos |
| Q14 | total de servidores · número aproximado · quantitativo · vínculos · servidores |
| Q15 | consignado · consignação · margem consignável · averbação · empréstimo · empréstimo consignado · cartão de crédito consignado · consignação em folha |
| Q16 | prova de vida · recadastramento · recenseamento · comprovação de vida · beneficiários |
| Q17 | garantia · caução · seguro-garantia · fiança bancária · art. 96 · garantia prestada · garantia de proposta · garantia de execução · garantia contratual · art. 69 |

### Por que os termos foram reescritos a partir dos editais

No início, os termos foram escritos a partir da **pergunta** — o vocabulário de quem analisa. Auditados contra as **729 páginas** das 13 licitações da amostra (22/09/2026), **dez termos não apareciam em página nenhuma**: "prazo para assinar", "prazo de implantação", "obrigações do vencedor", "taxa de juros", "percentual entre lances", "art. 98" e outros quatro. Termo morto não recupera nada, e a falha é silenciosa: a pergunta continua sendo respondida porque as outras palavras salvam, e ninguém descobre que parte dos sinais não fazia nada.

Eles foram trocados pelo que os editais **de fato escrevem**:

| Antes (termo morto) | Depois (o que o edital escreve) |
|---|---|
| prazo para assinar | assinar o termo de contrato · convocado para assinar |
| prazo de implantação | iniciar a operacionalização · implantação dos serviços |
| taxa de juros | empréstimo consignado · consignação em folha |
| art. 98 | garantia prestada · garantia de proposta · garantia de execução |

Recall medido depois da troca, em Pirapó/RS: de 93% para **100%**, e o ponto em que o recall atinge o teto caiu de 12 para 4 páginas por pergunta ([[RAG com BM25]]).

Mais duas correções vieram do mesmo procedimento — perda medida, palavras tiradas do próprio trecho, recall remedido, custo R$ 0,00:

- **Q10 — "começar a executar".** Bertioga/SP escreve *"a contratada tem 60 (sessenta) dias para começar a executar os serviços"*; todos os termos eram da família de "iniciar", e o BM25 é léxico: não atravessa "começar" ↔ "iniciar". A página não entrava nem entre as 12 mais bem pontuadas de 115. Com quatro expressões novas, o recall foi de 98,0% para 100% com 12 páginas por pergunta e de 93,9% para 95,9% com 6.
- **Q7 — "convocará a empresa vencedora".** São Lourenço do Sul/RS escreve *"esgotados todos os prazos recursais, a Administração convocará a empresa vencedora do certame"*; nenhum dos seis termos aparecia no trecho. Com três expressões novas, o recall com 6 páginas por pergunta foi de 97,0% para **100%**.

> [!important] A exceção deliberada: a Q16
> "Prova de vida", "recenseamento" e "comprovação de vida" também não aparecem na maioria dos editais — e ali isso **é a resposta**, não defeito: o conceito não existe nesses documentos. Termo de conceito ausente é **sonda negativa** e fica como está. Bertioga/SP mostra que a sonda funciona: é a única da amostra em que a Q16 não é "não localizado" (o item 5.4 obriga o recadastramento dos beneficiários).

## Onde o questionário aparece em produção

| Onde | Como |
|---|---|
| [[Prompt do extrator]] | o bloco de perguntas de cada lote traz `Qn. pergunta`, `O que responder:` e `Formato:` |
| [[RAG com BM25]] | `consulta = texto da pergunta + termos` |
| [[Verificador determinístico]] | as regras da Q13 e da Q14, o "não se aplica" por modalidade, a sanidade da Q1 e da Q9 |
| Banco | tabela `perguntas` (as 17, com a marca de crítica) e `respostas` (uma linha por pergunta por execução) — [[Modelo de dados]] |
| Site | [[Página Detalhe da licitação]] (um cartão por pergunta), [[Página Relatório]], [[Página Revisão]] |
| E-mail | a tabela das 17 respostas no aviso de extração ([[E-mails do produto]]) |

## Relacionadas

[[MOC IA]] · [[Prompt do extrator]] · [[RAG com BM25]] · [[Verificador determinístico]] · [[Best-of-N]] · [[W23 Extrair]] · [[W24 Verificar e publicar]] · [[Página Detalhe da licitação]] · [[Modelo de dados]] · [[Glossário]]
