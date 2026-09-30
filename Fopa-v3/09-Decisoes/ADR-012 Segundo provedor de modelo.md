---
tipo: decisao
familia: decisoes
adr: 12
data: 2026-09-23
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, modelo, redundancia, custo]
---

# ADR-012 — Segundo provedor de modelo

> [!abstract] Em uma frase
> O extrator fala com **dois fornecedores** — Claude, o principal, e OpenAI, o plano B — atrás do mesmo contrato de entrada e saída; a troca é barata porque o verificador **não usa modelo**, e o custo desconhecido é gravado como **nulo, nunca como zero**.

## Problema

A solução responde a **prazo de licitação**: a data da sessão está no edital e não se move porque um fornecedor de API caiu. Isso não é hipótese — a API de documentos do PNCP ficou fora do ar por dias durante a construção. Com um provedor só, uma indisponibilidade é **parada**; com dois, é degradação.

## Opções

| Opção | Avaliação |
|---|---|
| um fornecedor só | indisponibilidade vira parada |
| **dois fornecedores atrás do mesmo contrato** | a troca não afeta o que garante a resposta |
| validar a resposta com modelo | trocar o extrator obrigaria a revalidar o validador — por isso a verificação é determinística |

## O que muda entre os dois, isolado na montagem do corpo

| | Claude | OpenAI |
|---|---|---|
| endpoint | Messages | **Responses** |
| teto de saída | `max_tokens` | `max_output_tokens` |
| raciocínio | `thinking: adaptive` + `effort` | `reasoning.effort` |
| saída estruturada | `output_config.format` | `text.format` (`strict`) |
| cache | explícito | automático por prefixo |
| contagem de entrada | cache à parte | `input_tokens` já inclui o cache — descontado para comparar |
| resposta truncada | `stop_reason` | `status: incomplete` — detectado, nunca lido como JSON pela metade |

## O que foi medido

- **GPT-5.6 Sol contra os dois gabaritos (23/09/2026):** ancoragem **100%** nos dois; acurácia 16/17 e 15/17 contra 17/17 do Opus 5. A ancoragem não separa fornecedores; a profundidade separa ([[Comparação de modelos]]).
- **Preço conferido na fatura:** dividindo o cobrado pelos tokens de cada linha, US$ 4 de entrada, US$ 5 de gravação de cache, US$ 0,40 de leitura e US$ 20 de saída por milhão — bate com a tabela dentro de 0,01%.
- **O identificador do modelo saiu da conta**, não de memória: o palpite óbvio não existia; a conta tinha `gpt-5.6-sol`, `-luna` e `-terra`.
- **Limite de taxa lido no cabeçalho da resposta**, não na mensagem de erro: a conta passou de 3 para 500 requisições por minuto no mesmo dia — os tempos medidos antes disso eram espera, não inferência.
- **O defeito de cache na OpenAI** continua aberto: ela quase nunca lê o cache, mesmo com a ordem nova do prompt ([[Cache de prompt e ordem do prompt]]).

## Escolha

- Claude é o principal; OpenAI é o plano B, selecionável na configuração ou no botão "Extrair com IA" ([[Modelos e provedores]]).
- **Preço sem fonte não entra:** só entra no catálogo modelo com preço conferido; sem preço, o custo sai "n/d" — um R$ 0,00 falso contaminaria planilha, benchmark e teto de gasto.
- Uma execução no provedor secundário é marcada como condição **degradada** ([[Consciência operacional]]).

## O que custa

- Uma dependência a mais e a manutenção de dois formatos de chamada.
- Enquanto o cache da OpenAI não for lido, o GPT custa mais na v3.1 (+21,6% em Pirapó).

## Onde vive em produção

O W23 escolhe o nó pelo provedor (Anthropic ou OpenAI); as chaves ficam em credenciais do n8n; o worker monta os dois corpos em cada `POST /prompt` ([[W23 Extrair]]).

## O que reabriria a decisão

O fornecedor secundário passar a ter acurácia equivalente no edital difícil — ou deixar de ter preço conferido.

## Relacionadas

[[MOC Decisões]] · [[Modelos e provedores]] · [[Comparação de modelos]] · [[ADR-004 Evidência obrigatória]] · [[ADR-009 Modelo de extração]] · [[Disponibilidade do PNCP]]
