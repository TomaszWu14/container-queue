import { test, expect } from './fixtures'
import { QueuePage } from './pages/QueuePage'
import { ContainerPage } from './pages/ContainerPage'
import { API } from './ports'

test.describe('Izolacja multi-company', () => {
  test('user firmy A nie widzi kontenera firmy B na liście kolejki', async ({ page, loginAs, seeded }) => {
    await loginAs(seeded.userA.login)
    const queue = new QueuePage(page)
    await queue.goto()
    await expect(page.getByText(seeded.containerA.no, { exact: true }).first()).toBeVisible()
    await expect(page.getByText(seeded.containerB.no, { exact: true })).toHaveCount(0)
  })

  test('user firmy A nie ma dostępu do karty kontenera firmy B (403)', async ({ page, loginAs, seeded }) => {
    await loginAs(seeded.userA.login)

    // kontrola pozytywna: karta WŁASNEGO kontenera A musi się renderować
    const list = await page.request.get(`${API}/api/containers`)
    const mine = ((await list.json()) as Array<{ id: number; container_no: string }>).find(
      (c) => c.container_no === seeded.containerA.no
    )
    expect(mine).toBeTruthy()
    const detail = new ContainerPage(page)
    await detail.goto(mine!.id)
    await expect(page.getByText(seeded.containerA.no, { exact: true }).first()).toBeVisible()

    // odmowa: karta B nigdy się nie renderuje — numer B nie pojawia się na stronie
    await detail.goto(seeded.containerB.id)
    await expect(page.getByText(seeded.containerB.no, { exact: true })).toHaveCount(0)
  })
})
