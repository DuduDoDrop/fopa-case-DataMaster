# api/ — o worker e a API do site

Dois serviços FastAPI na **mesma imagem** (`docker/worker.Dockerfile`), em processos separados:

| Serviço | Entrada | Porta | Quem chama | Papel no banco |
|---|---|---|---|---|
| **worker** | `worker.py` | 8000, só na rede interna (em produção, atrás do HTTPS interno do Caddy) | o n8n, com `Authorization: Bearer` | `worker_rw` |
| **API do site** | `site.py` | 8080 (publicada só em 127.0.0.1; em produção, atrás do Caddy) | o navegador | `api_rw` (grava só decisões humanas) |

## O worker

| Módulo | O que faz |
|---|---|
| `worker.py` | a aplicação e as rotas `/health`, `/versao`, `/reverificar`, `/render`, `/escopo`, `/questionario` e `/custo` |
| `rotas_extracao.py` · `extracao.py` | o caminho da extração que o W23 e o W24 percorrem — `/prompt`, `/reforco`, `/verificar`, `/importar-respostas` e os provedores sem custo `/responder-simulado` e `/gravado/v1/messages` |
| `rotas_jobs.py` · `jobs.py` | os jobs longos (`/jobs/baixar`, `/jobs/paginas`, histórico) numa fila própria, com concorrência configurável e órfãos declarados no arranque |
| `baixar.py` · `converter.py` | baixar todos os documentos de uma licitação; o que não é PDF passa pelo fluxo de exceção e vira PDF |
| `leitura.py` | congelar o texto de cada página, com OCR onde precisa e detecção de texto escondido |
| `persistencia.py` · `politica.py` · `injecao.py` | gravar a verificação, aplicar a política de veredito e marcar injeção suspeita |
| `rotas_jev.py` · `jev.py` | montar a pergunta ao Jev e interpretar a resposta (o n8n faz a chamada) |
| `rotas_escopo.py` · `escopo_ajuste.py` | reavaliar o escopo com a regra atual e a camada de ajuste de falsos positivos |
| `historico_pncp.py` · `contratos_pncp.py` · `descoberta_historica.py` | o histórico de compras, itens, resultados e contratos do PNCP |
| `modelos_ia.py` | o catálogo de provedores e modelos do botão "Extrair com IA", com o esforço fixo e a estimativa de custo |
| `render.py` · `reconstrucao.py` | o relatório HTML de uma verificação, a partir do banco |
| `storage.py` | o armazenamento dos arquivos (disco local ou S3, com URL assinada) |
| `versao.py` · `auth.py` · `banco.py` | as versões declaradas no `/health`, a autenticação e a conexão com o Postgres |
| `demo_reservar.py` | reserva de licitações para demonstração: marca como ensaio e deixa o W20 chamá-las direto |

## A API do site

| Módulo | O que faz |
|---|---|
| `site.py` | as rotas `/api/*`, `/auth/google/*`, `/api/admin/*`, `/api/acoes/*` e a página `/privacidade`; serve o site React |
| `oauth.py` · `sessao.py` · `config.py` | login com Google (OpenID Connect, PKCE, `state`, `nonce`), sessão de 12 horas revogável e configuração |
| `consultas.py` · `analytics.py` | as consultas de leitura do painel, do detalhe, da revisão e do Analytics |

## Testes

```bash
python -m pytest api/tests -q      # 474 funções de teste; roda sem nenhuma chave de modelo
```

Documentação: [Endpoints do worker](<../Fopa-v3/04-Worker-e-API/Endpoints do worker.md>) · [API do site — endpoints](<../Fopa-v3/04-Worker-e-API/API do site — endpoints.md>) · [Worker — visão geral e jobs](<../Fopa-v3/04-Worker-e-API/Worker — visão geral e jobs.md>)
