# -*- coding: utf-8 -*-
"""
Coleta objetos de licitação para ampliar a suíte do filtro de escopo.

    python 24_corpus_escopo.py                 uma tentativa
    python 24_corpus_escopo.py --ate-conseguir espera a API voltar

Custo R$ 0,00 — só consulta, nunca extrai. O que ele grava é o **objeto** de
cada licitação que a busca devolve, que é exatamente o texto sobre o qual o
filtro decide.

POR QUE ISTO VALE MAIS QUE A SUÍTE ATUAL
A suíte de `23_testa_escopo.py` tem 13 objetos reais — os que já estão em disco.
É pouco: um filtro que acerta 13 pode errar o décimo quarto, e o custo do erro é
uma extração inteira mais um relatório inútil. Foi assim que Rio Azul/PR entrou.

Com algumas centenas de objetos dá para medir a taxa de desacordo e, mais
importante, ver QUAIS casos ficam na fronteira. O filtro devolve o motivo da
decisão, então o relatório agrupa por motivo e mostra exemplos — que é como se
descobre a regra que falta.

O QUE ELE NÃO FAZ
Não decide sozinho quem está certo. A saída é material para leitura humana: os
casos duvidosos ficam listados para alguém julgar e, se for o caso, virarem
teste. Um filtro validado por ele mesmo não vale nada.
"""
from __future__ import annotations

import argparse
import collections
import io                  # mesclar() lia o corpus antigo sem isto, e estourava
import json
import glob
import os
import sys
import time

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
AMOSTRAS = os.path.join(RAIZ, "amostras")
sys.path.insert(0, AQUI)

from fopa import escopo, execucao, pncp                                # noqa: E402

SAIDAS = os.path.join(RAIZ, "saidas")
DESTINO = os.path.join(SAIDAS, "_corpus_escopo.json")

# Termos amplos de propósito: o objetivo é trazer TAMBÉM o que não é do escopo,
# para medir se o filtro descarta. Buscar só "cessão onerosa" testaria o filtro
# apenas contra o que ele já acerta.
TERMOS = (
    "cessão onerosa folha de pagamento",
    "folha de pagamento servidores instituição financeira",
    "gestão de consignações folha de pagamento",
    # medido em 23/09/2026: 132 de folha em 150 itens (88%). Tres licitacoes
    # que a varredura de recall achou e a busca nao escrevem "bancaria" e nao
    # "financeira" no objeto -- Pirassununga/SP, Sao Jose dos Campos/SP e
    # Pompeia/SP.
    "folha de pagamento instituição bancária",
    "administração da folha de pagamento",
    "sistema de folha de pagamento",
    "processamento da folha de pagamento",
    # TRES TERMOS QUE A VARREDURA DE 2026-08 COBROU, e cada um tem o caso
    # que o obrigou (varredura dia a dia, 26.352 registros brutos):
    #
    #   "creditos da folha"  -> Aguas de Chapeco/SC, Pitanga/PR e Bonito/PE
    #       escrevem "creditos PROVENIENTES da folha de pagamento". Os tres
    #       contem "folha de pagamento" E "instituicao financeira", e mesmo
    #       assim NENHUM dos sete termos aparece inteiro no objeto -- a busca
    #       do PNCP casa a frase, nao as palavras soltas. Um termo, tres casos.
    #
    #   "empresa bancaria"   -> Pompeia/SP diz "empresa bancaria objetivando
    #       servicos de gerenciamento e processamento da folha". Nao e
    #       "instituicao" nem "financeira": e outra palavra para a mesma coisa.
    #
    #   "folha salarial"     -> Pitanga/PR. O sinonimo que nenhum dos sete
    #       cobria, e que nao tem nada de exotico.
    "créditos da folha de pagamento",
    # ERRO DA RODADA ANTERIOR, PEGO PELA MEDICAO SEGUINTE.
    # Adicionei "creditos da folha de pagamento" achando que cobriria Aguas de
    # Chapeco, Pitanga e Bonito. Nao cobre: os tres escrevem "creditos
    # PROVENIENTES da folha de pagamento", e a busca do PNCP casa a frase --
    # a palavra no meio quebra. A varredura de agosto mostrou os tres ainda
    # perdidos, mais Caninde/CE e Bauru/SP com a mesma redacao.
    #
    # As duas frases convivem porque sao conjuntos distintos, e as duas tem
    # densidade de 100% no corpus: 89 ocorrencias da primeira, 109 da segunda,
    # todas dentro do escopo.
    "créditos provenientes da folha de pagamento",
    # Piedade/SP nao diz "folha" no comeco: "CENTRALIZACAO DOS SERVICOS DE
    # PAGAMENTO DAS REMUNERACOES, SALARIOS E PROVENTOS DOS SERVIDORES". Esta
    # frase NAO tem densidade medida -- nao ha nenhuma ocorrencia no corpus,
    # justamente porque a busca nunca trouxe esses casos. Entra como aposta
    # declarada, e a proxima varredura mede.
    "centralização dos serviços de pagamento",
    "empresa bancária folha de pagamento",
    "folha salarial instituição financeira",
)


_ESTADO: dict = {}


def coletar(paginas: int) -> list[dict]:
    """
    Coleta os termos e DIZ QUANTO FICOU DE FORA.

    O `api/search` declara o tamanho do conjunto no campo `total`. Medido em
    23/09/2026, "folha de pagamento instituicao bancaria" declara **1.204**
    resultados -- e 10 paginas de 50 leem 500, ou seja 42%. O teto de
    paginacao nunca foi cego: o numero que o mede vinha na resposta e ninguem
    lia.

    O corte continua sendo deliberado (ler 1.204 por termo, dez termos, custa
    caro e traz cada vez mais ruido). O que muda e saber o tamanho do que se
    corta -- a diferenca entre "paro na pagina 10" e "vejo 42% e sei disso".
    """
    itens = []
    cobertura = []
    falhos = []
    for termo in TERMOS:
        try:
            lote, info = pncp.buscar_com_info(termo, paginas=paginas, tam=50)
        except pncp.ErroPNCP as e:
            parcial = getattr(e, "itens", []) or []
            print("    %-54s falhou: %s%s"
                  % ('"%s"' % termo[:52], str(e)[:40],
                     " (aproveitando %d)" % len(parcial) if parcial else ""))
            itens.extend(parcial)
            falhos.append((termo, len(parcial)))
            continue
        pct = info.get("cobertura_pct")
        print("    %-54s %4d de %5s declarados%s"
              % ('"%s"' % termo[:52], len(lote),
                 info.get("total_declarado") or "?",
                 ("  (%.0f%%)" % pct) if pct else ""))
        cobertura.append((termo, info))
        itens.extend(lote)

    total_decl = sum((i.get("total_declarado") or 0) for _, i in cobertura)
    total_lido = sum(i.get("lidos") or 0 for _, i in cobertura)
    print()
    # A COBERTURA SO PODE FALAR DOS TERMOS QUE RESPONDERAM.
    #
    # A primeira versao imprimia "358 de 358 declarados (100%)" numa execucao
    # em que NOVE dos doze termos falharam -- porque `cobertura` so recebia os
    # que deram certo. Cem por cento de um terco do trabalho, apresentado como
    # cem por cento. E a mesma familia do "nada a fazer" x "nao consegui
    # olhar" que o monitor ja corrigiu.
    if total_decl:
        print("    cobertura dos termos que responderam: %d de %d (%.0f%%)"
              % (total_lido, total_decl, 100.0 * total_lido / total_decl))
        print("    (com sobreposicao entre termos; a dedup vem a seguir)")
    if falhos:
        salvos = sum(n for _, n in falhos)
        print()
        print("    !! %d de %d termo(s) FALHARAM — esta coleta é PARCIAL."
              % (len(falhos), len(TERMOS)))
        print("       %d registro(s) aproveitados do que já tinha sido lido"
              % salvos)
        print("       antes da falha; o resto desses termos não foi visto.")
        for t, n in falhos:
            print("        · %-52s %s" % (t[:52],
                                          "%d parcial" % n if n else "nada"))
        if len(falhos) == len(TERMOS):
            print()
            print("    NENHUM termo respondeu: esta execução ficou CEGA.")
            print("    Não há o que concluir dela, nem mesmo que não havia nada.")
    _ESTADO["cobertura"] = {t: i for t, i in cobertura}
    _ESTADO["termos_falhos"] = [t for t, _ in falhos]
    return pncp.dedup(itens)


def mesclar(novos: list[dict]) -> list[dict]:
    """
    Junta a coleta nova com o que o corpus já tinha, pelo número de controle.

    POR QUE ACUMULAR, E NÃO SUBSTITUIR
      Porque a busca do PNCP é uma JANELA MÓVEL, não um censo. Duas coletas do
      mesmo termo, com horas de diferença, devolvem conjuntos parcialmente
      distintos — em 23/09 uma trouxe 329 registros e a seguinte, 247, com
      sobreposição parcial.

      Sobrescrever descarta o que a janela anterior viu e a atual não vê. E foi
      exatamente o que aconteceu: uma reexecução apagou 329 registros, incluindo
      os 217 fora de escopo que sustentavam a medição "112 de 329 são folha".
      O arquivo está no `.gitignore`, então não havia de onde recuperar.

      A medição continua tendo valido no momento em que foi feita. O que se
      perdeu foi a capacidade de REFAZÊ-LA — que, num projeto cujo argumento é
      "tudo é verificável", é a parte que importa.
    """
    antigos = []
    if os.path.isfile(DESTINO):
        try:
            antigos = json.load(io.open(DESTINO, encoding="utf-8")).get("registros", [])
        except (ValueError, OSError):
            antigos = []

    por_ctrl = {}
    for r in antigos:
        c = (r.get("controle") or "").strip()
        if c:
            por_ctrl[c] = r
    novos_ctrl = 0
    for r in novos:
        c = (r.get("controle") or "").strip()
        if not c:
            continue
        if c not in por_ctrl:
            novos_ctrl += 1
        por_ctrl[c] = r          # a coleta nova tem precedência no conteúdo

    print("  corpus: %d já existiam · %d novos · %d no total"
          % (len(antigos), novos_ctrl, len(por_ctrl)))
    # A SERIE DESTE NUMERO E O DADO, NAO O NUMERO DE HOJE.
    #
    # A busca do PNCP e uma JANELA MOVEL: cada execucao devolve um conjunto
    # parcialmente diferente, e o corpus acumula. Saber se as execucoes estao
    # CONVERGINDO -- trazendo cada vez menos novos -- e o que diz se o acervo
    # esta perto de completo ou se o teto de paginacao ainda corta.
    #
    # Em 23/09/2026 a serie mostrou o oposto de convergencia: depois de subir
    # o teto de 2 para 10 paginas, as coletas trouxeram 92, depois 239, depois
    # 409 registros novos. Acelerando, nao desacelerando -- sinal de que 10
    # paginas continua sendo o limitante.
    #
    # Esse padrao so ficou visivel porque os numeros estavam no historico da
    # execucao. Este script era o unico dos cinco que NAO registrava execucao, e
    # e justamente aquele cuja serie importa.
    _ESTADO["antigos"] = len(antigos)
    _ESTADO["novos"] = novos_ctrl
    _ESTADO["total"] = len(por_ctrl)
    return reavaliar(list(por_ctrl.values()))


def reavaliar(registros: list[dict]) -> list[dict]:
    """
    Roda o filtro de escopo DE NOVO em todo registro guardado.

    POR QUE, E O QUE ISTO ACHOU
      O corpus guardava o veredito do filtro no momento da coleta, e nunca mais
      olhava. Quando o filtro melhora, o registro velho fica com a resposta
      velha — para sempre, e sem sinal nenhum.

      Medido em 23/09/2026: Ronda Alta/RS, "Aquisição de relógios de ponto com
      reconhecimento facial e tela touch", estava no corpus como DENTRO DO
      ESCOPO, com o motivo "contrata a operação da folha". O filtro de hoje a
      rejeita corretamente. Era 1 em 414 — mas contava nos 178 de folha, no
      painel e em toda medição que usa o corpus como denominador.

      Um cache que guarda o resultado de uma REGRA, e não um fato do mundo,
      precisa ser invalidado quando a regra muda. Aqui invalidar é barato:
      `escopo.avaliar` é determinístico, local e roda em milissegundos. Não há
      motivo para cachear, e havia motivo para não cachear.
    """
    mudou = []
    for r in registros:
        dentro, motivo = escopo.avaliar(r.get("objeto") or "")
        if bool(r.get("dentro")) != dentro or r.get("motivo") != motivo:
            mudou.append((r, bool(r.get("dentro")), dentro))
            r["dentro"], r["motivo"] = dentro, motivo
    if mudou:
        viraram_fora = sum(1 for _, a, d in mudou if a and not d)
        viraram_dentro = sum(1 for _, a, d in mudou if d and not a)
        print("  reavaliação do escopo: %d registro(s) mudaram de veredito"
              % len(mudou))
        print("     %d saíram do escopo · %d entraram"
              % (viraram_fora, viraram_dentro))
        # O ROTULO PRECISA DISTINGUIR TRES COISAS, NAO DUAS.
        #
        # A versao anterior imprimia "DENTRO->fora" ou "fora->DENTRO" para toda
        # mudanca, inclusive quando so o MOTIVO mudou e o veredito ficou igual.
        # Rio de Janeiro passou de "nao e sobre folha" para "servico SOBRE a
        # folha" -- continuou fora o tempo todo -- e apareceu na tela como
        # "fora->DENTRO". Contradizia o contador logo acima, na mesma saida.
        for r, a, d in mudou[:6]:
            if a == d:
                rotulo = "so o motivo"
            else:
                rotulo = "DENTRO→fora" if a else "fora→DENTRO"
            print("     %-11s %-24s %s"
                  % (rotulo, (r.get("municipio") or "?")[:24],
                     (r.get("objeto") or "")[:50]))
    return registros


def sincronizar_inventarios(registros: list[dict]) -> int:
    """
    Copia para os inventários em disco os campos que o corpus acabou de trazer.

    POR QUE ISTO RODA AQUI, E NÃO NUM SCRIPT SEPARADO
      O corpus é uma janela móvel: cada refresh traz campos para registros que
      antes não os tinham. Em 23/09 o `fim_prazo` passou a ser guardado, e as
      175 pastas já em disco continuaram sem ele — o painel exibia "prazo não
      informado" enquanto o dado estava no corpus, a um `join` de distância.

      A sincronização foi feita à mão uma vez, o teste 9 do `40_fumaca.py` passou, e
      **no refresh seguinte ele falhou de novo**: mais 17 registros ganharam
      prazo e os inventários ficaram para trás.

      Um passo manual que precisa acontecer depois de outro passo é um passo
      que vai ser esquecido. Ou roda junto, ou não existe.

    Só PREENCHE campo vazio: nunca sobrescreve o que o coletor gravou na hora
    do download. Aquilo é o estado no momento da coleta; isto é o estado de
    agora. Quando divergem, quem baixou tem a informação de origem.
    """
    por_ctrl = {}
    for r in registros:
        c = (r.get("controle") or "").strip()
        if c:
            por_ctrl[c] = r

    n = 0
    for f in glob.glob(os.path.join(AMOSTRAS, "*", "_inventario.json")):
        if os.path.basename(os.path.dirname(f)).startswith("_"):
            continue
        try:
            d = json.load(io.open(f, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        r = por_ctrl.get((d.get("controle") or "").strip())
        if not r:
            continue
        mudou = False
        for k in ("fim_prazo", "municipio", "situacao", "publicado_em",
                  "orgao", "uf", "modalidade"):
            v = r.get(k)
            v = v.strip() if isinstance(v, str) else v
            if v and not (d.get(k) or ""):
                d[k] = v
                mudou = True
        if mudou:
            try:
                json.dump(d, io.open(f, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
                n += 1
            except OSError:
                pass
    return n


def so_reavaliar() -> int:
    """
    Reaplica o filtro de escopo ao corpus em disco, SEM ir a rede.

    Existe porque o teste 12 do `40_fumaca.py` acusa divergencia entre o
    veredito guardado e o filtro de hoje -- e ate agora o unico conserto era
    uma coleta completa, que leva minutos e depende do PNCP estar de pe.
    Consertar um cache local nao pode exigir uma API de terceiro.

        python 24_corpus_escopo.py --so-reavaliar
    """
    if not os.path.isfile(DESTINO):
        print("sem corpus em disco")
        return 1
    d = json.load(io.open(DESTINO, encoding="utf-8"))
    registros = reavaliar(d.get("registros") or [])
    d["registros"] = registros
    d["reavaliado_em"] = time.strftime("%Y-%m-%d %H:%M")
    io.open(DESTINO, "w", encoding="utf-8").write(
        json.dumps(d, ensure_ascii=False, indent=1))
    dentro = sum(1 for r in registros if r.get("dentro"))
    print("  %d registros · %d no escopo · %d fora"
          % (len(registros), dentro, len(registros) - dentro))
    print("  custo em rede: zero")
    return 0


def main() -> int:
    _t0 = time.time()
    if "--so-reavaliar" in sys.argv:
        return so_reavaliar()
    ap = argparse.ArgumentParser()
    # QUANTAS PAGINAS -- E POR QUE 2 ERA POUCO DEMAIS.
    #
    # O default era 2, desde sempre, sem ninguem revisitar. Medido em 23/09/2026
    # sobre o termo "folha de pagamento servidores instituicao financeira":
    #
    #     pagina  1 .... 41 de 50 sao de folha
    #     pagina  4 .... 43 de 50
    #     pagina  8 .... 41 de 50
    #     pagina 16 .... 45 de 50
    #     800 itens varridos, 699 de folha -- 87%
    #
    # A DENSIDADE NAO CAI. O ranking do `api/search` nao concentra os relevantes
    # nas primeiras paginas, entao parar na 2a nao e "pegar os melhores": e ver
    # 100 de 800+, ou 12%.
    #
    # Foi assim que Dracena/SP e Sao Jose dos Campos/SP ficaram de fora -- estao
    # na PAGINA 3 de um termo que o projeto ja usava. A varredura de recall as
    # marcou como "a busca perdeu", e a busca nao tinha perdido: ela nao tinha
    # olhado.
    ap.add_argument("--paginas", type=int, default=10)
    ap.add_argument("--ate-conseguir", action="store_true",
                    help="tenta de novo até a API responder")
    ap.add_argument("--espera", type=int, default=180,
                    help="segundos entre tentativas (padrão 180)")
    ap.add_argument("--tentativas", type=int, default=12)
    a = ap.parse_args()

    print("=" * 96)
    print("  CORPUS DE ESCOPO — objetos reais para ampliar a suíte do filtro")
    print("=" * 96)

    itens = []
    for n in range(1, (a.tentativas if a.ate_conseguir else 1) + 1):
        if a.ate_conseguir and n > 1:
            print("\n  tentativa %d/%d" % (n, a.tentativas))
        itens = coletar(a.paginas)
        if itens or not a.ate_conseguir:
            break
        # A API do PNCP cai por janelas de dezenas de minutos, não de segundos:
        # esperar pouco só multiplica o log sem aumentar a chance.
        print("    nada veio — nova tentativa em %ds" % a.espera)
        time.sleep(a.espera)

    if not itens:
        print("\n  a API não respondeu. Nada foi gravado.")
        return 2

    print("\n  %d objetos após deduplicação\n" % len(itens))

    registros, por_motivo = [], collections.Counter()
    for it in itens:
        objeto = " ".join(str(it.get(c) or "") for c in
                          ("description", "objeto", "objetoCompra", "title"))
        dentro, motivo = escopo.avaliar(objeto)
        por_motivo[(dentro, motivo)] += 1
        # O PRAZO VINHA NA BUSCA E SE PERDIA AQUI.
        #
        # `data_fim_vigencia` é o fim do prazo de propostas — o campo que
        # decide se uma licitação é urgente. O corpus não o guardava, o
        # coletor não tinha de onde tirar, e o painel exibia "prazo não
        # informado" em **169 das 175** licitações do acervo.
        #
        # O recurso mais visível do produto — "fecham em ≤7 dias" — operava
        # sobre as 6 pastas antigas que um coletor anterior havia preenchido.
        # Não era limitação do PNCP: era um campo descartado na primeira etapa
        # e procurado na última.
        registros.append(dict(
            controle=it.get("numero_controle_pncp"),
            orgao=it.get("orgao_nome"), uf=it.get("uf"),
            municipio=it.get("municipio_nome"),
            modalidade=it.get("modalidade_licitacao_nome"),
            fim_prazo=str(it.get("data_fim_vigencia") or "")[:16],
            publicado_em=str(it.get("data_publicacao_pncp") or "")[:10],
            situacao=it.get("situacao_nome"),
            dentro=dentro, motivo=motivo, objeto=objeto[:900]))

    dentro = sum(1 for r in registros if r["dentro"])
    print("  %d no escopo · %d descartados\n" % (dentro, len(registros) - dentro))
    print("  %-62s %5s" % ("motivo da decisão", "qtd"))
    print("  " + "-" * 70)
    for (d, motivo), n in por_motivo.most_common():
        print("  %-62s %5d" % (("[DENTRO] " if d else "[fora]   ") + motivo[:52], n))

    # Os que ficam na fronteira são os que ensinam. Exemplo de cada motivo.
    print("\n  Um exemplo de cada motivo, para leitura humana:")
    vistos = set()
    for r in registros:
        chave = (r["dentro"], r["motivo"])
        if chave in vistos:
            continue
        vistos.add(chave)
        print("\n    %s %s" % ("[DENTRO]" if r["dentro"] else "[fora]  ", r["motivo"]))
        print("      %s/%s · %s" % (r["orgao"], r["uf"], r["modalidade"]))
        print("      %s" % r["objeto"][:200].replace("\n", " "))

    os.makedirs(SAIDAS, exist_ok=True)
    registros = mesclar(registros)
    with open(DESTINO, "w", encoding="utf-8") as f:
        json.dump({"coletado_em": time.strftime("%Y-%m-%d %H:%M"),
                   "registros": registros}, f, ensure_ascii=False, indent=1)
    _sinc = sincronizar_inventarios(registros)
    if _sinc:
        print("  inventários sincronizados: %d pasta(s) receberam campos novos"
              % _sinc)
    dentro = sum(1 for r in registros if r.get("dentro"))
    execucao.registrar("24_corpus_escopo.py", _t0,
                       novos=_ESTADO.get("novos", 0),
                       total=_ESTADO.get("total", len(registros)),
                       no_escopo=dentro,
                       paginas=a.paginas, termos=len(TERMOS))
    print("\n  salvo: %s" % os.path.relpath(DESTINO, RAIZ))
    print("  custo em API: R$ 0,00 — nenhuma extração foi feita")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
