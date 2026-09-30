---
tipo: edital
status: verificado
orgao_emissor: MUNICIPIO DE SÃO LOURENÇO DO SUL
cnpj: "87893111000152"
uf: RS
modalidade: Concorrência - Eletrônica
numero: Concorrência nº 09/2026
processo: Processo nº 327/2026
numero_controle_pncp: 87893111000152-1-000381/2026
data_publicacao_pncp: 2026-08-26
data_sessao: 2026-09-22T09:30:00-03:00
valor_minimo: 1900000.00
servidores_aprox: 1782
vigencia_meses: "{{A VERIFICAR}}"
extraido_em: 2026-09-22
extraido_por: Claude Code (sessão FOPA)
fonte: https://pncp.gov.br/app/editais/87893111000152/2026/381
api_arquivos: https://pncp.gov.br/api/pncp/v1/orgaos/87893111000152/compras/2026/381/arquivos
tags:
  - edital
  - amostra
  - caso-de-teste
---

# Edital Prefeitura São Lourenço do Sul — Concorrência 09/2026

> [!info] Identificação
> **Órgão emissor:** Município de São Lourenço do Sul / RS — CNPJ 87.893.111/0001-52
> **Objeto:** cessão onerosa do direito de efetuar o pagamento da folha dos servidores públicos (ativos, inativos, celetistas, pensionistas e contratados temporários)
> **Modalidade:** Concorrência Eletrônica nº 09/2026 · Processo nº 327/2026
> **Sessão pública:** 22/09/2026 às 09h30 (após retificação)
> **Data de extração:** 22/09/2026
> **Extraído por:** Claude Code — sessão FOPA
> **Origem:** [API de arquivos do PNCP](https://pncp.gov.br/api/pncp/v1/orgaos/87893111000152/compras/2026/381/arquivos)

## Inventário de arquivos

| # | Arquivo local | Nome original no PNCP | Tipo (PNCP) | Pág. | Texto | Responsável (assinatura digital) | Data assin. | Situação |
|---|---|---|---|---|---|---|---|---|
| 01 | `01 - Edital original (digitalizado, 44p).pdf` | `Concorr_ncia_09-2026_Cess_o.pdf` | Edital | 44 | ❌ **0 chars** | — | — | Digitalizado, requer OCR |
| 02 | `02 - Termo de Referencia corrigido (VIGENTE).pdf` | `Termo_de_Refer_ncia_Corrigido.pdf` | Outros Documentos | 15 | ✅ 37.266 | CLAUDIA LEMKE; ELIS REGINA MENDES | 24/08/2026 | **Vigente** |
| 03 | `03 - Aviso de Retificacao e reabertura de prazo.pdf` | `Retifica__o_Assinado..pdf` | Outros Documentos | 2 | ✅ 3.031 | TAIS DORILÉIA KUNDE | 26/08/2026 | **Vigente** |
| 04 | `04 - Edital corrigido (SUPERADO).pdf` | `Edital_Corrigido.pdf` | Edital | 27 | ✅ 84.033 | — | — | ⚠ Superado pelo 05 |
| 05 | `05 - Edital correto (VIGENTE).pdf` | `Edital_Correto.pdf` | Edital | 27 | ✅ 83.865 | — | — | **Vigente** |

### Hashes SHA-256 (auditoria de integridade)

| # | SHA-256 (16 primeiros) |
|---|---|
| 01 | `55da3d8726798c2c` |
| 02 | `e703e1c4012f00b8` |
| 03 | `ce8ba064f89c4edc` |
| 04 | `e094dc527038c40c` |
| 05 | `d5f0525b29c42298` |

## O que vem em cada arquivo

### 01 — Edital original (digitalizado)
44 páginas, 10,6 MB, **29 objetos de imagem e zero fontes embutidas**. A extração de texto devolveu 44 caracteres (só espaços).

> [!risco] É o maior arquivo e o único inútil sem OCR
> É provavelmente o edital completo **com anexos**, escaneado. Os outros dois editais têm só 27 páginas — ou seja, **17 páginas de conteúdo só existem aqui**, em imagem.
>
> Sem OCR, essas 17 páginas são invisíveis ao pipeline.

### 02 — Termo de Referência corrigido
15 páginas. **É onde mora a pirâmide salarial.**

Objeto (item 1): contratação de instituição financeira pública ou privada, ou cooperativa de crédito, autorizada pelo BCB, para a cessão onerosa do direito de efetuar o pagamento da folha — **"em número aproximado de 1.782 (um mil e setecentos e oitenta e dois) servidores do poder executivo, podendo ocorrer variações"**.

Pirâmide salarial (referente a maio/2026), com **mais colunas que as previstas**:

| Salário | Qtde | Vlr. Bruto | Vlr. Líquido | Aux. Alimentação |
|---|---|---|---|---|
| De R$ 00,00 até R$ 1.000,00 | 07 | R$ 5.684,56 | R$ 5.734,29 | R$ 655,08 |
| De R$ 1.000,01 até R$ 2.000,00 | 57 | R$ 116.420,50 | R$ 93.250,25 | — |
| De R$ 2.000,01 até R$ 3.000,00 | 157 | R$ 414.857,23 | R$ 354.993,07 | R$ 30.420,00 |
| De R$ 3.000,01 até R$ 4.000,00 | 03 | R$ 11.751,44 | R$ 10.362,81 | R$ 91.260,90 |
| De R$ 4.000,01 até R$ 5.000,00 | 61 | R$ 269.272,76 | R$ 256.785,45 | R$ 1.800,00 |
| De R$ 5.000,01 até R$ 6.000,00 | 02 | R$ 10.614,62 | R$ 10.833,14 | R$ 36.600,00 |
| De R$ 6.000,01 até R$ 7.000,00 | 00 | — | — | R$ 1.200,00 |

> [!risco] A tabela acima é de UM vínculo apenas ("Contratos")
> O cabeçalho da seção diz **"Contratos"**. Somando essa tabela: **287 servidores** — muito abaixo dos **1.782** do objeto.
>
> Existem **outras tabelas** no documento (estatutários, inativos, pensionistas, temporários). A Q13 só está correta se capturar **todas**.
>
> É exatamente a falha que já detectamos em Uru (182 vs 205), aqui em escala maior. Confirma que a validação "soma das faixas = total" é obrigatória, não opcional. Ver [[4 Verificador]].

> [!risco] Assinatura digital contamina o texto extraído
> O texto da tabela vem entrelaçado com a tarja lateral de assinatura:
>
> ```
> A pirâmide salarial (valor e quantidade...), referente    Assinado por 2 pessoas: CLAUDIA LEMKE e ELIS...
> ao mês de maio de 2026:                    Para verificar a autenticidade do documento, acesse https://...
> ```
>
> Um parser de tabela ingênuo lê "Assinado por 2 pessoas" como célula. O pré-processador precisa **remover a faixa de assinatura antes de parsear tabelas**.

### 03 — Aviso de Retificação e reabertura de prazo
2 páginas. Documento curto e o **mais importante do conjunto**.

> [!fato] Ele muda a data da sessão e cita a base legal
> "em razão de retificações no Termo de Referência [...] As alterações realizadas impactam a formulação das propostas, motivo pelo qual, em atendimento ao disposto no **art. 55, §4º e §5º da Lei nº 14.133/2021**, fica reaberto o prazo para apresentação das propostas. O Termo de Referência, com as alterações nos **item 1 (um) e 4 (quatro)**, estarão disponíveis no portal de compras públicas."
>
> **Novo cronograma:**
> - Início do recebimento das propostas: 31/08/2026
> - Limite para envio das propostas: 22/09/2026
> - **Abertura da sessão pública: 22/09/2026 às 09h30min**

> [!risco] A Q1 extraída do edital estaria ERRADA
> A data da sessão vigente **não está em nenhum dos editais** — está só neste aviso de 2 páginas. Quem responder a Q1 lendo o edital entrega data vencida.
>
> E o item 1 do TR é justamente o **objeto com a pirâmide salarial** — ou seja, a retificação pode ter alterado a própria Q13.

### 04 e 05 — os dois editais "vigentes"
27 páginas cada, ambos `statusAtivo: true`, ambos `tipoDocumentoNome: "Edital"`. Diferença de 112 bytes.

> [!fato] Eles divergem justamente na Q5
> | Arquivo | Item 2.3 |
> |---|---|
> | 04 `Edital_Corrigido` | "Valor **Estimado** da Contratação: O valor **estimado** da licitação é de R$ 1.900.000,00" |
> | 05 `Edital_Correto` | "Valor **Mínimo** da Contratação: O valor **mínimo** da licitação é de R$ 1.900.000,00" |
>
> Outras diferenças: numeração do capítulo corrigida ("1. DO CRITÉRIO DE JULGAMENTO" → "2. DO CRITÉRIO..."), inclusão de "Quadro Resumo:" e reordenação de parágrafos.

> [!risco] Por que isso é grave e não cosmético
> A Q5 pergunta **"Qual o Valor Mínimo de Contratação?"**. Em leilão de **maior oferta**, "valor estimado" e "valor mínimo" são conceitos distintos: um é referência, o outro é o **piso que o lance precisa superar**.
>
> O número é o mesmo (R$ 1.900.000,00), mas o **significado jurídico muda** — e é sobre esse significado que a mesa de negociação decide o lance.
>
> Este é o caso real que valida a regra do maior `sequencialDocumento`: o correto é o **05**. Ver [[ADR-006 Documento vigente é o de maior sequencial]].

## Lições que este conjunto gerou

> [!abstract] O que esta licitação provou empiricamente
> 1. **OCR não é opcional** — o maior arquivo (44 p.) tem zero texto.
> 2. **A resposta pode estar em documento que não é o edital** — a pirâmide está no TR; a data da sessão está no aviso de retificação.
> 3. **"Edital" ativo não significa edital vigente** — havia 3, e dois divergiam na Q5.
> 4. **O total do objeto não fecha com a tabela** — 1.782 declarados vs 287 na primeira tabela.
> 5. **Assinatura digital polui o texto** e quebra parsing de tabela.
> 6. **`Info` precisa dizer o arquivo, não só a página** — "p. 30" é ambíguo com 5 arquivos.

## Pendências

> [!todo] A completar
> - [ ] Rodar OCR no arquivo 01 e verificar quais das 17 páginas extras trazem resposta.
> - [ ] Extrair **todas** as tabelas da pirâmide do TR e conferir se somam 1.782.
> - [ ] Preencher `vigencia_meses` (Q9) a partir do arquivo 05.
> - [ ] Confirmar se a retificação alterou a pirâmide (comparar TR vigente com a versão anterior, se disponível).
> - [ ] Consultar [[PNCP - resultados]] após 22/09/2026 para registrar vencedor e valor homologado.

## Relacionadas

[[PNCP - documentos]] · [[3 Extrator de edital]] · [[4 Verificador]] · [[ADR-006 Documento vigente é o de maior sequencial]] · [[Questionário de extração]] · [[Gabarito - Uru]]
