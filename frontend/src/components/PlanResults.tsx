import { useState } from 'react'
import { api, ApiError } from '../api/client'
import type { PlanOption, PlanResponse } from '../api/types'
import {
  MODE_LABELS,
  PRIORITY_LABELS,
  formatDate,
  formatDuration,
  formatTime,
  formatTransfers,
} from '../format'

type SaveState =
  | { kind: 'idle' }
  | { kind: 'saving'; index: number }
  | { kind: 'saved'; index: number }
  | { kind: 'error'; index: number; message: string }

interface PlanResultsProps {
  plan: PlanResponse
  onSaved: () => void
}

export function PlanResults({ plan, onSaved }: PlanResultsProps) {
  const [saveState, setSaveState] = useState<SaveState>({ kind: 'idle' })

  async function saveOption(option: PlanOption, index: number) {
    setSaveState({ kind: 'saving', index })
    try {
      // Etapy z /api/plan mają format LegCreate — wysyłamy je bez żadnej konwersji.
      await api.createTrip({
        name: `${plan.origin} → ${plan.destination}`,
        origin: plan.origin,
        destination: plan.destination,
        travel_date: plan.travel_date,
        priority: plan.priority,
        legs: option.legs,
      })
      setSaveState({ kind: 'saved', index })
      onSaved()
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Nie udało się zapisać.'
      setSaveState({ kind: 'error', index, message })
    }
  }

  return (
    <section className="results">
      <h2>
        {plan.origin_name} → {plan.destination_name}
      </h2>
      <p className="muted">
        {formatDate(plan.travel_date)} · {PRIORITY_LABELS[plan.priority]}
        {plan.parsed_by === 'ai' && ' · rozpoznane przez AI'}
      </p>

      {plan.warnings.map((warning) => (
        <p key={warning} className="notice notice-warn">
          {warning}
        </p>
      ))}

      {plan.recommendation && <p className="notice notice-ok">{plan.recommendation}</p>}

      {/* key = indeks jest tu bezpieczny: lista przychodzi w całości z API i nie zmienia
          kolejności w trakcie wyświetlania. Przy listach edytowalnych używaj stabilnych id. */}
      {plan.options.map((option, index) => (
        <OptionCard
          key={index}
          option={option}
          saveLabel={saveLabel(saveState, index)}
          saveDisabled={saveState.kind === 'saving' || isSaved(saveState, index)}
          saveError={saveState.kind === 'error' && saveState.index === index ? saveState.message : null}
          onSave={() => saveOption(option, index)}
        />
      ))}

      <p className="muted small">
        Rozkłady jazdy:{' '}
        <a href={plan.data_sources_url} target="_blank" rel="noreferrer">
          Transitous i jego źródła danych
        </a>
        .
      </p>
    </section>
  )
}

function isSaved(state: SaveState, index: number): boolean {
  return state.kind === 'saved' && state.index === index
}

function saveLabel(state: SaveState, index: number): string {
  if (state.kind === 'saving' && state.index === index) return 'Zapisywanie…'
  if (isSaved(state, index)) return 'Zapisano'
  return 'Zapisz plan'
}

interface OptionCardProps {
  option: PlanOption
  saveLabel: string
  saveDisabled: boolean
  saveError: string | null
  onSave: () => void
}

function OptionCard({ option, saveLabel, saveDisabled, saveError, onSave }: OptionCardProps) {
  return (
    <article className={option.recommended ? 'card option recommended' : 'card option'}>
      <header className="option-header">
        <div>
          <strong className="option-times">
            {formatTime(option.departure)} → {formatTime(option.arrival)}
          </strong>
          {option.recommended && <span className="badge badge-ok">Polecane</span>}
          {option.is_estimate && <span className="badge badge-warn">Szacunek</span>}
        </div>
        <button type="button" onClick={onSave} disabled={saveDisabled}>
          {saveLabel}
        </button>
      </header>

      <ul className="stats">
        <li>{formatDuration(option.duration_minutes)}</li>
        <li>{formatTransfers(option.transfers)}</li>
        <li>{option.total_distance_km.toFixed(0)} km</li>
        <li>{option.total_co2_kg.toFixed(1)} kg CO₂e</li>
        <li>ok. {option.estimated_cost_eur.toFixed(0)} €</li>
      </ul>

      <ol className="legs">
        {option.legs.map((leg, legIndex) => (
          <li key={legIndex}>
            <span className="leg-time">
              {formatTime(leg.departure)}–{formatTime(leg.arrival)}
            </span>{' '}
            {MODE_LABELS[leg.mode]}: {leg.from_place} → {leg.to_place}{' '}
            <span className="muted">
              ({leg.distance_km.toFixed(0)} km, {leg.co2_kg.toFixed(1)} kg CO₂e
              {leg.source === 'estimate' && ', szacunek'})
            </span>
          </li>
        ))}
      </ol>

      {saveError && <p className="notice notice-error">{saveError}</p>}
    </article>
  )
}
