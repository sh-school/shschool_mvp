# حارسُ الثوابت: خصوصيّةُ الصور المرفوعة (PDPPL)

> صفٌّ من جدول «ج. حرّاسُ الثوابت» — مقطعٌ من `docs/governance/regression_guards.md` (الفهرس)؛ النصُّ منقولٌ حرفيّاً (W-20261020-018).

| المجال | الحرّاس | ما يفرضونه |
|---|---|---|
| **خصوصيّةُ الصور المرفوعة (PDPPL)** | `test_uploads_are_photo_cleaned`، `test_tardiness_excuse_photo_privacy`، `test_staff_exception_evidence_privacy`، `test_quality_evidence_privacy` | كلُّ دالّةٍ تقرأ `request.FILES` تمرّ بـ`core.photo_privacy.clean_photo` (يمحو EXIF/GPS ويصغّر) أو مسمّاةٌ بسببها؛ والنماذجُ التي لا تقبل صورةً أصلاً (`DOCUMENTS_ONLY`) يثبت الحارسُ رفضَها لكلّ امتدادٍ صوريّ؛ والديونُ المعلَنة (`KNOWN_UNCLEANED`) لا تزيد وتُحذف حين تُنظَّف (فارغةٌ اليوم)؛ وإذنُ التأخّر ومرفقُ استثناء الموظّف ودليلُ الإجراء يُحفظون نظيفين ومُتحقَّقاً منهم بالبايتات؛ ودليلُ الإجراء يُفحص في `QualityService` لا في كلّ view (`quality/evidence_files.py`: مستندٌ أو صورةٌ حتى 10MB، والحكمُ بالمحتوى) |
