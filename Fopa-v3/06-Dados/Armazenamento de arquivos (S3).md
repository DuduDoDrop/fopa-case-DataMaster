---
tipo: componente
familia: dados
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - api/storage.py
  - api/config.py
  - api/baixar.py
  - api/render.py
  - api/site.py
  - docker/backup_fora.py
tags: [dados, armazenamento, s3, seguranca, lgpd]
---

# Armazenamento de arquivos (S3)

> [!abstract] Em uma frase
> Os PDFs baixados e os relatórios gerados ficam num **bucket S3 privado em São Paulo** (`fopa-editais-1`, região sa-east-1), com **chaves derivadas do conteúdo** (o SHA-256 do arquivo) — o que torna cada objeto verificável, elimina duplicatas e deixa o nome original só como marcador de citação; o navegador nunca acessa o bucket diretamente: o site entrega uma **URL assinada de 10 minutos**, só para quem está logado.

## Papel na solução

Os documentos são a prova: toda citação aponta para uma página de um PDF guardado. O armazenamento precisa garantir que o arquivo guardado é **exatamente** o que foi lido (hash), que ele fica no Brasil (os editais trazem nome e salário de servidores) e que só quem está logado o abre ([[Privacidade e LGPD]]).

## As chaves

| Objeto | Chave | Exemplo de forma |
|---|---|---|
| PDF de uma licitação | `pdf/{cnpj}/{ano}/{seq}/{sha256}.pdf` | o CNPJ do órgão, o ano e o sequencial da compra, o hash do conteúdo |
| relatório HTML de uma verificação | `html/{slug}/{verificacao_id}.html` | o *slug* da licitação e o número da verificação |
| backups do banco | `backups/{carimbo}/…` | cópia diária de cada backup bom ([[Backup e restauração]]) |

- **Por que a chave é o hash:** o nome original do PNCP tem acento, espaço, `%` e `#`; ele fica só em `arquivos.nome`, onde é o marcador de citação que o modelo vê. A chave é o SHA-256 do conteúdo: dois arquivos idênticos com nomes diferentes viram **um objeto só** (o segundo é registrado como `alias_duplicado`), e "todo arquivo `ok` tem objeto com o hash gravado" é conferível.
- **Alfabeto restrito:** só letras, dígitos, `.`, `_`, `-` e `/`, sem `..`, sem barra inicial, sem espaço e sem caractere não-ASCII — a mesma chave funciona em disco (Windows e Linux), em URL sem codificação e no S3, e nunca sai da raiz.
- **O conteúdo é conferido na gravação:** se o hash embutido na chave não bater com o hash dos bytes, a gravação é recusada (`ConteudoDivergente`); no S3, o próprio serviço confere o corpo contra o hash declarado na requisição assinada.

## Os dois modos

| Modo | Onde | Uso |
|---|---|---|
| `fs` | um volume de disco (`fopa_dados`) | a infraestrutura local de desenvolvimento; escrita atômica (arquivo temporário e troca), para o site nunca servir PDF pela metade |
| `s3` | o bucket `fopa-editais-1`, em sa-east-1 | **produção** |

As chaves são as mesmas nos dois: migrar de um para o outro é copiar os objetos, sem mexer no banco. O cliente S3 é próprio (assinatura SigV4 calculada no código, endereço no estilo de caminho) e funciona com S3, R2 e MinIO.

## Acesso

- **Bucket privado;** o usuário de acesso da aplicação só lista, lê e grava — **não apaga**. Nada no site apaga objeto.
- **PDF para o navegador:** `GET /api/pdf/{slug}/{arquivo_id}` exige sessão (sem cookie, 401 — nenhum anexo é servido fora do login) e responde com **302 para uma URL assinada de 10 minutos**, com o tipo `application/pdf` para o navegador **abrir** (não baixar); o `#page=N` do link é reaplicado pelo navegador no destino ([[API do site — endpoints]]).
- **Se a URL expirar** durante a leitura de um PDF enorme, basta clicar de novo no link do site (outra URL).
- **Sem configuração, o serviço sobe e explica:** faltando uma variável do S3, cada operação responde com o **nome** do que falta (nunca o valor), e o `/health` diz o mesmo ([[Saúde e observabilidade]]).

## Retenção

- PDFs e relatórios **não expiram**; um PDF perdido também pode voltar do PNCP (o download confere o hash) e um relatório, ser gerado de novo pela rota de render.
- Os backups no prefixo `backups/` **expiram em 30 dias** por uma regra de ciclo de vida do bucket (o bucket não tem versionamento, então expirar apaga de fato); ficam cerca de 30 cópias.

## Relacionadas

[[MOC Dados]] · [[W21 Baixar]] · [[W24 Verificar e publicar]] · [[Hospedagem na AWS]] · [[Backup e restauração]] · [[Privacidade e LGPD]] · [[ADR-022 Produção na AWS, em São Paulo, numa máquina pequena]]
