# الطبقاتُ المُلزِمة

العرضُ يستقبل الطلبَ ويردّ. القراءةُ في `selectors.py`، والكتابةُ في `services.py`،
وقواعدُ المجال التي لا تعرف قاعدةَ البيانات في `core/domain/`. وحارسٌ يعدّ ويمنع
الزيادة: `tests/layering_ratchet.py`.

## ما يجوز في العرض

- قراءةُ الطلب: `request.GET`، `request.POST`، `request.FILES`، `request.school`.
- الحراسة: المزيِّنات، و`get_object_or_404` على نموذجٍ أو QuerySet من selector (ويُعدّ
  استدعاءَ ORM كغيره).
- تركيبُ السياق: أسماءُ مفاتيح القالب، ونصوصُ البطاقات وألوانُها (`tone_for`، `_share_tone`).
- استدعاءُ selector أو service أو دالّةِ مجال — ثمّ `render` أو `redirect` أو ملفّ.

وما سوى ذلك يخرج: عرضٌ فوق **60 سطراً** أو **5 استدعاءات ORM** مباشرة يُسجَّل
ولا يزيد.

## selectors — القراءة

دوالُّ بلا أثرٍ جانبيّ، تأخذ مدرسةً وعاماً ويوماً (لا `request`) وتُرجع QuerySet أو
قاموساً أو عدداً. تُختبر بلا طلبٍ ولا قالب. أمثلة:

| الملفّ | ما فيه |
|---|---|
| `student_affairs/selectors.py` | سجلُّ الطلبة بفرزه وفلاتره، ملفُّ الطالب ووثيقتُه، ملخّصُ السلوك، التأخّرُ الصباحيّ |
| `operations/selectors.py` | عدّاداتُ الحضور، تنبيهاتُ الغياب المعلّقة، حصصُ المعلّم والشعبة، طلباتُ التبديل |
| `core/dashboard_selectors.py` | عدّاداتُ لوحة التحكم لكلّ دور (نتائج، سلوك، عيادة، مكتبة، حسابات) |
| `analytics/selectors.py` | مؤشّراتُ لوحة الإحصاءات الستّةَ عشر |

قراءةٌ تشترك فيها شاشتان تُكتب في تطبيقها مرّةً (`operations.selectors.attendance_status_counts`
تقرؤها لوحةُ التحكم وشؤونُ الطلبة) — لا نسخةَ في كلّ تطبيق.

## services — الكتابة

`@transaction.atomic`، وتُرجع نتيجةً صريحة (الكائنَ المكتوب، أو `None` حين لا شيءَ
يُكتب)، وسجلُّ التدقيق في المعاملة نفسِها. مثال: `TardinessService.record_morning_tardiness`.
والتحقّقُ من المُدخَل (نوعُ الملفّ وحجمُه) في العرض أو النموذج قبل الخدمة.

## core/domain — القواعد

نسبةُ الحضور (`attendance_rate`، `percent`)، وشرائحُ الدرجات، وسلالمُ الألوان. لا ORM،
ولا تُعاد كتابتُها في selector: `round(x / y * 100)` في موضعٍ و`x * 100 / y` في آخر
يختلفان عند الأنصاف.

## الحارس

`tests/layering_ratchet.py` يعدّ بشجرة `ast` (التعليقُ والنصُّ لا يُعدّان) ثلاثةَ أشياء:

1. **كلُّ دالّةٍ في ملفّ عروض** — `views.py` و`views_*.py` و`*_views.py` و`views/*.py`؛
   العرضُ ومساعدُه وتوابعُ أصنافه: الأسطرُ من `def` إلى آخرها، واستدعاءاتُ ORM. والمعدود:
   - الوصولُ إلى `.objects`؛
   - توابعُ QuerySet التي لا يملكها غيرُه، أينما وقعت ولو على مديرٍ مرتبط
     (`student.enrollments.exclude(`): `filter` `exclude` `annotate` `aggregate` `all`
     `order_by` `values_list` `distinct` `only` `defer` `select_related` `prefetch_related`
     `select_for_update` `get_or_create` `update_or_create` `bulk_create` `bulk_update` `in_bulk`؛
   - `get_object_or_404(` و`get_list_or_404(` و`Q(` — وأسماءُ `Q` المستعارة (`import Q as W`)؛
   - توابعُ يشاركها القاموسُ والطلب — `get` `update` `create` `save` `delete` `values`
     `count` `exists` `first` `last` `earliest` `latest` `iterator` — حين يكون مستقبِلُها
     من ORM: سلسلةً فيها ما سبق، أو اسماً أُسند منها في الدالّة (`m = X.objects` ثمّ
     `m.get(`؛ `t = get_object_or_404(…)` ثمّ `t.save()`؛ `obj, created = …get_or_create()`؛
     حلقةٌ ومُولِّدٌ و`:=`)، أو بناءَ نموذجٍ مستورَدٍ من `models` (`cover = WingCoverage(…)`
     ثمّ `cover.save()`)، أو `request.user`، أو `form.save()` من مصنّفٍ مستورَدٍ من `forms`
     (و`commit=False` لا تُعدّ). و`request.GET.get(` و`ctx.update(` وقاموسُ `aggregate(` لا تُعدّ؛
   - المديرُ المرتبطُ على نسخةٍ لا يُعرف نوعُها: `photo_set.`، وما لا نظيرَ له في القاموس على
     صفةِ نسخة (`student.enrollments.first()`، `.create(`، `.exists()`)، وما لا يقبله القاموسُ
     بوسائطه (`.get(pk=1)`، `.count()`، `.values("a")`) — إلّا ما جذرُه `request` أو `os` أو
     `settings`… وما مرّ بقاموسٍ معروف (`cleaned_data`، `GET`، `session`، `kwargs`…).

   **والعرضُ يُحمَّل استعلاماتِ مساعديه**: كلَّ دالّةٍ يبلغها في ملفّات العروض — في ملفّه
   أو مستورَدةً من ملفّ عروضٍ آخر — مرّةً واحدة. فتقسيمُ عرضٍ بخمسةٍ وعشرين استدعاءً على
   `_part1…_part5` لا يُنقصه؛ ونقلُها إلى `selectors.py` هو ما يُنقصه.

   ما فوق السقف وحده يُسجَّل.
2. **`get_school()` في ملفّات العروض** — كلُّها لا ما في العروض وحدها: كلُّ إشارةٍ إليه
   (مستدعاةً، ومستعارةً `g = user.get_school`، و`getattr(user, "get_school")`)، وكلُّ
   استدعاءٍ لغلافٍ يُرجعه — `_get_school(request)` في الملفّ، أو `school_of(request)`
   مستورَداً من وحدةٍ في المشروع.
3. **استيرادُ `core` لوحدةٍ نازلة** — ولو كسولاً داخل دالّة، ولو بنصّ (`__import__("x")`،
   `import_module`، `import_string`، `apps.get_model("app", …)`) — معدوداً لكلّ تطبيقٍ على
   النواة كلِّها.

والسجلُّ `tests/layering_baseline.json`: **زاد** → يسقط `tests/test_layering.py`؛
**نقص** → يسقط كذلك حتى يُثبَّت؛ عرضٌ جديدٌ فوق السقف يسقط.

```bash
python -m tests.layering_ratchet             # الفحص
python -m tests.layering_ratchet --update     # تثبيتُ ما نقص — وما زاد يبقى على قيمته ويُسمّى
python -m tests.layering_ratchet --accept "<الموضع>" --reason "<لماذا>"  # زيادةٌ كُتبت بلا الحارس
python -m tests.layering_ratchet --rebaseline # حين يتغيّر تعريفُ العدّ نفسُه — يُراجَع سطراً سطراً
```

### الفروعُ التي أساسُها قبل الحارس

فرعٌ بدأ قبل `tests/test_layering.py` يمرّ في CI وحدَه، ويسقط بعد دمجه مع ما فيه الحارس:
زاد عرضاً مسجَّلاً (يُسقط الفحصَ الأوّل)، أو رحّل عرضاً (يُسقط الثاني حتى يُثبَّت). والمخرج:

1. `--update` يُثبّت كلَّ نقص ولو زاد بندٌ آخر — كان يرفض السجلَّ كلَّه فيحبس النقصَ وراء الزيادة.
2. ما زاد: يُرحَّل، أو يُقبل **باسمه** بـ`--accept` وسببٍ لا يقلّ عن عشرين حرفاً. يُرفع البندُ
   وحدَه، ويُكتب في `accepted` الموضعُ والمقياسُ والقيمتان والسبب، فيراه المراجعُ في طلب الدمج.
   و`--accept` يرفض ما لم يزد. أمّا `--rebaseline` فلتغيّر تعريف العدّ وحدَه: يُعيد القياسَ كلَّه
   فتذوب الزيادةُ بين مئةِ بند.

## الأرقام

| الموضع | عروضٌ فوق سقف | فوق الأسطر | فوق ORM | `get_school()` | استيرادٌ نازلٌ في core |
|---|---|---|---|---|---|
| قبل الترحيل (تعريف 1: ما أوّلُ وسائطه `request`) | 82 | 52 | 62 | 146 | 61 جملةً / 14 ملفّاً |
| بعد شؤون الطلبة | 67 | 38 | 49 | 146 | 61 / 14 |
| تعريف 2 (كلُّ دالّة) — الشيفرةُ نفسُها | 79 | 40 | 60 | 146 | 61 / 14 |
| بعد لوحة التحكم والإحصاءات و`request.school` | 70 | 38 | 51 | 77 | 61 / 15 |
| دمج main حتّى #284 (`wings` تحت الحارس) | 70 | 38 | 51 | 77 | 61 / 15 |
| تعريف 3 (`*_views.py`، والكتابةُ والمستعار) — الشيفرةُ نفسُها | 120 | 42 | 106 | 88 | 61 / 15 |
| تعريف 4 (المديرُ المرتبطُ ونسخُ النماذج، ومساعدو العرض، وأغلفةُ `get_school`، والاستيرادُ بنصّ) — الشيفرةُ نفسُها | 162 | 42 | 154 | 105 | 62 / 16 |

- **شؤون الطلبة**: 17 عرضاً فوق السقف → 2. رُحِّل خمسةَ عشرَ (الاثنا عشرَ الأثقلُ وثلاثةٌ
  تشاركها قراءاتِها)، وبقي `student_add` و`student_edit` فوق الأسطر وحدها (82 و76) —
  كتابتُهما في `StudentService` أصلاً.
- **لوحة التحكم**: ثمانيةُ مساعدات (`_get_director_ctx` 113 سطراً و46 استدعاءً …) → 0.
- **الإحصاءات**: `analytics_dashboard` (89 سطراً، 31 استدعاءً) → 0.
- **`request.school`** في `analytics`، `operations/views_swap`، `reports`، `exam_control`،
  `wings`، `operations/views_attendance`، `parents` (69 موضعاً). والسلوكُ واحد: الوسيطُ
  يضع `user.get_school()` للمسجَّل و`None` لغيره، وكلُّ هذه العروض خلف `login_required`.
- الملفُّ الخامسَ عشرَ في core هو `core/dashboard_selectors.py`: انتقلت إليه استيراداتُ
  اللوحة من العرض، فالجُملُ 61 كما هي.

## الباقي

- `quality/views.py` — 12 `get_school()` (يملكه وكيلُ الامتثال H).
- `staff_affairs/views.py` — `staff_list` و`staff_profile` فوق السقف لم تُرحَّلا (يعدّله وكيلُ الامتثال G).
- 162 دالّةً فوق السقف في بقيّة التطبيقات، و105 `get_school()`؛ والسجلُّ يسمّيها. والتعريفُ
  الرابع حمّل العروضَ استعلاماتِ مساعديها (`academic_management/assignment_views.py` كلُّه
  يمرّ بـ`_render_card` — 26 استدعاءً)، وعدّ غلافَي `_get_school` في
  `academic_management/views.py` (1 → 6) و`_school` في `api/views.py` (4 → 16)، و`__import__`
  في `core/querysets.py` (`core → operations` 16 → 17). والتعريفُ
  الثالث أدخل أربعةَ ملفّات (`academic_management/assignment_views.py`،
  `operations/api_views.py`، `quality/evaluation_views.py`، `quality/observation_views.py`:
  أحدَ عشرَ `get_school()`) وعروضَ الكتابة كـ`student_affairs/views.py::transfer_review` (8).
- الاستيرادُ النازلُ في core (61 جملة): لوحةُ التحكم تقرأ من التطبيقات بطبيعتها؛
  وإخراجُه يحتاج سجلَّ مزوّدين يُملأ من `apps.ready()` — لم يُبدأ.
- `behavior/views.py::_behaviour_year_window` تكرارٌ لـ`student_affairs.selectors.behaviour_window`.
