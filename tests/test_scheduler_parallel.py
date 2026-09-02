"""[SCHEDULE] الشعبةُ المنقسمة: مادّتان في خانةٍ واحدةٍ ومعلّمان.

    InstructionalPeriods ≠ OccupiedSlots

أربعُ شعبٍ في المدرسة يتفرّق طلابها بين مادّتين في التوقيت نفسه: 11/1 و12/1
بين التكنولوجيا والفنون البصرية، و11/4 و12/4 بين الكيمياء والفنون. قسمٌ يذهب
إلى المعمل وقسمٌ يبقى.

وكان الازدواجُ مسجَّلاً في `ScheduleSlot.elective_group` فقط — أي في الجدول
المستورَد لا في الإسناد. فترتّب عليه خطآن:

    تحذيرُ الطاقة  يعدّ 37 حصّةً ويقيسها بـ35 خانةً فيُنذر إنذاراً كاذباً
    المولّد        لا يعرف الازدواجَ أصلاً، فيضع إحدى المادّتين ويعدّ الأخرى متعذّرة

فصار الإسنادُ يحمل `parallel_group`: مادّتان في الشعبة الواحدة تحملان الوسمَ
نفسه تُوضعان في خانةٍ واحدة، ويُكتب لكلٍّ صفُّها بـ`elective_group` كما في
الجدول القائم.
"""

import pytest

from operations.services import CapacityCheckService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


@pytest.fixture
def group(school):
    return ClassGroupFactory(school=school, grade="G11", level_type="sec", academic_year=YEAR)


@pytest.fixture
def teachers(school):
    role = RoleFactory(school=school, name="teacher")
    out = []
    for name in ("معلّمُ الفنون", "معلّمُ التكنولوجيا", "معلّمُ الرياضيات"):
        user = UserFactory(full_name=name)
        MembershipFactory(user=user, school=school, role=role)
        out.append(user)
    return out


@pytest.fixture
def subjects(school):
    from operations.models import Subject

    # الازدواجُ يُطلب بالحقل لا بالرمز: كان `code in {"ART", "TECH"}` محفوراً
    # في المحرّك فيُزدوجان بلا طلب، فلمّا صار الحقلُ وحدَه الحكمَ لزم أن
    # يُصرّح به الاختبار — وهذا اختبارُ التوازي لا اختبارُ من يقرّر الازدواج.
    return [
        Subject.objects.create(
            school=school, name_ar="الفنون البصرية", code="ART", requires_double_period=True
        ),
        Subject.objects.create(
            school=school, name_ar="التكنولوجيا", code="TECH", requires_double_period=True
        ),
        Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT"),
    ]


def assign(school, group, teacher, subject, *, periods, parallel=""):
    from operations.models import SubjectClassAssignment

    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=periods,
        parallel_group=parallel,
        is_active=True,
    )


@pytest.fixture
def split(school, group, teachers, subjects):
    """شعبةٌ منقسمة: فنونٌ وتكنولوجيا بالتوازي، ورياضياتٌ وحدَها."""
    art = assign(school, group, teachers[0], subjects[0], periods=2, parallel="اختياري-1")
    tech = assign(school, group, teachers[1], subjects[1], periods=2, parallel="اختياري-1")
    maths = assign(school, group, teachers[2], subjects[2], periods=4)
    return art, tech, maths


# ── الطاقة تُقاس بالخانات لا بالحصص ──────────────────────────────────


def test_parallel_subjects_consume_one_slot_not_two(school, split):
    """ثمانِ حصصٍ في ستّ خانات — فالمتوازيتان تتشاركان الزمن."""
    rows = list(split)

    assert sum(r.weekly_periods for r in rows) == 8
    assert CapacityCheckService.slot_demand(rows) == 6


def test_the_false_alarm_is_gone(school, group, teachers, subjects):
    """37 حصّةً في 35 خانة ليست فائضاً — وهي حالُ 11/1 و12/1 فعلاً."""
    rows = [
        assign(school, group, teachers[0], subjects[0], periods=2, parallel="اختياري-1"),
        assign(school, group, teachers[1], subjects[1], periods=2, parallel="اختياري-1"),
        assign(school, group, teachers[2], subjects[2], periods=33),
    ]

    assert sum(r.weekly_periods for r in rows) == 37
    assert CapacityCheckService.slot_demand(rows) == 35
    assert CapacityCheckService.get_overcapacity_classes(rows) == []


def test_a_real_overflow_is_still_reported(school, group, teachers, subjects):
    """ولا يُخفي الإصلاحُ فائضاً حقيقيّاً."""
    rows = [
        assign(school, group, teachers[0], subjects[0], periods=2, parallel="اختياري-1"),
        assign(school, group, teachers[1], subjects[1], periods=2, parallel="اختياري-1"),
        assign(school, group, teachers[2], subjects[2], periods=36),
    ]

    [flagged] = CapacityCheckService.get_overcapacity_classes(rows)

    assert (flagged["demand"], flagged["capacity"], flagged["overflow"]) == (38, 35, 3)


# ── المولّد يضعهما معاً ──────────────────────────────────────────────


def test_the_generator_places_both_subjects_in_the_same_slot(school, split):
    from operations.models import ScheduleSlot
    from operations.scheduler import build_tasks, generate_schedule

    tasks = build_tasks(school, YEAR)
    #: الفنونُ والتكنولوجيا مادّتان مزدوجتان ومتوازيتان معاً، فهما مهمّةٌ
    #: واحدةٌ بساكنَين تشغل خانتين متلاصقتين — لا مهمّتانِ مفردتان.
    assert len(tasks) == 5, "أربعُ رياضياتٍ ومهمّةٌ متوازيةٌ مزدوجة"
    [parallel] = [t for t in tasks if t.is_split]
    assert parallel.span == 2

    result = generate_schedule(school, YEAR)

    assert result["success"], result["errors"][:3]
    rows = ScheduleSlot.objects.filter(school=school, academic_year=YEAR, is_active=True)
    assert rows.count() == 8, "ثمانِ حصصٍ تُكتب: خانتان × مادّتان + أربعُ رياضيات"

    shared = sorted(
        (r.day_of_week, r.period_number) for r in rows if r.subject.code in ("ART", "TECH")
    )
    assert len(shared) == 4, "حصّتان لكلّ مادّة"
    assert len(set(shared)) == 2, "في خانتين اثنتين"
    (day, first), (_, second) = sorted(set(shared))
    assert second == first + 1, "متلاصقتان"


def test_the_group_doubles_only_when_every_member_asks_for_it(school, group, teachers, subjects):
    """الازدواجُ لا يُفرض على شريكٍ لا يطلبه.

    الفنّيّةُ مزدوجةٌ والكيمياءُ ليست كذلك، وهما متوازيتان في الحادي عشر/4
    والثاني عشر/4. فلو جرّت الفنّيّةُ الكيمياءَ إلى خانتين متلاصقتين لاجتمعت
    حصّتا الكيمياء في يومٍ واحد — والأولى بها يومان. فتُبنى المجموعةُ حصصاً
    مفردةً تُفرّقها القسمةُ على الأيّام.
    """
    from operations.models import Subject
    from operations.scheduler import build_tasks

    art = Subject.objects.create(
        school=school, name_ar="الفنون البصرية", code="ART2", requires_double_period=True
    )
    chemistry = Subject.objects.create(school=school, name_ar="الكيمياء", code="CHE")
    assign(school, group, teachers[0], art, periods=2, parallel="اختياري-2")
    assign(school, group, teachers[1], chemistry, periods=2, parallel="اختياري-2")

    tasks = [t for t in build_tasks(school, YEAR) if t.is_split]

    assert len(tasks) == 2, "حصّتان مفردتان لا مهمّةٌ مزدوجة"
    assert all(t.span == 1 for t in tasks)


def test_a_group_whose_members_all_ask_for_it_still_doubles(school, split):
    """وشريكانِ كلاهما مزدوج — الفنّيّةُ والتكنولوجيا — يبقيان متلاصقين."""
    from operations.models import Subject
    from operations.scheduler import build_tasks

    Subject.objects.filter(school=school, code__in=("ART", "TECH")).update(
        requires_double_period=True
    )

    [parallel] = [t for t in build_tasks(school, YEAR) if t.is_split]

    assert parallel.span == 2


def test_each_row_carries_its_elective_group(school, split):
    """الصفُّ يحمل وسمَ مجموعته، وإلّا رفضه قيدُ «شعبةٌ واحدةٌ في التوقيت»."""
    from operations.models import ScheduleSlot
    from operations.scheduler import generate_schedule

    generate_schedule(school, YEAR)

    rows = ScheduleSlot.objects.filter(
        school=school, academic_year=YEAR, is_active=True, subject__code__in=("ART", "TECH")
    )
    assert all(r.elective_group for r in rows)
    assert {r.elective_group for r in rows} == {"الفنون البصرية", "التكنولوجيا"}

    plain = ScheduleSlot.objects.filter(
        school=school, academic_year=YEAR, is_active=True, subject__code="MAT"
    )
    assert all(r.elective_group == "" for r in plain), "وغيرُ المنقسمة تبقى بلا وسم"


def test_both_teachers_are_busy_in_that_slot(school, split, teachers):
    """معلّمانِ يعملان في الخانة نفسها — فلا يُسنَد إليهما شيءٌ آخر فيها."""
    from operations.scheduler import build_tasks, generate_schedule

    result = generate_schedule(school, YEAR)
    grid = result["grid"]
    entry = next(e for e in grid.all_entries() if len(e["task"].members) > 1)

    #: المعلّمانِ مشغولان في **كلتا** خانتَي المزدوجة، لا في أولاهما وحدَها.
    for member in entry["task"].members:
        for slot in entry["task"].slots(entry["period"]):
            assert grid.teacher_busy(member.teacher_id, entry["day"], slot)

    assert len(build_tasks(school, YEAR)) == 5
