/**
 * `/entrar` — um botão só, para o `/login` do SERVIDOR (api/site.py), que
 * decide o modo: na demo com `FOPA_AUTH_MODE=local` ele já entra como o admin
 * semeado; no resto redireciona ao fluxo do Google (`/auth/google/login` →
 * Google → callback → cookie HttpOnly → `/`). O front nunca aponta para o
 * OAuth direto: apontar ignorava o modo local e a demo sem Wi-Fi não entrava.
 *
 * `/login` é rota do servidor (o SPA não a serve), por isso esta página mora
 * em `/entrar`, para onde o 401 manda. O rótulo do botão vem do
 * `auth_mode` da `/api/saude` (pública); sem ela, "Entrar".
 */
import '../../design/painel.css';
import { useSearchParams } from 'react-router-dom';
import { useSaude } from '../api/consultas';

export const URL_LOGIN = '/login';

function rotulo(modo: string | undefined): string {
  if (modo === 'local') return 'Entrar (demonstração local)';
  if (modo === 'google') return 'Entrar com Google';
  return 'Entrar';
}

export function Login() {
  const [params] = useSearchParams();
  const erro = params.get('erro');
  const saude = useSaude(false);
  const modo = saude.data?.auth_mode;
  return (
    <div className="pg-painel">
      <div className="wrap">
        <header>
          <p className="eyebrow">Folha de pagamento · setor público</p>
          <h1>FOPA</h1>
          <p className="sub">Licitações de folha de pagamento, lidas e verificadas página a página.</p>
        </header>
        {erro && <p className="alerta">{erro === '403' ? 'Este e-mail não tem acesso ao sistema. Solicite a liberação ao administrador.' : erro}</p>}
        <div className="atual">
          <a className="primario" href={URL_LOGIN}>
            {rotulo(modo)}
          </a>
          <span className="atualmsg">
            {modo === 'local'
              ? 'Demonstração local: acesso como administrador de teste.'
              : 'Somente o nome e o e-mail da conta são lidos.'}
          </span>
        </div>
        <p className="atualmsg"><a href="/privacidade">Política de privacidade</a></p>
      </div>
    </div>
  );
}
