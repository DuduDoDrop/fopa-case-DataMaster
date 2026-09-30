---
tipo: avaliacao
familia: avaliacao
status: verificado
atualizado: 2026-09-28
testado_em: 2026-09-28
fonte_codigo:
  - scripts/35_antes_depois.py
  - scripts/15_acuracia.py
  - scripts/fopa/extrator.py
  - scripts/fopa/melhor_de_n.py
tags: [avaliacao, v3-1, cache, best-of-n, custo]
---

# Antes e depois da v3.1

> [!abstract] Em uma frase
> A v3.1 (em produção desde 28/09/2026) mudou duas coisas no extrator — **documentos antes das perguntas** e **Best-of-N só no que falha** — e a remedição nos dois gabaritos, no Claude e no GPT, mostrou: **−32,5% de custo no Claude em contexto completo com a mesma acurácia**, +7,2% no RAG, o GPT mais caro enquanto o cache da OpenAI não for lido, e **uma resposta crítica recuperada sem nenhuma piorada**.

## Papel na solução

É a medição que autorizou a v3.1 a ir para produção e a que diz, com número, o que ela ganhou e o que ela custa. As duas mudanças estão descritas em [[Cache de prompt e ordem do prompt]] e [[Best-of-N]]; a decisão, em [[ADR-024 Best-of-N e documentos antes das perguntas]].

## Como foi medido

- **Editais:** Pirapó/RS (contexto completo) e Bertioga/SP (RAG) — as duas licitações com gabarito ([[Gabaritos]]).
- **Modelos:** Claude Opus 5.5 e GPT-5.6 Sol, esforço `high`.
- **Antes** = a v3.0: perguntas antes dos documentos, uma tentativa (a ordem antiga continua no código, byte a byte, para medir o "antes" com o mesmo código). **Depois** = a v3.1.
- **Ferramenta:** `scripts/35_antes_depois.py`, que primeiro rodou em **modo seco** (monta os prompts reais, conta tokens, simula o cache chamada a chamada, aplica os preços — nenhuma chamada de modelo) e estimou **R$ 24,22**; a medição real gastou **R$ 23,79**, com um teto que pararia antes de estourar.
- **n = 1 por linha.** Custo e tempo repetem em cerca de 1%; acurácia, ±1 resposta em 17 ([[Variância e como citar números]]).

## Resultado

| Edital | Modelo | R$ antes | R$ depois | Δ custo | Acurácia | Críticas |
|---|---|---|---|---|---|---|
| Pirapó (contexto completo) | Claude Opus 5.5 | 3,71 | **2,50** | **−32,5%** | 16/17 → 16/17 | 7/7 → 7/7 |
| Pirapó (contexto completo) | GPT-5.6 Sol | 3,31 | 4,03 | +21,6% | 17/17 → 16/17 | 7/7 → 6/7 |
| Bertioga (RAG) | Claude Opus 5.5 | 2,35 | 2,52 | +7,2% | 16/17 → 16/17 | 6/7 → 6/7 |
| Bertioga (RAG) | GPT-5.6 Sol | 2,75 | 2,63 | −4,6% | 14/17 → 15/17 | 4/7 → 5/7 |

### No Claude, o documento passou a ser lido do cache

| Pirapó · Claude | Chamadas | Entrada nova | Cache gravado | Cache lido | Custo |
|---|---|---|---|---|---|
| antes | 3 | 135.984 | 1.542 | 3.084 | R$ 3,71 |
| depois | 5 | 2.221 | 44.743 | 186.682 | R$ 2,50 |

O documento é gravado uma vez e lido nas outras quatro chamadas — inclusive nas duas do reforço, que saem quase de graça. A estimativa de ~28% de economia se confirmou com folga. No RAG não há prefixo comum para ler, e o reforço é custo puro (+7,2%).

### Na OpenAI, o cache quase nunca é lido

| GPT-5.6 Sol | Chamadas | Entrada nova | Cache gravado | Cache lido |
|---|---|---|---|---|
| Pirapó antes | 3 | 9 | 81.484 | 0 |
| Pirapó depois | 5 | 15 | 108.497 | 27.016 |
| Bertioga antes | 3 | 9 | 40.848 | 0 |
| Bertioga depois | 5 | 15 | 51.597 | 0 |

A OpenAI registra quase toda a entrada como gravação de cache (mais cara que entrada nova) e leu uma única vez em 16 chamadas. A ordem não basta; a próxima hipótese é o `prompt_cache_key`, não medida ([[Próximos passos]]).

### O que o reforço fez, pergunta a pergunta

| Onde | Pergunta | Gabarito | Tentativas | O que ficou |
|---|---|---|---|---|
| Pirapó · Claude e GPT | Q15, Q16 | ausência real | 3 | a ausência, confirmada — **certa** |
| Pirapó · GPT | Q17 | exige "garantia" | 3 | "não localizado" nas 3 — errada, como veio |
| Bertioga · Claude e GPT | Q17 | exige "garantia" | 3 | "não localizado" nas 3 — errada em todas as execuções |
| Bertioga · GPT | **Q1** (crítica) | 21/09/2026, sessão suspensa | 2 | **recuperada na 2ª**: "21/09/2026 às 10h00 (abertura suspensa)", ancorada — **certa** |

Oito respostas reforçadas, todas "não localizado": **4 ausências reais confirmadas**, **3 erros sistemáticos** (a mesma resposta nas três tentativas; a Q17 pede a nuance "não exige garantia, mas as penalidades a pressupõem", que reamostrar não produz) e **1 crítica recuperada**. Nenhuma piorou — por construção, a original só é trocada por candidato de pontuação maior.

## Como ler

- **Claude em contexto completo:** a mesma acurácia por dois terços do preço.
- **RAG:** a ordem não mexe no custo; o reforço soma cerca de 7% no Claude.
- **GPT:** mais caro enquanto o cache da OpenAI não for lido; a acurácia oscilou ±1 nos dois sentidos, dentro da variância conhecida.
- **Versões:** a `versao_prompt` mudou (as execuções de antes e depois se distinguem no banco); a `versao_regras` não mudou — a v3.1 não exigiu reverificar o acervo.

## Duas conferências feitas junto

- **O gabarito reprovou acerto de novo, e era formato.** A Q13 de Bertioga terminava em "…; Total 1.896." e o comparador recusava pontuação depois de número. A resposta estava certa. Corrigido com teste; as oito execuções foram reavaliadas a partir das auditorias, **sem chamar modelo** — as tabelas acima já são as reavaliadas (duas mudaram: Bertioga/Claude/depois de 15 para 16 e Bertioga/GPT/depois de 14 para 15).
- **O ensaio de ponta a ponta na infraestrutura** (provedor simulado, W20 → W23 → `/reforco` → W24): 3 lotes mais 2 rodadas de reforço só com as 8 perguntas que falharam — 7 chamadas, com rodadas 0, 0, 0, 1, 1, 2, 2 — e o registro do Best-of-N gravado na verificação. Com o simulado, determinístico, fica sempre a original, como tem de ser.

## Relacionadas

[[MOC Avaliação]] · [[Cache de prompt e ordem do prompt]] · [[Best-of-N]] · [[Resultados medidos]] · [[Custo por edital]] · [[W23 Extrair]] · [[W24 Verificar e publicar]] · [[ADR-024 Best-of-N e documentos antes das perguntas]] · [[Linha do tempo da construção]]
