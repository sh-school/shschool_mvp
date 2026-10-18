---
paths:
  - "static/**"
  - "templates/**"
  - "core/css_files.py"
  - "tests/css_source.py"
  - "tests/test_css_split.py"
  - "tests/test_px_tokens.py"
  - "tests/test_web_vitals_budget.py"
---

# قواعدُ الواجهة والهويّة البصريّة — النواة

> تُحمَّل حين تقرأ أو تكتب ملفّاً في `static/` أو `templates/` أو ملفّاتِ حرّاس الأنماط. اختُصرت (W-20261014-025، قرار المالك 2026-10-14) إلى الأحكام الملزمة وفهرس الحرّاس؛ **الأسبابُ والتفاصيلُ والأمثلة بنصّها في `docs/design/design_system_appendix.md`** (اقرأه عند الحاجة). وكلُّ ذكرٍ لـ«`custom.css`» يعني ملفّاتِ `static/css/custom/`. والخريطةُ الكاملة للحرّاس: `docs/governance/regression_guards.md`؛ وقواعدُ الجداول: `.claude/rules/tables.md`.

## الأحكامُ الملزمة وحارسُ كلٍّ منها

| الحكم | الحارس |
|---|---|
| **كلُّ شيءٍ داخل المنصّة:** لا `target="_blank"` ولا `window.open(` ولا `href="http(s)://…"` في القوالب وجافاسكربت المنصّة؛ التصديرُ من مركز التصدير (`data-app-file`) | `tests/test_no_external_pages.py` (خطٌّ أساسيّ لا يزيد) |
| **الأنماط في `static/css/custom/` بثمانية ملفّاتٍ:** `10-foundation` ثمّ `20-components` ثمّ `30..33-modules` ثمّ `40-themes` ثمّ `50-utilities`؛ ملفٌّ جديد = سطرٌ في `core/css_files.py:CSS_FILES`؛ لا قاعدةَ خارج `@layer`؛ جملةُ الطبقات في `10-foundation` وحدَها | `tests/test_css_split.py`، و`tests/css_source.read_css()` |
| **التباعدُ والتقوّس بالرموز:** `margin/padding/gap` بـ`var(--sp-*)`، و`border-radius` بـ`var(--radius-*)`، و`font-size` بـ`rem` لا px؛ ولا px جديدةً خارج السلّم | `tests/test_px_tokens.py` (سقّاطة) |
| **الألوانُ رموزٌ لا قيمٌ حرفيّة؛ لا صنفَ بلا تعريف؛ لا طبقاتٍ مكسورة** | `tests/test_css_colours_are_tokens.py`، `tests/test_css_selectors.py`، `tests/test_css_layers.py` |
| **ميزانيّةُ الأداء:** CLS ≤ 0.1، LCP ≤ 2500ms، INP ≤ 300ms؛ CSS ≤ 460KB وJS ≤ 400KB؛ ≤ 10 أوراق أنماط | `tests/test_web_vitals_budget.py` (وظيفةُ `axe-a11y`) |
| **حجمُ الملفّات:** لا `.py` جديدٌ فوق 1000 سطر، ولا مسجَّلٌ يكبر أكثر من 25 سطراً؛ قسِّم حسب المسؤوليّة | `tests/test_file_size.py` |
| **التنبيهاتُ وسمٌ واحد** `{% callout "<نوع>" %}` (hint/info/warning/error/success): أيقونةٌ في شريط `section_card` أو بجانب `page_header` **لا سطراً داخل البطاقة**؛ `error` يبقى `role=alert`؛ الاستثناءُ الوحيد `ui-note` و`ui-field-hint`؛ الألوانُ رموزُ الحالة | صنفٌ بلا تعريف (`test_css_selectors`)؛ **بلا حارسٍ لموضع الأيقونة** |
| **تنقّلُ الصفحات:** الترويسةُ والقائمةُ والفوتر ثابتةٌ والمحتوى وحدَه يتلاشى؛ المدّةُ من `--transition-page` لا رقمٌ في JS؛ لا تحوِّل `/admin/` إلى تبديل DOM؛ سكربتُ الصفحة بغلاف IIFE | `tests/test_page_nav_shell.py`، `test_page_nav_callables.py`، `test_page_nav_htmx_process.py`، `test_admin_theme.py` |
| **القائمةُ الرئيسيّة بالمرور ولا شريطَ فرعيّ** (`section_nav` محذوف): فتحٌ بتأخّر 150ms وإغلاقٌ بـ300ms وEsc | **بلا حارس** |
| **سبعةُ أنماط تخطيط** `layout-dashboard/hub/list/detail/form/sheet/report` (المرجع `docs/design/page_layouts.md`)؛ لا شبكةً محلّيّة؛ لا حدَّ ارتفاعٍ بـ`@media` لصفحة؛ البطاقةُ بارتفاع محتواها (`is-fit`) ولا تمريرَ داخل بطاقةٍ محدودة | `tests/test_page_layouts.py`، `page_layout_ratchet.py`، `test_noscroll_floor.py` |
| **عرضُ النافذة كاملاً:** لا `max-w-*` ولا `.container` على صفحةٍ جديدة؛ قوائمُ غيرُ محدودةٍ بعمودٍ ضيّق تُقسَّم بـ`chunk_for_grid` في الـview وتُعرض في `.auto-grid` | `tests/test_tailwind_freeze.py` (للـ`max-w`)؛ **القسمةُ بلا حارس** |
| **كسرُ ذاكرة المتصفّح: لا تفعل شيئاً** — لا `?v=N` يدوياً؛ الإنتاجُ يبصم الأسماءَ (`CompressedManifestStaticFilesStorage`) والتطويرُ بـ`max-age=0` | **بلا حارس** |

## ما بلا حارسٍ فحكمُه عليك

البنودُ الأربعة المعلَّمة «بلا حارس» (موضعُ أيقونة التنبيه، القائمةُ بالمرور، قسمةُ الأعمدة، كسرُ الذاكرة) تُراجَع بالعين في المعاينة؛ وتحويلُها إلى حرّاس آليّة مقترحٌ في W-20261014-025 (تحذيرٌ أولاً ثمّ حاجز).

## ثوابتُ لا تُمسّ

الجدولُ المعتمد الحيّ على الإنتاج (D-381م)، ومجلّداتُ الأيقونات `static/icons/v2` و`static/icons/v3`، وقرارُ الشعارات (D-434م)، وتنازلُ المخالفات الموروثة بتوقيع 0501 وحدَها.
