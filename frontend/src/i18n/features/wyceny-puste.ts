import { defineFeature } from '../feature'

// Wyceny: pusty stan dla spedytora — nie instrukcja „utwórz zlecenie” dla logistyki (audyt UI C12, UX-034)
export default defineFeature({
  pl: {
    quoteNoneForwarder: 'Nie masz zaproszeń do wyceny.',
    quoteNoneForwarderHint: 'Gdy logistyka zaprosi Cię do wyceny transportu, zlecenie pojawi się tutaj.',
  },
  en: {
    quoteNoneForwarder: 'You have no quote invitations.',
    quoteNoneForwarderHint: 'When logistics invites you to quote a transport, the request will appear here.',
  },
  pt: {
    quoteNoneForwarder: 'Não tem convites para cotação.',
    quoteNoneForwarderHint: 'Quando a logística o convidar para cotar um transporte, o pedido aparecerá aqui.',
  },
})
