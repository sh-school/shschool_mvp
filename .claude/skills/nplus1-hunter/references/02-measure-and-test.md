# القياسُ والاختبار وحدودُ الفاحص

متى تقرأ هذا الملف: حين تكتب اختبارَ الثبات لصفحةٍ أو نقطة، أو تقيس دالّةً يدويّاً، أو تقرأ مخرجَ `nplus1_scan.py` وتريد أن تعرف ما يُصدَّق منه.

## اختبارُ الثبات — نمطُ المشروع
المرجع: `tests/test_n_plus_one_queries.py::assert_flat` و`tests/test_admin_changelist_queries.py`. الفكرة: لا رقمَ مطلق، بل مقارنةٌ بعد إحماء.

```python
import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

pytestmark = pytest.mark.django_db


def _count(client, url):
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200, url
    return ctx.captured_queries


def test_class_list_is_flat(school, principal_user):
    client = Client()
    client.force_login(principal_user)          # جلسة: الوسيطُ يفحصها قبل DRF
    make_class(school)                           # مساعدٌ تكتبه بمصانع tests/conftest.py
    client.get(URL)                              # إحماء: ما يُحمَّل كسولاً مرّةً
    one = _count(client, URL)
    make_class(school); make_class(school)
    three = _count(client, URL)
    assert len(three) == len(one), [q["sql"] for q in three if q not in one]
```
- المكان: `tests/` في الجذر — هناك `tests/conftest.py` بمصانعه (`SchoolFactory`، `UserFactory`، `ClassGroupFactory`…) وfixtures الأدوار (`teacher_user`، `principal_user`، `student_user`…). اختبارٌ في `<app>/tests/` لا يراها.
- الاختبارُ يجب أن **يسقط قبل الإصلاح** — اكتبه أوّلاً وسجّل عدديه في تعليقه كما في الملفّ المرجع.
- حين يستحيل التساوي التامّ (تخزينٌ مؤقّتٌ يتغيّر بعدد الصفوف) فالسماحُ صغيرٌ ومبرَّر: `many <= few + 2` في اختبار قوائم الإدارة.
- الإعداد: `DJANGO_SETTINGS_MODULE=shschool.settings.testing` (`pyproject.toml`)، والتشغيلُ بأمر الاختبار في `CLAUDE.md` داخل حاوية الجلسة.

## قياسٌ يدويّ لدالّةٍ أو selector
داخل حاوية الجلسة (`$DC` كما في مهارة schoolos-migration-guard، `references/03-parallel-sessions.md`):
```bash
$DC python manage.py shell -c "
from django.db import connection
from django.test.utils import CaptureQueriesContext
from reports.selectors import <دالّتك>
with CaptureQueriesContext(connection) as ctx:
    list(<دالّتك>(...))
print(len(ctx.captured_queries))"
```
الصفحاتُ الكاملة تُقاس بالاختبار لا بالـshell: الوسائطُ والجلسةُ جزءٌ من العدد.
ولا `debug_toolbar`: إعدادُه في `shschool/settings/development.py` مشروطٌ باستيراده، والحزمةُ ليست في `requirements*.txt` ولا في صورة الحاوية (فُحص 2026-09-28).

## الفاحص: ما يرى وما لا يرى
`scripts/nplus1_scan.py` تحليلٌ نصّيٌّ بلا Django:
- **بايثون:** حلقةٌ `for x in …` (و`for i, x in enumerate(…)`) يقرأ جسمُها `x.rel.attr` أو `x.rel.all()/count()/filter()…`، ومصدرُها لا يحوي `select_related`/`prefetch_related`/`annotate`/`values` — ولا المتغيّرُ الذي أُسند إليه في الدالّة نفسِها.
- **قوالب:** `{{ v.a.b }}` داخل `{% for v in … %}`؛ لا يعرف مصدرَ القائمة في الـview، فأكثرُ مرشّحات القوالب يُحسم بقراءة الـview.
- **لا يرى:** الدوالَّ والخصائص (`get_role`، `school`، `__str__` الذي يقرأ علاقة)، ولا المصدرَ المُجهَّز في دالّةٍ أخرى، ولا الـserializers التي تقرأ `source="a.b"`. ابحث عنها يدويّاً: `get_role|get_school|has_role|\.school\b` داخل الحلقات.
- المجلّداتُ المستثناة: `tests`، `migrations`، `staticfiles`، `docs`، `AAdocs`، `staging`… نسبةً إلى جذر الشجرة (الإصدارُ السابق كان يستثنيها في المسار المطلق فلا يجد شيئاً داخل `.claude/worktrees/`).
- حجمُ المخرج على main (2026-09-28): 60 مرشّحاً في بايثون (كان 135 مع التكرار والإيجابيّات الكاذبة) و575 في القوالب. فابدأ بالملفّ الذي تعدّله (`--path`) لا بالمستودع كلّه.

## أنماطٌ مضادّة
- `django_assert_num_queries(4)` لصفحةٍ كاملة: يسقط مع كلّ تغييرٍ في الوسائط أو القالب، فيُرفع الرقمُ بلا تفكير.
- اختبارُ ثباتٍ بلا إحماء: الطلبُ الأوّل يحمّل ما يُحمَّل مرّةً فيبدو الفرقُ N+1.
- اختبارٌ يضيف الصفوفَ لمدرسةٍ أخرى أو لعامٍ آخر فلا تظهر في الصفحة — العددان متساويان لأنّ الصفوف لم تُعرض.
- قراءةُ «لا مرشّحات» من الفاحص براءةً للصفحة.
