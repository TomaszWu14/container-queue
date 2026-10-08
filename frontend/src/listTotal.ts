// X-Total-Count listy obciętej limitem (audyt DATA-002). api.ts zapamiętuje go przy obiekcie
// odpowiedzi, strona czyta po tym samym obiekcie — bez zmiany sygnatury api.get (i mocków w testach).
const totals = new WeakMap<object, number>()

export function rememberTotal(data: unknown, header: string | null) {
  if (header !== null && data !== null && typeof data === 'object') totals.set(data, Number(header))
}

export const totalOf = (data: unknown): number | null =>
  data !== null && typeof data === 'object' ? totals.get(data) ?? null : null
