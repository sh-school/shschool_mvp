"""حارسُ «ما يُعرض هو ما يُصدَّر» (W-20261113-003): كلُّ صفحةٍ فيها `export_button` تُفحص عبر رابط التصدير **الذي ترسمه**.

الخللُ الذي فاتَ الاختباراتِ ثلاثةَ أسابيع (W-20261113-001): اختبارُ التصدير يستدعي المسارَ بمعاملاتٍ صحيحةٍ مباشرةً فلا يمرّ بالرابط
المرسوم في الصفحة، فيفقد الرابطُ معاملاتِه (أو يخرج `amp;` في أسمائها) ويُصدَّر غيرُ المعروض وكلُّ اختبارٍ أخضر.

هنا: (1) كلُّ صفحةٍ في `PAGES` تُطلب بمعاملاتٍ نموذجيّة ويُستخرج رابطُ تصديرها من HTML، فيجب أن يحمل كلَّ معاملٍ بقيمته بلا `amp;`؛
(2) سقّاطةٌ: قالبٌ فيه `export_button` وصفحتُه ليست في `PAGES` ولا في `EXEMPT` بسببٍ مكتوب يُسقط الاختبار؛
(3) الملفُّ المُصدَّر عبر الرابط المستخرج نفسِه يطابق صفوفَ الصفحة (العددُ وأوّلُ عمود) — هنا سجلُّ السلوك اليوميّ والجدولُ الأسبوعيُّ
لمعلّمٍ؛ وسجلُّ الطلاب وزياراتُ العيادة ومتابعةُ الغياب في `test_export_matches_display_rows.py` وتقريرُ الجناح في
`test_export_matches_ministry.py` (لكلٍّ أجهزتُه التي لا يجوز أن تتسرّب إلى غيره).
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re
from dataclasses import dataclass
from io import BytesIO

import pytest
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from behavior.models import BehaviorInfraction
from operations.models import ScheduleSlot, Subject
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory
from tests.export_display_helpers import (
    data_rows,
    download,
    export_links,
    first_column,
    link_of,
    query_of,
)
from tests.test_period_register import klass, year  # noqa: F401
from tests.visual_snapshots import FIXED_NOW

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

ROOT = pathlib.Path(__file__).resolve().parent.parent
_BUTTON = re.compile(r'\{% export_button "(?:xlsx|pdf)"')


@dataclass(frozen=True)
class Page:
    """صفحةٌ تحمل أزرارَ تصدير: مسارُها، ومعاملاتُ ترشيحٍ نموذجيّة، ودورُ مَن يفتحها، وقوالبُها."""

    route: str
    params: dict[str, str]
    templates: tuple[str, ...]
    role: str = "principal_user"


#: سجلُّ الصفحات: اسمُ المسار + معاملاتٌ (معاملان فأكثر حيث تقبل الصفحةُ) + الدور.
#: القيمُ هنا ما تُعيده الصفحةُ حرفيّاً في رابطها؛ ما تُسقطه الصفحةُ حين لا تعرفه (صفٌّ أو جناحٌ بلا بيانات) لا يُرسَل.
PAGES: dict[str, Page] = {
    "student_affairs:student_list": Page(
        "student_affairs:student_list",
        {"q": "سالم", "grade": "G7", "section": "أ"},
        ("templates/student_affairs/student_list.html",),
    ),
    "clinic:visits_list": Page(
        "clinic:visits_list",
        {"date_from": "2026-11-01", "date_to": "2026-11-10", "student": "سالم"},
        ("templates/clinic/partials/visit_rows.html",),
        role="nurse_user",
    ),
    "daily_report": Page(
        "daily_report",
        {"date": "2026-11-10", "grade": "G7", "wing": "1", "q": "سالم", "sort": "name"},
        ("templates/operations/absence_followup/base.html",),
    ),
    "behavior:daily_report": Page(
        "behavior:daily_report",
        {"date": "2026-11-10", "grade": "G7"},
        ("templates/behavior/daily_report.html",),
    ),
    "wings:ministry_report": Page(
        "wings:ministry_report",
        {"date": "2026-11-10", "q": "سالم"},
        ("templates/wings/ministry_report.html",),
    ),
    "wings:exit_permit_list": Page(
        "wings:exit_permit_list",
        {"date": "2026-11-10"},
        ("templates/wings/exit_permits.html",),
    ),
    "student_affairs:tardiness_list": Page(
        "student_affairs:tardiness_list",
        {"date": "2026-11-10", "grade": "G7", "section": "أ"},
        ("templates/student_affairs/tardiness_list.html",),
    ),
    "student_affairs:enrolment_movements": Page(
        "student_affairs:enrolment_movements",
        {"kind": "transfer_in", "from": "2026-11-01", "to": "2026-11-10"},
        ("templates/student_affairs/movements.html",),
    ),
    "student_affairs:activity_list": Page(
        "student_affairs:activity_list",
        {"type": "club", "scope": "school"},
        ("templates/student_affairs/activity_list.html",),
    ),
    "staff_affairs:attendance_board": Page(
        "staff_affairs:attendance_board",
        {"date": "2026-10-05", "q": "سالم", "status": "unmarked"},
        ("templates/staff_affairs/attendance_board.html",),
    ),
    "staff_affairs:attendance_report": Page(
        "staff_affairs:attendance_report",
        {"month": "2026-10"},
        ("templates/staff_affairs/attendance_report.html",),
    ),
}

#: قوالبُ الجدول الأسبوعيّ: صفحتُه `/teacher/weekly-schedule/` تحتاج معلّماً بحصّةٍ فيغطّيها اختبارٌ خاصٌّ أدناه.
WEEKLY_TEMPLATES = ("templates/schedule/print_view.html",)

#: قوالبُ فيها `export_button` ولا تدخل سجلَّ الصفحات، **بسببٍ مكتوب** (المفتاحُ مسارُ القالب).
_NO_FILTERS = (
    "جدولُها المُصدَّر لا يقرأ معاملاتِ الشاشة: محدِّدُه `absence_rows` / `behavior_rows` على نافذةٍ ثابتة "
    "(آخر 30 يوماً / العام) يتجاهل `params`، فلا معاملَ ترشيحٍ يضيع من الرابط"
)
_BLANK_OR_FIXED = "زرُّها يصدّر قالباً فارغاً أو لائحةً ثابتةً لا تتبدّل بمعاملات الصفحة"
_PER_RECORD = (
    "صفحةُ سجلٍّ مفردٍ (طالب/واقعة/مستند) مفتاحُها في المسار لا في معاملاتٍ مرشِّحة، وزرُّها بلا استعلام"
)
_NEEDS_SETUP = "صفحةٌ تتطلّب إعداداً خاصّاً (مجموعُ تقييمٍ أو تقريرٌ أو ملفُّ استيراد أو معلّمُ إسناد) يغطّي تصديرَها اختبارُها الخاصّ"
_STATS = (
    "معاملاتُها (`year`, `month`) تُطبَّع على نافذة التقويم الدراسيّ وتُسقَط القيمةُ المجهولة، فلا قيمةَ نموذجيّةً "
    "صالحةً بلا تقويمٍ مبذور؛ ورابطُها يبنيه الخادمُ كلَّه في `export_query` من الاستعلام المطبَّع نفسِه"
)

EXEMPT: dict[str, str] = {
    **dict.fromkeys(
        (
            "templates/student_affairs/attendance_overview.html",
            "templates/student_affairs/behavior_overview.html",
        ),
        _NO_FILTERS,
    ),
    **dict.fromkeys(
        (
            "templates/behavior/dashboard.html",
            "templates/core/student_import_export.html",
        ),
        _BLANK_OR_FIXED,
    ),
    **dict.fromkeys(
        (
            "templates/behavior/student_profile.html",
            "templates/student_affairs/student_profile.html",
            "templates/breach/detail.html",
            "templates/quality/observation_list.html",
            "templates/quality/observation_detail.html",
            "templates/quality/observation_pdf_view.html",
            "templates/operations/absence_followup/viewer.html",
            "templates/parents/dashboard.html",
        ),
        _PER_RECORD,
    ),
    **dict.fromkeys(
        (
            "templates/assessments/class_gradebook.html",
            "templates/academic_management/reports/_base.html",
            "templates/reports/report_viewer.html",
            "templates/reports/index.html",
            "templates/quality/progress_report.html",
            "templates/analytics/kpi_dashboard.html",
            "templates/staging/import_grades.html",
            "templates/schedule/pages_view.html",
            "templates/wings/partials/record_panel.html",
        ),
        _NEEDS_SETUP,
    ),
    "templates/behavior/statistics.html": _STATS,
}


def _templates_with_buttons() -> set[str]:
    found: set[str] = set()
    base = ROOT / "templates"
    for path in base.rglob("*.html"):
        if _BUTTON.search(path.read_text(encoding="utf-8")):
            found.add("templates/" + path.relative_to(base).as_posix())
    return found


def _registered_templates() -> set[str]:
    return {t for page in PAGES.values() for t in page.templates} | set(WEEKLY_TEMPLATES)


def test_every_template_with_export_button_has_a_page_in_the_registry_or_a_written_exemption():
    unknown = sorted(_templates_with_buttons() - _registered_templates() - set(EXEMPT))
    assert not unknown, (
        "قالبٌ فيه export_button بلا صفحةٍ في سجلّ PAGES ولا استثناءٍ مسبَّبٍ في EXEMPT — "
        f"سجّل صفحتَه بمعاملاتٍ نموذجيّة أو اكتب سببَ الاستثناء: {unknown}"
    )


def test_registry_and_exemptions_do_not_go_stale():
    buttons = _templates_with_buttons()
    stale = sorted(set(EXEMPT) - buttons)
    assert not stale, f"استثناءٌ لم يعد له زرٌّ — احذفه من EXEMPT: {stale}"
    assert not set(EXEMPT) & _registered_templates(), "قالبٌ مسجَّلٌ ومستثنًى معاً"
    assert _registered_templates() <= buttons, "قالبٌ مسجَّلٌ بلا export_button"
    assert all(reason.strip() for reason in EXEMPT.values()), "استثناءٌ بلا سبب"


def test_every_registered_page_offers_at_least_two_filters_unless_it_accepts_one():
    one_filter = {"wings:exit_permit_list", "staff_affairs:attendance_report"}
    thin = sorted(k for k, p in PAGES.items() if len(p.params) < 2 and k not in one_filter)
    assert not thin, f"صفحةٌ بمعاملٍ واحدٍ فقط وهي تقبل أكثر: {thin}"


@pytest.mark.parametrize("key", sorted(PAGES))
def test_export_links_carry_every_filter_the_page_was_given(key, request, client_as):
    page = PAGES[key]
    user = request.getfixturevalue(page.role)
    resp = client_as(user).get(reverse(page.route), page.params)
    assert resp.status_code == 200, (key, resp.status_code)

    links = export_links(resp.content.decode())
    assert links, f"{key}: لا رابطَ تصديرٍ في الصفحة"
    for kind, href in links:
        query = query_of(href)
        assert not [k for k in query if "amp;" in k], (key, kind, href)
        for name, value in page.params.items():
            assert query.get(name) == [value], (key, kind, name, href)


# ── الجدولُ الأسبوعيّ لمعلّم: العنوانُ باسمه والاسمُ يحمل الأسبوع ──────────────────────────────


def test_teacher_weekly_schedule_file_is_titled_by_the_teacher_and_names_the_week(
    client_as, principal_user, teacher_user, class_group
):
    ScheduleSlot.objects.create(
        school=class_group.school,
        class_group=class_group,
        teacher=teacher_user,
        subject=Subject.objects.create(school=class_group.school, name_ar="علوم"),
        day_of_week=0,
        period_number=1,
        start_time=dt.time(7, 30),
        end_time=dt.time(8, 15),
        academic_year=class_group.academic_year,
    )
    client = client_as(principal_user)
    resp = client.get(
        "/teacher/weekly-schedule/",
        {
            "view": "teacher",
            "teacher": str(teacher_user.id),
            "source": "actual",
            "week": "2026-11-08",
            "paper": "a4",
        },
    )
    assert resp.status_code == 200

    content, filename = download(client, principal_user, link_of(resp.content.decode(), "xlsx"))

    sheet = load_workbook(BytesIO(content)).active
    heading = " ".join(str(c.value) for row in sheet.iter_rows(max_row=4) for c in row if c.value)
    assert teacher_user.full_name in heading, heading
    assert "2026-11-08" in filename, filename


# ── السلوك اليوميّ: ملفُّ الرابط يطابق الصفحةَ مرشَّحةً بالصفّ ────────────────────────────────


def test_behavior_daily_file_from_the_page_link_matches_the_filtered_page(
    client_as, principal_user, school, year, klass
):
    today = timezone.localdate(FIXED_NOW)
    other = ClassGroupFactory(
        school=school, grade="G8", section="1", level_type="prep", academic_year=year
    )
    for group in (klass, other):
        pupil = UserFactory(full_name=f"طالب سلوك {group.grade}")
        StudentEnrollmentFactory(student=pupil, class_group=group, enrolled_at=dt.date(2026, 9, 1))
        inf = BehaviorInfraction.objects.create(
            school=school, student=pupil, session=None, auto_rule="", level=1, description="x"
        )
        # `auto_now_add` يقرأ تاريخَ النظام الحقيقيّ لا الساعةَ المثبَّتة، فنضبط يومَ الكتابة على يوم الاختبار.
        BehaviorInfraction.objects.filter(pk=inf.pk).update(date=today)

    client = client_as(principal_user)
    resp = client.get(
        reverse("behavior:daily_report"), {"date": today.isoformat(), "grade": klass.grade}
    )
    assert resp.status_code == 200
    shown = sorted(str(row["student"]) for row in resp.context["rows"])
    assert shown == [f"طالب سلوك {klass.grade}"], "الترشيحُ بالصفّ يضيّق الصفحةَ إلى صفٍّ واحد"

    content, _ = download(client, principal_user, link_of(resp.content.decode(), "xlsx"))

    rows = data_rows(content)
    assert len(rows) == len(shown)
    assert first_column(rows) == shown
