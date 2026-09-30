---
tipo: componente
familia: worker-e-api
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/ocr.py
  - scripts/fopa/extrator.py
  - api/leitura.py
  - docker/worker.Dockerfile
tags: [ocr, tesseract, leitura, dados]
---

# OCR

> [!abstract] Em uma frase
> Parte dos editais é imagem escaneada; o sistema faz **OCR local com o Tesseract 5.4.0 em português**, página a página, só onde o PDF não tem texto (menos de 120 caracteres por página), com dois perfis medidos — um para texto corrido e outro para tabela — e **nunca** confia sozinho numa pirâmide salarial lida por OCR.

## Papel na solução

Sem OCR, um edital escaneado é invisível — e nele pode estar a informação que decide o lance. O OCR é **local** (nenhum documento sai do servidor) e **determinístico** (o mesmo arquivo gera o mesmo texto), o que mantém a verificação reproduzível ([[ADR-008 OCR — stack, configuração e limites]]).

## As regras

| Regra | Como | Por quê (medido) |
|---|---|---|
| **Gatilho** | página com **menos de 120 caracteres** de texto nativo → OCR | o texto nativo é exato; o OCR só onde falta |
| **Texto corrido** | `lang=por`, **150 dpi**, `psm 3` | 92,97% de similaridade de palavra, 2,2 s/página; DPI maior não melhora e é mais lento; o português vale 6,4 pontos sobre o inglês |
| **Tabela** | `lang=por`, **400 dpi**, `psm 4` | **zero valores errados** nas tabelas medidas (outras configurações liam `1.000,07` onde era `1.000,01`) |
| **Assinatura digital** | a tarja "assinado por N pessoas / código para verificação" é removida antes de ler tabela | ela entra no meio das tabelas |
| **Preferir o digital** | se a mesma informação existe num documento com texto, usa-se esse | o OCR recupera ~79% dos valores de uma pirâmide escaneada |
| **Pirâmide de OCR nunca entra sozinha** | a resposta vai para revisão humana com a marca | valor faltando o verificador sinaliza; valor **errado** entraria no lance |
| **OCR forçado e rotação** | um operador pode marcar um arquivo para OCR forçado ou girado (camada de texto cortada, carimbo sobre imagem, página de cabeça para baixo) | três defeitos passam pelo gatilho de 120 caracteres com texto ruim |

## Versão fixa, verificada

- O Tesseract **5.4.0** e a Leptonica 1.84.1 são **compilados na imagem** do worker; o `por.traineddata` tem o SHA-256 conferido no build.
- O `/health` do worker responde 503 se a versão ou o idioma não baterem, e o [[W00 Saúde]] confere de hora em hora.
- Motivo: as medições de qualidade foram feitas com essa versão; outra versão geraria leituras **não comparáveis**. A equivalência entre o OCR da máquina de desenvolvimento e o da imagem de produção foi **medida** (arquivos `docs/ocr-equivalencia-*.json`) — a imagem é a referência.
- A versão do OCR (com as marcações de OCR forçado) faz parte da **identidade da leitura**: outro OCR gera outra leitura, lado a lado, nunca sobrescrita ([[W22 Ler]]).

## Quanto OCR o acervo exige

Medição em 324 PDFs de 108 licitações: **12,7% dos arquivos** e **8,6% das páginas** precisam de OCR; uma licitação em cada sete tem ao menos um arquivo escaneado — geralmente um **anexo grande**, raramente o edital principal. Em produção, o painel mostra por licitação quantas páginas foram por OCR (Itapecuru Mirim/MA: 60 páginas, 0 por OCR).

## Relacionadas

[[MOC Worker e API]] · [[W22 Ler]] · [[Worker — visão geral e jobs]] · [[Conversão de formatos]] · [[Consciência operacional]] · [[ADR-008 OCR — stack, configuração e limites]] · [[W00 Saúde]]
