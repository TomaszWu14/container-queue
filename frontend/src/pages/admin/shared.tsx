import { ReactNode, useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import { useEscClose } from '../../components'
import { useDiscardGuard } from '../../formGuard'
import type { Company, Named, Role, Warehouse } from '../../types'

// --- tabela słownika (jedna dla wszystkich zakładek admina) ---
// To JEDNA tabela HTML, więc thead i tbody zawsze dzielą tę samą siatkę — nie mogą się
// rozjechać. Używamy table-layout:auto (styles.css), żeby kolumny dobierały szerokość do
// treści: nagłówki (np. AKTYWNY) się mieszczą, a wąskie słowniki nie są rozpychane.
// colgroup nadal podaje szerokości tam, gdzie chcemy je przypiąć (kolumna akcji).
export type DictCol = string | { label?: ReactNode; width?: string }

export function DictTable({ cols, className, children }:
                          { cols: DictCol[]; className?: string; children: ReactNode }) {
  const defs = cols.map(c => (typeof c === 'string' ? { label: c } : c))
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className={`grid dict-table${className ? ' ' + className : ''}`}>
        <colgroup>{defs.map((c, i) => <col key={i} style={{ width: c.width }} />)}</colgroup>
        <thead><tr>{defs.map((c, i) => <th key={i}>{c.label}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

// puste pole słownika — jedno miejsce zamiast `|| '—'` rozsianego po zakładkach
export const dash = (v: unknown): ReactNode => {
  const s = v == null ? '' : String(v)
  return s || <span className="dict-empty">—</span>
}

// Klucz duplikatu: nazwa bez wielkości liter, ogonków i znaków — „SHANGHAI”, „Shanghai”
// i „shang-hai” dają to samo. Prefiks spółki, bo scalać wolno tylko w jej obrębie.
export const dupKey = (name: string, companyId?: number): string =>
  `${companyId ?? ''}|${name.normalize('NFD').replace(/\p{M}/gu, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '')}`

// --- współdzielone hooki słowników (używane przez zakładki panelu admina) ---
// błąd ładowania nie może zniknąć bez śladu (pusty select ≠ „brak danych") → toast

// enabled=false: rola bez dostępu do /api/companies (np. sprzedaż) nie woła API
export function useCompanies(enabled = true) {
  const { showToast } = useToast()
  const [companies, setCompanies] = useState<Company[]>([])
  useEffect(() => {
    if (!enabled) return
    api.get<Company[]>('/api/companies').then(setCompanies)
      .catch(err => showToast(errorMessage(err), 'error'))
  }, [showToast, enabled])
  return companies
}

export function useWarehouses() {
  const { showToast } = useToast()
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  useEffect(() => {
    api.get<Warehouse[]>('/api/warehouses').then(setWarehouses)
      .catch(err => showToast(errorMessage(err), 'error'))
  }, [showToast])
  return warehouses
}

export function useForwarders() {
  const { showToast } = useToast()
  const [forwarders, setForwarders] = useState<Named[]>([])
  useEffect(() => {
    api.get<Named[]>('/api/forwarders').then(setForwarders)
      .catch(err => showToast(errorMessage(err), 'error'))
  }, [showToast])
  return forwarders
}

export function useCustomsAgencies() {
  const { showToast } = useToast()
  const [agencies, setAgencies] = useState<Named[]>([])
  useEffect(() => {
    api.get<Named[]>('/api/customs-agencies').then(setAgencies)
      .catch(err => showToast(errorMessage(err), 'error'))
  }, [showToast])
  return agencies
}

// Otwiera domyślnego klienta poczty (Outlook) z gotową treścią zaproszenia i odbiorcą.
// Bez serwerowego SMTP — admin wysyła ręcznie klikając „Wyślij".
// Hasło tymczasowe NIE trafia do mailto: (URL ląduje w historii, logach klienta poczty,
// skrzynce „Wysłane") — admin widzi je raz w panelu i przekazuje osobnym kanałem.
export function inviteMailUrl(u: { login: string; full_name: string; email: string }): string {
  const origin = window.location.origin
  const subject = 'Zaproszenie do aplikacji Kolejka'
  const body = `Cześć ${u.full_name || u.login},

Założono dla Ciebie konto w aplikacji Kolejka.
Adres: ${origin}
Login: ${u.login}
Hasło tymczasowe przekażę Ci osobno.

Przy pierwszym logowaniu ustawisz własne hasło.`
  return `mailto:${encodeURIComponent(u.email)}?subject=${encodeURIComponent(subject)}`
    + `&body=${encodeURIComponent(body)}`
}
export function openInviteMail(u: { login: string; full_name: string; email: string }) {
  window.location.href = inviteMailUrl(u)
}

// last_seen z backendu to naiwny UTC (bez strefy) — dokładamy 'Z', by nie policzyć jako lokalny
export const seenDate = (s: string | null) => (s ? new Date(/[Z+]/.test(s) ? s : s + 'Z') : null)
export const isOnline = (s: string | null) => {
  const d = seenDate(s)
  return !!d && Date.now() - d.getTime() < 5 * 60 * 1000   // aktywny w ostatnich 5 min
}

// --- A1: jedna reguła rola→przypisanie (bez duplikatu add/edit) ---
// To reguła izolacji danych: wysyłamy TYLKO przypisania pasujące do roli, resztę zerujemy,
// żeby stary company_id/warehouse_id ze zmienionej roli nie trafił do konta (np. spedytor
// błędnie przypięty do spółki). Wcześniej ta sama logika istniała w dwóch miejscach.

export type RoleAssign = {
  role: Role
  company_id: string
  forwarder_id: string
  customs_agency_id: string
  warehouse_id: string
  view_all_companies: boolean
}

// partner zewnętrzny (spedytor, agencja celna) nie należy do spółki — ani spółka, ani
// „wszystkie spółki" (backend i tak je czyści i ignoruje)
export const isPartnerRole = (role: Role) => role === 'forwarder' || role === 'customs'

export function rolePayload(f: RoleAssign) {
  return {
    company_id: isPartnerRole(f.role) ? null : (f.company_id ? Number(f.company_id) : null),
    view_all_companies: !isPartnerRole(f.role) && f.view_all_companies,
    forwarder_id: f.role === 'forwarder' && f.forwarder_id
      ? Number(f.forwarder_id) : null,
    customs_agency_id: f.role === 'customs' && f.customs_agency_id
      ? Number(f.customs_agency_id) : null,
    warehouse_id: f.role === 'warehouse' && f.warehouse_id
      ? Number(f.warehouse_id) : null,
  }
}

// Selektory przypisania zależne od roli (spedytor / agencja celna / spółka + magazyn).
// Ten sam blok w formularzu dodawania i edycji użytkownika.
export function RoleAssignmentFields({ form, patch, companies, forwarders, agencies, warehouses }: {
  form: RoleAssign
  patch: (p: Partial<RoleAssign>) => void
  companies: Company[]
  forwarders: Named[]
  agencies: Named[]
  warehouses: Warehouse[]
}) {
  const t = useT()
  return (
    <>
      {form.role === 'forwarder' ? (
        <select aria-label={t('forwarder')} value={form.forwarder_id} onChange={e => patch({ forwarder_id: e.target.value })}>
          <option value="">— {t('forwarder')} —</option>
          {forwarders.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      ) : form.role === 'customs' ? (
        <select aria-label={t('customsAgency')} value={form.customs_agency_id}
                onChange={e => patch({ customs_agency_id: e.target.value })}>
          <option value="">— {t('customsAgency')} —</option>
          {agencies.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      ) : (
        <select aria-label={t('company')} value={form.company_id} onChange={e => patch({ company_id: e.target.value })}>
          <option value="">— {t('company')} —</option>
          {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      )}
      {form.role === 'warehouse' && (
        <select value={form.warehouse_id}
                onChange={e => patch({ warehouse_id: e.target.value })}
                title={t('warehouseScope')}>
          <option value="">— {t('warehouseScope')} —</option>
          {warehouses
            .filter(w => !form.company_id || w.company_id === Number(form.company_id))
            .map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
      )}
    </>
  )
}

// --- wspólne akcje formularzy zakładek (2026-09-24): Anuluj po lewej, Zapisz/Dodaj po prawej ---
// Anuluj w wierszu dodawania: widoczny, gdy coś wpisano; czyści pola (z pytaniem „porzucić?").
export function AddCancel({ dirty, onReset }: { dirty: boolean; onReset: () => void }) {
  const t = useT()
  const cancel = useDiscardGuard(dirty, onReset)
  return dirty ? <button type="button" className="btn secondary" onClick={cancel}>{t('cancel')}</button> : null
}

// Akcje edycji w wierszu: [Anuluj][Zapisz]; Esc = Anuluj. Edycja pracuje na kopii pól,
// więc wyjście z trybu edycji = powrót do oryginalnych wartości rekordu.
export function EditActions({ dirty, onSave, onCancel, busy = false }: {
  dirty: boolean; onSave: () => void; onCancel: () => void; busy?: boolean
}) {
  const t = useT()
  const cancel = useDiscardGuard(dirty, onCancel)
  useEscClose(cancel, !busy)
  return (
    <span className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
      <button type="button" className="btn small secondary" disabled={busy} onClick={cancel}>{t('cancel')}</button>
      <button type="button" className="btn small" disabled={busy} onClick={onSave}>{t('save')}</button>
    </span>
  )
}
