// Każdy typ sygnału z backendu (app/signals.py) ma etykietę sig_* we wszystkich językach —
// inaczej Pulpit pokazuje surowy klucz („sig_docs_pre_eta: …").
import { describe, expect, it } from 'vitest'
import { DICTS } from './i18n'

const TYPES = ['delayed', 'demurrage', 'stuck', 'missing_avizo', 'missing_eta', 'missing_docs',
  'eta_shift', 'po_unconfirmed', 'docs_pre_eta', 'special_care']

describe('etykiety sygnałów', () => {
  for (const [lang, dict] of Object.entries(DICTS)) {
    it(`${lang}: komplet sig_*`, () => {
      const missing = TYPES.filter(t => !(dict as Record<string, string>)[`sig_${t}`])
      expect(missing).toEqual([])
    })
  }
})
