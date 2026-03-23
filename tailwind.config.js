/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        adaam: {
          DEFAULT: '#8A1538',
          light: '#A01B42',
          dark: '#6B1029',
          bg: '#fdf2f5',
          border: '#e8b4c3',
        },
        gold: {
          DEFAULT: '#C9A84C',
          light: '#E0C76E',
          dark: '#A88A30',
          bg: '#fdf8ed',
          border: '#f0dfa0',
        },
        skyline: { DEFAULT: '#0D4261', light: '#1A5C80' },
        palm:    { DEFAULT: '#129B82', light: '#17BFA0' },
        sea:     { DEFAULT: '#4194B3', light: '#5BB0CC' },
      },
      fontFamily: {
        tajawal: ['Tajawal', 'Arial', 'sans-serif'],
      },
      borderRadius: {
        'qatar': '14px',
      },
      boxShadow: {
        'qatar': '0 4px 16px rgba(0,0,0,.10)',
        'qatar-lg': '0 8px 32px rgba(0,0,0,.12)',
      },
    },
  },
  plugins: [],
}
