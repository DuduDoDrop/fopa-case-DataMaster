---
tipo: decisao
familia: decisoes
adr: 6
data: 2026-09-22
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, documentos, precedencia, retificacao]
---

# ADR-006 — Documento vigente é o de maior sequencial

> [!abstract] Em uma frase
> Quando uma licitação tem vários documentos que se contradizem, vale o de **maior número sequencial** dentro do mesmo tipo, e retificações, suspensões e comunicados têm precedência sobre o edital — regra adotada pelo comportamento observado, porque o PNCP **não diz** qual documento é o vigente.

## Problema

Uma licitação no PNCP pode ter vários arquivos marcados como "Edital", **todos ativos**, e a API não informa qual vale. Em São Lourenço do Sul/RS, o edital de sequencial 4 dizia "Valor **Estimado** da Contratação" e o de sequencial 5, "Valor **Mínimo** da Contratação" — o mesmo R$ 1.900.000,00, mas conceitos opostos num leilão de maior oferta: um é referência, o outro é o piso que o lance precisa superar.

## Opções

| Opção | Avaliação |
|---|---|
| pelo nome do arquivo | "Corrigido" e "Correto" são indistinguíveis; acentos chegam corrompidos |
| pelo `statusAtivo` | todos vêm ativos: o portal não desativa a versão velha |
| perguntar a um modelo | reintroduz o não determinismo que se quer eliminar |
| processar todos e unir | respostas contraditórias sem critério |
| **maior `sequencialDocumento` no mesmo tipo, com retificações por cima** | determinístico, e confirmado contra a data de publicação |

## O que foi medido

- **O manual e a especificação do PNCP são omissos:** `sequencialDocumento` aparece 30 vezes na especificação da API sem nenhuma descrição, e a palavra "vigente" não aparece nenhuma vez. A regra é **convenção adotada**, não leitura de norma.
- **Sequencial crescente = mais recente:** em 82 licitações com dois ou mais arquivos ativos, a ordem por sequencial foi **igual** à ordem por data de publicação em todas (0 discordâncias).
- **Nenhum órgão reaproveita sequencial** (107 licitações conferidas); há buracos na numeração (remoções), por isso nunca se itera de 1 a N.
- **A regra vale para 1 em cada 5 licitações:** 19% têm mais de um "Edital".
- **Retificação depois do download é rara:** 1 em 171 licitações ganhou documento novo em menos de um dia (a primeira medição dizia 4,8% e estava errada: contava como "novos" arquivos recusados cujo sequencial o inventário não guardava).

## Escolha

- Todos os documentos são lidos (nunca só "o edital"): a resposta frequentemente está no termo de referência, no aviso de retificação ou na resposta a um esclarecimento.
- **Ordem de precedência** na leitura e no prompt: retificação > suspensão > comunicado > redesignação > errata > resposta a esclarecimento > termo de referência > edital. O modelo recebe os documentos nessa ordem e a regra 5 do prompt manda usar o mais recente e **descrever a divergência** em `conflito`.
- No modo RAG, os arquivos de retificação, suspensão, comunicado, redesignação, errata e aviso entram **sempre**, independentemente da pontuação ([[RAG com BM25]]).
- Se um dia sequencial e data discordarem, a data manda — ela é o fato, o sequencial é o índice.

## O que custa

- A regra é convenção, e está dito como convenção.
- A ancoragem não protege contra edital retificado depois da leitura: o trecho continua existindo na página citada, mas o órgão substituiu o documento. Isso é coberto por outro mecanismo — o acompanhamento de retificações.

## Onde vive em produção

| Onde | Como |
|---|---|
| `scripts/fopa/extrator.py` | `PRECEDENCIA` ordena os arquivos; `SEMPRE_INCLUIR` força as âncoras no RAG |
| [[Prompt do extrator]] | regra 5 (precedência e conflito) |
| [[W01 Descoberta]] | uma licitação conhecida que o PNCP atualizou vira ação `retificar` |
| [[W70 Retificações]] | aos domingos, confere documentos novos nas licitações acompanhadas e as leva ao estado `retificada`, que prioriza o reprocessamento |
| [[Verificador determinístico]] | resposta com conflito vai para REVISAR; cruzamento com o valor e o critério informados na API do PNCP |

## O que reabriria a decisão

O PNCP passar a publicar um campo oficial de vigência, ou um caso em que sequencial e data discordem.

## Relacionadas

[[MOC Decisões]] · [[Fontes de dados — PNCP]] · [[W70 Retificações]] · [[Ciclo de vida de uma licitação]] · [[RAG com BM25]] · [[ADR-005 Info é arquivo mais página física]]
