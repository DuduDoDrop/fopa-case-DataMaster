# -*- coding: utf-8 -*-
"""
Agente 3 — Extrator de edital.

Responde as 17 perguntas a partir dos documentos de uma licitação, citando arquivo,
página física e trecho literal. É o único agente que produz o entregável, e o único
cujo erro é INVISÍVEL: sai plausível, formatado e com página citada.

Por isso ele não decide nada sozinho — tudo que sai daqui passa pelo Verificador.

Regras (Fopa-v2/00-Case/Regras de negócio.md):
  RN-01 evidência  ·  RN-02 "não localizado"  ·  RN-04 documento vigente
  RN-05 não exigir tipo "Edital"  ·  RN-06 ler todos os documentos
  RN-08 arquivo + página  ·  RN-13 transcrever, nunca calcular
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field, asdict

from . import ocr as ocr_mod
from . import condicoes as cond
from . import furtivo as furt
from . import recuperacao as rec
from .modelos import MODELO_EXTRATOR, ErroModelo, Provedor, Uso
from .questionario import (PERGUNTAS, POR_ID, ESQUEMA_LOTE, NAO_LOCALIZADO,
                           instrucao_sistema)

# RN-06 — arquivos que jamais podem faltar do contexto, por menores que sejam.
# O aviso de retificação tem 2 páginas e carrega a data vigente da sessão.
SEMPRE_INCLUIR = ("retifica", "suspens", "comunicado", "redesign", "errata", "aviso")

# ordem de precedência quando documentos divergem (RN-14)
PRECEDENCIA = ("retifica", "suspens", "comunicado", "redesign", "errata",
               "resposta", "esclarecim", "termo de referencia", "edital")


@dataclass
class Resposta:
    id: str
    pergunta: str
    resposta: str
    arquivo: str | None = None
    pagina: int | None = None
    trecho_literal: str | None = None
    conflito: str | None = None
    confianca: str = "media"
    # preenchidos pelo Verificador
    # Guarda a pagina que o modelo CITOU, quando o Verificador a corrige. Sem
    # isto a correcao apagava o proprio rastro: a pagina salva passava a ser a
    # certa, a reverificacao seguinte nao achava mais divergencia, e o caso
    # virava APROVADO como se nunca tivesse havido erro de citacao.
    pagina_citada: int | None = None
    # O nome de arquivo RESOLVIDO pela mesma função que localiza a página
    # (`Extracao.pagina`). `arquivo` guarda o que o modelo escreveu — que pode
    # ser sufixo ou vir com o rótulo do marcador colado — e o link do relatório
    # precisa do nome que existe no disco. `None` quando a citação não resolve.
    arquivo_canonico: str | None = None
    veredito: str = "PENDENTE"
    alertas: list[str] = field(default_factory=list)

    @property
    def info(self) -> str:
        """RN-08 — a coluna Info: arquivo + página física."""
        if self.resposta.strip() == NAO_LOCALIZADO or not self.arquivo:
            return NAO_LOCALIZADO
        return "%s p. %d" % (self.arquivo, self.pagina) if self.pagina else self.arquivo

    def para_dict(self) -> dict:
        d = asdict(self)
        d["info"] = self.info
        return d


@dataclass
class Extracao:
    licitacao: str
    respostas: list[Resposta]
    paginas: list[rec.Pagina] = field(default_factory=list)
    modo: str = ""
    uso: Uso = field(default_factory=Uso)
    arquivos: list[str] = field(default_factory=list)
    # A CONFIGURACAO faz parte do resultado.
    #
    # `modo` ja era gravado; `provedor` e `effort` nao eram, e sem eles um
    # `auditoria.json` reaberto semanas depois obriga a deduzir do codigo o que
    # deveria estar no arquivo. O harness registra isso no rotulo da execucao
    # ("opus-5 · high") justamente porque, sem a configuracao, dois numeros
    # diferentes nao dizem se o modelo mudou ou se a configuracao mudou.
    provedor: str = ""
    effort: str = ""
    # O que o sistema observou sobre a PRÓPRIA execução. Ver `condicoes.py`:
    # a confiança deixa de ser um número que o modelo emite sobre si e passa a
    # ser derivada de fatos observados.
    condicoes: "cond.Condicoes" = field(default_factory=lambda: cond.Condicoes())
    # Best-of-N (v3.1): {"n": N, "rodadas": k, "perguntas": {pid: {"tentativas", "escolhida", "pontos"}}}.
    # Vazio quando N=1 — a extração de sempre.
    melhor_de_n: dict = field(default_factory=dict)

    def por_id(self, pid: str) -> Resposta | None:
        return next((r for r in self.respostas if r.id == pid), None)

    def pagina(self, arquivo: str, numero: int) -> rec.Pagina | None:
        """Localiza a página citada, resolvendo o nome do arquivo.

        A comparação era por igualdade exata, e isso reprovava evidência CORRETA.
        Duas formas de citação legítima não batiam byte a byte:

          "EDITAL.pdf"                    → sufixo, sem o prefixo de ordenação
          "ARQUIVO 01 - Edital - ...pdf"  → com o RÓTULO do marcador colado

        A segunda vem do prompt, não do modelo: o contexto marca as páginas
        como `=== ARQUIVO <nome> | PÁGINA <n> ===`, e nada ali diz que a palavra
        "ARQUIVO" é rótulo e não parte do nome. O Opus e o Sonnet inferem; o
        Haiku 4.5 copia o que está escrito — que é, a rigor, o comportamento mais
        obediente dos três. O marcador foi desfeito dessa ambiguidade, e aqui
        fica a rede de proteção para as variantes que ainda apareçam.

        A tolerância para no ponto em que começaria a afrouxar a verificação:
        o apelido só é aceito se resolver para UM único arquivo. Havendo dois
        candidatos, a citação é de fato ambígua e continua reprovando.
        """
        alvo = (arquivo or "").strip()
        exato = next((p for p in self.paginas
                      if p.arquivo == alvo and p.numero == numero), None)
        if exato is not None:
            return exato

        chave = _apelido(alvo)
        if not chave:
            return None
        nomes = {p.arquivo for p in self.paginas}
        cands = {n for n in nomes if _casa(_apelido(n), chave)}
        if len(cands) != 1:
            return None
        unico = cands.pop()
        return next((p for p in self.paginas
                     if p.arquivo == unico and p.numero == numero), None)


# ------------------------------------------------- resolução do nome citado
_RUIDO = re.compile(
    r"^(?:===\s*)?(?:arquivo|ficheiro|documento|doc|file)\s*[:\-]?\s*", re.I)


def _apelido(nome: str) -> str:
    """Reduz o nome a uma chave comparável.

    Tira o rótulo do marcador, aspas e pontuação de separação. O que sobra são
    letras e dígitos — o suficiente para reconhecer o arquivo, e pouco o
    bastante para não deixar duas grafias diferentes colidirem por acidente.
    """
    n = (nome or "").strip().strip('"\'`')
    n = _RUIDO.sub("", n)
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", n.lower())


def _casa(nome_real: str, citado: str) -> bool:
    """Um lado conter o outro basta; qual deles contém qual, não importa.

    O modelo tanto encurta o nome ("editalpdf") quanto o alonga com o rótulo
    ("arquivo01editaleditalpdf"). Exigir uma direção só resolveria metade.
    """
    if not nome_real or not citado:
        return False
    return citado in nome_real or nome_real in citado


# ---------------------------------------------------------------- carregamento
def _ordem_precedencia(nome: str) -> int:
    baixo = rec.normalizar(nome)
    for i, marca in enumerate(PRECEDENCIA):
        if marca in baixo:
            return i
    return len(PRECEDENCIA)


def _e_pdf(caminho: str) -> bool:
    """O cabecalho `%PDF` aparece no primeiro KB (a especificacao tolera bytes arbitrarios antes)."""
    try:
        with open(caminho, "rb") as f:
            return b"%PDF" in f.read(1024)
    except OSError:
        return False


def carregar_paginas(pasta: str, progresso=None,
                    observador=None) -> list[rec.Pagina]:
    """
    Lê todos os PDFs da pasta, em ordem de precedência, com OCR quando necessário.

    RN-05: não filtra por tipo de documento. Dispensa não tem arquivo "Edital", e
    filtrar por tipo devolveria nada, em silêncio.
    """
    pdfs = sorted((f for f in os.listdir(pasta) if f.lower().endswith(".pdf")),
                  key=lambda f: (_ordem_precedencia(f), f))
    paginas: list[rec.Pagina] = []
    for nome in pdfs:
        caminho = os.path.join(pasta, nome)
        # PDF PELO CONTEUDO, NAO PELA EXTENSAO.
        #
        # O PNCP entrega ZIP e DOCX com nome terminado em ".pdf" (Camacari/BA,
        # Verdejante/PE, Arraial do Cabo/RJ...). Um so desses derrubava a pasta
        # inteira com `FileDataError` -- e com ela as paginas que se leriam bem,
        # inclusive o conteudo do ZIP, que o download ja extrai ao lado.
        #
        # Pular nao e silencio: o arquivo continua no `_inventario.json`, e o
        # `extrair` o reporta em `condicoes.faltando` como documento nao lido.
        if not _e_pdf(caminho):
            continue
        diag = ocr_mod.diagnosticar(caminho)
        if progresso:
            progresso(nome, diag)
        if observador is not None:
            # A varredura roda no MESMO passe em que o arquivo ja e aberto para
            # ler texto. Custo desprezivel, e a alternativa -- varrer depois --
            # abriria cada PDF duas vezes.
            v = furt.varrer(caminho)
            for a in v.achados[:3]:
                observador.furtivos.append(
                    "%s p.%d: %s" % (a.arquivo, a.pagina, a.motivo))
        if observador is not None and diag.requer_ocr:
            # OCR é condição degradada: o texto foi RECONHECIDO, não extraído.
            # Foi num anexo digitalizado que a pirâmide de São Lourenço veio
            # truncada, e é honesto dizer ao leitor onde isso aconteceu.
            observador.arquivos_ocr.append(nome)
            observador.paginas_ocr += diag.paginas
        textos = ocr_mod.ler_documento(caminho)
        for i, t in enumerate(textos, start=1):
            paginas.append(rec.Pagina(arquivo=nome, numero=i,
                                      texto=ocr_mod.limpar_assinatura(t)))
    return paginas


# ---------------------------------------------------------------- prompts
def _bloco_perguntas(ids: list[str]) -> str:
    linhas = []
    for pid in ids:
        p = POR_ID[pid]
        linha = "%s. %s\n   O que responder: %s" % (p.id, p.texto, p.orienta)
        if p.formato:
            linha += "\n   Formato: %s" % p.formato
        linhas.append(linha)
    return "\n\n".join(linhas)


# A ORDEM DO PROMPT (v3.1).
#
# O cache dos dois provedores casa por PREFIXO. Até a v3.0 a mensagem começava pelas perguntas do lote — que mudam
# a cada lote — e o documento, idêntico nos três lotes, era regravado três vezes: 45,6% da fatura da OpenAI foi
# gravação de cache (Fopa-v2/04-Avaliacao/Resultados medidos.md). Com os documentos primeiro o prefixo é o mesmo
# nos lotes: 1 gravação + 2 leituras. A ordem antiga fica disponível para medir o "antes" com o mesmo código.
ORDENS = ("documentos-primeiro", "perguntas-primeiro")
ORDEM_PADRAO = "documentos-primeiro"
FIM_DOCUMENTOS = "=== FIM DOS DOCUMENTOS ==="
_INSTRUCAO_FINAL = ("Devolva uma resposta para CADA pergunta listada, na ordem, com trecho literal,\n"
                    'arquivo e página física conforme os marcadores "=== ARQUIVO x | PÁGINA n ===".')


def montar_partes(contexto: str, ids: list[str], licitacao: str,
                  ordem: str = ORDEM_PADRAO) -> tuple[str, str]:
    """
    A mensagem do lote em duas partes, `(prefixo, sufixo)`; juntas por uma linha em branco dão o texto inteiro.

    Na ordem nova o prefixo é a licitação + os documentos (igual em todos os lotes: é o que vai para o cache) e o
    sufixo, as perguntas do lote + a instrução final. Na antiga, o texto de sempre, byte a byte.
    """
    if ordem == "perguntas-primeiro":
        return ("LICITAÇÃO: %s\n\nResponda as perguntas abaixo usando EXCLUSIVAMENTE os documentos fornecidos."
                "\n\n%s" % (licitacao, _bloco_perguntas(ids)),
                "=== DOCUMENTOS ===\n\n%s\n\n%s\n\n%s" % (contexto, FIM_DOCUMENTOS, _INSTRUCAO_FINAL))
    if ordem != "documentos-primeiro":
        raise ValueError("ordem do prompt desconhecida: %r (use %s)" % (ordem, " ou ".join(ORDENS)))
    return ("LICITAÇÃO: %s\n\n=== DOCUMENTOS ===\n\n%s\n\n%s" % (licitacao, contexto, FIM_DOCUMENTOS),
            "Responda as perguntas abaixo usando EXCLUSIVAMENTE os documentos acima.\n\n%s\n\n%s"
            % (_bloco_perguntas(ids), _INSTRUCAO_FINAL))


def montar_mensagem(contexto: str, ids: list[str], licitacao: str, ordem: str = ORDEM_PADRAO) -> str:
    return "\n\n".join(montar_partes(contexto, ids, licitacao, ordem))


def usuario_do_lote(contexto: str, ids: list[str], licitacao: str, ordem: str = ORDEM_PADRAO,
                    cache: bool = True):
    """
    O que o provedor recebe: as duas partes na ordem nova, e o Claude põe o cache no prefixo (os documentos); na
    antiga, o texto único de sempre — o "antes" da medição tem de ser a chamada de antes, sem o cache novo.

    `cache=False` (o modo RAG): cada lote recupera páginas diferentes, então o prefixo de documentos nunca se repete
    e marcá-lo cobraria a gravação no cache (1,25×) sem leitura nenhuma — +43% em Bertioga no Claude, pela estimativa
    da medição antes/depois (28/09). Os documentos continuam antes das perguntas, num texto único.
    """
    if ordem == "documentos-primeiro" and cache:
        return montar_partes(contexto, ids, licitacao, ordem)
    return montar_mensagem(contexto, ids, licitacao, ordem)


# ---------------------------------------------------------------- extração
def _paginas_do_lote(paginas: list, grupo: list[str], modo: str, indice, k_rag: int) -> list:
    """As páginas que vão no contexto de um lote: todas em contexto completo; no RAG, as recuperadas para as
    perguntas do lote, na ordem de precedência (RN-14). O reforço do Best-of-N usa a mesma seleção."""
    if modo != "rag":
        return paginas
    escolhidas: dict[tuple[str, int], rec.Pagina] = {}
    for pid in grupo:
        for pg in rec.paginas_para_pergunta(indice, POR_ID[pid], k=k_rag, sempre=SEMPRE_INCLUIR):
            escolhidas[(pg.arquivo, pg.numero)] = pg
    return sorted(escolhidas.values(), key=lambda x: (_ordem_precedencia(x.arquivo), x.arquivo, x.numero))


def respostas_do_lote(dados: dict, grupo: list[str], pular_ausentes: bool = False) -> list[Resposta]:
    """
    As respostas de um lote, na ordem do grupo; pergunta que não veio vira "não localizado".

    `pular_ausentes` (o reforço do Best-of-N): a pergunta que não veio é PULADA, não vira "não localizado". Um
    reforço que volta sem a pergunta é silêncio, não resposta (ADR-011): se virasse ausência, venceria uma original
    reprovada como se o modelo tivesse dito que o dado não existe (revisão da v3.1, 28/09).
    """
    vindas = {r.get("id"): r for r in (dados or {}).get("respostas", [])}
    saida = []
    for pid in grupo:
        r = vindas.get(pid)
        if not r:
            if not pular_ausentes:
                saida.append(Resposta(id=pid, pergunta=POR_ID[pid].texto, resposta=NAO_LOCALIZADO,
                                      confianca="baixa"))
            continue
        saida.append(Resposta(
            id=pid, pergunta=POR_ID[pid].texto,
            resposta=(r.get("resposta") or NAO_LOCALIZADO).strip(),
            arquivo=r.get("arquivo"), pagina=r.get("pagina"),
            trecho_literal=r.get("trecho_literal"),
            conflito=r.get("conflito"),
            confianca=r.get("confianca") or "media"))
    return saida


def extrair(pasta: str, provedor: Provedor, modelo: str = MODELO_EXTRATOR,
            modo: str | None = None, lote: int = 6, k_rag: int = 6,
            effort: str = "high", progresso=None,
            paginas_prontas: list | None = None, ordem: str = ORDEM_PADRAO,
            melhor_de_n: int = 1, modalidade: str | None = None) -> Extracao:
    """
    Extrai as 17 respostas.

    `modo`:
      contexto-completo  todos os documentos em uma requisição por lote de perguntas
      rag                páginas recuperadas por BM25, específicas de cada pergunta
      None               escolhe por tamanho (ver recuperacao.escolher_modo)

    `lote`: quantas perguntas por requisição. Mais perguntas por requisição amortiza
    o custo de reenviar o documento; menos perguntas dá mais atenção a cada uma.
    6 é o meio-termo adotado — e é parâmetro justamente para poder ser medido.
    """
    licitacao = os.path.basename(pasta.rstrip("\\/"))
    # `paginas_prontas` evita refazer OCR quando o harness varre várias configurações
    # sobre o mesmo edital — sem isso, comparar 6 configs custaria 6× o tempo de leitura.
    c = cond.Condicoes()
    esperados = cond.documentos_esperados(pasta)
    paginas = paginas_prontas or carregar_paginas(pasta, progresso=progresso,
                                                  observador=c)
    if not paginas:
        raise ValueError("nenhuma página legível em %s" % pasta)

    modo_efetivo = rec.escolher_modo(paginas, forcado=modo)
    indice = rec.IndiceBM25(paginas) if modo_efetivo == "rag" else None

    ids = [p.id for p in PERGUNTAS]
    lotes = [ids[i:i + lote] for i in range(0, len(ids), lote)]

    respostas: list[Resposta] = []
    # Começa SEM modelo: o nome vem do provedor que de fato respondeu, não do que
    # foi pedido. Inicializar com `modelo` fazia execuções simuladas serem gravadas
    # como se fossem do modelo real — e aí não havia como distinguir um resultado
    # medido de um resultado de ensaio.
    uso_total = Uso()

    def perguntar(grupo: list[str], reforco: bool = False) -> list[Resposta]:
        """Um lote ao modelo: o contexto do lote, a chamada, o custo somado, as respostas lidas. No reforço, a
        pergunta que não veio é pulada (`respostas_do_lote(pular_ausentes=True)`)."""
        contexto = rec.montar_contexto(_paginas_do_lote(paginas, grupo, modo_efetivo, indice, k_rag))
        dados, uso = provedor.responder_json(
            sistema=instrucao_sistema(),
            usuario=usuario_do_lote(contexto, grupo, licitacao, ordem, cache=modo_efetivo != "rag"),
            esquema=ESQUEMA_LOTE, modelo=modelo, effort=effort)
        uso_total.somar(uso)
        return respostas_do_lote(dados, grupo, pular_ausentes=reforco)

    for grupo in lotes:
        respostas.extend(perguntar(grupo))
    respostas.sort(key=lambda r: int(r.id[1:]))

    # Best-of-N (v3.1): até N-1
    # rodadas de reforço; cada uma manda ao modelo SÓ as perguntas que ainda falham, considerando o melhor
    # candidato já obtido, com o mesmo contexto do lote normal. Para cedo quando não sobra falha. A escolha é do
    # Verificador (melhor_de_n.py), nunca de um modelo.
    registro_n: dict = {}
    if melhor_de_n > 1:
        from . import melhor_de_n as bon       # tardio: melhor_de_n importa o verificador, que importa este módulo
        base = Extracao(licitacao=licitacao, respostas=respostas, paginas=paginas, modo=modo_efetivo)
        candidatos: dict[str, list[Resposta]] = {}
        tentadas: dict[str, int] = {}
        rodadas = 0
        for _ in range(melhor_de_n - 1):
            atual = Extracao(licitacao=licitacao, paginas=paginas, modo=modo_efetivo, respostas=[
                bon.escolher(r, candidatos[r.id], base)[0] if r.id in candidatos else r for r in respostas])
            pendentes = bon.falhas(atual, modalidade)
            if not pendentes:
                break
            rodadas += 1
            for i in range(0, len(pendentes), lote):
                grupo = pendentes[i:i + lote]
                for pid in grupo:
                    tentadas[pid] = tentadas.get(pid, 0) + 1
                try:
                    novas = perguntar(grupo, reforco=True)
                except ErroModelo:
                    # o reforço é best-effort: a tentativa conta no registro e fica o que já havia — um reforço que
                    # falha não pode jogar fora os lotes já pagos (revisão da v3.1, 28/09)
                    continue
                for r in novas:
                    candidatos.setdefault(r.id, []).append(r)
        registro_n = {"n": melhor_de_n, "rodadas": rodadas,
                      "perguntas": bon.aplicar(base, candidatos, tentadas) if tentadas else {}}
    c.esperados = len(esperados)
    c.obtidos = len({p.arquivo for p in paginas})
    c.faltando = cond.nao_lidos(esperados, {p.arquivo for p in paginas})
    c.provedor = getattr(provedor, "nome", "")
    c.modelo = uso_total.modelo or modelo
    c.effort = effort
    # "simulado" NAO e provedor secundario: e ensaio, e ja se identifica como
    # tal em `uso.modelo`. Marcar ensaio como degradacao fazia toda execucao de
    # custo zero aparecer como leitura comprometida - ruido que ensinaria o
    # leitor a ignorar o aviso, que e o pior destino de um aviso.
    c.secundario = c.provedor not in ("claude", "simulado", "")
    # tres niveis: fopa/ -> scripts/ -> raiz do projeto, onde mora saidas/
    c.corpus_horas = cond.idade_do_corpus(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    c.abstencoes = [r.id for r in respostas
                    if r.resposta.strip().lower().startswith(NAO_LOCALIZADO.lower())]

    return Extracao(licitacao=licitacao, respostas=respostas, paginas=paginas,
                    modo=modo_efetivo, uso=uso_total,
                    arquivos=sorted({p.arquivo for p in paginas}),
                    # o nome vem do provedor que DE FATO respondeu, pelo mesmo
                    # motivo que `uso.modelo` vem: um ensaio não pode ficar
                    # gravado como se fosse a execução real
                    provedor=getattr(provedor, "nome", ""), effort=effort,
                    condicoes=c, melhor_de_n=registro_n)


__all__ = ["Resposta", "Extracao", "extrair", "carregar_paginas",
           "montar_mensagem", "montar_partes", "usuario_do_lote", "respostas_do_lote", "ORDENS", "ORDEM_PADRAO",
           "FIM_DOCUMENTOS", "SEMPRE_INCLUIR", "PRECEDENCIA"]
