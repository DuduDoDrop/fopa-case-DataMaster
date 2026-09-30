---
tipo: moc
familia: decisoes
status: verificado
atualizado: 2026-09-28
tags: [moc, decisao]
---

# MOC Decisões

> [!abstract] Em uma frase
> As 24 decisões de arquitetura e produto da solução (ADRs), cada uma no formato **problema → opções → o que foi medido → escolha → o que custa → onde vive em produção → o que a reabriria**, mais as decisões de implementação da construção.

## Papel na solução

Uma decisão sem o motivo vira dogma; uma decisão sem medição vira opinião. Aqui cada escolha diz por que foi feita, o que foi medido para sustentá-la, o que ela custa e qual fato novo justificaria reabri-la — para que ninguém precise refazer a discussão sem informação nova. Quando uma decisão foi superada, ela aparece como "era X, virou Y porque Z".

## As decisões

| ADR | Decisão | Família |
|---|---|---|
| [[ADR-001 Escopo somente setor público]] | só folha do setor público | negócio |
| [[ADR-002 PNCP como fonte primária]] | o PNCP é a fonte de tudo | dados |
| [[ADR-003 Classificação por regras antes de IA]] | escopo por regra; IA só como sinal | IA |
| [[ADR-004 Evidência obrigatória]] | arquivo, página e trecho em toda resposta, conferidos sem IA | IA |
| [[ADR-005 Info é arquivo mais página física]] | a evidência é arquivo + página física | dados |
| [[ADR-006 Documento vigente é o de maior sequencial]] | precedência documental, com retificações por cima | dados |
| [[ADR-007 Cobertura de municípios pequenos]] | cobertura declarada; diário oficial avaliado e não construído | negócio |
| [[ADR-008 OCR — stack, configuração e limites]] | Tesseract local, dois perfis, pirâmide sempre revisada | leitura |
| [[ADR-009 Modelo de extração]] | extrator Claude Opus, escolhido por medição | IA |
| [[ADR-010 RAG vs contexto completo]] | híbrido por tamanho, BM25 por página; sem embeddings nem fine-tuning | IA |
| [[ADR-011 Uma regra precisa saber quando falhou em ler]] | silêncio nunca é conferência | IA |
| [[ADR-012 Segundo provedor de modelo]] | Claude principal, OpenAI plano B | IA |
| [[ADR-013 Identidade de licitação é o número de controle]] | o número de controle é a identidade | dados |
| [[ADR-014 Extração por agente, sem API]] | acervo extraído fora da API, pelo mesmo verificador | IA |
| [[ADR-015 Acervo só de 2026 e só compra de folha]] | recorte de 2026 e escopo de compra de folha na fila paga | negócio |
| [[ADR-016 O produto manda só dois e-mails]] | licitação nova e extração pedida | produto |
| [[ADR-017 O arquivo que não é PDF vira PDF]] | conversão para PDF no download | leitura |
| [[ADR-018 Licitação de folha pega todos os arquivos]] | sem teto de download para folha | leitura |
| [[ADR-019 O site mostra só o que a IA confirma como folha]] | filtro sempre aplicado nas telas | produto |
| [[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]] | esforço fixo `medium`; Opus 5.5 | IA |
| [[ADR-021 Quem vê o quê — usuário, operador, admin e admin supremo]] | ver é amplo, agir é restrito | segurança |
| [[ADR-022 Produção na AWS, em São Paulo, numa máquina pequena]] | EC2 t3.small e S3 em São Paulo | infraestrutura |
| [[ADR-023 O histórico e os contratos do PNCP todo dia]] | histórico e contratos às 04:30 | dados |
| [[ADR-024 Best-of-N e documentos antes das perguntas]] | cache pela ordem do prompt; reforço só do que falha | IA |

E as escolhas de implementação: [[Decisões de construção da v3]].

## As decisões que nasceram de medição

Várias decisões **não existiam** no desenho inicial e surgiram de fatos medidos em documentos reais: a evidência como arquivo + página (vários arquivos por licitação), o documento vigente (editais ativos que se contradizem), a cobertura declarada (a dispensa do art. 176), a guarda numérica da ancoragem (citação com algarismo trocado aprovada), a conversão de formatos (licitações inteiras em RTF) e o fim do teto de download para folha (o processo de 773 páginas). É o efeito esperado de testar contra a realidade antes de escrever o código.

## Relacionadas

[[Home]] · [[MOC IA]] · [[MOC Avaliação]] · [[Arquitetura]] · [[Resultados medidos]]
