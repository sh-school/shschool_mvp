/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        adaam: { DEFAULT: '#8A1538', light: '#A01B42', dark: '#6B1029' },
        gold:  '#C9A84C',
      },
      fontFamily: {
        tajawal: ['Tajawal', 'Arial', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
