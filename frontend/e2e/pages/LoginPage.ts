import type { Locator, Page } from '@playwright/test'

// „/" renderuje bezpośrednio ekran logowania (bez landingowego topnavu) —
// selektory jak w login.spec.ts. „Wyloguj” siedzi w rozwijanym menu użytkownika (ukryte do
// kliknięcia), więc znacznikiem zalogowania jest przycisk menu (.tn-user) w pasku górnym.
export class LoginPage {
  constructor(private page: Page) {}

  userMenu(): Locator {
    return this.page.locator('button.tn-user')
  }

  async submit(user: string, pass: string): Promise<void> {
    await this.page.goto('/')
    await this.page.locator('#kl2-login').fill(user)
    await this.page.locator('#kl2-pass').fill(pass)
    await this.page.getByRole('button', { name: 'Zaloguj się' }).click()
  }

  async login(user: string, pass: string): Promise<void> {
    await this.submit(user, pass)
    await this.userMenu().waitFor()
  }

  async logout(): Promise<void> {
    await this.userMenu().click()
    await this.page.getByRole('button', { name: 'Wyloguj' }).click()
  }
}
