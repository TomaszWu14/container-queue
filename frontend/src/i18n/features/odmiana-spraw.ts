import { defineFeature } from '../feature'

// Odmiana „N spraw w toku” przez Intl.PluralRules (audyt UI B34); forma „many/other” = csInProgress
export default defineFeature({
  pl: { csInProgress_one: 'sprawa w toku', csInProgress_few: 'sprawy w toku' },
  en: { csInProgress_one: 'case in progress', csInProgress_few: 'cases in progress' },
  pt: { csInProgress_one: 'caso em curso', csInProgress_few: 'casos em curso' },
})
