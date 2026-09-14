# ADR-0002: نموذجٌ واحدٌ لتقييم أداء الموظّفين — `quality.EmployeeEvaluation`

- **التاريخ:** 2026-09-14
- **الكاتب:** فريق منصّة SchoolOS
- **الحالة:** مقترح (Proposed). لا حذفَ ولا دمجَ لنموذجٍ قبل قرار المالك في القسم 6.
- **البند:** 1.2 من `AAdocs/ministry_data/2026_2027/remediation_plan.md` — «قرارٌ معماري
  (دمج/إحلال `operations.StaffEvaluation` بـ`quality.EmployeeEvaluation`)». الدمجُ جزءٌ من
  البند 1.2 نفسِه، لا بندٌ مستقلّ؛ و1.3 في الخطّة هو نموذجُ الاستئذان.
- **المرجع الوزاريّ:** `AAdocs/ministry_data/2026_2027/06_attendance_performance_review.md` §2.

---

## 1. السياق

في المنصّة نموذجان لتقييم الأداء السنويّ، كُتب كلٌّ منهما بمعزلٍ عن الآخر:

| | `operations.StaffEvaluation` | `quality.EmployeeEvaluation` |
|---|---|---|
| الموضع | `operations/models.py:1734` | `quality/models.py` (الصنف `EmployeeEvaluation`) |
| المرجع المذكور في الشيفرة | قرار مجلس الوزراء 32/2019 م.15 | القرار الأميري 9/2016 + قانون 9/2017 |

وجاءت الاستماراتُ الوزاريّةُ السبع (§2.3–2.9) بمحاورَ وأوزانٍ لا يحملها أيٌّ منهما.

### 1.1 من يستعمل كلّاً منهما — بالأوامر

الأعدادُ من الفرع `claude/wave3-h` بعد إيداعَي البذر والقيد (`17607835`، `7d04249c`).
والتقريرُ السابق زعم «8 مواضع» و«34 موضعاً» بلا أمر؛ هذه المخرجات تحلّ محلّه.

```text
$ git grep -n -w StaffEvaluation -- "*.py" "*.html" ":!*/migrations/*"
core/models/audit.py:58:        ("StaffEvaluation", "تقييم أداء موظف"),
operations/models.py:1734:class StaffEvaluation(models.Model):
staff_affairs/models.py:4:(TeacherAbsence, StaffEvaluation, TeacherSwap, CompensatorySession).
staff_affairs/services.py:54:        from operations.models import StaffEvaluation, TeacherAbsence, TeacherSwap
staff_affairs/services.py:83:        pending_evals = StaffEvaluation.objects.filter(

$ git grep -n -E "staff_evaluations|evaluations_as_staff|evaluations_as_evaluator" -- "*.py" "*.html" ":!*/migrations/*"
operations/models.py:1768:        related_name="evaluations_as_staff",
operations/models.py:1774:        related_name="evaluations_as_evaluator",
operations/models.py:1780:        related_name="staff_evaluations",
staff_affairs/services.py:180:            list(school.staff_evaluations.filter(staff=user).order_by("-academic_year")[:5])
staff_affairs/services.py:181:            if hasattr(school, "staff_evaluations")

$ git grep -c -w EmployeeEvaluation -- "*.py" "*.html" ":!*/migrations/*"
quality/admin.py:2
quality/evaluation_services.py:7
quality/evaluation_views.py:8
quality/models.py:4
quality/observation_models.py:1
tests/test_evaluation_sanction_gate.py:5
tests/test_ministry_appraisal_forms.py:2
tests/test_quality_models.py:4
tests/test_querysets_services.py:5
tests/test_views_quality2.py:6

$ git grep -n "evaluation_views\." -- quality/urls.py
quality/urls.py:84:    path("evaluations/", evaluation_views.evaluation_dashboard, name="evaluation_dashboard"),
quality/urls.py:87:        evaluation_views.create_evaluation,
quality/urls.py:92:        evaluation_views.acknowledge_evaluation,
quality/urls.py:95:    path("evaluations/mine/", evaluation_views.my_evaluations, name="my_evaluations"),
```

الخلاصة:

| | `StaffEvaluation` | `EmployeeEvaluation` |
|---|---|---|
| مسارٌ يكتبه | **لا شيء** — لا عرضَ ولا نموذجَ ولا أمرَ ولا تسجيلَ في الإدارة | `create_evaluation` عبر `evaluation_services.save_evaluation`، و`acknowledge_evaluation` |
| من يقرؤه | لوحةُ شؤون الموظّفين (`staff_affairs/services.py:83`، مؤشّر «تقييماتٌ غير مكتملة»)، وملفُّ الموظّف (`:180`) | لوحةُ التقييم، نموذجُه، «تقييماتي»، `EvaluationCycle.completion_rate` |
| المسارات | 0 | 4 (`quality/urls.py:84–95`) |
| القوالب | عبر `staff_affairs/dashboard.html:33` و`staff_profile.html:25,133` | `quality/evaluation_dashboard.html`، `evaluation_form.html`، `my_evaluations.html` |
| الإدارة | غير مسجَّل | `quality/admin.py:249` |
| الاختبارات | لا شيء | ثلاثةُ ملفّاتٍ قائمة + ملفّا هذه الموجة |

والنتيجةُ العمليّة: **شؤونُ الموظّفين تقرأ من نموذجٍ لا يكتبه أحد.** مؤشّرُ «تقييماتٌ غير
مكتملة» صفرٌ دائماً، وقسمُ «تقييم الأداء» في ملفّ الموظّف فارغٌ دائماً، ولو قُدّمت عشراتُ
التقييمات في `quality`.

### 1.2 الصفوف — محلّيّاً

قاعدةُ الجلسة `ss_wave3_h` نسخةٌ من `shschool_db` المشتركة (`scripts/session-db.sh`)،
بعد تطبيق البذر وحذف قوالب الجولة الأولى اليتيمة:

```text
$ python manage.py shell -c "…for M in (StaffEvaluation, EmployeeEvaluation, EvaluationScore, EvaluationCycle, RoleEvaluationTemplate, EvaluationAxis): print(M._meta.label, M.objects.count())"
DB ss_wave3_h
operations.StaffEvaluation 0
quality.EmployeeEvaluation 0
quality.EvaluationScore 0
quality.EvaluationCycle 0
quality.RoleEvaluationTemplate 21
quality.EvaluationAxis 190
```

والقاعدةُ المحلّيّة لا تمثّل الإنتاج، فالقرارُ لا يُبنى على صفرها.

### 1.3 الصفوف — الإنتاج (يُشغّله المالك)

```bash
railway ssh -s shschool_mvp
python manage.py shell -c "from operations.models import StaffEvaluation; from quality.models import EmployeeEvaluation, EvaluationScore, EvaluationCycle, RoleEvaluationTemplate, EvaluationAxis; [print(M._meta.label, M.objects.count()) for M in (StaffEvaluation, EmployeeEvaluation, EvaluationScore, EvaluationCycle, RoleEvaluationTemplate, EvaluationAxis)]; print(sorted(RoleEvaluationTemplate.objects.values_list('school__code', 'role_name', 'academic_year')))"
```

النتيجة: ___ (تُلصق هنا قبل تحويل الحالة إلى «مقبول»).

### 1.4 الفروق الحقليّة، ومقابلُها في الاستمارة الوزاريّة

| الجانب | `StaffEvaluation` | `EmployeeEvaluation` | الاستمارات السبع (§2) |
|---|---|---|---|
| المحاور | خمسةُ معاييرَ ثابتة 1–5، منها «فاعلية التدريس» و«تقييم الطلاب» — لا تصلح لغير المعلّم | أربعةُ محاورَ افتراضيّة 0–25، أو محاورُ قالب الدور (`RoleEvaluationTemplate`/`EvaluationAxis`) | لكلّ فئةٍ استمارتُها: 5–8 مجالاتٍ موزونة، أو 20 عنصراً للفئة العمالية؛ المجموع 100 |
| المجموع | `overall_score` متوسّطٌ عشريّ من 5 | `total_score` من 100، مرجَّحٌ على المقيِّمين (`EvaluationScore`) | من 100 |
| التقدير | `recommendation` بستّ درجات يختارها المقيِّم | `rating` محسوبٌ بأربع: 90 / 75 / 60 | خمس: ممتاز 90–100، جيد جداً 76–89، جيد 66–75، مقبول 50–65، ضعيف أقلّ من 50 (§2.2) |
| الدوريّة | صفٌّ لكلّ (موظّف، عام، مدرسة) | `period` = S1 أو S2 — مرّتان في العام | «سنوية في كل الاستمارات السبع بلا استثناء» (§2) |
| الحالة | مسودّة / مُقدَّم / معتمد | + «مُستلم من الموظّف» مع `acknowledged_at` و`employee_comment` | استلامُ الموظّف نسختَه، والتظلّمُ خلال 15 يوماً (§2، البند 7) |
| المقيِّم | `evaluator` واحد | رئيسيٌّ + متعدّدون بأوزان | توقيعُ مدير/ة المدرسة؛ من يُدخل الدرجات غيرُ محدَّد نصّاً (§2) |
| الجزاءات التأديبيّة | لا | لا — وقيدُ المادتين 17/18 في مسار الحفظ منذ `7d04249c` | جدولٌ في كلّ استمارة + المادتان 17 و18 (§2.1) |
| الدورات التدريبيّة | لا | لا | جدولٌ في كلّ استمارة + قيدا التدريب (§2.1) |

## 2. القرار المقترح

**`quality.EmployeeEvaluation` هو النموذجُ الواحد، و`operations.StaffEvaluation` يُسحب.**

المسوّغ:

1. هو النموذجُ الوحيد الذي يُكتب. الآخرُ لا مسارَ يكتبه، فلا عملَ يُفقد بسحبه.
2. بنيتُه تحمل الاستمارات: قالبٌ لكلّ دورٍ بمحاورَ موزونة. والبذرُ في هذه الموجة يملؤه
   (21 دوراً، 190 محوراً) من ملفّ بياناتٍ يُقارَن بالمرجع خانةً بخانة
   (`quality/ministry_appraisal_forms.json`، `tests/test_ministry_appraisal_forms.py`).
   ومعاييرُ `StaffEvaluation` الخمسة تدريسيّةٌ لا تُطابق أيَّ استمارة.
3. قيدُ الجزاء صار في مسار حفظه (`quality/evaluation_services.py`)، فالربطُ بسجلّ
   الجزاءات (2.1) نقطةٌ واحدة.

## 3. البدائل المدروسة

| البديل | لماذا لا |
|---|---|
| إبقاؤهما | شؤونُ الموظّفين تبقى تعرض صفراً من نموذجٍ ميّت، وكلُّ ربطٍ لاحق (الجزاءات، التدريب، التظلّم) يُكتب مرّتين أو يُنسى في أحدهما |
| `StaffEvaluation` هو الواحد | يحتاج إعادةَ بناء القوالب والمقيِّمين المتعدّدين والدورات والشاشات الأربع التي في `quality` — أي كتابةَ `EmployeeEvaluation` من جديد في تطبيقٍ آخر |
| نموذجٌ ثالثٌ جديد | هجرتان بدل واحدة، والبنيةُ القائمة في `quality` تكفي بعد البذر |

## 4. النتائج والمقايضات

- يُعاد توجيهُ القراءتين في `staff_affairs/services.py` (`:83` و`:180`) إلى
  `EmployeeEvaluation`. هذا الملفُّ خارج نطاق هذه الموجة (مالكُه وكيلُ شؤون الموظّفين).
- ثمّ هجرةُ حذفٍ لـ`StaffEvaluation`، مشروطةٌ بصفرٍ في الإنتاج (1.3). وإن لم يكن صفراً
  فهجرةُ بياناتٍ أوّلاً — ولا تحويلَ آليّاً ممكن: خمسةُ معاييرَ من 5 لا تقابل مجالاتِ أيّ
  استمارة، فالصفوفُ تُحفظ أرشيفاً للقراءة لا تُحوَّل.
- `core/models/audit.py:58` يبقى خيارَ تدقيقٍ تاريخيّاً ما دامت سجلّاتٌ قديمةٌ تحمله.

## 5. ما نُفّذ في هذه الموجة (البند 1.2)

| | الموضع | الدليل |
|---|---|---|
| بذرُ الاستمارات السبع لكلّ دورٍ تسمّيه | `seed_quality_templates`، `quality/appraisal_seed.py` | `--apply` مرّتين: 27/241 ثمّ 27/241 (بقوالب الجولة الأولى الستّة اليتيمة)، و`--prune-orphans`: 21/190 |
| الشاشةُ تقرأ ما بُذر | `_get_axes_for_employee` | `test_evaluation_screen_reads_the_seeded_axes` |
| درجاتُ القالب تُحفظ | `save_evaluation` ← `EvaluationScore.custom_axes` | `test_view_saves_ministry_axes_instead_of_dropping_them` |
| قيدُ المادتين 17/18 | `has_active_sanction` (False — يُربط بـ2.1) | `test_view_rejects_excellent_for_sanctioned_teacher` |

ولم يُمسّ أيُّ نموذجٍ بالحذف أو الدمج.

## 6. قراراتٌ للمالك

1. **الدمج:** قبولُ القسم 2، بعد لصق عدّ الإنتاج في 1.3.
2. **سُلَّم التقدير:** `EmployeeEvaluation.RATINGS` أربعُ درجاتٍ بعتبات 90/75/60، والوزارةُ
   خمسٌ بعتبات 90/76/66/50 (§2.2). فمجموعُ 75 «جيد جداً» في المنصّة و«جيد» في الاستمارة —
   وعلى الحدّ نفسِه يعمل قيدُ الجزاء. تغييرُه يمسّ `choices` وصفوفاً قائمة، فهو قرار.
3. **الدوريّة:** الاستماراتُ سنويّة، والمنصّةُ تقيّم فصلين (S1/S2).
4. **فئاتٌ بلا استمارة:** أدوارٌ في `Role.ROLES` لا تسمّيها أيُّ استمارةٍ نصّاً فبقيت على
   المحاور الافتراضيّة — `principal`، `ese_teacher`، `coordinator`، `activities_coordinator`،
   `speech_therapist`، `occupational_therapist`، `nurse`، `librarian`، `bus_supervisor`،
   `transport_officer`، `admin`، `specialist`. وخاناتٌ في رؤوس الاستمارات لا دورَ لها في
   المنصّة — «نائب المدير لشؤون الروضة»، «مسؤول الإرشاد والتوجيه»، «منسّق شؤون الطلاب»،
   «اخصائي قياس سمع»، «الأخصائي العلاجي»، «اخصائي لغة إشارة»، «مسؤول مركز مصادر التعلم»،
   «اخصائي أنشطة مدرسية»، «مهندس مختبرات العلوم والتكنولوجيا». الأقربُ مثل
   `librarian`↔«مسؤول مركز مصادر التعلم» و`ese_teacher`↔«المعلم» لم يُربط تخميناً.
5. **المؤشّراتُ الفرعيّة:** محفوظةٌ في ملفّ البيانات ومقارَنة، ولا تُبذر — `EvaluationAxis` بلا
   مستوىً فرعيّ. واستمارةُ المعلّم تحمل تعارضاً مطبوعاً (§2.4: مجموعُ مؤشّرات أربعة مجالاتٍ
   لا يساوي وزنَها) نُقل كما هو.
