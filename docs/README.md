# docs/ — implantação, credenciais e medições brutas

| Arquivo | O que é |
|---|---|
| [`DEPLOY.md`](DEPLOY.md) | o roteiro de implantação num servidor: máquina, DNS, bucket, `.env` de produção, certificado interno, imagem, dados, credenciais do n8n, login Google, OCR na CPU nova, backup, restauração, atualização e volta de versão — e, no §18, a instalação local sem agenda |
| [`n8n-credenciais.md`](n8n-credenciais.md) | as credenciais do n8n por nome, os segredos locais que o `n8n/bootstrap.py` gera e a configuração do e-mail (SPF, DKIM, DMARC) — nenhum valor secreto |
| `ocr-equivalencia-*.json` | a comparação página a página do OCR de cada ambiente com a linha de base (`tests/ocr_baseline`): a imagem local e o servidor de produção |
| `medicoes/` | os resultados brutos, em JSON, das medições do Jev (critérios, escopo com e sem edital, credenciamento, sustentação) citadas nas notas de avaliação |

A documentação da solução — negócio, arquitetura, fluxos, site, dados, IA, avaliação, decisões, infraestrutura, segurança, base legal, escalabilidade, reprodução e evolução — está no vault [`Fopa-v3/`](<../Fopa-v3/00-Entrada/Home.md>).
