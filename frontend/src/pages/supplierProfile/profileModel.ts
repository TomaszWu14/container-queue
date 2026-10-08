// Profil dokumentów dostawcy (CI + packing list) — typy API i czyste operacje na mapie
// kolumn {rola: [aliasy nagłówka]}. Wzorzec z compare: auto-propozycja ról z nagłówków.
import type { TileCode } from '../../DocumentTiles'

// lustro backend/app/invoices/extractor.py COLUMN_ROLES (walidacja PUT odrzuci inną rolę)
export const COLUMN_ROLES = ['ref', 'desc', 'qty', 'price', 'net', 'unit', 'lot',
  'weight_net', 'weight_gross', 'cartons', 'no'] as const
export const REQUIRED_ROLES = ['ref', 'qty'] as const

export type RoleMap = Record<string, string[]>
export type DocKind = 'ci' | 'pl'

export interface ProfileForm {
  status: 'draft' | 'active'
  currency: string
  doc_language: string
  keywords: string[]
  ci_map: RoleMap
  pl_map: RoleMap
  ref_kind: 'ours' | 'supplier'
  split_marker: string
  tol_amount_pct: number
  tol_qty_pct: number
}

export interface SampleTest {
  ok: boolean
  errors: string[]
  pages: { ci: number[]; pl: number[] }
  ci_items: number
  pl_items: number
  matched: number
  sum_items?: number
  total?: number | null
  sum_ok?: boolean | null
  items: { ref: string; master_ref: string; qty: string | null; matched: boolean }[]
}

export interface Sample {
  id: number
  filename: string
  created_at: string | null
  last_test: Partial<SampleTest>
  last_test_at: string | null
}

export interface Profile extends ProfileForm {
  id: number | null
  supplier_id: number
  samples: Sample[]
  required_docs?: TileCode[] | null   // null = domyślny zestaw kafelków (decyzja 16)
}

export interface Preview {
  found: boolean
  page: number | null
  headers: string[]
  rows: string[][]
  detected: Record<string, number>
  pages: { ci: number[]; pl: number[] }
}

export interface TestResult extends SampleTest { sample_id: number; filename: string }

export function formOf(p: Profile): ProfileForm {
  const { status, currency, doc_language, keywords, ci_map, pl_map, ref_kind, split_marker,
    tol_amount_pct, tol_qty_pct } = p
  return { status, currency, doc_language, keywords, ci_map, pl_map, ref_kind, split_marker,
    tol_amount_pct, tol_qty_pct }
}

const norm = (s: string) => s.trim().replace(/\s+/g, ' ').toLowerCase()

export function roleOf(map: RoleMap, header: string): string {
  const h = norm(header)
  return Object.keys(map).find(r => map[r].some(a => norm(a) === h)) ?? ''
}

/** Nagłówek `header` dostaje rolę `role` ('' = pomiń); ten sam nagłówek znika z innych ról. */
export function assignRole(map: RoleMap, header: string, role: string): RoleMap {
  const h = norm(header)
  const out: RoleMap = {}
  for (const [r, aliases] of Object.entries(map)) {
    const kept = aliases.filter(a => norm(a) !== h)
    if (kept.length) out[r] = kept
  }
  if (role && header.trim()) out[role] = [...(out[role] ?? []), header.trim()]
  return out
}

/** Auto-propozycja z detekcji ekstraktora: tylko role jeszcze niezmapowane i wolne nagłówki. */
export function proposeRoles(map: RoleMap, headers: string[], detected: Record<string, number>): RoleMap {
  let out = map
  for (const [role, idx] of Object.entries(detected)) {
    const header = headers[idx]
    if (!header || role in out || roleOf(out, header)) continue
    out = assignRole(out, header, role)
  }
  return out
}

export const mappedCount = (map: RoleMap) => Object.keys(map).length
export const hasRequired = (map: RoleMap) => REQUIRED_ROLES.every(r => (map[r] ?? []).length > 0)
