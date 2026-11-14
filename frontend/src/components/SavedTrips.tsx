import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { LegRead, TransportMode, TripRead } from '../api/types'
import {
  MODE_LABELS,
  PRIORITY_LABELS,
  formatDate,
  formatDateTime,
  fromDateTimeLocalValue,
  toDateTimeLocalValue,
} from '../format'

type TripsState =
  | { kind: 'loading' }
  | { kind: 'ready'; trips: TripRead[] }
  | { kind: 'error'; message: string }

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Coś poszło nie tak.'
}

interface SavedTripsProps {
  // Rodzic zwiększa tę liczbę po zapisaniu planu — zmiana uruchamia ponowne pobranie listy.
  refreshKey: number
}

export function SavedTrips({ refreshKey }: SavedTripsProps) {
  const [state, setState] = useState<TripsState>({ kind: 'loading' })

  // Pierwsze pobranie i odświeżenie po zapisaniu planu (zmiana refreshKey).
  // Stan ustawiamy dopiero w .then(), po odpowiedzi serwera — nie synchronicznie w efekcie.
  useEffect(() => {
    const controller = new AbortController()
    api
      .listTrips(controller.signal)
      .then((trips) => setState({ kind: 'ready', trips }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setState({ kind: 'error', message: errorMessage(error) })
      })
    return () => controller.abort()
  }, [refreshKey])

  // Odświeżenie po edycji/usunięciu w kartach. useCallback: ta sama funkcja między
  // renderami, więc karty nie dostają za każdym razem „nowego” propsa.
  const reload = useCallback(async () => {
    try {
      setState({ kind: 'ready', trips: await api.listTrips() })
    } catch (error) {
      setState({ kind: 'error', message: errorMessage(error) })
    }
  }, [])

  return (
    <section className="saved">
      <h2>Zapisane plany</h2>
      {state.kind === 'loading' && <p className="muted">Ładowanie…</p>}
      {state.kind === 'error' && <p className="notice notice-error">{state.message}</p>}
      {state.kind === 'ready' && state.trips.length === 0 && (
        <p className="muted">Nie masz jeszcze zapisanych planów — kliknij „Zapisz plan” przy wyniku.</p>
      )}
      {state.kind === 'ready' &&
        // key = id z bazy (nie indeks!): po usunięciu planu React nie pomyli wierszy.
        state.trips.map((trip) => <TripCard key={trip.id} trip={trip} onChanged={reload} />)}
    </section>
  )
}

// ---------- Jeden plan ----------

interface TripCardProps {
  trip: TripRead
  onChanged: () => Promise<void>
}

function TripCard({ trip, onChanged }: TripCardProps) {
  const [isRenaming, setIsRenaming] = useState(false)
  const [newName, setNewName] = useState(trip.name)
  const [error, setError] = useState<string | null>(null)

  // Wspólny wzorzec dla każdej zmiany: wyślij → odśwież listę → albo pokaż błąd.
  // Prostsze niż ręczne poprawianie stanu (sumy CO₂ i km liczy backend).
  async function run(action: () => Promise<unknown>): Promise<boolean> {
    setError(null)
    try {
      await action()
      await onChanged()
      return true
    } catch (caught) {
      setError(errorMessage(caught))
      return false
    }
  }

  async function handleRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (await run(() => api.updateTrip(trip.id, { name: newName.trim() }))) {
      setIsRenaming(false)
    }
  }

  async function handleDeleteTrip() {
    if (window.confirm(`Usunąć plan „${trip.name}”?`)) {
      await run(() => api.deleteTrip(trip.id))
    }
  }

  return (
    // <details> to natywne rozwijanie w HTML — bez dodatkowego stanu w React.
    <details className="card trip">
      <summary>
        <strong>{trip.name}</strong>
        <span className="muted">
          {' '}
          · {formatDate(trip.travel_date)} · {trip.total_distance_km.toFixed(0)} km ·{' '}
          {trip.total_co2_kg.toFixed(1)} kg CO₂e
        </span>
      </summary>

      <p className="muted small">
        {trip.origin} → {trip.destination} · {PRIORITY_LABELS[trip.priority]}
      </p>

      {isRenaming ? (
        <form className="inline-form" onSubmit={handleRename}>
          <input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            maxLength={200}
            required
            aria-label="Nowa nazwa planu"
          />
          <button type="submit">Zapisz</button>
          <button type="button" onClick={() => setIsRenaming(false)}>
            Anuluj
          </button>
        </form>
      ) : (
        <div className="actions">
          <button type="button" onClick={() => setIsRenaming(true)}>
            Zmień nazwę
          </button>
          <button type="button" className="danger" onClick={handleDeleteTrip}>
            Usuń plan
          </button>
        </div>
      )}

      {error && <p className="notice notice-error">{error}</p>}

      {trip.legs.length === 0 ? (
        <p className="muted">Ten plan nie ma już etapów.</p>
      ) : (
        <ol className="legs">
          {trip.legs.map((leg) => (
            <LegRow key={leg.id} leg={leg} onChanged={onChanged} />
          ))}
        </ol>
      )}
    </details>
  )
}

// ---------- Jeden etap ----------

const MODES = Object.keys(MODE_LABELS) as TransportMode[]

interface LegRowProps {
  leg: LegRead
  onChanged: () => Promise<void>
}

function LegRow({ leg, onChanged }: LegRowProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [mode, setMode] = useState<TransportMode>(leg.mode)
  const [departure, setDeparture] = useState(() => toDateTimeLocalValue(leg.departure))
  const [arrival, setArrival] = useState(() => toDateTimeLocalValue(leg.arrival))
  const [error, setError] = useState<string | null>(null)

  function startEditing() {
    // Świeże wartości z propsów — po poprzedniej edycji lista mogła się odświeżyć.
    setMode(leg.mode)
    setDeparture(toDateTimeLocalValue(leg.departure))
    setArrival(toDateTimeLocalValue(leg.arrival))
    setError(null)
    setIsEditing(true)
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    try {
      // Wysyłamy tylko pola, które się zmieniły (semantyka PATCH). Zmiana trybu sprawi,
      // że backend sam przeliczy CO₂ i oznaczy etap jako szacunek.
      await api.updateLeg(leg.trip_id, leg.id, {
        ...(mode !== leg.mode && { mode }),
        departure: fromDateTimeLocalValue(departure),
        arrival: fromDateTimeLocalValue(arrival),
      })
      setIsEditing(false)
      await onChanged()
    } catch (caught) {
      // 422 z backendu, np. „Przyjazd nie może być wcześniejszy niż odjazd”.
      setError(errorMessage(caught))
    }
  }

  async function handleDelete() {
    if (!window.confirm(`Usunąć etap ${leg.from_place} → ${leg.to_place}?`)) return
    try {
      await api.deleteLeg(leg.trip_id, leg.id)
      await onChanged()
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  if (isEditing) {
    return (
      <li>
        <form className="leg-form" onSubmit={handleSave}>
          <select
            value={mode}
            onChange={(event) => setMode(event.target.value as TransportMode)}
            aria-label="Środek transportu"
          >
            {MODES.map((value) => (
              <option key={value} value={value}>
                {MODE_LABELS[value]}
              </option>
            ))}
          </select>
          <input
            type="datetime-local"
            value={departure}
            onChange={(event) => setDeparture(event.target.value)}
            required
            aria-label="Odjazd"
          />
          <input
            type="datetime-local"
            value={arrival}
            onChange={(event) => setArrival(event.target.value)}
            required
            aria-label="Przyjazd"
          />
          <button type="submit">Zapisz</button>
          <button type="button" onClick={() => setIsEditing(false)}>
            Anuluj
          </button>
        </form>
        {error && <p className="notice notice-error">{error}</p>}
      </li>
    )
  }

  return (
    <li>
      <span className="leg-time">
        {formatDateTime(leg.departure)} – {formatDateTime(leg.arrival)}
      </span>{' '}
      {MODE_LABELS[leg.mode]}: {leg.from_place} → {leg.to_place}{' '}
      <span className="muted">
        ({leg.distance_km.toFixed(0)} km, {leg.co2_kg.toFixed(1)} kg CO₂e
        {leg.source === 'estimate' && ', szacunek'})
      </span>{' '}
      <button type="button" className="link" onClick={startEditing}>
        Edytuj
      </button>
      <button type="button" className="link danger" onClick={handleDelete}>
        Usuń
      </button>
      {error && <p className="notice notice-error">{error}</p>}
    </li>
  )
}
