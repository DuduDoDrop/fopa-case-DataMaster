---
tipo: tecnica
familia: ia
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - api/modelos_ia.py
  - scripts/fopa/modelos.py
  - api/extracao.py
  - n8n/workflows/W23.json
  - db/016_configuracao_e_papel_do_site.sql
  - db/033_pedido_extracao_ia.sql
  - db/037_pedido_modelo_esforco.sql
tags: [ia, modelos, provedores, custo, redundancia]
---

# Modelos e provedores

> [!abstract] Em uma frase
> O extrator pode rodar em dois fornecedores de modelo — **Claude (Anthropic)**, o padrão, e **OpenAI (GPT)**, o plano B — atrás do mesmo contrato de entrada e saída; o modelo configurado em produção é o **Claude Opus 5.5 com esforço médio**, e um administrador pode pedir, para uma licitação específica, qualquer modelo do catálogo pelo botão "Extrair com IA".

## Papel na solução

Escolher o modelo é a decisão de IA com mais impacto em qualidade, e a medição mostrou que ela se decide por **profundidade de leitura**, não por citar certo — todos os modelos testados citam com fidelidade parecida, mas diferem em quanto encontram ([[Comparação de modelos]]). Ter dois fornecedores é redundância operacional: licitação tem data de sessão, e ela não se move porque uma API caiu. A troca de fornecedor é barata por um motivo de arquitetura: o [[Verificador determinístico]] **não usa modelo** e não sabe quem escreveu a resposta — trocar quem responde não muda o que garante a resposta.

## O catálogo

É a lista que o botão "Extrair com IA" oferece (`api/modelos_ia.py`), com o esforço fixo de cada modelo, o preço de tabela e a estimativa que a tela mostra.

| Provedor | Modelo | Esforço (fixo) | US$ por milhão — entrada / saída | Estimativa por edital¹ | Nota do catálogo |
|---|---|---|---|---|---|
| Claude | **Claude Opus 5.5** (`claude-opus-5-5`) | medium | 4,00 / 20,00 | US$ 0,65 (máx. 1,43) | o extrator do projeto; mais barato que o Opus 5 |
| Claude | Claude Sonnet 5 (`claude-sonnet-5`) | medium | 2,00 / 10,00 | US$ 0,33 (máx. 0,72) | equilíbrio entre qualidade e custo |
| Claude | Claude Haiku 4.5 (`claude-haiku-4-5`) | sem esforço | 1,00 / 5,00 | US$ 0,18 (máx. 0,36) | o mais barato; sem controle de esforço; contexto de 200 mil tokens |
| OpenAI | **GPT-5.6 Sol** (`gpt-5.6-sol`) | medium | 4,00 / 20,00 | US$ 0,65 (máx. 1,43) | o modelo OpenAI configurado como plano B |
| OpenAI | GPT-6 Sol (`gpt-6-sol`) | medium | 2,00 / 10,00 | US$ 0,33 (máx. 0,72) | raciocínio forte, metade do preço do 5.6 Sol |
| OpenAI | GPT-6 Astra (`gpt-6-astra`) | medium | 10,00 / 50,00 | US$ 1,63 (máx. 3,59) | o mais capaz da OpenAI; o mais caro |
| OpenAI | GPT-6 Luna (`gpt-6-luna`) | medium | 0,10 / 0,50 | US$ 0,02 (máx. 0,04) | o mais barato e rápido |

¹ A estimativa parte de um edital real de referência (Poá/SP: 118.648 tokens de entrada e 11.726 de saída em esforço alto, 3 chamadas), ajusta a saída pelo esforço e não conta o desconto do cache; o "máx." supõe as 3 chamadas no teto de saída. É uma ordem de grandeza para decidir antes de clicar — **a medida é a fatura**.

- **Só entra no catálogo modelo com preço** na tabela de preços do código. Sem preço, o custo sairia "preço não configurado" e o teto do dia não protegeria nada. Os preços do Claude são os da tabela oficial; os da OpenAI foram conferidos por duas fontes — a tabela e a fatura (custo dividido pelo uso), que bateram dentro de 0,01%.
- **Preço desconhecido é nulo, nunca zero.** Um custo R$ 0,00 só é gravado quando é de fato zero (os provedores de ensaio). Uma execução sem preço conhecido aparece como "n/d" no site e no e-mail ([[Custo por edital]]).
- **Câmbio:** o custo em reais usa `FOPA_USD_BRL` (5,10 por padrão), gravado junto de cada execução.

## Configuração em produção

Lida no [[Página Admin|Admin]] em 28/09/2026:

| Chave | Valor | Efeito |
|---|---|---|
| `provedor` | `simulado` | o processamento automático da fila (W10 → W20) lê e prepara as licitações novas, mas **não gasta**: sem provedor real, a licitação real para em `preparada` |
| `modelo` | `claude-opus-5-5` | o modelo Claude usado quando o provedor é `claude` |
| `modelo_openai` | `gpt-5.6-sol` | o modelo usado quando o provedor é `openai` |
| `effort` | `medium` | o esforço padrão |
| `max_tokens` | 16000 | o teto de saída por chamada |

Com essa configuração, a **extração paga acontece por pedido explícito**: o botão "Extrair com IA" do detalhe grava um pedido com provedor e modelo (`pedidos_extracao`), que vale **só para aquela licitação e aquela execução**, e aciona na hora o processamento só dela ([[W11 Ações do site]], [[W23 Extrair]]). Foi assim que Itapecuru Mirim/MA foi extraída em 28/09/2026, com o Claude Haiku 4.5, por R$ 0,78.

## Os provedores

| Provedor | Onde chama | Custo | Pode virar o resultado oficial de uma licitação real? |
|---|---|---|---|
| `claude` | Anthropic, `POST /v1/messages` | sim | sim |
| `openai` | OpenAI, `POST /v1/responses` | sim | sim |
| `simulado` | worker, `POST /responder-simulado` (expressões regulares sobre o texto) | não | **não** — só em licitação de ensaio |
| `gravado` | worker, `POST /gravado/v1/messages` (repete respostas reais já gravadas) | não | **não** |

A trava que impede resultado de ensaio de virar oficial está no banco: uma execução `simulado` ou `gravado` nunca é canônica, e um gatilho recusa torná-la vigente numa licitação real ([[Controles de consistência]]).

### O que muda entre Claude e OpenAI

Tudo fica isolado na montagem do corpo; o resto do pipeline recebe o mesmo JSON.

| Item | Claude | OpenAI |
|---|---|---|
| Endpoint | Messages API | **Responses API** (os modelos de raciocínio da família GPT vivem nela) |
| Teto de saída | `max_tokens` | `max_output_tokens` (`max_tokens` devolve erro 400) |
| Raciocínio | `thinking: adaptive` + `output_config.effort` | `reasoning.effort` |
| Saída estruturada | `output_config.format` (`json_schema`) | `text.format` (`json_schema`, `strict: true`) |
| Cache de prompt | explícito, `cache_control` em até dois pontos | automático por prefixo ([[Cache de prompt e ordem do prompt]]) |
| Contagem de entrada | cache gravado e lido vêm separados | `input_tokens` já inclui o cache; o sistema desconta para as colunas ficarem comparáveis |
| Resposta truncada | `stop_reason` diferente de `end_turn` | `status: incomplete` |

A chave de cada provedor fica **só** na credencial do n8n; o worker não tem nenhuma ([[Controle de acesso e segredos]]). Nas chamadas, o W23 repete até 3 vezes em erro de rede ou HTTP 408, 429, 500, 502, 503 e 529, respeitando o `retry-after` do provedor; recusa e truncamento viram erro sem nova tentativa ([[W23 Extrair]]).

## Por que o Claude é o padrão

Medido contra os dois gabaritos humanos (Pirapó/RS, contexto completo; Bertioga/SP, RAG), esforço `high`:

| Modelo | Pirapó | Bertioga | Completude em Bertioga |
|---|---|---|---|
| Claude Opus 5.5 | 16/17 | **17/17** | **38/49** |
| Claude Opus 5 | **17/17** | **17/17** | 37/49 |
| GPT-5.6 Sol | 16/17 | 15/17 | 25/49 |
| GPT-6 Sol | **17/17** | 14/17 | 26/49 |
| GPT-6 Luna | 16/17 | 11/17 ¹ | 25/49 |

¹ Recontado em 28/09/2026 com o avaliador corrigido (era 10/17); os outros modelos da tabela não foram recontados.

- **A ancoragem empata** — 100% em todos os modelos medidos em Pirapó: todos citam com honestidade.
- **A profundidade separa:** os dois Claude ficam em 17/17 no edital difícil (9 documentos que se contradizem, uma suspensão, pirâmide em anexo); os GPT caem. E a completude — trazer a ressalva, a divergência, o contexto em volta do número — fica em 33 a 38 no Claude contra 17 a 26 no GPT.
- **O Opus 5.5 substituiu o Opus 5** em 26/09/2026 ([[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]]): mais novo, mais barato (US$ 4/20 contra 5/25 por milhão; ≈ US$ 0,65 contra 0,89 por edital na mesma conta de tokens), empatado em acurácia no edital difícil, com mais completude, e o mais rápido dos medidos (cerca de 70 s contra 100 s).
- **O Haiku 4.5 fica fora da extração padrão:** nas medições de 22/09 errou 2 de 17 e 1 das 7 críticas em Pirapó, respondendo "não localizado" para uma informação que estava no termo de referência — desistência, não leitura errada. E o contexto de 200 mil tokens é um teto real para editais grandes depois do OCR. Continua no catálogo como opção barata para quem quiser pedir.
- **O GPT-5.6 Sol é o plano B:** ancoragem de 100% nos dois gabaritos, acurácia de 16/17 e 15/17 — serve para não parar quando o fornecedor principal cai, não como substituto do extrator.
- **Em produção, um modelo barato com Best-of-N:** pelo botão, o GPT-6 Luna extraiu Itapecuru Mirim/MA por R$ 0,20, com 16 de 16 respostas ancoradas depois do reforço — ancoragem, não acurácia: no edital difícil com gabarito, Bertioga/SP, o Luna acertou 14 e 13 de 17 pelo botão em `medium` e 13 de 17 em `high`, contra 16 de 17 do Claude Opus 5.5 — o esforço maior não mudou a acurácia e foi desfeito no mesmo dia ([[Best-of-N]], [[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]]).

Todos esses números são n = 1 por configuração; a ordem de grandeza e a direção é o que se afirma ([[Variância e como citar números]]).

## Outras origens de resposta

Além das execuções por API, o banco registra de onde veio cada conjunto de respostas (`execucoes_modelo.origem`), e todas passam pelo mesmo verificador:

| Origem | O que é |
|---|---|
| `api` | extração por Claude ou OpenAI, feita pelo W23 |
| `agente` | respostas produzidas por um agente de IA sobre a mesma leitura congelada, fora da API, e importadas pelo site ("Importar respostas do agente"); **sem preço de API** — nunca aparecem como R$ 0,00 ([[ADR-014 Extração por agente, sem API]]) |
| `simulado`, `gravado` | ensaio e demonstração, nunca canônicas |
| `legado` | execuções importadas do acervo da versão anterior ([[Acervo e migração da v2]]) |

## Relacionadas

[[MOC IA]] · [[Prompt do extrator]] · [[Chain-of-thought e esforço de raciocínio]] · [[Custo por edital]] · [[Comparação de modelos]] · [[Jev — score de escopo e sustentação]] · [[W23 Extrair]] · [[Página Detalhe da licitação]] · [[Página Admin]] · [[ADR-009 Modelo de extração]] · [[ADR-012 Segundo provedor de modelo]] · [[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]]
