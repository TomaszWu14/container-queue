import { request } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { SeedData } from './seed-types'
import { API } from './ports'

// polityka haseł (W14 #89): min. 12 znaków — 11-znakowe hasło blokowało cały seed e2e (422)
const E2E_PASSWORD = 'E2ePass1234!'
const __dirname = dirname(fileURLToPath(import.meta.url))

// Seed przez REST admina: bootstrap() sieje tylko admina, więc scoped userów i
// kontenery A/B tworzymy tu. Uruchamiane raz przed wszystkimi testami (globalSetup).
export default async function globalSetup() {
  // baza e2e.db jest świeża na starcie backendu tylko jeśli usunięta; przy
  // reuseExistingServer lokalnie może zostać po poprzednim biegu. Seed jest
  // idempotentny na loginach/numerach — 409 (konflikt) traktujemy jako „już jest".
  const ctx = await request.newContext({ baseURL: API })

  // 1. login admina — OAuth2PasswordRequestForm (x-www-form-urlencoded)
  const login = await ctx.post('/api/auth/login', {
    form: { username: 'admin', password: 'admin123' },
  })
  if (!login.ok()) throw new Error(`Seed: login admina nieudany (${login.status()})`)

  // 2. dwie różne firmy z domyślnego seedu
  const companiesRes = await ctx.get('/api/companies')
  const companies = (await companiesRes.json()) as Array<{ id: number; code: string }>
  if (companies.length < 2) throw new Error('Seed: potrzebne min. 2 firmy w bootstrapie')
  const companyA = companies[0]
  const companyB = companies[1]

  // 3. userzy logistics scoped do A i do B (idempotentnie)
  async function ensureUser(login: string, companyId: number) {
    const res = await ctx.post('/api/users', {
      data: {
        login, full_name: `E2E ${login}`, password: E2E_PASSWORD,
        send_invite: false, role: 'logistics', company_id: companyId,
        view_all_companies: false, is_active: true,
      },
    })
    if (!res.ok() && res.status() !== 409) {
      throw new Error(`Seed: user ${login} nieudany (${res.status()}): ${await res.text()}`)
    }
  }
  await ensureUser('e2e_a', companyA.id)
  await ensureUser('e2e_b', companyB.id)

  // 4. kontenery A/B (numery ISO 6346 poprawne)
  async function ensureContainer(no: string, companyId: number): Promise<number> {
    const res = await ctx.post('/api/containers', { data: { container_no: no, company_id: companyId } })
    if (res.ok()) return (await res.json()).id as number
    if (res.status() === 409) {
      // już istnieje — znajdź po numerze na liście admina (widzi wszystko)
      const list = await ctx.get('/api/containers')
      const found = ((await list.json()) as Array<{ id: number; container_no: string }>)
        .find(c => c.container_no === no)
      if (found) return found.id
    }
    throw new Error(`Seed: kontener ${no} nieudany (${res.status()}): ${await res.text()}`)
  }
  const idA = await ensureContainer('MSDU0806613', companyA.id)
  const idB = await ensureContainer('TCLU1234568', companyB.id)

  const seed: SeedData = {
    password: E2E_PASSWORD,
    userA: { login: 'e2e_a', companyId: companyA.id },
    userB: { login: 'e2e_b', companyId: companyB.id },
    containerA: { no: 'MSDU0806613' },
    containerB: { id: idB, no: 'TCLU1234568' },
  }
  writeFileSync(join(__dirname, '.seed.json'), JSON.stringify(seed, null, 2))
  await ctx.dispose()
  void idA
}
