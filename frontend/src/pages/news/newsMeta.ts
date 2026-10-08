// Ikony kategorii Aktualności (Lucide — zasada repo: bez emoji jako ikon).
import { BellRingIcon, ClipboardListIcon, MessageSquareIcon, ShipIcon, StampIcon, TruckIcon } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { NewsCategory } from './newsModel'

export const CATEGORY_ICON: Record<NewsCategory, LucideIcon> = {
  vessels: ShipIcon, customs: StampIcon, orders: ClipboardListIcon,
  deliveries: TruckIcon, messages: MessageSquareIcon, system: BellRingIcon,
}
