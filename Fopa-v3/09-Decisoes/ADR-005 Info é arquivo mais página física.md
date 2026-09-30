---
tipo: decisao
familia: decisoes
adr: 5
data: 2026-09-22
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, evidencia, questionario]
---

# ADR-005 — Info é arquivo mais página física

> [!abstract] Em uma frase
> A evidência de cada resposta é **o arquivo e a página física** do PDF — a que o leitor mostra, não a numeração impressa —, porque uma licitação tem de 1 a 9 documentos e "p. 30" sozinho não diz de qual.

## Problema

A especificação original do entregável definia a coluna de evidência como "p. N". Os documentos reais mostraram que isso não permite conferência: página 30 de qual arquivo?

## O que foi medido

- Uma licitação tem de **1 a 9 arquivos** (medido em 6 modalidades).
- **20 de 107 licitações (19%) têm mais de um arquivo do tipo "Edital"**; o extremo, Arraial do Cabo/RJ, tem sete. São Lourenço do Sul/RS tem três, e a pirâmide salarial está no termo de referência, não no edital.
- A numeração impressa diverge da física: capa, anexos e páginas sem número desalinham.
- **Nem todo arquivo tem página:** o censo de 23/09/2026 achou documentos em Word, RTF, `.doc` antigo e RAR — em quatro licitações, o arquivo ilegível era o próprio edital, e em duas era o único arquivo. Um DOCX não tem página física: a paginação é calculada por quem abre, e dois leitores chegam a números diferentes.

## Opções

| Opção | Avaliação |
|---|---|
| só "p. N" | ambíguo com vários arquivos; inviabiliza a conferência |
| numeração impressa | diverge da física |
| só o nome do arquivo | não localiza o trecho |
| **arquivo + página física** | conferível por qualquer pessoa e pelo verificador |

## Escolha

- Evidência = **arquivo + página física**. O contexto do modelo marca cada página com `=== ARQUIVO x | PÁGINA n ===`, e a regra 4 do prompt manda citar esse número ([[Prompt do extrator]]).
- Todo documento que **não é PDF é convertido em PDF** uma vez, no download; o PDF gerado é congelado e passa a ser o fato contra o qual se cita ([[ADR-017 O arquivo que não é PDF vira PDF]]).

## O que custa

- Uma coluna mais longa que a especificada originalmente.
- Nome de arquivo estável — resolvido pelo inventário com SHA-256 de cada documento e, no verificador, pela resolução do nome citado (aceita só se resolver para um único arquivo).
- A conversão de formatos é uma dependência de sistema (LibreOffice sem tela), no mesmo balde do OCR.

## Onde vive em produção

- A tabela `paginas` guarda o texto por arquivo e página física; `verificacao_respostas` guarda o arquivo resolvido, a página final e a página que o modelo citou.
- No site e no e-mail, cada citação é um link "arquivo p. N" que abre o PDF **na página**: a API responde com um redirecionamento para uma URL assinada de 10 minutos do armazenamento, e o navegador aplica o `#page=N` ([[API do site — endpoints]]).

## O que reabriria a decisão

Um formato de documento que não possa virar PDF com paginação estável — hoje, esse caso fica recusado com o motivo escrito, nunca citado.

## Relacionadas

[[MOC Decisões]] · [[ADR-004 Evidência obrigatória]] · [[ADR-017 O arquivo que não é PDF vira PDF]] · [[Verificador determinístico]] · [[Conversão de formatos]] · [[Página Relatório]]
