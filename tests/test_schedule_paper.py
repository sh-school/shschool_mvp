"""ورقةُ الجدول الأسبوعيّ: «11/2»، والفسحةُ والصلاةُ بتوقيتهما، والجدولُ يملأ الورقة.

قرارات 2026-09-14 (operations/schedule_paper.py). والأجراسُ من `seed_time_bands`
لا من أرقامٍ مكتوبةٍ هنا: الاختبارُ يتبع الجرسَ المعتمد إن تغيّر.
"""

import datetime as dt

import pytest
from django.core.management import call_command
from django.urls import reverse

from core.models import ClassGroup, TimeBand
from operations.bells import REGULAR, THURSDAY
from operations.models import ScheduleSlot, Subject
from operations.schedule_paper import (
    bell_tables,
    breaks_after,
    grid_to_days,
    paper_geometry,
    teacher_bands_by_day,
    week_layout,
)
from operations.services import ScheduleService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

YEAR = "2026-2027"


# ── الاسمُ المختصر ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("grade", "section", "label"),
    [("G11", "2", "11/2"), ("G7", "1", "7/1"), ("G7", "07/ESE", "7/ESE"), ("G12", "4", "12/4")],
)
def test_the_short_label_is_grade_slash_section_without_zero_track_or_year(grade, section, label):
    klass = ClassGroup(grade=grade, section=section, track="technology", academic_year=YEAR)
    assert klass.short_label == label


def test_the_class_heading_keeps_the_track_but_not_the_year():
    klass = ClassGroup(grade="G11", section="2", track="technology", academic_year=YEAR)
    assert klass.label_with_track == "11/2 — تكنولوجي"
    assert YEAR not in klass.label_with_track


# ── مواضعُ الاستراحات ─────────────────────────────────────────────────


@pytest.fixture
def bands(db, school):
    call_command("seed_time_bands")
    return {b.code: b for b in TimeBand.objects.filter(school=school)}


def _afters(bell):
    return [(after, item.label) for after, item in breaks_after(bell)]


@pytest.mark.django_db
def test_breaks_sit_after_the_last_period_that_ends_before_them(school, bands):
    tables = bell_tables(school)

    assert _afters(tables[REGULAR]["ground"]) == [(3, "الفسحة"), (6, "الصلاة")]
    assert _afters(tables[THURSDAY]["ground"]) == [(3, "الفسحة"), (5, "الصلاة")]
    assert _afters(tables[REGULAR]["secondary"]) == [(4, "الفسحة"), (7, "الصلاة")]
    assert _afters(tables[THURSDAY]["ninth"]) == [(3, "الفسحة"), (6, "الصلاة")]


def _empty_days():
    return [[[] for _ in range(7)] for _ in range(5)]


@pytest.mark.django_db
def test_a_ground_class_gets_a_prayer_column_that_is_empty_on_thursday(school, bands):
    """الصلاةُ بعد السادسة من الأحد إلى الأربعاء وبعد الخامسة يومَ الخميس:
    عمودان، كلٌّ منهما فارغٌ في أيّام الآخر — والترتيبُ الزمنيُّ صادق."""
    week = week_layout(_empty_days(), [["ground"]] * 5, bell_tables(school))
    order = [c["number"] if c["kind"] == "period" else f"b{c['after']}" for c in week["columns"]]

    assert order == [1, 2, 3, "b3", 4, 5, "b5", 6, "b6", 7]
    sunday, thursday = week["lines"][0]["entries"], week["lines"][4]["entries"]
    after_5, after_6 = order.index("b5"), order.index("b6")
    assert not sunday[after_5]["items"] and sunday[after_6]["items"][0].label == "الصلاة"
    assert thursday[after_5]["items"][0].label == "الصلاة" and not thursday[after_6]["items"]
    assert week["lines"][0]["day"] == "الأحد"


@pytest.mark.django_db
def test_a_teacher_in_two_bells_sees_both_bells_named(school, bands):
    """قرار 2026-09-14: الجرسان كاملان مع اسم الجرس — لا طابقٌ غالبٌ ولا حذف."""
    tables = bell_tables(school)
    week = week_layout(_empty_days(), [["ground", "secondary"]] * 5, tables)
    sunday = week["lines"][0]["entries"]
    breaks = [item for entry in sunday if entry["kind"] == "break" for item in entry["items"]]

    fasahat = [item for item in breaks if item.label == "الفسحة"]
    assert [(f.start, bool(f.band)) for f in fasahat] == [
        (dt.time(9, 35), True),
        (dt.time(10, 25), True),
    ], "فسحتان بوقتين، ولكلٍّ اسمُ جرسه"
    assert [f.band for f in fasahat] == ["الأرضيّ", "الثانويّ"], "لا «الطابق» اسماً لجرس"


@pytest.mark.django_db
def test_a_break_shared_by_two_bells_names_both(school, bands):
    """التاسعُ والثانويُّ فسحتُهما واحدةٌ من الأحد إلى الأربعاء: تُكتب مرّةً باسميهما."""
    week = week_layout(_empty_days(), [["ground", "ninth", "secondary"]] * 5, bell_tables(school))
    sunday = week["lines"][0]["entries"]
    upper = [
        item
        for entry in sunday
        if entry["kind"] == "break"
        for item in entry["items"]
        if item.label == "الفسحة" and item.start == dt.time(10, 25)
    ]
    assert len(upper) == 1 and upper[0].band == "التاسع · الثانويّ"


@pytest.mark.django_db
def test_a_class_without_a_bell_gets_no_break_columns(school, bands):
    week = week_layout(_empty_days(), [[]] * 5, bell_tables(school))
    assert [c["kind"] for c in week["columns"]] == ["period"] * 7


# ── المقاس ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("paper", ["a4", "a3"])
@pytest.mark.parametrize("orient", ["landscape", "portrait"])
@pytest.mark.parametrize("with_who", [True, False])
def test_the_rows_fill_what_the_bands_leave(paper, orient, with_who):
    geo = paper_geometry(paper, orient, with_who=with_who)

    used = geo.bands_h + geo.rows * geo.row_h
    assert geo.content_h - geo.safety - 0.5 <= used <= geo.content_h, "ما بقي للصفوف كلُّه"
    assert geo.row_h >= 24, "صفٌّ يسع المادّةَ والشعبةَ والتوقيت"
    assert all("," not in value for value in geo.css.values()), "لا فاصلةَ عشريّةً في CSS"


# ── الورقةُ نفسُها ───────────────────────────────────────────────────


@pytest.fixture
def paper_lessons(school, bands):
    user = UserFactory(full_name="معلّمُ الورقة")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    upper = ClassGroupFactory(
        school=school,
        grade="G10",
        section="3",
        level_type="sec",
        academic_year=YEAR,
        time_band=bands["secondary"],
    )
    subject = Subject.objects.create(school=school, name_ar="التربية الإسلامية", code="ISL")
    ScheduleSlot.objects.create(
        school=school,
        teacher=user,
        class_group=upper,
        subject=subject,
        day_of_week=1,
        period_number=2,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        academic_year=YEAR,
        is_active=True,
    )
    return user, upper


@pytest.mark.django_db
def test_the_teacher_paper_writes_the_short_label_and_the_breaks(
    client, principal_user, paper_lessons
):
    teacher, upper = paper_lessons
    client.force_login(principal_user)

    body = client.get(
        reverse("schedule_pages_paper"), {"year": YEAR, "teacher": teacher.id}
    ).content.decode()

    assert '<div class="slot-meta">10/3</div>' in body
    assert str(upper) not in body and "(2026-2027)" not in body
    assert "الفسحة" in body and "10:25" in body and "10:45" in body
    assert "flex: 1 1 auto" not in body, "الجدولُ بارتفاع صفٍّ صريح لا بعنصرٍ مرن"


@pytest.mark.django_db
def test_the_printed_schedule_uses_the_same_grid(client, principal_user, paper_lessons):
    teacher, _ = paper_lessons
    client.force_login(principal_user)

    body = client.get(
        reverse("schedule_print"),
        {"view": "teacher", "teacher": teacher.id, "year": YEAR},
        HTTP_HOST="localhost",
    ).content.decode()

    assert 'class="week-grid"' in body and "10/3" in body and "الصلاة" in body


@pytest.mark.django_db
def test_the_service_keeps_seven_cells_beside_the_week(school, paper_lessons):
    """`cells` باقيةٌ سبعاً (يقرؤها غيرُ الورقة)، والأعمدةُ الجديدةُ في `week`."""
    row = ScheduleService.teacher_pages(school, YEAR)[0]
    assert all(len(line["cells"]) == 7 for line in row["by_day"])
    assert row["week"]["break_count"] == 2
    days = grid_to_days(ScheduleService.get_weekly_schedule(school, row["teacher"], None, YEAR))
    assert teacher_bands_by_day(days, ScheduleService._band_codes(school))[1] == ["secondary"]


@pytest.mark.django_db
@pytest.mark.parametrize(("paper", "orient"), [("a4", "landscape"), ("a3", "portrait")])
def test_the_pdf_is_one_full_page_per_teacher(client, principal_user, paper_lessons, paper, orient):
    """الامتلاءُ بلا فيضان: كسرُ ملّيمترٍ زائدٌ يُخرج صفحةً ثانية في WeasyPrint."""
    pdfium = pytest.importorskip("pypdfium2")
    pytest.importorskip("weasyprint")
    teacher, _ = paper_lessons
    client.force_login(principal_user)

    response = client.get(
        reverse("schedule_pages_pdf"),
        {"year": YEAR, "teacher": teacher.id, "paper": paper, "orient": orient},
    )
    if response.get("Content-Type") != "application/pdf":
        pytest.skip("مولّدُ PDF غيرُ متاحٍ في هذه البيئة")

    pdf = pdfium.PdfDocument(response.content)
    try:
        assert len(pdf) == 1
    finally:
        pdf.close()
