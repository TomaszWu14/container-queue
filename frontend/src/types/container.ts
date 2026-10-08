import type { ContainerStatus, CustomsStatus, DocumentStatus, PurchasingStatus } from './core'

export interface SupplierStatContainer {
  id: number
  container_no: string
  status: string
  eta: string | null
  atd: string | null
  notify_date: string | null
}

export interface SupplierStats {
  active_containers: number
  on_time_pct: number | null
  avg_transit_days: number | null
  recent_containers: SupplierStatContainer[]
}

export interface Container {
  id: number
  container_no: string
  company_id: number
  company_name: string | null
  order_id: number | null
  order_number: string | null
  supplier_id: number | null
  supplier_name: string | null
  supplier_raw?: string   // nazwa z pliku kolejki; przy supplier_id null = do zmapowania
  forwarder_id: number | null
  forwarder_name: string | null
  warehouse_id: number | null
  warehouse_name: string | null
  port_id: number | null
  port_name: string | null
  carrier_id: number | null
  carrier_name: string | null
  status: ContainerStatus
  customs_status: CustomsStatus
  purchasing_status: PurchasingStatus
  customs_note: string
  customs_date: string | null
  customs_agency: string
  customs_agency_id: number | null
  customs_agency_name: string | null
  customs_agent_name: string
  customs_agent_phone: string
  customs_agent_email: string
  customs_assigned_at: string | null
  customs_case_status_id: number | null
  customs_case_status_name: string | null
  missing_documents?: string[] | null
  vessel: string
  eta: string | null
  etd: string | null            // data wypłynięcia (z trackingu — 1. zdarzenie DEPART)
  eta_estimate?: string | null  // D12: ETD + transit portu, gdy brak ETA z trackingu („szacunek”)
  atd: string | null            // rzeczywista data dostawy (ETA zostaje jako plan)
  notify_date: string | null
  slot_time?: string             // #13 zarezerwowany slot rozładunku (HH:MM)
  proposed_delivery_date: string | null
  transport_type: 'morski' | 'lotniczy' | 'kolej' | 'kola' | 'inne' | null
  transport_details: string
  on_carriage: 'drogowo' | 'intermodal' | null   // dowóz po odprawie
  container_size: string
  documents_ok: boolean
  is_transit: boolean
  is_special: boolean
  customer_order?: string | null   // flaga „pod klienta" (moduł specjalnej troski)
  special_reason?: string | null
  special_note?: string
  customer_id: number | null
  customer_name: string
  customer_address: string
  customer_contact: string
  planning_status: 'PROPOZYCJA' | 'WYSLANE' | 'POTWIERDZONE'
  needs_forwarding: boolean
  notify_date_manual: boolean
  notify_conflict?: number | null   // #49: ostrzeżenie z PATCH — inne kontenery dostawcy z tą datą
  // ostrzeżenie z zapisu daty/magazynu: paczka transportowa rozjeżdża się tego dnia
  // do różnych magazynów (lista nazw magazynów)
  transport_conflict?: string[] | null
  // decyzja 9 (spec dokumenty-dostaw): status ZWOLNIONY/ODPRAWIONY/DOSTARCZONY zapisany mimo braków
  docs_warning?: string | null
  planning_sent_at: string | null
  planning_confirmed_at: string | null
  planning_eta_at_send: string | null
  document_status: DocumentStatus
  demurrage_free_days: number | null
  demurrage_deadline?: string | null   // termin demurrage (tylko lista kolejki)
  incoming_delivery_no: string
  rf_number: string
  notes: string
  transport_id: string | null
  order_numbers: string
  delivery_note: string
  purchase_note: string
  document_flow: string
  sent_required: boolean | null
  sent_number: string
  sent_status: string
  driver_name: string
  driver_id_no: string
  truck_no: string
  trailer_no: string
  driver_phone: string
  materials_list: string
  palletization_note: string
  pallet_count: number | null
  unload_started_at?: string | null
  unload_finished_at?: string | null
  is_delayed: boolean
  is_stuck?: boolean
  status_age_days?: number | null
  vessel_mismatch?: boolean
  created_at: string
  updated_at: string
  completed_at: string | null
  tracked_at: string | null
  tracking_error: string
}

export interface TrackingEvent {
  id: number
  event_code: string
  description: string
  location: string
  vessel: string
  occurred_at: string | null
  is_estimated: boolean
  source: string
}

export interface QueueDay {
  day: string
  is_free_day: boolean
  limit: number | null
  used: number
  over_limit: boolean
  containers: Container[]
}

export interface AuditEntry {
  id: number
  field: string
  old_value: string | null
  new_value: string | null
  note: string
  user_login: string | null
  created_at: string
}
