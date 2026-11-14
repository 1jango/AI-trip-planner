import { useState, type FormEvent } from 'react'
import type { PlanRequest, Priority } from '../api/types'
import { PRIORITY_LABELS, toLocalDateInputValue } from '../format'

type Mode = 'ai' | 'form'

interface SearchFormProps {
  aiAvailable: boolean
  isLoading: boolean
  onSearch: (request: PlanRequest) => void
  // Rodzic może wymusić formularz, np. gdy AI zwróci 503 w trakcie wyszukiwania.
  forceForm: boolean
}

const PRIORITIES: Priority[] = ['fast', 'cheap', 'green']

const EXAMPLE_QUERIES = [
  "Gdańsk → 's-Hertogenbosch w przyszły czwartek, najtaniej",
  'z Gdyni do Berlina jutro, ekologicznie',
  'Warszawa – Kraków w sobotę, jak najszybciej',
]

export function SearchForm({ aiAvailable, isLoading, onSearch, forceForm }: SearchFormProps) {
  const [preferredMode, setPreferredMode] = useState<Mode>('ai')
  const [query, setQuery] = useState('')
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [travelDate, setTravelDate] = useState(() => toLocalDateInputValue(new Date()))
  const [priority, setPriority] = useState<Priority>('fast')

  // Tryb wyliczany, a nie trzymany w osobnym stanie: bez AI zawsze formularz.
  const mode: Mode = aiAvailable && !forceForm ? preferredMode : 'form'

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault() // bez tego przeglądarka przeładowałaby stronę
    if (mode === 'ai') {
      onSearch({ query: query.trim() })
    } else {
      onSearch({
        origin: origin.trim(),
        destination: destination.trim(),
        travel_date: travelDate,
        priority,
      })
    }
  }

  return (
    <form className="card search" onSubmit={handleSubmit}>
      {aiAvailable && !forceForm && (
        <div className="tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'ai'}
            className={mode === 'ai' ? 'tab active' : 'tab'}
            onClick={() => setPreferredMode('ai')}
          >
            Jednym zdaniem (AI)
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'form'}
            className={mode === 'form' ? 'tab active' : 'tab'}
            onClick={() => setPreferredMode('form')}
          >
            Formularz
          </button>
        </div>
      )}

      {mode === 'ai' ? (
        <>
          <label className="field">
            <span>Dokąd jedziesz?</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Gdańsk → 's-Hertogenbosch w przyszły czwartek, najtaniej"
              maxLength={300}
              required
            />
          </label>
          <div className="examples">
            <span className="muted small">Wypróbuj:</span>
            {EXAMPLE_QUERIES.map((example) => (
              // Klik wpisuje przykład do pola — użytkownik widzi zdanie, zanim wyśle.
              <button
                key={example}
                type="button"
                className="chip"
                onClick={() => setQuery(example)}
              >
                {example}
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="form-grid">
          <label className="field">
            <span>Skąd</span>
            <input
              value={origin}
              onChange={(event) => setOrigin(event.target.value)}
              placeholder="Gdańsk"
              maxLength={200}
              required
            />
          </label>
          <label className="field">
            <span>Dokąd</span>
            <input
              value={destination}
              onChange={(event) => setDestination(event.target.value)}
              placeholder="Berlin"
              maxLength={200}
              required
            />
          </label>
          <label className="field">
            <span>Data</span>
            <input
              type="date"
              value={travelDate}
              min={toLocalDateInputValue(new Date())}
              onChange={(event) => setTravelDate(event.target.value)}
              required
            />
          </label>
          <label className="field">
            <span>Priorytet</span>
            <select
              value={priority}
              // value z <select> to zwykły string — rzutujemy, bo opcje pochodzą z PRIORITIES.
              onChange={(event) => setPriority(event.target.value as Priority)}
            >
              {PRIORITIES.map((value) => (
                <option key={value} value={value}>
                  {PRIORITY_LABELS[value]}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      <button type="submit" className="primary" disabled={isLoading}>
        {isLoading ? 'Szukam połączeń…' : 'Szukaj'}
      </button>
    </form>
  )
}
