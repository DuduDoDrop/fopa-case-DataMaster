# -*- coding: utf-8 -*-
"""
Página HTML por edital — o entregável que a planilha não consegue ser.

A vantagem sobre o .xlsx é uma só, e é decisiva: cada resposta tem um link que
**abre o PDF na página citada**. A RN-01 deixa de ser promessa e vira dois cliques.

O arquivo é autocontido (CSS inline, sem rede) e fica ao lado dos PDFs, para que
os links relativos funcionem ao abrir direto do disco.
"""
from __future__ import annotations

import html
import json
import os
import urllib.parse
from datetime import date

from . import distribuicao
from .extrator import Extracao
from .questionario import POR_ID
from .verificador import Relatorio, APROVADO, REVISAR, REPROVADO, nao_encontrou



def _num(v) -> str:
    """Inteiro no padrão brasileiro: 1408 vira 1.408.

    A pirâmide é lida por quem precisa comparar faixas de olho, e sem separador
    "1408" e "148" têm quase a mesma largura visual. Num documento em que a
    diferença entre 1.408 e 1.896 é o achado principal, isso não é detalhe.
    """
    return ("{:,}".format(int(v))).replace(",", ".")


def _brl(v) -> str:
    """R$ com separador de milhar. A troca ingênua de ponto por vírgula não o põe.

    `"%0.2f" % 527400.0` devolve "527400.00" — o formato do Python não agrupa
    milhar. Trocar ponto por vírgula produzia "R$ 527400,00", que é legível por
    esforço e errado por convenção.
    """
    try:
        return "R$ " + ("{:,.2f}".format(float(v))
                        .replace(",", "\x00").replace(".", ",").replace("\x00", "."))
    except (TypeError, ValueError):
        return ""


def _tabela_distribuicao(resposta: str) -> str:
    """Estrutura a distribuição que a Q13 devolve em prosa.

    A distribuição é o insumo mais caro da folha e chega como uma frase de
    quinze linhas. Quem confere precisa somar de cabeça, e quem lê rápido não
    percebe que o edital trouxe servidores por VÍNCULO em vez de por faixa
    salarial — que é outra informação, e não serve para precificar.

    A barra é proporção, não enfeite: é onde a concentração da folha aparece
    sem ninguém calcular nada.
    """
    d = distribuicao.ler(resposta)
    if not d.grupos:
        return ""

    partes = []
    if not d.por_faixa:
        partes.append(
            '<p class="avisodist"><b>Não é pirâmide por faixa salarial.</b> '
            'O edital trouxe a distribuição por <b>%s</b> — sem faixa não há '
            'ticket médio nem estimativa de consignado.</p>' % _e(d.tipo))
    elif d.parcial and not d.completa:
        partes.append(
            '<p class="avisodist"><b>Leitura incompleta.</b> A própria resposta '
            'declara que falta dado: a soma abaixo não representa a população.</p>')

    maior = max((l.quantidade for l in d.linhas), default=0) or 1
    for g in d.grupos:
        linhas = []
        for l in g.linhas:
            pct = int(round(100.0 * l.quantidade / maior))
            valor = _brl(l.valor) if l.valor is not None else ""
            linhas.append(
                '<tr><td class="dl">%s</td><td class="dq">%s</td>'
                '<td class="db"><span style="width:%d%%"></span></td>'
                '<td class="dv">%s</td></tr>'
                % (_e(l.rotulo), _num(l.quantidade), pct, _e(valor)))

        if g.confere is True:
            rodape = ('<tr class="dt"><td>total</td><td class="dq">%s</td>'
                      '<td colspan="2" class="dok">confere com o total impresso</td></tr>'
                      % _num(g.soma))
        elif g.confere is False:
            rodape = ('<tr class="dt"><td>soma</td><td class="dq">%s</td>'
                      '<td colspan="2" class="dbad">total impresso: %s — diverge</td></tr>'
                      % (_num(g.soma), _num(g.total_declarado)))
        else:
            rodape = ('<tr class="dt"><td>soma das linhas</td><td class="dq">%s</td>'
                      '<td colspan="2" class="dmut">sem total impresso para conferir</td></tr>'
                      % _num(g.soma))

        titulo = ('<caption>%s</caption>' % _e(g.nome)) if g.nome else ""
        partes.append('<table class="dist">%s%s%s</table>'
                      % (titulo, "".join(linhas), rodape))

    if len(d.grupos) > 1:
        partes.append('<p class="somatot">%d tabelas &middot; %s: <b>%s</b></p>'
                      % (len(d.grupos), _e(d.rotulo_soma), _num(d.soma)))

    return ('<details open><summary>distribuição estruturada (%d linha%s)</summary>'
            '%s</details>'
            % (len(d.linhas), "" if len(d.linhas) == 1 else "s", "".join(partes)))

CRITICAS = tuple(p.id for p in POR_ID.values() if p.critico)


def _e(s) -> str:
    return html.escape(str(s or ""))


def _link_pdf(arquivo: str | None, pagina: int | None,
              base_pdf_url: str = "", url_por_arquivo: dict | None = None) -> str:
    """
    Link para a página física do PDF.

    `#page=N` é entendido por Chrome, Edge, Firefox e Acrobat. Sem base nem
    mapa, o HTML fica na mesma pasta dos PDFs e o caminho relativo resolve sem
    servidor — é o comportamento de sempre, e o único que troca só `#` e espaço.

    Na v3 os PDFs moram num storage, não ao lado do HTML, e aí há duas formas
    de chegar neles, nesta ordem: `url_por_arquivo` (URL assinada, uma por
    arquivo — vence porque já vem pronta) e `base_pdf_url` + nome codificado.
    O `quote(safe='')` é deliberado: nome de anexo do PNCP traz `%`, `?` e `&`,
    e qualquer um deles solto no caminho quebra a URL em silêncio.
    """
    if not arquivo:
        return ""
    pronta = (url_por_arquivo or {}).get(arquivo)
    if pronta:
        destino = pronta
    elif base_pdf_url:
        destino = base_pdf_url + urllib.parse.quote(arquivo, safe="")
    else:
        destino = arquivo.replace("#", "%23").replace(" ", "%20")
    return "%s#page=%d" % (destino, pagina) if pagina else destino


CSS = """
:root{color-scheme:light;--ink:#11243D;--ink2:#1B3454;--paper:#FFFFFF;--surf:#FFFFFF;--surf2:#F4F2EE;
--line:#DCD7CC;--muted:#55606E;--red:#B23A32;--reds:#F6E4E2;--teal:#1D6F63;
--teals:#DDEAE7;--amber:#8A6A18;--ambers:#F5EBD2;
--sans:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif;
--mono:'IBM Plex Mono',ui-monospace,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
font-size:15px;line-height:1.55;padding-inline:16px}
.wrap{max-width:1180px;margin-inline:auto;padding-block:32px 64px;
display:flex;flex-direction:column;gap:22px}
header h1{font-size:30px;font-weight:600;margin:0 0 6px;line-height:1.2}
.sub{color:var(--muted);margin:0;font-size:14.5px}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.16em;
text-transform:uppercase;color:var(--red);margin:0 0 8px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--surf);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.tile b{display:block;font-family:var(--mono);font-size:22px;font-variant-numeric:tabular-nums}
.tile span{font-size:12.5px;color:var(--muted)}
.tile.ok b{color:var(--teal)} .tile.al b{color:var(--red)}
table{width:100%;border-collapse:collapse;background:var(--surf);
border:1px solid var(--line);border-radius:10px;overflow:hidden}
th{background:var(--ink);color:var(--paper);text-align:left;font-size:12.5px;
letter-spacing:.06em;text-transform:uppercase;padding:11px 14px;font-weight:600}
td{padding:13px 14px;border-top:1px solid var(--line);vertical-align:top;
font-size:14.5px;overflow-wrap:anywhere}
tr:hover td{background:var(--surf2)}
/* O nowrap existe para o CÓDIGO da pergunta ("Q13"), que não pode quebrar no
   meio. Ele herdava para o texto da pergunta aninhado, que então não quebrava
   linha nenhuma e transbordava por cima da coluna da resposta. */
.qid{font-family:var(--mono);font-weight:600;white-space:nowrap;
width:23ch;min-width:15ch}
.perg{color:var(--muted);font-size:13px;display:block;margin-top:4px;
white-space:normal;overflow-wrap:anywhere;font-family:var(--sans);
font-weight:400;line-height:1.4}
.info a{font-family:var(--mono);font-size:12.5px;color:var(--teal);
text-decoration:none;border-bottom:1px dotted var(--teal);word-break:break-all}
.info a:hover{background:var(--teals)}
.nl{font-family:var(--mono);font-size:12.5px;color:var(--muted)}
.v{font-family:var(--mono);font-size:11.5px;padding:3px 8px;border-radius:999px;
white-space:nowrap;border:1px solid transparent}
.v.APROVADO{background:var(--teals);color:var(--teal);border-color:var(--teal)}
.v.REVISAR{background:var(--ambers);color:var(--amber);border-color:var(--amber)}
.v.REPROVADO{background:var(--reds);color:var(--red);border-color:var(--red)}
/* A barra da pergunta crítica era VERMELHA, e vermelho no resto do relatório
   significa defeito: trecho não conferido, soma que não bate, evidência
   ausente. Uma linha perfeita, aprovada e ancorada, aparecia marcada como se
   houvesse algo errado só por ser importante.
   Importância e problema são eixos diferentes e agora têm cores diferentes: a
   crítica ganha a cor da tinta e um rótulo que diz o que é. */
/* A BARRA DA PRIMEIRA COLUNA CODIFICA O STATUS, e nada mais.
   Antes ela marcava "pergunta crítica" — e importância não é status: uma
   crítica perfeita aparecia marcada como se houvesse algo errado. A crítica
   passou a ser um RÓTULO de texto (.marca), e a barra ficou livre para dizer
   a única coisa que o leitor precisa ver de relance:
       verde     conferido — o trecho existe na página citada
       âmbar     precisa de olho humano — página corrigida, conflito, regra
       vermelho  não localizado — a resposta não está nos documentos
   Três cores, três significados, nenhum acúmulo. */
tr.st-ok td:first-child{box-shadow:inset 3px 0 0 var(--teal)}
tr.st-rev td:first-child{box-shadow:inset 3px 0 0 var(--amber)}
tr.st-nl td:first-child{box-shadow:inset 3px 0 0 var(--red)}
/* CONDICOES DE OPERACAO — o que o sistema sabe sobre a propria execucao.
   Fica ACIMA do questionario de proposito: quem le as respostas precisa saber
   antes, nao depois, se a leitura aconteceu com um documento faltando ou com
   OCR num anexo digitalizado. */
/* A TAG e deliberadamente mais forte que o resto do bloco de condicoes.
   As outras condicoes dizem "leia com ressalva"; esta diz "alguem tentou
   manipular este documento". Sao categorias diferentes de aviso. */
.tagsusp{display:inline-block;background:var(--red);color:#fff;
font-family:var(--mono);font-size:11.5px;font-weight:600;letter-spacing:.04em;
padding:4px 10px;border-radius:6px;margin:0 0 10px}
/* ENSAIO: execução do simulado ou replay do gravado. Âmbar de propósito — é
   "não use para decidir", não o vermelho de "alguém manipulou o documento". */
.tagensaio{display:inline-block;background:var(--ambers);color:var(--amber);
border:1px solid var(--amber);font-family:var(--mono);font-size:11.5px;
font-weight:600;letter-spacing:.04em;padding:4px 10px;border-radius:6px;margin:0}
.cond{margin:0 0 18px;padding:14px 16px;border-radius:10px;
border:1px solid var(--line);background:var(--surf);font-size:13.5px;
line-height:1.5}
.cond.deg{border-left:4px solid var(--amber);background:var(--ambers)}
.cond.ok{border-left:4px solid var(--teal)}
.cond b{font-family:var(--sans);letter-spacing:.02em}
.cond ul{margin:7px 0 0;padding-left:18px}
.cond li{margin:3px 0;color:var(--ink)}
.cond .meta{color:var(--muted);font-family:var(--mono);font-size:12px;
margin-top:8px;display:block}
.legenda{display:flex;align-items:center;gap:14px;margin:0 0 10px;
flex-wrap:wrap}
.lg{font-size:12px;font-family:var(--mono);color:var(--muted);
padding-left:11px;position:relative}
.lg::before{content:"";position:absolute;left:0;top:50%;transform:translateY(-50%);
width:3px;height:13px;border-radius:2px}
.lg-ok::before{background:var(--teal)}
.lg-rev::before{background:var(--amber)}
.lg-nl::before{background:var(--red)}
.lgnota{font-size:11.5px;color:var(--muted);font-style:italic}
.marca{display:inline-block;font-family:var(--mono);font-size:10.5px;
letter-spacing:.08em;text-transform:uppercase;color:var(--ink2);
border:1px solid var(--line);border-radius:4px;padding:1px 5px;margin-top:5px}
details{margin-top:9px}
summary{cursor:pointer;font-size:12.5px;color:var(--muted);font-family:var(--mono)}
summary:hover{color:var(--ink)}
blockquote{margin:9px 0 0;padding:10px 13px;background:var(--surf2);
border-left:3px solid var(--line);font-size:13.5px;color:var(--ink);
font-family:var(--mono);line-height:1.5;white-space:pre-wrap}
.conf{border-left-color:var(--amber);background:var(--ambers)}
.naoaplica{border-left-color:var(--teal);background:var(--teals);color:var(--teal);font-family:var(--sans)}
.semev{border-left-color:var(--muted);background:var(--surf2);color:var(--muted);font-family:var(--sans);font-style:italic}
.faltaev{border-left-color:var(--red);background:var(--reds);color:var(--red);font-family:var(--sans)}
/* Distribuição estruturada da Q13 */
.avisodist{margin:9px 0 0;padding:10px 13px;background:var(--ambers);
color:var(--amber);border-left:3px solid var(--amber);font-size:13.5px;
line-height:1.45;border-radius:0 6px 6px 0}
table.dist{width:100%;margin:10px 0 0;border:1px solid var(--line);
border-radius:8px;font-size:13px;background:var(--surf)}
table.dist caption{caption-side:top;text-align:left;font-family:var(--mono);
font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;
color:var(--muted);padding:8px 12px 5px}
table.dist td{padding:6px 12px;border-top:1px solid var(--line);font-size:13px;
vertical-align:middle}
table.dist tr:first-child td{border-top:none}
.dl{color:var(--ink2);white-space:nowrap;padding-right:10px}
.dq{font-family:var(--mono);text-align:right;width:11ch;min-width:9ch;
white-space:nowrap;font-variant-numeric:tabular-nums;font-weight:600}
.db{width:42%;padding-right:14px}
.db span{display:block;height:9px;border-radius:3px;background:var(--teal);
min-width:2px}
.dv{font-family:var(--mono);font-size:12px;color:var(--muted);text-align:right;
white-space:nowrap}
tr.dt td{border-top:2px solid var(--line);background:var(--surf2);
font-weight:600}
.dok{font-size:12px;color:var(--teal);font-family:var(--mono)}
.dbad{font-size:12px;color:var(--red);font-family:var(--mono)}
.dmut{font-size:12px;color:var(--muted);font-family:var(--mono)}
.somatot{margin:9px 0 0;font-size:13px;color:var(--muted);font-family:var(--mono)}
h2{font-size:18px;margin:14px 0 0;font-weight:600}
.nota{background:var(--surf);border:1px solid var(--line);border-left:4px solid var(--red);
border-radius:8px;padding:14px 16px;font-size:14px}
/* Voltar ao painel. Sem isto o único caminho de volta é o botão do navegador,
   e quem abre o relatório por duplo clique no arquivo não tem histórico nenhum
   para voltar. */
.voltar{display:inline-flex;align-items:center;gap:7px;text-decoration:none;
font-size:13.5px;color:var(--ink2);background:var(--surf);padding:8px 14px;
border:1px solid var(--line);border-radius:8px;align-self:flex-start}
.voltar:hover{border-color:var(--ink2);background:var(--surf2)}
.voltar b{font-family:var(--mono);color:var(--red)}
.rodape-nav{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
footer{border-top:1px solid var(--line);padding-top:14px;font-size:12.5px;color:var(--muted)}
/* NO CELULAR o questionário vira uma pilha de cartões. As 4 colunas não
   cabem em 390px: o # tem 15ch de mínimo e o selo do veredito não quebra, e a
   tabela passava da tela (400px a 641px nas amostras). Cada linha passa a ser
   código e pergunta, resposta, e a origem ao lado do veredito; a barra de
   status sai da primeira célula e marca o cartão inteiro. */
@media(max-width:640px){.perg{max-width:none}td,th{padding:10px}
table.q thead{display:none}
table.q,table.q tbody{display:block}
table.q tr{display:grid;grid-template-columns:minmax(0,1fr) auto;
column-gap:10px;border-top:1px solid var(--line)}
table.q tbody tr:first-child{border-top:none}
table.q td{display:block;border-top:none;padding:8px 12px}
table.q td.qid{grid-column:1/-1;width:auto;min-width:0;padding-top:12px}
table.q td:nth-child(2){grid-column:1/-1}
table.q td:nth-child(4){align-self:center;padding-bottom:12px}
table.q td.info{padding-bottom:12px}
table.q tr td:first-child{box-shadow:none}
table.q tr.st-ok{box-shadow:inset 3px 0 0 var(--teal)}
table.q tr.st-rev{box-shadow:inset 3px 0 0 var(--amber)}
table.q tr.st-nl{box-shadow:inset 3px 0 0 var(--red)}}
@media print{body{background:#fff}.tile,table{break-inside:avoid}}
"""


# Provedores de ENSAIO (ADR-012): nenhum deles é extração de verdade. O W23 da v3
# grava o modelo CONFIGURADO também no simulado, e o relatório saía dizendo
# "modelo claude-opus-5" com "R$ 0,00": uma extração real de graça, para quem lê.
ENSAIO = {"simulado": "respostas geradas pelo simulador, sem modelo nenhum",
          "gravado": "replay de chamadas gravadas de uma extração anterior, sem chamada paga"}


def escrever(ext: Extracao, rel: Relatorio, destino: str,
             link_pncp: str = "", base_pdf_url: str = "",
             url_por_arquivo: dict | None = None,
             link_voltar: str = "../index.html") -> str:
    """Escreve o relatório HTML. Os defaults reproduzem o layout de disco:
    PDFs ao lado do HTML e o painel um nível acima. A v3 passa `base_pdf_url`
    ou `url_por_arquivo` (ver `_link_pdf`) e o `link_voltar` da sua própria
    rota; nada muda para quem chama sem eles.
    """
    crit_ok = sum(1 for r in ext.respostas
                  if r.id in CRITICAS and r.veredito == APROVADO)
    conflitos = [r for r in ext.respostas if r.conflito]

    def link(arquivo, pagina):
        return _link_pdf(arquivo, pagina, base_pdf_url, url_por_arquivo)

    # Legado importado sem leitura: não há páginas congeladas para linkar, e
    # "0 páginas" diria que o edital está vazio — o que não é verdade.
    paginas = ("páginas não congeladas" if not ext.paginas
               else "%d páginas" % len(ext.paginas))

    provedor = getattr(ext, "provedor", "") or ""
    ensaio = ENSAIO.get(provedor)
    modelo = (ext.uso.modelo or "-") + (" (provedor %s)" % provedor if ensaio else "")
    L = ['<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         "<title>%s — FOPA</title><style>%s</style></head><body>" % (_e(ext.licitacao), CSS),
         '<div class="wrap">',
         '<a class="voltar" href="%s"><b>&larr;</b> Voltar ao painel</a>' % _e(link_voltar),
         "<header>",
         '<p class="eyebrow">FOPA · extração verificada</p>',
         "<h1>%s</h1>" % _e(ext.licitacao),
         '<p class="sub">%d arquivos · %s · modo <code>%s</code> · modelo <code>%s</code>%s · '
         'gerado em %s</p>' % (len(ext.arquivos), paginas, _e(ext.modo),
                               _e(ext.uso.modelo or "-"),
                               " · provedor <code>%s</code>" % _e(provedor) if ensaio else "",
                               date.today().strftime("%d/%m/%Y"))]
    if ensaio:
        L.append('<p class="tagensaio">ENSAIO · provedor %s — %s. Não use para decidir.</p>'
                 % (_e(provedor), _e(ensaio)))
    L.append("</header>")

    if link_pncp:
        L.append('<p class="sub">Origem: <a href="%s">%s</a></p>' % (_e(link_pncp), _e(link_pncp)))

    # ---- painel
    L += ['<div class="tiles">',
          '<div class="tile %s"><b>%d/%d</b><span>ancoragem verificada</span></div>'
          % ("ok" if rel.taxa_ancorada >= 0.95 else "al", rel.ancoradas, rel.respondidas),
          '<div class="tile"><b>%d</b><span>aprovadas sem ressalva</span></div>' % rel.aprovadas,
          '<div class="tile %s"><b>%d</b><span>para revisão</span></div>'
          % ("al" if rel.revisar else "", rel.revisar),
          '<div class="tile %s"><b>%d</b><span>reprovadas</span></div>'
          % ("al" if rel.reprovadas else "ok", rel.reprovadas),
          '<div class="tile"><b>%d/%d</b><span>críticas aprovadas</span></div>'
          % (crit_ok, len(CRITICAS)),
          # "R$ 0,00" para modelo sem tabela de preço é enganoso: a chamada
          # foi cobrada. Mesma regra do `saida.py`, que grava `null` no JSON.
          # Foi assim que 93 relatórios do agente saíram dizendo "de graça".
          ('<div class="tile"><b>%s</b><span>custo da extração</span></div>' % _brl(ext.uso.brl)
           if ext.uso.preco_conhecido
           else '<div class="tile"><b>—</b><span>preço não configurado</span></div>'),
          "</div>"]

    L.append('<div class="nota"><b>Como conferir:</b> cada resposta cita arquivo e '
             '<b>página física</b>. Clique no link em <i>Origem</i> para abrir o PDF '
             'exatamente naquela página. O trecho literal, sob “ver evidência”, foi '
             'conferido por comparação de string contra o texto daquela página — '
             'sem IA. <b>Toda</b> resposta traz o bloco de evidência: quando ele diz '
             'que não há trecho, isso também é resultado, não omissão. '
             'Perguntas marcadas <b>crítica</b> são as que movem o lance; '
             'o vermelho, aqui, é sempre defeito.</div>')

    if rel.alertas_globais:
        L.append('<h2>Alertas</h2><div class="nota">' +
                 "<br>".join("⚠ " + _e(g) for g in rel.alertas_globais) + "</div>")

    # ---- condições de operação
    c = getattr(ext, "condicoes", None)
    if c is not None and (c.motivos() or c.abstencoes or c.modelo):
        cls = "deg" if c.degradada else "ok"
        titulo = ("Esta leitura aconteceu sob condição degradada"
                  if c.degradada else "Condições normais de leitura")
        bloco = ['<div class="cond %s">' % cls]
        for t in c.tags():
            bloco.append('<span class="tagsusp">%s</span><br>' % _e(t))
        bloco.append('<b>%s</b>' % _e(titulo))
        if c.motivos():
            bloco.append("<ul>%s</ul>"
                         % "".join("<li>%s</li>" % _e(m) for m in c.motivos()))
        elif not c.abstencoes:
            bloco.append("<ul><li>Todos os documentos do inventário foram lidos, "
                         "nenhum exigiu OCR, e o modelo principal respondeu.</li></ul>")
        if c.abstencoes:
            bloco.append('<ul><li>O sistema <b>absteve-se</b> em %d pergunta(s): '
                         '%s — evidência procurada e não encontrada.</li></ul>'
                         % (len(c.abstencoes), _e(", ".join(c.abstencoes))))
        bloco.append('<span class="meta">%s · %s · %d de %d documento(s) · '
                     'corpus há %s</span>'
                     % (_e(c.modelo or "?"), _e("effort " + (c.effort or "?")),
                        c.obtidos, c.esperados or c.obtidos,
                        ("%.0fh" % c.corpus_horas) if c.corpus_horas is not None
                        else "—"))
        bloco.append("</div>")
        L += ["<h2>Condições desta execução</h2>", "".join(bloco)]

    # ---- questionário
    L += ['<h2>Questionário</h2>',
          '<p class="legenda">'
          '<span class="lg lg-ok">conferido</span>'
          '<span class="lg lg-rev">revisar</span>'
          '<span class="lg lg-nl">não localizado</span>'
          '<span class="lgnota">a barra à esquerda de cada linha</span>'
          '</p>',
          '<table class="q"><thead><tr>',
          "<th>#</th><th>Resposta</th><th>Origem</th><th>Verificação</th>",
          "</tr></thead><tbody>"]
    for r in ext.respostas:
        # A classe da linha sai do STATUS, não da importância. "Não localizado"
        # vence o veredito: uma ausência ancorada continua sendo uma ausência,
        # e é isso que o leitor precisa enxergar primeiro.
        if nao_encontrou(r.resposta) or not r.arquivo:
            estado = "st-nl"
        elif r.veredito == APROVADO:
            estado = "st-ok"
        else:
            estado = "st-rev"
        classes = [estado] + (["crit"] if r.id in CRITICAS else [])
        crit = ' class="%s"' % " ".join(classes)
        if nao_encontrou(r.resposta) or not r.arquivo:
            origem = '<span class="nl">não localizado</span>'
        else:
            # O link vai para o nome RESOLVIDO pelo verificador; o texto mostra
            # o que o modelo citou, que é o que o leitor vai conferir.
            origem = '<a href="%s">%s%s</a>' % (
                _e(link(r.arquivo_canonico or r.arquivo, r.pagina)), _e(r.arquivo),
                " — p. %d" % r.pagina if r.pagina else "")
        celula = _e(r.resposta).replace("\n", "<br>")
        if r.id == "Q13":
            celula += _tabela_distribuicao(r.resposta)
        # O bloco de evidência aparece SEMPRE, mesmo vazio.
        #
        # Antes ele só existia quando havia trecho, e a ausência ficava
        # invisível: quem percorre 17 linhas não repara numa que não tem o
        # botão. Num relatório cuja tese é "nada entra sem evidência", evidência
        # faltando é a informação mais importante da linha — e era a única que
        # não estava escrita.
        #
        # Os dois casos de ausência são diferentes e o texto distingue: não ter
        # trecho porque a informação não existe no edital é resposta correta;
        # não ter trecho tendo respondido é defeito.
        if r.trecho_literal:
            celula += ('<details><summary>ver evidência</summary>'
                       '<blockquote>%s</blockquote></details>'
                       % _e(r.trecho_literal))
        elif nao_encontrou(r.resposta):
            # Três motivos diferentes para não haver trecho, e o leitor precisa
            # saber qual é: a pergunta não cabe nesta modalidade, a informação
            # não consta do edital, ou o sistema não achou. O primeiro caso não
            # é lacuna nenhuma.
            motivo = next((a for a in r.alertas
                           if a.startswith("não se aplica a esta modalidade")), "")
            if motivo:
                celula += ('<details><summary>ver evidência</summary>'
                           '<blockquote class="naoaplica"><b>Não se aplica a esta '
                           'modalidade.</b> %s. A pergunta foi desenhada para '
                           'pregão e concorrência; aqui não há o que citar.'
                           '</blockquote></details>'
                           % _e(motivo.split("—", 1)[-1].strip()))
            else:
                celula += ('<details><summary>ver evidência</summary>'
                           '<blockquote class="semev">Sem trecho porque a informação '
                           'não consta dos documentos. A ausência é a resposta, e é '
                           'candidata a pedido de esclarecimento ao órgão.'
                           '</blockquote></details>')
        else:
            celula += ('<details open><summary>ver evidência</summary>'
                       '<blockquote class="faltaev"><b>Evidência não encontrada.</b> '
                       'A resposta foi dada sem trecho literal, então não pode ser '
                       'conferida contra o documento — não use sem revisar na fonte.'
                       '</blockquote></details>')
        if r.conflito:
            celula += ('<details open><summary>conflito entre documentos</summary>'
                       '<blockquote class="conf">%s</blockquote></details>'
                       % _e(r.conflito))
        if r.alertas:
            celula += ('<details><summary>%d alerta(s) da verificação</summary>'
                       '<blockquote>%s</blockquote></details>'
                       % (len(r.alertas), _e(" · ".join(r.alertas))))
        marca = ('<span class="marca" title="entra no cálculo do lance">'
                 'crítica</span>') if r.id in CRITICAS else ""
        L += ["<tr%s><td class=\"qid\">%s<span class=\"perg\">%s</span>%s</td>"
              % (crit, r.id, _e(r.pergunta), marca),
              "<td>%s</td>" % celula,
              '<td class="info">%s</td>' % origem,
              '<td><span class="v %s">%s</span></td></tr>' % (r.veredito, r.veredito)]
    L.append("</tbody></table>")

    # ---- conflitos em destaque
    if conflitos:
        L.append("<h2>Divergências entre documentos (%d)</h2><table><thead><tr>"
                 "<th>#</th><th>O que diverge</th><th>Resposta adotada</th>"
                 "</tr></thead><tbody>" % len(conflitos))
        for r in conflitos:
            L += ["<tr><td class=\"qid\">%s</td><td>%s</td><td>%s</td></tr>"
                  % (r.id, _e(r.conflito), _e(r.resposta[:220]))]
        L.append("</tbody></table>")

    # ---- arquivos
    L.append("<h2>Documentos lidos</h2><table><thead><tr><th>Arquivo</th>"
             "<th>Páginas</th></tr></thead><tbody>")
    for a in ext.arquivos:
        n = sum(1 for p in ext.paginas if p.arquivo == a)
        L.append('<tr><td><a href="%s" class="info">%s</a></td><td>%d</td></tr>'
                 % (_e(link(a, None)), _e(a), n))
    L.append("</tbody></table>")

    L += ['<div class="rodape-nav">',
          '<a class="voltar" href="%s"><b>&larr;</b> Voltar ao painel</a>' % _e(link_voltar),
          '<a class="voltar" href="#">Voltar ao topo</a>',
          "</div>",
          "<footer>Gerado pelo pipeline FOPA · %s · %d chamada(s) ao modelo · "
          "%s tokens de entrada · verificação determinística, sem IA</footer>"
          % (_e(modelo), ext.uso.chamadas,
             f"{ext.uso.entrada:,}".replace(",", ".")),
          "</div></body></html>"]

    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return destino


__all__ = ["escrever"]
