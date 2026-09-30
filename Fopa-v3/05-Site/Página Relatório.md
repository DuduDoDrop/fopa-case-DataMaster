---
tipo: pagina
familia: site
rota: "/licitacao/:slug/relatorio"
papel_minimo: usuario
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - web/src/paginas/Relatorio.tsx
  - api/render.py
  - scripts/fopa/pagina.py
tags: [site, pagina, relatorio]
---

# Página Relatório

> [!abstract] Em uma frase
> O **relatório HTML** de uma extração verificada, gerado no momento da publicação e guardado junto dela: a mesma prova do detalhe (quadros, alertas, condições, as 17 respostas com veredito, evidência e link para a página do PDF) num documento autossuficiente, em tema claro, pronto para abrir de um e-mail.

## Papel na solução

É o **artefato de entrega** de cada extração: o e-mail de extração aponta para ele, e ele sobrevive às mudanças de tela do site, porque é gerado uma vez por verificação e guardado no armazenamento (`html/{slug}/{verificacao_id}.html`, [[W24 Verificar e publicar]] — passo "POST /render").

![[site-relatorio.jpg]]

O print é o relatório vigente de Itapecuru Mirim/MA: a extração do GPT-6 Luna (16/16 ancoradas, R$ 0,20), com as condições da leitura em modo degradado, por ter rodado no provedor secundário.

## O que mostra

- título (modalidade e local), arquivos, páginas, modo, modelo e data de geração; o link de origem no PNCP;
- os quadros da verificação (ancoragem verificada, aprovadas, revisar, reprovadas, críticas aprovadas, custo);
- "Como conferir", alertas e condições da execução;
- o questionário com as 17 respostas, a evidência e o link "arquivo · p. N" para o PDF.

## Como é servido

`GET /api/licitacoes/{slug}/relatorio` devolve o HTML da **verificação vigente** (o site o abre em `/licitacao/{slug}/relatorio`). Exige sessão, como tudo no site. O detalhe da licitação não tem mais botão para ele — já mostra as mesmas respostas —, mas o link continua no e-mail de extração.

## Relacionadas

[[MOC Site]] · [[Página Detalhe da licitação]] · [[W24 Verificar e publicar]] · [[E-mails do produto]] · [[Armazenamento de arquivos (S3)]]
