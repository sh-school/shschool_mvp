# أ. سقّاطاتُ العدّ

> الحرّاسُ من نوع السقّاطة — مقطعٌ من `docs/governance/regression_guards.md` (الفهرس)؛ النصُّ منقولٌ حرفيّاً (W-20261020-018).

### أ. سقّاطاتُ العدّ (ثمان)

| السقّاطة | ما تعدّه | الملفّ | خطُّ الأساس اليوم | أين تعمل | تسجيلُ التحسّن |
|---|---|---|---|---|---|
| **الهويّة البصريّة** | في القوالب: `inline_style`، `palette_class`، `hex_colour`، `legacy_header`، `hand_kpi` + أصنافٌ مستعملةٌ بلا تعريفٍ في CSS؛ وسبعةُ مقاييس تسجّل الحالَ (W-20261009-009) | `tests/design_ratchet.py` ← `design_ratchet_baseline.json` | **0** في الخمسة الأولى، و0 صنفٍ بلا تعريف؛ والسبعةُ مقيسةٌ على main (انظر الفقرة بعد الجدول) | `pytest — تغطية` (`test_design_ratchet.py`) | `python -m tests.design_ratchet --update` |
| **الوصوليّة (مصدرُ القالب)** | `unnamed_field`، `label_without_for`، `page_without_h1`، `table_without_wrap`، `partial_without_empty_state` | `tests/a11y_ratchet.py` ← `a11y_ratchet_baseline.json` | **0** في الخمسة | `pytest — تغطية` (`test_a11y_ratchet.py`) | `python -m tests.a11y_ratchet --update` |
| **axe-core الحيّ** | عُقَدُ المخالفة لكلّ صفحةٍ وكلّ قاعدة WCAG 2.0/2.1 (أ وAA) في Chromium بعد تسجيل الدخول | `tests/a11y_axe_ratchet.py` ← `a11y_axe_ratchet_baseline.json` | **0** (VI-25: `aria-pressed` على رابط «غير المقروء فقط» في `notification_inbox` صار `aria-current`؛ كانت 2 ثمّ 1، والخطُّ الأساس الآن `{}` فلا استثناءَ مسجَّلاً)؛ ويحرس `test_no_aria_pressed_on_links` كلَّ القوالب بلا متصفّح | وظيفةُ `axe-a11y` | `AXE_UPDATE=1 pytest tests/test_a11y_axe_ratchet.py::test_axe_violations_have_not_grown` |
| **الجوال (M-00)** | لكلّ صفحةٍ من رحلات خمسة أدوار (25 صفحة): أهدافُ لمسٍ دون 44px ودون 24px، نصٌّ مقروءٌ دون 12px، تجاوزٌ أفقيّ، حقولٌ دون 16px — جوالاً 375×812 (`is_mobile`) بـChromium وWebKit، وسطحَ مكتبٍ 1440 بـChromium (النصُّ والتجاوزُ وحدُّ الفأرة 24px — DBT-44)؛ وخانةُ الاختيار وزرُّه هدفُهما اتّحادُ الصندوق والتسمية المرتبطة (DBT-45) | `tests/mobile_audit.py` ← `mobile_audit_baseline.json` | جوالاً (Chromium): K1 **0%** (0/431) دون 44px، K2 0%، 0 صفحةٍ بخطٍّ ≤10px، 0 تجاوز، 0 حقل (WebKit: 0/434)؛ سطحُ المكتب: 25 صفحةً، K2 0%؛ الأرقامُ لكلّ مِلفّ في خطّة الجوال §2 | وظيفةُ `axe-a11y` | `MOBILE_AUDIT_UPDATE=1 pytest tests/test_mobile_audit.py -s` |
| **الأنواع** | أخطاءُ mypy لكلّ ملف | `tests/mypy_ratchet.py` ← `mypy_ratchet_baseline.json` | **1,324** خطأً في 122 ملفاً — بعد استثناء `management/commands` من النطاق (2026-09-26، DBT-01: تغييرُ نطاقٍ لا إصلاح؛ 1,730 ← 1,324، منها 67 خطأً في ثلاث وحداتٍ لا يبلغها mypy إلّا من الأوامر) | وظيفةُ `mypy` (`python -m tests.mypy_ratchet`) | `python -m tests.mypy_ratchet --update` |
| **الطبقات** | دالّةُ العرض ≤ 60 سطراً و≤ 5 استدعاءاتِ ORM؛ `core` لا يستورد وحدةً نازلة؛ `get_school()` في ملفّات العروض | `tests/layering_ratchet.py` ← `layering_baseline.json` (ADR-0004) | `views` 207، `get_school` 176 موضعاً في 29 ملفّاً، `core_imports` 12 ملفّاً (34 استيراداً)، `accepted` 7 (`python -m tests.layering_ratchet` يطبع المجاميع) | `pytest — تغطية` (`test_layering.py`) | `--update` · `--accept "<موضع>" --reason "<سبب>"` · `--rebaseline` (على المضيف: `git` ليس في الحاوية) |
| **حجمُ ملفّات الشيفرة** | أسطرُ كلّ `.py` (عدا الهجرات والاختبارات) فوق **1000** سطر: الملفُّ الجديدُ لا يتجاوز، والمسجَّلُ لا يكبر أكثرَ من هامش **25** سطراً — سطرٌ أو سطران في ملفٍّ كبير لا يُسقط جلساتٍ متوازية (استثناءٌ مقصودٌ من «النقص يسقط أيضاً»: النقصُ يسقط عند تجاوز الهامش أو النزول تحت الحدّ) | `tests/file_size_ratchet.py` ← `file_size_baseline.json` | ملفّاتٌ مسجَّلةٌ بتجاوزها (`file_size_baseline.json`)، أكبرُها `student_affairs/views.py` | `pytest — تغطية` (`test_file_size.py`) | `python -m tests.file_size_ratchet --update` · وعند التجاوز: حزمةٌ حسب المسؤوليّة (النموذج `staff_affairs/attendance/`، #447) |
| **أنماطُ التخطيط (LAY-03)** | صفحاتٌ لم تعلن نمطَ تخطيطها بـ`{% block main_class %}{% page_layout "…" %}{% endblock %}` (الأنماطُ السبعة، قرار D-16، `docs/design/page_layouts.md`): صفحةٌ جديدةٌ بلا نمطٍ تسقط، ومن أعلن نمطَه يُحذف من الخطّ الأساس | `tests/page_layout_ratchet.py` ← `page_layout_baseline.json` | 138 صفحةً سبقت الحارس (LK1 = 12.7% عند دمجه) | `pytest — تغطية` (`test_page_layouts.py`) | `python -m tests.page_layout_ratchet --update` |

> **مقاييسُ الهويّة السبعة (W-20261009-009، مقيسةٌ على رأس main يوم 2026-10-10):** كلٌّ منها يعدّ لكلّ قالبٍ أو ملفّ، وزيادتُه ونقصُه كلاهما يُسقط `test_design_ratchet` حتى يُسجَّل العدد بـ`python -m tests.design_ratchet --update`، وقالبٌ جديدٌ يبدأ بصفر. تسجّل الحالَ ولا تُصلح القديم.
> - `style_block`: كتلُ `<style>` داخل القوالب (26 في 17 قالباً)؛ لأنّ الأنماطَ مكانُها `static/css/custom/` بطبقاتها.
> - `max_w`: أصنافُ `max-w-*` من Tailwind في القوالب (7 في 7)؛ العرضُ من أنماط التخطيط لا من أصنافٍ موضعيّة.
> - `button_no_type`: `<button>` بلا `type=` (85 في 21)؛ يُرسل النموذجَ افتراضاً.
> - `inline_script`: `<script>` بلا `src=` (84 في 73)؛ كتلُ `application/json` و`ld+json` بياناتٌ فلا تُعدّ.
> - `important`: `!important` في `static/css/custom/` (6 في 4 ملفّات) بعد استثناء كتل `@media print` و`prefers-reduced-motion` (11 تصريحاً) لأنّ الطباعةَ وتفضيلَ تقليل الحركة يلزمهما التغليب؛ وطبقة utilities لا تُستثنى.
> - `transition_all`: `transition: all` و`transition-property: all` (9 في 3)؛ يحرّك التخطيطَ نفسه لا اللونَ وحده.
> - `physical_side`: خصائصُ فيزيائيّةٌ (`margin/padding/border-left|right` و`left:`/`right:` و`text-align|float|clear: left|right` وأنصافُ أقطار الزوايا) (30 في 4 ملفّات)؛ تكسر RTL — البديلُ `inline-start/end`.
>
> **نشأتُها:** الهويّةُ البصريّة 2026-09-13 (`c201de9f`)، الوصوليّةُ والأنواع 2026-09-14 (`35ff73d5`)، الطبقات 2026-09-18 (`9edd0097`)، axe 2026-09-18 (#379)، الجوال 2026-09-23 (M-00).
>
> **لماذا سقّاطةُ axe لا تبدأ من صفر:** القياسُ الأوّل (P0-1، 2026-09-18) وجد مخالفاتٍ موجودةً فعلاً
> على الإنتاج، وإصلاحُها بندٌ منفصل. فالحارسُ يمنع أن تزيد لا أن يُصلحها.
