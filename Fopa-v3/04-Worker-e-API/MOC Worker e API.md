---
tipo: moc
familia: worker-e-api
status: verificado
atualizado: 2026-09-28
tags: [moc, worker, api]
---

# MOC Worker e API

> [!abstract] Em uma frase
> Os dois serviços Python da solução, construídos da mesma imagem: o **worker**, que processa (documentos, OCR, prompt, verificação, relatório, histórico), e a **API do site**, que autentica, lê o banco e aciona a automação.

## Papel na solução

O n8n orquestra, o worker executa, a API mostra ([[Arquitetura]]). Os dois compartilham o núcleo `scripts/fopa` — o mesmo código que produziu as medições do projeto —, e nenhum deles tem a chave do modelo.

## As notas

| Nota | Assunto |
|---|---|
| [[Worker — visão geral e jobs]] | o que o worker faz, como é construído, jobs assíncronos e filas |
| [[Endpoints do worker]] | cada rota interna, entrada, saída e quem chama |
| [[API do site — endpoints]] | as 46 rotas do site, com o papel exigido |
| [[OCR]] | Tesseract 5.4.0, gatilho, perfis medidos, versão fixa |
| [[Conversão de formatos]] | o que não é PDF vira PDF |

## Relacionadas

[[Home]] · [[MOC Fluxos n8n]] · [[MOC Site]] · [[MOC IA]] · [[MOC Dados]] · [[Containers e serviços]]
