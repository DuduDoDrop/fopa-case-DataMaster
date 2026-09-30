---
tipo: legal
familia: legal
status: verificado
atualizado: 2026-09-28
fontes:
  - https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm
  - https://www.tce.sp.gov.br/legislacao-comentada/lei-14133-1o-abril-2021/54
  - https://www.tce.sp.gov.br/legislacao-comentada/lei-14133-1o-abril-2021/55
  - https://www.tce.sp.gov.br/legislacao-comentada/lei-14133-1o-abril-2021/176
  - https://www.gov.br/pncp/pt-br/pncp/perguntas-e-respostas
tags: [legal, licitacao, pncp, lei-14133]
aliases: [Nova Lei de Licitações, NLLC]
---

# Lei 14.133/2021 — visão geral

> [!abstract] Em uma frase
> A norma geral de licitações e contratos da administração direta, autárquica e fundacional de todos os entes é a base jurídica da solução: o **art. 54** obriga a publicação do **inteiro teor** do edital no PNCP (o insumo da solução), o **art. 176** dá aos municípios de até 20 mil habitantes até **01/04/2027** para aderir ao PNCP (o limite de cobertura), e os arts. **33, 55, 98 e 110** explicam critérios, prazos e garantias que aparecem nas 17 perguntas.

## Papel na solução

Sem o art. 54, a solução não existiria: é ele que torna o edital completo público, íntegro e centralizado. E a lei também explica por que alguns campos do PNCP não descrevem bem a licitação de folha — o que é mais um motivo para ler o edital ([[Cessão onerosa da folha - fundamentos]]).

## Art. 54 — publicidade do edital

> [!quote] Redação literal
> **Caput.** "A publicidade do edital de licitação será realizada mediante divulgação e manutenção do inteiro teor do ato convocatório e de seus anexos no Portal Nacional de Contratações Públicas (PNCP)."
>
> **§ 1º** "Sem prejuízo do disposto no caput, é obrigatória a publicação de extrato do edital no Diário Oficial da União, do Estado, do Distrito Federal ou do Município, ou, no caso de consórcio público, do ente de maior nível entre eles, bem como em jornal diário de grande circulação."
>
> **§ 3º** "Após a homologação do processo licitatório, serão disponibilizados no Portal Nacional de Contratações Públicas (PNCP) (…) os documentos elaborados na fase preparatória que porventura não tenham integrado o edital e seus anexos."

| Consequência | Na solução |
|---|---|
| inteiro teor no PNCP | a fonte dos documentos que o extrator lê ([[Fontes de dados — PNCP]]) |
| extrato no diário oficial | um diário traz o **extrato**, não o edital — por isso um agregador de diários seria canal de descoberta, não de extração ([[ADR-007 Cobertura de municípios pequenos]]) |
| documentos da fase preparatória depois da homologação | a lista de documentos de uma licitação pode crescer depois da sessão ([[W70 Retificações]]) |

O art. 174 cria o PNCP e torna a divulgação nele obrigatória para todos os entes federados; o portal opera em formato de dados abertos, sob a Lei de Acesso à Informação ([[Legalidade da automação]]).

## Art. 176 — a transição dos municípios pequenos

> [!quote] Redação literal (trecho)
> "Os Municípios com até 20.000 (vinte mil) habitantes terão o prazo de 6 (seis) anos, contado da data de publicação desta Lei, para cumprimento: (…) III - das regras relativas à divulgação em sítio eletrônico oficial.
>
> Parágrafo único. Enquanto não adotarem o PNCP, os Municípios a que se refere o caput deste artigo deverão: I - publicar, em diário oficial, as informações que esta Lei exige que sejam divulgadas em sítio eletrônico oficial, admitida a publicação de extrato; II - disponibilizar a versão física dos documentos em suas repartições (…)."

A lei foi publicada em **01/04/2021**: o prazo vence em **01/04/2027**. Não houve prorrogação (a Lei 14.770/2023 alterou outros pontos e não este prazo). Metade dos municípios que a solução já enxerga está nessa faixa e publica no PNCP assim mesmo ([[ADR-007 Cobertura de municípios pequenos]]).

## Art. 55 — prazos mínimos entre a divulgação e as propostas

Em **dias úteis**, contados da divulgação do edital:

| Objeto / critério | Dias úteis |
|---|---|
| bens — menor preço ou maior desconto | 8 |
| bens — demais casos | 15 |
| serviços e obras comuns — menor preço ou maior desconto | 10 |
| serviços e obras especiais — menor preço ou maior desconto | 25 |
| **maior lance** | **15** |
| técnica e preço, melhor técnica, conteúdo artístico | 35 |
| contratação semi-integrada e demais casos | 35 |
| contratação integrada | 60 |

- **§ 1º:** alterar o edital exige nova divulgação e reabre o prazo, salvo se a mudança não afetar a formulação das propostas — **a data da sessão pode andar para frente** depois de uma retificação.
- **O prazo legal não é o tempo que o banco tem.** Ele conta da divulgação do edital; o tempo útil para a análise conta de quando o registro **aparece no PNCP**. Medido em 198 licitações (23/09/2026): mediana de **16 dias úteis** entre o registro no portal e o fim do prazo; 94,4% com ao menos 10; e três licitações com **zero** — registro no portal no dia da sessão ([[Resultados medidos]]).

## Art. 33 — os critérios de julgamento

O artigo lista menor preço, maior desconto, melhor técnica ou conteúdo artístico, técnica e preço, **maior lance (no caso de leilão)** e maior retorno econômico. Nenhum descreve a cessão onerosa da folha, em que **o banco paga** ao órgão — a lacuna está detalhada em [[Cessão onerosa da folha - fundamentos]] e explica por que o campo "critério" do PNCP vem disperso (por isso o verificador compara **famílias** de critério — [[Verificador determinístico]]).

## Arts. 96 e 98 — garantias (Q17)

Garantia de proposta até 1% do valor estimado (art. 96); garantia de execução **facultativa**, até 5% do valor inicial, 10% com justificativa, sobre o **valor anual** em contratos contínuos com vigência acima de um ano (art. 98) — detalhes em [[Garantia contratual]].

## Art. 110, I — o prazo dos contratos que geram receita (Q9)

"Na contratação que gere receita (…) os prazos serão de: I – até 10 (dez) anos, nos contratos sem investimento." A cessão da folha **gera receita** para o órgão: é esse o fundamento dos contratos de 60 meses, não o art. 107, que trata da prorrogação de serviços contínuos em que a Administração **paga** ([[Cessão onerosa da folha - fundamentos]]).

## Relacionadas

[[MOC Legal]] · [[Cessão onerosa da folha - fundamentos]] · [[Garantia contratual]] · [[Lei 13.303-2016 - estatais]] · [[Jurisprudência — tribunais de contas]] · [[ADR-002 PNCP como fonte primária]] · [[ADR-007 Cobertura de municípios pequenos]] · [[Questionário — as 17 perguntas]]
