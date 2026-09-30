# ci/ — o executor dos testes

| Arquivo | O que faz |
|---|---|
| `rodar.py` | o executor único, no Windows e no Linux. **Camada (a)**: numa cópia limpa do repositório, sem acervo, sem infraestrutura e sem chave — guardas de texto, banco, migração, worker e API, containers, site e filtro de escopo. **Camada (b)**, opcional e detectada: a instância local do n8n, os invariantes no banco local e as guardas dos containers |
| `sem_chave.py` | tira do ambiente de todo processo filho as chaves de modelo e reprova se alguma reaparecer |
| `tests/test_guardas_texto.py` | o endereço da API do modelo só no ramo certo do W23; nenhum arquivo versionado com cara de segredo |
| `tests/test_guardas_stack.py` | nenhum container rodando com chave de modelo no ambiente |

```bash
python ci/rodar.py --camada a     # o que o GitHub Actions roda (.github/workflows/ci.yml)
python ci/rodar.py                # as duas camadas
make ci                           # o mesmo, onde houver make
```

Sai 0 só se tudo o que rodou passou; o que foi pulado sai listado com o motivo e nunca conta como aprovado.

Documentação: [Testes e CI](<../Fopa-v3/14-Reproducao/Testes e CI.md>)
