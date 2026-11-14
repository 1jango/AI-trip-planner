import { useEffect, useState } from 'react'
import { api, ApiError } from './api/client'
import type { HealthResponse, PlanRequest, PlanResponse } from './api/types'
import { PlanResults } from './components/PlanResults'
import { SearchForm } from './components/SearchForm'

// Unia stanów zamiast trzech osobnych useState (loading, error, data): nie da się
// przypadkiem pokazać jednocześnie „ładowanie” i „błąd”.
type HealthState =
  | { kind: 'loading' }
  | { kind: 'ready'; health: HealthResponse }
  | { kind: 'error'; message: string }

type PlanState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  // searchId rośnie przy każdym wyniku — używamy go jako `key`, żeby React zresetował
  // stan kart (np. „Zapisano ✓”) po nowym wyszukiwaniu.
  | { kind: 'success'; plan: PlanResponse; searchId: number }
  | { kind: 'error'; message: string }

function App() {
  const [healthState, setHealthState] = useState<HealthState>({ kind: 'loading' })
  const [planState, setPlanState] = useState<PlanState>({ kind: 'idle' })
  const [forceForm, setForceForm] = useState(false)
  const [searchCount, setSearchCount] = useState(0)

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

  async function handleSearch(request: PlanRequest) {
    setPlanState({ kind: 'loading' })
    try {
      const plan = await api.createPlan(request)
      const searchId = searchCount + 1
      setSearchCount(searchId)
      setPlanState({ kind: 'success', plan, searchId })
    } catch (error) {
      if (error instanceof ApiError && error.status === 503 && 'query' in request) {
        // AI przestało działać w trakcie (limit, timeout) — przełączamy na formularz.
        setForceForm(true)
      }
      const message = error instanceof ApiError ? error.message : 'Coś poszło nie tak.'
      setPlanState({ kind: 'error', message })
    }
  }

  const aiAvailable = healthState.kind === 'ready' && healthState.health.ai_available

  return (
    <main className="page">
      <header className="page-header">
        <h1>AI Trip Planner</h1>
        <HealthBadge state={healthState} />
      </header>
      <p className="muted">
        Wpisz podróż jednym zdaniem — pokażemy połączenia, czas i emisję CO₂.
      </p>

      <SearchForm
        aiAvailable={aiAvailable}
        forceForm={forceForm}
        isLoading={planState.kind === 'loading'}
        onSearch={handleSearch}
      />

      {planState.kind === 'error' && (
        <p className="notice notice-error" role="alert">
          {planState.message}
        </p>
      )}
      {planState.kind === 'success' && (
        <PlanResults key={planState.searchId} plan={planState.plan} />
      )}
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
