/** @type {import('tailwindcss').Config} */
module.exports = {
  /* Dark Mode: synced with Alpine data-theme attribute */
  darkMode: ['class', '[data-theme="dark"]'],
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        /* Qatar Brand — linked to CSS vars */
        adaam: {
          DEFAULT: '#8A1538',
          light: '#A01B42',
          dark: '#6B1029',
          bg: '#fdf2f5',
          border: '#e8b4c3',
        },
        brand: {
          50:  '#fdf2f5',
          100: '#fce7ee',
          200: '#e8b4c3',
          300: '#d48a9f',
          400: '#b8294e',
          500: '#A01B42',
          600: '#8A1538',
          700: '#8A1538',   /* ← Al Adaam — اللون الرئيسي */
          800: '#6B1029',
          900: '#4a0b1c',
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

        /* Semantic — linked to CSS vars */
        surface: {
          page:    'var(--page-bg)',
          base:    'var(--surface)',
          alt:     'var(--surface-alt)',
        },
        txt: {
          primary:   'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted:     'var(--text-muted)',
        },
      },
      fontFamily: {
        tajawal: ['Tajawal', 'Arial', 'sans-serif'],
      },
      borderRadius: {
        'qatar': '14px',
        'sm': 'var(--radius-sm)',
        'md': 'var(--radius-md)',
        'lg': 'var(--radius-lg)',
        'xl': 'var(--radius-xl)',
      },
      boxShadow: {
        'qatar': '0 4px 16px rgba(0,0,0,.10)',
        'qatar-lg': '0 8px 32px rgba(0,0,0,.12)',
      },
      zIndex: {
        'navbar':   'var(--z-navbar)',
        'modal':    'var(--z-modal)',
        'toast':    'var(--z-toast)',
        'dropdown': 'var(--z-dropdown)',
      },
    },
  },
  plugins: [],
}
