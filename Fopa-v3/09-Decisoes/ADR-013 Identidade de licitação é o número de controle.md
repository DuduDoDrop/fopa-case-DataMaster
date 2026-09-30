---
tipo: decisao
familia: decisoes
adr: 13
data: 2026-09-23
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, dados, identidade, coleta]
---

# ADR-013 — Identidade de licitação é o número de controle

> [!abstract] Em uma frase
> Uma licitação é identificada pelo **número de controle do PNCP** (CNPJ do órgão, tipo, sequencial e ano, como `05648696000180-1-000088/2026`) — único e imutável —, nunca por nome de município, de órgão ou de pasta; tudo o que responde "já temos isso?" casa por ele.

## Problema

Nomes são convenientes para gente e péssimos como chave. O mesmo defeito apareceu **quatro vezes**, nos dois sentidos:

| Forma | Caso | Estrago |
|---|---|---|
| **uma licitação, dois nomes** | a mesma dispensa aparecia como "Rio Branco-AC" (pelo município) e "Tribunal de Contas do Estado do Acre" (pelo órgão) | virava "órfã" no mapa e era baixada de novo |
| **duas licitações, um nome** | Bento Gonçalves/RS tem seis licitações de folha distintas, todas "Concorrência Eletrônica" | **30 de 172 (17%)** licitações em escopo descartadas em silêncio; depois de recuperadas, 27 das 30 puladas por outra função que ainda comparava nomes |

## Opções

| Opção | Avaliação |
|---|---|
| nome da pasta ou do município como chave | colide nos dois sentidos |
| nome + desempate | reproduz o defeito com mais passos |
| **número de controle como identidade; nome é só rótulo** | único, imutável, vem do próprio PNCP |

## Escolha

1. Toda comparação de "já temos isso?" casa por **número de controle**.
2. O nome é endereço ou rótulo de exibição, e pode mudar sem quebrar nada.
3. Quando um defeito de identidade aparece, procuram-se **todos** os lugares que comparam nomes antes de fechar — escrever a lição não é aplicá-la: na quarta ocorrência, a correção de uma função ficou invisível porque a função ao lado ainda comparava nomes.

## Onde vive em produção

| Onde | Como |
|---|---|
| Banco | `licitacoes.controle` é a chave primária; todas as tabelas da licitação referenciam o controle ([[Modelo de dados]]) |
| [[W01 Descoberta]] | deduplica os itens da busca pelo controle; `fn_registrar_vista` decide inserir, ignorar, retificar ou só marcar como vista |
| Site | a URL usa o controle com "/" trocado por "-" (o *slug*): `/licitacao/05648696000180-1-000088-2026` |
| Gêmeas | uma licitação republicada com outro controle e **os mesmos PDFs** é marcada como gêmea (`gemea_de`) pelo conjunto de hashes dos documentos, nunca pelo nome ([[W22 Ler]]) |
| Republicações | o Analytics liga a licitação que voltou ao portal à anterior por heurística explícita — mesmo órgão, até 540 dias, a anterior sem vencedor ([[Página Analytics Histórico FOPA]]) |

## O que custa

Nada de relevante: o controle vem em toda resposta do PNCP. O cuidado é não deixar nenhum caminho antigo decidir por nome.

## O que reabriria a decisão

O PNCP mudar o formato ou a unicidade do número de controle.

## Relacionadas

[[MOC Decisões]] · [[Modelo de dados]] · [[W01 Descoberta]] · [[Fontes de dados — PNCP]] · [[ADR-002 PNCP como fonte primária]]
