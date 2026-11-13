"""استيرادُ مواضع حصص aSc من PDF — محلِّلٌ على صفحاتٍ مصطنعة، وأمرٌ يكتب مسودّةً لا تُفعَّل.

لا PDF حقيقيّاً هنا ولا اسمَ حقيقيّاً: الصفحةُ كائنٌ بخطوطٍ وكلماتٍ مرسومةٍ بالإحداثيّات،
والكلمةُ العربيّةُ تُسلَّم معكوسةً كما يستخرجها pdfplumber.
"""

import io
import json
from contextlib import contextmanager
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from academic_management import asc_pdf
from core.academic_calendar import academic_year_for_school
from operations.models import ScheduleGeneration, ScheduleSlot, Subject, SubjectClassAssignment
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

XS = [100 * n for n in range(1, 10)]  # تسعُ قيم x: ثمانيةُ أعمدة، أيمنُها للأيّام
YS = [100 * n for n in range(1, 8)]  # سبعُ قيم y: العنوانُ وخمسةُ أيّام
TAG = "نصفان-7.1-فنون"


class FakePage:
    def __init__(self, lines: list[dict], words: list[dict]) -> None:
        self.lines = lines
        self._words = words

    def extract_words(self) -> list[dict]:
        return self._words


def _raw(text: str) -> str:
    """كما يُستخرج من PDF: العربيّةُ معكوسةٌ، واللاتينيّةُ كما هي."""
    return text[::-1] if any("؀" <= c <= "ۿ" for c in text) else text


def _word(text: str, x: float, y: float) -> dict:
    return {"text": _raw(text), "x0": x - 10, "x1": x + 10, "top": y - 5, "bottom": y + 5}


def _lines(merged: set[tuple[int, int]] = frozenset(), size=(9, 7)) -> list[dict]:
    """خطوطُ الشبكة؛ و`merged` = {(يوم، فهرسُ الحدّ)} للفواصل الغائبة."""
    xs, ys = XS[: size[0]], YS[: size[1]]
    lines = [{"x0": xs[0], "x1": xs[-1], "top": y, "bottom": y} for y in ys]
    for row in range(len(ys) - 1):
        for index, x in enumerate(xs):
            if row >= 1 and (row - 1, index) in merged:
                continue
            lines.append({"x0": x, "x1": x, "top": ys[row], "bottom": ys[row + 1]})
    return lines


def _cell_words(day: int, period: int, text: list[str]) -> list[dict]:
    col = 7 - period
    cx, cy = (XS[col] + XS[col + 1]) / 2, YS[day + 1] + 10
    return [_word(t, cx, cy + 20 * i) for i, t in enumerate(text)]


def teacher_page(name: str, cells: list[tuple], size=(9, 7)) -> FakePage:
    """cells: (يوم، حصّة، رمزُ الشعبة، المادّة[، عددُ الحصص المدموجة])."""
    words = [_word(w, 300 - 40 * i, 50) for i, w in enumerate(name.split())]
    merged: set[tuple[int, int]] = set()
    for day, period, code, subject, *span in cells:
        extra = span[0] if span else 1
        words += _cell_words(day, period, [code, subject, "R12"])
        merged |= {(day, 8 - period + k) for k in range(extra - 1)}
    return FakePage(_lines(merged, size), words)


def class_page(code: str, cells: list[tuple]) -> FakePage:
    words = [_word(code, 300, 50)]
    merged: set[tuple[int, int]] = set()
    for day, period, *span in cells:
        extra = span[0] if span else 1
        words += _cell_words(day, period, ["مادة"])
        merged |= {(day, 8 - period + k) for k in range(extra - 1)}
    return FakePage(_lines(merged), words)


# ── المحلِّل ────────────────────────────────────────────────────────────


def test_fix_word_reverses_arabic_then_nfkc():
    assert asc_pdf.fix_word("معلم"[::-1]) == "معلم"
    assert asc_pdf.fix_word("ﻡ"[::-1]) == "م"  # شكلُ عرضٍ يُوحَّد إلى الحرف الأصل
    assert asc_pdf.fix_word("R12") == "R12"
    assert asc_pdf.fix_word("7.1") == "7.1"


def test_teacher_page_maps_day_period_and_ignores_room():
    page = teacher_page("معلم الف", [(0, 1, "7.1", "رياضيات"), (4, 7, "8.2", "علوم عامة")])
    parsed = asc_pdf.parse_teacher_page(page)
    assert parsed.name == "معلم الف"
    # الحصّةُ الأولى في أقصى اليمين من أعمدة الحصص، والسابعةُ في أقصى اليسار
    assert (0, 1, "7.1", "رياضيات") in parsed.lessons
    assert (4, 7, "8.2", "علوم عامة") in parsed.lessons
    assert len(parsed.lessons) == 2


def test_title_words_are_dropped_from_name():
    page = teacher_page("جدول معلم باء", [(1, 2, "7.1", "علوم")])
    assert asc_pdf.parse_teacher_page(page, ("جدول",)).name == "معلم باء"


def test_missing_vertical_separator_makes_a_double_period():
    page = teacher_page("معلم الف", [(2, 4, "7.1", "علوم", 2)])
    parsed = asc_pdf.parse_teacher_page(page)
    assert sorted(parsed.lessons) == [(2, 3, "7.1", "علوم"), (2, 4, "7.1", "علوم")]


def test_separator_missing_in_another_row_does_not_merge_this_one():
    page = teacher_page("معلم الف", [(0, 4, "7.1", "علوم", 2), (1, 4, "7.1", "علوم")])
    parsed = asc_pdf.parse_teacher_page(page)
    assert sorted(parsed.lessons) == [
        (0, 3, "7.1", "علوم"),
        (0, 4, "7.1", "علوم"),
        (1, 4, "7.1", "علوم"),
    ]


def test_class_page_collects_occupied_cells():
    parsed = asc_pdf.parse_class_page(class_page("7.1", [(0, 1), (3, 5, 2)]))
    assert parsed.class_code == "7.1"
    assert parsed.slots == {(0, 1), (3, 5), (3, 4)}


def test_unexpected_grid_is_an_error_not_a_guess():
    with pytest.raises(asc_pdf.AscPdfError):
        asc_pdf.parse_teacher_page(teacher_page("معلم الف", [], size=(8, 7)))


def test_cell_without_class_code_is_an_error():
    page = FakePage(_lines(), [_word("معلم", 300, 50), *_cell_words(0, 1, ["رياضيات"])])
    with pytest.raises(asc_pdf.AscPdfError):
        asc_pdf.parse_teacher_page(page)


def test_class_page_reads_code_from_hc_title_word():
    page = class_page("HC.11.2", [(0, 1)])
    assert asc_pdf.parse_class_page(page).class_code == "11.2"


def test_class_page_without_code_has_empty_code():
    page = FakePage(_lines(), [_word("صفحة", 300, 50), *_cell_words(0, 1, ["مادة"])])
    parsed = asc_pdf.parse_class_page(page)
    assert parsed.class_code == "" and parsed.slots == {(0, 1)}


def test_teacher_cell_drops_dotted_room_code_from_subject():
    page = FakePage(
        _lines(),
        [_word("معلم", 300, 50), *_cell_words(0, 1, ["7.1", "علوم", "عامة", "HC.12.4", "LAB1"])],
    )
    assert asc_pdf.parse_teacher_page(page).lessons == ((0, 1, "7.1", "علوم عامة"),)


def test_name_is_the_biggest_font_title_line_only():
    school_line = [
        {**_word(w, 300 - 40 * i, 20), "size": 8} for i, w in enumerate(["مدرسة", "نموذج"])
    ]
    name_line = [{**_word(w, 300 - 40 * i, 50), "size": 14} for i, w in enumerate(["معلم", "الف"])]
    page = FakePage(_lines(), [*school_line, *name_line, *_cell_words(0, 1, ["7.1", "علوم"])])
    assert asc_pdf.parse_teacher_page(page).name == "معلم الف"


# ── الأمر ───────────────────────────────────────────────────────────────


class FakePdf:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages


@pytest.fixture(autouse=True)
def _no_private_rules(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMETABLE_NAME_RULES_FILE", str(tmp_path / "absent.json"))


@pytest.fixture
def year(school):
    return academic_year_for_school(school)


@pytest.fixture
def world(school, year):
    """شعبةٌ 7.1، معلّمان مصطنعان، مادّتان، وإسنادان: رياضيات (حصّتان) وفنون (حصّة)."""
    group = ClassGroupFactory(school=school, grade="G7", section="1", academic_year=year)
    role = RoleFactory(school=school, name="teacher")
    people = {}
    for n, name in enumerate(["معلم الف", "معلم باء"], start=1):
        user = UserFactory(full_name=name, national_id=f"2900000000{n}", phone=f"+9745500000{n}")
        MembershipFactory(user=user, school=school, role=role)
        people[name] = user
    math = Subject.objects.create(school=school, name_ar="رياضيات")
    arts = Subject.objects.create(school=school, name_ar="فنون")

    def assign(teacher, subject, periods, group_tag=""):
        return SubjectClassAssignment.objects.create(
            school=school,
            class_group=group,
            subject=subject,
            teacher=teacher,
            weekly_periods=periods,
            academic_year=year,
            parallel_group=group_tag,
        )

    return {"group": group, "people": people, "math": math, "arts": arts, "assign": assign}


@pytest.fixture
def run(monkeypatch, tmp_path):
    """يشغّل الأمرَ على صفحاتٍ مصطنعة؛ والملفّان بايتاتٌ بسيطةٌ لحساب sha256 لا PDFٌ حقيقيّ."""

    def go(teachers: list[FakePage], classes: list[FakePage], *flags: str, tag: str = "v1"):
        t_path, c_path = tmp_path / f"t-{tag}.pdf", tmp_path / f"c-{tag}.pdf"
        t_path.write_bytes(f"teachers-{tag}".encode())
        c_path.write_bytes(f"classes-{tag}".encode())
        books = {str(t_path): FakePdf(teachers), str(c_path): FakePdf(classes)}

        @contextmanager
        def opener(path: str) -> Any:
            yield books[path]

        monkeypatch.setattr(asc_pdf, "open_pdf", opener)
        out = io.StringIO()
        call_command(
            "import_schedule_from_asc_pdf",
            "--teachers",
            str(t_path),
            "--classes",
            str(c_path),
            *flags,
            stdout=out,
        )
        return out.getvalue()

    return go


def _simple(world):
    world["assign"](world["people"]["معلم الف"], world["math"], 2)
    teachers = [
        teacher_page("معلم الف", [(0, 1, "7.1", "رياضيات"), (1, 3, "7.1", "رياضيات")]),
    ]
    classes = [class_page("7.1", [(0, 1), (1, 3)])]
    return teachers, classes


@pytest.mark.django_db
def test_report_without_apply_writes_nothing(world, run):
    teachers, classes = _simple(world)
    out = run(teachers, classes)
    assert "تقريرٌ فقط" in out
    assert ScheduleGeneration.objects.count() == 0
    assert ScheduleSlot.objects.count() == 0


@pytest.mark.django_db
def test_report_is_always_printed_with_unmatched_and_count_mismatch(world, run):
    world["assign"](world["people"]["معلم الف"], world["math"], 3)  # الجدولُ يحمل حصّتين فقط
    teachers = [
        teacher_page("معلم الف", [(0, 1, "7.1", "رياضيات"), (1, 3, "7.1", "رياضيات")]),
        teacher_page("غريب مجهول", [(2, 2, "7.1", "علوم")]),
    ]
    out = run(teachers, [class_page("7.1", [(0, 1), (1, 3), (2, 2)])])
    assert "معلّمٌ لم يُطابَق" in out
    assert "عددٌ مخالف" in out and "استُورد 2 والإسناد 3" in out


@pytest.mark.django_db
def test_apply_refused_while_report_has_items(world, run):
    world["assign"](world["people"]["معلم الف"], world["math"], 3)
    teachers = [teacher_page("معلم الف", [(0, 1, "7.1", "رياضيات")])]
    with pytest.raises(CommandError):
        run(teachers, [class_page("7.1", [(0, 1)])], "--apply")
    assert ScheduleGeneration.objects.count() == 0


@pytest.mark.django_db
def test_class_file_difference_is_a_conflict(world, run):
    teachers, _ = _simple(world)
    out = run(teachers, [class_page("7.1", [(0, 1)])])
    assert "تعارض: في ملفّ المعلّمين ولا في ملفّ الشعب" in out
    with pytest.raises(CommandError):
        run(teachers, [class_page("7.1", [(0, 1)])], "--apply")


@pytest.mark.django_db
def test_apply_writes_inactive_draft_and_keeps_live_slots(world, run, school, year):
    teachers, classes = _simple(world)
    live = ScheduleSlot.objects.create(
        school=school,
        teacher=world["people"]["معلم باء"],
        class_group=world["group"],
        day_of_week=4,
        period_number=6,
        start_time="07:00",
        end_time="07:45",
        academic_year=year,
        is_active=True,
    )
    run(teachers, classes, "--apply")

    generation = ScheduleGeneration.objects.get()
    assert generation.status == "draft"
    assert generation.config_snapshot["mode"] == "import"
    assert len(generation.config_snapshot["sha256_teachers"]) == 64
    assert len(generation.config_snapshot["sha256_classes"]) == 64
    slots = list(generation.slots.all())
    assert {(s.day_of_week, s.period_number) for s in slots} == {(0, 1), (1, 3)}
    assert not any(s.is_active for s in slots)
    assert all(s.subject_id == world["math"].id for s in slots)
    live.refresh_from_db()
    assert live.is_active and live.generation_id is None
    assert ScheduleSlot.objects.filter(is_active=True).count() == 1


@pytest.mark.django_db
def test_apply_twice_with_same_files_creates_one_draft(world, run):
    teachers, classes = _simple(world)
    run(teachers, classes, "--apply")
    out = run(teachers, classes, "--apply")
    assert ScheduleGeneration.objects.count() == 1
    assert ScheduleSlot.objects.count() == 2
    assert "موجودةٌ" in out


@pytest.mark.django_db
def test_double_period_writes_two_consecutive_slots(world, run):
    world["assign"](world["people"]["معلم الف"], world["math"], 2)
    teachers = [teacher_page("معلم الف", [(2, 4, "7.1", "رياضيات", 2)])]
    run(teachers, [class_page("7.1", [(2, 4, 2)])], "--apply")
    assert sorted(ScheduleSlot.objects.values_list("day_of_week", "period_number")) == [
        (2, 3),
        (2, 4),
    ]


def _parallel_pages():
    cell = (0, 1, "7.1", "x")
    teachers = [
        teacher_page("معلم الف", [(0, 1, "7.1", "رياضيات"), (1, 3, "7.1", "رياضيات")]),
        teacher_page("معلم باء", [(cell[0], cell[1], "7.1", "فنون")]),
    ]
    return teachers, [class_page("7.1", [(0, 1), (1, 3)])]


@pytest.mark.django_db
def test_two_teachers_in_cell_with_shared_parallel_group_is_accepted(world, run):
    world["assign"](world["people"]["معلم الف"], world["math"], 2, TAG)
    world["assign"](world["people"]["معلم باء"], world["arts"], 1, TAG)
    teachers, classes = _parallel_pages()
    run(teachers, classes, "--apply")
    shared = ScheduleSlot.objects.filter(day_of_week=0, period_number=1)
    assert shared.count() == 2
    assert set(shared.values_list("elective_group", flat=True)) == {TAG}
    assert ScheduleSlot.objects.filter(day_of_week=1).get().elective_group == ""


@pytest.mark.django_db
def test_two_teachers_in_cell_without_shared_group_is_a_conflict(world, run):
    world["assign"](world["people"]["معلم الف"], world["math"], 2)
    world["assign"](world["people"]["معلم باء"], world["arts"], 1)
    teachers, classes = _parallel_pages()
    out = run(teachers, classes)
    assert "بلا وسمِ توازٍ مشترك" in out
    with pytest.raises(CommandError):
        run(teachers, classes, "--apply")


@pytest.mark.django_db
def test_ignore_list_pair_does_not_block_apply(world, run, tmp_path, monkeypatch):
    world["assign"](world["people"]["معلم الف"], world["math"], 3)  # عددٌ مخالف
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps({"asc_ignore": ["معلم الف|7.1"]}), encoding="utf-8")
    monkeypatch.setenv("TIMETABLE_NAME_RULES_FILE", str(rules))
    teachers = [teacher_page("معلم الف", [(0, 1, "7.1", "رياضيات")])]
    out = run(teachers, [class_page("7.1", [(0, 1)])], "--apply")
    assert "متجاهَل" in out
    assert ScheduleSlot.objects.count() == 1


@pytest.mark.django_db
def test_subject_falls_back_to_sole_assignment_of_teacher_in_class(world, run):
    world["assign"](world["people"]["معلم الف"], world["math"], 1)
    teachers = [teacher_page("معلم الف", [(0, 1, "7.1", "اسم مختلف تماما")])]
    run(teachers, [class_page("7.1", [(0, 1)])], "--apply")
    assert ScheduleSlot.objects.get().subject_id == world["math"].id


def _unlabeled_class_page(cells: list[tuple]) -> FakePage:
    words = [_word("صفحة", 300, 50)]
    for day, period in cells:
        words += _cell_words(day, period, ["مادة"])
    return FakePage(_lines(), words)


@pytest.mark.django_db
def test_unlabeled_class_page_goes_to_the_sole_matching_class(world, run):
    world["assign"](world["people"]["معلم الف"], world["math"], 2)
    teachers = [teacher_page("معلم الف", [(0, 1, "7.1", "رياضيات"), (1, 3, "7.1", "رياضيات")])]
    out = run(teachers, [_unlabeled_class_page([(0, 1), (1, 3)])])
    assert "بنودُ التقرير: 0" in out


@pytest.mark.django_db
def test_unlabeled_class_page_without_sole_match_is_one_item(world, run):
    world["assign"](world["people"]["معلم الف"], world["math"], 2)
    teachers = [teacher_page("معلم الف", [(0, 1, "7.1", "رياضيات"), (1, 3, "7.1", "رياضيات")])]
    out = run(teachers, [_unlabeled_class_page([(2, 2)])])
    assert "بنودُ التقرير: 1" in out
    assert "بلا رمزِ شعبةٍ" in out


@pytest.mark.django_db
def test_empty_class_file_is_one_item_not_one_per_slot(world, run):
    teachers, _ = _simple(world)
    out = run(teachers, [])
    assert "بنودُ التقرير: 1" in out
    assert "لم تُقرأ منه أيُّ خانة" in out


@pytest.mark.django_db
def test_two_assignments_in_class_link_by_subject_despite_room_code(world, run):
    teacher = world["people"]["معلم الف"]
    world["assign"](teacher, world["math"], 1)
    world["assign"](teacher, world["arts"], 1)
    page = FakePage(
        _lines(),
        [
            _word("معلم", 300, 50),
            _word("الف", 260, 50),
            *_cell_words(0, 1, ["7.1", "رياضيات", "HC.12.4"]),
            *_cell_words(1, 2, ["7.1", "فنون", "HC.12.4"]),
        ],
    )
    run([page], [class_page("HC.7.1", [(0, 1), (1, 2)])], "--apply")
    assert ScheduleSlot.objects.count() == 2
