# هندسةُ CSS في المنصّة — الملفّات والطبقات والحرّاس والميزانيّات

متى تقرأ هذا الملف: قبل أن تكتب سطرَ CSS، أو تضيف ملفّاً، أو تنقل قاعدة، أو حين تقترب من سقف الحجم.

المصادر: `CLAUDE.md` (قسم «أنماطُ المنصّة — ثمانيةُ ملفّات»)، `docs/adr/0003-split-custom-css-by-layer.md`، `core/css_files.py`، `docs/governance/regression_guards.md`، `tests/web_vitals.py`، `tests/test_css_budget.py`.

## الملفّات والطبقات
```
@layer tailwind, reset, base, tokens, layout, components, modules, utilities, themes;   ← في 10-foundation.css وحدَه
```
| الملفّ | الطبقة | ما يُكتب فيه |
|---|---|---|
| `10-foundation.css` | tailwind(مجمَّدة)، reset، base، tokens، layout | جملةُ الترتيب، `:root`، الخطوط، التخطيطُ العامّ |
| `20-components.css` | components | مكوّناتٌ عامّة (بطاقات، شارات، أزرار، جداول، حركةُ `page-in`/`is-leaving`) |
| `30..33-modules-N.css` | modules | شاشاتٌ ووحدات؛ الجديدُ في `33` ما لم يكن لقسمك موضعٌ قائم؛ الترتيبُ 30→33 يحسم عند تساوي النوعيّة |
| `40-themes.css` | themes | كلُّ `html.dark` (آخرُ طبقة فتغلب) |
| `50-utilities.css` | utilities | أصنافٌ مساعدة (`page-noscroll`، `is-fit`…) |

- التحميلُ بوسم `{% custom_css %}` (`core/templatetags/assets.py`) من `core/css_files.py:CSS_FILES`؛ ملفٌّ جديدٌ = سطرٌ هناك وإلّا سقط `tests/test_css_split.py` — **وقرارٌ**: كلُّ ورقةٍ حاجبةٍ طلبٌ جديد والسقفُ 10.
- استثناءان مبرَّران خارج الثمانية: `admin_theme.css` (لوحة `/admin/`، تنسخ الرموزَ ويحرسها `test_admin_theme`) و`styleguide.css` (صفحاتُ الدليل وحدَها، لا صنفَ `sg-` في ملفّات المنصّة).
- الحرّاسُ تقرأ المصدرَ بـ`tests/css_source.read_css()`؛ لا تكتب مسار `css/custom.css` في اختبار.

## قواعدٌ ثابتة (حارسُها بين قوسين)
- لا قاعدةَ خارج `@layer` — غيرُ المطبَّق يغلب المطبَّقَ مهما علا وزنُه (`test_css_layers`).
- لا محدِّدَ ناقص ولا `url()` نسبيٌّ مكسور (`test_css_selectors`، `test_css_layers`).
- لا لونَ حرفيّ (`test_css_colours_are_tokens`)، ولا `left:`/`right:` (`test_rtl_logical_properties`)، ولا px على السلّم (`test_px_tokens`)، ولا `font-size` بـpx.
- لا نظيرَ ليليٌّ ميّت (`test_css_dead_overrides`، سقفُه 11)، ولا تعليقٌ زخرفيّ (خطوطُ `═══`) يثقل الحجم (`test_css_comment_decoration`).
- لا صنفَ Tailwind جديد في `@layer tailwind` ولا `tailwind.min.css` (`test_tailwind_freeze`، 130 اسماً مجمَّداً).
- لا `style="…"` في القوالب ولا لوحةَ Tailwind (`bg-red-50`) ولا سداسيّ ولا بنيةٌ باليد (`card-qatar`، `card-header`، `exec-header`، `card-bar`، `kpi-mini`) — سقّاطةُ الهويّة `tests/design_ratchet.py` على صفر.
- صنفٌ يُستعمل في قالبٍ يُعرَّف في CSS أو في `<style>` القالب نفسِه (الحارسُ نفسُه)؛ ولا صنفٌ معرَّفٌ في ملفّين (مبدأ المركزيّة، `feedback_centralization_principle.md`).
- لا لونٌ سداسيٌّ ولا `style=` في سلاسل بايثون؛ اللونُ من `core/brand.py` (`test_no_styles_in_python`).
- `<style>` في قالب ويب: استثناءٌ بسبب (مثلُ أرضيّة الصفحة المبكّرة في `base/base.html`)، والأصلُ ملفُّ الطبقة. قوالبُ PDF خارج هذا — لها `<style>` وإطارٌ مطبوع (`schoolos-report-ar`).
- لا `!important` جديد (17 موضعاً اليوم في الثمانية؛ لا حارسَ يعدّها — الضابطُ المراجعة)، ولا `#id` في المحدِّدات إلّا لعنصرٍ فريدٍ في الغلاف (`#main-content`، `#crumbs`).

## ترتيبُ القواعد
- `@media` تُكتب **بعد** القاعدة الأساسيّة التي تعدّلها: بالنوعيّة نفسها يغلب الأخيرُ في الملفّ (حادثةُ فوتر المنصّة، `feedback_css_media_order_and_mobile_baseline.md`).
- داخل `modules` يحسم الترتيبُ 30→33؛ ولا تعتمد على ترتيبٍ بين الطبقات (جملةُ الترتيب تحسم).

## الميزانيّات (من ملفّاتها الحيّة 2026-09-28)
| السقف | القيمة | الملفّ |
|---|---|---|
| CSS مصغَّرٌ يصل المتصفّح | ≤ 269KB | `tests/test_css_budget.py:MAX_SHIPPED_BYTES` |
| CSS خامّ (بالتعليقات) | ≤ 470KB | `tests/web_vitals.py:BUDGET["css_kb"]` |
| JS · خطوط · صور · طلبات | 400KB · 120KB · 220KB · 40 | `BUDGET` |
| أوراقٌ حاجبة | ≤ 10 | `BUDGET["blocking_stylesheets"]` |
| LCP · INP · CLS | 2500ms · 300ms · 0.1 | `BUDGET` |
| px خارج السلّم | تباعد ≤ 78، تقوّس ≤ 31 | `tests/test_px_tokens.py` |

- التعليقُ العربيّ بايتان للحرف ويُحسب في الخامّ — اكتب التعليلَ بإيجاز (التصغيرُ وقتَ `collectstatic` بـ`rcssmin` يحذفه من المنتَج لا من الخامّ).
- قرارُ المالك VD8: لا رفعَ لسقف الخامّ ثانيةً؛ تجاوزُه يُعالَج بالتقليص.
- `CLAUDE.md` يذكر 460KB للخامّ و`regression_guards.md` يذكر 260KB للمصغَّر — الملفّاتُ الحيّةُ أعلاه أحدث.

## بعد التعديل
- حدِّث الصفحة وحسب: WhiteNoise يخدم `static/` بـ`max-age=0` في التطوير (`USE_FINDERS`)، والإنتاجُ يبصم الاسمَ بمحتواه (`CompressedManifestStaticFilesStorage` + تصغيرٌ في `core/static_storage.py`). لا `?v=N` ولا `collectstatic`.

## أنماطٌ مضادّة
- ملفٌّ CSS جديدٌ «لقسمي» دون قرار، أو `<link>` إضافيٌّ في قالب.
- `@container` (ADR-0005 D3/ADR-0006) أو `@import` داخل CSS.
- إسكاتُ حارسٍ بنقل القاعدة خارج نطاق فحصه، أو `--update` لخطّ أساسٍ ارتفع بلا سبب.
- رفعُ سقف ميزانيّةٍ في الطلب نفسِه الذي تجاوزه.
