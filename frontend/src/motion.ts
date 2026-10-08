// Systemowe „ogranicz ruch” (UX-040). CSS wygasza animacje globalnie (00-tokens.css);
// to jest dla JS: pętle rAF, bezwładność kamery i jawne { behavior: 'smooth' }, których CSS nie dosięga.
export const prefersReducedMotion = (): boolean =>
  typeof matchMedia === 'function' && !!matchMedia('(prefers-reduced-motion: reduce)')?.matches

export const scrollBehavior = (): ScrollBehavior => (prefersReducedMotion() ? 'auto' : 'smooth')
