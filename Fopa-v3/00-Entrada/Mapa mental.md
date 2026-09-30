---
tipo: referencia
familia: entrada
status: verificado
atualizado: 2026-09-28
tags: [entrada, mapa-mental, visao-geral]
---

# Mapa mental

> [!abstract] Em uma frase
> A solução inteira numa figura: do problema de negócio ao resultado no site, passando pela descoberta, a fila, a leitura, a extração com IA, a verificação sem IA, a revisão humana e a análise de mercado — com a operação, a infraestrutura, a segurança e a avaliação que sustentam tudo.

## Papel na solução

É o mapa de navegação: cada ramo corresponde a uma família de notas. A versão navegável, em que cada caixa abre a nota correspondente, é o canvas [[Mapa da solução.canvas|Mapa da solução]].

## O fluxo inteiro

```mermaid
mindmap
  root((FOPA))
    Negócio
      Dor informada pelo banco
        R$ 1,05 bi por ano em compra de folhas
        PDF por fornecedor em D+3, a R$ 100 mil por ano
        2 dos 5 dias para analisar
        26 pessoas lendo documentos
      17 perguntas que decidem o lance
      Ganho: a manhã da descoberta em vez de D+3
    Descobrir
      W01 às 06:00 em dias úteis
      Busca no PNCP com recorte de 2026
      Regra de escopo antes de IA
      Jev como segundo sinal
      E-mail licitação nova
    Fila
      W10 de 06:00 a 07:50
      Reivindicar com trava de linha
      Lease, backoff e disjuntor
    Baixar e ler
      W20 orquestra por estado
      W21 baixa todos os arquivos
      Não PDF vira PDF
      W22 lê com OCR local
      Texto congelado por página
      Texto escondido detectado
    Extrair com IA
      W23 é o único que fala com modelo
      Claude Opus 5.5 por padrão
      17 perguntas em 3 lotes
      Contexto completo ou RAG BM25
      Documento em cache
      Best-of-N nas que falham
      Teto de gasto no banco
    Verificar sem IA
      W24 verifica e publica
      Trecho na página citada
      Guarda numérica
      Regras de pirâmide, totais e objeto
      Cruzamento com o PNCP
      Não localizado vai para revisão
    Publicar e avisar
      Relatório com link para a página
      E-mail extração pronta
      Site com Painel e Detalhe
    Revisar
      Fila de revisão com motivo
      Jev: o trecho sustenta?
      Rótulo humano de escopo
    Analisar o mercado
      W41 às 04:30
      Histórico e contratos do PNCP
      Analytics de Mercado
      Analytics Histórico FOPA
    Operar
      W00 saúde de hora em hora
      W40 prioridades às 07:00
      W50 fila de e-mails a cada minuto
      W70 retificações aos domingos
      W90 erro
      W11 ações do site
      W30 reverificar a custo zero
    Infraestrutura
      AWS em São Paulo
      Docker Compose
      Postgres 16 e S3
      Caddy com HTTPS
      Backup diário e cópia no S3
    Segurança e ética
      Papéis de acesso
      Chave do modelo só no n8n
      LGPD e dados no Brasil
      Defesas contra injeção
      Legalidade da coleta
    Avaliação
      Gabaritos humanos
      Harness e métricas
      Comparação de modelos
      Antes e depois da v3.1
```

## Onde cada ramo está descrito

| Ramo | Notas |
|---|---|
| Negócio | [[MOC Negócio]] · [[Problema de negócio]] · [[Questionário — as 17 perguntas]] · [[Ganho para o negócio]] |
| Descobrir | [[W01 Descoberta]] · [[Regras antes de IA]] · [[Jev — score de escopo e sustentação]] |
| Fila | [[W10 Fila]] · [[Funções e views do banco]] |
| Baixar e ler | [[W20 Processar uma licitação]] · [[W21 Baixar]] · [[Conversão de formatos]] · [[W22 Ler]] · [[OCR]] |
| Extrair com IA | [[W23 Extrair]] · [[Modelos e provedores]] · [[Prompt do extrator]] · [[RAG com BM25]] · [[Cache de prompt e ordem do prompt]] · [[Best-of-N]] · [[Custo por edital]] |
| Verificar sem IA | [[W24 Verificar e publicar]] · [[Verificador determinístico]] |
| Publicar e avisar | [[Página Relatório]] · [[E-mails do produto]] · [[MOC Site]] |
| Revisar | [[Página Revisão]] · [[Página Detalhe da licitação]] |
| Analisar o mercado | [[W41 Histórico do PNCP]] · [[Página Analytics de Mercado]] · [[Página Analytics Histórico FOPA]] |
| Operar | [[MOC Fluxos n8n]] · [[Horários e agendamentos]] · [[Saúde e observabilidade]] |
| Infraestrutura | [[MOC Infra]] |
| Segurança e ética | [[MOC Segurança e Ética]] · [[Página Governança]] |
| Avaliação | [[MOC Avaliação]] |

## Relacionadas

[[Home]] · [[Visão geral da solução]] · [[Arquitetura]] · [[Ciclo de vida de uma licitação]]
