import type { Role } from './core'

// --- Moduł Wiedza (W16) ---

export interface KnowledgeScope {
  scope_type: 'screen' | 'port' | 'supplier' | 'customer' | 'material'
    | 'document_type' | 'process'
  scope_key: string
}

export interface KnowledgeNote {
  id: number
  scope_type: string
  scope_key: string
  title: string
  body: string
  url: string
  is_active: boolean
  created_at: string
  created_by_name: string
  created_by_id?: number | null
}

export interface TrainingTopic {
  id: number
  scope_type: string
  scope_key: string
  title: string
  body: string
  status: 'otwarty' | 'zaplanowany' | 'omowiony'
  created_at: string
  created_by_name: string
  votes: number
  my_vote: boolean
}

export interface KnowledgeBulletin {
  id: number
  title: string
  body: string
  roles: Role[]
  company_id?: number | null   // null = cała grupa
  created_at: string
  created_by_name: string
}

export interface BulletinAck {
  user_id: number
  login: string
  full_name: string
  role: Role
  read_at: string | null
}
