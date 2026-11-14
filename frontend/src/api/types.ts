// Typy odpowiadające modelom backendu (backend/app/models.py).
// Nazwy pól zostają w snake_case, tak jak w JSON-ie z API — bez warstwy konwersji
// nie ma miejsca, w którym nazwy mogłyby się rozjechać.
// Daty przychodzą jako stringi ISO 8601 (JSON nie ma typu "data").

export type Priority = 'cheap' | 'fast' | 'green'
export type TransportMode = 'train' | 'bus' | 'flight' | 'tram' | 'ferry' | 'walk'
export type LegSource = 'transitous' | 'estimate'

export interface HealthResponse {
  status: string
  version: string
  ai_available: boolean
}

export interface LegCreate {
  mode: TransportMode
  from_place: string
  to_place: string
  departure: string // np. "2026-11-19T07:30:00Z"
  arrival: string
  distance_km: number
  co2_kg: number
  source: LegSource
}

export interface LegRead extends LegCreate {
  id: number
  trip_id: number
}

// Partial<T> = wszystkie pola opcjonalne — dokładnie semantyka PATCH.
export type LegUpdate = Partial<LegCreate>

interface TripBase {
  name: string
  origin: string
  destination: string
  travel_date: string // "2026-11-19"
  priority: Priority
}

export interface TripCreate extends TripBase {
  legs: LegCreate[]
}

export interface TripRead extends TripBase {
  id: number
  created_at: string
  legs: LegRead[]
  total_co2_kg: number
  total_distance_km: number
}

export type TripUpdate = Partial<TripBase>

// Unia: ALBO zdanie dla AI, ALBO formularz. TypeScript nie pozwoli wysłać obu naraz —
// ta sama reguła, którą backend sprawdza w PlanRequest.check_query_or_form.
export type PlanRequest =
  | { query: string }
  | { origin: string; destination: string; travel_date: string; priority?: Priority }

export interface PlanOption {
  legs: LegCreate[]
  transfers: number
  departure: string
  arrival: string
  duration_minutes: number
  total_distance_km: number
  total_co2_kg: number
  estimated_cost_eur: number
  is_estimate: boolean
  recommended: boolean
}

export interface PlanResponse {
  origin: string
  destination: string
  origin_name: string
  destination_name: string
  travel_date: string
  priority: Priority
  parsed_by: 'ai' | 'form'
  options: PlanOption[]
  recommendation: string | null
  warnings: string[]
  data_sources_url: string
}
