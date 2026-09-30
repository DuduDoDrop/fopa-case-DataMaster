/**
 * `/governanca` — governança e compliance. Página estática, para todo usuário logado.
 *
 * Cada frase vem das notas conferidas do vault de entrega (Fopa-v3: 11-Seguranca-e-Etica e 12-Legal), com o
 * dispositivo de cada norma, e nenhuma promete o que o sistema não faz. O termo em inglês é o rótulo acima do título em
 * português. O texto fica no JSX, e não numa lista de dados, para a guarda de
 * textos (textos.test.ts) o enxergar.
 */
import '../../design/relatorio.css';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

function Bloco(p: { id: string; rotulo: string; titulo: string; largo?: boolean; children: ReactNode }) {
  return (
    <section className={p.largo ? 'governanca-cartao largo' : 'governanca-cartao'} aria-labelledby={p.id}>
      <p className="governanca-termo">{p.rotulo}</p>
      <h2 id={p.id}>{p.titulo}</h2>
      {p.children}
    </section>
  );
}

export function Governanca() {
  return (
    <div className="pg-relatorio">
      <div className="wrap">
        <header>
          <p className="eyebrow">FOPA · governança e compliance</p>
          <h1>Governança e compliance</h1>
          <p className="sub">
            Princípios, controles e fundamentos legais que orientam o uso de inteligência artificial na análise de
            licitações de folha de pagamento. Os controles descritos estão implementados em produção e são auditáveis.
          </p>
        </header>
        <div className="governanca-grade">
          <Bloco id="gov-supervisao" rotulo="Human-in-the-loop" titulo="Supervisão humana">
            <p>A inteligência artificial apoia a análise. A decisão é sempre humana.</p>
            <ul>
              <li>Toda resposta apresenta o arquivo, a página e o trecho literal que a sustentam</li>
              <li>Um verificador determinístico, sem inteligência artificial, confere cada trecho no documento original</li>
              <li>
                Respostas reprovadas ou não localizadas, alertas em perguntas críticas e sinais de manipulação seguem para
                revisão humana
              </li>
              <li>
                Cada decisão é registrada com responsável e data, sem alterar a resposta do modelo nem o veredito do
                verificador
              </li>
            </ul>
            <p>
              A fila de revisão está disponível na página <Link to="/revisao">Revisão</Link>.
            </p>
          </Bloco>

          <Bloco id="gov-rastreabilidade" rotulo="Accountability" titulo="Rastreabilidade e prestação de contas">
            <ul>
              <li>Cada resposta identifica o modelo de IA e a data da extração que a produziu</li>
              <li>Cada documento registra a origem, a data da coleta e o hash SHA-256, que atesta a integridade</li>
              <li>Cada execução do processamento é registrada com duração, custo e resultado</li>
              <li>Os registros da automação não são sobrescritos; as decisões humanas ficam em registro próprio</li>
            </ul>
          </Bloco>

          <Bloco id="gov-normas" rotulo="Legal & regulatory compliance" titulo="Fundamentos legais e regulatórios" largo>
            <p>Normas que fundamentam a coleta, o tratamento dos dados e a leitura das licitações.</p>
            <table>
              <thead>
                <tr>
                  <th>Norma</th>
                  <th>Aplicação na solução</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Lei nº 14.133/2021, arts. 54 e 174</td>
                  <td>Publicação obrigatória do inteiro teor do edital no PNCP, fonte dos documentos analisados</td>
                </tr>
                <tr>
                  <td>Lei nº 12.527/2011 (LAI), art. 8º, § 3º, III</td>
                  <td>Acesso automatizado a dados públicos por sistemas externos, em formato aberto</td>
                </tr>
                <tr>
                  <td>Lei nº 13.709/2018 (LGPD), arts. 6º e 7º, IX</td>
                  <td>Finalidade, necessidade e legítimo interesse no tratamento de dados já públicos</td>
                </tr>
                <tr>
                  <td>Lei nº 13.303/2016</td>
                  <td>Regime de licitações das empresas estatais</td>
                </tr>
                <tr>
                  <td>TCU, Acórdãos 3.042/2008 e 1.940/2015, e tribunais de contas estaduais</td>
                  <td>Fundamentos da cessão onerosa da folha de pagamento</td>
                </tr>
                <tr>
                  <td>Resolução CMN nº 5.058/2022 e Lei nº 15.252/2025</td>
                  <td>Conta-salário e portabilidade salarial, que afetam o valor da folha</td>
                </tr>
                <tr>
                  <td>Lei nº 14.509/2022</td>
                  <td>
                    Margem consignável federal; a solução registra a regra do edital, pois estados e municípios têm norma
                    própria
                  </td>
                </tr>
              </tbody>
            </table>
          </Bloco>

          <Bloco id="gov-dados" rotulo="Privacy by design · LGPD" titulo="Proteção de dados pessoais">
            <ul>
              <li>A análise utiliza apenas documentos publicados no PNCP por obrigação legal</li>
              <li>
                As perguntas solicitam dados agregados, como servidores por faixa salarial; nenhum dado individual é
                extraído
              </li>
              <li>Do login, somente nome e e-mail; nenhum outro dado da conta Google é acessado</li>
              <li>
                Dados armazenados no Brasil (AWS, região São Paulo); documentos acessíveis apenas a usuários autenticados
              </li>
              <li>
                Dados de usuários não são vendidos nem compartilhados, e nenhum dado é utilizado para treinar modelos de IA
              </li>
            </ul>
            <p>
              Detalhes na <a href="/privacidade">Política de privacidade</a>.
            </p>
          </Bloco>

          <Bloco id="gov-coleta" rotulo="Open data" titulo="Dados públicos e coleta responsável">
            <ul>
              <li>Coleta exclusiva pelas APIs oficiais e documentadas do PNCP, sem raspagem de páginas</li>
              <li>Cada requisição identifica o sistema, a finalidade e um contato</li>
              <li>Ritmo conservador de consultas, com pausas e novas tentativas espaçadas</li>
              <li>Coleta mínima: somente licitações de folha de pagamento têm documentos baixados</li>
              <li>Nenhum login, captcha ou controle de acesso é contornado</li>
            </ul>
          </Bloco>

          <Bloco id="gov-seguranca" rotulo="Least privilege" titulo="Segurança da informação e gestão de acessos">
            <ul>
              <li>Autenticação pelo Google (OAuth 2.0 com OpenID Connect) e sessão com validade de 12 horas</li>
              <li>Perfis Usuário, Admin e Admin Supremo, com segregação de funções</li>
              <li>Ações que geram custo são restritas ao Admin; a concessão de acessos, ao Admin Supremo</li>
              <li>Comunicação criptografada (HTTPS) e servidor com exposição mínima de portas</li>
              <li>Credenciais dos serviços de IA cifradas, fora do código, das imagens e dos backups</li>
            </ul>
          </Bloco>

          <Bloco id="gov-continuidade" rotulo="Business continuity · Risk management" titulo="Continuidade e gestão de riscos">
            <ul>
              <li>Backup diário, com cópia em armazenamento externo que a aplicação não tem permissão para apagar</li>
              <li>Restauração testada semanalmente, com conferência dos dados restaurados</li>
              <li>Teto diário de gasto com IA, configurável pela administração</li>
              <li>
                Proteção contra instruções inseridas nos documentos: o conteúdo do edital nunca é tratado como comando
              </li>
              <li>Monitoramento da saúde dos serviços a cada hora</li>
              <li>
                Cobertura declarada: municípios de até 20 mil habitantes podem publicar fora do PNCP até 01/04/2027
              </li>
            </ul>
          </Bloco>

          <Bloco id="gov-responsabilidade" rotulo="Shared responsibility" titulo="Responsabilidade compartilhada" largo>
            <p>
              A adoção formal pela instituição financeira requer instrumentos internos, sob responsabilidade da própria
              instituição:
            </p>
            <ul>
              <li>Relatório de impacto à proteção de dados pessoais (RIPD)</li>
              <li>Parecer do encarregado pelo tratamento de dados pessoais (DPO)</li>
              <li>Política de retenção dos documentos</li>
              <li>Política interna de uso de IA com documentos externos</li>
              <li>Processo de revisão humana na área de negócio</li>
            </ul>
          </Bloco>
        </div>
        <p className="governanca-rodape">
          Leitura técnica dos fundamentos legais, com a indicação de cada dispositivo. Não constitui parecer jurídico.
        </p>
      </div>
    </div>
  );
}
