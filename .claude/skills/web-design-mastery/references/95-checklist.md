# قائمةُ مراجعة الواجهة قبل الدفع

متى تقرأ هذا الملف: قبل أن تعلن تعديلاً في قالبٍ أو CSS أو JS «جاهزاً للمعاينة». كلُّ بندٍ يحيل إلى مرجعه؛ والقائمةُ القديمة (145 سطراً من 14 كتاباً) أُعيدت كتابتُها بقيم المنصّة.

## الصفحة
- [ ] أعلنت نمطها: `{% page_layout "…" %}` (`20-layouts-components.md`).
- [ ] لها `h1` واحدٌ عبر `page_header`، ولا `max-w-*` ولا `.container`.
- [ ] البطاقاتُ بقدر محتواها (`is-fit` للمحدود)، والقائمةُ الضيّقةُ الطويلةُ أعمدة (`chunk_for_grid`).
- [ ] الحالةُ الفارغة `empty_state`، والتنبيهُ `callout` بنوعه الصحيح (و`show=True` لما لا يُخبَّأ).

## الأنماط
- [ ] كلُّ قاعدةٍ في ملفّ طبقتها وداخل `@layer`، و`html.dark` في `40-themes.css` وحدَه (`10-css-architecture.md`).
- [ ] لا لونَ حرفيّ؛ النصُّ `--text-*`/`--status-*-fg`، وفوق الحشو `--on-fill` (`00-tokens-theming.md`).
- [ ] التباعدُ `var(--sp-*)`، والتقوّسُ `var(--radius-*)`، والخطُّ `rem`/`--text-*`.
- [ ] خصائصُ منطقيّةٌ لا `left`/`right`.
- [ ] `@media` بعد قاعدتها الأساسيّة، ولا `@container`، ولا صنفُ Tailwind جديد.
- [ ] لا `style="…"` ولا صنفٌ مستعمَلٌ بلا تعريف ولا صنفٌ معرَّفٌ في ملفّين.
- [ ] لا `!important` جديد، ولا تعليقٌ زخرفيّ، والتعليقُ العربيّ موجز (يُحسب في الخامّ).

## السلوك
- [ ] لا `onclick`/`onchange`؛ `data-*` من `actions.js`، و`data-call` في `CALLABLE` (`30-htmx-js.md`).
- [ ] كلُّ `<script>` داخليٍّ بـ`nonce`، وسكربتُ الصفحة داخل IIFE.
- [ ] HTMX: الـview تختار الجزئيّة (`htmx_or_full`)، والإشعارُ `htmx_toast`، والمسارُ `{% url %}`.
- [ ] لا `window.print()` في صفحةٍ تفاعليّة؛ التصديرُ بـ`data-app-file`.

## الوصوليّة (`40-accessibility.md`)
- [ ] كلُّ حقلٍ عبر `{% field %}` أو بـ`<label for>` واسمٍ عربيّ.
- [ ] زرُّ الأيقونة الوحيدة له `label`، والرابطُ الحاليّ `aria-current`.
- [ ] الجدولُ في `table-wrap` برؤوسٍ `scope`.
- [ ] التركيزُ ظاهر، والمعنى ليس في اللون وحده.

## الأجهزة (`50-responsive-mobile.md`)
- [ ] قيس فعلاً: 1366×768، 1920×1080، لوحيّ ~768×1024، جوّال 375×812 — نهاراً وليلاً؛ وما لم يُقَس مذكور.
- [ ] لا تمريرَ أفقيّ، والأهدافُ ≥ `--control-h` على اللمس، و`100vh` معها `100dvh`.
- [ ] الوضعُ الليليّ: لا خلفيّةَ فاتحة، ورأسُ الجدول نصُّه أبيض.

## الأداء (`70-performance.md`)
- [ ] `<img>` بـ`width` و`height`، ولا `<link>` أنماطٍ جديد، ولا مكتبةَ CDN خارج ما يقبله CSP.
- [ ] لا `?v=N` ولا `collectstatic`؛ وعاملُ الخدمة برقمٍ جديدٍ إن تغيّر منطقُه.
- [ ] `{% static %}` يشير إلى ملفٍّ موجود.

## الحرّاسُ قبل الدفع
شغّل من شجرة عملك (أمرُ الاختبار في `CLAUDE.md`):
`tests/test_css_split.py tests/test_css_layers.py tests/test_css_colours_are_tokens.py tests/test_px_tokens.py tests/test_rtl_logical_properties.py tests/test_dark_parity.py tests/test_contrast_ratios.py tests/test_design_ratchet.py tests/test_a11y_ratchet.py tests/test_page_layouts.py tests/test_css_budget.py`
— وقراءةُ الفاشل وتسجيلُ خطّ أساسٍ تحسّن: مهارة `schoolos-quality-guards`. ثمّ المعاينةُ والدفعُ بخطوات `schoolos-flow`.

## أنماطٌ مضادّة
- إعلانُ «جاهز» بقياسٍ على مقاسٍ واحد.
- تشغيلُ الحرّاس بعد الدفع لا قبله.
