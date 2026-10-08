# Teksty funkcji

Nowe teksty interfejsu dodawaj tutaj — **jeden plik na funkcję**, nie dopisuj do
`../pl.modules.ts` / `en` / `pt` (wspólne pliki = konflikty między PR-ami).

```ts
// src/i18n/features/kalendarz.ts
import { defineFeature } from '../feature'

export default defineFeature({
  pl: { calToday: 'Dziś' },
  en: { calToday: 'Today' },
  pt: { calToday: 'Hoje' },
})
```

Plik ładuje się sam (`import.meta.glob` w `src/i18n.ts`). Test `i18n.features.test.ts` pilnuje,
żeby klucz nie powtarzał się między plikami ani z kluczami bazowymi.
