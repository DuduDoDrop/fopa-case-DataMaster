# tests/ — utilitários de teste e a linha de base do OCR

| Arquivo | O que é |
|---|---|
| `pg_efemero.py` | sobe um `postgres:16-alpine` em container, numa porta sorteada em 127.0.0.1, para as suítes de banco — nunca a porta da instalação local |
| `ocr_baseline/` | seis páginas digitalizadas de um edital real e o texto de referência do Tesseract 5.4.0, com o SHA-256 de cada arquivo; `medir.py` compara o OCR de uma máquina com a referência e `gerar.py` a refaz. Veja o [README da pasta](ocr_baseline/README.md) |

As suítes de cada componente ficam junto do código: `api/tests`, `db/tests`, `migracao/tests`, `docker/tests`, `n8n/tests`, `ci/tests` e os testes do site em `web/src`.

Documentação: [Testes e CI](<../Fopa-v3/14-Reproducao/Testes e CI.md>) · [OCR](<../Fopa-v3/04-Worker-e-API/OCR.md>)
