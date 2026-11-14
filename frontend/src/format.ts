// Czyste funkcje formatujące — bez Reacta, więc łatwe do przetestowania.
import type { Priority, TransportMode } from './api/types'

// Record<TransportMode, ...> wymusza wpis dla KAŻDEGO trybu: gdy backend dostanie nowy
// tryb i dopiszemy go do types.ts, kompilator wskaże to miejsce jako błąd.
export const MODE_LABELS: Record<TransportMode, string> = {
  train: '🚆 Pociąg',
  bus: '🚌 Autobus',
  flight: '✈️ Samolot',
  tram: '🚋 Tramwaj / metro',
  ferry: '⛴️ Prom',
  walk: '🚶 Pieszo',
}

export const PRIORITY_LABELS: Record<Priority, string> = {
  cheap: 'Najtaniej',
  fast: 'Najszybciej',
  green: 'Najbardziej ekologicznie',
}

export function formatDuration(totalMinutes: number): string {
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours === 0) {
    return `${minutes} min`
  }
  return `${hours} h ${String(minutes).padStart(2, '0')} min`
}

/** Polska odmiana: 1 przesiadka, 2–4 przesiadki, 5+ przesiadek (ale 12–14 przesiadek). */
export function formatTransfers(count: number): string {
  if (count === 0) return 'bez przesiadek'
  if (count === 1) return '1 przesiadka'
  const lastDigit = count % 10
  const lastTwoDigits = count % 100
  if (lastDigit >= 2 && lastDigit <= 4 && !(lastTwoDigits >= 12 && lastTwoDigits <= 14)) {
    return `${count} przesiadki`
  }
  return `${count} przesiadek`
}

/**
 * Godzina w strefie czasowej użytkownika (API zwraca UTC, np. "2026-11-19T06:30:00Z").
 * `timeZone` jest parametrem, żeby testy dawały ten sam wynik na każdym komputerze.
 */
export function formatTime(isoDateTime: string, timeZone?: string): string {
  return new Intl.DateTimeFormat('pl-PL', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone,
  }).format(new Date(isoDateTime))
}

export function formatDate(isoDate: string): string {
  // "2026-11-19" bez godziny JS czyta jako północ UTC — w strefie UTC-5 byłby to 18.11!
  // Dlatego formatujemy w UTC, czyli dokładnie ten dzień, który jest w stringu.
  return new Intl.DateTimeFormat('pl-PL', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  }).format(new Date(isoDate))
}

/**
 * Dzisiejsza data jako "YYYY-MM-DD" dla <input type="date"> — w LOKALNEJ strefie.
 * Pułapka: new Date().toISOString().slice(0, 10) daje datę w UTC, więc w Polsce
 * między 00:00 a 01:00/02:00 zwróciłaby jeszcze wczorajszy dzień.
 */
export function toLocalDateInputValue(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0') // getMonth() liczy od 0!
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
