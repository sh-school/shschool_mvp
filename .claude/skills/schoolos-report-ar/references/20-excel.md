# ملفّاتُ Excel الرسميّة

متى تقرأ هذا الملف: حين تبني ملفَّ Excel يُصدَّر أو تعدّل واحداً قائماً، أو حين يسقط `tests/test_excel_print_footer.py` أو `tests/test_excel_formula_injection.py`.

المصادر: `reports/services.py::ExcelService` و`AcademicReportsExcel`، `core/export_utils.py`، `core/excel_safety.py`، `tests/test_excel_print_footer.py`، `tests/test_national_id_never_bulk.py`.

## الأدوات
| الأداة | الموضع | ما تفعله |
|---|---|---|
| `ExcelService._make_workbook(title)` | `reports/services.py` | مصنّفٌ بورقةٍ `rightToLeft = True` وأنماطُ الجدول الموحّدة |
| `ExcelService._add_professional_header(ws, school_name, title, year, num_cols)` | `reports/services.py` | ثلاثةُ صفوف عنوان (المدرسة وشعارُها ← العنوان والسنة ← الوزارة وتاريخ الطباعة) + رأسُ صفحة الطباعة باسم المدرسة |
| `add_excel_title_rows(ws, num_cols, first, second, third)` | `core/export_utils.py` | الصفوفُ الثلاثة نفسُها لمن لا يستعمل `ExcelService` |
| `excel_table_styles()` / `brand_cell(cell)` | `core/export_utils.py` | رأسٌ عنّابيٌّ بنصٍّ أبيض، شبكةٌ بلون الحدود، صفٌّ متناوبٌ `MAROON_BG`، خطُّ Tajawal |
| `ExcelService._setup_print(ws, num_cols, num_rows, paper="a4", orientation="portrait")` | `reports/services.py` | مقاسُ الورق، ملاءمةُ العرض في صفحة، هوامش، `print_title_rows = "1:4"`، منطقةُ الطباعة |
| `ExcelService._apply_protection(ws, num_cols)` | `reports/services.py` | حمايةُ القراءة مع الفرز والتصفية؛ كلمةُ السرّ من `EXCEL_PROTECTION_PASSWORD` |
| `excel_to_response(wb, filename, school)` / `ExcelService.to_response(...)` | `core/export_utils.py`، `reports/services.py` | يستدعي `apply_print_footer` ثمّ يبني الاستجابةَ بترويسة اسم ملفٍّ صحيحة |
| `apply_print_footer(wb, school)` | `core/export_utils.py` | لكلّ ورقة: الوسطُ «الرؤية — &P / &N» سطراً واحداً، واليمينُ `&D` إن كان فارغاً |
| `neutralize_formula_value(v)` | `core/excel_safety.py` | يُسبق النصَّ الذي يبدأ بـ`= + - @` بـ`'` (CWE-1236) |

## الشكلُ المعتمد
- الصفوف 1–3 عنوان، والصفّ 4 رأسُ الأعمدة، والبيانُ من الصفّ 5: **`ws.freeze_panes = "A5"`** وتكرارُ الطباعة `"1:4"` (كما في `class_results_excel` و`attendance_excel` و`behavior_excel`).
- الأرقامُ والدرجاتُ وسطاً (`data_align`)؛ عرضُ الأعمدة يُمرَّر مع العنوان في `_add_header_row(ws, styles, 4, [(عنوان، عرض)…])`.
- A3 أفقيٌّ للكشوف العريضة عبر `_setup_print_a3_landscape`؛ ولا تنقل حجمَ الخطّ تحت 10 لتسع.
- ألوانُ الشيفرة من `core.brand` عبر `brand.excel(...)`/`xl_fill`/`xl_font` — لا سداسيٌّ مكتوب (`tests/test_brand_literals.py`).

## ذيلُ الطباعة (قرارُ المالك 2026-09-27)
- **كلُّ نقطة حفظٍ لمصنّفٍ تمرّ بـ`apply_print_footer`** — والحارسُ النصّيّ في `tests/test_excel_print_footer.py` يمنع نقطةَ حفظٍ جديدةً بلا الرؤية.
- في الـview: `excel_to_response(...)`. في البنّاء الخلفيّ (يُرجع bytes): `apply_print_footer(wb, school)` ثمّ `wb.save(buf)`.
- لا تكتب `ws.oddFooter.center.text` بعده — تمحو الرؤية. واليمينُ يُترك إن ملأتَه أنت قبله.
- تباين: المواصفة §٥-٦ تقترح خطَّ 10pt في الذيل، والشيفرةُ تكتب 8 (`footer.center.size = 8`) — قرارٌ لمسار الهويّة لا لطلب تقرير.

## الرقمُ الشخصيّ في Excel (قرارُ المالك 2026-09-14)
- **كاملٌ** حيث يعود الملفُّ للمطابقة: الاستيرادُ أو الرفعُ الوزاريّ — والدالّةُ مسمّاةٌ في `EXCEL_FULL_NUMBER` وتعليقُها «الرقم الشخصيّ: مطابقةٌ وزاريّة — كامل»، ورايةُ `full_national_id=True` في التدقيق.
- **مستورٌ** في كلّ Excel سواه: `mask_national_id`، وتعليقُ «الرقم الشخصيّ: مستور».
- وفي الحالتين `log_export` (أو `rows`/`full_national_id` في `ExportResult`).

## الحقنُ والقيم
- كلُّ نصٍّ كتبه مستخدمٌ (اسم، سبب، ملاحظة) يمرّ بـ`neutralize_formula_value` قبل الخليّة؛ الأرقامُ والتواريخ تُكتب بقيمها لا نصوصاً.
- التواريخُ قيمُ `date` لا نصوص، والنسبُ أرقامٌ بتنسيق خليّةٍ لا نصٌّ فيه «%».

## أنماطٌ مضادّة
- `openpyxl.Workbook()` جديدٌ داخل view (السقّاطة `HEAVY_IN_VIEWS`) أو ترويسةٌ رابعةٌ بتصميمٍ مختلف.
- `ws.freeze_panes = "A2"` أو `print_title_rows = "1:1"` مع ترويسة المنصّة.
- `wb.save(response)` مباشرةً دون `apply_print_footer`، أو `Content-Disposition` مكتوبٌ يدويّاً باسمٍ عربيّ (يصل مشوَّهاً).
- لوحةُ ألوانٍ خاصّة (`1F4E79`، `F5F5F5`…) أو خطُّ Cairo/Calibri — الهويّةُ واحدة.
- كلمةُ سرّ حمايةٍ حرفيّةٌ في الشيفرة.
