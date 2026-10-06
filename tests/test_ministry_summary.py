"""[ATTENDANCE] ملخّصُ الحصّتين الأولى والثانية للرفع في نظام الوزارة — أمرُ المالك 2026-10-06.

الثوابتُ: لا يُرفع طالبٌ على رصدٍ ناقص (بلا رصدٍ ≠ حاضر)، والمبدئيُّ لا يُحتسب، والنطاقُ نطاقُ الطلبة
(المشرفُ لجناحه، وحاصرُ الغياب العامّ والقيادةُ للمدرسة)، والمخرجاتُ بلا رقمٍ شخصيّ، والتصديرُ مدقَّق.
ولا رقمَ وظيفيّاً ولا اسماً حقيقيّاً هنا: كلُّ هويّةٍ مولَّدة.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from core import capability_grants as grants
from core.models import AuditLog, Wing
from operations.models import Session, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED, SUNDAY, _staff, at
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory
from wings.ministry_selectors import ministry_summary

pytestmark = pytest.mark.django_db

REASON = "حصرُ الغياب في المدرسة كلِّها بتكليفٍ من الإدارة"


@pytest.fixture(autouse=True)
def _day(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(9, 0))


@pytest.fixture
def periods(school, klass, teacher, session, bells):
    """الحصّتان الأولى (07:10) والثانية (08:00) للشعبة في الأحد."""
    second = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    return session, second


def pupil(school, klass, name, nid):
    student = UserFactory(full_name=name, national_id=nid)
    StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=ENROLLED)
    return student


def mark(school, session, student, status, excuse=""):
    return StudentAttendance.objects.create(
        school=school, session=session, student=student, status=status, excuse_type=excuse
    )


@pytest.fixture
def class_day(school, klass, periods, kid):
    """طالبٌ غاب الحصّتين بلا عذر، وآخرُ بعذر، وثالثٌ غاب الأولى فقط، ورابعٌ تأخّر، وخامسٌ لم تُرصد ثانيتُه."""
    first, second = periods
    both = kid
    excused = pupil(school, klass, "غائبٌ بعذر", "29000003002")
    one = pupil(school, klass, "غائبٌ إحداهما", "29000003003")
    late = pupil(school, klass, "متأخّر", "29000003004")
    open_ = pupil(school, klass, "بلا رصدٍ كامل", "29000003005")
    for student in (both, excused):
        mark(school, first, student, "absent", "sick" if student is excused else "")
        mark(school, second, student, "absent", "sick" if student is excused else "")
    mark(school, first, one, "absent")
    mark(school, second, one, "present")
    mark(school, first, late, "late")
    mark(school, second, late, "present")
    mark(school, first, open_, "absent")  # الثانيةُ لم تُرصد
    return both, excused, one, late, open_


def test_the_class_row_counts_each_case_once(school, klass, class_day):
    summary = ministry_summary(school, SUNDAY)
    row = summary.class_rows[0].counts

    assert row.enrolled == 5
    assert (row.absent_both_unexcused, row.absent_both_excused) == (1, 1)
    assert (row.absent_one, row.late, row.unrecorded) == (1, 1, 1)
    assert summary.total.absent_both == 2


def test_the_unrecorded_student_is_never_lifted_to_the_ministry(school, klass, class_day):
    summary = ministry_summary(school, SUNDAY)

    assert {m.name for m in summary.ministered} == {"غائبٌ بعذر", "طالب الشعبة"}
    assert "بلا رصدٍ كامل" not in {m.name for m in summary.ministered}
    assert any("بلا رصدٍ" in note for note in summary.notes)


def test_a_class_without_two_periods_is_not_judged(school, klass, kid, session, bells):
    summary = ministry_summary(school, SUNDAY)  # حصّةٌ واحدةٌ فقط

    row = summary.class_rows[0]
    assert not row.has_periods
    assert row.counts.absent_both == 0 and row.counts.unrecorded == 0


def test_a_teacher_entry_awaiting_approval_is_flagged_not_counted(
    school, klass, periods, kid, teacher
):
    from operations.attendance_entries import submit_entry

    first, _ = periods
    submit_entry(teacher, first, kid, "absent", now=at(7, 30))

    summary = ministry_summary(school, SUNDAY)

    assert summary.total.pending == 1
    assert summary.total.absent_both == 0


def test_the_wing_supervisor_sees_only_his_wing_and_the_wide_holder_sees_all(
    school, year, band, klass, class_day, holder, client_as
):
    other_holder = _staff(school, "admin_supervisor", "حاملُ الثاني", "29000003010")
    other_wing = Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other_holder
    )
    other_class = ClassGroupFactory(
        school=school,
        grade="G8",
        section="1",
        level_type="prep",
        academic_year=year,
        wing=other_wing,
    )
    pupil(school, other_class, "طالبُ الجناح الثاني", "29000003011")
    principal = _staff(school, "principal", "المدير", "29000003012")
    wide = _staff(school, "admin_supervisor", "حاصرُ الغياب", "29000003013")
    grants.grant(user=wide, capability="wings.school_wide", by=principal, reason=REASON)

    own = client_as(holder).get(reverse("wings:ministry_report")).content.decode()
    everyone = client_as(wide).get(reverse("wings:ministry_report")).content.decode()

    assert "طلبةُ جناحك" in own and "8.1" not in own
    assert "المدرسةُ كلُّها" not in own
    assert "8.1" in everyone and "المدرسةُ كلُّها" in everyone


def test_a_teacher_is_refused(school, teacher, client_as):
    assert client_as(teacher).get(reverse("wings:ministry_report")).status_code == 403


def test_the_exports_are_audited_carry_no_national_id_and_open(
    school, klass, class_day, holder, client_as
):
    page = client_as(holder).get(reverse("wings:ministry_report"), {"date": SUNDAY.isoformat()})
    body = page.content.decode()
    xlsx = client_as(holder).get(
        reverse("wings:ministry_report"), {"date": SUNDAY.isoformat(), "format": "xlsx"}
    )

    assert page.status_code == 200 and "للرفع في نظام الوزارة" in body
    assert "29000003002" not in body  # لا رقمَ شخصيّاً
    pdf = client_as(holder).get(
        reverse("wings:ministry_report"), {"date": SUNDAY.isoformat(), "format": "pdf"}
    )
    assert xlsx.status_code == 200 and "spreadsheetml" in xlsx["Content-Type"]
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    assert AuditLog.objects.filter(object_repr__contains="ملخّصُ غياب").exists()


def test_the_daily_absence_page_links_to_the_summary_for_the_supervisor(
    school, klass, class_day, holder, client_as
):
    body = (
        client_as(holder)
        .get(reverse("daily_report"), {"date": SUNDAY.isoformat()})
        .content.decode()
    )

    assert reverse("wings:ministry_report") in body


def test_the_absence_register_page_links_to_the_summary_and_lists_every_wing_for_the_wide_holder(
    school, year, band, klass, class_day, holder, client_as
):
    """رابطُ الملخّص في «رصد الغياب» (أمرُ المالك 2026-10-06: لا داعي له في الرئيسيّة) والأجنحةُ كلُّها لحاصر الغياب العامّ."""
    other_holder = _staff(school, "admin_supervisor", "حاملُ الثاني", "29000003020")
    Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other_holder
    )
    principal = _staff(school, "principal", "المدير", "29000003021")
    wide = _staff(school, "admin_supervisor", "حاصرُ الغياب", "29000003022")
    grants.grant(user=wide, capability="wings.school_wide", by=principal, reason=REASON)

    body = client_as(wide).get(reverse("wings:record_index")).content.decode()
    home = client_as(wide).get("/dashboard/").content.decode()

    assert reverse("wings:ministry_report") in body
    assert "لا جناحَ مُسنَدٌ إليك" not in body
    assert reverse("wings:ministry_report") not in home  # الرئيسيّةُ بلا إضافةٍ لهذا الملخّص
    assert "wing-panel" in body  # الأجنحةُ في «رصد الغياب»
    assert "wing-panel" not in home  # لا بطاقاتِ أجنحةٍ مكدّسةً في رئيسيّة حاصر الغياب العامّ
    assert "لا جناحَ مُسنَدٌ إليك" not in home


def test_the_ordinary_wing_supervisor_keeps_his_wing_card_on_the_home_page(
    school, klass, class_day, holder, client_as
):
    assert "wing-panel" in client_as(holder).get("/dashboard/").content.decode()


def test_the_screen_is_a_platform_page_with_filters_and_exports_not_a_print_sheet(
    school, klass, class_day, holder, client_as
):
    """الشاشةُ بمكوّنات المنصّة (ترويسةٌ وشريطُ ترشيحٍ وبطاقاتٌ) وفيها تصديرُ Excel وPDF — لا قالبَ طباعة."""
    body = (
        client_as(holder)
        .get(reverse("wings:ministry_report"), {"date": SUNDAY.isoformat()})
        .content.decode()
    )

    assert 'role="search"' in body and "ui-page-header" in body and "ui-kpis" in body
    assert 'value="xlsx"' in body and 'value="pdf"' in body
    assert "running-footer" not in body  # ليس قالبَ PDF


def test_the_grade_and_search_filters_narrow_the_numbers_and_the_names_together(
    school, klass, class_day, holder, client_as
):
    page = client_as(holder)
    url = reverse("wings:ministry_report")

    by_name = page.get(url, {"date": SUNDAY.isoformat(), "q": "غائبٌ بعذر"}).content.decode()
    nothing = page.get(url, {"date": SUNDAY.isoformat(), "q": "لا يوجد أحد بهذا"}).content.decode()
    own_grade = page.get(url, {"date": SUNDAY.isoformat(), "grade": klass.grade}).content.decode()

    assert "غائبٌ بعذر" in by_name and "طالب الشعبة" not in by_name
    assert "لا شعبَ تطابق الترشيح" in nothing
    assert "غائبٌ بعذر" in own_grade


def test_a_filtered_export_matches_the_screen(school, klass, class_day, holder, client_as):
    from wings.ministry_selectors import narrow

    summary = ministry_summary(school, SUNDAY)
    narrowed = narrow(summary, q="غائبٌ بعذر")

    assert [m.name for m in narrowed.ministered] == ["غائبٌ بعذر"]
    assert narrowed.total.enrolled == summary.total.enrolled  # شعبتُه وحدَها وهي الوحيدة
    assert narrow(summary) is summary  # بلا ترشيحٍ لا نسخةَ ثانية
    other = narrow(summary, grade="G99")  # صفٌّ لا يضمّ شعبتَه
    assert other.ministered == [] and other.total.enrolled == 0
