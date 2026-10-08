// @vitest-environment jsdom
// Strażnik audytu 2026-09-23: pilna zmiana ceny przyjmuje polski format kwoty
// („1 250,50") — backend (Decimal) dostaje „1250.50", nie 422.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
const { apiPost } = vi.hoisted(() => ({ apiPost: vi.fn() }))
vi.mock('../../api', () => ({ api: { post: apiPost } }))

import { PriceChangeForm } from './forms'
import type { TransportJob } from '../../types'

afterEach(() => { cleanup(); apiPost.mockReset() })

describe('PriceChangeForm — kwota w polskim formacie', () => {
  it.each([['1 250,50', '1250.50'], ['1250,5', '1250.5'], ['99.90', '99.90']])(
    '%s → %s', async (typed, sent) => {
      apiPost.mockResolvedValue({})
      render(<PriceChangeForm job={{ id: 7, my_quote: null } as unknown as TransportJob}
                              onAction={fn => { fn() }} />)
      fireEvent.change(screen.getAllByRole('textbox')[0], { target: { value: typed } })
      fireEvent.click(screen.getByRole('button'))
      await vi.waitFor(() => expect(apiPost).toHaveBeenCalled())
      expect(apiPost.mock.calls[0][1]).toMatchObject({ revised_amount: sent })
    })
})
