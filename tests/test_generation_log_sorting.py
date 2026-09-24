"""[SORTING] سجلُّ التوليد يُفرَز، ويبدأ تصاعديّاً بتاريخ التوليد ووقته.

عُطّل فرزُه لسببين معاً، ولم يُلحظ حتى طلبه المالك (2026-09-24):

١. المحرّكُ (`static/js/base.js`) لا يفرز أقلَّ من ثلاثة صفوف (`MIN_ROWS`)، وسجلُّ التوليد
   يحمل صفّاً أو صفّين في الأيّام الأولى — فلا تظهر ترويسةٌ تُنقر.
٢. عمودُ التاريخ يُستنتَج عدداً لأنّ «24/09/2026 14:53» يبدأ برقم، فيُفرَز باليوم وحده:
   أغسطس 25 بعد سبتمبر 24. وعمودُ الزمن يخلط «6:14 د» و«25.6 ث».

فالقالبُ يصرّح بقيمة الفرز (طابعٌ زمنيّ، وملّي ثوانٍ)، وبأنّ عمودَ التاريخ هو الافتراضيّ
تصاعداً. والمحرّكُ يفهم ذلك (`data-sort-default`، `data-sort-min-rows`) لكلّ جدول.
وسلوكُه في المتصفّح فُحص فعلاً على صفحةٍ معزولةٍ بصفّين وثلاثة.
"""

from pathlib import Path

import pytest
from django.urls import reverse

from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"
BASE_JS = (Path(__file__).resolve().parent.parent / "static" / "js" / "base.js").read_text(
    encoding="utf-8"
)


def test_the_engine_understands_a_default_column_and_a_smaller_minimum():
    assert "data-sort-default" in BASE_JS, "الترتيبُ الافتراضيّ لعمودٍ صرّح به القالب"
    assert "data-sort-min-rows" in BASE_JS, "جدولٌ بصفّين يُفرَز إن صرّح قالبُه"
    assert "var MIN_ROWS = 3;" in BASE_JS, "الافتراضُ العامّ لسائر الجداول لم يتغيّر"


@pytest.fixture
def principal(school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def assignment(school):
    """الصفحةُ لا ترسم سجلَّ التوليد قبل أن يوجد توزيعٌ واحد."""
    from operations.models import Subject, SubjectClassAssignment

    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّمُ الرياضيات")
    MembershipFactory(user=teacher, school=school, role=role)
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
    group = ClassGroupFactory(school=school, grade="G9", level_type="prep", academic_year=YEAR)
    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=5,
        is_active=True,
    )


@pytest.mark.django_db
def test_the_generation_log_declares_how_it_sorts(client_as, principal, school, assignment):
    from operations.models import ScheduleGeneration

    first = ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="draft", generation_time_ms=190000
    )
    second = ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="approved", generation_time_ms=25600
    )

    body = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}").content.decode()

    assert 'data-sort-min-rows="2"' in body, "صفّان يكفيان لفرزه"
    assert 'data-sort="num" data-sort-first="asc" data-sort-default="asc">التاريخ' in body
    for generation in (first, second):
        stamp = int(generation.generated_at.timestamp())
        assert f'data-sort-value="{stamp}"' in body, "التاريخُ يُفرز بالطابع الزمنيّ لا بنصّه"
    assert (
        'data-sort-value="190000"' in body and 'data-sort-value="25600"' in body
    ), "الزمنُ يُفرز بالملّي ثانية لا بنصٍّ يخلط الدقائقَ والثواني"
