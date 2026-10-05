# دليل المعلّم — الإصدار 0.1 (نسخةٌ مؤقّتة على الوضع الحاليّ)

على غرار «دليل مشرف الجناح». الناتج: `teacher_guide_v0.1.pdf` (21 صفحة). كلُّ ما فيه مأخوذٌ من شيفرة المنصّة، والصورُ من بيئةٍ تجريبيّةٍ **ببياناتٍ مستعارةٍ كلِّها**.

## إعادة البناء

1. قاعدةٌ فارغةٌ مهجَّرة (لا الإنتاج ولا قاعدة جلسة)، ثمّ بذرُ البيانات المستعارة: `seed_demo.py` (الدخول: الرقمُ الوظيفيّ `70001`).
2. الخادمُ بساعةٍ مثبَّتةٍ على الإثنين 2026-10-05 الساعة 09:20 كي تقع الحصّةُ داخلَ نافذة الإدخال: `python docs/guides/teacher_guide_v0_1/run_demo_server.py 8765` (مع `TWO_FACTOR_REQUIRED_FOR_STAFF=False`).
3. اللقطاتُ المرقَّمة: `python docs/guides/teacher_guide_v0_1/annotate_shots.py` ← `shots/*.png`.
4. الدليل: `cd docs/guides/teacher_guide_v0_1 && python build_guide.py` ← PDF (WeasyPrint، خطُّ Tajawal من `static/fonts`).

المحتوى كلُّه في `content.py`؛ وحدودُ النسخة ومواضعُ التأكيد في قسمه الأخير.
