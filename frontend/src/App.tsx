import { useEffect, useState } from 'react'
import { api, ApiError } from './api/client'
import type { HealthResponse } from './api/types'

// Unia stanów zamiast trzech osobnych useState (loading, error, data): nie da się
// przypadkiem pokazać jednocześnie „ładowanie” i „błąd”.
type HealthState =
  | { kind: 'loading' }
  | { kind: 'ready'; health: HealthResponse }
  | { kind: 'error'; message: string }

function App() {
  const [healthState, setHealthState] = useState<HealthState>({ kind: 'loading' })

  useEffect(() => {
    // AbortController anuluje żądanie, gdy komponent zniknie (w trybie dev StrictMode
    // celowo montuje komponenty dwa razy — bez tego wysyłalibyśmy zbędne zapytania).
    const controller = new AbortController()
    api
      .getHealth(controller.signal)
      .then((health) => setHealthState({ kind: 'ready', health }))
      .catch((error: unknown) => {
        if (error instanceof ApiError) {
          setHealthState({ kind: 'error', message: error.message })
        }
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="page">
      <header className="page-header">
        <h1>AI Trip Planner</h1>
        <HealthBadge state={healthState} />
      </header>
      <p className="muted">
        Wpisz podróż jednym zdaniem — pokażemy połączenia, czas i emisję CO₂.
      </p>
    </main>
  )
}

function HealthBadge({ state }: { state: HealthState }) {
  switch (state.kind) {
    case 'loading':
      return <span className="badge">Łączenie z serwerem…</span>
    case 'error':
      return <span className="badge badge-error">{state.message}</span>
    case 'ready':
      return state.health.ai_available ? (
        <span className="badge badge-ok">AI dostępne</span>
      ) : (
        <span className="badge badge-warn">AI niedostępne — użyj formularza</span>
      )
  }
}

export default App
