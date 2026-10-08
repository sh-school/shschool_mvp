"""امتثالُ الإجازات لقانون الموارد البشرية 15/2016 (W-20261001-007 و008 و010 و011).

النصوصُ الحرفيّة: ``AAdocs/ministry_data/2026_2027/02d_hr_law_leaves_verbatim.md``، وفي
اسم كلّ اختبارٍ المادّةُ التي يحرسها. التاريخُ المستعملُ أسبوعُه: الأحد 2026-10-04
عمل، الجمعة 10-09 والسبت 10-10 عطلة.
"""

import datetime as dt
import re
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from staff_affairs.forms import LeaveRequestForm
from staff_affairs.leave_rules import M61_TYPES, count_leave_days
from staff_affairs.models import LEAVE_TYPES, LeaveBalance
from staff_affairs.services import LeaveService
from tests.conftest import MembershipFactory, SchoolFactory, UserFactory

LAW = Path(__file__).resolve().parent.parent / (
    "AAdocs/ministry_data/2026_2027/02d_hr_law_leaves_verbatim.md"
)
SUN = dt.date(2026, 10, 4)
PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n"


def _request(school, staff, leave_type, start, end, days, attachment=None):
    return LeaveService.create_leave_request(
        school=school,
        staff=staff,
        leave_type=leave_type,
        start_date=start,
        end_date=end,
        days_count=days,
        reason="سبب",
        attachment=attachment,
    )


@pytest.fixture
def setup(db):
    school = SchoolFactory()
    staff = UserFactory()
    MembershipFactory(user=staff, school=school)
    return school, staff, UserFactory()


# ── 011: LEAVE_TYPES مقابل م61 الحرفيّة ──────────────────────────────


def _m61_items():
    text = LAW.read_text(encoding="utf-8")
    block = text[text.index("المادة 61") : text.index("المادة 62")]
    return {
        int(n): label.strip()
        for n, label in re.findall(r"^\s*(\d+)-\s*(.+?)\s*\.?\s*$", block, re.M)
    }


def test_m61_the_law_text_still_lists_seventeen_types():
    """م61: سبعةَ عشر نوعاً — فإن تغيّر النصُّ انتبه هذا الحارس."""
    assert sorted(_m61_items()) == list(range(1, 18))


def test_m61_every_listed_type_exists_in_leave_types():
    """م61(1..17): لكلّ بندٍ نوعٌ في LEAVE_TYPES، فلا تُسجَّل إجازةٌ تحت «أخرى»."""
    codes = {code for code, _ in LEAVE_TYPES}
    assert set(M61_TYPES) == set(_m61_items())
    assert set(M61_TYPES.values()) <= codes


def test_m61_leave_types_has_no_unexplained_extras():
    """ما زاد على م61 مسمّى: «work_injury» (م71) و«official» (إيفاد) و«other» — وغيرُه يُرفض."""
    extras = {code for code, _ in LEAVE_TYPES} - set(M61_TYPES.values())
    assert extras == {"work_injury", "official", "other"}


@pytest.mark.parametrize("code", ["spouse_companion", "mahram", "exceptional", "exams"])
def test_m61_newly_added_types_fit_the_column(code):
    """م61(10،11،13،16): الرمزُ يسع حقلَ leave_type (20)."""
    assert len(code) <= 20


# ── 008: أيّام العمل لا التقويميّة ───────────────────────────────────


def test_m65_emergency_over_a_weekend_counts_working_days_only():
    """م65: «عشرة أيام عمل» — الأحد→الأحد (8 تقويميّة) عملُها 6 (يستبعد الجمعة والسبت)."""
    assert count_leave_days("emergency", SUN, SUN + dt.timedelta(days=7)) == 6


def test_m66_sick_counts_working_days():
    """م66: «ثلاثة أيام عمل متصلة» — الخميس→الأحد 2 يومَ عمل (الخميس والأحد)."""
    assert count_leave_days("sick", dt.date(2026, 10, 8), dt.date(2026, 10, 11)) == 2


def test_m76_marriage_counts_calendar_days():
    """م76: «خمسة عشر يوماً» — الأيّامُ تقويميّة لا أيّامُ عمل."""
    assert count_leave_days("marriage", SUN, SUN + dt.timedelta(days=14)) == 15


def test_m62_official_holiday_inside_annual_is_not_charged(db):
    """م62: «إذا تخللت إجازة الموظف أيام العطلات الرسمية فتضاف أيام بعددها» — لا تُخصم."""
    from core.models import AcademicYear, CalendarEvent

    school = SchoolFactory()
    year = AcademicYear.objects.create(
        school=school,
        name="2026-2027",
        start_date=dt.date(2026, 8, 23),
        end_date=dt.date(2027, 6, 30),
    )
    CalendarEvent.objects.create(
        academic_year=year,
        event_type="break",
        name="عطلة",
        start_date=dt.date(2026, 10, 5),
        end_date=dt.date(2026, 10, 6),
        audience="both",
    )
    # الأحد→الخميس 5 أيام عمل، منها الاثنان والثلاثاء عطلةٌ رسميّة
    assert count_leave_days("annual", SUN, dt.date(2026, 10, 8), school) == 3


def test_m60_a_students_only_break_is_not_a_staff_holiday(db):
    """م60: العطلة الرسميّة للموظّف؛ إجازةُ الطلبة وحدَهم يومُ دوامٍ للكادر."""
    from core.models import AcademicYear, CalendarEvent

    school = SchoolFactory()
    year = AcademicYear.objects.create(
        school=school,
        name="2026-2027",
        start_date=dt.date(2026, 8, 23),
        end_date=dt.date(2027, 6, 30),
    )
    CalendarEvent.objects.create(
        academic_year=year,
        event_type="break",
        name="طلبة",
        start_date=dt.date(2026, 10, 5),
        end_date=dt.date(2026, 10, 5),
        audience="students",
    )
    assert count_leave_days("emergency", SUN, dt.date(2026, 10, 6), school) == 3


def _form(leave_type, start, end, **files):
    return LeaveRequestForm(
        data={
            "staff_id": "00000000-0000-0000-0000-000000000001",
            "leave_type": leave_type,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "reason": "سبب",
        },
        files=files,
    )


def test_m66_form_days_count_skips_the_weekend():
    """م66 في النموذج: days_count أيّامُ عمل."""
    form = _form("sick", dt.date(2026, 10, 8), dt.date(2026, 10, 11))
    assert form.is_valid(), form.errors
    assert form.cleaned_data["days_count"] == 2


def test_m66_form_rejects_a_period_that_is_all_weekend():
    """م66: لا يومَ عملٍ في الفترة فلا إجازةَ تُحتسب."""
    form = _form("sick", dt.date(2026, 10, 9), dt.date(2026, 10, 10))
    assert not form.is_valid()


# ── 007: السقوف والأرصدة ─────────────────────────────────────────────


def test_m65_form_rejects_twelve_working_days_of_emergency():
    """م65: عارضةٌ لا تتجاوز عشرة أيام عمل — 12 يوم عملٍ تُرفض في النموذج."""
    form = _form("emergency", SUN, SUN + dt.timedelta(days=15))  # 16 تقويميّاً = 12 عملاً
    assert not form.is_valid()
    assert any("10" in e for e in form.non_field_errors())


def test_m65_ten_working_days_of_emergency_is_accepted():
    """م65: العاشرُ مقبول — الأحد→الخميس التالي (فيه 9 عمل)؛ والحدّ بالضبط 10."""
    form = _form("emergency", SUN, dt.date(2026, 10, 15))  # أحد..خميس=5 + أحد..خميس=5
    assert form.is_valid(), form.errors
    assert form.cleaned_data["days_count"] == 10


def test_m65_second_emergency_request_exceeding_the_year_cap_is_refused_at_approval(setup):
    """م65: عشرة أيام عمل «في السنة» — 6 ثم 6 يُرفض الثاني عند الاعتماد."""
    school, staff, reviewer = setup
    first = _request(school, staff, "emergency", SUN, SUN, 6)
    LeaveService.review_leave(first, "approved", reviewer)
    second = _request(school, staff, "emergency", SUN, SUN, 6)
    with pytest.raises(ValueError, match="م65"):
        LeaveService.review_leave(second, "approved", reviewer)
    second.refresh_from_db()
    assert second.status == "pending"
    assert LeaveBalance.objects.get(staff=staff, leave_type="emergency").used_days == 6


def test_m65_legacy_balance_row_seeded_with_thirty_does_not_lift_the_cap(setup):
    """م65: صفوفٌ قديمةٌ بُذرت total_days=30 لكلّ نوعٍ — السقفُ القانونيّ يغلبها."""
    school, staff, reviewer = setup
    leave = _request(school, staff, "emergency", SUN, SUN, 11)
    LeaveBalance.objects.create(
        school=school,
        staff=staff,
        academic_year=leave.academic_year,
        leave_type="emergency",
        total_days=30,
    )
    with pytest.raises(ValueError, match="م65"):
        LeaveService.review_leave(leave, "approved", reviewer)


def test_m75_hajj_is_once_per_service(setup):
    """م75: «لمرة واحدة طوال مدة خدمته» — حجٌّ ثانٍ يُرفض ولو في عامٍ آخر."""
    school, staff, reviewer = setup
    first = _request(school, staff, "hajj", SUN, SUN, 21)
    LeaveService.review_leave(first, "approved", reviewer)
    second = _request(school, staff, "hajj", SUN, SUN, 21)
    second.academic_year = "2030-2031"
    second.save(update_fields=["academic_year"])
    with pytest.raises(ValueError, match="م75"):
        LeaveService.review_leave(second, "approved", reviewer)


def test_m75_hajj_is_capped_at_twenty_one_days(setup):
    """م75: واحدٌ وعشرون يوماً — 22 يُرفض عند الاعتماد."""
    school, staff, reviewer = setup
    leave = _request(school, staff, "hajj", SUN, SUN, 22)
    with pytest.raises(ValueError, match="م75"):
        LeaveService.review_leave(leave, "approved", reviewer)


def test_m76_marriage_is_capped_at_fifteen_days_in_form():
    """م76: خمسةَ عشر يوماً — 16 تقويميّاً يُرفض (والمستندُ مرفق)."""
    doc = SimpleUploadedFile("c.pdf", PDF, content_type="application/pdf")
    form = _form("marriage", SUN, SUN + dt.timedelta(days=15), attachment=doc)
    assert not form.is_valid()
    assert any("15" in e for e in form.non_field_errors())


def test_m76_marriage_over_cap_is_refused_at_approval_too(setup):
    """م76: الحارسُ في الخدمة لا في النموذج وحدَه — 16 يوماً تُرفض عند الاعتماد."""
    school, staff, reviewer = setup
    doc = SimpleUploadedFile("c.pdf", PDF, content_type="application/pdf")
    leave = _request(school, staff, "marriage", SUN, SUN, 16, attachment=doc)
    with pytest.raises(ValueError, match="م76"):
        LeaveService.review_leave(leave, "approved", reviewer)


def test_m62_annual_default_balance_is_thirty_and_overrun_is_refused(setup):
    """م62: رصيدُ السنويّة الافتراضيّ 30 (الدرجات الأخرى) — 31 يُرفض لا يُخفى بـmax(0,..)."""
    school, staff, reviewer = setup
    leave = _request(school, staff, "annual", SUN, SUN, 31)
    with pytest.raises(ValueError, match="م62"):
        LeaveService.review_leave(leave, "approved", reviewer)


def test_m62_annual_uses_the_stored_balance_for_higher_grades(setup):
    """م62: 45 يوماً للدرجة السابعة فأعلى — الرصيدُ المخزَّن يُحترم فيُقبل 40."""
    school, staff, reviewer = setup
    leave = _request(school, staff, "annual", SUN, SUN, 40)
    LeaveBalance.objects.create(
        school=school,
        staff=staff,
        academic_year=leave.academic_year,
        leave_type="annual",
        total_days=45,
    )
    LeaveService.review_leave(leave, "approved", reviewer)
    assert LeaveBalance.objects.get(staff=staff, leave_type="annual").used_days == 40


def test_m66_sick_has_no_platform_cap_medical_authority_decides(setup):
    """م66: ما زاد على 15 يعتمده الجهةُ الطبّيّة المختصّة — المنصّةُ لا ترفضه."""
    school, staff, reviewer = setup
    leave = _request(school, staff, "sick", SUN, SUN, 40)
    LeaveService.review_leave(leave, "approved", reviewer)
    leave.refresh_from_db()
    assert leave.status == "approved"


# ── 010: المستند اللازم ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("leave_type", "article"),
    [("marriage", "م76"), ("maternity", "م73"), ("iddah", "م77"), ("exams", "م91")],
)
def test_required_document_form_rejects_a_request_without_attachment(leave_type, article):
    """م76 وم73 وم77 ولائحة م91: بلا مرفقٍ يُرفض الطلبُ ويُذكر المرجع."""
    form = _form(leave_type, SUN, SUN + dt.timedelta(days=1))
    assert not form.is_valid()
    assert any(article in e for e in form.non_field_errors())


@pytest.mark.parametrize("leave_type", ["marriage", "maternity", "iddah", "exams"])
def test_required_document_form_accepts_the_request_with_attachment(leave_type):
    """م76 وم73 وم77 ولائحة م91: بمرفقٍ سليمٍ يُقبل."""
    doc = SimpleUploadedFile("proof.pdf", PDF, content_type="application/pdf")
    form = _form(leave_type, SUN, SUN + dt.timedelta(days=1), attachment=doc)
    assert form.is_valid(), form.errors


@pytest.mark.parametrize("leave_type", ["marriage", "maternity", "iddah", "exams"])
def test_required_document_service_refuses_without_attachment(setup, leave_type):
    """المستندُ مشروطٌ في الخدمة كذلك — فمن يتجاوز النموذجَ لا يتجاوز الشرط."""
    school, staff, _ = setup
    with pytest.raises(ValueError):
        _request(school, staff, leave_type, SUN, SUN, 1)


@pytest.mark.parametrize("leave_type", ["annual", "emergency", "sick", "hajj", "unpaid"])
def test_no_document_is_required_for_other_types(leave_type):
    """لا نصَّ في القانون يشترط مرفقاً لهذه الأنواع — لا نُضيف شرطاً من عندنا."""
    form = _form(leave_type, SUN, SUN)
    assert form.is_valid(), form.errors
