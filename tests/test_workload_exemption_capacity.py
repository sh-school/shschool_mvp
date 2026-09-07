"""[WORKLOAD] التفريغُ يومَ كاملٍ يضغط النصابَ ولا يُخفّفه.

    FullDayExemption → Availability          (متى لا يُجدَّل)
    Reduction        → TeachingTarget        (كم يُدرّس)

فمعلّمٌ في دورةٍ خارجيّةٍ يوم الأحد يبقى نصابُه كما هو، ويُحشر في أربعة أيّام.
ولو خصمنا حصصَ اليوم تلقائيّاً لصار للنصاب مصدرانِ يتنازعانه: قرارُ التخفيض
ورقمٌ مشتقٌّ من الجدول — وهو الخطأُ الذي طردناه من `Allocation`.

ولأنّ الضغطَ لا يُخفّف، لزمت مقابلةٌ لم تكن لازمةً من قبل: **هل تسع الأيّامُ
المتاحةُ الهدفَ أصلاً؟** فبثلاثة تفريغاتٍ يصير ثمانيةَ عشرَ نصاباً مستحيلاً،
ولا يظهر استحالتُه إلّا يومَ يُولَّد الجدولُ فيعجز.
"""

import pytest

from academic_management import workload_workflow as flow
from academic_management.models import FROM_MANUAL
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
SUNDAY = 0
MONDAY = 1
TUESDAY = 2


def actor(school, role_name, name):
    role = RoleFactory(school=school, name=role_name)
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def coordinator(school):
    return actor(school, "coordinator", "منسّق الرياضيات")


@pytest.fixture
def target_teacher(school):
    return actor(school, "teacher", "العرامين")


@pytest.fixture
def subject(school):
    from operations.models import Subject

    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


def exempt(school, teacher, by, *, day=SUNDAY, kind="full_day", period=None, **kw):
    from operations.models import TeacherExemption

    row = TeacherExemption(
        school=school,
        teacher=teacher,
        academic_year=YEAR,
        exemption_type=kind,
        day_of_week=day,
        period_number=period,
        reason=kw.pop("reason", "دورةٌ خارج المدرسة"),
        source=kw.pop("source", "ministry"),
        created_by=by,
        is_active=True,
    )
    row.full_clean(exclude=["created_by"])
    row.save()
    return row


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


def a_plan(school, teacher, by, **kw):
    fields = {
        "required_weekly_periods": 18,
        "required_source_kind": FROM_MANUAL,
        "required_source_reference": "تعميم 7 / 2026",
        "reduction_periods": 0,
        "reduction_reason": "",
        "reduction_source": "",
        "reduction_source_reference": "",
    }
    fields.update(kw)
    return flow.open_draft(school, teacher, YEAR, by=by, **fields)


# ── التفريغُ لا يمسّ الهدف ───────────────────────────────────────────


def test_a_full_day_exemption_does_not_reduce_the_teaching_target(
    school, coordinator, target_teacher
):
    """الدورةُ يومَ الأحد لا تُنقص حصّةً واحدةً من النصاب."""
    plan = a_plan(school, target_teacher, coordinator)
    assert plan.teaching_target == 18

    exempt(school, target_teacher, coordinator)

    plan.refresh_from_db()
    assert plan.teaching_target == 18, "النصابُ يُضغط في بقيّة الأيّام ولا يُخفَّف"
    assert plan.reduction_periods == 0, "ولا يُخلق له تخفيضٌ لم يقرّره أحد"


def test_a_reduction_still_comes_from_its_own_decision(school, coordinator, target_teacher):
    """وإن خُفّف نصابُه فبقرارٍ مستقلٍّ له مرجعُه — لا اشتقاقاً من التفريغ."""
    exempt(school, target_teacher, coordinator)
    plan = a_plan(
        school,
        target_teacher,
        coordinator,
        reduction_periods=2,
        reduction_reason="منسّق مادّة",
        reduction_source="school",
        reduction_source_reference="محضر 12",
    )

    assert plan.teaching_target == 16
    assert plan.reduction_source_reference == "محضر 12", "مرجعُ التخفيض قرارُ مدرسةٍ لا تعميمُ دورة"


# ── مصدرُ قرار التفريغ ──────────────────────────────────────────────


def test_a_specific_period_exemption_needs_its_period(school, coordinator, target_teacher):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        exempt(school, target_teacher, coordinator, kind="specific_period", period=None)


def test_the_settings_screen_accepts_a_documented_exemption(client_as, school, target_teacher):
    from django.urls import reverse

    from operations.models import TeacherExemption

    principal = actor(school, "principal", "مدير المدرسة")
    client_as(principal).post(
        reverse("add_exemption"),
        {
            "year": YEAR,
            "teacher": str(target_teacher.pk),
            "exemption_type": "full_day",
            "day_of_week": SUNDAY,
            "reason": "دورةٌ خارج المدرسة",
            "source": "ministry",
        },
        follow=True,
    )

    row = TeacherExemption.objects.get()
    assert (row.day_of_week, row.source) == (SUNDAY, "ministry")


# ── المقابلةُ الجديدة: هل تسع الأيّامُ الهدف؟ ────────────────────────


def test_the_days_left_must_hold_the_target(school, coordinator, target_teacher, subject):
    """أربعةُ أيّامٍ تسع ثمانيةَ عشرَ — والبوّابةُ تقول ذلك برقمه."""
    assign(school, target_teacher, subject, periods=18)
    exempt(school, target_teacher, coordinator)
    plan = a_plan(school, target_teacher, coordinator)

    capacity = flow.available_capacity(plan)

    assert capacity["days_off"] == ["الأحد"]
    assert capacity["capacity"] == 27, "٧×٣ لبقيّة الأيّام + ٦ للخميس الإعداديّ"
    assert capacity["fits"] is True

    check = next(c for c in flow.validate(plan) if "تسع" in c["label"])
    assert check["passed"] is True
    assert "18" in check["detail"] and "27" in check["detail"]


def test_three_exempt_days_make_the_target_impossible_and_the_gate_says_so(
    school, coordinator, target_teacher, subject
):
    """ولا يُكتشف هذا يومَ يعجز المولّد — بل قبل الاعتماد."""
    assign(school, target_teacher, subject, periods=18)
    for day in (SUNDAY, MONDAY, TUESDAY):
        exempt(school, target_teacher, coordinator, day=day)
    plan = a_plan(school, target_teacher, coordinator)

    capacity = flow.available_capacity(plan)
    assert capacity["capacity"] == 13 and capacity["fits"] is False

    check = next(c for c in flow.validate(plan) if "تسع" in c["label"])
    assert check["passed"] is False


def test_single_period_exemptions_eat_into_the_capacity_too(
    school, coordinator, target_teacher, subject
):
    """حصّةٌ محجوزةٌ في يومٍ عاملٍ تُنقص الطاقةَ حصّةً — لا يوماً."""
    assign(school, target_teacher, subject, periods=18)
    exempt(school, target_teacher, coordinator, kind="specific_period", day=MONDAY, period=3)
    plan = a_plan(school, target_teacher, coordinator)

    assert flow.available_capacity(plan)["capacity"] == 33, "٣٤ ناقص خانةٍ واحدة"


def test_a_secondary_teacher_keeps_the_seventh_thursday_period(
    school, coordinator, target_teacher, subject
):
    """الخميسُ ستٌّ للإعداديّ وسبعٌ للثانويّ — والأشدُّ تقييداً هو الحاكم."""
    assign(school, target_teacher, subject, periods=18, grade="G10", level="sec")
    plan = a_plan(school, target_teacher, coordinator)

    assert flow.available_capacity(plan)["capacity"] == 35


def test_a_teacher_with_no_exemption_has_the_whole_week(
    school, coordinator, target_teacher, subject
):
    assign(school, target_teacher, subject, periods=18)
    plan = a_plan(school, target_teacher, coordinator)

    capacity = flow.available_capacity(plan)

    assert capacity["days_off"] == [] and capacity["capacity"] == 34


# ── الشاشة تُظهر الضغط ──────────────────────────────────────────────


def test_the_assignment_card_shows_the_exempt_days_so_the_approver_knows(
    client_as, school, coordinator, target_teacher, subject
):
    """من يوقّع على ثمانيةَ عشرَ حصّةً يحقّ له أن يرى أنّها في أربعة أيّام.

    كانت تُعرض في محرّر الخطّة، وحلّت محلَّه بطاقةُ المعلّم في شاشة الإسناد
    (قرارُ التبسيط 2026-09-06). وتُعرض حيث تلزم: على المرفوع للمراجعة والمُراجَع
    — أي حيثما يقف المراجعُ والمعتمِد.
    """
    from django.urls import reverse

    assign(school, target_teacher, subject, periods=18)
    exempt(school, target_teacher, coordinator)
    plan = a_plan(school, target_teacher, coordinator)
    flow.submit_for_review(plan, by=coordinator)
    principal = actor(school, "principal", "المدير")

    body = (
        client_as(principal)
        .get(reverse("academic_management:assignments"), {"year": YEAR})
        .content.decode()
    )

    assert "الأحد" in body
    assert "دورةٌ خارج المدرسة" in body
    assert "لا يُخفّف النصاب" in body, "ويُقال صراحةً أنّ التفريغَ ضغطٌ لا تخفيف"
