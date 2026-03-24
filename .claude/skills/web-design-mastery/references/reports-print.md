# التقارير الاحترافية — PDF + Excel + طباعة A4/A3

---

## 1. معايير تقارير PDF

### الهوامش والتخطيط

| العنصر | القيمة | ملاحظة |
|--------|--------|--------|
| هوامش عادية | 20mm من كل جانب | المعيار للتقارير |
| هامش التجليد (RTL) | 30mm يمين، 15mm يسار | للتجليد على اليمين |
| منطقة الهيدر | 15mm أعلى | شعار + عنوان + رقم الصفحة |
| منطقة الفوتر | 12mm أسفل | تاريخ + سرية + صفحة X من Y |
| المنطقة الآمنة A4 | 170mm × 257mm | بعد خصم الهوامش |
| المنطقة الآمنة A3 | 257mm × 380mm | بعد خصم الهوامش |

### الطباعة (Typography) للتقارير

**الخطوط المعتمدة (بالأولوية):**
1. **Noto Sans Arabic** — شامل، مجاني، ممتاز للتقارير
2. **IBM Plex Sans Arabic** — احترافي، تناغم مع اللاتيني
3. **Cairo** — واضح، مقروء، مناسب للبيانات
4. **Sakkal Majalla** — خط نظام Windows، رسمي

**أحجام الخطوط:**

| العنصر | الحجم | الوزن |
|--------|-------|-------|
| عنوان التقرير (H1) | 20pt | Bold |
| عنوان قسم (H2) | 16pt | Bold |
| عنوان فرعي (H3) | 13pt | SemiBold |
| نص عربي أساسي | 12pt | Regular (400) |
| نص إنجليزي ثانوي | 10-11pt | Regular |
| نص الجداول | 9-10pt | Regular |
| الفوتر/الهيدر | 8pt | Regular |
| ملاحظات/حواشي | 8pt | Light (300) |

**قواعد:**
- `line-height: 1.6-1.8` للنص العربي
- لا italic للعربي — استخدم **bold** أو لون للتمييز
- Font subsetting: خفّض من ~900KB إلى ~100KB بتضمين الأحرف المستخدمة فقط
- تضمين الخط في PDF (embed) لضمان العرض الصحيح على أي جهاز

### الألوان في الطباعة

| الاستخدام | اللون | الكود |
|-----------|-------|-------|
| نص أساسي | أسود نقي | `#000000` |
| نص ثانوي | رمادي غامق | `#555555` |
| هيدر جدول (خلفية) | لون البراند الغامق | `#1F4E79` أو لون المدرسة |
| هيدر جدول (نص) | أبيض | `#FFFFFF` |
| صف زوجي (zebra) | رمادي فاتح جداً | `#F5F5F5` |
| حدود جدول | رمادي خفيف | `#CCCCCC` |
| نجاح/ناجح | أخضر غامق | `#2E7D32` |
| رسوب/خطر | أحمر غامق | `#C62828` |
| تحذير | برتقالي غامق | `#E65100` |

**قواعد:**
- صمّم أولاً للأبيض والأسود — اللون تحسين
- `print-color-adjust: exact` لحفظ ألوان الخلفية
- تباين ≥ 7:1 للنص الصغير (WCAG AAA)
- لا تعتمد على اللون وحده — أضف أيقونات أو نص

### تنسيق الجداول في PDF

```css
/* هيدر يتكرر كل صفحة */
thead { display: table-header-group; }
tfoot { display: table-footer-group; }

/* هيدر الجدول */
thead th {
  background-color: #1F4E79;
  color: #FFFFFF;
  font-weight: bold;
  font-size: 10pt;
  padding: 6pt 8pt;
  border-bottom: 2pt solid #000;
  text-align: right; /* RTL */
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}

/* خلايا البيانات */
tbody td {
  padding: 4pt 8pt;
  border-bottom: 0.5pt solid #CCCCCC;
  font-size: 9pt;
  vertical-align: middle;
}

/* صفوف زوجية */
tbody tr:nth-child(even) {
  background-color: #F5F5F5;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}

/* منع تقسيم الصف بين صفحتين */
tr { break-inside: avoid; }

/* أرقام بمحاذاة عمودية */
td.num {
  text-align: center;
  font-variant-numeric: tabular-nums;
  font-family: 'Courier New', monospace; /* أرقام بعرض ثابت */
}
```

### Metadata للـ PDF

```python
# في Django/WeasyPrint
metadata = {
    'title': 'كشف درجات الفصل الأول - 2025/2026',
    'author': 'SchoolOS - مدرسة الشحانية',
    'subject': 'تقرير أكاديمي',
    'creator': 'SchoolOS v1.0',
    'keywords': 'درجات, تقرير, الفصل الأول',
}
```

### تحسين حجم الملف
- Font subsetting — ضروري (يوفر 200KB+ لكل خط)
- صور JPEG بجودة 75-85، PNG للشعارات فقط
- دقة 150 DPI كافية لطابعات المكتب (300 DPI للطباعة الاحترافية فقط)
- **هدف:** تقرير درجات بسيط < 200KB، تقرير معقد متعدد الصفحات < 1MB

---

## 2. معايير ملفات Excel

### التنسيق الاحترافي

```python
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# === الأنماط المعتمدة ===

# عنوان التقرير
TITLE_STYLE = {
    'font': Font(name='Cairo', bold=True, size=16, color='1F4E79'),
    'alignment': Alignment(horizontal='center', vertical='center'),
}

# هيدر الجدول
HEADER_STYLE = {
    'font': Font(name='Cairo', bold=True, size=11, color='FFFFFF'),
    'fill': PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid'),
    'alignment': Alignment(horizontal='center', vertical='center', wrap_text=True),
    'border': Border(bottom=Side(style='medium', color='000000')),
}

# بيانات عادية
DATA_STYLE = {
    'font': Font(name='Cairo', size=10),
    'alignment': Alignment(horizontal='right', vertical='center', readingOrder=2),
    'border': Border(bottom=Side(style='thin', color='DDDDDD')),
}

# بيانات رقمية
NUM_STYLE = {
    'font': Font(name='Calibri', size=10),
    'alignment': Alignment(horizontal='center', vertical='center'),
    'number_format': '#,##0.0',
}

# صف زوجي (zebra)
ZEBRA_FILL = PatternFill(start_color='F5F5F5', end_color='F5F5F5', fill_type='solid')

# نجاح
SUCCESS_FONT = Font(name='Cairo', size=10, color='2E7D32', bold=True)
# رسوب
DANGER_FONT = Font(name='Cairo', size=10, color='C62828', bold=True)
```

### عرض الأعمدة وارتفاع الصفوف

| نوع العمود | العرض (حروف) | الاستخدام |
|-----------|-------------|-----------|
| اسم الطالب | 25-30 | أسماء عربية كاملة |
| رقم الطالب | 12-15 | ID |
| درجة | 8-10 | أرقام |
| نسبة مئوية | 10-12 | نسب |
| تاريخ | 12-14 | تواريخ |
| ملاحظات | 30-40 | نص حر |
| حالة حضور | 4-5 | ح/غ/م |

| نوع الصف | الارتفاع (points) |
|----------|------------------|
| عنوان التقرير | 35-40 |
| هيدر الجدول | 28-32 |
| بيانات عادية | 20-22 |
| صف ملخص | 25 |

### إعدادات RTL

```python
from openpyxl.worksheet.views import SheetView

# اتجاه الورقة من اليمين لليسار
ws.sheet_view = SheetView(rightToLeft=True)

# محاذاة عربية
rtl_alignment = Alignment(
    horizontal='right',
    vertical='center',
    readingOrder=2,  # 2 = RTL
    wrap_text=True,
)

# محاذاة أرقام (تبقى LTR)
num_alignment = Alignment(
    horizontal='center',
    vertical='center',
    readingOrder=1,  # 1 = LTR للأرقام
)
```

### Freeze Panes + Auto-Filter

```python
# تجميد الصف الأول (الهيدر)
ws.freeze_panes = 'A2'

# أو تجميد الصفين الأولين + العمود الأول
ws.freeze_panes = 'B3'

# فلتر تلقائي على كل الأعمدة
last_col = get_column_letter(ws.max_column)
ws.auto_filter.ref = f'A1:{last_col}{ws.max_row}'
```

### تنسيق الأرقام

```python
FORMATS = {
    'percentage': '0.0%',
    'grade': '0.00',
    'integer': '#,##0',
    'date_ar': 'YYYY/MM/DD',
    'date_en': 'DD/MM/YYYY',
    'currency_qar': '#,##0.00 "ر.ق"',
    'attendance': '@',  # نص (ح/غ/م)
}
```

### Data Validation

```python
from openpyxl.worksheet.datavalidation import DataValidation

# الدرجة بين 0 و 100
grade_validation = DataValidation(
    type="decimal",
    operator="between",
    formula1=0,
    formula2=100,
    errorTitle="خطأ في الدرجة",
    error="الدرجة يجب أن تكون بين 0 و 100",
    promptTitle="أدخل الدرجة",
    prompt="أدخل رقماً بين 0 و 100",
)
ws.add_data_validation(grade_validation)
grade_validation.add('C2:C1000')

# الحضور: ح أو غ أو م
attendance_validation = DataValidation(
    type="list",
    formula1='"ح,غ,م,أ"',
    errorTitle="خطأ في الحضور",
    error="اختر: ح (حاضر) أو غ (غائب) أو م (متأخر) أو أ (إذن)",
)
```

### تنظيم الأوراق المتعددة

| الورقة | المحتوى | الترتيب |
|--------|---------|---------|
| **الملخص** | إحصائيات عامة + رسوم بيانية | 1 (أولاً) |
| **البيانات التفصيلية** | الجدول الكامل | 2 |
| **الرسوم البيانية** | Charts منفصلة | 3 |
| **المعايير** | جداول مرجعية (تقييم، سلّم) | 4 (آخر) |

```python
# تلوين tabs الأوراق
ws_summary.sheet_properties.tabColor = '1F4E79'
ws_details.sheet_properties.tabColor = '2E7D32'
ws_charts.sheet_properties.tabColor = 'E65100'
```

### إعداد الطباعة من Excel

```python
from openpyxl.worksheet.page import PageMargins

# === A4 Portrait (تقارير درجات) ===
ws.page_setup.paperSize = ws.PAPERSIZE_A4
ws.page_setup.orientation = 'portrait'
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0

# === A3 Landscape (كشوف حضور عريضة) ===
ws.page_setup.paperSize = 8  # A3
ws.page_setup.orientation = 'landscape'
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0

# الهوامش
ws.page_margins = PageMargins(
    left=0.5, right=0.5,
    top=0.75, bottom=0.75,
    header=0.3, footer=0.3,
)

# تكرار الهيدر في كل صفحة مطبوعة
ws.print_title_rows = '1:2'

# منطقة الطباعة
ws.print_area = f'A1:{get_column_letter(ws.max_column)}{ws.max_row}'

# التمركز أفقياً
ws.print_options.horizontalCentered = True

# هيدر/فوتر مطبوع
ws.oddHeader.right.text = "مدرسة الشحانية"
ws.oddHeader.left.text = "&D"  # التاريخ
ws.oddFooter.center.text = "صفحة &P من &N"
```

---

## 3. معايير CSS للطباعة (@media print)

### إعداد الصفحة الكامل

```css
/* ============================================
   PRINT STYLESHEET — SchoolOS Reports
   ============================================ */

/* --- إعداد الصفحة --- */
@page {
  size: A4 portrait;
  margin: 20mm 15mm 20mm 15mm;
}

@page :first {
  margin-top: 30mm; /* مساحة إضافية للغلاف */
}

/* هوامش التجليد RTL */
@page :left {
  margin-right: 25mm; /* جانب التجليد */
  margin-left: 15mm;
}
@page :right {
  margin-right: 15mm;
  margin-left: 25mm;
}

/* A3 عرضي */
@page a3-landscape {
  size: A3 landscape;
  margin: 15mm;
}
.page-a3-landscape { page: a3-landscape; }

/* A4 عرضي */
@page a4-landscape {
  size: A4 landscape;
  margin: 15mm;
}
.page-a4-landscape { page: a4-landscape; }

/* --- أنماط الطباعة الأساسية --- */
@media print {

  /* إعادة ضبط */
  * {
    box-shadow: none !important;
    text-shadow: none !important;
  }

  body {
    font-family: 'Cairo', 'Noto Sans Arabic', sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #000;
    direction: rtl;
  }

  /* === إخفاء عناصر غير مطبوعة === */
  nav, .sidebar, .no-print, .toolbar,
  button:not(.print-visible), .btn,
  .pagination, .search-box, .toast,
  footer.site-footer, .mobile-menu {
    display: none !important;
  }

  /* === العناوين === */
  h1 { font-size: 20pt; margin-bottom: 12pt; }
  h2 { font-size: 16pt; margin-bottom: 10pt; break-after: avoid; }
  h3 { font-size: 13pt; margin-bottom: 8pt; break-after: avoid; }

  /* === التحكم في فواصل الصفحات === */
  p { orphans: 3; widows: 3; }
  h1, h2, h3, h4 { break-after: avoid; }
  tr { break-inside: avoid; }
  img, figure, .card, .student-card { break-inside: avoid; }
  .page-break { break-before: page; }
  .no-break { break-inside: avoid; }

  /* === الجداول === */
  table {
    border-collapse: collapse;
    width: 100%;
    font-size: 9pt;
  }

  thead { display: table-header-group; }  /* يتكرر كل صفحة */
  tfoot { display: table-footer-group; }

  thead th {
    background-color: #1F4E79 !important;
    color: #FFF !important;
    font-weight: bold;
    padding: 6pt 8pt;
    border-bottom: 2pt solid #000;
    text-align: right;
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }

  tbody td {
    padding: 4pt 8pt;
    border-bottom: 0.5pt solid #CCC;
  }

  tbody tr:nth-child(even) {
    background-color: #F5F5F5 !important;
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }

  /* أرقام */
  .num {
    text-align: center;
    font-variant-numeric: tabular-nums;
  }

  /* === الهيدر المتكرر (كل صفحة) === */
  .report-header {
    position: running(reportHeader);
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1pt solid #333;
    padding-bottom: 3mm;
  }
  @page { @top-center { content: element(reportHeader); } }

  .report-header .school-logo {
    height: 12mm;
    width: auto;
  }

  /* === الفوتر المتكرر (كل صفحة) === */
  .report-footer {
    position: running(reportFooter);
    font-size: 8pt;
    color: #666;
    border-top: 0.5pt solid #999;
    display: flex;
    justify-content: space-between;
    padding-top: 2mm;
  }
  @page { @bottom-center { content: element(reportFooter); } }

  /* رقم الصفحة (WeasyPrint) */
  .page-number::after { content: counter(page); }
  .page-total::after { content: counter(pages); }

  /* === أنماط التقارير المدرسية === */

  /* بيانات الطالب */
  .student-info {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4pt;
    margin-bottom: 12pt;
    font-size: 11pt;
  }
  .student-info dt { font-weight: bold; }
  .student-info dd { margin: 0; }

  /* التوقيعات */
  .signatures {
    display: flex;
    justify-content: space-between;
    margin-top: 20mm;
    padding-top: 5mm;
  }
  .signature-line {
    text-align: center;
    min-width: 35mm;
  }
  .signature-line::before {
    content: '';
    display: block;
    border-top: 1pt solid #000;
    margin-bottom: 3pt;
    width: 100%;
  }

  /* مساحة الختم */
  .stamp-area {
    width: 30mm;
    height: 30mm;
    border: 0.5pt dashed #999;
    margin-top: 10mm;
    float: left; /* RTL: يظهر يسار */
  }

  /* ثنائي اللغة */
  .bilingual {
    display: flex;
    justify-content: space-between;
  }
  .bilingual .ar { font-size: 14pt; font-weight: bold; }
  .bilingual .en { font-size: 11pt; color: #555; }

  th .ar { display: block; font-size: 10pt; }
  th .en { display: block; font-size: 7pt; color: #DDD; font-weight: normal; }
}
```

### أبعاد الورق الدقيقة

| الورق | العرض | الارتفاع | آمن (2cm) | أقصى أعمدة (9pt) | الاستخدام |
|-------|-------|---------|----------|-----------------|-----------|
| A4 Portrait | 210mm | 297mm | 170×257mm | 8-10 | درجات، خطابات، تقارير |
| A4 Landscape | 297mm | 210mm | 257×170mm | 12-15 | شهادات، رسوم بيانية |
| A3 Portrait | 297mm | 420mm | 257×380mm | 12-15 | تقارير تفصيلية طويلة |
| A3 Landscape | 420mm | 297mm | 380×257mm | 18-22 | كشوف حضور 31 يوم |

---

## 4. تقارير مدرسية احترافية

### هيكل تقرير الدرجات

```
┌──────────────────────────────────────────────────┐
│ [شعار المدرسة]    اسم المدرسة         [شعار   │
│                    School Name          الوزارة] │
│              التقرير الأكاديمي                    │
│           Academic Report                         │
├──────────────────────────────────────────────────┤
│ الطالب: ____________  الرقم: ____  الصف: ____    │
│ الفصل: ___  العام: 2025/2026  التاريخ: ___       │
├──────────────────────────────────────────────────┤
│                                                    │
│ ┌──────────────────────────────────────────────┐ │
│ │ المادة │ المعلم │ ف1 │ ف2 │ ف3 │ ف4 │ النهائي │ │
│ │────────│────────│────│────│────│────│─────────│ │
│ │ رياضيات│ أ.محمد │ 85 │ 90 │ 88 │ 92 │ 88.75  │ │
│ │ عربي  │ أ.خالد │ 78 │ 82 │ 85 │ 80 │ 81.25  │ │
│ └──────────────────────────────────────────────┘ │
│                                                    │
│ ┌──────────────────────────────────────────────┐ │
│ │ ملخص الحضور                                   │ │
│ │ حاضر: 165 │ غائب: 8 │ متأخر: 12 │ إذن: 5    │ │
│ └──────────────────────────────────────────────┘ │
│                                                    │
│ ملاحظات المعلم:                                   │
│ ________________________________________           │
│                                                    │
├──────────────────────────────────────────────────┤
│ التوقيعات:                                        │
│ المعلم: ______  المنسق: ______                    │
│ المدير: ______  ولي الأمر: ______                 │
│                                           [ختم]   │
├──────────────────────────────────────────────────┤
│ تاريخ الإصدار: ____ │ سري │ صفحة X من Y          │
└──────────────────────────────────────────────────┘
```

### كشف الحضور (A3 Landscape)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ كشف حضور الصف التاسع — شهر يناير 2026                                 │
├─────┬──────────────┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬─────┬─────┬────────┤
│ م   │ اسم الطالب    │ 1│ 2│ 3│ 4│ 5│ 6│ 7│...│30│31│ حاضر│ غائب│ نسبة % │
├─────┼──────────────┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼─────┼─────┼────────┤
│ 1   │ أحمد محمد    │ ح│ ح│ غ│ ح│ ح│ ح│ م│...│ ح│ ح│  27 │   2 │ 93.1% │
│ 2   │ خالد عبدالله │ ح│ ح│ ح│ ح│ غ│ ح│ ح│...│ ح│ ح│  28 │   1 │ 96.6% │
└─────┴──────────────┴──┴──┴──┴──┴──┴──┴──┴──┴──┴──┴─────┴─────┴────────┘
```

**مواصفات A3 Landscape للحضور:**
- أعمدة الأيام: 8mm عرض لكل يوم
- عمود الاسم: 40mm
- عمود الرقم: 20mm
- خط: 9pt condensed
- Padding: 3pt minimum
- حدود: 0.25pt خفيفة جداً
- هيدر يتكرر كل صفحة
- عطلات نهاية الأسبوع: خلفية رمادية أغمق

### كشف الدرجات التفصيلي

```
┌────────────────────────────────────────────────────────────┐
│ المادة: الرياضيات │ المعلم: أ. محمد │ الصف: التاسع أ       │
├─────┬────────────┬────┬────┬────┬────┬────┬────┬──────────┤
│ م   │ الطالب      │ شفهي│واجب│ ف1 │ ف2 │عملي│نهائي│ المجموع │
│     │             │ /10 │/10 │/20 │/20 │/10 │/30 │  /100   │
├─────┼────────────┼────┼────┼────┼────┼────┼────┼──────────┤
│ 1   │ أحمد محمد  │  9 │  8 │ 18 │ 17 │  9 │ 27 │   88    │
│ 2   │ خالد عبدالله│  7 │  9 │ 15 │ 16 │  8 │ 22 │   77    │
├─────┼────────────┼────┼────┼────┼────┼────┼────┼──────────┤
│     │ المتوسط    │ 8.0│ 8.5│16.5│16.5│ 8.5│24.5│  82.5   │
│     │ الأعلى     │  9 │  9 │ 18 │ 17 │  9 │ 27 │   88    │
│     │ الأدنى     │  7 │  8 │ 15 │ 16 │  8 │ 22 │   77    │
└─────┴────────────┴────┴────┴────┴────┴────┴────┴──────────┘
```

### الشهادة / السجل الأكاديمي (Transcript)

**متطلبات رسمية:**
- ورق A4 Portrait
- إطار زخرفي خفيف (border decorative)
- شعار المدرسة + شعار الوزارة
- اسم الطالب بالعربي والإنجليزي
- كل المواد مع الدرجات والتقديرات
- المعدل التراكمي (GPA)
- حالة الطالب (ناجح/راسب/متخرج)
- مساحة ختم + توقيع المدير
- رقم تسلسلي للوثيقة
- QR Code للتحقق الرقمي (اختياري)

---

## 5. Django — مكتبات وأنماط

### المكتبات المعتمدة

| الغرض | المكتبة | ملاحظة |
|-------|---------|--------|
| HTML → PDF | **WeasyPrint** + **django-weasyprint** | أفضل دعم CSS + عربي |
| إنشاء Excel | **openpyxl** | تنسيق كامل + charts + RTL |
| Excel كبير | **XlsxWriter** | أسرع + `set_right_to_left()` |
| رسوم بيانية في PDF | SVG مدمج في HTML | WeasyPrint يرندر SVG |
| تحسين PDF | **pikepdf** أو **PyMuPDF** | ضغط وتحسين |

### نمط WeasyPrint في Django

```python
# views.py
from django_weasyprint import WeasyTemplateResponseMixin

class GradeReportPDFView(WeasyTemplateResponseMixin, DetailView):
    model = Student
    template_name = 'reports/grade_report.html'
    pdf_stylesheets = [
        settings.STATIC_ROOT / 'css/print-report.css',
    ]

    def get_pdf_filename(self):
        student = self.get_object()
        return f'تقرير_درجات_{student.name}_{student.student_id}.pdf'
```

### نمط Excel في Django

```python
# views.py
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.worksheet.views import SheetView

def export_grades_excel(request, class_id):
    wb = Workbook()
    ws = wb.active
    ws.title = "الدرجات"
    ws.sheet_view = SheetView(rightToLeft=True)

    # هيدر
    headers = ['م', 'الطالب', 'ف1', 'ف2', 'ف3', 'ف4', 'النهائي']
    ws.append(headers)
    # ... تطبيق الأنماط والبيانات ...

    ws.freeze_panes = 'A2'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.print_title_rows = '1:1'

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="grades.xlsx"'
    wb.save(response)
    return response
```

---

## 6. Checklist — التقارير

### PDF
- [ ] هوامش 20mm + هامش تجليد إضافي (RTL: يمين)؟
- [ ] خط عربي 12pt+ مع line-height 1.6-1.8؟
- [ ] هيدر يتكرر كل صفحة (شعار + عنوان + صفحة)؟
- [ ] فوتر يتكرر (تاريخ + سرية + صفحة X من Y)؟
- [ ] `thead { display: table-header-group; }`؟
- [ ] Zebra striping محفوظ بـ `print-color-adjust: exact`؟
- [ ] Font embedded + subsetted؟
- [ ] حجم الملف < 200KB (بسيط) أو < 1MB (معقد)؟
- [ ] Metadata محدّث (عنوان، مؤلف، تاريخ)؟

### Excel
- [ ] RTL: `rightToLeft=True` + `readingOrder=2`؟
- [ ] Freeze panes على الهيدر؟
- [ ] Auto-filter مفعّل؟
- [ ] تنسيق أرقام صحيح (نسب، تواريخ، أعداد)؟
- [ ] Zebra rows؟
- [ ] Print title rows لتكرار الهيدر؟
- [ ] Paper size + orientation + fitToWidth؟
- [ ] أوراق متعددة منظمة (ملخص → تفاصيل)؟

### طباعة CSS
- [ ] `@page { size: A4/A3; margin: ... }`؟
- [ ] `orphans: 3; widows: 3`؟
- [ ] العناوين: `break-after: avoid`؟
- [ ] الصفوف: `break-inside: avoid`؟
- [ ] عناصر غير مطبوعة مخفية؟
- [ ] `print-color-adjust: exact` على الألوان المهمة؟
- [ ] `thead { display: table-header-group; }`؟

### التقارير المدرسية
- [ ] شعار المدرسة أعلى-يمين؟
- [ ] مساحة ختم 30×30mm؟
- [ ] خطوط توقيع مسماة (معلم، منسق، مدير)؟
- [ ] ثنائي اللغة (عربي + إنجليزي)؟
- [ ] بيانات الطالب كاملة (اسم، رقم، صف، فصل، عام)؟
