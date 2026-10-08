import type { Named } from './core'

export type QuoteStatus = 'ZAPYTANIE' | 'WYCENIONA' | 'WYBRANA' | 'ODRZUCONA' | 'WYGASLA'
export type TransportJobStatus = 'SZKIC' | 'WYSLANE' | 'ZLECONE' | 'ANULOWANE'

export interface Quote {
  id: number
  forwarder_id: number
  forwarder_name: string | null
  status: QuoteStatus
  amount: string | null
  currency: string
  valid_until: string | null
  note: string
  carrier_id: number | null
  carrier_name: string | null
  etd: string | null
  eta: string | null
  transit_time_days: number | null
  no_equipment: boolean
  can_roll_booking: boolean
  submitted_at: string | null
  revised_amount: string | null
  revised_note: string
  revised_at: string | null
  score: number | null
  recommended: boolean
}

export interface QuoteRevision {
  id: number
  amount: string | null
  currency: string
  note: string
  kind: string
  created_by_login: string | null
  created_at: string
}

export interface JobKpi {
  invited: number
  responded: number
  expired: number
  response_rate: number
  deadline_passed: boolean
}

export interface JobContainer {
  container_id: number
  container_no: string
  supplier_name: string | null
  supplier_contact_name: string | null
  supplier_contact_email: string | null
  supplier_contact_phone: string | null
  order_numbers: string
  warehouse_name: string | null
  eta: string | null
  notify_date: string | null
}

export interface TransportJob {
  id: number
  number: string
  status: TransportJobStatus
  pickup_location: string
  delivery_location: string
  note: string
  created_at: string
  sent_at: string | null
  response_hours: number
  response_deadline: string | null
  scfi_index: string
  shipment_number: string
  agent_name: string
  agent_phone: string
  agent_company: string
  agent_submitted_at: string | null
  cancel_reason: string
  cancelled_at: string | null
  chosen_quote_id: number | null
  container_count: number
  kpi: JobKpi
  containers: JobContainer[]
  quotes: Quote[]
  my_quote: Quote | null
}

// --- zakładanie zlecenia (Borealis/Cobalt) ---

export type PortCategory = 'GLOWNY_CN' | 'OUT'
export type MainMode = 'SEA' | 'AIR' | 'RAIL'
export type SeaService = 'STANDARD' | 'LONG'

export interface Port extends Named {
  country: string
  category: PortCategory
  transit_time_days: number | null
  transit_time_long_days: number | null
  // sezonowy transit time: klucz = miesiąc '1'..'12' (JSON), wartość = dni.
  // Brak miesiąca → obowiązuje transit_time_days (patrz backend planning.transit_days_for).
  monthly_transit: Record<string, number>
  is_active: boolean
}

export interface ContainerType extends Named {
  inner_length_m: string | null
  inner_width_m: string | null
  inner_height_m: string | null
  max_payload_kg: number | null
  teu: string | null
  volume_m3: number | null
}

export interface SupplierContact {
  id: number
  supplier_id: number
  full_name: string
  email: string
  phone: string
}

export interface FxConvert {
  amount: string
  currency: string
  rates: Record<string, number>
  converted: Record<string, number>
  as_of: string | null
  available: boolean
}
