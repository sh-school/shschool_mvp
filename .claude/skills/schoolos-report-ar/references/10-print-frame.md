# الإطارُ المطبوع المركزيّ والخطّ والمقاس

متى تقرأ هذا الملف: حين تكتب قالبَ PDF أو تعدّله، أو حين يُشتكى من ترويسةٍ مزدوجة أو تذييلٍ بلا رؤيةٍ أو بسطرين أو خطٍّ صغير أو صفحةٍ مقصوصة.

المصادر: `docs/design/print_fit_spec.md` (v2.4، معتمَدةٌ بقرارات D1–D3)، `core/print_frame.py`، `core/templatetags/print_frame.py`، `templates/components/print/`، `tests/print_frame_ratchet.py`، ذاكرة `reference_pdf_font_standards_2026_09_26.md`.

## الوسوم الثلاثة
```django
{% load brand_tags print_frame %}
<html lang="ar" dir="rtl" data-pdf-own-page>
<head>{% print_frame_css "a4" "portrait" %}<style>/* أصنافُ المحتوى فقط */</style></head>
<body>
{% print_frame_header "a4" "portrait" school title subtitle for_pdf=True %}
{% print_frame_footer "a4" "portrait" school %}   {# stats="…" اختياريّ #}
… المحتوى …
```
- الورق: `"a4"`/`"a3"` والاتّجاه `"portrait"`/`"landscape"` — غيرُهما `ValueError` صريح.
- **الوسمان قبل المحتوى**: العنصرُ الجاري يسري من صفحة وروده (`tests/test_form_pdf_page_footer.py`).
- `for_pdf=True` في PDF (الشعارُ بمسارٍ نسبيٍّ يحلّه WeasyPrint من الجذر، والعاملُ بلا manifest)؛ وبدونه على الشاشة.
- `data-pdf-own-page` على `<html>`: وإلّا حقن `core/pdf_utils.py::_inject_wp_page_header_css` إطارَه القديم. **مقيسٌ 2026-09-28 بـWeasyPrint:** قالبٌ يبدأ بـ`print_frame_css` بلا العلامة خرج بترويسة «SchoolOS» وتذييل «SchoolOS v6» بدل الإطار المركزيّ؛ و`behavior/pdf/base_form.html` (بلا العلامة، وأنماطُه قبل الإطار) خرج بالإطار المركزيّ **وزيادة** «SchoolOS v6» والتاريخ في زاويتَي التذييل.

## ما يرسمه الإطار
| الجزء | المحتوى | المصدر |
|---|---|---|
| الترويسة | الشعار (`static/brand/logoMaroon.png`) ← «وزارة التربية والتعليم والتعليم العالي — دولة قطر» 9pt ← اسمُ المدرسة 14pt ← العنوان 12pt ← سطرٌ فرعيّ 9pt | `frame_header.html`، `MINISTRY` |
| التذييل | صفٌّ واحدٌ ثابتُ الارتفاع: المدرسة · ص/ص · تاريخُ الطباعة ووقتُها (ملزِمة) ثمّ `stats` والرؤيةُ والوزارةُ والاتّصال بقدر ما يسع | `footer_plan` في `core/print_frame.py` |
| الخطّ | `FOOTER_PT = 10`، يتصاغر حتى `FOOTER_MIN_PT = 9` | `core/print_frame.py` |
| الهوامش | علويٌّ وسفليٌّ 6مم حول الإطار، جانبيٌّ 9مم، فاصلٌ 2مم | `MARGIN_*_MM`، `GAP_MM` |

الرؤيةُ نصُّها من `components/ministry_vision.html` (مصدرٌ واحدٌ يقرأ `school.vision` أو الافتراض)، ولا تُكتب حرفيّاً في أيّ ملفّ.

## تباينُ المواصفة والشيفرة اليوم (اعرفه ولا «تصلحه» في طلبٍ غير مخصّص)
- المواصفة v2.4 (D1 النهائيّ): الرؤيةُ في **التذييل** دائماً سطراً واحداً، والترويسةُ ≈30مم لكلّ المقاسات.
- `core/print_frame.py` على `main`: `HEADER_H_MM` 35مم للعموديّ و`VISION_IN_HEADER` يضع الرؤيةَ سطراً في **ترويسة** A4/A3 العموديّ — أثرُ v2.3.
- الأثرُ: قالبٌ عموديٌّ اليومَ تظهر رؤيتُه في الترويسة. التوفيقُ قرارٌ لمسار «الواجهة والهويّة»؛ أبلغ ولا تعدّل الثوابتَ من طلب تقرير.

## حدودُ الخطّ (D2، المواصفة §٤-١)
| الصنف | مثاليّ | أدنى صارم |
|---|---|---|
| عنوانُ الوثيقة | 16pt | 14pt |
| متنُ النماذج والنصوصُ الحرّة (A4) | 11pt (الاستمارة 12/11) | 10pt |
| قوائمُ وجداولُ متعدّدةُ الصفحات | 10pt | 10pt |
| عناوينُ الأعمدة والمفاتيح | جسمُها − 0.5 | 9pt |
| التذييل | 10pt | 9pt |
| الجدولُ العامّ (ت1، A3 أفقيّ) | — | 7.9pt — استثناءٌ بقرار المالك لهذا الجدول وحدَه |

- ما لا يسع: A3، أو صفحاتٌ أكثر بترويسةٍ متكرّرة، أو «تتمّة» موسومة (D3) — **لا خطٌّ أصغر ولا قصّ**.
- الأحجامُ في PDF بـ`pt` و`mm`؛ الـ`px` في قالبٍ مطبوعٍ قديمٌ يُترجم إلى نقاطٍ صغيرة (خطُّ الأساس المقيس 5.2–7.5pt في 20 وثيقة).
- المرجعُ الخارجيّ الذي تنازل عنه المالكُ عن وعي: RNIB ≥ 12pt؛ ووسيطُ وثائق الوزارة المقيس 14pt.

## الخطوط
- المتاح في `static/fonts/`: Tajawal (400/500/700 وعائلةُ `Tajawal Tashkeel` للمشكول)، Amiri، Noto Naskh Arabic؛ وTraditional Arabic يُحمَّل من `StoredFile` بأمر `install_pdf_font` لأنّه مملوكٌ لا يُودَع في المستودع العامّ.
- `_inject_fonts` يحقن `@font-face` بمساراتٍ مطلقة؛ ويتخطّى الحقنَ إن وجد في القالب `@font-face` مع tajawal/amiri — فلا تكتب واحداً.
- xhtml2pdf (الاحتياطيّ) يستعمل Amiri مع إعادة تشكيل العربيّة؛ لا يعرف العناصرَ الجارية فلا إطارَ فيه.

## الجدولُ في المطبوع
- `thead { display: table-header-group; }` لتكرار الرأس، و`tbody tr { break-inside: avoid; }`.
- الأرقامُ وسطاً بـ`font-variant-numeric: tabular-nums`؛ النصُّ `text-align: start`.
- التاريخُ داخل سطرٍ عربيٍّ بين عازلَي اتّجاه (U+2066…U+2069) — مولّدُ PDF لا يقرأ `unicode-bidi` (كما يفعل التذييل).

## أنماطٌ مضادّة
- `position: running(...)` أو `@page { @bottom-… }` أو صنفٌ `*-footer` في قالبٍ جديد (السقّاطةُ تسقط؛ الملفُّ الجديدُ رقمُه صفر).
- إضافةُ «SchoolOS» أو «SchoolOS-SAMM ©» إلى التذييل — أُخرج بأمر المالك 2026-09-27.
- رؤيةٌ بسطرين (`\A` أو `white-space: pre-line`).
- `@font-face` بـ`{% static %}`، أو خطُّ Cairo/Noto Sans Arabic غيرُ الموجود.
- `line-clamp` أو `max-height` أو `truncatechars` على نصٍّ حرٍّ مطبوع.
