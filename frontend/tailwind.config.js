/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  // Preflight pozostaje wyłączony, ale w v4 decyduje o tym src/tailwind.css (nie importuje
  // preflight.css) — klucz corePlugins nie istnieje już w v4 i byłby cichym no-opem.
  theme: {
    extend: {
      // mostek do istniejących tokenów (zmienne CSS) — jedno źródło kolorów.
      // dzięki temu bg-panel / text-muted / border-border działają spójnie ze starym CSS.
      colors: {
        bg: 'var(--bg)',
        panel: 'var(--panel)',
        border: 'var(--border)',
        text: 'var(--text)',
        muted: 'var(--muted)',
        accent: 'var(--accent)',
        danger: 'var(--danger)',
      },
      borderRadius: {
        DEFAULT: '9px',
      },
    },
  },
  plugins: [],
}
