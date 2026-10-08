export type ComplaintStatus = 'SZKIC' | 'NOWA' | 'ZGLOSZONA' | 'WYSLANA' | 'ODPOWIEDZ' | 'ZAMKNIETA'
export type ComplaintRecipient = '' | 'PRZEWOZNIK' | 'UBEZPIECZYCIEL' | 'DOSTAWCA'

export interface ProblemType {
  id: number
  name: string
  sort_order: number
  is_active: boolean
}

export interface ComplaintPhoto {
  id: number
  filename: string
  content_type: string
  size: number
  caption: string
  created_at: string
}

export interface Complaint {
  id: number
  number: string
  kind: 'PROBLEM' | 'REKLAMACJA'
  status: ComplaintStatus
  container_id: number
  container_no: string | null
  company_id: number
  description: string
  driver_note: string
  created_by_login: string | null
  created_at: string
  reported_at: string | null
  sent_at: string | null
  sent_target: string
  response_at: string | null
  closed_at: string | null
  age_days: number
  problems: string[]
  photo_count: number
  // W11: adresat + zegar przedawnienia + koszty + auto-szkic
  recipient_type: ComplaintRecipient
  deadline_at: string | null
  deadline_days_left: number | null
  claim_amount: number | null
  recovered_amount: number | null
  claim_currency: string
  auto_draft: boolean
  photos?: ComplaintPhoto[]
}

export interface ComplaintStatsRow {
  name: string
  containers: number
  with_complaint: number
  pct: number
}

export interface ComplaintCostRow {
  currency: string
  claim: number
  recovered: number
  recovery_pct: number
}

export interface ComplaintStats {
  months: number
  suppliers: ComplaintStatsRow[]
  carriers: ComplaintStatsRow[]
  costs: ComplaintCostRow[]
}

export interface ChecklistPoint {
  id: number
  name: string
  sort_order: number
  is_active: boolean
}

export type ChecklistVerdict = 'OK' | 'NOK' | 'UWAGA'

export interface ChecklistRow {
  point_id: number
  name: string
  result: ChecklistVerdict | null
  note: string
  checked_by_login: string | null
  checked_at: string | null
}
