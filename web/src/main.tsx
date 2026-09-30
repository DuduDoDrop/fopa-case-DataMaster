import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { aplicarTema, temaInicial } from './lib/tema';
import './estilo/extra.css';

aplicarTema(temaInicial());

createRoot(document.getElementById('raiz')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
