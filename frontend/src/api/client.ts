// Typowany klient API. Komponenty nie wołają fetch() bezpośrednio — dzięki temu obsługa
// błędów jest w jednym miejscu, a zmiana adresu endpointu to zmiana w jednej linii.
import type {
  HealthResponse,
  LegRead,
  LegUpdate,
  PlanRequest,
  PlanResponse,
  TripCreate,
  TripRead,
  TripUpdate,
} from './types'

// Względna ścieżka: w trybie dev Vite przekazuje /api do backendu (vite.config.ts).
const API_BASE = '/api'

/** Błąd API z kodem HTTP i komunikatem gotowym do pokazania użytkownikowi. */
export class ApiError extends Error {
  // status 0 = żądanie w ogóle nie dotarło do serwera (brak sieci, backend wyłączony).
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * FastAPI zwraca błędy jako {"detail": ...}. `detail` to string (nasze HTTPException)
 * albo lista błędów walidacji Pydantic (automatyczne 422). Odpowiedź traktujemy jako
 * `unknown` i sprawdzamy kształt krok po kroku — bez zgadywania i bez `any`.
 */
export function extractErrorMessage(body: unknown, fallback: string): string {
  if (typeof body !== 'object' || body === null || !('detail' in body)) {
    return fallback
  }
  const { detail } = body
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item: unknown) =>
        typeof item === 'object' && item !== null && 'msg' in item && typeof item.msg === 'string'
          ? item.msg
          : null,
      )
      .filter((message): message is string => message !== null)
    if (messages.length > 0) {
      return messages.join('; ')
    }
  }
  return fallback
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: init.body ? { 'Content-Type': 'application/json' } : undefined,
    })
  } catch (error) {
    // AbortError przepuszczamy dalej — to nie błąd, tylko anulowane żądanie (np. odmontowany komponent).
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new ApiError(0, 'Brak połączenia z serwerem. Czy backend jest uruchomiony?')
  }

  if (response.status === 204) {
    // 204 No Content (DELETE) nie ma body — response.json() rzuciłby błąd.
    return undefined as T
  }

  // Najpierw tekst, potem JSON: odpowiedź błędu nie zawsze jest JSON-em (np. 502 z proxy).
  const text = await response.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      extractErrorMessage(body, `Błąd serwera (HTTP ${response.status}).`),
    )
  }
  // Rzutowanie to obietnica, nie sprawdzenie: TypeScript znika po kompilacji.
  // Ufamy tu NASZEMU backendowi; dane z obcego API walidowalibyśmy (np. biblioteką zod).
  return body as T
}

function jsonBody(method: string, data: unknown, signal?: AbortSignal): RequestInit {
  return { method, body: JSON.stringify(data), signal }
}

export const api = {
  getHealth: (signal?: AbortSignal) => request<HealthResponse>('/health', { signal }),

  createPlan: (data: PlanRequest, signal?: AbortSignal) =>
    request<PlanResponse>('/plan', jsonBody('POST', data, signal)),

  listTrips: (signal?: AbortSignal) => request<TripRead[]>('/trips', { signal }),
  createTrip: (data: TripCreate) => request<TripRead>('/trips', jsonBody('POST', data)),
  updateTrip: (tripId: number, data: TripUpdate) =>
    request<TripRead>(`/trips/${tripId}`, jsonBody('PATCH', data)),
  deleteTrip: (tripId: number) => request<void>(`/trips/${tripId}`, { method: 'DELETE' }),

  updateLeg: (tripId: number, legId: number, data: LegUpdate) =>
    request<LegRead>(`/trips/${tripId}/legs/${legId}`, jsonBody('PATCH', data)),
  deleteLeg: (tripId: number, legId: number) =>
    request<void>(`/trips/${tripId}/legs/${legId}`, { method: 'DELETE' }),
}
