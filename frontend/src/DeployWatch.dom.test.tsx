// @vitest-environment jsdom
// Ekran wdrożenia: chwilowa przerwa sieci nic nie pokazuje; dłuższa → ekran; > 5 min → kontakt;
// serwer wraca z nową wersją → przeładowanie; nowa wersja bez przerwy → pasek „Odśwież”.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (key: string) => key }))
import DeployWatch, { CONTACT } from './DeployWatch'

let replies: (string | 'down')[] = []
const ok = (build: string) => ({ ok: true, json: async () => ({ version: build, built_at: 'x' }) })
beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn(async () => {
    const next = replies.length > 1 ? replies.shift()! : replies[0]
    if (next === 'down') throw new TypeError('Failed to fetch')
    return ok(next)
  }))
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms))

describe('DeployWatch', () => {
  it('przerwa → ekran, po 5 min kontakt, powrót z nową wersją → przeładowanie', async () => {
    replies = ['v1', 'down']
    const reload = vi.fn()
    render(<DeployWatch reload={reload} />)
    await tick(0)
    expect(screen.queryByRole('alertdialog')).toBeNull()
    await tick(60_000)          // kolejny sprawdzian: brak serwera
    expect(screen.queryByRole('alertdialog')).toBeNull()   // jedna porażka to jeszcze nie wdrożenie
    await tick(3_000)
    expect(screen.getByRole('alertdialog')).toBeTruthy()
    expect(screen.getByText('deployTitle')).toBeTruthy()
    expect(screen.queryByText(CONTACT)).toBeNull()
    await tick(5 * 60_000)
    expect(screen.getByText(CONTACT).getAttribute('href')).toBe(`mailto:${CONTACT}`)
    replies = ['v2']
    await tick(5_000)
    expect(reload).toHaveBeenCalled()
  })

  it('chwilowa przerwa (jedna porażka) — bez ekranu; nowa wersja bez przerwy → pasek „Odśwież”', async () => {
    replies = ['v1', 'down', 'v1']
    render(<DeployWatch reload={vi.fn()} />)
    await tick(0)
    await tick(60_000)
    await tick(3_000)
    expect(screen.queryByRole('alertdialog')).toBeNull()
    replies = ['v2']
    await tick(60_000)
    expect(screen.getByRole('status').textContent).toContain('deployNewVersion')
  })
})
