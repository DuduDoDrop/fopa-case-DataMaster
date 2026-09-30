---
tipo: tecnica
familia: ia
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/questionario.py
  - scripts/fopa/extrator.py
  - scripts/fopa/recuperacao.py
  - scripts/fopa/modelos.py
  - api/extracao.py
  - api/rotas_extracao.py
  - api/versao.py
  - api/modelos_ia.py
tags: [ia, prompt, extracao, structured-output, nucleo]
---

# Prompt do extrator

> [!abstract] Em uma frase
> O que o modelo recebe em cada chamada: uma **instrução de sistema fixa com nove regras absolutas**, uma mensagem com **os documentos primeiro** — cada página marcada com arquivo e número físico — e **as 6 perguntas do lote no fim**, e um **esquema JSON fechado** para a resposta; o worker monta, o n8n envia.

## Papel na solução

O prompt é a única peça generativa do pipeline, e por isso é a mais controlada: curto, imperativo, sem pedir "seja cuidadoso". Cada regra é uma proibição verificável que nasceu de uma falha observada em documento real, e a maioria tem um teste correspondente no [[Verificador determinístico]]. O resultado não é aceito porque o modelo é confiável — é aceito se a citação **confere** na página.

## Quem monta e quem envia

| Etapa | Quem | O quê |
|---|---|---|
| Montar | worker, `POST /prompt` | lê a leitura congelada no banco, escolhe o modo (contexto completo ou RAG), divide as 17 perguntas em lotes e devolve, para cada lote, o corpo exato da Anthropic (`body`), o da OpenAI (`body_openai`) e o SHA-256 do corpo (`request_sha256`) |
| Enviar | n8n, [[W23 Extrair]] | um *HTTP Request* por lote, com a credencial do provedor guardada no n8n |
| Registrar | n8n + worker `POST /custo` | cada chamada vira uma linha de `chamadas_modelo` com tokens, custo, `stop_reason` e o `request_sha256` |

O worker **nunca** tem a chave do modelo: em produção, o `/health` informa `anthropic_key_presente: false`, e um teste de guarda do CI (`ci/tests/test_guardas_texto.py`) garante que o endereço da Anthropic só aparece no ramo `claude` do W23 — nunca no worker nem no site. O mesmo código de montagem produziu as medições do projeto: o que está em produção é o que foi medido ([[Harness de avaliação]]).

## A estrutura de uma chamada

```text
system ─ instrução fixa com as 9 regras .......................... cache_control (1º ponto de cache)

user ─── LICITAÇÃO: <município/UF — modalidade>
         === DOCUMENTOS ===
         === ARQUIVO <nome do arquivo> | PÁGINA 1 ===
         <texto da página>
         === ARQUIVO <nome do arquivo> | PÁGINA 2 ===
         <texto da página>
         …
         === FIM DOS DOCUMENTOS ===  ............................. cache_control (2º ponto, só em contexto completo)

         Responda as perguntas abaixo usando EXCLUSIVAMENTE os documentos acima.
         Q1. Qual a Data da Licitação ?
            O que responder: Data e hora da sessão pública. Se houver aviso de retificação…
            Formato: DD/MM/AAAA às HHhMM (horário de Brasília)
         … (as 6 perguntas do lote)
         Devolva uma resposta para CADA pergunta listada, na ordem, com trecho literal,
         arquivo e página física conforme os marcadores "=== ARQUIVO x | PÁGINA n ===".
```

- **Documentos antes das perguntas (desde a v3.1):** o cache dos provedores casa por prefixo; com os documentos na frente, o prefixo é o mesmo nos três lotes e o edital é gravado no cache uma vez e lido nas outras chamadas ([[Cache de prompt e ordem do prompt]]).
- **Ordem dos arquivos:** por precedência documental — retificação, suspensão, comunicado, redesignação, errata, resposta a esclarecimento, termo de referência, edital — e, dentro de cada grupo, pelo nome. O modelo lê primeiro o que tem mais chance de valer.
- **Marcador de página:** `=== ARQUIVO x | PÁGINA n ===` dá a página **física** (a que o leitor de PDF mostra), que é a unidade de citação. A numeração impressa no rodapé não é usada ([[ADR-005 Info é arquivo mais página física]]).
- **Tarja de assinatura removida:** linhas como "Assinado por N pessoas", "Para verificar a autenticidade" e "Código para verificação" saem do texto antes de ele virar contexto — elas se entrelaçam com as tabelas.
- **Modo de contexto:** até 180.000 caracteres, todas as páginas vão em cada lote; acima disso, só as páginas recuperadas pelo BM25 para as perguntas do lote ([[RAG com BM25]]).

## As nove regras absolutas

A instrução de sistema é um texto fixo de `questionario.instrucao_sistema()`. Ela entra antes do documento e nunca muda entre licitações — é isso que a torna cacheável.

| # | Regra (resumo fiel do texto) | Por que existe |
|---|---|---|
| 1 | Só afirme o que está escrito nos documentos; nunca infira, nunca calcule, nunca complete com conhecimento geral sobre licitações | o modelo conhece o "edital típico" e tende a completar com ele |
| 2 | Toda resposta traz `trecho_literal` copiado **exatamente**, mais `arquivo` e `pagina`; o trecho será conferido caractere a caractere, e paráfrase é rejeitada | é a base da ancoragem ([[ADR-004 Evidência obrigatória]]) |
| 3 | Não encontrou? `"Não localizado"`, com arquivo, página e trecho nulos — resposta **correta** e preferível a uma tentativa | um chute plausível é o erro que ninguém percebe; em Bertioga/SP, o "não localizado" da Q17 evitou repetir um percentual de garantia que só aparecia no pedido de um licitante |
| 4 | A `pagina` é a página **física** do marcador, não a numeração impressa | a numeração impressa diverge da física, e "p. 30" sozinho é ambíguo |
| 5 | Documentos podem se contradizer; precedência: aviso de retificação ou suspensão mais recente > termo de referência corrigido > edital de maior sequencial > editais anteriores; ao usar o mais recente, descreva a divergência em `conflito` | Bertioga/SP: a sessão do edital (21/09) foi suspensa por comunicado de 18/09 ([[ADR-006 Documento vigente é o de maior sequencial]]) |
| 6 | Transcreva rótulos como estão: "valor mínimo", "valor estimado" e "valor de referência" são conceitos diferentes em leilão de maior oferta | Bertioga/SP usa três rótulos para o mesmo montante; São Lourenço do Sul/RS tem editais que dizem "estimado" e um que diz "mínimo" |
| 7 | A pirâmide salarial vem em **várias tabelas**, separadas por vínculo; capture todas; se a soma de uma tabela não bater com o total impresso dela, relate em `conflito` em vez de ajustar | São Lourenço do Sul/RS: contratos 287 + inativos e pensionistas 593 + ativos 902 = 1.782; parar na primeira tabela erra por até 84% |
| 8 | Ignore as linhas de assinatura digital | a tarja entra no meio das tabelas no texto extraído |
| 9 | Nunca calcule percentuais, totais ou valores derivados; transcreva o percentual e a base de cálculo declarada | garantia de contrato plurianual incide sobre o valor anual; aplicar o percentual ao total erra por múltiplos |

## Os lotes

As 17 perguntas vão em **lotes de 6** (`configuracao.lote = 6`): Q1–Q6, Q7–Q12 e Q13–Q17 — **3 chamadas por extração**, feitas **em série** pelo W23.

| Estratégia | Custo | Qualidade |
|---|---|---|
| 1 pergunta por chamada | reenvia o documento 17 vezes | máxima atenção por pergunta |
| **6 por chamada** (em uso) | 3 chamadas; com o cache, o documento é pago cheio uma vez | perguntas relacionadas vistas juntas — a Q13 (pirâmide) e a Q14 (total) caem no mesmo lote e são lidas em conjunto |
| 17 de uma vez | 1 chamada | risco de resposta rasa nas últimas perguntas e de saída truncada |

O tamanho do lote é parâmetro do [[Página Admin|Admin]] justamente para poder ser medido; o valor 6 é o meio-termo adotado e não foi varrido ([[Próximos passos]]).

## O corpo enviado a cada provedor

O worker monta os dois corpos a partir das mesmas partes; o W23 usa o do provedor vigente.

| Item | Claude (`POST /v1/messages`) | OpenAI (`POST /v1/responses`) |
|---|---|---|
| Modelo | `model` | `model` |
| Instrução de sistema | `system`, em bloco com `cache_control` | `instructions` |
| Mensagem | `messages[0].content` em **dois blocos**: documentos (com `cache_control`) e perguntas | `input`, texto único começando pelos documentos (o cache da OpenAI é automático por prefixo) |
| Teto de saída | `max_tokens` | `max_output_tokens` |
| Raciocínio | `thinking: {type: adaptive}` e `output_config.effort` | `reasoning.effort` |
| Saída estruturada | `output_config.format` = `json_schema` | `text.format` = `json_schema` com `strict: true` |

- **Teto de saída por chamada:** 16.000 tokens no esforço padrão; 32.000 em `xhigh` e 64.000 em `max` (níveis que o catálogo atual não usa — o esforço é fixo em `medium`).
- **Claude Haiku 4.5** é de geração anterior: não aceita raciocínio adaptativo nem esforço, e o corpo vai só com a saída estruturada ([[Modelos e provedores]]).
- **No RAG**, a mensagem vai como texto único e sem o 2º ponto de cache, porque cada lote leva páginas diferentes.

## O que torna a saída controlada

1. **Esquema fechado.** `additionalProperties: false` e todos os campos obrigatórios. Não há texto livre para interpretar, nem campo onde uma instrução injetada vire ação ([[Injeção de prompt e defesas]]).
2. **Preenchimento garantido.** Se o modelo omitir uma pergunta do lote, o sistema grava "Não localizado" com confiança baixa. Ausência nunca vira silêncio. (No reforço do [[Best-of-N]] é o contrário: a pergunta que não voltou é pulada, porque silêncio não é resposta.)
3. **Ordem independente.** As respostas são reordenadas por número de pergunta; a divisão em lotes não aparece no resultado.
4. **Confiança só rebaixa.** `confianca: baixa` leva o veredito a REVISAR; `alta` não dispensa a ancoragem.
5. **Conflito é dado.** O modelo responde pelo documento de maior precedência **e** descreve a divergência; o verificador rebaixa a resposta com conflito para REVISAR.
6. **Resposta interrompida não vale.** Uma chamada que termina por limite de saída (`stop_reason` diferente de `end_turn`, ou `status: incomplete` na OpenAI) é tratada como falha — nunca como JSON pela metade.

## Versão do prompt

A `versao_prompt` é o SHA-256 do que o modelo **vê**: a instrução de sistema, o esquema, o molde da mensagem montado com marcadores no lugar do documento e as 17 perguntas serializadas (com termos e marca de crítica). É calculada pelo comportamento, não pelo arquivo: refatorar sem mudar o prompt não muda a versão. Toda execução grava a versão vigente — na licitação de Itapecuru Mirim/MA extraída em 28/09/2026, `f224a746b51a`, a mesma que o [[Página Saúde|/saude]] mostra para o worker em produção.

## Os provedores de ensaio

Dois provedores sem custo usam exatamente o mesmo prompt, para testar o encanamento:

- **`simulado`:** o worker procura, por expressões regulares, a página que contém ao menos dois termos de cada pergunta e devolve um trecho dela no mesmo formato de resposta. Não é um modelo: é o **piso** de comparação. Em Bertioga/SP, o regex teve 0 de 13 respostas ancoradas contra 17 de 17 do modelo — a medida de que o modelo agrega valor.
- **`gravado`:** repete, lote a lote, as respostas reais já gravadas daquela licitação; serve para demonstrar o fluxo inteiro sem rede e a custo zero.

Nenhum dos dois pode virar o resultado oficial de uma licitação real (trava no banco, [[Controles de consistência]]).

## Relacionadas

[[MOC IA]] · [[Questionário — as 17 perguntas]] · [[RAG com BM25]] · [[Cache de prompt e ordem do prompt]] · [[Chain-of-thought e esforço de raciocínio]] · [[Modelos e provedores]] · [[Best-of-N]] · [[Verificador determinístico]] · [[W23 Extrair]] · [[Endpoints do worker]] · [[ADR-004 Evidência obrigatória]]
