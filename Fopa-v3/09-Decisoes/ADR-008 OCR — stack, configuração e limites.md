---
tipo: decisao
familia: decisoes
adr: 8
data: 2026-09-22
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, ocr, leitura, dados]
---

# ADR-008 — OCR: stack, configuração e limites

> [!abstract] Em uma frase
> O texto das páginas escaneadas é reconhecido **localmente**, com o **Tesseract 5.4.0 em português**, em dois perfis medidos — 150 dpi para texto corrido e 400 dpi para tabela —, com versão fixa na imagem e equivalência medida entre máquinas; e a pirâmide salarial lida por OCR **nunca** entra sem revisão humana.

## Problema

Editais escaneados são comuns — e invisíveis sem OCR. O maior arquivo de São Lourenço do Sul/RS tinha 44 páginas, 10,6 MB e **44 caracteres** de texto extraível; nele estava uma justificativa de preço que não existia em nenhum outro documento.

## Opções

| Opção | Avaliação |
|---|---|
| OCR em nuvem | envia o documento a terceiro; abre discussão de conformidade que o OCR local não tem |
| modelo de visão para ler tabela | não determinístico; reintroduz o risco que o verificador elimina |
| outros motores abertos | não testados; o Tesseract com o modelo `por` já estava validado |
| um DPI só para tudo | medido: 150 é melhor para texto, 400 para tabela |
| **Tesseract local, dois perfis, pirâmide sempre revisada** | medido contra verdade conhecida |

## Como foi medido

O edital **digital** de São Lourenço do Sul (27 páginas, texto conhecido) foi rasterizado em imagem — simulando a digitalização — e submetido ao OCR; a saída foi comparada com o texto verdadeiro. A acurácia é **medida**, não estimada. (A primeira medição usou `difflib` com o `autojunk` ligado, que trata letras comuns como ruído e derrubou a similaridade para ~4% em páginas **corretas**; corrigido, e registrado porque teria reprovado o OCR por engano.)

| Texto corrido | Similaridade de palavra | Segundos por página |
|---|---|---|
| **português, 150 dpi, psm 3** | **92,97%** | **2,2** |
| português, 300 dpi, psm 3 | 92,96% | 3,0 |
| português, 400 dpi, psm 3 | 92,41% | 3,5 |
| inglês, 300 dpi, psm 3 | 86,58% | 2,2 |

- DPI acima de 150 não melhora texto corrido; o modelo em português vale 6,4 pontos sobre o inglês.
- Os campos do questionário saíram **exatos** do documento inteiro: o valor `R$ 1.900.000,00`, as datas, o CNPJ, a modalidade, o critério.

| Pirâmide (valores monetários das tabelas) | Recuperados | **Errados** | Recall |
|---|---|---|---|
| psm 3, 150 dpi | 100 | **3** | 68,5% |
| psm 6, 150 dpi | 115 | 1 | 78,8% |
| **psm 4, 400 dpi** | **115** | **0** | **78,8%** |

> [!danger] O OCR não chega perto de 100% na pirâmide — e às vezes inventa
> O melhor perfil recupera 78,8% dos valores. Pior: uma configuração leu `1.000,07` onde o documento diz `1.000,01` — corrupção silenciosa. E o Tesseract 5.4.0 chegou a ler o **fio vertical da tabela** como o algarismo `1`: dígito criado do nada, que a guarda numérica da ancoragem não pega, porque o erro já está na página. **Valor faltando o verificador sinaliza; valor errado entraria no lance.**

## Escolha

1. **Motor:** Tesseract 5.4.0 + Leptonica 1.84.1, **compilados na imagem** do worker; modelo `por` com SHA-256 conferido no build.
2. **Gatilho:** página com menos de 120 caracteres de texto nativo → OCR.
3. **Texto corrido:** `por`, 150 dpi, `psm 3`. **Tabela:** `por`, 400 dpi, `psm 4` — otimizado por **zero valor errado**, não por recall.
4. **Tarja de assinatura digital removida** antes de ler tabela.
5. **Documento digital primeiro:** se a mesma informação existe com texto nativo, usa-se esse.
6. **Pirâmide vinda de OCR nunca entra sozinha:** vai para revisão humana, com a marca.
7. **OCR forçado e rotação** por arquivo, marcáveis pelo operador (camada de texto cortada, carimbo sobre imagem, página de cabeça para baixo).

## Versão fixa e equivalência medida

Outro OCR gera outra leitura — e as medições valem para uma versão. Por isso:

- o `/health` do worker responde 503 se a versão ou o idioma não baterem, e o [[W00 Saúde]] confere de hora em hora;
- a versão do OCR faz parte da identidade da leitura: outra versão gera leitura nova, lado a lado, nunca por cima ([[W22 Ler]]);
- **a equivalência entre máquinas foi medida**, não suposta: o Tesseract compilado não reproduz byte a byte o da máquina das primeiras medições (similaridade mínima por página 0,9922), então **a imagem é a referência**; em 28/09/2026, a produção na AWS reproduziu a imagem página por página — mesma similaridade, mesma contagem de caracteres, mesmo binário e mesmo modelo (`docs/ocr-equivalencia-*.json`).

## O que custa

- Dois perfis aumentam a complexidade do pipeline.
- A pirâmide de documento escaneado continua exigindo humano — não é automação completa.
- Em produção, um job de OCR por vez: uma licitação grande e escaneada demora mais ([[Escalabilidade]]).

## Quanto OCR o acervo exige

12,7% dos arquivos e 8,6% das páginas (324 PDFs de 108 licitações); uma licitação em cada sete tem ao menos um arquivo escaneado — geralmente um anexo grande, raramente o edital principal ([[OCR]]).

## O que reabriria a decisão

Um motor de OCR que meça **zero valor errado** com recall maior na pirâmide, na mesma medição contra verdade conhecida.

## Relacionadas

[[MOC Decisões]] · [[OCR]] · [[W22 Ler]] · [[Worker — visão geral e jobs]] · [[Verificador determinístico]] · [[Escalabilidade]]
