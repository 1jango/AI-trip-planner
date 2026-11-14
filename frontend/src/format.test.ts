import { describe, expect, it } from 'vitest'
import {
  formatDate,
  formatDuration,
  formatTime,
  formatTransfers,
  fromDateTimeLocalValue,
  toDateTimeLocalValue,
  toLocalDateInputValue,
} from './format'

describe('formatDuration', () => {
  it.each([
    [45, '45 min'],
    [60, '1 h 00 min'],
    [125, '2 h 05 min'],
    [870, '14 h 30 min'],
  ])('%i minut → %s', (minutes, expected) => {
    expect(formatDuration(minutes)).toBe(expected)
  })
})

describe('formatTransfers', () => {
  // Te same przypadki co w backendzie (test_format_transfers_polish_plural).
  it.each([
    [0, 'bez przesiadek'],
    [1, '1 przesiadka'],
    [2, '2 przesiadki'],
    [4, '4 przesiadki'],
    [5, '5 przesiadek'],
    [12, '12 przesiadek'],
    [14, '14 przesiadek'],
    [22, '22 przesiadki'],
    [25, '25 przesiadek'],
  ])('%i → %s', (count, expected) => {
    expect(formatTransfers(count)).toBe(expected)
  })
})

describe('formatTime', () => {
  it('converts UTC to the given time zone', () => {
    expect(formatTime('2026-11-19T06:30:00Z', 'Europe/Warsaw')).toBe('07:30')
    expect(formatTime('2026-11-19T06:30:00Z', 'UTC')).toBe('06:30')
  })
})

describe('formatDate', () => {
  it('keeps the calendar day from the string', () => {
    expect(formatDate('2026-11-19')).toBe('czwartek, 19 listopada')
  })
})

describe('toLocalDateInputValue', () => {
  it('uses local date parts with zero padding', () => {
    // Konstruktor z liczbami tworzy datę w LOKALNEJ strefie — test działa wszędzie.
    expect(toLocalDateInputValue(new Date(2026, 0, 5, 0, 30))).toBe('2026-01-05')
  })
})

describe('datetime-local conversion', () => {
  it('round-trips through the local input value', () => {
    // Wynik pośredni zależy od strefy komputera, ale powrót musi dać ten sam moment.
    const iso = '2026-11-19T06:30:00.000Z'

    const localValue = toDateTimeLocalValue(iso)

    expect(localValue).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    expect(fromDateTimeLocalValue(localValue)).toBe(iso)
  })

  it('builds the input value from local date parts', () => {
    const localMoment = new Date(2026, 10, 19, 7, 5) // 19.11.2026 07:05 czasu lokalnego

    expect(toDateTimeLocalValue(localMoment.toISOString())).toBe('2026-11-19T07:05')
  })
})
