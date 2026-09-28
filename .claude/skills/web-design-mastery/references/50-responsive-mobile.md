# التجاوبُ والجوال واللوحيّ

متى تقرأ هذا الملف: حين تعدّل تخطيطاً قد يتغيّر بعرض النافذة أو ارتفاعها، أو تبني شيئاً يُلمس، أو يُشتكى من تمريرٍ أفقيٍّ أو زرٍّ مقصوصٍ أو عنصرٍ تحت شريط الجوال.

المصادر: ذاكرة `feedback_all_devices_responsive.md` (أمرُ المالك 2026-09-22)، `docs/governance/regression_guards.md` (حرّاسُ الجوال M/Q/H)، `docs/mobile_remediation_plan_2026-09.md`، `static/css/custom/*.css`، ADR-0005 وADR-0006.

## أربعةُ أجهزةٍ لا اثنان
كلُّ تعديلٍ بصريٍّ يُقاس فعلاً على: سطح المكتب **1366×768 و1920×1080**، ولوحيّ **~768×1024 أو 820×1180**، وجوّال **375×812** — نهاراً وليلاً. وما لم يُقَس يُقال صراحةً «لم يُقَس». اللوحيُّ (641–1024) فجوةٌ موثَّقةٌ تاريخيّاً.

## نقاطُ القطع كما تكتبها المنصّة
| الاستعلام | العدد اليوم | المعنى |
|---|---|---|
| `@media (max-width: 640px)` | 26 | الجوال |
| `@media (min-width: 641px)` | 10 | ما فوق الجوال |
| `@media (max-width: 1024px)` / `(min-width: 1025px)` | 7 / 9 | اللوحيّ / الحاسوب |
| `(pointer: coarse)` و`(hover:hover) and (pointer:fine)` | — | اللمسُ مقابل الفأرة (أهدافُ اللمس، فتحُ القوائم بالمرور) |
- المنصّةُ ليست «mobile-first بـ`min-width` فقط»: اتبع اتّجاهَ الملفّ الذي تعمل فيه، وضع `@media` **بعد** قاعدتها الأساسيّة.
- **لا `@container`** (ADR-0005 D3؛ ADR-0006 قاس 656 تصييراً فلم يجد مكوّناً يحتاجه) — `.auto-grid` وأمثالُها تكفي.
- لا `@media` بارتفاع النافذة لصفحة: «بلا تمرير» يقرّره `window.fitNoscroll` مركزيّاً.

## قواعدٌ محروسة
- `viewport`: `width=device-width, initial-scale=1.0, viewport-fit=cover` — لا `user-scalable` ولا `maximum-scale` (`tests/test_wcag22_mobile.py`).
- أهدافُ اللمس ≥ `var(--control-h)` على `pointer: coarse` (`tests/test_touch_target_token.py`)، و`touch-action: manipulation` على التحكّمات (`tests/test_touch_controls.py`).
- الحقول ≥ 16px على الجوال (وإلّا كبّر iOS الصفحة)، والنصُّ المقروء ≥ 12px (0.75rem) — `tests/mobile_audit.py` يقيسهما مع التجاوز الأفقيّ على 25 صفحةً من رحلات خمسة أدوار.
- كلُّ `100vh` يتبعه في القاعدة نفسِها `100dvh` (`tests/test_dynamic_viewport.py`)؛ ولا `vh` في السكربتات.
- الشريطُ السفليّ والحشوُ والتوست تقرأ `--dock-h` و`--dock-pad` و`--edge-inline` و`--safe-inline` لا أرقاماً (`tests/test_safe_area_tokens.py`).
- لا عرضَ ثابتٌ > 320px (`tests/test_reflow.py`)، ولا `inset-inline: auto` بقيمةٍ واحدة (يمحو الطرفين).
- حقلُ رقمٍ بـ`inputmode` (يشتقّه `{% field %}` من `step`؛ `tests/test_numeric_inputmode.py`).
- قائمةُ الهامبرغر تُغلق بالنقر خارجها وبكلّ انتقال (`window.closeMobMenu`؛ `tests/test_mobile_nav_menu.py`).

## الجداولُ على الشاشات الصغيرة
- سجلٌّ عريض: `table-wrap` بتمريرٍ أفقيٍّ يبدأ من اليمين، ورأسُ الجدول اللاصق لا يغطّي المركَّز (معالجُ `focusin` في `base.js`).
- أضيقُ عمودٍ لا يقلّ عن أطول كلمةٍ في عنوانه (حادثةُ `staff-register`، DBT-46).
- «الجدولُ بطاقاتٌ بـ`data-label`» ليس نمطاً في المنصّة (لا `attr(data-label)` في الأنماط، وقالبٌ واحدٌ يحمل السمة) — لا تُدخله دون قرار.

## RTL مع التجاوب
- خصائصُ منطقيّة دائماً (`margin-inline-start`، `inset-inline-end`، `text-align: start`)؛ `start` يمينُ المستند هنا.
- الهامبرغر وانزلاقُ اللوح من اليمين، وأسهمُ «التالي/رجوع» معكوسة؛ والأرقامُ والتواريخُ اللاتينيّة داخل عازلَي اتّجاه.

## خطُّ أساس الجوال
- `tests/mobile_audit_baseline.json` يرفض التحسّنَ غيرَ المسجَّل كما يرفض التراجع؛ وحاويةُ الجلسة بلا مكتبات Chromium/WebKit فلا يُعاد القياسُ محلّيّاً — الأرقامُ من سجلّ CI (`feedback_css_media_order_and_mobile_baseline.md`). وقراءةُ فشله في `schoolos-quality-guards`.

## أنماطٌ مضادّة
- إصلاحُ الحاسوب وحدَه أو الجوال وحدَه وإعلانُ «تمّ».
- `max-w-*` أو `.container` على صفحة (العرضُ الكامل قرارُ 2026-09-11).
- `44px` حرفيّاً بدل `var(--control-h)`، أو `height: 100vh` وحدَها.
- `@container` أو استعلامُ ارتفاعٍ لصفحةٍ بعينها.
