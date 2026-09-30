---
tipo: avaliacao
familia: ia
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/melhor_de_n.py
  - scripts/fopa/recuperacao.py
  - api/modelos_ia.py
  - api/jev.py
tags: [ia, tecnicas, decisao, rag, fine-tuning, best-of-n, avaliacao]
---

# Técnicas avaliadas e descartadas

> [!abstract] Em uma frase
> Cada técnica de IA considerada para a solução passou pelo mesmo critério — **ela se apoia em algo que o projeto já tem e melhora uma medida real?** —; as que passaram estão em produção com número, e as que não passaram estão aqui com o motivo e com o que as traria de volta.

## Papel na solução

Escolher técnica por reputação é o jeito mais rápido de adicionar custo e risco sem ganho. O projeto tem um ativo raro que decidiu quase todas as linhas abaixo: um **avaliador determinístico, gratuito e sem modelo** — o [[Verificador determinístico]] — e dois **gabaritos humanos** para medir acurácia ([[Gabaritos]]). Com eles, uma técnica deixa de ser argumento e vira experimento.

## O que está em produção

| Técnica | Como está na solução | O número que a sustenta |
|---|---|---|
| **RAG** (recuperação) | híbrido: contexto completo até 180 mil caracteres, BM25 por página acima disso, com arquivos-âncora ([[RAG com BM25]]) | no mesmo edital, −45% de entrada e −36% de custo com a mesma acurácia (17/17, 7/7 críticas) |
| **Chain-of-thought** | raciocínio adaptativo do modelo, esforço fixo `medium` ([[Chain-of-thought e esforço de raciocínio]]) | 75% a 79% da saída é raciocínio; `low`, `medium` e `high` deram a mesma acurácia |
| **Escala de computação na inferência** | dois eixos: profundidade (esforço) e amostragem (Best-of-N) | subir o esforço não mudou a acurácia; a amostragem dirigida recuperou uma crítica |
| **Best-of-N** | até 2 tentativas extras só nas respostas que falham, escolhidas pelo verificador ([[Best-of-N]]) | 8 respostas reforçadas: 4 ausências confirmadas, 1 crítica recuperada, nenhuma piorou |
| **Saída estruturada** | esquema JSON fechado, todos os campos obrigatórios ([[Prompt do extrator]]) | nenhum parser frágil; nenhum campo livre para instrução injetada |
| **Cache de prompt** | documentos antes das perguntas, dois pontos de cache no Claude ([[Cache de prompt e ordem do prompt]]) | −32,5% no Claude em contexto completo |
| **Regras antes de IA** | escopo por vocabulário, com motivo e versão ([[Regras antes de IA]]) | custo zero; o Jev confirmou o filtro com probabilidade média de 0,91 |
| **Classificador probabilístico como segundo sinal** | Jev no escopo e no "sustenta?", só com convicção ([[Jev — score de escopo e sustentação]]) | discordâncias convictas com a regra de 75 para 2 depois das correções que ele apontou |
| **Exemplos no contexto** (*in-context learning*) | pontual: o critério do Jev traz exemplos dos dois lados; o prompt do extrator usa regras e formato, não exemplos | o critério com exemplos subiu a AUC do Jev de 0,947 para 0,968 |

## O que foi descartado, e por quê

| Técnica | Decisão | Motivo | O que a traria de volta |
|---|---|---|---|
| **Embeddings + banco vetorial** | ❌ | o vocabulário do edital é fechado e a pergunta usa as palavras da resposta; embedding custaria dependência externa, custo por token e documento saindo do servidor para resolver paráfrase que quase não há | editais descrevendo a mesma exigência com palavras diferentes, além do que a curadoria de termos alcança |
| **Fine-tuning** | ❌ | não há volume rotulado (dois gabaritos); o problema é de evidência, não de estilo; cada mudança do questionário exigiria retreino; um modelo ajustado pode "saber" a resposta típica sem que ela esteja no documento | ao menos 500 editais com gabarito humano **e** o gargalo medido ser custo, não acurácia |
| **Modelo como juiz** (*LLM-as-judge*) | ❌ | herdaria a subjetividade do juiz e o mesmo modo de falha que deveria detectar; tornaria a avaliação não reprodutível | — é o princípio da verificação ([[ADR-004 Evidência obrigatória]]) |
| **Modelo extrativo** (resposta como recorte do texto) | ❌ | quebra em três perguntas: a Q13 junta várias tabelas, a Q11 resume obrigações, a Q1 decide entre datas em arquivos diferentes; a rastreabilidade que ele daria vem de exigir o trecho literal e conferi-lo | — |
| **Recorte por parágrafo** no RAG | ❌ | perderia a página física, que é a unidade de citação | — |
| **OCR em nuvem ou por modelo de visão** | ❌ | nuvem envia o documento a terceiro; modelo de visão não é determinístico e reintroduz o risco que a verificação elimina ([[OCR]]) | — |
| **Modelo aberto local na extração** | ❌ | o OCR já é local, o que resolve a parte sensível; na extração, a diferença de acurácia não se paga | política do banco que proíba modelo de terceiro em nuvem |
| **Claude Haiku 4.5 como extrator padrão** | ❌ | errou uma pergunta crítica por desistência e tem teto de 200 mil tokens de contexto; segue no catálogo como opção barata ([[Modelos e provedores]]) | — |
| **Reamostrar as 17 perguntas** | ❌ | N vezes o custo para mexer no que já ancora | — |
| **Classificador de escopo treinado** | ❌ | os rótulos disponíveis vêm em boa parte do próprio filtro; treinar neles imitaria o filtro, erros incluídos | rótulos humanos independentes em volume |
| **Decompor a pergunta do Jev** em 5 perguntas atômicas | ❌ refutada por medição | AUC de 0,624 e 72 folhas recusadas com convicção: "é sobre consignado?" é verdade para contratos de folha que incluem consignado | — |

## Nomes que foram avaliados e não se aplicam

Algumas técnicas do estado da arte foram consideradas porque o comportamento da solução lembra o que elas descrevem — e rejeitadas porque o nome não corresponde ao que existe aqui.

| Técnica | Por que não se aplica |
|---|---|
| **Process Reward Model** | premia os passos do raciocínio e exige rótulos passo a passo; o verificador é um **modelo de recompensa de resultado** (ORM) determinístico: a resposta ancora ou não |
| **Monte Carlo Tree Search** | busca em árvore precisa de decisões sequenciais com ramificação; as 17 perguntas são independentes — o Best-of-N é a forma correta do mesmo instinto |
| **PPO e GRPO** | ajustam pesos por reforço: exigem acesso aos pesos (o modelo é consumido por API) e milhares de exemplos rotulados |
| **Consciência situacional emergente** | é propriedade de modelo medida em laboratório de segurança; o que a solução tem é monitoramento de si em tempo de execução ([[Consciência operacional]]) |
| **Autoaperfeiçoamento recursivo** | o ciclo que existe — o Jev acha divergências, uma pessoa rotula, a regra melhora — tem um humano no meio, e é justamente ele que fecha o ciclo |

## O que está em teste

| Hipótese | Por que ainda não entrou |
|---|---|
| `prompt_cache_key` da OpenAI, igual em todos os lotes da licitação | a mudança de ordem não fez a OpenAI ler o cache; a chave de roteamento é a próxima hipótese, não medida ([[Próximos passos]]) |
| Combinar perguntas do Jev por regressão logística | AUC de 0,985 em validação cruzada, mas com erros convictos e só 48 negativos para aprender |
| Variar o tamanho do lote (hoje 6 perguntas) | é parâmetro do Admin justamente para ser medido; ainda não foi varrido |

## Relacionadas

[[MOC IA]] · [[RAG com BM25]] · [[Best-of-N]] · [[Chain-of-thought e esforço de raciocínio]] · [[Verificador determinístico]] · [[Jev — score de escopo e sustentação]] · [[Consciência operacional]] · [[Resultados medidos]] · [[ADR-010 RAG vs contexto completo]] · [[Próximos passos]]
