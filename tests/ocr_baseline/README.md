# Baseline de OCR — o host das medições, versionado

## O que é

Seis páginas do edital **digitalizado** de São Lourenço do Sul/RS
(`01 - Edital original (digitalizado, 44p).pdf`, páginas físicas 1 a 6),
rasterizadas em PNG a 150 dpi, e o texto que o **Tesseract 5.4.0.20240606 do
host** extraiu de cada uma com o `por.traineddata` do repositório. É o mesmo
edital, as mesmas 6 páginas e a mesma quantidade de caracteres (13.375) da
comparação registrada em `BACKLOG.md:427-463`, em que a 5.3.0 da imagem
`python:3.12-slim-bookworm` deu 0 de 6 páginas idênticas e leu o fio vertical
da tabela da pirâmide salarial como o algarismo `1` (`p02.host.txt`, linha
`De R$ 9.000,00 até R$ 10.000,00 00 R$ -1 R$ -`).

| arquivo | o que é |
|---|---|
| `sao-lourenco-scan-6p.pdf` | as 6 páginas copiadas do PDF de 44 (1,1 MB; o original tem 10,6 MB e fica fora do git). Rasteriza pixel a pixel igual ao original — `test_png_e_a_rasterizacao_do_pdf_a_150dpi` confere |
| `pNN.png` | página física NN a 150 dpi, RGB, exatamente o que `fopa.ocr._renderizar` entrega ao Tesseract |
| `pNN.host.txt` | saída do `pytesseract.image_to_string` do host, byte a byte (`\n`, UTF-8; o `.gitattributes` impede o git de trocar o fim de linha) |
| `manifest.json` | sha256 do PDF, do tessdata e de cada PNG/txt; versão exata do Tesseract; `lang/psm/oem` usados; de onde vieram as páginas |
| `gerar.py` | regenera tudo a partir do PDF |
| `medir.py` | roda o OCR desta máquina nas 6 PNG e compara com o host |
| `test_medir.py` | prova que a baseline se reproduz no próprio host e que o manifesto bate com os arquivos |

## Por que 150 dpi, psm 3, oem 3

Porque é o `PERFIL_TEXTO` de `scripts/fopa/ocr.py` (RN-20): o perfil que
`ler_documento` usa em produção para texto corrido e que produziu todos os
números de OCR do projeto (92,97 % de similaridade de palavra no grid do
`03_ocr_benchmark.py`). Uma baseline em outro dpi ou psm mediria outra coisa.
`medir.py` e `gerar.py` **importam** o perfil de `fopa.ocr` em vez de copiar
os números — se o pipeline mudar, o teste `test_manifest_configuracao_e_a_do_pipeline`
acusa que o manifesto ficou para trás.

## Como medir

```
python tests/ocr_baseline/medir.py --saida docs/ocr-equivalencia-<sha>.json [--tesseract /usr/local/bin/tesseract]
```

`<sha>` é substituído pelos 12 primeiros hex do sha256 do binário usado. O
binário vem, nesta ordem, de `--tesseract`, `FOPA_TESSERACT`, o padrão do
`fopa.ocr` (`C:\Program Files\Tesseract-OCR\tesseract.exe`) ou o `tesseract`
do `PATH`. O JSON traz `tesseract`, `tessdata_sha256`, `paginas[{pagina,
identica, similaridade, chars_host, chars_aqui}]`, `identicas`,
`similaridade_min` e `plataforma`; o resumo sai no terminal.

**O script nunca falha por diferença.** É medição, não portão: o build da
imagem Docker o roda e registra o resultado. Falha só quando não há Tesseract.

## Como regenerar

```
python tests/ocr_baseline/gerar.py
```

Regenera PNG, textos e manifesto a partir do `sao-lourenco-scan-6p.pdf`
versionado. Para escolher outras páginas, aponte para o PDF completo:

```
python tests/ocr_baseline/gerar.py --origem "amostras/Concorrencia - Eletronica - Sao Lourenco do Sul-RS/01 - Edital original (digitalizado, 44p).pdf" --paginas 1 2 3 4 5 6
```

Regenerar **troca a referência** para o Tesseract da máquina em que rodou.
Só faça isso de propósito (ver abaixo) e diga no commit qual máquina virou a
referência. Depois rode `python -m pytest tests/ocr_baseline`.

## Se a imagem não reproduzir o host

A hipótese "mesma 5.4.0, mesmo texto" é só hipótese: o host é um build MSVC
com AVX512 e a imagem compila no Linux; a mesma minor não garante saída igual
(Plano v3, seção 6 "Imagem" e seção 12). Se `medir.py` dentro da imagem der
menos de 6/6 idênticas, vale a decisão já tomada na ADR-008 e no BACKLOG:

**a imagem é a referência.** Os números de OCR do projeto passam a ser os que
a imagem produz, e não os do host:

1. rodar `gerar.py` **dentro da imagem** e commitar os novos `pNN.host.txt` e
   `manifest.json` (o `tesseract_host` e a `plataforma` do manifesto passam a
   dizer Linux);
2. guardar o `docs/ocr-equivalencia-<sha>.json` que mostrou a diferença — é a
   evidência de por que a referência mudou;
3. republicar os números de OCR (ADR-008, `Regras de negócio.md` RN-21) a
   partir da imagem, e marcar em `leituras.versao_ocr` que a leitura veio dela.

O que **não** fazer: afrouxar o teste para aceitar "quase igual". A guarda
numérica da ADR-004 reprova qualquer algarismo que não esteja na página
citada, e um `|` que vira `1` numa versão e não na outra é exatamente o caso
em que "quase igual" muda um veredito.
