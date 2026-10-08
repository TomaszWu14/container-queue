import type { MapWatcher } from './AvatarStack'

export interface Vessel {
  id: number
  name: string
  mmsi: number | null
  imo: number | null
  lat: number | null
  lon: number | null
  sog: number | null
  cog: number | null
  destination: string
  ais_eta: string | null
  last_seen: string | null
  trail: [number, number][]
  companies: string[]
  containers: number
  delayed: number
  drift_days: number | null
  eta_alert: boolean
  hours_to_dest: number | null
  near_port: string
  predicted_late: boolean
  length_m: number | null
  beam_m: number | null
  has_photo: boolean
  watchers?: MapWatcher[]
  watched?: WatchedAboard[]   // MOJE obserwowane kontenery na pokładzie (per user)
}

export interface WatchedAboard { id: number; container_no: string; reason: string }

/** Zawartość statku (karta statku): kontenery usera + pozycje zamówień. */
export interface CargoItem {
  material: string
  description: string
  quantity: string
  unit: string
}

export interface CargoContainer {
  id: number
  container_no: string
  company: string
  status: string
  eta: string | null
  is_special: boolean
  items: CargoItem[]
}

export interface VesselCargo {
  containers: CargoContainer[]
  items_visible: boolean
}
