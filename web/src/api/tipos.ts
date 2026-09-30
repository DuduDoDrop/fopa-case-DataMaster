/**
 * O CONTRATO da fopa-api como ela responde de verdade (api/site.py +
 * api/consultas.py) — não como o site gostaria que fosse.
 *
 * Os corpos gravados da API real (`src/__fixtures__/contrato/*.json`, feitos
 * por `web/scripts/gerar_fixtures.py`) são atribuídos a estes tipos em
 * `src/__fixtures__/contrato.ts`: um campo obrigatório aqui que a API não
 * manda quebra o `tsc` do build. Por isso:
 *
 * - campo que a API manda hoje é OBRIGATÓRIO aqui (com `| null` quando a
 *   coluna pode ser NULL); campo que outra frente ainda está acrescentando
 *   (Jev, recorte, n8n na saúde, rótulos de escopo) é OPCIONAL (`?:`) e a
 *   tela não pode quebrar sem ele;
 * - texto que vem de coluna `text` é `string` (papel, veredito, ausência,
 *   status): a API não promete o literal, e a tela compara;
 * - `numeric` pode chegar como número ou string: valores em reais e taxas são
 *   `number | string` e passam por `numero()`. Custo NULL é "preço não
 *   configurado", nunca 0.
 *
 * Os nomes são os das colunas de `v_card`/`v_detalhe` (db/010_views.sql) e
 * das tabelas: a API devolve a linha como está.
 */

export type Papel = 'leitor' | 'operador' | 'admin';
export type Num = number | string;

export interface Me {
  email: string;
  papel: string;
  nome: string | null;
  /** o admin supremo (db/046): o único que dá e tira acesso */
  supremo?: boolean;
}

/** Envelope das listas paginadas no servidor (`/api/licitacoes`, `/api/execucoes`, `/api/emails`). */
export interface Pagina<T> {
  total: number;
  page: number;
  por_pagina: number;
  paginas: number;
  itens: T[];
  /** só em /api/licitacoes: o recorte aplicado (`ano_minimo` | `todos`) */
  recorte?: string;
}

// ------------------------------------------------------------------ Jev (campos novos, opcionais)
/** Sinal do Jev sobre o filtro de escopo: score, nunca decisão. */
export interface JevFiltro {
  p_filtro_ok: Num | null;
  /** a chance de SER folha, na opinião do Jev — o que a tela mostra desde 26/09 (ausente em API anterior) */
  p_folha?: Num | null;
  discorda: boolean;
  candidata: boolean;
}

export interface JevResumo {
  escopo_avaliadas: number;
  escopo_discordancias: number;
  p_filtro_ok_medio: Num | null;
}

export interface JevSustenta {
  p_sustenta: Num | null;
  resposta: string | null;
  confianca: Num | null;
  contexto_enviado: string | null;
}

export interface JevDetalhe {
  escopo: JevFiltro | null;
  sustenta: Record<string, JevSustenta>;
}

// ------------------------------------------------------------------ lista (v_card)
/** Uma linha de `v_card`. `dias` NÃO vem: o navegador calcula (lib/prazo.ts). */
export interface Card {
  controle: string;
  slug: string;
  orgao: string | null;
  uf: string | null;
  municipio: string | null;
  local: string;
  modalidade: string | null;
  objeto: string | null;
  situacao: string | null;
  fim_prazo: string | null;
  fim_prazo_tem_hora: boolean | null;
  /** db/047: a data de sessão do PNCP quando é absurda (mais de 2 anos depois da publicação); aí `fim_prazo` vem null */
  fim_prazo_pncp_invalido?: string | null;
  publicado_em: string | null;
  link: string | null;
  estado: string;
  estado_motivo: string | null;
  estado_desde: string | null;
  escopo_dentro: boolean | null;
  escopo_motivo: string | null;
  ensaio: boolean;
  reserva_demo: boolean;
  procedencia_incerta: boolean | null;
  extraida: boolean;
  verificacao_id: number | null;
  verificado_em: string | null;
  versao_regras: string | null;
  respondidas: number;
  ancoradas: number;
  aprovadas: number;
  revisar: number;
  reprovadas: number;
  nao_localizado: number;
  taxa_ancorada: Num | null;
  conflitos: number;
  alertas_globais: string[];
  tags: string[];
  degradada: boolean;
  injecao_suspeita: boolean;
  execucao_id: number | null;
  /** `execucoes_modelo.origem`: api | agente | harness | experimento | simulado | gravado | legado */
  procedencia: string | null;
  provedor: string | null;
  modelo: string | null;
  brl: Num | null;
  brl_legado: Num | null;
  preco_conhecido: boolean | null;
  procedencia_completa: boolean | null;
  n_arquivos: number;
  n_arquivos_ok: number;
  tem_relatorio: boolean;
  revisao_pendente: boolean;
  /** ADR-015: a API lista só o recorte de 2026 por padrão; `?recorte=todos` traz o resto. */
  no_recorte?: boolean;
  jev_filtro?: JevFiltro | null;
  /** Os formatos que o sistema não lê (RTF, RAR, DOC antigo...) quando a leitura parou por isso; null nas outras. */
  sem_pdf?: string | null;
}

export interface UltimaColeta {
  id: number;
  workflow: string;
  script_legado: string | null;
  iniciado_em: string;
  duracao_s: Num | null;
  cego: boolean | null;
  status: string | null;
}

export interface Resumo {
  licitacoes: number;
  abertas: number;
  urgentes: number;
  /** abertas de 8 a 20 dias (a faixa âmbar; a API manda desde 26/09) */
  aviso?: number;
  extraidas: number;
  ancoradas: number;
  respondidas: number;
  respostas_revisar: number;
  custo_conhecido_brl: Num;
  custo_sem_preco: number;
  /** extraídas que rodaram LOCAL (agente, sem API — ADR-014): não entram no "sem preço" */
  extraidas_local: number;
  para_revisar: number;
  ultima_coleta: UltimaColeta | null;
  teto_brl_dia: Num | null;
  auto_processar: boolean | null;
  provedor: string | null;
  /** o recorte que os contadores usaram (`ano_minimo` | `todos`) */
  recorte?: string;
  ano_minimo?: number;
  /** quantas o recorte padrão esconde */
  fora_recorte?: number;
  /** a situação que os contadores usaram (`ativas` | `historico` | `todas`) */
  situacao?: string;
  /** quantas já saíram da grade de trabalho: sessão passada ou legado (fora do recorte) */
  historico?: number;
  /** os motivos de estar no histórico, que os quadros de lá mostram */
  com_vencedor?: number;
  desfeitas?: number;
  antes_do_recorte?: number;
  /** fora da conta: o PNCP não entrega documento que se leia (db/044) */
  sem_documento_fonte?: number;
  jev?: JevResumo | null;
}

// ------------------------------------------------------------------ detalhe
export interface Arquivo {
  id: number;
  seq: number | null;
  tipo: string | null;
  titulo: string | null;
  nome: string;
  status: string;
  motivo: string | null;
  paginas: number | null;
  chars: number | null;
  /** 16 primeiros hex (o inteiro não interessa ao leitor). */
  sha256: string | null;
  bytes: number | null;
  bytes_aproximado: boolean | null;
  formato_real: string | null;
  requer_ocr: boolean | null;
  pai_id: number | null;
  alias_de: number | null;
  baixado_em: string | null;
  /** Há PDF no storage: só então existe `/api/pdf/{slug}/{id}`. */
  tem_pdf: boolean;
}

export type Ausencia = 'nao_se_aplica' | 'sem_evidencia' | 'falta_evidencia';
export type Veredito = 'APROVADO' | 'REVISAR' | 'REPROVADO';

/** `respostas` ⋈ `perguntas`: o que o MODELO respondeu. */
export interface RespostaCrua {
  pergunta_id: string;
  pergunta: string;
  critico: boolean;
  resposta: string;
  arquivo_citado: string | null;
  pagina_citada: number | null;
  trecho_literal: string | null;
  conflito: string | null;
  confianca: string | null;
  completada: boolean | null;
}

/** `verificacao_respostas`: o que o VERIFICADOR decidiu (sem IA). */
export interface VerificacaoResposta {
  pergunta_id: string;
  veredito: string;
  arquivo_canonico: string | null;
  arquivo_id: number | null;
  pagina_final: number | null;
  pagina_citada: number | null;
  alertas: string[] | null;
  /** migracao/regras.py:ausencia — null quando há trecho. */
  ausencia: string | null;
}

/**
 * Uma linha das 17 como a TELA usa: a resposta crua + o veredito dela
 * (lib/respostas.ts:mesclarRespostas). Não vem pronta da API.
 */
export interface RespostaDetalhe {
  pergunta_id: string;
  pergunta: string;
  critico: boolean;
  resposta: string;
  arquivo_citado: string | null;
  /** a página que o modelo citou */
  pagina_citada: number | null;
  trecho_literal: string | null;
  conflito: string | null;
  confianca?: string | null;
  /** null = a verificação vigente não tem linha para esta pergunta */
  veredito: string | null;
  arquivo_canonico: string | null;
  arquivo_id: number | null;
  /** a página onde o verificador achou o trecho */
  pagina_final: number | null;
  alertas: string[] | null;
  ausencia: string | null;
}

/** `verificacoes.condicoes` = fopa.condicoes.Condicoes.para_dict(). */
export interface Condicoes {
  tags?: string[];
  degradada?: boolean;
  motivos?: string[];
  documentos?: { esperados?: number; obtidos?: number; faltando?: string[] };
  ocr?: { arquivos?: string[]; paginas?: number };
  modelo?: { provedor?: string | null; modelo?: string | null; effort?: string | null; secundario?: boolean };
  texto_furtivo?: unknown;
  corpus_horas?: number | null;
  abstencoes?: string[];
}

/** `verificacoes.q13_estruturada` = migracao/regras.py:q13_estruturada. */
export interface Q13 {
  tipo: string;
  parcial: boolean;
  por_faixa: boolean;
  soma: number;
  total_declarado: number | null;
  confere: boolean | null;
  completa: boolean;
  rotulo_soma: string;
  grupos: {
    nome: string | null;
    total_declarado: number | null;
    soma: number;
    confere: boolean | null;
    linhas: { rotulo: string; quantidade: number; valor: number | null }[];
  }[];
}

/** Uma linha de `v_detalhe` (v_card + procedência, leitura e verificação vigente). */
export interface Detalhe extends Card {
  ano: number | null;
  seq: number | null;
  cnpj: string | null;
  rotulo: string | null;
  /** origem da LICITAÇÃO (pncp, legado, manual) — a da execução é `procedencia` */
  origem: string | null;
  modo: string | null;
  effort: string | null;
  lote: number | null;
  k_rag: number | null;
  versao_prompt: string | null;
  chamadas: number | null;
  tok_entrada: number | null;
  tok_saida: number | null;
  tok_cache_escrita: number | null;
  tok_cache_leitura: number | null;
  tok_raciocinio: number | null;
  segundos: Num | null;
  usd: Num | null;
  usd_brl: Num | null;
  leitura_id: number | null;
  leitura_vigente_id: number | null;
  versao_ocr: string | null;
  procedencia_texto: string | null;
  n_paginas: number;
  n_paginas_ocr: number;
  condicoes: Condicoes | null;
  q13_estruturada: Q13 | null;
  html_uri: string | null;
  n_verificacoes: number;
  revisoes_abertas: number;
}

export interface ChamadaModelo {
  id: number;
  lote_ids: string[] | null;
  stop_reason: string | null;
  http_status: number | null;
  tentativas: number | null;
  tok_entrada: number | null;
  tok_saida: number | null;
  segundos: Num | null;
  usd: Num | null;
  brl: Num | null;
  preco_conhecido: boolean | null;
  em: string;
}

/** `execucoes_modelo` da verificação vigente, com as chamadas pagas. */
export interface ExecucaoModelo {
  id: number;
  origem: string;
  provedor: string | null;
  modelo: string | null;
  modo: string | null;
  effort: string | null;
  chamadas: number | null;
  tok_entrada: number | null;
  tok_saida: number | null;
  segundos: Num | null;
  usd: Num | null;
  brl: Num | null;
  preco_conhecido: boolean | null;
  status: string;
  erro: string | null;
  procedencia_completa: boolean | null;
  brl_legado: Num | null;
  reaproveitado_de: unknown;
  iniciado_em: string | null;
  finalizado_em: string | null;
  workflow_execucao_id: number | null;
  chamadas_modelo: ChamadaModelo[];
}

export interface Leitura {
  id: number;
  preparado_em: string | null;
  segundos: Num | null;
  versao_ocr: string | null;
  modo_sugerido: string | null;
  chars_total: number | null;
  procedencia_texto: string | null;
  vigente: boolean;
  n_paginas: number;
}

export interface VerificacaoHistorico {
  id: number;
  execucao_id: number;
  versao_regras: string;
  verificado_em: string;
  aprovadas: number | null;
  revisar: number | null;
  reprovadas: number | null;
  nao_localizado: number | null;
  ancoradas: number | null;
  respondidas: number | null;
  taxa_ancorada: Num | null;
  tags: string[] | null;
  degradada: boolean | null;
  vigente: boolean;
  /** o Best-of-N desta verificação (db/050); ausente na API anterior à v3.1 */
  melhor_de_n?: MelhorDeN | null;
  origem: string | null;
  provedor: string | null;
  modelo: string | null;
  /** {Q1: 'APROVADO', ...} — o site calcula o diff entre verificações seguidas. */
  vereditos: Record<string, string>;
}

/** O que o Best-of-N decidiu numa pergunta (scripts/fopa/melhor_de_n.py:escolher). */
export interface TentativasMelhorDeN {
  /** a primeira resposta + as tentativas extras */
  tentativas: number;
  /** o índice da que ficou: 0 = a primeira (a original) */
  escolhida: number;
  /** [ordem, similaridade] de cada tentativa: ordem 2 ancorada, 1 página corrigida, 0 ausência, -1 reprovada */
  pontos: [number, number][];
}

/**
 * `verificacoes.melhor_de_n` (db/050, v3.1): a resposta que falhou no verificador ganhou até N-1 tentativas extras.
 * Só as perguntas que tiveram tentativas extras aparecem em `perguntas`.
 */
export interface MelhorDeN {
  n: number;
  rodadas: number;
  perguntas: Record<string, TentativasMelhorDeN>;
}

export interface Evento {
  id: number;
  de: string | null;
  para: string;
  motivo: string | null;
  dados: unknown;
  n8n_execution_id: string | null;
  em: string;
}

export interface Gabarito {
  pergunta_id: string;
  critica: boolean;
  resposta_referencia: string | null;
  fatos_obrigatorios: string[] | null;
  fatos_desejaveis: string[] | null;
  fonte: unknown;
}

/** Uma linha de `revisoes_humanas` (camada própria: nunca altera respostas nem vereditos). */
export interface RevisaoHumana {
  id: number;
  controle?: string;
  verificacao_id: number | null;
  pergunta_id: string | null;
  motivo: string | null;
  status: string;
  resposta_corrigida: string | null;
  nota: string | null;
  decidido_por: string | null;
  decidido_em: string | null;
  criado_em: string;
}

/** Rodada do n8n ligada à licitação (`execucoes_workflow` + custo somado das chamadas). */
export interface WorkflowDaLicitacao {
  id: number;
  workflow: string;
  n8n_execution_id: string | null;
  script_legado: string | null;
  gatilho: string | null;
  iniciado_em: string;
  duracao_s: Num | null;
  status: string | null;
  erro: string | null;
  cego: boolean | null;
  custo_brl: Num | null;
  chamadas: number;
  sem_preco: number;
}

/** `GET /api/licitacoes/{slug}` — listas SEPARADAS; quem junta é o site. */
export interface LicitacaoCompleta {
  licitacao: Detalhe;
  respostas: RespostaCrua[];
  verificacao_respostas: VerificacaoResposta[];
  arquivos: Arquivo[];
  execucao: ExecucaoModelo | null;
  leitura: Leitura | null;
  historico: VerificacaoHistorico[];
  eventos: Evento[];
  gabarito: Gabarito[];
  revisoes: RevisaoHumana[];
  execucoes_workflow: WorkflowDaLicitacao[];
  jev?: JevDetalhe | null;
  /** Cada trecho escondido que a varredura achou (db/028), suspeitos primeiro. */
  furtivos?: TrechoFurtivo[];
  /** A varredura desta leitura; null = nunca varrida (a tag, se houver, é a da leitura antiga). */
  furtivos_varredura?: VarreduraFurtivos | null;
  /** O pedido do botão "Extrair com GPT" ainda não usado (db/033); o W23 o gasta ao abrir a execução. */
  pedido_ia?: PedidoIa | null;
  /** O Best-of-N da verificação vigente (db/050); null = execução sem Best-of-N; ausente na API anterior à v3.1. */
  melhor_de_n?: MelhorDeN | null;
}

export interface PedidoIa {
  provedor: string;
  pedido_por: string;
  pedido_em: string;
  /** a escolha da tela (db/037); null nos pedidos antigos */
  modelo?: string | null;
  effort?: string | null;
}

/** Um trecho que a máquina lê e o humano não vê (api/injecao.py). */
export interface TrechoFurtivo {
  arquivo: string;
  pagina: number;
  motivo: string;
  texto: string;
  /** Quantas linhas do detector o trecho junta, e o tamanho do texto inteiro antes do corte. */
  linhas: number;
  caracteres: number;
  classe: string;
  suspeito: boolean;
}

export interface VarreduraFurtivos {
  arquivos: number;
  achados: number;
  suspeitos: number;
  erro: string | null;
  em: string;
}

// ------------------------------------------------------------------ execuções e custo
export interface Busca {
  id: number;
  termo: string;
  paginas_lidas: number | null;
  total_declarado: number | null;
  lidos: number | null;
  cobertura_pct: Num | null;
  teto_atingido: boolean | null;
  falhou: boolean;
  pagina_falha: number | null;
  em: string;
}

/** Linha de `GET /api/execucoes`. */
export interface ExecucaoWorkflow {
  id: number;
  workflow: string;
  n8n_execution_id: string | null;
  script_legado: string | null;
  gatilho: string | null;
  iniciado_em: string;
  duracao_s: Num | null;
  argumentos: unknown;
  contadores: Record<string, unknown> | null;
  cego: boolean | null;
  status: string | null;
  erro: string | null;
  controle: string | null;
  custo_brl: Num | null;
  chamadas: number;
  sem_preco: number;
  n_buscas?: number;
  cobertura_min?: Num | null;
  buscas_falhas?: number;
}

/** `GET /api/execucoes/{id}` — o status mora em `execucao.status`, não no topo. */
export interface ExecucaoDetalhe {
  execucao: ExecucaoWorkflow & { custo_brl_gravado: Num | null };
  buscas: Busca[];
  buscas_paginas: {
    termo: string;
    pagina: number;
    status: number | null;
    falhou: boolean;
    motivo: string | null;
    em: string;
    n_itens: number;
  }[];
  execucoes_modelo: {
    id: number;
    controle: string;
    slug: string;
    origem: string;
    provedor: string | null;
    modelo: string | null;
    status: string;
    brl: Num | null;
    preco_conhecido: boolean | null;
    iniciado_em: string | null;
    finalizado_em: string | null;
  }[];
}

export interface Custo {
  por_dia: { dia: string; brl: Num; usd: Num; chamadas: number; sem_preco: number }[];
  por_modelo: {
    origem: string;
    provedor: string | null;
    modelo: string | null;
    execucoes: number;
    brl: Num | null;
    brl_legado: Num | null;
    sem_preco: number;
  }[];
  hoje_brl: Num;
  /** chamadas de hoje sem tabela de preço (a API manda desde a v3; opcional para a anterior) */
  hoje_sem_preco?: number;
  teto_brl_dia: Num | null;
  auto_processar: boolean | null;
}

/**
 * Os gastos com IA da home. A
 * fatura das Admin APIs (Claude, GPT) e o painel da TypeSafe (Jev) mais o que o sistema mediu depois — db/045.
 */
export interface GastoProvedor {
  provedor: string;
  rotulo: string;
  /** null = sem leitura (nunca US$ 0, ADR-012) */
  usd: Num | null;
  /** 'admin-api' (fatura) | 'painel' (TypeSafe, lido à mão) | 'medido' (tokens × preço, sem leitura do painel) */
  fonte: string | null;
  desde: string | null;
  lido_em: string | null;
  /** Jev: o que o sistema mediu depois da leitura do painel (já somado em `usd`) */
  medido_depois_usd?: Num;
}

export interface GastosIa {
  provedores: GastoProvedor[];
  total_usd: Num | null;
  total_brl: Num | null;
  usd_brl: Num;
  sem_leitura: string[];
}

export interface Email {
  id: number;
  tipo: string;
  controle: string | null;
  slug: string | null;
  assunto: string;
  corpo_html: string | null;
  /** pendente | enviado | falhou */
  status: string;
  /** destinatário: o da linha (a extração vai para quem pediu) ou os admins ativos (db/038) */
  para: string | null;
  canal: string | null;
  tentativas: number;
  enviado_em: string | null;
  erro: string | null;
  em: string;
}

// ------------------------------------------------------------------ saúde
/**
 * `/api/saude` é pública. Em PRODUÇÃO sem sessão ela devolve só
 * `{ok, caiu, avisos}` (mensagens internas são para quem entrou) — por isso
 * o resto é opcional. 503 = Postgres ou worker fora, com o corpo dizendo qual;
 * o n8n fora NÃO derruba (vai em `avisos`).
 */
export interface Saude {
  ok: boolean;
  caiu: string[];
  /** nomes de peças com problema que não derrubam o site (hoje: "n8n") */
  avisos?: string[];
  api_ok?: boolean;
  ambiente?: string;
  /** google | local — a tela de entrada diz qual */
  auth_mode?: string;
  worker?: { ok: boolean | null; erro?: string; status?: number; health?: Record<string, unknown> | null };
  postgres?: { ok: boolean | null; erro?: string };
  n8n?: { ok: boolean | null; status?: number; erro?: string } | null;
  ultima_coleta?: UltimaColeta | null;
  ultimo_alerta?: { em: string; workflow: string | null; mensagem: string | null } | null;
}

// ------------------------------------------------------------------ revisão humana
/** Uma licitação da lista leve da revisão (`GET /api/fila-revisao/licitacoes?q=`, 25/09). */
export interface LicitacaoEmRevisao {
  controle: string;
  slug: string;
  orgao: string | null;
  uf: string | null;
  municipio: string | null;
  modalidade: string | null;
  fim_prazo: string | null;
  /** campos com revisão aberta na verificação vigente */
  abertas: number;
  /** quantos deles são perguntas críticas (entram no lance) */
  criticas: number;
}

/** Os totais sempre; as licitações só com a busca (até 50; `encontradas` diz quantas bateram). */
export interface LicitacoesEmRevisao {
  total_revisoes: number;
  total_licitacoes: number;
  encontradas: number;
  itens: LicitacaoEmRevisao[];
}

/** Linha de `GET /api/fila-revisao` (revisão aberta + resposta + veredito). */
export interface ItemRevisao {
  id: number;
  controle: string;
  slug: string;
  orgao: string | null;
  uf: string | null;
  municipio: string | null;
  fim_prazo: string | null;
  verificacao_id: number | null;
  pergunta_id: string | null;
  pergunta: string | null;
  critico: boolean | null;
  motivo: string | null;
  criado_em: string;
  veredito: string | null;
  alertas: string[] | null;
  arquivo_id: number | null;
  pagina_final: number | null;
  ausencia: string | null;
  resposta: string | null;
  arquivo_citado: string | null;
  pagina_citada: number | null;
  trecho_literal: string | null;
  conflito: string | null;
}

/**
 * Linha da aba "escopo" (`GET /api/rotulos-escopo`, api/consultas.py:
 * rotulos_escopo): primeiro as candidatas do Jev ainda sem rótulo, depois as
 * rotuladas. `rotulo` é o rótulo humano mais recente (null = pendente).
 */
export interface RotuloEscopo {
  controle: string;
  slug: string;
  orgao: string | null;
  uf: string | null;
  municipio: string | null;
  modalidade: string | null;
  objeto: string | null;
  fim_prazo: string | null;
  estado: string;
  escopo_dentro: boolean | null;
  escopo_motivo: string | null;
  escopo_versao: string | null;
  jev_filtro: JevFiltro | null;
  rotulo: { dentro: boolean; motivo: string | null; por: string | null; em: string } | null;
}

export interface RotulosEscopoResposta {
  itens: RotuloEscopo[];
  pendentes: number;
  rotuladas: number;
}

// ------------------------------------------------------------------ questionário (worker)
export interface Questionario {
  versao_prompt: string;
  sistema: string;
  esquema_lote: unknown;
  perguntas: { id: string; texto: string; orienta: string; formato: string; critico: boolean; termos: string[] }[];
  nao_se_aplica: Record<string, string[]>;
  marcador: string;
  precedencia: string[];
  sempre_incluir: string[];
}

// ------------------------------------------------------------------ admin
export interface ItemConfiguracao {
  chave: string;
  valor: unknown;
  descricao: string | null;
  alterado_por: string | null;
  em: string;
}

export interface ConfiguracaoResposta {
  itens: ItemConfiguracao[];
  provedores: string[];
  aviso_custo: string;
}

export interface Orcamento {
  id: number;
  teto_brl_dia: Num | null;
  max_por_execucao: number | null;
  auto_processar: boolean;
  alterado_por: string | null;
  em: string;
}

export interface OrcamentoResposta {
  vigente: Orcamento | null;
  historico: (Orcamento & { vigente: boolean })[];
  aviso_custo: string;
}

export interface Termo {
  termo: string;
  paginas: number;
  ativo: boolean;
  prioridade: number;
  densidade_pct: Num | null;
  medido_em: string | null;
}

export interface Usuario {
  email: string;
  nome: string | null;
  papel: string;
  ativo: boolean;
  /** o admin supremo (db/046): o site não o altera */
  supremo?: boolean;
}

export interface ReservaResposta {
  reservadas: string[];
  nao_encontradas: string[];
  fim_prazo: string | null;
}

// ------------------------------------------------------------------ analytics (GET /api/analytics, db/027)
/** Um banco no ranking: CNPJ-raiz (as filiais são o mesmo comprador), nome mais frequente. */
export interface BancoAnalytics {
  banco: string;
  cnpj_raiz: string;
  natureza_juridica: string | null;
  licitacoes: number;
  valor_total: number;
  ticket_medio: number;
  /** fração das licitações compradas (soma 1 entre os bancos) */
  participacao: number;
  primeira: string | null;
  ultima: string | null;
  /** instituição financeira pelo nome (api/analytics.py:financeira); false = venceu, mas não é banco */
  financeira?: boolean;
}

export interface SerieMensal {
  banco: string;
  /** null na série "Outros" */
  cnpj_raiz: string | null;
  licitacoes: number[];
  valor: number[];
}

export type ResultadoTentativa = 'comprada' | 'deserta' | 'fracassada' | 'revogada' | 'anulada' | 'aberta';

export interface TentativaPublicacao {
  /** 1ª, 2ª, 3ª publicação */
  publicacao: number;
  /** o cadastro duplicado do mesmo dia é UMA tentativa, com os dois controles */
  controles: string[];
  publicado_em: string;
  resultado: ResultadoTentativa;
  valor_estimado: number | null;
}

export interface CadeiaRepublicacao {
  orgao_cnpj: string;
  orgao: string | null;
  municipio: string | null;
  uf: string | null;
  tentativas: number;
  historico: TentativaPublicacao[];
  situacao_atual: ResultadoTentativa;
  sem_comprador: boolean;
  ultima_publicacao: string;
}

export interface Analytics {
  filtro: { escopo: 'dentro' | 'todos'; ano: number | null; de?: string | null; ate?: string | null };
  resumo: {
    compras: number;
    com_vencedor: number;
    bancos: number;
    valor_homologado: number;
    valor_estimado: number;
    desertas: number;
    republicadas: number;
    coletadas_em: string | null;
    /** compras cadastradas duas vezes no PNCP que saíram das contas (28/09) */
    duplicadas?: number;
    /** compras com homologado simbólico (≤ R$ 1) contadas pelo valor do contrato */
    pelo_contrato?: number;
    /** compras com homologado simbólico e sem contrato no PNCP */
    simbolicas?: number;
  };
  bancos: BancoAnalytics[];
  mensal: { meses: string[]; series: SerieMensal[] };
  republicadas: CadeiaRepublicacao[];
}

/** Uma instituição financeira do filtro pesquisável (GET /api/analytics/compras). */
export interface BancoComprador {
  cnpj_raiz: string;
  banco: string;
  licitacoes: number;
  valor_total: number;
}

/** Os contratos (db/049) daquela licitação com o banco: valor acumulado (com os aditivos) e a vigência mais longa. */
export interface ContratoDaCompra {
  controle: string;
  contratos: number;
  valor: number;
  assinado_em: string | null;
  vigencia_fim: string | null;
}

export interface CompraDoBanco {
  controle: string;
  /** FOPA (o que a tela mostra por padrão) ou fora do escopo (só com "mostrar fora do escopo") */
  fopa: boolean;
  municipio: string | null;
  uf: string | null;
  orgao: string | null;
  modalidade: string | null;
  numero_compra: string | null;
  objeto: string | null;
  publicado_em: string | null;
  /** a publicação em que foi comprada: 1ª, 2ª, 3ª... (a cadeia do histórico inteiro) */
  rodada: number;
  /** o que o banco homologou na licitação (soma dos itens); com homologado simbólico, o contrato */
  valor: number;
  /** de onde veio `valor` (28/09): o homologado, o contrato (homologado ≤ R$ 1) ou o simbólico sem contrato */
  fonte_valor?: 'homologado' | 'contrato' | 'simbolico';
  /** o resultado homologado mais antigo do banco na licitação; null se o PNCP não disse */
  comprada_em: string | null;
  contrato: ContratoDaCompra | null;
}

/** GET /api/analytics/compras — o que cada instituição financeira comprou. */
export interface ComprasPorBanco {
  filtro: { escopo: 'dentro' | 'todos'; so_fopa_ia: boolean; banco: string | null; de: string | null; ate: string | null };
  bancos: BancoComprador[];
  banco: { cnpj_raiz: string; banco: string | null } | null;
  compras: CompraDoBanco[];
  total: { licitacoes: number; valor: number };
  coletadas_em: string | null;
}

/** GET /api/modelos-ia — o catálogo do botão "Extrair com IA" (api/modelos_ia.py). */
export interface EstimativaIa {
  usd: number;
  /** o pior caso: as 3 chamadas no teto de saída do esforço */
  usd_max: number;
  brl: number;
}

export interface ModeloIa {
  id: string;
  rotulo: string;
  /** o esforço FIXO do modelo (ADR-020, 26/09: medium); null = o modelo não tem esforço (Haiku 4.5) */
  esforco: string | null;
  nota: string;
  /** custo estimado de um edital no esforço fixo */
  estimativa: EstimativaIa;
}

export interface ProvedorIa {
  id: 'openai' | 'claude';
  rotulo: string;
  modelos: ModeloIa[];
}

export interface CatalogoIa {
  provedores: ProvedorIa[];
  /** de onde sai a estimativa (o edital de Poá) */
  base: string;
}
