---
tipo: tecnica
familia: ia
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/verificador.py
  - scripts/fopa/distribuicao.py
  - scripts/fopa/condicoes.py
  - api/politica.py
  - api/injecao.py
  - api/persistencia.py
  - api/versao.py
  - api/rotas_extracao.py
  - db/005_verificacoes.sql
tags: [ia, verificador, antialucinacao, ancoragem, nucleo]
---

# Verificador determinístico

> [!abstract] Em uma frase
> Toda resposta do modelo é conferida **sem IA**: o trecho citado precisa existir na página citada (similaridade de pelo menos 0,90 para letras e igualdade exata para algarismos), e regras de domínio conferem a pirâmide, o total de servidores, o objeto entre documentos, as lacunas e os campos do PNCP; o resultado é um veredito por pergunta — **APROVADO, REVISAR ou REPROVADO** — com os motivos escritos.

## Papel na solução

É a peça que justifica a solução ([[ADR-004 Evidência obrigatória]]). Uma resposta alucinada é indistinguível de uma correta: mesmo formato, mesma confiança, página citada. Se a verificação também fosse feita por um modelo de linguagem, herdaria exatamente o modo de falha que deveria detectar — uma alucinação plausível confirmada por outra alucinação plausível. Aqui só há comparação de texto e aritmética, coisas que não inventam.

**Quem gera não verifica:** o modelo produz ([[Prompt do extrator]]); o verificador, código Python puro, confere. É por causa dele que o relatório pode ser usado sem reconferir cada linha à mão — e que trocar de modelo ou de fornecedor não muda a garantia ([[Modelos e provedores]]).

## Onde roda

| Rota do worker | Chamada por | Quando |
|---|---|---|
| `POST /verificar` | [[W24 Verificar e publicar]] | depois de cada extração: funde as chamadas gravadas, escolhe entre os candidatos do [[Best-of-N]], verifica, grava |
| `POST /reverificar` | [[W11 Ações do site]] ("Reverificar"), [[W30 Reverificar em lote]] | quando as regras mudam: as mesmas respostas, contra o mesmo texto congelado, com as regras novas — **R$ 0,00** |
| `POST /importar-respostas` | [[W11 Ações do site]] ("Importar respostas do agente") | respostas produzidas fora da API passam pelo **mesmo** verificador |

O verificador confere contra a **leitura congelada** no banco (o texto de cada página, tal como o [[W22 Ler]] gravou), nunca contra uma nova leitura do PDF: a mesma resposta, verificada duas vezes com as mesmas regras, dá o mesmo resultado.

## Etapa 1 — A ancoragem, resposta por resposta

A pergunta que ela responde é uma só: **o trecho citado existe mesmo naquela página?** O texto dos dois lados é normalizado antes de comparar — sem acentos, minúsculo, espaços colapsados e a hifenização de fim de linha desfeita —, porque é isso que o PDF bagunça.

| # | Situação | Veredito | Motivo registrado |
|---|---|---|---|
| 1 | "Não localizado" sem trecho, arquivo e página | APROVADO nesta etapa (a política da v3 rebaixa depois) | ausência declarada |
| 2 | resposta sem trecho | REPROVADO | "sem trecho literal utilizável" |
| 3 | resposta sem arquivo ou sem página | REPROVADO | "resposta sem arquivo ou página" |
| 4 | a página citada não existe | REPROVADO | "página citada não existe" |
| 5 | a página já tinha sido corrigida numa verificação anterior | REVISAR | a correção continua sendo um fato sobre a citação |
| 6 | trecho com menos de 12 caracteres | APROVADO **só se** ele aparece uma única vez em todo o conjunto, e na página citada (típico de valor em célula de tabela); senão REPROVADO | curto e repetido não prova nada |
| 7 | o trecho está contido na página | **APROVADO** | — |
| 8 | melhor casamento local ≥ **0,90** | APROVADO, **se todo número do trecho estiver na página**; senão REPROVADO | "ancoragem aproximada — ruído de PDF" ou "o número X não aparece na página citada" |
| 9 | o trecho está em **outra** página (mesmo arquivo ou outro) | REVISAR, com a citação **corrigida** e a página citada guardada | "página corrigida: o trecho está na p. N" |
| 10 | nada disso | REPROVADO | "trecho não encontrado na página citada (melhor casamento X)" |

Detalhes que decidem casos reais:

- **O casamento aproximado** usa uma janela deslizante do tamanho do trecho, com passo de um quarto do tamanho, e `difflib.SequenceMatcher` com `autojunk` desligado (ligado, a similaridade colapsa em textos longos). O limiar de 0,90 absorve o ruído de extração de PDF — hifenização, espaço duplo, ligadura.
- **A folga vale para letra, não para algarismo.** Ruído de PDF não troca dígito. Antes dessa guarda, citações falsas passavam com folga:

| Citação falsa | Similaridade | Veredito sem a guarda |
|---|---|---|
| R$ 1.250.000,00 → R$ 2.250.000,00 | 0,98 | aprovado |
| R$ 1.250.000,00 → R$ 125.000,00 | 0,98 | aprovado |
| R$ 1.250.000,00 → R$ 10,00 | 0,93 | aprovado |
| 60 (sessenta) meses → 6 (seis) meses | 0,92 | aprovado |

  Com a guarda, todo número que o trecho afirma precisa estar na página, sem aproximação. Na reverificação de 190 respostas reais de dois fornecedores, ela não reprovou nenhuma resposta legítima.
- **O nome do arquivo** é resolvido primeiro por igualdade; se não bater, por um apelido normalizado (sem o rótulo do marcador, sem pontuação) — aceito **só se resolver para um único arquivo**. Em Bertioga/SP há três arquivos `RESPOSTA.pdf`: uma citação ambígua continua reprovando. Tolerar o apelido resolve um problema de identificador; tolerar a ambiguidade afrouxaria a verificação.
- **Página vizinha não é alucinação.** O trecho certo na página errada (a cláusula que atravessa a virada de página) é corrigido e vai para revisão, em vez de ser descartado junto com o trecho inventado — que não existe em lugar nenhum.

Depois da ancoragem, duas regras só **rebaixam**: resposta com `conflito` relatado pelo modelo vai de APROVADO para REVISAR, e resposta com confiança `baixa` também. Confiança alta nunca promove.

## Etapa 2 — As regras sobre o conjunto

A ancoragem confere uma resposta contra **uma** página. Alguns erros só aparecem cruzando respostas ou documentos. Cada regra gera um alerta com código, e o alerta recai sobre a pergunta pela **regra** que o gerou — nunca por menção de texto.

| Código | Pergunta | O que confere | O caso que a originou |
|---|---|---|---|
| **RN-09** | Q13 | a soma das faixas da pirâmide contra o total declarado na Q14; abaixo de 60% do total, "forte indício de que só parte das tabelas foi lida"; com menos de duas faixas reconhecidas, declara que **não aplicou** a regra | Bertioga/SP: faixas somando 1.408 contra 1.896 vínculos — 488 faltando justamente nas faixas mais altas |
| **RN-10** | Q13 | uma quantidade de faixa maior ou igual à soma de todas as outras (a assinatura de um total deslocado para uma linha) | São Lourenço do Sul/RS: o total 287 lido na faixa "acima de R$ 10.000" |
| **RN-11** | Q13 | a resposta declara qual população a pirâmide cobre (ativos, inativos, pensionistas, vínculo) | Bertioga/SP exclui aposentados e pensionistas; São Lourenço do Sul/RS inclui |
| **RN-12** | Q14 | a resposta declara a unidade: vínculos ou pessoas | Bertioga/SP: 1.896 eram vínculos, e o edital não informava o número de pessoas |
| **RN-13** | Q2 | a população coberta é a mesma em todas as definições de objeto do conjunto (edital × minuta de contrato) | Pirapó/RS: o edital licita ativos, inativos e pensionistas; a minuta, só os Poderes — os inativos eram 31,9% da folha, e todos os modelos ancoraram 100% citando um lado só |
| **RN-14** | Q13 | a Q13 traz distribuição por vínculo, e não por faixa salarial (sem faixa não há ticket médio), ou a pirâmide foi lida em parte | Fruta de Leite/MG: 504 servidores contados por vínculo, sem salário |
| **RN-15** | conjunto | lista **todo** "não localizado", sem exceção; com 5 ou mais de uma vez, avisa que a causa provável é falta de insumo, não edital omisso | uma ausência que vira rotina para de ser olhada |
| cruzamento com o PNCP | Q5 e Q4 | o valor da Q5 contra o `valorTotal` dos itens da API; o critério da Q4 contra o `criterioJulgamentoNome`, comparando **famílias** de critério ("maior oferta" = "maior lance"); divergência sugere documento superado | três alarmes falsos com comparação literal; conforto falso com comparação pela primeira palavra |
| sanidade | Q1, Q9 | a Q1 contém data `DD/MM/AAAA`; a vigência da Q9 está entre 6 e 120 meses; nenhuma pergunta faltando | — |

> [!important] Uma regra precisa saber quando falhou em ler
> Toda regra declara quando **não conseguiu ler** o material — "RN-09 não aplicada: só 1 faixa foi reconhecida; a pirâmide precisa de conferência humana" — e esse estado é diferente de aprovar. Silêncio lido como conferência é o pior dos dois mundos, porque parece seguro ([[ADR-011 Uma regra precisa saber quando falhou em ler]]).

## A política da v3

Depois do verificador, uma política de produto (`api/politica.py`) **rebaixa todo "Não localizado" aprovado para REVISAR**, com o motivo "a resposta não está nos documentos — conferir antes de usar", inclusive as perguntas que não se aplicam à modalidade. A regra só rebaixa: REPROVADO continua REPROVADO. O motivo: para quem usa o produto, a pergunta que o edital não respondeu é justamente a que precisa de olho humano — pode ser lacuna do edital, candidata a pedido de esclarecimento, ou página que não chegou à leitura.

## Etapa 3 — As condições da leitura

A verificação também registra **sob que condições** a resposta foi produzida, derivadas de fatos observados e não da confiança que o modelo declara sobre si ([[Consciência operacional]]): documentos que não foram lidos, arquivos que exigiram OCR, provedor secundário, perguntas em que o modelo se absteve e **texto furtivo** — texto que o PDF mostra à máquina e esconde do leitor. Só o trecho furtivo com cara de instrução para IA gera a tag **"Prompt Injection - Conteúdo Suspeito"**, que marca a verificação como degradada e abre revisão humana ([[Injeção de prompt e defesas]]).

## O que fica gravado

| Tabela | O que guarda |
|---|---|
| `verificacoes` | uma linha por verificação: versão das regras, contagens (aprovadas, revisar, reprovadas, não localizado, ancoradas, respondidas), taxa de ancoragem, alertas globais, tags, se a leitura foi degradada, condições, a Q13 estruturada, se usou os itens da API, a auditoria completa em JSON e se é a **vigente** |
| `verificacao_respostas` | uma linha por pergunta: veredito, arquivo resolvido, página final, **página citada pelo modelo**, alertas e o tipo de ausência (`nao_se_aplica`, `sem_evidencia` ou `falta_evidencia`) |

- **Uma verificação por execução e versão de regras:** verificar de novo com as mesmas regras devolve 409, nunca duplica.
- **A verificação nasce não vigente.** Tornar vigente é decisão do fluxo (W24 ou W30), nunca efeito colateral de verificar. Um índice único garante **uma** vigente por licitação.
- **A taxa de ancoragem é separada do veredito:** conta as respostas cujo trecho conferiu, **antes** de qualquer rebaixamento por conflito ou confiança. Uma resposta pode estar perfeitamente ancorada e ainda ir para revisão por conflito entre documentos — são coisas diferentes, e misturá-las esconderia a métrica que importa.

## Versão das regras e reverificação a custo zero

A `versao_regras` é o SHA-256 do conteúdo de `verificador.py`, `questionario.py`, `distribuicao.py`, `condicoes.py`, `api/politica.py` e `api/injecao.py` — tudo o que decide veredito e tag. Um número escolhido à mão depende de alguém lembrar de incrementar; o hash muda sozinho quando o código muda. Em produção, a versão vigente é `b32b66ede7f6…` ([[Página Saúde]]).

Como o verificador não usa IA e o texto está congelado, **mudar uma regra e remedir são passos separados e gratuitos**: o [[W30 Reverificar em lote]] aplica as regras novas às respostas vigentes e grava o diff. Reexecutar o modelo mudaria duas variáveis ao mesmo tempo — a regra e a amostra — e não provaria qual moveu o número.

Validação de cinco correções de regra em 22/09/2026, sem gastar um token:

| Verificação | Antes | Depois |
|---|---|---|
| Claude Haiku 4.5 · Pirapó (nome de arquivo citado com o rótulo do marcador) | 0/13 | **12/13** |
| RN-09 numa pirâmide íntegra (Pirapó) | alarme nos 3 modelos | **silenciosa nos 3** |
| RN-09 numa pirâmide truncada (Bertioga) | número invertido | **488 faltantes nos 3** |
| RN-13 em editais consistentes | acusava 3 | **silenciosa em 11 de 13** |

A regra ficar silenciosa nos três modelos onde a pirâmide está certa e disparar nos três onde ela está truncada é a evidência de que voltou a medir **o documento**, e não a redação de quem o leu.

## Em produção

| Recorte (28/09/2026) | Respostas com trecho conferido na página citada |
|---|---|
| Painel — licitações ativas | **98,67%** (822 de 833) |
| Histórico | **99,96%** (25.114 de 25.122) |

Caso real, Itapecuru Mirim/MA (Claude Haiku 4.5): **9 de 16** respostas ancoradas, 7 aprovadas, 8 para revisão e 2 reprovadas; alertas RN-09 (faixas somando 3.338 contra 3.385 declarados na Q14, diferença de 47), RN-15 (Q16 sem resposta) e a Q1 fora do formato `DD/MM/AAAA`. Nada disso impediu a publicação — publicou com os vereditos e abriu as revisões: as reprovadas e as críticas em REVISAR (Q5, Q9, Q14 e Q17).

## O que o verificador não pega, e o que cobre essas lacunas

| Lacuna | Cobertura |
|---|---|
| trecho que existe na página mas **não responde** à pergunta ("prazo de 12 meses para a garantia" citado como vigência) | o sinal "sustenta?" do Jev abre candidata de revisão ([[Jev — score de escopo e sustentação]]) |
| divergência **entre** páginas que o modelo não relatou | RN-13 para o objeto; o campo `conflito`; o contexto completo quando cabe ([[RAG com BM25]]) |
| erro que já está **na página**, vindo do OCR (um fio de tabela lido como o algarismo 1) | pirâmide lida por OCR nunca entra sozinha: vai para revisão com a marca ([[OCR]]) |
| resposta certa que a regra lê errado | toda regra declara quando não conseguiu ler; falso positivo do verificador é tratado como defeito grave |

## Relacionadas

[[MOC IA]] · [[Prompt do extrator]] · [[Best-of-N]] · [[Questionário — as 17 perguntas]] · [[Consciência operacional]] · [[Injeção de prompt e defesas]] · [[Jev — score de escopo e sustentação]] · [[W24 Verificar e publicar]] · [[W30 Reverificar em lote]] · [[Controles de consistência]] · [[Métricas]] · [[ADR-004 Evidência obrigatória]] · [[ADR-011 Uma regra precisa saber quando falhou em ler]] · [[Página Revisão]]
