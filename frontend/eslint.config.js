// ESLint panelu (CODE-002): typescript-eslint (recommended, bez reguł wymagających typów)
// + reguły hooków Reacta. Uruchamianie: `npm run lint` (instalacja: `npm run lint:setup`).
//
// Wtyczki ładujemy z osobnego pakietu tools/eslint: typescript-eslint potrzebuje TypeScriptu
// < 6.1 (API kompilatora w JS), a panel buduje TypeScript 7 (natywny, bez tego API) —
// w jednym package.json to konflikt peer-dependency. Tam TS służy tylko do parsowania.
import { createRequire } from 'node:module'

const require = createRequire(new URL('./tools/eslint/package.json', import.meta.url))
const js = require('@eslint/js')
const globals = require('globals')
const reactHooks = require('eslint-plugin-react-hooks')
const tseslint = require('typescript-eslint')

// Dług sprzed wprowadzenia lintera (2026-09-28): w tych plikach reguła tylko ostrzega.
// Lista może tylko maleć — poprawiając plik, usuń go stąd (nowy kod w innych plikach = błąd).
const LEGACY_WARN = {
  'react-hooks/exhaustive-deps': ['src/CustomsPanels.tsx', 'src/DriverPanel.tsx',
    'src/pages/admin/ProblemsTab.tsx', 'src/pages/queueFill.tsx'],
  '@typescript-eslint/no-explicit-any': ['src/pages/LandingPage.tsx'],
  'no-useless-assignment': ['src/pages/queue/EnterpriseGroup.tsx'],
}

export default tseslint.config(
  { ignores: ['dist/**', 'tools/**', 'e2e/**', 'public/**', '*.config.*', '*.mjs'] },
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: { globals: { ...globals.browser } },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      // warunkowe/pętlowe hooki psują stan komponentu
      'react-hooks/rules-of-hooks': 'error',
      // niestabilne zależności efektów: pętle zapytań → 429, stare domknięcia (5cb3716).
      // Świadomy wyjątek: `// eslint-disable-next-line react-hooks/exhaustive-deps` + powód.
      'react-hooks/exhaustive-deps': 'error',
      // `_arg` = celowo nieużyty (jak noUnusedParameters w tsc)
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }],
      // `cond ? a() : b()` / `ok && run()` jako instrukcja — styl przyjęty w kodzie
      '@typescript-eslint/no-unused-expressions': ['error', {
        allowShortCircuit: true, allowTernary: true }],
    },
  },
  ...Object.entries(LEGACY_WARN).map(([rule, files]) => ({ files, rules: { [rule]: 'warn' } })),
)
