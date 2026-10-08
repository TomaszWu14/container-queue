import type { Page } from '@playwright/test'

// Karta kontenera pod /kontenery/{id}. Edycja przez przycisk „Edytuj" (rola admin/logistics).
export class ContainerPage {
  constructor(private page: Page) {}

  async goto(id: number): Promise<void> {
    await this.page.goto(`/kontenery/${id}`)
  }

  async startEdit(): Promise<void> {
    await this.page.getByRole('button', { name: 'Edytuj' }).click()
    await this.page.getByTestId('container-form').waitFor()
  }

  async setContainerNo(no: string): Promise<void> {
    await this.page.getByTestId('container-no-input').fill(no)
  }

  async submit(): Promise<void> {
    await this.page.getByTestId('container-submit').click()
  }
}
