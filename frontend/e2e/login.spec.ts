import { expect, test } from '@playwright/test'
import { LoginPage } from './pages/LoginPage'

// E2E lokalny — uruchamia prawdziwy backend+frontend (patrz playwright.config.ts / README).
// Zakłada świeżą bazę dev (admin/admin123 z bootstrap()).
// „/" renderuje bezpośrednio ekran logowania (formularz #kl2-login/#kl2-pass).

test('logowanie poprawnymi danymi wpuszcza do panelu', async ({ page }) => {
  const login = new LoginPage(page)
  await login.submit('admin', 'admin123')
  await expect(login.userMenu()).toBeVisible()
})

test('błędne hasło pokazuje komunikat i nie wpuszcza', async ({ page }) => {
  const login = new LoginPage(page)
  await login.submit('admin', 'zle-haslo')
  await expect(page.getByText('Błędny login lub hasło.')).toBeVisible()
  await expect(login.userMenu()).not.toBeVisible()
})

test('wylogowanie wraca do ekranu logowania', async ({ page }) => {
  const login = new LoginPage(page)
  await login.login('admin', 'admin123')
  await login.logout()
  await expect(login.userMenu()).not.toBeVisible()
  await expect(page.locator('#kl2-login')).toBeVisible()
})
