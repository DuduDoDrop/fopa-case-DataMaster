# -*- coding: utf-8 -*-
"""
Descoberta e teste de fumaça do provedor OpenAI.

    python 26_modelos_openai.py                 lista os modelos da conta
    python 26_modelos_openai.py --testar        + uma chamada real, barata
    python 26_modelos_openai.py --testar --modelo gpt-5.6-mini

POR QUE ESTE SCRIPT EXISTE
  Porque não se sabe de antemão qual modelo esta conta tem, e adivinhar identificador de
  modelo é a forma mais barata de perder uma hora. O catálogo do fornecedor muda
  sem aviso, o nome que o usuário lembra nem sempre é o da API, e o erro que
  volta quando se erra o identificador ("model not found") não sugere o certo.

  A regra 2 do vault vale aqui inteira: não inventar. Então o identificador sai
  de `/v1/models` — da conta, não da memória de ninguém.

CUSTO
  A listagem é grátis: `/v1/models` não consome token. O `--testar` faz UMA
  chamada com um documento de sete linhas e teto de saída curto — centavos.
  A extração de verdade é o `10_extrair_edital.py --provedor openai`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from fopa import modelos, segredos                            # noqa: E402


def barra(t: str) -> None:
    print("\n" + "=" * 92 + "\n  %s\n" % t + "=" * 92)


# Documento minúsculo, com uma armadilha de propósito: o trecho que responde
# está na PÁGINA 2, e a página 1 contém um número parecido. Um provedor que
# devolve a primeira ocorrência erra a página — e é a página que o Verificador
# confere. O teste de fumaça já exercita a propriedade que interessa.
DOC_TESTE = """=== ARQUIVO edital_teste.pdf | PÁGINA 1 ===
PREFEITURA MUNICIPAL DE TESTE
Processo Administrativo nº 12/2026. Publicado no Diário Oficial de 02/03/2026.
O valor estimado do processo anterior foi de R$ 1.200.000,00.

=== ARQUIVO edital_teste.pdf | PÁGINA 2 ===
CLÁUSULA TERCEIRA — DO VALOR MÍNIMO
Fica estabelecido o valor mínimo de R$ 2.450.000,00 (dois milhões, quatrocentos
e cinquenta mil reais) para a cessão onerosa da folha de pagamento.
"""

PERGUNTA_TESTE = (
    "Qual o VALOR MÍNIMO estabelecido para a cessão onerosa da folha?\n"
    "Responda em JSON com: resposta, arquivo, pagina (inteiro) e trecho_literal "
    "(copiado EXATAMENTE do documento, caractere a caractere)."
)

ESQUEMA_TESTE = {
    "type": "object",
    "properties": {
        "resposta": {"type": "string"},
        "arquivo": {"type": ["string", "null"]},
        "pagina": {"type": ["integer", "null"]},
        "trecho_literal": {"type": ["string", "null"]},
    },
    "required": ["resposta", "arquivo", "pagina", "trecho_literal"],
    "additionalProperties": False,
}


def listar(cliente) -> list[str]:
    ids = sorted(m.id for m in cliente.models.list())
    interessantes = [i for i in ids
                     if i.startswith(("gpt-", "o1", "o3", "o4", "chatgpt"))]

    barra("MODELOS DA CONTA — %d no total, %d da família GPT/o"
          % (len(ids), len(interessantes)))
    for i in interessantes:
        marca = "  <- padrão do FOPA" if i == modelos.MODELO_OPENAI else ""
        print("   %s%s" % (i, marca))
    if not interessantes:
        print("   (nenhum) — a conta não expõe modelo de texto da família GPT")

    if modelos.MODELO_OPENAI not in ids:
        print("\n  ATENÇÃO: o padrão configurado (%s) NÃO está nesta conta."
              % modelos.MODELO_OPENAI)
        print("  Escolha um da lista acima e grave no .env:")
        print("      FOPA_MODELO_OPENAI=<id>")
    return interessantes


def testar(modelo: str) -> int:
    barra("TESTE DE FUMAÇA — %s" % modelo)
    print("  Documento de 2 páginas. A resposta está na p.2; a p.1 tem um número")
    print("  parecido, de propósito. Confere-se a PÁGINA e o TRECHO, não o texto.\n")

    prov = modelos.ProvedorOpenAI()
    try:
        dados, uso = prov.responder_json(
            sistema="Você extrai informação de editais de licitação brasileiros. "
                    "Cite sempre o arquivo, a página e o trecho literal.",
            usuario=DOC_TESTE + "\n" + PERGUNTA_TESTE,
            esquema=ESQUEMA_TESTE, modelo=modelo, max_tokens=4000, effort="low")
    except modelos.ErroModelo as e:
        print("  FALHOU: %s" % e)
        return 1

    print("  resposta ....... %s" % dados.get("resposta"))
    print("  arquivo ........ %s" % dados.get("arquivo"))
    print("  página ......... %s" % dados.get("pagina"))
    print("  trecho ......... %s" % (dados.get("trecho_literal") or "")[:80])
    print("\n  %s" % uso)

    # A mesma pergunta que o Verificador faz, em miniatura: o trecho citado
    # existe, literalmente, na página citada?
    falhas = []
    if dados.get("pagina") != 2:
        falhas.append("citou a página %s; a resposta está na 2 (caiu na armadilha "
                      "do número parecido na p.1)" % dados.get("pagina"))
    trecho = (dados.get("trecho_literal") or "").strip()
    if not trecho:
        falhas.append("não devolveu trecho literal")
    elif trecho not in DOC_TESTE:
        falhas.append("o trecho citado não existe literalmente no documento")

    print("\n" + "-" * 92)
    if falhas:
        print("  ANCORAGEM REPROVADA:")
        for f in falhas:
            print("    · %s" % f)
        print("\n  Não é impeditivo: o provedor responde, e o Verificador pegaria")
        print("  isso em produção. Mas indique nas notas antes de usar em lote.")
        return 1
    print("  ANCORAGEM OK — página certa e trecho conferido caractere a caractere.")
    print("\n  Próximo passo, a extração de verdade contra um gabarito:")
    print("      python 10_extrair_edital.py \"ABERTO Concorrencia - Eletronica - Pirapo-RS\" \\")
    print("             --provedor openai --saida saidas/_openai_pirapo")
    print("      python 15_acuracia.py")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Descobre e testa o provedor OpenAI")
    ap.add_argument("--testar", action="store_true",
                    help="faz uma chamada real (centavos)")
    ap.add_argument("--modelo", default=None, help="sobrescreve FOPA_MODELO_OPENAI")
    a = ap.parse_args()

    barra("CHAVES VISÍVEIS")
    print(segredos.diagnostico())

    if not segredos.obter("OPENAI_API_KEY"):
        print("\n  Sem OPENAI_API_KEY não há o que listar.")
        print("  Grave a chave em %s (o arquivo está no .gitignore):" % segredos.CAMINHO_ENV)
        print("      OPENAI_API_KEY=sk-...")
        return 3

    try:
        import openai
    except ImportError:
        print("\n  SDK não instalado: pip install openai")
        return 3

    cliente = openai.OpenAI(api_key=segredos.obter("OPENAI_API_KEY"))
    try:
        disponiveis = listar(cliente)
    except Exception as e:                                     # noqa: BLE001
        print("\n  falha ao listar modelos: %s" % e)
        return 1

    if not a.testar:
        print("\n  Para uma chamada real: python 26_modelos_openai.py --testar")
        return 0

    modelo = a.modelo or modelos.MODELO_OPENAI
    if modelo not in disponiveis:
        print("\n  %s não está na conta. Passe --modelo com um id da lista." % modelo)
        return 2
    return testar(modelo)


if __name__ == "__main__":
    raise SystemExit(main())
