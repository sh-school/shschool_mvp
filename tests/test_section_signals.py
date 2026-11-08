"""[STUDENT-INFO] صفحةُ طلاب الشعبة: إشاراتُ الاستثناء وشريطُ الملخّص والبحث (W-20261108-019).

[LEGAL] عتباتُ الغياب (5 · 8 · 11 · 15 للصفوف 1–11، و8 · 15 للثاني عشر) من نصّ الدليل لا من الذاكرة:
المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.4.1.3
(وهي في `operations/absence_policy.py` منقولةً حرفاً). وهامشُ «القرب» (يومان) وقيدُ «الجديد»
(14 يوماً) قرارا عرضٍ لا نصٌّ وزاريّ.
"""

import datetime as dt
from datetime import time

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from behavior.models import BehaviorInfraction
from operations.models import Session, StudentAttendance
from student_info import selectors
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.visual_snapshots import FIXED_NOW

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

TODAY = timezone.localdate(FIXED_NOW)
OLD = TODAY - dt.timedelta(days=60)


@pytest.fixture
def year(seeded_calendar):
    return seeded_calendar


@pytest.fixture
def group(school, year):
    return ClassGroupFactory(school=school, grade="G7", section="1", academic_year=year)


def _student(school, group, name, enrolled_at=OLD):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=user, class_group=group, enrolled_at=enrolled_at)
    return user


def _mark(school, group, teacher, student, day, status, hour=8):
    # حصّةٌ واحدة للشعبة في اليوم والساعة (قيد no_class_time_overlap_real): تُعاد لا تُكرَّر
    session, _ = Session.objects.get_or_create(
        school=school,
        class_group=group,
        date=day,
        start_time=time(hour, 0),
        defaults={"teacher": teacher, "end_time": time(hour, 45), "status": "scheduled"},
    )
    StudentAttendance.objects.create(session=session, student=student, school=school, status=status)


def _roster(group, school, year, **kw):
    from student_info import services

    return selectors.section_roster(
        group, services.students_of_section(group), school, TODAY, year, **kw
    )


def _sig(result, student):
    return next(s for e, s in result["rows"] if e.student_id == student.id)


# ── العتبة ────────────────────────────────────────────────────────────


def test_gate_signal_uses_the_ministry_thresholds_and_shows_only_when_near():
    """قربٌ بالهامش من أوّل عتبةٍ لم تُتجاوَز؛ وبعيدٌ أو صفرٌ فلا شارة؛ وتجاوزُ الكلّ تجاوزٌ."""
    assert selectors._gate_signal("G7", 0) == (None, False)
    assert selectors._gate_signal("G7", 2) == (None, False)  # 5 − 2 = 3 أكبر من الهامش
    gate, over = selectors._gate_signal("G7", 3)
    assert (gate.max_days, over) == (5, False)
    assert selectors._gate_signal("G7", 5)[0].max_days == 5  # المساواةُ لا تحرم لكنّها على الحدّ
    assert selectors._gate_signal("G7", 6)[0].max_days == 8  # تجاوز 5 وصار قريباً من 8
    assert selectors._gate_signal("G7", 16) == (None, True)


def test_gate_signal_for_grade_12_has_only_two_gates():
    """الثاني عشر: عتبتان (8 · 15) — فثلاثةُ أيّامٍ بعيدةٌ عن 8."""
    assert selectors._gate_signal("G12", 3) == (None, False)
    assert selectors._gate_signal("G12", 6)[0].max_days == 8


# ── الإشارات والملخّص ─────────────────────────────────────────────────


def test_the_cell_is_empty_without_a_signal_and_late_counts_present(
    school, group, year, teacher_user
):
    quiet = _student(school, group, "أ هادئ")
    late = _student(school, group, "ب متأخر")
    _mark(school, group, teacher_user, quiet, TODAY, "present")
    _mark(school, group, teacher_user, late, TODAY, "late")

    result = _roster(group, school, year)

    assert not _sig(result, quiet).is_flagged
    assert _sig(result, late).attendance == selectors.PRESENT and _sig(result, late).late
    assert result["summary"] == []  # لا غائب ولا قرب ولا بند: الشريطُ بلا أزرار


def test_absent_today_open_item_and_enrollment_signals(school, group, year, teacher_user):
    absent = _student(school, group, "ج غائب")
    opened = _student(school, group, "د بند")
    fresh = _student(school, group, "هـ جديد", enrolled_at=TODAY - dt.timedelta(days=3))
    moved = _student(school, group, "و منقول")
    other = ClassGroupFactory(school=school, grade="G7", section="2", academic_year=year)
    StudentEnrollmentFactory(
        student=moved,
        class_group=other,
        is_active=False,
        enrolled_at=OLD,
        left_at=TODAY - dt.timedelta(days=30),
    )
    _mark(school, group, teacher_user, absent, TODAY, "absent")
    BehaviorInfraction.objects.create(school=school, student=opened, level=1, description="س")

    result = _roster(group, school, year)

    assert _sig(result, absent).flags == {"absent"}
    assert _sig(result, opened).has_open_item and _sig(result, opened).flags == {"open"}
    assert _sig(result, fresh).enrollment == "new"
    assert _sig(result, moved).enrollment == "transferred"
    assert {(i["key"], i["count"]) for i in result["summary"]} == {("absent", 1), ("open", 1)}
    # أصحابُ الإشارات أولاً ثمّ البقيّة
    flagged = [e.student.full_name for e, s in result["rows"] if s.is_flagged]
    assert [e.student.full_name for e, _ in result["rows"]][: len(flagged)] == flagged


def test_a_resolved_item_is_not_open(school, group, year):
    kid = _student(school, group, "ز")
    BehaviorInfraction.objects.create(
        school=school, student=kid, level=1, description="س", is_resolved=True
    )

    assert not _sig(_roster(group, school, year), kid).has_open_item


def test_near_gate_from_unexcused_absence_days(school, group, year, teacher_user):
    from core.academic_calendar import academic_year_window

    start, _ = academic_year_window(school, TODAY)
    kid = _student(school, group, "ح قريب")
    for i in range(3):  # ثلاثةُ أيّامٍ بلا عذر: 5 − 3 = 2 ← قريبٌ من عتبة الخمسة
        _mark(school, group, teacher_user, kid, start + dt.timedelta(days=i), "absent")

    result = _roster(group, school, year)
    sig = _sig(result, kid)

    assert sig.absence_days == 3 and sig.gate.max_days == 5
    assert {i["key"] for i in result["summary"]} == {"near"}


def test_filter_and_search_narrow_the_rows_but_not_the_summary(school, group, year, teacher_user):
    absent = _student(school, group, "ط غائب")
    _student(school, group, "ي حاضر")
    _mark(school, group, teacher_user, absent, TODAY, "absent")

    flagged = _roster(group, school, year, flag="absent")
    searched = _roster(group, school, year, q="حاضر")
    junk = _roster(group, school, year, flag="__x__")

    assert [e.student_id for e in flagged["enrollments"]] == [absent.id]
    assert [e.student.full_name for e in searched["enrollments"]] == ["ي حاضر"]
    assert searched["summary"] == flagged["summary"]  # الأرقامُ على الشعبة كلِّها
    assert len(junk["enrollments"]) == 2  # مفتاحٌ مجهولٌ يُهمل


def test_query_count_is_constant_whatever_the_class_size(school, group, year, teacher_user):
    # سجلُّ غيابٍ واحدٌ في الحالتين: `unexcused_days_for_class` يتخطّى استعلام الحصص إن خلا السجلّ،
    # فبلا هذا تختلف الحالتان بمسارٍ لا بعدد الطلاب.
    first = _student(school, group, "طالب 0")
    _mark(school, group, teacher_user, first, TODAY, "absent")
    for i in range(1, 3):
        _student(school, group, f"طالب {i}")
    with CaptureQueriesContext(connection) as small:
        _roster(group, school, year)
    for i in range(3, 12):
        kid = _student(school, group, f"طالب {i}")
        _mark(school, group, teacher_user, kid, TODAY, "absent")
        BehaviorInfraction.objects.create(school=school, student=kid, level=1, description="س")
    with CaptureQueriesContext(connection) as large:
        _roster(group, school, year)

    assert len(large) == len(small)


# ── الصفحة والنطاق ────────────────────────────────────────────────────


def test_the_page_renders_signals_and_hides_zero_buttons(
    client, school, group, year, principal_user, teacher_user
):
    absent = _student(school, group, "ك غائب")
    _mark(school, group, teacher_user, absent, TODAY, "absent")
    client.force_login(principal_user)

    html = client.get(reverse("student_info:section_students", args=[group.id])).content.decode()

    assert "غائب اليوم" in html and "flag=absent" in html
    assert "قرب العتبة" not in html and "بندٌ مفتوح</span>" not in html  # الأصفارُ مخفيّة


def test_every_signal_has_its_own_centered_column_and_empty_cells_show_a_dash(
    client, school, group, year, principal_user, teacher_user
):
    """[LEGAL] العتبةُ من 08_conduct_policy_2026.md م3.4.1.3 (عبر absence_policy)؛ هنا الشكلُ لا الرقم.

    المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.4.1.3
    """
    late = _student(school, group, "م متأخر")
    _student(school, group, "ن هادئ")
    _mark(school, group, teacher_user, late, TODAY, "late")
    client.force_login(principal_user)

    html = client.get(reverse("student_info:section_students", args=[group.id])).content.decode()

    for head in ("حضور اليوم", "الغياب مقابل العتبة", "حالة القيد", "بندٌ مفتوح", "الملفّ"):
        assert f">{head}</th>" in html
    assert 'class="table-wrap table-wrap-scroll tbl-cols"' in html  # التوسيطُ مركزيّ لا محلّيّ
    assert html.count('<th class="fu-name">') == 1 and "text-align" not in html.split("<table")[1]
    assert "حاضر (متأخر)" in html  # المتأخرُ يُحتسب حاضراً
    assert 'aria-label="لا إشارة">–</span>' in html  # الخليّةُ بلا إشارة «–» لا فراغ


def test_the_page_carries_no_grades_national_id_or_guardian_data(
    client, school, group, year, principal_user
):
    kid = _student(school, group, "ل")
    client.force_login(principal_user)

    html = client.get(reverse("student_info:section_students", args=[group.id])).content.decode()

    assert kid.national_id not in html
    assert "ولي الأمر" not in html and "الدرجة" not in html
