import { defineFeature } from '../feature'

// XML SADUE (WinSAD) z faktur paczki — przycisk przy paczce i załącznik w mailu do agencji
export default defineFeature({
  pl: {
    invSadueXml: 'Pobierz XML (WinSAD)', mailPrevKind_sadue: 'XML do WinSAD (pozycje SAD)',
    invSadueXmlHint: 'Pozycje zgłoszenia z zatwierdzonych faktur (grupy CN × kraj pochodzenia) do importu w WinSAD agencji. Pozycja bez REF lub CN blokuje XML.',
  },
  en: {
    invSadueXml: 'Download XML (WinSAD)', mailPrevKind_sadue: 'XML for WinSAD (SAD items)',
    invSadueXmlHint: 'Declaration items from confirmed invoices (CN × origin groups) for import into the agency’s WinSAD. An item without REF or CN blocks the XML.',
  },
  pt: {
    invSadueXml: 'Descarregar XML (WinSAD)', mailPrevKind_sadue: 'XML para WinSAD (linhas do DAU)',
    invSadueXmlHint: 'Linhas da declaração a partir das faturas confirmadas (grupos NC × origem) para importar no WinSAD do despachante. Uma linha sem REF ou NC bloqueia o XML.',
  },
})
