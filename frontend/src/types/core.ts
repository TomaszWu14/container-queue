export type Role = 'admin' | 'logistics' | 'warehouse' | 'forwarder' | 'customs' | 'purchasing' | 'sales'

export type TransportOrderStatus =
  | 'WYSTAWIONE' | 'ZAAKCEPTOWANE' | 'ODRZUCONE'
  | 'W_REALIZACJI' | 'WYKONANE' | 'POTWIERDZONE'

export interface TransportOrder {
  id: number
  container_id: number
  container_no: string | null
  company_id: number
  forwarder_id: number
  forwarder_name: string | null
  status: TransportOrderStatus
  pickup_location: string
  delivery_location: string
  pickup_date: string | null
  delivery_date: string | null
  instructions: string
  rejection_reason: string
  created_by_login: string | null
  created_at: string
  updated_at: string
}

export interface Message {
  id: number
  container_id: number
  body: string
  user_login: string | null
  user_full_name: string | null
  user_role: Role | null
  created_at: string
}

export interface Notification {
  id: number
  kind: string
  title: string
  body: string
  container_id: number | null
  is_read: boolean
  created_at: string
}

export interface Attachment {
  id: number
  container_id: number
  filename: string
  content_type: string
  size: number
  uploaded_by_login: string | null
  document_type_id: number | null
  document_type_name: string | null
  gate_warning?: string | null   // bramka wgrania: „niepewny” — wpuszczony z ostrzeżeniem
  can_delete?: boolean           // attachment_rules: czy pokazać Usuń / Podmień
  can_replace?: boolean
  replace_needs_reason?: boolean // po wysłaniu do agencji podmiana tylko z powodem
  shared_with?: string[]         // wspólny plik: pozostałe kontenery (numery)
  owner_container_no?: string | null // właściciel — gdy plik oglądany z kontenera powiązanego
  can_unlink?: boolean
  created_at: string
}

export type ContainerStatus =
  | 'ZAPOWIEDZIANY' | 'W_PRODUKCJI' | 'TRANSPORT_WSTEPNY' | 'W_TRANSPORCIE' | 'W_PORCIE' | 'ODPRAWA'
  | 'AWIZOWANY' | 'W_DOSTAWIE' | 'DOSTARCZONY' | 'ZREALIZOWANY'

export type CustomsStatus =
  | 'BRAK' | 'DOKUMENTY_KOMPLETNE' | 'ZLECONA'
  | 'DRAFT_WYSLANY' | 'DRAFT_POTWIERDZONY' | 'ODPRAWIONY' | 'ZWOLNIONY' | 'REWIZJA'

// obieg dokumentów kontenera (§10.4 specyfikacji)
export type DocumentStatus = 'BRAK' | 'ZALACZONE' | 'WYSLANE'

// WARTOŚCI STARTOWE — do potwierdzenia z działem zakupów (#12)
export type PurchasingStatus =
  | 'BRAK' | 'DO_ZAMOWIENIA' | 'ZAMOWIONE' | 'POTWIERDZONE'
  | 'ZREALIZOWANE' | 'WSTRZYMANE'

export const CONTAINER_STATUSES: ContainerStatus[] = [
  'ZAPOWIEDZIANY', 'W_PRODUKCJI', 'TRANSPORT_WSTEPNY', 'W_TRANSPORCIE', 'W_PORCIE', 'ODPRAWA',
  'AWIZOWANY', 'W_DOSTAWIE', 'DOSTARCZONY', 'ZREALIZOWANY',
]

export const CUSTOMS_STATUSES: CustomsStatus[] = [
  'BRAK', 'DOKUMENTY_KOMPLETNE', 'ZLECONA',
  'DRAFT_WYSLANY', 'DRAFT_POTWIERDZONY', 'ODPRAWIONY', 'ZWOLNIONY', 'REWIZJA',
]

/** Odprawa zakończona (odprawiony / zwolniony / rozliczony) — wyjście z tego zbioru = cofnięcie. */
export const CUSTOMS_CLEARED: ReadonlySet<string> = new Set(['ODPRAWIONY', 'ZWOLNIONY', 'ROZLICZONY'])

export const DOCUMENT_STATUSES: DocumentStatus[] = ['BRAK', 'ZALACZONE', 'WYSLANE']

export const PURCHASING_STATUSES: PurchasingStatus[] = [
  'BRAK', 'DO_ZAMOWIENIA', 'ZAMOWIONE', 'POTWIERDZONE', 'ZREALIZOWANE', 'WSTRZYMANE',
]

export interface User {
  id: number
  login: string
  full_name: string
  email: string
  role: Role
  company_id: number | null
  forwarder_id: number | null
  customs_agency_id: number | null
  customs_agency_name: string | null
  view_all_companies: boolean
  is_active: boolean
  warehouse_id: number | null
  company_code: string | null
  must_change_password: boolean
  watch_only_notifications: boolean
  last_seen: string | null
  // bezpieczeństwo (W14) — opcjonalne, by nie łamać mocków w istniejących testach
  totp_enabled?: boolean
  must_enroll_2fa?: boolean  // SEC-006: admin bez 2FA — ekran włączania zamiast panelu
  impersonated?: boolean
  allowed_warehouse_ids?: number[] | null
  has_avatar?: boolean
  // tylko w odpowiedzi na utworzenie z zaproszeniem / reset-invite (jednorazowo)
  temp_password?: string | null
}

export interface Company {
  id: number
  name: string
  code: string
  is_active: boolean
  avizo_cc?: string   // CC maili awizacji (CSV)
}

export interface Named {
  id: number
  name: string
  email?: string
  is_active?: boolean
}

export interface Warehouse extends Named {
  company_id: number
  country: string
  default_daily_limit: number
  slot_windows?: string
  slot_capacity?: number
}

export interface Supplier extends Named {
  // null/brak = kartoteka dostawców Acme; liczba = nadawca kontenerów tej spółki-klienta
  client_company_id?: number | null
  is_active?: boolean
  address?: string
  note?: string
  column_map?: string
  sap_code?: string
  country?: string
}
