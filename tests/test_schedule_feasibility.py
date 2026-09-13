"""[SCHEDULE] فحصُ الجدوى: يعدّ ولا يبحث.

    ما عجز في العدّ لا يجده بحثٌ مهما طال.

المولّدُ لا يعرف الفرقَ بين «لم أجد» و«لا يوجد»: يدور حتى ينفد وقتُه ثمّ
يخرج بحصصٍ متعذّرةٍ بلا بيان — وقد كلّف ذلك سبعمئةً وخمساً وثلاثين ثانيةً
وسقوطاً على Railway. فهذه الفحوصُ تقارن الطلبَ بالخانات قبل أن يُضغط الزرّ.

والحدُّ الأدنى للمتعذّر **أكبرُ عجزٍ لا مجموعُ الأعجاز**: الفحوصُ تتقاطع،
فمعلّمٌ ضاق وقتُه قد يكون صاحبَ المادّة التي ضاقت أيّامُها. ووعدُ المستخدم
برقمٍ أسوأَ من الحقيقة كذبٌ وإن كان في جانب الحذر.
"""

import pytest
from django.urls import reverse

from operations import schedule_feasibility as sf
from operations.models import SchedulingResource, Subject, SubjectClassAssignment, TeacherExemption

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


# ── تجهيز ────────────────────────────────────────────────────────────


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-FEA")


def a_user(school, name, role_name):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name=role_name)
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def vice(db, school):
    return a_user(school, "النائب الأكاديميّ", "vice_academic")


@pytest.fixture
def teacher(db, school):
    return a_user(school, "معلّمُ الرياضيات", "teacher")


def a_subject(school, name, code, **kw):
    return Subject.objects.create(school=school, name_ar=name, code=code, **kw)


def a_class(school, grade="G8", section="1", level="prep"):
    from core.models import ClassGroup

    return ClassGroup.objects.create(
        school=school, grade=grade, section=section, level_type=level, academic_year=YEAR
    )


def assign(school, subject, class_group, teacher, periods):
    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        subject=subject,
        class_group=class_group,
        teacher=teacher,
        weekly_periods=periods,
    )


def free_day(school, teacher, day):
    return TeacherExemption.objects.create(
        school=school,
        teacher=teacher,
        academic_year=YEAR,
        exemption_type="full_day",
        day_of_week=day,
        reason="اجتماعُ منسّقي المواد",
        source="school",
    )


def finding(report, code):
    return next(f for f in report.findings if f.code == code)


# ── الطاقةُ الأسبوعيّة ───────────────────────────────────────────────


def test_the_week_is_thirty_four_periods_for_prep_and_thirty_five_for_secondary():
    """الخميسُ وحدَه يفرّق: إعداديٌّ ستٌّ وثانويٌّ سبع (HC4)."""
    assert sf.weekly_capacity("prep") == 34
    assert sf.weekly_capacity("sec") == 35


def test_an_empty_school_is_feasible(school):
    report = sf.check(school, YEAR)

    assert report.feasible
    assert report.minimum_unplaceable == 0
    assert {f.status for f in report.findings} == {"ok"}


# ── طاقةُ الشعبة ─────────────────────────────────────────────────────


def test_a_class_asked_for_more_than_its_week(school, teacher):
    """أربعٌ وثلاثون خانةً في أسبوع الإعداديّ — والطلبُ خمسٌ وثلاثون."""
    section = a_class(school)
    assign(school, a_subject(school, "الرياضيات", "MAT"), section, teacher, 35)

    report = sf.check(school, YEAR)
    found = finding(report, "capacity.class")

    assert found.status == "fail"
    assert found.gap == 1
    assert not report.feasible


def test_a_class_within_its_week_passes(school, teacher):
    section = a_class(school)
    assign(school, a_subject(school, "الرياضيات", "MAT"), section, teacher, 34)

    assert finding(sf.check(school, YEAR), "capacity.class").status == "ok"


# ── طاقةُ المعلّم ────────────────────────────────────────────────────


def test_a_teacher_whose_load_exceeds_his_remaining_days(school, teacher):
    """ثلاثةُ أيّامِ تفريغٍ تترك يومين — والخميسُ منهما ستٌّ لا سبع (HC4)."""
    subject = a_subject(school, "الرياضيات", "MAT")
    assign(school, subject, a_class(school, section="1"), teacher, 15)
    assign(school, subject, a_class(school, section="2"), teacher, 15)
    for day in (0, 1, 2):
        free_day(school, teacher, day)

    found = finding(sf.check(school, YEAR), "capacity.teacher")

    assert found.status == "fail"
    assert found.gap == 30 - 13, "الأربعاءُ سبعٌ والخميسُ ستٌّ لشعبةٍ إعداديّة"
    assert "3 يومَ تفريغٍ كامل" in found.rows[0].note


def test_single_period_exemptions_narrow_the_capacity_too(school, teacher):
    """التفريغُ الجزئيُّ خاناتٌ خارجةٌ عن وقته كذلك — لا يومَ كاملاً فقط."""
    subject = a_subject(school, "الرياضيات", "MAT")
    assign(school, subject, a_class(school), teacher, 34)
    TeacherExemption.objects.create(
        school=school,
        teacher=teacher,
        academic_year=YEAR,
        exemption_type="specific_period",
        day_of_week=0,
        period_number=1,
        reason="قرار إدارة المدرسة — لا أولى ولا سابعة",
        source="school",
    )

    found = finding(sf.check(school, YEAR), "capacity.teacher")

    assert found.status == "fail", "خانةٌ واحدةٌ تكفي لقلب الميزان حين لا هامش"
    assert found.gap == 1


def test_a_teacher_with_room_passes(school, teacher):
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 20)

    assert finding(sf.check(school, YEAR), "capacity.teacher").status == "ok"


# ── الموارد ──────────────────────────────────────────────────────────


def test_a_resource_asked_for_more_than_its_slots(school, teacher):
    """معملٌ واحدٌ يسع خمساً وثلاثين حصّةً في الأسبوع — والطلبُ أربعون."""
    subject = a_subject(school, "علوم الحاسب", "CS")
    lab = SchedulingResource.objects.create(school=school, name="معمل الحاسب", capacity=1)
    lab.subjects.add(subject)
    for i in range(2):
        assign(school, subject, a_class(school, section=str(i + 1)), teacher, 20)

    found = finding(sf.check(school, YEAR), "capacity.resource")

    assert found.status == "fail"
    assert found.gap == 40 - 35


def test_two_labs_carry_twice_as_much(school, teacher):
    subject = a_subject(school, "علوم الحاسب", "CS")
    lab = SchedulingResource.objects.create(school=school, name="معملا الحاسب", capacity=2)
    lab.subjects.add(subject)
    for i in range(2):
        assign(school, subject, a_class(school, section=str(i + 1)), teacher, 20)

    assert finding(sf.check(school, YEAR), "capacity.resource").status == "ok"


# ── إسنادٌ بلا معلّم ─────────────────────────────────────────────────


def test_an_assignment_without_a_teacher_warns_but_does_not_block(school):
    """`build_tasks` يتخطّاه صامتاً — فحصصُه تضيع ولا تُعَدّ متعذّرة."""
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        subject=a_subject(school, "الرياضيات", "MAT"),
        class_group=a_class(school),
        teacher=None,
        weekly_periods=4,
    )

    report = sf.check(school, YEAR)
    found = finding(report, "assignment.unassigned")

    assert found.status == "warn"
    assert report.feasible, "التنبيهُ لا يمنع"
    assert "4 حصّة" in found.summary


# ── الحكمُ الجامع ────────────────────────────────────────────────────


def test_the_minimum_is_the_largest_gap_not_their_sum(school, teacher):
    """عجزان قد يكونان عجزاً واحداً — فلا يُجمعان في وجه المستخدم."""
    subject = a_subject(school, "التكنولوجيا", "TECH")
    assign(school, subject, a_class(school), teacher, 40)

    report = sf.check(school, YEAR)

    gaps = sorted(f.gap for f in report.blocking)
    assert len(gaps) >= 2, "الشعبةُ والمعلّمُ كلاهما يشتكي"
    assert report.minimum_unplaceable == max(gaps)
    assert report.minimum_unplaceable < sum(gaps)


def test_the_report_is_storable(school, teacher):
    """يُحفظ مع عمليّة التوليد — فالحكمُ يُقرأ بعد أشهر."""
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 35)

    stored = sf.check(school, YEAR).as_dict()

    assert stored["feasible"] is False
    assert stored["minimum_unplaceable"] == 1
    assert {f["code"] for f in stored["findings"]} == {
        "capacity.class",
        "capacity.teacher",
        "capacity.resource",
        "assignment.unassigned",
    }


# ── الشاشة ───────────────────────────────────────────────────────────


def test_the_smart_schedule_screen_shows_the_verdict(client_as, vice, school, teacher):
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 35)

    page = client_as(vice).get(f"{reverse('smart_schedule')}?year={YEAR}").content.decode()

    assert "فحصُ الجدوى قبل التوليد" in page
    assert "لن تجد موضعاً" in page
    assert "عجزٌ يقينيّ" in page


def test_a_healthy_school_is_told_so(client_as, vice, school, teacher):
    assign(school, a_subject(school, "الرياضيات", "MAT"), a_class(school), teacher, 20)

    page = client_as(vice).get(f"{reverse('smart_schedule')}?year={YEAR}").content.decode()

    assert "لا عجزَ في العدّ" in page
    assert "عجزٌ يقينيّ" not in page
