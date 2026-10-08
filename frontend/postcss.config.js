export default {
  plugins: {
    '@tailwindcss/postcss': {},
    // Autoprefixer zostaje mimo zaleceń upgrade guide'u v4: Lightning CSS prefiksuje
    // tylko output Tailwinda, a ręczny styles.css ma backdrop-filter/user-select,
    // które bez tego straciłyby prefiksy -webkit-.
    autoprefixer: {},
  },
}
