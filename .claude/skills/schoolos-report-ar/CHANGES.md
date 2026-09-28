# CHANGES — schoolos-report-ar

الأصل: `snapshot/.claude/skills/schoolos-report-ar/` (SKILL 99 سطراً، مرجعٌ 60، قالبٌ 120). التحقّقُ على `origin/main@81bc4937` (2026-09-28)، وبتصيير WeasyPrint حقيقيٍّ في حاوية `shschool_mvp-web` بلا شبكة.

## سجلُّ الادّعاءات
| # | الادّعاء في الأصل | الحكم | الدليل |
|---|---|---|---|
| 1 | `core.pdf_utils.render_pdf(html, filename, paper_size)`، WeasyPrint ثمّ Playwright/xhtml2pdf | صحيحٌ ناقص | يقبل `as_attachment`، وله أخٌ `render_pdf_bytes` للعامل |
| 2 | `reports.services.ExcelService` / `AcademicReportsExcel` / `ReportDataService` / `AcademicReportsService` | صحيح | `reports/services.py:45,289,793,979` |
| 3 | نمطُ الـview: `render_to_string` ثمّ `render_pdf` | قديمٌ للجديد | الجديدُ بنّاءٌ مسجَّل + `respond_export` (ADR-0007)؛ و`HEAVY_IN_VIEWS` تمنع زيادته |
| 4 | «التوليد الثقيل → Celery» | صحيحٌ عامّ | صار محدَّداً: `core/exports/`، `core.export.run_job`، العتبتان |
| 5 | «ابدأ من `assets/report_template.html`» | **خاطئٌ ضارّ** | القالبُ القديم: `running(pageHeader)` و`@bottom-*` (يُسقط `tests/print_frame_ratchet.py`)، خطوط `NotoSansArabic-*.ttf` غيرُ موجودة في `static/fonts/`، `@font-face` بـ`{% static %}` (يسقط إلى DejaVu بنصّ `core/pdf_utils.py`)، سداسيٌّ حرفيّ (حارسُ الهويّة)، ولا علامة `data-pdf-own-page` (يحقن الإطارَ القديم) |
| 6 | ترويسة: شعارُ الدولة يميناً، «دولة قطر — وزارة التعليم والتعليم العالي» | خاطئ | «وزارة التربية والتعليم والتعليم العالي — دولة قطر» (`core/templatetags/print_frame.py::MINISTRY`، `reports/services.py`)؛ الشعارُ وسطاً فوق الوزارة |
| 7 | الشعار `assets/brand/qatar-emblem-2022.svg` | خاطئ | غيرُ موجود؛ `static/brand/logoMaroon.png` و`emblem.svg` |
| 8 | تذييل: سرّيّة · تاريخٌ هجريّ/ميلاديّ · «صفحة X من Y» · بصمةُ المنصّة | خاطئ | الإطار: المدرسة · ص/ص · تاريخُ الطباعة ووقتُها ثمّ الرؤية…؛ «SchoolOS-SAMM» أُخرج بأمر المالك 2026-09-27 (المواصفة v2.3) |
| 9 | الخطوط Noto Sans Arabic · IBM Plex · Cairo · Sakkal Majalla | خاطئ | `static/fonts/`: Tajawal وAmiri وNoto Naskh Arabic؛ وTraditional Arabic من `StoredFile` |
| 10 | «≥ 9pt للبيانات»، H1 20pt، جداول 10–11 | قديم | D2 (المواصفة §٤-١): جداول 10pt، عنوان 16 (أدنى 14)، تذييل 10 (أدنى 9) |
| 11 | هوامش 20mm وتجليدٌ 30mm، ترويسة 22mm، تذييل 14mm | غيرُ موثَّقٍ ومخالف | `core/print_frame.py`: 6/6/9مم، ترويسة 30–35مم، تذييل 8مم |
| 12 | `thead { display: table-header-group }` و`page-break-inside: avoid` | صحيح | CSS Paged Media؛ مستعملٌ في القوالب |
| 13 | Excel: `rightToLeft=True` | صحيح | `ExcelService._make_workbook` |
| 14 | Excel: `freeze_panes = "A4"` | خاطئ | `"A5"` (ثلاثةُ صفوف عنوان + رأسٌ في الرابع) `reports/services.py:1228,1320,1412` |
| 15 | `ExcelService._add_professional_header` | صحيح | `reports/services.py:1013` |
| 16 | «reportlab يفشل مع جدولٍ فارغ» وحارسٌ في `reports/views.py` | صحيح | تعليقُ الحارس في `class_results_pdf` |
| 17 | `hijri-converter` «إن كان مثبّتاً» | لا يمكن التحقّق/غائب | غيرُ موجودٍ في `requirements.txt` |
| 18 | تصنيفاتُ السرّيّة عام/داخلي/سرّي | غيرُ موثَّق | لا أثرَ في الشيفرة ولا في الذاكرة ولا في المواصفة |
| 19 | أسماءُ ملفّاتٍ عربيّةٌ وصفيّة | صحيحٌ جزئيّاً | عربيّةٌ في التقارير، لاتينيّةٌ في السلوك وغيره، و`generate_export_filename` موحِّدٌ غيرُ عامّ |
| 20 | «المسار الوحيد: D:\shschool_mvp مباشرة» | قديم (أُلغي 2026-09-08) | `CLAUDE.md` |
| 21 | «مرجعُ الطباعة أيضاً في `web-design-mastery/references/reports-print.md`» | قديمٌ متضارب | ذلك المرجع عامٌّ ويخالف الإطار؛ صار مختصراً يحيل إلى هذه المهارة |

## التغييرات
| البند | القديم | الجديد | السبب | الدليل |
|---|---|---|---|---|
| الوصف | عربيٌّ، كلماتٌ عامّة (print, RTL) | EN ثمّ AR pushy ثمّ «ليست لـ»، بأسماء الأدوات والشكاوى الشائعة | الكرّاسة §2؛ منعُ تفعيلٍ على صفحات الويب | BRIEF.md |
| المسار | view يولّد | بنّاءٌ مسجَّل + `respond_export` + عامل | ADR-0007، الحارس | `core/exports/`، `tests/test_export_guards.py` |
| القالب `assets/` | ترويسةٌ وتذييلٌ محلّيّان وخطوطٌ غائبة | وسومُ الإطار + `data-pdf-own-page` + `brand_color` + D2 | البند 5 | تصييرٌ حقيقيّ (أدناه) |
| الإطار | «ترويسةٌ وتذييلٌ لكلّ صفحة» عامّ | مرجع `10-print-frame.md`: الوسوم، ما يُرسم، الحدود، تباينُ المواصفة v2.4 والشيفرة | مصدرٌ واحد | `print_fit_spec.md`، `core/print_frame.py` |
| الخطّ | ≥ 9pt | جدولُ D2 كاملاً والاستثناءُ الوحيد (7.9pt) | قرارُ المالك 2026-09-26 | المواصفة §٤-١ |
| Excel | أسطرٌ عامّة | مرجع `20-excel.md`: الأدوات، `A5`، ذيلُ الرؤية، الرقمُ في Excel، حقنُ الصيغ | قراراتُ 09-14 و09-27 | `core/export_utils.py`، `core/excel_safety.py`، حارسان |
| الخصوصيّة | «لا PII غير مبرّر + تصنيفُ سرّيّة» | قاعدةُ `core/privacy.py` (جماعيٌّ مستور، فرديٌّ مسمّى) + `log_export` | مكتوبةٌ ومحروسة | `tests/test_national_id_never_bulk.py` |
| الطباعة | — | لا زرَّ طباعة صفحة ويب؛ الوثيقةُ الثابتة ملفٌّ ثابت | حارسٌ وذاكرة | `tests/test_no_web_page_print_button.py`؛ `feedback_performance_static.md` |
| الهجريّ والسرّيّة | قاعدتان | «غيرُ موثَّق» ينتظر قراراً | الكرّاسة §3 | — |
| البنية | SKILL + مرجع | SKILL + `00`/`10`/`20`/`30`/`99` + القالب | الكرّاسة §2 | — |

**اختبارُ القالب الجديد** (حاوية `shschool_mvp-web`، `--network none`، إعدادات `testing`، على نسخةٍ من main في المؤقّت): 90 صفّاً ← 4 صفحات A4 (210×297) و4 صفحات A3 أفقيّ (420×297)، اسمُ المدرسة في ترويسة كلّ صفحة، أصغرُ خطٍّ مرسومٍ 9pt (سطرُ الوزارة والتذييل من الإطار)، والحالةُ الفارغة تُولَّد؛ `python -m tests.print_frame_ratchet` و`python -m tests.design_ratchet` برمز 0 والقالبُ منسوخٌ تحت `templates/`. **وبلا العلامة** خرج بترويسة «SchoolOS» وتذييل «SchoolOS v6» بدل الإطار — فالعلامةُ إلزاميّة. ملفّاتُ الفحص حُذفت من المؤقّت ولا شيءَ منها في التسليم.

## يحتاج قرارَ المالك أو تأكيدَه
1. **عيبٌ على main:** `templates/behavior/pdf/base_form.html` يستعمل الإطارَ المركزيّ بلا `data-pdf-own-page`، فتُطبع «SchoolOS v6» والتاريخ في زاويتَي تذييل نماذج السلوك فوق التذييل المركزيّ — مخالفٌ لأمر 2026-09-27 بإخراج علامة المنصّة. مقيسٌ بتصييرٍ حقيقيّ؛ و`tests/test_form_pdf_page_footer.py` لا يلتقطه (يتحقّق من الرؤية وحدها).
2. **المواصفة v2.4 مقابل `core/print_frame.py`:** الرؤيةُ في ترويسة العموديّ و`HEADER_H_MM` 35مم في الشيفرة، والمواصفةُ تقول تذييلاً وترويسةً 30مم لكلّ المقاسات.
3. **خطُّ ذيل Excel** 8pt في `apply_print_footer` والمواصفة §٥-٦ تقترح 10pt.
4. **التاريخُ الهجريّ وتصنيفُ السرّيّة** في المطبوعات — مطلوبان؟ لا قرارَ ولا مكتبة.
5. **توحيدُ أسماء الملفّات** (عربيٌّ وصفيّ أم `generate_export_filename`) — القائمُ مختلط.
