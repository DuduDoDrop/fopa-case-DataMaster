# Textos do site — guia de estilo

Pedido de 28/09/2026: todos os textos do site concisos, diretos, bem pontuados e em linguagem formal, porque a
entrega é executiva e corporativa, para instituições financeiras.

Este guia vale para todo texto que aparece na tela do site: títulos, rótulos, botões, avisos, textos de ajuda,
estados vazios e de carregamento, colunas de tabela, `title`, `aria-label`, `placeholder` e as mensagens da API que
chegam à tela. A guarda automática `web/src/__testes__/textos.test.ts` barra o jargão interno e as marcas de
informalidade nos arquivos já revisados; o tom e a concisão se conferem lendo, por este guia.

## Regras

1. **Registro formal e impessoal.** Sem primeira pessoa, sem "você", sem "a gente", sem gíria. Instruções no infinitivo
   ou no imperativo formal ("Selecione o período", "Informe o nome da instituição").
2. **Conciso.** Uma ideia por frase; até ~20 palavras por frase; textos de ajuda com no máximo duas frases. Corte o que
   explica a implementação.
3. **Sem jargão interno na tela.** Proibido nas páginas de negócio: nomes de fluxos (W01…W90), `n8n`, `Postgres`,
   `ADR-xxx`, `v2`, `Claude Code`, rotas (`/api/...`), nomes de variáveis e de pessoas. Nas páginas de operação (Admin,
   Execuções, E-mails, Saúde), termo técnico só quando indispensável e depois do termo de negócio: "Processamento
   (n8n)".
4. **Pontuação.** Frase completa termina em ponto. Rótulo, título, botão, item de lista e coluna de tabela não terminam
   em ponto. Sem cadeias de travessões e de dois-pontos: divida em frases. Dois-pontos só para introduzir valor ou
   lista. Reticências (…) só em estado de carregamento. Sem ponto de exclamação.
5. **Maiúsculas.** Título e rótulo com inicial maiúscula e o resto minúsculo (exceto nomes próprios e siglas): "Gastos
   com IA", "Documentos do edital".
6. **Números e datas no padrão brasileiro.** "R$ 1.234,56", "12.345 licitações", "28/09/2026", "Lei nº 14.133/2021,
   art. 54".
7. **Mensagens de erro:** o que aconteceu + o que fazer. "Não foi possível carregar a lista. Tente novamente em
   instantes."
8. **Estados vazios:** fato, sem desculpa: "Nenhuma licitação encontrada para os filtros selecionados."
9. **Carregamento:** "Carregando…", "Verificando a sessão…", "Redirecionando para o login…".
10. **Glossário:** *licitação* (o processo) × *edital* (o documento); *instituição financeira* em títulos e textos
    (*banco* só em rótulo curto de filtro); *extração* (não "rodada"); *revisão humana* (não "olho humano"); *serviço
    pago* (não "API paga"); *prazo final* (não "fim do prazo").

## Glossário

| Use | Não use | Observação |
|---|---|---|
| licitação | edital (para o processo) | a licitação é o processo; o edital é o documento |
| edital | licitação (para o documento) | "Documentos do edital", "Abrir o edital no PNCP" |
| instituição financeira | banco (em títulos e textos) | *banco* só em rótulo curto de filtro |
| extração | rodada | "Extrair com IA", "extração vigente" |
| revisão humana | olho humano | "Itens que exigem revisão humana" |
| serviço pago | API paga | "provedor selecionado (serviço pago)" |
| prazo final | fim do prazo | "estende o prazo final em N dias" |

## Exemplos reais (antes → depois)

| Antes (site hoje) | Depois |
|---|---|
| O que precisa de olho humano. A decisão fica registrada com nome e data numa camada própria… | Itens que exigem revisão humana. Cada decisão é registrada com responsável e data. |
| Acompanhando o processamento: a página se atualiza sozinha enquanto a licitação anda (baixar, ler, extrair, verificar, publicar). | Processamento em andamento. A página é atualizada automaticamente a cada etapa: download, leitura, extração, verificação e publicação. |
| Chama a API paga do provedor escolhido para só esta licitação: baixa e lê (se preciso), extrai, verifica e publica. | Executa a extração desta licitação com o provedor selecionado (serviço pago), incluindo download e leitura, quando necessários, verificação e publicação. |
| a IA acha que não é folha | Classificadas pela IA como fora do escopo |
| Dados vivos do Postgres da FOPA. Fonte dos documentos: PNCP — dados abertos, Lei 14.133/2021 art. 54. Nenhum dado pessoal é armazenado. | Dados atualizados continuamente. Fonte: Portal Nacional de Contratações Públicas (PNCP), dados abertos (Lei nº 14.133/2021, art. 54). Nenhum dado pessoal é armazenado. |
| A API ainda não expõe /api/rotulos-escopo: o rótulo humano de escopo entra quando a rota existir. Até lá, o escopo é só o da regra (ADR-003). | A rotulagem manual de escopo ainda não está disponível. O escopo segue as regras de classificação. |
| Fila do W50: pendentes, enviados e falhas, com o corpo exatamente como saiu. | Fila de envio de e-mails: pendentes, enviados e com falha, com o conteúdo enviado. |
| Cada rodada do n8n (e dos scripts da v2 importados), com duração, custo e o que produziu. | Execuções do processamento, com duração, custo e resultado. |
| … e empurra o fim do prazo para daqui a N dias (1 a 60), pela API, sem editar o banco à mão. | … e estende o prazo final em N dias (de 1 a 60). |
| carregando… / conferindo a sessão… / indo para o login… / aguardando o n8n… | Carregando… / Verificando a sessão… / Redirecionando para o login… / Aguardando o processamento… |
| Abrindo o RELATORIO… Se não abrir, | Abrindo o relatório… Caso não abra, |
| sessão ausente: entre em /login | Sessão não encontrada. Faça login para continuar. |
| ação exige papel '%s' (você é '%s') | Esta ação requer o perfil %s. Seu perfil atual é %s. |

## O que não muda

- Conteúdo que vem do edital ou do modelo (respostas, trechos literais, nomes de arquivos), nomes de modelos (Claude
  Opus 5.5, GPT-6 Luna…), siglas oficiais (PNCP, CNPJ, UF, CPF), números e valores.
- Os conceitos do produto: veredito (Aprovada, Revisar, Reprovada), ancoragem, Best-of-N, extração, verificação.
- O cabeçalho segue em MAIÚSCULAS, com o e-mail em minúsculas (commit `9305cdb`).
- Só texto: nenhuma lógica, rota, nome de campo da API, chave de URL ou estrutura de componente muda por causa deste
  guia. Testes que fixam texto passam ao texto novo, com a mesma consulta, nunca afrouxados.
