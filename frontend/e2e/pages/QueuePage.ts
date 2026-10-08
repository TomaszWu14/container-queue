import type { Page } from '@playwright/test'

// Lista kolejki pod /kolejka; numery kontenerów renderowane jako unikalny tekst mono.
// Domyślny zakres to bieżący tydzień — kontenery z seeda nie mają dat, więc pełny zakres.
export class QueuePage {
  constructor(private page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto('/kolejka?okres=all')
  }

  async hasContainer(no: string): Promise<boolean> {
    return this.page.getByText(no, { exact: true }).first().isVisible().catch(() => false)
  }
}
