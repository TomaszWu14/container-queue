// Testy Master data: strona pod trasą /master-data/:section? otwarta na danej sekcji.
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

export function mdAt(slug: string, page: ReactElement) {
  return (
    <MemoryRouter initialEntries={[`/master-data/${slug}`]}>
      <Routes><Route path="/master-data/:section?" element={page} /></Routes>
    </MemoryRouter>
  )
}
