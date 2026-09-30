import { useEffect, useState } from 'react';

/**
 * O relógio da página, renovado a cada minuto: quem deixa o painel aberto
 * de um dia para o outro vê o "1 dia" virar "0 dias" sem recarregar — o
 * oposto do número congelado do HTML da v2.
 */
export function useAgora(intervaloMs = 60_000): Date {
  const [agora, setAgora] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setAgora(new Date()), intervaloMs);
    return () => clearInterval(t);
  }, [intervaloMs]);
  return agora;
}
