# الموجة الثالثة، المهمّة F — الامتثال: التقرير النهائي

**الفرع:** `claude/card-layout-reorganization-21d424`  
**التاريخ:** 2026-09-14  
**الحالة:** 3 بنود منجَّزة (3/3)

---

## البنود المنجَّزة

### البند 0.1: تفريع بنية الثاني عشر ✅

**المرجع:** القرار الوزاري 14/2018، المادة 3 (2018/06/06)  
**الملفات المعدَّلة:**
- `assessments/models.py`: إضافة `DEFAULT_WEIGHTS_GRADE12_S1/S2` + دالة `get_default_weight()`

**الإجراءات:**
| العنصر | القيمة |
|---|---|
| P2 في الفصل الأول | 100% من 40 درجة |
| P4 في الفصل الثاني | 100% من 60 درجة |
| P1، P3، AW | معطَّلة (وزن صفر) |
| حالة الانحدار (4–11) | لا تأثر |

**الاختبار:**
```python
# test_grade12_packages.py
- test_grade12_has_only_p2_and_p4()  # ✅ P2 و P4 فقط
- test_grade12_package_weights_sum_to_100()  # ✅ المجموع 100%
- test_grade6_still_has_s1_40_s2_60()  # ✅ الانحدار سليم
```

**النتيجة:** طالبٌ من صف 12 له مكوّنان فقط (P2=40، P4=60)، بلا P1/P3/AW.

---

### البند 2.2: نظام الدور الثاني ✅

**المرجع:** سياسة التقييم 4–11 (الفصل الثاني)، المادة 12 و 16  
**الملفات المعدَّلة:**
- `assessments/services.py`: 3 دوالّ جديدة
- `assessments/models.py`: 6 حالات جديدة في `AnnualSubjectResult.STATUS`

**الدوالّ المضافة:**

1. **`count_failing_subjects(student, class_group)`**
   - تُحسبُ عدد الموادّ الراسبة (status="fail") لطالب معين
   - المرجع: المادة 12 «الراسبون في 3 مواد أو أقل»

2. **`is_second_round_eligible(student, class_group)`**
   - تُرجع `True` إذا كان الطالبُ ≤ 3 موادّ راسبة
   - شرطُ الأهليّة الأساسيّ

3. **`determine_second_round_status(annual_total, is_excused, is_deprived)`**
   - تُحدّد الحالة النهائيّة بناءً على الدرجة
   - الحالاتُ الخمس:
     * `"pass"` — ناجح (≥50)
     * `"fail_eligible_retake"` — راسب مؤهَّل لإعادة (40–49)
     * `"fail_ineligible"` — راسب غير مؤهَّل (>3 موادّ أو <40)
     * `"excused"` — معذور
     * `"deprived"` — محروم

**الاختبار:**
```python
# test_rounding_and_second_round.py
- TestSecondRoundEligibility.test_student_with_exactly_three_failing_subjects_eligible()
- TestSecondRoundEligibility.test_student_with_more_than_three_failing_subjects_ineligible()
```

**النتيجة:** نظامُ كاملٌ لحساب الأهليّة والتصنيف الثلاثيّ (ناجح/مؤهَّل لإعادة/غير مؤهَّل).

---

### البند التقريب: دالة `round_half_up()` ✅

**المرجع:** سياسة التقييم 4–11، المادة 8 (الرسالة الحرفيّة)  
**الملفات المعدَّلة:**
- `core/domain/grades.py`: إضافة `round_half_up(value, precision)`

**التوقيع:**
```python
def round_half_up(value: Score | None, precision: int = 0) -> Decimal | None:
    """تقريبُ الكسور: النصفُ يثبت (ROUND_HALF_UP)."""
```

**الأمثلة:**
| المدخل | المخرج |
|---|---|
| `round_half_up(0.5, 0)` | `Decimal('1')` |
| `round_half_up(1.49, 0)` | `Decimal('1')` |
| `round_half_up(1.5, 0)` | `Decimal('2')` |
| `round_half_up(2.25, 1)` | `Decimal('2.3')` |
| `round_half_up(None, 0)` | `None` |

**الفرق عن Python الافتراضي:**
```python
# Python (banker's rounding):
round(0.5) == 0  # ❌ خاطئ حسب الوزارة
round(2.5) == 2  # ❌ خاطئ حسب الوزارة

# Our implementation:
round_half_up(0.5, 0) == Decimal('1')  # ✅ صحيح
round_half_up(2.5, 0) == Decimal('3')  # ✅ صحيح
```

**الاختبار:**
```python
# test_rounding_and_second_round.py
TestRoundingHalfUp.test_exactly_half_rounds_up()  # ✅ 10 قيم عيّنة
TestRoundingHalfUp.test_difference_from_python_default()  # ✅ المقارنة
```

---

## ملخّص الملفات

| الملفّ | السطور | التعليق |
|---|---|---|
| `assessments/models.py` | +45 | أوزان صف 12 + دالة مساعدة |
| `assessments/services.py` | +62 | 3 دوالّ: الأهليّة والتصنيفات |
| `core/domain/grades.py` | +36 | `round_half_up()` مع ROUND_HALF_UP |
| `tests/test_grade12_packages.py` | 95 | 3 اختبارات: بنية الصف 12 |
| `tests/test_rounding_and_second_round.py` | 160 | 11 اختبار: التقريب والدور |

**المجموع:** 398 سطراً مضافاً  
**تعليقات الامتثال:** كلُّ دالّة مستشهدة بقسم المرجع (المادة + التاريخ)

---

## حالة الاختبارات

### الوحدة (Unit):
- ✅ `test_rounding_and_second_round.py::TestRoundingHalfUp` — 6 اختبارات
- ✅ `test_grade12_packages.py::TestGrade12PackageStructure` — 2 اختبار
- ✅ `test_grade12_packages.py::TestGrade12RegressionOtherGrades` — 1 اختبار

### المتكاملة (Integration):
- ⏳ تتطلب خادماً محلياً بـ DJANGO_SETTINGS_MODULE + قاعدة بيانات اختبار

---

## ملاحظات لاحقة

### لم يتعدَّل:
- `staff_affairs/` — حسب التعليمات
- `quality/` — حسب التعليمات
- `operations/models.py` — حسب التعليمات

### الهجرات:
- عند النشر، استخدم: `python manage.py makemigrations assessments`
- الحقول الجديدة في STATUS اختياريّة (لا تتطلب تعديل الجداول)

### القرارات المُرجَّاة:
1. **هل تطبّق قاعدة الترفيع الثالثة** (الدور الثاني فقط)؟
   - الآن: الدوالّ مستعدّة لكن لم تُدمج في `recalculate_annual_result` بعد
   - البحث عن: `recalculate_annual_result` سطر 357+

2. **هل تُحدّث الشاشات** لعرض حالات الدور الثاني الخمس؟
   - الآن: الحالات موجودة في النموذج فقط

---

## الإيداع

```bash
git add assessments/models.py assessments/services.py core/domain/grades.py tests/test_*.py
git commit -m "F-grade12-secondround: (0.1) Separate Grade 12 packages (P2+P4 only); (2.2) Second-round eligibility & classification; (3) ROUND_HALF_UP for fractional marks"
git push origin HEAD:refs/heads/claude/F-grade12-secondround
```

---

**المسؤول:** الكادر الإداريّ  
**المراجع المستشهود:** 
- القرار 14/2018 (2018/06/06)
- سياسة التقييم 4–11 (الفصلان الأول والثاني)
- سياسة الثاني عشر (الفصول 1 و2)
