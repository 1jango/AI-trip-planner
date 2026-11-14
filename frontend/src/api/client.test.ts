// Testy klienta API bez backendu: podmieniamy globalne fetch() na atrapę (vi.fn).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, extractErrorMessage } from './client'

function mockFetch(response: Response | Error) {
  const fetchMock = vi.fn<typeof fetch>()
  if (response instanceof Error) {
    fetchMock.mockRejectedValue(response)
  } else {
    fetchMock.mockResolvedValue(response)
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api', () => {
  it('returns parsed JSON on success', async () => {
    const health = { status: 'ok', version: '0.1.0', ai_available: true }
    const fetchMock = mockFetch(jsonResponse(200, health))

    await expect(api.getHealth()).resolves.toEqual(health)
    expect(fetchMock).toHaveBeenCalledWith('/api/health', expect.objectContaining({}))
  })

  it('sends JSON body with Content-Type header', async () => {
    const fetchMock = mockFetch(jsonResponse(200, {}))

    await api.createPlan({ query: 'Gdańsk → Berlin jutro' })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/plan')
    expect(init?.method).toBe('POST')
    expect(init?.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(init?.body).toBe(JSON.stringify({ query: 'Gdańsk → Berlin jutro' }))
  })

  it('returns undefined for 204 No Content', async () => {
    mockFetch(new Response(null, { status: 204 }))

    await expect(api.deleteTrip(1)).resolves.toBeUndefined()
  })

  it('throws ApiError with backend message on 422', async () => {
    mockFetch(jsonResponse(422, { detail: 'Data podróży 2026-11-12 jest w przeszłości.' }))

    await expect(api.createPlan({ query: 'x' })).rejects.toEqual(
      new ApiError(422, 'Data podróży 2026-11-12 jest w przeszłości.'),
    )
  })

  it('throws ApiError with status 0 when server is unreachable', async () => {
    mockFetch(new TypeError('Failed to fetch'))

    const error = await api.getHealth().catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(0)
  })

  it('rethrows AbortError instead of reporting it as network error', async () => {
    mockFetch(new DOMException('aborted', 'AbortError'))

    await expect(api.getHealth()).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('uses fallback message when error body is not JSON', async () => {
    mockFetch(new Response('<html>Bad Gateway</html>', { status: 502 }))

    await expect(api.getHealth()).rejects.toEqual(new ApiError(502, 'Błąd serwera (HTTP 502).'))
  })
})

describe('extractErrorMessage', () => {
  it('reads string detail', () => {
    expect(extractErrorMessage({ detail: 'Trip not found' }, 'fallback')).toBe('Trip not found')
  })

  it('joins Pydantic validation messages', () => {
    const body = {
      detail: [
        { loc: ['body', 'origin'], msg: 'Field required', type: 'missing' },
        { loc: ['body', 'travel_date'], msg: 'Input should be a valid date', type: 'date' },
      ],
    }

    expect(extractErrorMessage(body, 'fallback')).toBe(
      'Field required; Input should be a valid date',
    )
  })

  it.each([null, 'text', 42, {}, { detail: 42 }, { detail: [{ foo: 1 }] }])(
    'falls back for unexpected body %j',
    (body) => {
      expect(extractErrorMessage(body, 'fallback')).toBe('fallback')
    },
  )
})
