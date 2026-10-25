# التشغيل الظلّيّ لـV2 — وصفة المالك لقياس الزمن (W-20261003-018، قرار D-318م)

يشغّل V2 وحدَه على مدخلات المدرسة الحاليّة ويقارن ناتجَه بالجدول المعتمَد بمؤشّرات W-20261010-008 (IND-02/04/08/13/16 وعدد الحصص المتغيّرة) ويقيس الزمن. **لا ينشر، ولا يترك حصّةً أو صفَّ توليدٍ في القاعدة، ولا يمسّ الجدول الحيّ المعتمَد** (الخطّ الأحمر D-381م): الحصصُ تُكتب داخل معاملةٍ تُتراجَع دائماً لتقيسها أداةُ المقارنة.

## الإذن

لا يعمل إلّا بقول المالك: المتغيّر `SCHEDULE_SHADOW_ALLOWED=1` في بيئة الويب والعامل معاً. غيابُه يرفض الطلبَ والمهمّةَ. ولا جدولةَ دوريّةَ له (لا يوجد في `CELERY_BEAT_SCHEDULE`).

## الطلب (يدويّ)

```bash
python manage.py shell -c "from core.models import School; from operations.scheduler_v2.tasks import request_shadow_run; print(request_shadow_run(School.objects.get(code='<رمز المدرسة>')))"
```

الطلبُ idempotent بالساعة لكلّ مدرسة. ويقبل `seed=` و`workers=` و`max_seconds=`؛ والافتراضيّ 1800ث. وللمهمّة حدٌّ ليّن 3600ث وحدٌّ صلب 3660ث (`limits.py`).

## النتيجة

ملفُّ JSON في التخزين الافتراضيّ بمفتاح `schedule_shadow/<معرّف المدرسة>/<معرّف التشغيل>.json`، قيمٌ فقط بلا أسماء (PDPPL). قراءتُه:

```bash
python manage.py shell -c "from operations.scheduler_v2.tasks import read_shadow_report; import json; print(json.dumps(read_shadow_report('<معرّف المدرسة>', '<معرّف التشغيل>'), ensure_ascii=False, indent=1))"
```

أهمّ حقوله: `state` (ok / infeasible / timeout / rejected / busy / soft_time_limit)، و`elapsed_seconds` (الزمن الجداريّ الكامل) و`solver_seconds` (زمن الحلّال) و`environment` (اسم بيئة Railway) و`comparison` (المؤشّراتُ الخمسة للمعتمَد والمسودّة والفرق).

## معنى الرقم المقيس

`elapsed_seconds` هو ما يلزم ليكتمل التوليدُ على عتاد Railway بعدد العمّال المضبوط؛ فإن بلغ `max_seconds` فالحلّال قُطع بالمهلة ولم يُثبت الأمثليّة (الحالة FEASIBLE لا OPTIMAL). يُسجَّل الرقمُ ومعناه للمالك قبل أيّ قرار ترقية.
