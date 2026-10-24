# حارسُ الثوابت: الكاتبُ المركزيّ لـExcel (W-20261021-004)

> صفٌّ من جدول «ج. حرّاسُ الثوابت» — ملفٌّ مستقلٌّ باسم أوّل اختبارٍ فيه.

| المجال | الحرّاس | ما يفرضونه |
|---|---|---|
| **حقنُ الصيغ في Excel (CWE-1236)** | `tests/test_excel_writer_guard.py` (حارسُ AST)، `tests/test_excel_writer_migration.py`، `tests/test_excel_formula_injection.py` | لا يُكتب نصٌّ في خليّة openpyxl خارج `core/excel_safety.py`: يرفض الحارسُ `ws.cell(..., value)` و`ws.append` و`ws[...] =` و`cell.value =` على ورقةٍ (تُعرف بالأسماء الشائعة أو بمتغيّرٍ من `wb.active`/`create_sheet`، فلا يخطئ بقوائم Python). المدخلُ الصحيح `safe_cell`/`safe_set`/`safe_append`: النصُّ المبدوء بـ`=` `+` `-` `@` يُسبق بـ`'`، والأرقامُ والتواريخُ و`None` و`bool` تمرّ بنوعها. مولّدٌ لم يُرحَّل يُسمّى في `PENDING_MIGRATION` بسببه (اليومَ: `staff_affairs/attendance/daily.py`)، ويفشل الاختبارُ إن رُحِّل ولم يُحذف مدخلُه |
