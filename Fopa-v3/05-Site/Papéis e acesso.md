---
tipo: referencia
familia: site
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - api/site.py
  - db/046_admin_supremo.sql
  - db/048_site_remove_usuario.sql
  - web/src/componentes/Restrita.tsx
tags: [site, acesso, seguranca, papeis]
---

# Papéis e acesso

> [!abstract] Em uma frase
> Quem entra pelo Google vira **usuário** (vê as licitações, as análises e revisa respostas); o **administrador** também opera o sistema (execuções, e-mails, saúde, configuração e os botões que chamam a automação ou gastam API); e só o **administrador supremo** dá e tira acesso.

## Papel na solução

O produto lida com dinheiro (o botão de extração chama API paga) e com decisões de negócio (revisões e rótulos). O controle de acesso garante que **ver** é amplo e **agir** é restrito, e que cada ação fica registrada com quem a fez ([[ADR-021 Quem vê o quê — usuário, operador, admin e admin supremo]]).

## Os papéis

| Papel | Como se obtém | Nível |
|---|---|---|
| **Usuário** (`leitor`) | automático: todo primeiro login com Google | 1 |
| **Operador** (`operador`) | atribuído pelo supremo; hoje não abre nada além do usuário | 2 |
| **Administrador** (`admin`) | atribuído pelo supremo | 3 |
| **Administrador supremo** | marca `supremo` no cadastro (o dono do produto); o site não consegue alterá-la | admin + gestão de acesso |

## O que cada papel vê e faz

| Recurso | Usuário | Admin | Supremo |
|---|---|---|---|
| [[Página Painel\|Painel]], [[Página Histórico\|Histórico]], [[Página Analytics de Mercado\|Analytics]], [[Página Analytics Histórico FOPA\|Analytics Histórico FOPA]] | ✅ | ✅ | ✅ |
| [[Página Detalhe da licitação\|Detalhe]], [[Página Relatório\|Relatório]] e o PDF na página citada | ✅ | ✅ | ✅ |
| [[Página Revisão\|Revisão]] de **respostas** (ver e decidir) | ✅ | ✅ | ✅ |
| Revisão de **escopo** (rótulos "é/não é folha") | — | ✅ | ✅ |
| [[Página Governança\|Governança]] (governança e compliance) | ✅ | ✅ | ✅ |
| Botões **Reverificar**, **Processar**, **Extrair com IA** | — | ✅ | ✅ |
| [[Página Execuções\|Execuções]], [[Página E-mails\|E-mails]], [[Página Saúde\|Saúde]], [[Página Admin\|Admin]] | — | ✅ | ✅ |
| Configuração, orçamento, termos, "Verificar agora", processar em lote, importar respostas, reservar para demonstração | — | ✅ | ✅ |
| **Usuários:** ver a lista | — | ✅ | ✅ |
| **Usuários:** dar papel, bloquear, desbloquear, remover | — | — | ✅ |

- **Bloquear:** a pessoa não entra mais (403 "Acesso não liberado").
- **Remover:** apaga o cadastro e as sessões; se ela entrar de novo, volta como usuário.
- O sistema impede que o último administrador ativo perca o papel.

## Como a regra é aplicada

1. **No servidor (a que vale):** cada rota da API declara o papel mínimo (`leitor`, `revisor` = usuário, `admin`, `so_supremo`); sem sessão válida, 401; sem papel, 403 com a mensagem "ação exige papel …" ([[API do site — endpoints]]).
2. **No site:** as páginas restritas são envolvidas por um componente que mostra "restrito" para quem não tem o papel, e os botões de ação só aparecem para administradores — conveniência, não segurança.
3. **No banco:** o site entra com o papel `api_rw`, que só grava decisões humanas; ele não tem como mudar estado de licitação nem publicar ([[Controle de acesso e segredos]]).

## Relacionadas

[[MOC Site]] · [[Login com Google]] · [[Página Admin]] · [[API do site — endpoints]] · [[Controle de acesso e segredos]] · [[Privacidade e LGPD]] · [[ADR-021 Quem vê o quê — usuário, operador, admin e admin supremo]]
