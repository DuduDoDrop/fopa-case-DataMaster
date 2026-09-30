---
tipo: pagina
familia: site
rota: "/governanca"
papel_minimo: usuario
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - web/src/paginas/Governanca.tsx
  - web/src/App.tsx
  - web/src/componentes/Layout.tsx
tags: [site, pagina, governanca, compliance, lgpd]
---

# Página Governança

> [!abstract] Em uma frase
> A tela **Governança e compliance** reúne, em linguagem executiva, os princípios, os controles e os fundamentos legais que orientam o uso de IA na solução: supervisão humana, rastreabilidade, normas, proteção de dados, coleta de dados públicos, segurança, continuidade e o que cabe à instituição financeira na adoção.

## Papel na solução

É a face, no site, das famílias [[MOC Segurança e Ética|Segurança e Ética]] e [[MOC Legal|Legal]]: quem avalia a ferramenta pelo lado de compliance encontra num só lugar o que o sistema faz para ser auditável e legítimo, com o dispositivo de cada norma. Cada frase da tela sai das notas conferidas dessas famílias e descreve um controle em produção; nada promete o que o sistema não faz.

![[site-governanca.jpg]]

## Quem vê

Todo usuário logado: o item **Governança** fica no menu logo depois de **Revisão**, para todos os papéis ([[Papéis e acesso]]).

## O que a tela mostra

Oito blocos, cada um com o termo em inglês usado no mercado como rótulo, acima do título em português.

| Rótulo | Título | Conteúdo | Notas de origem |
|---|---|---|---|
| Human-in-the-loop | Supervisão humana | a IA apoia e a decisão é humana; evidência em toda resposta; verificador sem IA; o que não confere vai para revisão, com responsável e data; link para a [[Página Revisão]] | [[Premissas éticas e matriz de cenários]], [[Verificador determinístico]] |
| Accountability | Rastreabilidade e prestação de contas | modelo e data de cada resposta; origem, data e SHA-256 de cada documento; execuções com duração, custo e resultado; registros da automação que não são sobrescritos | [[Controles de consistência]], [[Página Execuções]] |
| Legal & regulatory compliance | Fundamentos legais e regulatórios | tabela com sete normas e o dispositivo de cada uma: Lei 14.133/2021 (arts. 54 e 174), LAI (art. 8º, § 3º, III), LGPD (arts. 6º e 7º, IX), Lei 13.303/2016, TCU (Acórdãos 3.042/2008 e 1.940/2015) e tribunais de contas estaduais, Resolução CMN 5.058/2022 e Lei 15.252/2025, Lei 14.509/2022 | [[MOC Legal]] |
| Privacy by design · LGPD | Proteção de dados pessoais | só documentos publicados por obrigação legal; perguntas agregadas; do login, só nome e e-mail; dados no Brasil; nada vendido nem usado para treinar modelos; link para a [[Página Privacidade]] | [[Privacidade e LGPD]] |
| Open data | Dados públicos e coleta responsável | só as APIs oficiais do PNCP; identificação em cada pedido; ritmo conservador; coleta mínima; nada contornado | [[Legalidade da automação]] |
| Least privilege | Segurança da informação e gestão de acessos | Google (OAuth 2.0 com OpenID Connect) e sessão de 12 horas; perfis com segregação de funções; HTTPS e portas mínimas; credenciais de IA cifradas | [[Controle de acesso e segredos]], [[Segurança do servidor]] |
| Business continuity · Risk management | Continuidade e gestão de riscos | backup diário com cópia que a aplicação não apaga; restauração testada toda semana; teto diário de gasto; defesa contra instruções nos documentos; saúde a cada hora; cobertura declarada | [[Backup e restauração]], [[Custo por edital]], [[Injeção de prompt e defesas]], [[W00 Saúde]] |
| Shared responsibility | Responsabilidade compartilhada | o que a adoção formal pede da instituição: relatório de impacto (RIPD), parecer do encarregado (DPO), política de retenção, política interna de uso de IA e o processo de revisão humana na área de negócio | [[Premissas éticas e matriz de cenários]], [[Próximos passos]] |

No fim, o aviso: leitura técnica dos fundamentos legais, que não constitui parecer jurídico.

## De onde vêm os dados

A tela é **estática**: o texto está no próprio código da página, sem chamada à API. Mudar um controle do sistema pede mudar esta tela e as notas de origem. A guarda de textos do site (`web/src/__testes__/textos.test.ts`) cobre a página: nenhum jargão interno nem marca de informalidade.

## Relacionadas

[[MOC Site]] · [[MOC Segurança e Ética]] · [[MOC Legal]] · [[Página Revisão]] · [[Página Privacidade]] · [[Papéis e acesso]] · [[Premissas éticas e matriz de cenários]]
