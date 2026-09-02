"""[SCHEDULE] الإزاحة: حين تُسدُّ الخانةُ الأخيرة، يُزاح ساكنُها لا تُترك الحصّة.

الخوارزميّةُ جشعة: تضع كلَّ مهمّةٍ في أفضل خانةٍ متاحةٍ فوراً. وقد يُغلق هذا
البابَ على مهمّةٍ لاحقةٍ لا بديلَ لها، بينما للساكن الحاليّ بدائلُ كثيرة.

والتراجعُ الأعمى لا يُصلحها: يرفع **آخرَ** ما وُضع، وقد لا يكون له بالانسداد
صلة. ولذلك لم يُجدِ رفعُ حدّه من خمسمئةٍ إلى ثلاثين ألفاً (بل أعطى أسوأ).

    التراجعُ الأعمى    →  ارفع آخرَ ما وُضع، وجرّب
    الإزاحةُ الموجَّهة  →  اعرف مَن يسدّ هذه الخانة بعينه، وأزِحه إلى بديلٍ له

وهذه الاختباراتُ تصف حالةً يعجز عنها الأوّلُ ويحلّها الثاني: معلّمٌ له خانةٌ
واحدةٌ ممكنةٌ في الأسبوع كلِّه، وقد شغلها زميلٌ يملك أربعاً وثلاثين غيرَها.
"""

import pytest

from operations.models import Subject, SubjectClassAssignment, TeacherExemption
from operations.scheduler import build_tasks, generate_schedule
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


def teacher(school, name):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


def exempt_all_but(school, user, keep_day, keep_period):
    """يُضيَّق أسبوعُ المعلّم إلى خانةٍ واحدةٍ — بتفريغِ ما عداها."""
    for day in range(5):
        if day != keep_day:
            TeacherExemption.objects.create(
                school=school,
                teacher=user,
                academic_year=YEAR,
                exemption_type="full_day",
                day_of_week=day,
                reason="تضييقُ اختبار",
                source="school",
                source_reference="اختبار",
            )
    for period in range(1, 8):
        if period != keep_period:
            TeacherExemption.objects.create(
                school=school,
                teacher=user,
                academic_year=YEAR,
                exemption_type="specific_period",
                day_of_week=keep_day,
                period_number=period,
                reason="تضييقُ اختبار",
                source="school",
                source_reference="اختبار",
            )


@pytest.fixture
def cornered(school):
    """شعبةٌ فيها معلّمٌ مقيَّدٌ بخانةٍ واحدة، وزميلٌ حرٌّ يسبقه في الترتيب.

    الحرُّ يُدرّس مادّةً بستّ حصص، فيُرتَّب أوّلاً (نصابٌ أعلى)، ويُرجَّح له
    الأحدُ ح1. والمقيَّدُ لا يملك سواها.
    """
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    free = teacher(school, "المعلّمُ الحرّ")
    cornered_teacher = teacher(school, "المعلّمُ المقيَّد")
    exempt_all_but(school, cornered_teacher, keep_day=0, keep_period=1)

    heavy = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    single = Subject.objects.create(school=school, name_ar="الفنون البصرية", code="ART")
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=free,
        class_group=group,
        subject=heavy,
        weekly_periods=6,
        is_active=True,
    )
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=cornered_teacher,
        class_group=group,
        subject=single,
        weekly_periods=1,
        is_active=True,
    )
    return group, free, cornered_teacher


def test_the_cornered_lesson_gets_its_only_slot(school, cornered):
    """لا تُترك حصّةٌ لا بديلَ لها لأنّ صاحبَ البدائل سبقها."""
    group, free, cornered_teacher = cornered
    assert len(build_tasks(school, YEAR)) == 7

    result = generate_schedule(school, YEAR)

    assert result["errors"] == [], result["errors"]
    assert result["quality"]["placed_ratio"] == 100.0

    entries = {(e["day"], e["period"]): e["task"] for e in result["grid"].all_entries()}
    assert entries[(0, 1)].teacher_id == str(cornered_teacher.id), "الخانةُ الوحيدةُ لصاحبها"


def test_the_evicted_lesson_lands_somewhere_legal(school, cornered):
    """والمُزاحُ لا يضيع: يُعاد وضعُه في خانةٍ صحيحة."""
    group, free, _ = cornered

    result = generate_schedule(school, YEAR)
    grid = result["grid"]

    free_slots = [
        (e["day"], e["period"]) for e in grid.all_entries() if e["task"].teacher_id == str(free.id)
    ]
    assert len(free_slots) == 6, "ستُّ حصصٍ للمادّة السداسيّة"
    assert len(set(free_slots)) == 6, "لا ازدواجَ في الخانات"

    per_day = {}
    for day, _ in free_slots:
        per_day[day] = per_day.get(day, 0) + 1
    assert sorted(per_day.values()) == [1, 1, 1, 1, 2], "والتوزيعُ باقٍ على قاعدته"


def test_no_teacher_gets_two_lessons_back_to_back(school):
    """لا حصّتين متلاصقتين لمعلّمٍ — قرارُ إدارة المدرسة، وقيدٌ صلبٌ لا تفضيل.

    وكان الحدُّ ثلاثاً ثمّ اثنتين ثمّ صار واحدة. والمقايضةُ معلومةٌ ومقبولة:
    ستُّ حصصٍ من ثمانمئةٍ وواحدٍ وأربعين تُترك للإدخال اليدويّ، مقابل ألّا
    يقف معلّمٌ حصّتين متلاصقتين.
    """
    from collections import defaultdict

    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    only = teacher(school, "معلّمٌ وحيد")
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=only,
        class_group=group,
        subject=Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT"),
        weekly_periods=6,
        is_active=True,
    )

    result = generate_schedule(school, YEAR)

    per_day = defaultdict(list)
    for entry in result["grid"].all_entries():
        per_day[entry["day"]].append(entry["period"])
    for day, periods in per_day.items():
        periods.sort()
        for i in range(1, len(periods)):
            assert periods[i] != periods[i - 1] + 1, f"تلاصقٌ في اليوم {day}: {periods}"


def test_the_relaxation_is_spent_only_where_it_is_needed(school):
    """الرخصةُ تُصرَف عند الحاجة لا قبلها.

    والقياسُ هو الذي فرض هذا الترتيب: السماحُ بالتلاصق من البداية أنتج ثمانيةً
    وتسعين زوجاً عند خمسةٍ وأربعين معلّماً؛ والاسترخاءُ في آخر خطوةٍ — للمتعذّرات
    وحدَها — أنتج عشرين زوجاً عند ثلاثةَ عشر. والنتيجةُ واحدة: جدولٌ كامل.
    """
    from collections import defaultdict

    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    only = teacher(school, "معلّمٌ وحيد")
    SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=only,
        class_group=group,
        subject=Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT"),
        weekly_periods=6,
        is_active=True,
    )

    result = generate_schedule(school, YEAR)

    assert result["errors"] == []
    assert result["relaxed"] == 0, "جدولٌ واسعٌ لا يحتاج رخصة"

    per_day = defaultdict(list)
    for entry in result["grid"].all_entries():
        per_day[entry["day"]].append(entry["period"])
    for periods in per_day.values():
        periods.sort()
        for i in range(1, len(periods)):
            assert periods[i] != periods[i - 1] + 1, "ولا تلاصقَ حيث لا ضرورة"


def test_an_impossible_lesson_is_still_reported(school):
    """والإزاحةُ لا تُخفي المستحيل: معلّمانِ لخانةٍ واحدةٍ لا يجتمعان."""
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    first = teacher(school, "الأوّل")
    second = teacher(school, "الثاني")
    exempt_all_but(school, first, keep_day=0, keep_period=1)
    exempt_all_but(school, second, keep_day=0, keep_period=1)

    for index, user in enumerate((first, second)):
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=user,
            class_group=group,
            subject=Subject.objects.create(
                school=school, name_ar=f"مادّة {index}", code=f"S{index}"
            ),
            weekly_periods=1,
            is_active=True,
        )

    result = generate_schedule(school, YEAR)

    assert not result["success"]
    assert len(result["errors"]) == 1, "واحدةٌ تُوضع والأخرى تُعلَن متعذّرة"
    assert result["quality"]["total_slots"] == 1
