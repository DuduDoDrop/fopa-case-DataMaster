---
tipo: moc
familia: dados
status: verificado
atualizado: 2026-09-28
tags: [moc, dados]
---

# MOC Dados

> [!abstract] Em uma frase
> De onde vêm os dados (o PNCP), o que é uma licitação de folha, o caminho de cada dado até a resposta publicada, como o banco guarda tudo sem reescrever o que a máquina produziu, onde ficam os documentos e como o acervo anterior entrou.

## Papel na solução

A resposta publicada vale pelo rastro que ela deixa: o PDF exato, a página exata, o texto exato, o prompt exato, as regras exatas. Esta família descreve esse rastro — fontes, linhagem, esquema, funções, armazenamento — e as particularidades do dado público que a solução precisa tratar.

## As notas

| Nota | O que responde |
|---|---|
| [[Fontes de dados — PNCP]] | os serviços e endpoints do PNCP usados, os termos de busca, a conduta da coleta e as particularidades do dado |
| [[Disponibilidade do PNCP]] | como a fonte falha e como a solução se protege |
| [[Escopo — o que é licitação de folha]] | o conceito, as modalidades, o recorte de tempo e os números |
| [[Pipeline de dados]] | a linhagem: o que cada etapa grava e a impressão digital que prova a procedência |
| [[Modelo de dados]] | as 42 tabelas por assunto, as views, os papéis de acesso e os invariantes |
| [[Funções e views do banco]] | máquina de estados, fila, recorte, escopo, trava da IA, vaga de extração, proteção contra ensaio |
| [[Migrações do banco]] | as 51 migrações e o aplicador que não aceita histórico reescrito |
| [[Armazenamento de arquivos (S3)]] | chaves pelo hash, bucket privado em São Paulo, URL assinada de 10 minutos |
| [[Acervo e migração da v2]] | como o acervo anterior entrou sem reprocessar nada |

## Relacionadas

[[Home]] · [[Arquitetura]] · [[Ciclo de vida de uma licitação]] · [[MOC Fluxos n8n]] · [[MOC Worker e API]] · [[MOC IA]] · [[Privacidade e LGPD]]
