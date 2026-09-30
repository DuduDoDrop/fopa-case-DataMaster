---
tipo: avaliacao
familia: avaliacao
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/11_avaliar.py
  - scripts/15_acuracia.py
  - scripts/17_benchmark.py
  - scripts/34_placar.py
  - scripts/fopa/modelos.py
tags: [avaliacao, modelos, comparacao, custo]
---

# Comparação de modelos

> [!abstract] Em uma frase
> Seis modelos de dois fornecedores foram medidos contra os mesmos gabaritos: **todos citam com fidelidade** (ancoragem de 92% a 100%), mas diferem em **quanto encontram** — conflitos entre documentos e completude caem pela metade dos modelos mais fortes para os mais baratos, e o ordenamento muda com o perfil do edital; os Claude Opus foram os únicos em 17/17 no edital difícil.

## Papel na solução

É a base medida da escolha do extrator ([[Modelos e provedores]], [[ADR-009 Modelo de extração]], [[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]]). O princípio: **não se troca o padrão do projeto por reputação** — benchmark genérico não é a tarefa; por isso o projeto tem gabarito próprio.

## Claude: três modelos, dois editais (22/09/2026, esforço `high`)

### Pirapó/RS — 3 arquivos, 38 páginas, contexto completo

| Modelo | Acurácia | Críticas | Completude | Ancoragem | Conflitos | Custo | Tempo |
|---|---|---|---|---|---|---|---|
| Opus 5 | **17/17** | **7/7** | **38/41** | 14/14 | **5** | R$ 4,79 | 99 s |
| Sonnet 5 | **17/17** | **7/7** | 26/41 | 14/15 | 2 | R$ 2,12 | 122 s |
| Haiku 4.5 | 15/17 | 6/7 | 19/41 | 12/13 | 0 | R$ 0,64 | 31 s |

### Bertioga/SP — 9 arquivos, 115 páginas, RAG

| Modelo | Acurácia | Críticas | Ancoragem | Conflitos | Custo | Tempo |
|---|---|---|---|---|---|---|
| Opus 5 | **17/17** | **7/7** | **17/17** | 5 | R$ 2,91 | 100 s |
| Sonnet 5 | 16/17 | 6/7 | 15/16 | 5 | R$ 1,19 | 94 s |
| Haiku 4.5 | 16/17 | 7/7 | 15/16 | 4 | R$ 0,40 | 77 s |

- **O Sonnet empata nas críticas por 56% menos** em Pirapó; a diferença está na completude (63% contra 93%): o Sonnet entrega o fato, o Opus entrega o fato **e a ressalva que muda a leitura dele**.
- **O Haiku desiste:** os dois erros em Pirapó são "não localizado" para informação que estava no termo de referência (p. 6, item 8.1). Num sistema desenhado para que "não localizado" seja uma resposta honesta, um modelo que a usa como saída fácil corrói a regra.
- **Nenhum dos três achou a divergência que mais valia:** em Pirapó, o objeto da minuta é mais estreito que o do edital (31,9% da folha). Os três citaram um dos lados, nenhum marcou conflito, todos ancoraram 100%. Virou a regra RN-13 do verificador — a escolha do modelo não substitui regra determinística.

## Benchmark consolidado — 7 licitações

| Modelo | Licitações | Ancoragem | **Conflitos achados** | R$ por edital | s por edital |
|---|---|---|---|---|---|
| Opus 5 | 7 | 86/89 (96,6%) | **23** | 4,34 | 81 |
| Sonnet 5 | 7 | 80/86 (93,0%) | 16 | 1,79 (−59%) | 80 |
| Haiku 4.5 | 2 | 27/29 (93,1%) | 4 | 0,52 (−88%) | 54 |

**Recorte comparável** — as 2 licitações em que os três rodaram:

| Modelo | Ancoragem | Conflitos | R$ por edital |
|---|---|---|---|
| Opus 5 | 31/31 (100%) | **10** | 3,85 |
| Sonnet 5 | 29/31 (94%) | 7 | 1,65 |
| Haiku 4.5 | 27/29 (93%) | 4 | 0,52 |

> [!important] A relação é monotônica, e só numa das colunas
> **Ancoragem:** 100%, 94%, 93% — praticamente empatada. **Conflitos:** 10, 7, 4 — cai pela metade do topo à base. Citar com fidelidade é barato; **perceber que dois documentos se contradizem não é**. É a única dimensão em que o preço do modelo aparece no resultado — e é a que muda o lance.

## Dois fornecedores, seis modelos

### Pirapó/RS (23/09/2026, esforço `high`)

| Modelo | Acurácia | Críticas | Completude | Ancoragem | Tempo |
|---|---|---|---|---|---|
| `claude-opus-5` | **17/17** | **7/7** | **37/41** | 100% | 109 s |
| `gpt-6-sol` | **17/17** | **7/7** | 19/41 | 100% | 112 s |
| `claude-opus-5-5` | 16/17 | 7/7 | 33/41 | 100% | **72 s** |
| `gpt-5.6-sol` | 16/17 | 6/7 | 18/41 | 100% | 227 s¹ |
| `gpt-6-luna` | 16/17 | 7/7 | 17/41 | 100% | 166 s |
| `gpt-6-astra` | 15/17 | 6/7 | 19/41 | 100% | 299 s |

¹ medido quando a conta da OpenAI estava no limite inicial de 3 requisições por minuto — boa parte do tempo era espera, não inferência.

### Bertioga/SP — o edital difícil inverteu o fácil

| Modelo | Pirapó | **Bertioga** | Completude em Bertioga |
|---|---|---|---|
| `claude-opus-5-5` | 16/17 | **17/17** | **38/49** |
| `claude-opus-5` | 17/17 | **17/17** | 37/49 |
| `gpt-5.6-sol` | 16/17 | 15/17 | 25/49 |
| `gpt-6-sol` | **17/17** | 14/17 | 26/49 |
| `gpt-6-luna` | 16/17 | 11/17 ² | 25/49 |

² Recontado em 28/09/2026 com o avaliador corrigido (era 10/17); os outros modelos da tabela não foram recontados.

- **O empate não se sustenta no documento difícil.** Em Pirapó, o GPT-6 Sol empatou com o Opus — o melhor resultado de um GPT no projeto. Em Bertioga cai para 14/17, e o GPT-6 Luna despenca de 16 para 11. Os dois Opus ficam em 17/17.
- **O que muda entre os dois não é só o tamanho:** Bertioga tem 9 documentos que se contradizem, uma suspensão que altera a data da sessão e a pirâmide num anexo — recuperação sob conflito, não leitura linear. É o caso real de uma licitação de porte.
- **O "modelo mais inteligente" empatou com o mais barato:** o GPT-6 Astra, topo da linha da OpenAI, fez 15/17 em Pirapó — o mesmo que o Haiku —, com o dobro do tempo. Um nível abaixo, o GPT-6 Sol foi mais preciso, mais rápido e 37% mais barato que ele.
- **A completude separa por duas vezes:** Claude 33 a 38; GPT 17 a 26. Os GPT acertam o fato e não trazem o contexto — para quem precisa entender **por que** o valor é aquele antes do lance, não é o mesmo produto.
- **O Opus 5.5 ganhou o lugar do Opus 5:** perdeu em Pirapó (16 contra 17), empatou e ganhou em completude em Bertioga, sendo ~30% mais rápido, com preço menor por token ([[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]]).

## Em produção, pelo botão do site (28/09/2026)

A mesma licitação — Itapecuru Mirim/MA, 60 páginas, documento inteiro — extraída duas vezes pelo botão "Extrair com IA", com dois modelos baratos:

| | Claude Haiku 4.5 | GPT-6 Luna (`medium`) |
|---|---|---|
| custo | R$ 0,78 | **R$ 0,20** |
| tempo | 1 min 38 s | 2 min 54 s |
| aprovadas · revisar · reprovadas | 7 · 8 · 2 | **13 · 4 · 0** |
| respostas ancoradas | 9 de 16 (56%) | **16 de 16 (100%)** |

A diferença nas reprovadas veio do reforço do [[Best-of-N]]: no Luna, a Q11 e a Q12 ancoraram na 3ª e na 2ª tentativa; no Haiku, não ancoraram em nenhuma. Sem gabarito para esta licitação, a comparação é de **ancoragem**, não de acurácia, e é n = 1 por modelo — no edital difícil com gabarito, Bertioga/SP, o Luna acertou 14 e 13 de 17 pelo botão em `medium` e 13 de 17 em `high` (o Claude Opus 5.5 fez 16 de 17).

## Bertioga pelo botão, contra o gabarito (28/09/2026)

O edital difícil (Bertioga/SP, 115 páginas, RAG) extraído pelo botão com a v3.1 e pontuado contra o gabarito humano pelo mesmo avaliador do [[Harness de avaliação]]:

| Extração | Esforço | Acurácia | Críticas | Completude | Custo | Tempo |
|---|---|---|---|---|---|---|
| GPT-6 Luna, v3 (23/09/2026) | `high` | 11/17 | 3/7 | 25/49 | — | — |
| GPT-6 Luna, v3.1, botão (execução 2709) | `medium` | 14/17 | 5/7 | 20/49 | R$ 0,09 | 2 min 16 s |
| GPT-6 Luna, v3.1, botão (2710) | `medium` | 13/17 | 4/7 | 24/49 | R$ 0,03 | 1 min 50 s |
| GPT-6 Luna, v3.1, botão (2711) | `high` | 13/17 | 4/7 | 26/49 | R$ 0,11 | 4 min 18 s |
| Claude Opus 5.5, por agente (728) | — | **16/17** | **6/7** | **37/49** | — | — |

- **O esforço maior não comprou acurácia:** em `high`, o Luna gerou o dobro da saída (cerca de 22 mil tokens contra 10 a 11 mil) e levou o dobro do tempo, com a mesma acurácia e 2 pontos a mais de completude. O esforço voltou para `medium` no mesmo dia ([[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]]).
- **Os erros mudam de uma execução para outra**, na faixa de 13 a 14 acertos: a Q1 errou nas três (pega a suspensão, mas esquece a data original); a Q11 e a Q12 acertaram em `medium` e erraram em `high`; a Q13 e a Q15 erraram em `medium` e acertaram em `high`; a Q17 errou em duas das três.
- **O cache da OpenAI dependeu do esforço:** a 2710 leu o cache inteiro da 2709 — mesmo prompt, mesmo esforço — e custou R$ 0,03; a 2711, com o mesmo texto em `high`, não leu nada ([[Cache de prompt e ordem do prompt]]).
- **Leitura:** o teto do Luna neste edital parece ser 13 a 14 de 17, contra 16 do Opus; é n = 1 por configuração. A página de Bertioga no site exibe a extração do Opus.

## O piso: o modelo supera o regex?

O provedor simulado localiza trechos por expressões regulares sobre o mesmo contexto. Em Bertioga: ancoragem **0/13** e nenhuma resposta utilizável contra **17/17** do Opus, com 4 conflitos detectados. O regex acerta a página às vezes, mas o texto que devolve não responde à pergunta. A diferença não é de grau — e ter esse piso em código transforma "precisamos de um modelo de linguagem" de afirmação em resultado.

## O que esta comparação não diz

- n = 1 por linha; a variância entre execuções de conflitos é de 19% ([[Variância e como citar números]]).
- Dois editais com gabarito; o ordenamento dependeu do perfil do documento — um terceiro edital com gabarito é o que a próxima decisão de modelo exige.
- Custo real por execução só é atribuível pela fatura quando os tokens da execução batem com os do modelo no período.

## Relacionadas

[[MOC Avaliação]] · [[Modelos e provedores]] · [[Gabaritos]] · [[Métricas]] · [[Resultados medidos]] · [[Custo por edital]] · [[ADR-009 Modelo de extração]] · [[ADR-012 Segundo provedor de modelo]] · [[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]]
