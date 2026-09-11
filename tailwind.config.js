/** @type {import('tailwindcss').Config} */
module.exports = {
  /* Dark Mode: الصنف `dark` على <html> — يضعه سكربتُ base.html و base.js.
     لا تستبدله بـ [data-theme] ما لم يضعه أحدٌ فعلاً، وإلّا ماتت أصنافُ dark:* كلُّها. */
  darkMode: 'class',
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      /* ══ لا قيمةَ لونٍ مكتوبةً هنا ══
         مصدرُ الحقيقةِ الوحيدُ هو `:root` في `static/css/custom.css`.
         كلُّ اسمٍ أدناه نافذةٌ على رمزٍ هناك، فلا يتباعد الملفّان.
         ولا تُضِف اسماً بلا رمزٍ يقابله — الصنفُ حينئذٍ يُبطل التصريحَ صامتاً. */
      colors: {
        adaam: {
          DEFAULT: 'var(--maroon)',
          light:   'var(--maroon-light)',
          dark:    'var(--maroon-dark)',
          bg:      'var(--maroon-bg)',
          border:  'var(--maroon-border)',
        },
        gold:    'var(--gold)',
        skyline: 'var(--skyline)',
        palm:    'var(--palm)',
        sea:     'var(--sea)',

        surface: {
          page: 'var(--page-bg)',
          base: 'var(--surface)',
          alt:  'var(--surface-alt)',
        },
        txt: {
          primary:   'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted:     'var(--text-muted)',
        },
      },
      borderRadius: {
        'sm': 'var(--radius-sm)',
        'md': 'var(--radius-md)',
        'lg': 'var(--radius-lg)',
        'xl': 'var(--radius-xl)',
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
