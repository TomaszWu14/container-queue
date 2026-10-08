import { test, expect } from './fixtures'
import { QueuePage } from './pages/QueuePage'
import { ContainerPage } from './pages/ContainerPage'
import { API } from './ports'

test.describe('Kontener — widoczność, edycja, ISO 6346', () => {
  test('kontener utworzony w seedzie jest widoczny na liście właściciela', async ({ page, loginAs, seeded }) => {
    await loginAs(seeded.userA.login)
    const queue = new QueuePage(page)
    await queue.goto()
    await expect(page.getByText(seeded.containerA.no, { exact: true }).first()).toBeVisible()
  })

  test('błędny numer ISO 6346 przy edycji jest blokowany komunikatem z backendu', async ({ page, loginAs, seeded }) => {
    await loginAs(seeded.userA.login)
    // wejdź na kartę własnego kontenera (id znajdujemy przez API listy po zalogowaniu)
    const list = await page.request.get(`${API}/api/containers`)
    const mine = ((await list.json()) as Array<{ id: number; container_no: string }>)
      .find(c => c.container_no === seeded.containerA.no)
    expect(mine).toBeTruthy()

    const detail = new ContainerPage(page)
    await detail.goto(mine!.id)
    await detail.startEdit()
    await detail.setContainerNo('MSDU0806615')   // zła cyfra kontrolna
    await detail.submit()

    // backend zwraca 4xx z polskim komunikatem ISO 6346 → widoczny w form-error
    await expect(page.getByTestId('form-error')).toContainText('ISO 6346')
    // numer nie zmienił się na błędny w tytule/treści karty
    await expect(page.getByText('MSDU0806615', { exact: true })).toHaveCount(0)
  })
})
