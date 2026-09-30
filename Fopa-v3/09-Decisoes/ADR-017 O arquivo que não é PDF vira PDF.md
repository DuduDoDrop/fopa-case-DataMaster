---
tipo: decisao
familia: decisoes
adr: 17
data: 2026-09-25
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, download, conversao, worker]
---

# ADR-017 — O arquivo que não é PDF vira PDF

> [!abstract] Em uma frase
> Todo documento que chega do PNCP em outro formato — Word, Excel, RTF, HTML, imagem, ZIP, RAR, assinatura digital com o documento dentro — é **convertido em PDF no download**, para que a leitura, o OCR e a citação por **página** funcionem igual para qualquer formato; o original fica registrado como `convertido` e, se a conversão falhar, o motivo fica escrito.

## Problema

O PNCP entrega cada documento com o nome que o órgão deu e não confere o formato: `Edital.pdf` que é RTF, `documento.doc.pdf` que é `.doc` antigo, `edital.rar.pdf` com o edital e os anexos dentro, ZIP só com `.docx`. Tudo o que não abria como PDF era recusado num estado **terminal** (tentar de novo não muda o formato). Em 25/09/2026 eram **41 licitações de folha inteiras presas** assim — uma delas aberta, com prazo em três dias e edital em RTF — e **90** tinham ao menos um arquivo recusado pelo formato.

## Opções

| Opção | Avaliação |
|---|---|
| ler o texto cru do Word ou do RTF | perderia a **página**, e com ela a citação verificável, o OCR e o link que abre na página certa |
| recusar o que não é PDF | licitações inteiras invisíveis |
| **converter para PDF uma vez, no download, e congelar** | a paginação vira fato auditável, como a de qualquer PDF |

## Escolha

| O que chega (pelos bytes, não pela extensão) | Como vira PDF |
|---|---|
| RTF, `.doc`/`.xls`, `.docx`/`.xlsx`/`.pptx`, ODF, HTML | LibreOffice sem tela, com perfil próprio a cada conversão e até 180 s por arquivo |
| PNG, JPEG | PDF de uma página; a leitura faz o OCR |
| ZIP, RAR, assinatura digital (`.p7s`) com o documento dentro | abre e aplica a mesma regra a cada arquivo de dentro, até 3 níveis |

- O original fica com status **`convertido`** e cada PDF gerado é **filho** dele, com a origem registrada.
- **A conversão nunca derruba o download:** se falhar, o arquivo fica `formato_nao_suportado` com o motivo ("… — a conversão para PDF falhou: …").
- **RAR é tudo ou nada** — nunca meio RAR em silêncio —, lido pelo `bsdtar` (o pacote de 7-Zip da distribuição vem sem o código do RAR, que não é livre); links simbólicos dentro do arquivo são ignorados.
- A imagem do worker traz fontes com as métricas das do Office, para a paginação do documento convertido não mudar.

## O que foi medido

- As 41 licitações presas foram reprocessadas uma a uma: **40 destravadas**; a que sobrou tinha um JSON no lugar do documento.
- No total, 44 licitações e 82 PDFs gerados (de ZIP e RAR, `.doc`, RTF, `.docx`, assinatura digital e `.xlsx`), com 1.811 páginas lidas.
- Casos novos que apareceram na primeira passada viraram código antes da segunda: PDF dentro de assinatura digital ICP-Brasil e ZIP com RAR dentro.

## O que custa

Uma dependência de sistema (LibreOffice) e segundos a mais por documento convertido; um formato sem conversor continua recusado — com o motivo, nunca em silêncio.

## Onde vive em produção

`api/converter.py` e `api/baixar.py`, rodados pelo job de download do [[W21 Baixar]]; o status `convertido` e a relação pai–filho em `arquivos`; no detalhe da licitação, o original aparece como "nome (convertido)" com o motivo, e o PDF gerado com link ([[Conversão de formatos]]).

## O que reabriria a decisão

Um formato recorrente que o LibreOffice não converta com paginação estável.

## Relacionadas

[[MOC Decisões]] · [[Conversão de formatos]] · [[W21 Baixar]] · [[ADR-005 Info é arquivo mais página física]] · [[ADR-018 Licitação de folha pega todos os arquivos]]
