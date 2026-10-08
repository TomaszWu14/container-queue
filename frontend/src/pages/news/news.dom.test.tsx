// @vitest-environment jsdom
// Aktualności na Pulpicie (spec 2026-10-01): kolumny tematów, wątki (jedna karta na kontener /
// statek), akcje wg rodzaju, przypięte pilne, szuflada = przeczytana, link z dzwonka ?wiadomosc=<id>.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { createContext } from 'react'

vi.mock('../../i18n', () => ({
  useT: () => (key: string) => key,
  LangContext: createContext({ lang: 'pl' }),
  localeFor: () => 'pl-PL',
}))
const get = vi.fn()
const post = vi.fn()
vi.mock('../../api', () => ({
  api: { get: (p: string) => get(p), post: (p: string, b: unknown) => post(p, b) },
  errorMessage: (e: unknown) => String(e),
}))

import NewsFeed from './NewsFeed'
import { newsAction, toCards } from './newsModel'
import type { NewsItem } from './newsModel'

const item = (id: number, over: Partial<NewsItem> = {}): NewsItem => ({
  id, kind: 'vessel_port', title: `Statek MV DEMO HELIOS w porcie ${id}`, body: '', container_id: null,
  is_read: false, created_at: '2026-10-01T08:00:00', category: 'vessels', priority: 'normal',
  thread_key: 'v:MV DEMO HELIOS', containers: [], ...over,
})

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('newsModel', () => {
  it('jedna karta na wątek, licznik wcześniejszych, nieprzeczytana gdy którakolwiek', () => {
    const cards = toCards([item(3, { is_read: true }), item(2), item(1, { thread_key: 'c:7', kind: 'customs', category: 'customs', title: 'Odprawa' })])
    expect(cards.map(c => [c.item.id, c.earlier, c.unread])).toEqual([[3, 1, true], [1, 0, true]])
  })

  it('akcja wg rodzaju: statek → kolejka z nazwą statku, odprawa → /odprawa', () => {
    expect(newsAction(item(1))).toEqual(['newsActQueue', '/kolejka?q=MV%20DEMO%20HELIOS'])
    expect(newsAction(item(2, { kind: 'customs', category: 'customs', title: 'Odprawa zlecona' })))
      .toEqual(['newsActCustoms', '/odprawa'])
    expect(newsAction(item(3, { kind: 'message', category: 'messages', title: 'Wiadomość' }))).toBeNull()
  })
})

describe('NewsFeed', () => {
  const urgent = item(9, { kind: 'system-error', category: 'system', priority: 'urgent', title: 'Błąd serwera', thread_key: 'n:9' })
  const customs = item(5, { kind: 'customs', category: 'customs', title: 'Odprawa zlecona', thread_key: 'c:5' })
  const byCat: Record<string, NewsItem[]> = { vessels: [item(2), item(1)], customs: [customs], system: [urgent] }
  const mount = (url = '/pulpit') => {
    get.mockImplementation((p: string) => {
      if (p.startsWith('/api/notifications/feed')) {
        const cat = new URLSearchParams(p.split('?')[1]).get('category') ?? ''
        return Promise.resolve({ items: byCat[cat] ?? [], pinned: [urgent], has_more: cat === 'vessels' })
      }
      if (p.includes('/thread')) return Promise.resolve({ items: [item(2), item(1)] })
      return Promise.reject(new Error(p))
    })
    post.mockResolvedValue({ ok: true })
    return render(<MemoryRouter initialEntries={[url]}><NewsFeed /></MemoryRouter>)
  }

  it('6 zapytań po kategorii; kolumna na temat, wątek statku jako jedna karta z „+1”', async () => {
    mount()
    const col = within(await screen.findByTestId('news-col-vessels'))
    expect(await col.findByText('Statek MV DEMO HELIOS w porcie 2')).toBeTruthy()
    expect(col.getByText('+1 newsEarlier')).toBeTruthy()
    expect(col.getByText('newsLoadOlder')).toBeTruthy()
    const cats = get.mock.calls.map(([p]) => new URLSearchParams(String(p).split('?')[1]).get('category'))
    expect(cats.sort()).toEqual(['customs', 'deliveries', 'messages', 'orders', 'system', 'vessels'])
    expect(within(screen.getByTestId('news-col-customs')).getByText('Odprawa zlecona')).toBeTruthy()
  })

  it('pilne przypięte nad kolumnami, nie dublują się w kolumnie; puste kolumny zwinięte z „0”', async () => {
    mount()
    expect(await screen.findByText('newsPinned', { selector: 'h3' })).toBeTruthy()
    expect(screen.getAllByText('Błąd serwera')).toHaveLength(1)
    await waitFor(() => expect(screen.getByTestId('news-col-orders').className).toContain('collapsed'))
    expect(within(screen.getByTestId('news-col-orders')).getByText('0')).toBeTruthy()
    expect(screen.getByTestId('news-col-system').className).toContain('collapsed')   // jedyna wiadomość przypięta
    expect(screen.getByTestId('news-col-vessels').className).not.toContain('collapsed')
  })

  it('„Załaduj starsze” dociąga tylko swoją kategorię', async () => {
    mount()
    fireEvent.click(await within(await screen.findByTestId('news-col-vessels')).findByText('newsLoadOlder'))
    await waitFor(() => expect(get).toHaveBeenCalledWith(expect.stringMatching(/category=vessels.*before_id=1/)))
  })

  it('klik w kartę otwiera szufladę i oznacza jako przeczytaną; Esc zamyka', async () => {
    mount()
    fireEvent.click(await screen.findByText('Statek MV DEMO HELIOS w porcie 2'))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/notifications/read?notification_id=2', {}))
    const drawer = screen.getByRole('dialog')
    expect(within(drawer).getByRole('heading', { level: 2, name: 'Statek MV DEMO HELIOS w porcie 2' })).toBeTruthy()
    expect(within(drawer).getByText('newsActQueue')).toBeTruthy()
    expect(document.activeElement).toBe(within(drawer).getByRole('button', { name: 'newsClose' }))
    await waitFor(() => expect(within(drawer).getByText('newsThread (1)')).toBeTruthy())
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('?wiadomosc=<id> z dzwonka otwiera wiadomość w szufladzie', async () => {
    mount('/pulpit?wiadomosc=2')
    const drawer = await screen.findByRole('dialog')
    expect(within(drawer).getByRole('heading', { level: 2, name: 'Statek MV DEMO HELIOS w porcie 2' })).toBeTruthy()
  })

  it('filtry: status i ważność idą do API, chip kategorii ukrywa kolumnę', async () => {
    mount()
    await screen.findByTestId('news-col-vessels')
    fireEvent.click(screen.getByRole('button', { name: 'newsStatusRead' }))
    await waitFor(() => expect(get).toHaveBeenCalledWith(expect.stringContaining('status=read')))
    fireEvent.change(screen.getByLabelText('newsFilterPriority'), { target: { value: 'urgent' } })
    await waitFor(() => expect(get).toHaveBeenCalledWith(expect.stringMatching(/status=read.*priority=urgent/)))
    const chip = within(screen.getByRole('group', { name: 'newsFilterCats' })).getByText('newsCat_customs')
    fireEvent.click(chip)
    expect(chip.getAttribute('aria-pressed')).toBe('false')
    expect(screen.queryByTestId('news-col-customs')).toBeNull()
  })

  it('status na karcie: „Nowa” + przełącznik oznacza cały wątek jako przeczytany bez otwierania', async () => {
    mount()
    const col = within(await screen.findByTestId('news-col-vessels'))
    expect(await col.findByText('newsStatusNew')).toBeTruthy()
    fireEvent.click(col.getByRole('button', { name: 'newsMarkRead' }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/notifications/read?notification_id=2', {}))
    expect(post).toHaveBeenCalledWith('/api/notifications/read?notification_id=1', {})
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(col.queryByText('newsStatusNew')).toBeNull()
    fireEvent.click(col.getByRole('button', { name: 'newsMarkUnread' }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/notifications/unread?notification_id=2', {}))
  })
})
