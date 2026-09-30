---
tipo: componente
familia: worker-e-api
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - api/converter.py
  - api/baixar.py
  - scripts/28_baixar_licitacao.py
tags: [download, conversao, formatos, dados]
---

# Conversão de formatos

> [!abstract] Em uma frase
> Quando o PNCP entrega um documento que **não é PDF** — Word, Excel, RTF, HTML, imagem, ZIP, RAR, assinatura digital com o documento dentro —, o worker o **transforma em PDF** antes da leitura, guardando o original como `convertido` e cada PDF gerado como filho dele; se não der, o arquivo fica recusado com o motivo escrito.

## Papel na solução

O resto do pipeline (páginas congeladas, OCR, citação "arquivo · p. N") depende de PDF. Ler o texto cru de um Word perderia a **página** — e a página é a prova. Converter mantém a mesma garantia para qualquer formato ([[ADR-017 O arquivo que não é PDF vira PDF]]).

## O que é convertido e como

| Formato real (pelos bytes, não pela extensão) | Como vira PDF |
|---|---|
| RTF, Word/Excel antigos (`.doc`, `.xls`), Office moderno (`.docx`, `.xlsx`, `.pptx`), ODF, HTML | LibreOffice sem tela (`soffice --headless`), até 180 s por arquivo |
| PNG, JPEG | PDF de uma página (PyMuPDF); a leitura faz o OCR |
| ZIP (inclusive o ZIP com nome `.pdf`) | abre e aplica a mesma regra a cada arquivo de dentro |
| RAR | extrai (`bsdtar`) e aplica a mesma regra |
| Assinatura digital CAdES (`.p7s` do ICP-Brasil) com o documento dentro | extrai o documento e aplica a mesma regra |
| PDF cortado (sem `%%EOF`) ou sem páginas | não há o que converter: recusa com o motivo ("é PDF, mas está cortado") |

Até **3 níveis** de arquivo dentro de arquivo (um ZIP com um RAR dentro abre; quatro camadas, não).

## Garantias

- **O formato é descoberto pelos primeiros bytes**, não pelo nome: o PNCP põe `.pdf` em arquivos que não são PDF.
- **Nada some em silêncio:** falhou a conversão, o arquivo fica `formato_nao_suportado` com o motivo em `arquivos.motivo` — visível no detalhe da licitação.
- **Tempo esgotado mata o grupo inteiro** de processos do LibreOffice (um RTF de 12,7 MB chegou a deixar um conversor órfão consumindo CPU).
- **Rastreabilidade:** o original e os gerados ficam ligados (`pai_id`), com a origem na proveniência.

## Resultado medido

Quando a conversão entrou (25/09/2026), **40 das 41** licitações de folha presas por formato foram destravadas; a única que sobrou tinha um JSON no lugar do documento.

## Relacionadas

[[MOC Worker e API]] · [[W21 Baixar]] · [[OCR]] · [[Armazenamento de arquivos (S3)]] · [[ADR-017 O arquivo que não é PDF vira PDF]]
