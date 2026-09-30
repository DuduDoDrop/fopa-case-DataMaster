---
tipo: referencia
familia: evolucao
status: verificado
atualizado: 2026-09-28
tags: [evolucao, proximos-passos, roadmap, implantacao]
---

# Próximos passos

> [!abstract] Em uma frase
> A solução está no ar e medida; o que vem depois está em quatro frentes, em ordem de valor: **implantar no banco** (piloto em paralelo com o fornecedor atual e a governança de dados e de IA), **ampliar a prova de qualidade** (mais gabaritos e as hipóteses de custo ainda não medidas), **ampliar a cobertura** onde o PNCP não chega, e **novas capacidades** sobre a mesma base — preço, revisão jurídica e outros tipos de documento.

## Papel na solução

Reúne num lugar só tudo o que as outras notas deixaram explicitamente em aberto, com o motivo e o critério de pronto de cada item. Nada aqui é pré-requisito do que está em produção; tudo aqui parte de algo que já existe.

## 1. Implantar no banco

### 1.1 Piloto em paralelo com o fornecedor atual

A troca de um processo que funciona se decide com dado do próprio banco. A proposta é um **piloto de 4 a 6 semanas** em que a área de análise recebe as licitações pelos dois caminhos e compara:

| Medida | Como | O que decide |
|---|---|---|
| **cobertura** | licitações de folha que a solução encontrou × as que o fornecedor enviou, nos dois sentidos | se o fornecedor pode sair |
| **antecedência** | o dia do aviso da solução × o dia em que o PDF chegou pelo fornecedor | quantos dias úteis a área ganha por licitação ([[Ganho para o negócio]]) |
| **acurácia** | as respostas conferidas pela área × as da solução — cada conferência vira gabarito | quanto a revisão pode confiar no "aprovado" |
| **tempo de análise** | tempo da área por edital, com e sem a solução | o retorno em horas da equipe |
| **custo** | custo por edital extraído, na fatura | o custo variável da operação ([[Custo por edital]]) |

### 1.2 Governança de dados e de IA

Documentos internos que a adoção formal pede e que não são da ferramenta ([[Privacidade e LGPD]], [[Premissas éticas e matriz de cenários]]):

- **relatório de impacto à proteção de dados** (RIPD) e **parecer do encarregado** (DPO);
- **política de retenção** dos documentos e dos registros de uso;
- **política interna de uso de IA com documentos externos**;
- o **processo de revisão humana** na área: quem decide a fila de revisão e em quanto tempo.

### 1.3 Identidade e ambiente do banco

- o **contato institucional** no `User-Agent` das chamadas ao PNCP e o domínio de e-mail do banco ([[Legalidade da automação]], [[E-mails do produto]]);
- o login pelo provedor de identidade corporativo no lugar do Google — a sessão, os papéis e o controle de acesso já são do produto e não mudam ([[Papéis e acesso]]);
- a mesma composição de containers no ambiente de nuvem aprovado pelo banco ([[Escalabilidade]], [[Deploy e atualização]]).

### 1.4 Os dados internos que fecham a conta

| Dado | Para quê |
|---|---|
| custo por hora da equipe que lê os editais | transforma o custo por edital em retorno calculado |
| carteira atual de folhas (órgãos, prazos, retenção) | cruza o mercado do [[Página Analytics de Mercado\|Analytics]] com o que o banco já tem |
| taxa histórica de portabilidade de saída nas folhas conquistadas | quanto uma folha vale de fato depois de comprada ([[Regulação bancária - conta-salário e portabilidade]]) |
| ágio praticado por porte de município | a referência de preço do lance ([[Concorrência e mercado]]) |

## 2. Ampliar a prova de qualidade

| Item | Por quê | Pronto quando |
|---|---|---|
| **mais gabaritos humanos** | hoje são dois; a acurácia só é medível onde existe gabarito, e cada modalidade (dispensa, credenciamento, pregão presencial) pode se comportar diferente | um gabarito por modalidade relevante, medido pelo mesmo harness ([[Gabaritos]]) |
| **`prompt_cache_key` da OpenAI** | a mudança de ordem do prompt não fez a OpenAI ler o cache; a chave de roteamento é a próxima hipótese | custo do segundo provedor remedido antes e depois ([[Cache de prompt e ordem do prompt]]) |
| **tamanho do lote** | o valor 6 é o meio-termo adotado e não foi varrido | varredura com custo e acurácia no harness ([[Prompt do extrator]]) |
| **combinação das perguntas do Jev** | a regressão logística deu AUC de 0,985 em validação cruzada, mas com erros convictos e só 48 negativos para aprender | mais rótulos humanos de escopo e a medição refeita ([[Jev — score de escopo e sustentação]]) |
| **outro motor de OCR** | nenhuma configuração do Tesseract melhorou o recall da pirâmide digitalizada | um motor que meça zero valor errado com recall maior, na mesma medição ([[ADR-008 OCR — stack, configuração e limites]]) |

## 3. Ampliar a cobertura

- **Diários oficiais como canal de descoberta** para municípios dispensados de publicar no PNCP: avaliado e não construído — o teto medido é de 6,4% da faixa dispensada, o diário publica só o extrato e a dispensa termina em 01/04/2027 ([[ADR-007 Cobertura de municípios pequenos]]).
- **Plataformas de pregão** ficam fora: foram mapeadas oito, a maior com 25,7% das sessões, cada uma com termos de uso próprios — e o edital chega pelo PNCP independentemente de onde a sessão acontece ([[ADR-002 PNCP como fonte primária]]).

## 4. Novas capacidades sobre a mesma base

| Capacidade | O que já existe | O que falta |
|---|---|---|
| **analista de preço** | o histórico de compras, contratos e valores do PNCP; o total de servidores e a pirâmide extraídos com evidência | o **ágio** e o **valor por servidor** por região e porte, e a série histórica ([[Concorrência e mercado]]) |
| **revisão jurídica automatizada** | as regras de cessão onerosa e a jurisprudência dos tribunais de contas, organizadas | as checagens de cláusula como regras do verificador — sinal para a revisão, nunca parecer ([[Cessão onerosa da folha - fundamentos]], [[Jurisprudência — tribunais de contas]]) |
| **outros documentos** | o pipeline descobrir → ler com prova → verificar sem IA → revisar | um questionário, uma regra de escopo e as regras do verificador para contratos, aditivos ou outros editais ([[Escalabilidade]]) |

## Relacionadas

[[MOC Evolução]] · [[Linha do tempo da construção]] · [[Desafios enfrentados]] · [[Problema de negócio]] · [[Escalabilidade]] · [[MOC Segurança e Ética]] · [[MOC Legal]]
