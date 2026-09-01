"""[SCHEDULE] صفحتا التوليد والإعدادات تفتحان — وهذا وحدَه لم يكن مضموناً.

كانت `/teacher/smart-schedule/` تسقط بـ500 على كلّ زائر، لأنّ
`CapacityCheckService.get_overcapacity_classes` يستورد `_grade_to_level` من
المولّد وقد حُذف منه حين صُحّح اشتقاقُ المرحلة هناك. فبقي استيرادٌ معلّقٌ في
موضعٍ آخر، وأسقط **الصفحةَ كلَّها** لا الفحصَ الذي يخصّه.

ولم يكن في المستودع اختبارٌ واحدٌ يفتح هذه الصفحة، فمرّ العطبُ صامتاً حتّى
ضغط عليها مستخدمٌ. وهذا ما تحرسه هذه الاختبارات: أن تُفتح.
"""

import pytest
from django.urls import reverse

from operations.services import CapacityCheckService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


@pytest.fixture
def principal(school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def teacher(school):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلّمٌ")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def teachers_pool(school):
    role = RoleFactory(school=school, name="teacher")
    out = []
    for index in range(2):
        user = UserFactory(full_name=f"معلّم {index}")
        MembershipFactory(user=user, school=school, role=role)
        out.append(user)
    return out


@pytest.fixture
def subject(school):
    from operations.models import Subject

    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


def assign(school, teacher, subject, *, periods, grade="G7", level="prep"):
    from operations.models import SubjectClassAssignment

    group = ClassGroupFactory(school=school, grade=grade, level_type=level, academic_year=YEAR)
    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=periods,
        is_active=True,
    )


def test_the_generation_page_opens(client_as, principal, school, teacher, subject):
    assign(school, teacher, subject, periods=6)

    response = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}")

    assert response.status_code == 200


def test_the_settings_page_opens(client_as, principal):
    assert client_as(principal).get(reverse("schedule_settings")).status_code == 200


# ── الاعتمادُ يُشعر، ولا يقع نصفَ فعل ────────────────────────────────


def test_approving_notifies_the_teachers_with_their_school_on_the_row(
    client_as, principal, school, teacher, subject
):
    """`school` لازمٌ لا زينة: الإشعارُ صفٌّ مستأجِرٌ ترفضه RLS بلا مدرسة."""
    from notifications.models import InAppNotification
    from operations.models import ScheduleGeneration

    assign(school, teacher, subject, periods=6)
    gen = ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="draft", total_slots_created=6
    )

    response = client_as(principal).post(
        reverse("approve_schedule", args=[gen.pk]), follow=True
    )

    assert response.status_code == 200
    gen.refresh_from_db()
    assert gen.status == "approved"
    rows = InAppNotification.objects.filter(school=school)
    assert rows.count() >= 1
    assert all(r.school_id == school.id for r in rows), "لا صفَّ بلا مدرسة"


def test_an_already_approved_generation_is_refused_politely(client_as, principal, school):
    from operations.models import ScheduleGeneration

    gen = ScheduleGeneration.objects.create(
        school=school, academic_year=YEAR, status="approved", total_slots_created=6
    )

    response = client_as(principal).post(
        reverse("approve_schedule", args=[gen.pk]), follow=True
    )

    assert response.status_code == 200
    assert "ليس مسودة" in response.content.decode()


# ── الرسالةُ تقول ما وقع ─────────────────────────────────────────────


def test_the_message_reports_what_was_actually_placed(client_as, principal, school, teachers_pool):
    """كانت تقول «0/0 حصة» على جدولٍ وُلِّد — لأنّها تقرأ مفاتيحَ لا يُرجعها المحرّك."""
    from operations.models import SubjectClassAssignment

    groups = [
        ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
        for _ in range(2)
    ]
    from operations.models import Subject

    subjects = [
        Subject.objects.create(school=school, name_ar=f"مادّة {i}", code=f"X{i}") for i in range(2)
    ]
    for group in groups:
        for t, subj in zip(teachers_pool, subjects, strict=True):
            SubjectClassAssignment.objects.create(
                school=school,
                academic_year=YEAR,
                teacher=t,
                class_group=group,
                subject=subj,
                weekly_periods=3,
                is_active=True,
            )

    response = client_as(principal).post(
        reverse("smart_generate"), {"year": YEAR}, follow=True
    )
    body = response.content.decode()

    assert "0/0" not in body, "لا رقمَ يصف ما لم يقع"
    assert "12/12" in body and "100.0%" in body
    assert "م1:" not in body, "ولا ذكرَ لمراحلَ لا وجودَ لها"


# ── فحصُ الطاقة نفسُه ────────────────────────────────────────────────


def test_a_class_within_its_week_is_not_flagged(school, teacher, subject):
    """إعداديّ: أربعةُ أيّامٍ بسبعٍ + خميسٌ بستّ = أربعٌ وثلاثون."""
    row = assign(school, teacher, subject, periods=34, level="prep")

    assert CapacityCheckService.get_overcapacity_classes([row]) == []


def test_a_class_beyond_its_week_is_flagged_with_the_overflow(school, teacher, subject):
    row = assign(school, teacher, subject, periods=36, level="prep")

    [flagged] = CapacityCheckService.get_overcapacity_classes([row])

    assert (flagged["demand"], flagged["capacity"], flagged["overflow"]) == (36, 34, 2)
    assert flagged["class_name"] == str(row.class_group), "التحذيرُ يُسمّي شعبتَه"


def test_a_secondary_class_keeps_its_seventh_thursday_period(school, teacher, subject):
    """الخميسُ سبعٌ للثانويّ — والطاقةُ خمسٌ وثلاثون لا أربعٌ وثلاثون.

    ولو اشتُقّت المرحلةُ من `grade` نصّاً لخرجت فارغةً، فأُخذ الخميسُ بالأضيق
    وضاق الجدولُ من حيث لا يُرى.
    """
    row = assign(school, teacher, subject, periods=35, grade="G10", level="sec")

    assert CapacityCheckService.get_overcapacity_classes([row]) == []
