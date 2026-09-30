---
tipo: etica
familia: seguranca-e-etica
status: verificado
atualizado: 2026-09-28
tags: [etica, responsabilidade, riscos, controles, nucleo]
---

# Premissas éticas e matriz de cenários

> [!abstract] Em uma frase
> A solução parte de cinco premissas — **a IA não decide o lance, toda afirmação tem prova, ausência é resposta legítima, dado pessoal não é o alvo e o custo tem teto** — e cada cenário de risco conhecido tem um controle implementado, com o lugar exato onde ele vive em produção.

## Papel na solução

Responsabilidade num sistema de IA não é declaração de intenção: é o conjunto de controles que tornam o comportamento previsível, auditável e corrigível. Esta nota amarra cada premissa a mecanismos concretos e lista os cenários que foram pensados — e os que dependem de decisão do banco.

## As premissas

| # | Premissa | O que ela implica |
|---|---|---|
| 1 | **A IA informa uma decisão humana; não decide** | o produto entrega respostas com evidência e uma fila de revisão; o lance é decidido por pessoas; nenhuma saída de modelo aprova, rotula escopo ou muda estado sozinha |
| 2 | **Toda afirmação tem prova conferível** | arquivo, página e trecho literal em toda resposta, conferidos por código sem IA ([[ADR-004 Evidência obrigatória]]) |
| 3 | **"Não localizado" é resposta legítima; conflito é informação** | o sistema não é obrigado a ter opinião; divergência entre documentos é relatada, nunca resolvida em silêncio; toda ausência vai para revisão |
| 4 | **Dado pessoal não é o alvo** | as perguntas pedem agregados; login com o mínimo (nome e e-mail); documentos no Brasil, com acesso restrito ([[Privacidade e LGPD]]) |
| 5 | **O custo e o consumo de serviços públicos têm limite** | teto diário de gasto com IA; coleta identificada, com ritmo conservador e mínima ([[Legalidade da automação]]) |

## A matriz de cenários

| Cenário | Risco | Controle | Onde vive |
|---|---|---|---|
| o modelo **inventa** uma resposta plausível | lance calculado sobre dado falso | ancoragem do trecho na página, com guarda numérica; reprovada vai para revisão | [[Verificador determinístico]] |
| o trecho existe mas **não responde** à pergunta | resposta ancorada e errada | sinal "sustenta?" do Jev abre revisão; gabarito mede a acurácia | [[Jev — score de escopo e sustentação]], [[Gabaritos]] |
| documentos da licitação **se contradizem** | usar a data ou o valor superado | precedência documental no prompt e no RAG; campo `conflito`; regra de objeto entre documentos; cruzamento com o PNCP | [[ADR-006 Documento vigente é o de maior sequencial]] |
| o edital é **retificado** depois da leitura | resposta velha com cara de certa | acompanhamento de documentos novos e reprocessamento | [[W70 Retificações]], [[W01 Descoberta]] |
| **injeção de prompt** no documento | desvio ou corrupção de dado | documento nunca vira instrução; esquema fechado; ancoragem; detecção e classificação de texto escondido; tag e revisão | [[Injeção de prompt e defesas]] |
| OCR **erra um número** da pirâmide | valor errado no preço | perfil de tabela otimizado para zero erro; pirâmide de OCR sempre revisada; regras de soma | [[OCR]], [[ADR-008 OCR — stack, configuração e limites]] |
| a regra do verificador **lê errado** | alarme falso ou silêncio lido como conferência | a regra declara quando não aplicou; versão por hash; reverificação a custo zero; caso de controle | [[ADR-011 Uma regra precisa saber quando falhou em ler]] |
| **ensaio vira resultado** oficial | resposta de regex publicada como de modelo | restrição, gatilhos e invariante no banco (T15) | [[Controles de consistência]] |
| o filtro **descarta** folha legítima ou **aceita** o que não é | licitação perdida ou extração desperdiçada | regra com motivo e versão; Jev como segundo sinal; rótulo humano prevalece | [[Regras antes de IA]] |
| a fonte **cai** | coleta silenciosamente vazia | rodada marcada cega; espera crescente; disjuntor | [[Disponibilidade do PNCP]] |
| **gasto** descontrolado | fatura inesperada | teto diário com reserva por extração; preço desconhecido nunca é zero; gasto conferido na fatura | [[Custo por edital]] |
| anexo com **lista nominal** de servidores | tratamento indevido de dado pessoal | perguntas agregadas; nenhuma extração de nomes; documento em bucket privado no Brasil | [[Privacidade e LGPD]] |
| **acesso indevido** ao sistema | ação paga ou mudança de dados por quem não deveria | papéis por rota; ações só do admin; gestão de acesso só do supremo | [[Controle de acesso e segredos]] |
| **vazamento de segredo** | uso indevido das APIs pagas | chave do modelo só no n8n; nenhum segredo em imagem ou repositório; guardas automáticas | [[Segurança do servidor]] |
| **perda de dados** | decisões humanas e extrações perdidas | backup diário, cópia fora da máquina que não pode ser apagada, restauração provada semanalmente | [[Backup e restauração]] |
| **sobrecarga** do portal público | risco reputacional | identificação, esperas, coleta mínima, nada contornado | [[Legalidade da automação]] |
| decisão humana **apaga o rastro** da máquina | auditoria impossível | revisões e rótulos em camadas próprias; tabelas da máquina só com inserção | [[Modelo de dados]] |

## Viés e cobertura

- **Cobertura geográfica:** municípios pequenos podem publicar só em diário oficial até 01/04/2027; a cobertura é **declarada por rodada**, nunca presumida — a ferramenta não promete ver todas as licitações do país ([[ADR-007 Cobertura de municípios pequenos]]).
- **Viés de modelo:** os números de qualidade vêm de dois gabaritos e são citados com a variância medida; o ordenamento de modelos mudou com o perfil do edital, e isso está dito ([[Variância e como citar números]]).
- **Rótulos que validam o próprio filtro:** os rótulos humanos de escopo nasceram em parte das discordâncias do Jev — servem de validação, mas enviesada a favor do critério que os gerou; isso está registrado.

## O que depende do banco

Relatório de impacto à proteção de dados, parecer do encarregado, política de retenção, política interna de uso de IA com documentos externos e o processo de revisão humana na área de negócio ([[Próximos passos]]).

## Relacionadas

[[MOC Segurança e Ética]] · [[Privacidade e LGPD]] · [[Injeção de prompt e defesas]] · [[Controle de acesso e segredos]] · [[Legalidade da automação]] · [[Controles de consistência]] · [[Consciência operacional]]
