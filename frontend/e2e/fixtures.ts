import { test as base } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { SeedData } from './seed-types'
import { LoginPage } from './pages/LoginPage'

const __dirname = dirname(fileURLToPath(import.meta.url))
const seed = JSON.parse(readFileSync(join(__dirname, '.seed.json'), 'utf-8')) as SeedData

export const test = base.extend<{ seeded: SeedData; loginAs: (login: string) => Promise<void> }>({
  seeded: async ({}, use) => { await use(seed) },
  loginAs: async ({ page }, use) => {
    await use(async (login: string) => {
      await new LoginPage(page).login(login, seed.password)
    })
  },
})

export { expect } from '@playwright/test'
