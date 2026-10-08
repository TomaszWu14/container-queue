/// <reference types="vite/client" />

// topojson-client nie publikuje typów (a @types nie chcemy dociągać dla jednej funkcji)
declare module 'topojson-client' {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export function feature(topology: any, object: any): any
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export function mesh(topology: any, object: any, filter?: (a: any, b: any) => boolean): any
}

// duży JSON z world-atlas: literalne typowanie przez resolveJsonModule byłoby
// bardzo kosztowne dla tsc — deklarujemy jako any
declare module 'world-atlas/countries-50m.json' {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const topo: any
  export default topo
}
declare module 'world-atlas/land-50m.json' {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const topo: any
  export default topo
}
