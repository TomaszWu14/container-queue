// --- faktury (CIPL) → Excel ---
export type InvoiceDocKind = 'invoice' | 'proforma' | 'packing_list' | 'other'
export type InvoiceJobStatus =
  | 'uploaded' | 'extracted' | 'confirmed' | 'error' | 'packing_list' | 'ignored'
export type InvoiceMatchStatus = 'matched' | 'ambiguous' | 'unmatched'

export interface InvoiceItem {
  id: number
  line_no: number
  raw_ref: string
  descr: string
  qty: string
  uom_src: string
  net_amount: string
  amount: string
  weight_net: string
  weight_gross: string
  cartons: string
  weight_source: string
  master_ref: string
  name_pl: string
  tariff_cn: string
  sent: boolean
  uom_factor: string
  match_status: InvoiceMatchStatus
  match_source: string
  ml_suggestion: string
  ml_confidence: number | null
  skipped: boolean
}

export interface InvoiceJob {
  id: number
  batch_id: number
  filename: string
  doc_kind: InvoiceDocKind
  status: InvoiceJobStatus
  error: string
  invoice_number: string
  container_no: string
  delivery_terms: string
  page_from: number
  page_to: number
  ocr_used: boolean
  items_count: number
  updated_at: string
  processing_started_at?: string | null   // kolejka w tle: start przetwarzania zestawu
  attempts?: number
}

// W5 #31: propozycja podpięcia dokumentu z OCR do kontenera
export interface AttachmentSuggestion {
  id: number
  job_id: number
  container_id: number
  doc_kind: string
  status: 'proposed' | 'accepted' | 'rejected'
  document_type_id: number | null
  attachment_id: number | null
  created_at: string
  filename: string | null
  invoice_number: string | null
  page_from: number | null
  page_to: number | null
  container_no: string | null
}

// W5 #33/#34: wiersz raportu rozjazdów dokument ↔ system
export interface CompareRow {
  ref: string
  doc_qty: string | null
  sys_qty: string | null
  status: 'ok' | 'qty_diff' | 'qty_unknown' | 'missing_in_system' | 'missing_in_document'
}

export interface CompareReport {
  job_id: number
  kind: 'packing_list' | 'invoice'
  rows: CompareRow[]
  mismatches: number
  invoice_total?: string | null
  po_total?: string | null
  diff_pct?: number | null
  tolerance_pct?: number
  exceeded?: boolean
}

// W5 #36: szablon wysyłki dokumentów do agencji celnej
export interface DocSendTemplate {
  id: number
  customs_agency_id: number | null
  customs_agency_name: string | null
  subject: string
  body: string
  updated_at: string
}

export interface MlStats {
  ref_materials: number
  ref_examples: number
  ref_trained_at: string | null
  dockind_examples: number
  dockind_classes: string[]
  dockind_trained: boolean
  dockind_trained_at: string | null
  auto_apply_threshold: number
  min_examples: number
}

export interface InvoiceJobDetail extends InvoiceJob {
  items: InvoiceItem[]
}

export interface InvoiceBatch {
  id: number
  container_id: number
  supplier_id: number | null
  supplier_name: string | null
  total: number
  confirmed: number
  errors: number
  ready: boolean          // wszystkie faktury zatwierdzone
  excel_current: boolean  // wygenerowany Excel odpowiada bieżącemu stanowi
  jobs: InvoiceJob[]
  attachment_id: number | null
  attachment_filename: string | null
  created_at: string
  updated_at: string
  skipped?: string[]      // tylko odpowiedź wgrania: pominięte duble
}

// Agencja po wysłaniu faktur: potwierdzenie odbioru i wersje draftu SAD (spec 2026-09-29)
export interface SadDraft {
  id: number
  version: number
  attachment_id: number
  filename: string
  source: 'manual' | 'automation'
  decision: 'pending' | 'accepted' | 'rejected'
  comment: string
  created_at: string
  decided_at: string | null
  decided_by: string | null
  summary?: SadSummary | null   // z ostatniego „Porównaj” (PR 2); null = jeszcze nie porównano
  // XML z WinSAD dosyłany po PDF — dane porównania z niego zastępują odczyt PDF
  xml_attachment_id?: number | null
  xml_filename?: string | null
  data_from?: 'xml' | 'pdf' | null   // null = jeszcze nie czytano
}

export interface AgencySadState {
  ack: { at: string; source: 'manual' | 'automation'; by: string | null } | null
  drafts: SadDraft[]   // najnowsza wersja pierwsza
}

// Porównanie draftu SAD z paczką faktur (spec 2026-09-29 §2, PR 2): POST …/sad-drafts/{id}/compare
export interface SadSummary { groups: number; ok: number; diff: number; manual: number; all_ok: boolean }

// pole porównania: nasze ↔ SAD; ok === null → nie sprawdzono automatycznie (sprawdź w PDF)
export interface SadField { ours: string | null; sad: string | null; diff_pct: number | null; ok: boolean | null }

export interface SadGroup {
  cn: string
  status: 'ok' | 'diff' | 'manual' | 'missing_in_sad' | 'extra_in_sad'
  refs: string[]
  sad_items: number[]
  suppl_unit: string
  value: SadField
  net_mass: SadField
  suppl_qty: SadField | null
}

export interface SadHeaderRow {
  field: 'invoices' | 'currency' | 'total' | 'country' | 'container'
  ours: string
  sad: string | null
  diff_pct: number | null
  ok: boolean | null
  detail: string
}

export interface SadComparison {
  draft_id: number
  version: number
  pages: number
  at: string
  header: SadHeaderRow[]
  groups: SadGroup[]
  no_cn: string[]
  unread: { item: number | null; field: string }[]
  error: 'no_text' | 'unreadable_pdf' | null
  tolerances: { amount_pct: number; qty_pct: number; mass_abs_kg: number }
  summary: SadSummary
}

// --- master data materiałów ---
export interface MaterialOverride {
  company_id: number
  name_pl: string
  tariff_cn: string
  customs_code: string
  base_uom: string
  sent: boolean | null
}

export interface Material {
  id: number
  ref_code: string
  name_pl: string
  name_en: string
  ean: string
  family: string
  base_uom: string
  producer_code: string
  tariff_cn: string
  customs_code: string
  vat_rate: string
  sent: boolean
  is_active: boolean
  overrides: MaterialOverride[]
  updated_at: string
}
