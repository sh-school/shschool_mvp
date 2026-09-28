# 02 — نظامُ التقييم ومحرّكُ الحكم

> متى تقرأ هذا الملف: قبل أيّ عملٍ على الدرجات أو الباقات أو النتائج أو الشهادات أو كشوف الرصد أو إحصاءات النجاح والرسوب.
> الأرقامُ هنا منقولةٌ من `core/domain/grades.py` على `main@81bc4937`؛ **الثابتُ في الشيفرة هو المرجع**، ونصُّ اللائحة عند مهارة schoolos-source-of-truth.

## البنية (القرار الوزاريّ 14/2018، المادّة 3)
الفصلُ الأوّل من 40 والثاني من 60، ومجموعُ السنة 100 — لكلّ الصفوف بما فيها الثاني عشر (تصحيحُ 2026-09-10: القرارُ ألغى 50/50 القديمة). المصدر: `core/domain/grades.py`، `AAdocs/ministry_data/2026_2027/remediation_plan.md` (البند 0.1).

| الباقة | المعنى | الصفوف 7–11: الدرجة (الوزن من الفصل) | الصفّ 12 |
|---|---|---|---|
| `P1` | منتصف ف1 | 15 من 40 (37.50%) | غير موجودة |
| `AW` (S1) | أعمال ف1 | 5 من 40 (12.50%) | غير موجودة |
| `P2` | نهاية ف1 | 20 من 40 (50.00%) | 40 من 40 (100%) |
| `P3` | منتصف ف2 | 15 من 60 (25.00%) | غير موجودة |
| `AW` (S2) | أعمال ف2 | 5 من 60 (8.33%) | غير موجودة |
| `P4` | نهاية ف2 | 40 من 60 (66.67%) | 60 من 60 (100%) |

- الباقةُ الغائبةُ في بنية الصفّ **غيرُ موجودة** (`None`) لا وزنُها صفر — فلا تُنشأ باقةٌ بوزنٍ صفريٍّ تظهر عموداً فارغاً. الدوالّ: `package_weights(grade, semester)`، `package_weight`، `package_out_of`، `semester_columns` (ترتيبُ أعمدة الكشف: منتصف · أعمال · نهاية).
- **الحسابُ بالكسر الدقيق** `exact_package_weight()` (2/3×100 لا 66.67) ومن درجات القرار — لا من `AssessmentPackage.weight` المخزَّن، فذاك للعرض (تصحيح 2026-09-16: التوزيعُ لقطاع التقييم لا للمدرسة، م5).
- `ClassGroup.grade` نصٌّ `"G7"…"G12"`؛ الرقمُ بـ`core.models.academic.grade_number()`.
- **الثاني عشر:** الشيفرةُ فيها فرعٌ كاملٌ له (`FINAL_GRADE = 12`، `PACKAGE_WEIGHTS_GRADE12`، `g12` في `judge_student`)، بينما ذاكرةُ `project_grade12_ministry_exams.md` (2026-09-19) تقول إنّ درجاته وزاريّةٌ لا تُرصد في المنصّة. لا تبنِ رصداً جديداً للثاني عشر قبل تأكيد المالك.

## جبرُ الكسور (م8) وحدُّ النجاح
- **الجبرُ إلى أقرب نصفٍ صعوداً، لا تقريب:** 47.2 ← 47.5، 47.5 تثبت، 47.6 ← 48 (`jabr_fraction`). ويُجبر على القيمة الدقيقة لا بعد قصٍّ إلى 0.01.
- **موضعُه ثلاثُ لحظاتٍ فقط:** منتصفُ الفصل (`P1`/`P3` تُجبر وحدَها)، ونهايةُ الفصل (مجموعُ الباقات الثلاث يُجبر مرّةً)، والدورُ الثاني. لا تجبر `AW` ولا `P2`/`P4` منفردةً. `package_score()` للعرض، و`semester_total()` للمجموع.
- **`PASS_MARK = 50`** من 100 (والمادّةُ التي لها نهايةٌ صغرى 50). ومعه: `MAX_FAILED_FOR_SECOND_ROUND = 3`، وقواعدُ الترفيع الثلاث (م50؛ الثالثة 75% في الباقي و40% في مادّة الرسوب، ويُكتب نصُّها `PROMOTION_RULE_3_ARTICLE` في الشهادة).
- **موادُّ بلا نجاحٍ ورسوب:** الفنونُ للسابع–التاسع، والتربيةُ البدنيّة للثاني عشر، والبرامجُ الإثرائيّة — `default_has_pass_mark(grade, name)`، ويُصرَّح لغيرها بـ`SubjectClassSetup.has_pass_mark`. حالتُها `no_pass_mark` وتُستبعد من العدّ والنسب.
- الدرجةُ الحرفيّة `letter_of()`: A+ ≥95، A ≥90، B+ ≥85، B ≥80، C+ ≥75، C ≥70، D+ ≥65، D ≥50، وما دونها F. وشرائحُ الرسم `band_of()` (90-100 … أقلّ من 50) جدولٌ آخر لا يُخلط بها.

## النماذج (`assessments/models.py`)
- `SubjectClassSetup(school, subject, class_group, teacher, academic_year, has_pass_mark)` — إسنادُ الرصد؛ فريدٌ نشطاً على (مادّة، شعبة، عام).
- `AssessmentPackage(setup, package_type ∈ P1..P4|AW, semester ∈ S1|S2, weight, semester_max_grade)`.
- `Assessment(package, assessment_type, max_grade, weight_in_package, status)` — الأنواع: exam, quiz, homework, project, classwork, oral, practical, participation, `makeup` (ملحقُ ف1 يُرصد في P2 لمن عُذر)؛ الحالة draft → published → graded → closed، و**المسودّةُ لا تُحسب** (`COUNTED_STATUSES` في `verdict_engine.py`).
- `StudentAssessmentGrade(grade, is_absent, is_excused, entered_by)`؛ علاماتُ الاختبار (غائب، معذور، محروم، ملغي، غش) في `MARK_CHOICES`.
- `StudentSubjectResult` — مجموعُ فصل (`p1_score`…`p4_score`، `p_aw_score`، `total`)؛ **لا حكمَ فيه**.
- `AnnualSubjectResult` — `s1_total + s2_total = annual_total`، `status` من `RESULT_STATUS_CHOICES`، و`standing` موقفُ الطالب في موادّه كلّها، و`article` موضعُ الحكم من السياسة، و`letter_grade`.
- `ExamDeprivation` (قرارُ الحرمان — لفريق إدارة سلوك الطلبة لا عدّادُ أيّام) و`ExamMisconduct`.

## الحالاتُ العشر وقراءتُها
`pass` `promoted` · `fail` `second_round` `cancelled` · `excused` `deprived` `makeup` `incomplete` · `no_pass_mark`.
- **لا تكتب `status="pass"` ولا `status="fail"`** في عدٍّ أو فلترة: `core.verdict_read.passing_statuses()` / `failing_statuses()` / `pending_statuses()` / `result_statuses()`. هذه تُرجع المجموعتين القديمتين ما دامت الراية مطفأة، والكاملةَ بعد رفعها، فلا يتغيّر عدٌّ قبل أوانه.
- «ملغي» راسبٌ (قرار 30/2018)، و«مادّةٌ بنيتُها تخالف القرار» تُحكم «غير مكتمل» مع تنبيهٍ لا بالناقص ضدّ الطالب.

## محرّكُ الحكم الواحد
- **الحكم:** `core.domain.grades.judge_student` (نقيٌّ بلا قاعدة)؛ **التطبيق:** `assessments/verdict_engine.py::VerdictEngine` يجمع الوقائع ويحكم ويخزّن ويكتب `AuditLog` بما تغيّر.
- **خلف راية** `settings.VERDICT_ENGINE_ENABLED` (من البيئة، **الافتراضُ مطفأة**)؛ ومطفأةً يبقى `GradeService` (`assessments/services.py`) على حسابه القديم. حالُ الراية في الإنتاج لا يُعرف من الشيفرة.
- `VERDICT_RULESET` إصدارُ قواعد الحكم: يُرفع متى تغيّر ما يُخزَّن لنتيجةٍ لم تتغيّر وقائعُها، فتُعاد نتائجُ الشعبة كلِّها تلقائيّاً مع أوّل مسارٍ يمسّها (`VerdictEngine.recalculate_students`)؛ ولمدرسةٍ كاملة: `python manage.py recalculate_grade_results` (عرض) ثمّ `--apply --actor …`.
- **الأعوامُ المغلقة مجمَّدة:** كتابةُ درجةٍ أو إعادةُ حسابٍ لعامٍ غير الجاري ترفع `ClosedYearError` (`ensure_open_year`).
- مسارُ الحفظ: `GradeService.save_grade` / `save_all_from_post` ثمّ `recalculate_semester_result` / `recalculate_annual_result` / `recalculate_full_class`.

## أنماطٌ مضادّة
- حدُّ نجاحٍ 60 أو أوزانُ «15/5/20/15/5/40 من 100» تُضرب في المجموع مباشرةً — الأوزانُ نسبٌ من درجة الفصل، والحدُّ 50 (انظر «يحتاج تأكيد» في CHANGES عن رقم 60 القديم).
- حكمٌ موازٍ في view أو تقرير (`if total >= 50: "ناجح"`) — كلُّ حكمٍ من `judge_student` المخزَّن.
- تقريبٌ عاديّ (`round`، `ROUND_HALF_UP`) لمجموع فصل — الجبرُ صعوداً إلى نصف.
- إنشاءُ `P1`/`P3`/`AW` بوزن صفر للثاني عشر.
- عدُّ تقييمٍ في حالة `draft`.
