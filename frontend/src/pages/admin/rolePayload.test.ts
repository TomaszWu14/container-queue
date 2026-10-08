import { describe, expect, it } from 'vitest'
import { rolePayload } from './shared'

const base = { company_id: '3', forwarder_id: '5', customs_agency_id: '7', warehouse_id: '',
               view_all_companies: true }

describe('rolePayload — partner zewnętrzny bez spółki', () => {
  it.each(['forwarder', 'customs'] as const)('%s: zeruje spółkę i „wszystkie spółki"', role => {
    const p = rolePayload({ ...base, role })
    expect(p.company_id).toBeNull()
    expect(p.view_all_companies).toBe(false)
  })

  it('rola wewnętrzna zachowuje spółkę i view_all', () => {
    const p = rolePayload({ ...base, role: 'logistics' })
    expect(p.company_id).toBe(3)
    expect(p.view_all_companies).toBe(true)
  })
})
