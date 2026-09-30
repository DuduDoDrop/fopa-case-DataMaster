---
tipo: componente
familia: infra
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - docs/DEPLOY.md
  - docker/compose.prod.yml
  - docker/Caddyfile.exemplo
tags: [infra, seguranca, servidor, rede]
---

# Segurança do servidor

> [!abstract] Em uma frase
> A máquina de produção expõe **só 22 (SSH por chave), 80 e 443**; tudo o mais — banco, worker, n8n, API — fica na rede interna dos containers ou no loopback; os segredos são gerados na própria máquina e nunca entram em imagem, repositório ou backup; e cada serviço entra no banco com um papel que só pode o que precisa.

## Papel na solução

A solução guarda documentos com dados pessoais de servidores, chaves de APIs pagas e decisões humanas. A defesa é em camadas: rede, acesso à máquina, segredos, permissões do banco e da aplicação ([[Controle de acesso e segredos]]).

## Rede

| Porta | Quem | Exposição |
|---|---|---|
| 22 | SSH | pública, **só por chave** |
| 80, 443 | Caddy (HTTPS, e o desafio do Let's Encrypt) | pública |
| 5432 | Postgres | **nenhuma** — backup e restauração por `docker exec` |
| 5678 | n8n | loopback (`127.0.0.1:5679`); de fora, só os webhooks via Caddy, o resto com senha antes do login do n8n |
| 8000 | worker | **só na rede interna**, por HTTPS interno e token |
| 8080 | API do site | loopback, para diagnóstico; de fora, via Caddy |

> [!aviso] O Docker ignora o firewall do sistema
> Porta publicada pelo Docker passa por fora do `ufw`. Por isso nenhuma porta nova entra na composição sem `127.0.0.1:` na frente — é regra escrita no roteiro de implantação.

## Acesso à máquina

- SSH só com chave, **sem login de root**, com limite de tentativas e **fail2ban**.
- Firewall (`ufw`) liberando 22, 80 e 443.
- **Atualizações automáticas de segurança** do sistema operacional.
- A porta 22 fica aberta para a internet (quem administra muda de IP), compensada pelas medidas acima.

## Segredos

- Gerados **na própria máquina** e escritos direto no `docker/.env` de produção, sem passar pela tela; nenhum segredo de desenvolvimento é reaproveitado — exceto a chave de cifragem do n8n, que tem de ser a mesma das credenciais restauradas.
- **A chave de API do modelo existe só nas credenciais do n8n**, cifradas: nenhum container recebe a variável (conferido: a contagem da variável no ambiente do worker e da API é zero), e um teste do CI garante que o endereço do provedor só aparece no fluxo de extração.
- Cada serviço recebe as variáveis **por nome** — nenhum arquivo de ambiente inteiro é despejado num container.
- `docker compose config` sem `--quiet` imprime os segredos: o roteiro usa sempre `--quiet`.
- O basic auth do n8n é guardado como **hash bcrypt**; a senha em claro não fica em arquivo nenhum da máquina.
- Backups sem senhas de papéis e com credenciais cifradas; a chave do n8n nunca vai no backup ([[Backup e restauração]]).

## Contenção do que o n8n pode fazer

Os nós de **executar comando** e de **ler arquivos do disco** estão excluídos da instância (`NODES_EXCLUDE`): um fluxo não consegue rodar comando no servidor nem ler o disco — o trabalho pesado vai ao worker, por HTTP.

## Permissões no banco e no armazenamento

- Cada serviço com seu papel: o site só grava decisões humanas; tabelas imutáveis só aceitam inserção ([[Modelo de dados]]).
- O usuário de aplicação no S3 **não apaga**; o bucket é privado e o PDF só sai por URL assinada de 10 minutos para quem está logado ([[Armazenamento de arquivos (S3)]]).

## Relacionadas

[[MOC Infra]] · [[Controle de acesso e segredos]] · [[Domínio, DNS e HTTPS]] · [[Containers e serviços]] · [[Hospedagem na AWS]] · [[Injeção de prompt e defesas]]
