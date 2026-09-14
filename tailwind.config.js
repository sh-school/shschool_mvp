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
    /* ══ لوحةُ الألوان هي رموزُ المنصّة وحدَها ══
       `colors` هنا لا `extend.colors`: فتُحذف لوحةُ Tailwind الافتراضيّة كلُّها
       (`bg-red-50`، `text-gray-500`…) ولا يبقى صنفُ لونٍ إلّا نافذةً على رمزٍ في
       `:root` بـ`static/css/custom.css`. كانت اللوحةُ متاحةً فكُتب منها 1351 صنفاً
       في القوالب حتى 2026-09-13 — وبعد الصفر لا يُعاد فتحُها.
       لا قيمةَ لونٍ مكتوبةً هنا، ولا اسمَ بلا رمزٍ يقابله — الصنفُ حينئذٍ يُبطل
       التصريحَ صامتاً. */
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      inherit: 'inherit',
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
    extend: {
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
