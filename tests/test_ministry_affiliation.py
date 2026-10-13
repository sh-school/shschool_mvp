"""تجميدُ سطر انتماء المدرسة للوزارة (W-20261012-008، قرار المالك D-399م ثمّ D-400م).

العبارةُ «وزارة التربية والتعليم والتعليم العالي — دولة قطر» لا تظهر افتراضاً ولا تُحذف: مصدرُها الوحيدُ `core/ministry.py`
ومفتاحُها `MINISTRY_AFFILIATION_VISIBLE` (متغيّرُ بيئة). هذا الملفُّ يحرس ثلاثة:

1. الحالتان: مطفأً (الافتراضيّ) لا أثرَ للعبارة ولا لفاصلٍ يتيمٍ يجاورها؛ ومشغَّلاً تعود كما كانت.
2. المصدرُ الواحد: لا نصَّ حرفيّاً للعبارة في الشيفرة خارج الوحدة المركزيّة إلّا في المواضع المسمّاة أدناه.
3. اسمُ المدرسة ورؤيتُها يبقيان ظاهرَين في الحالتين.
"""

import pathlib
import re

import pytest
from django.template import Context, Template
from django.template.loader import render_to_string

from core import ministry

FULL = "وزارة التربية والتعليم والتعليم العالي — دولة قطر"
SHORT = "وزارة التربية والتعليم والتعليم العالي"

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: الوزارةُ جهةً مرجعيّةً لا سطرَ انتماءٍ: خارجَ التجميد عمداً (مواصفةُ البطاقة).
REFERENCE_USES = {
    "core/models/user.py": "نصُّ مساعدةٍ لحقل الرقم الوظيفيّ لدى الوزارة",
    "operations/services/attendance.py": "جهةٌ مرجعيّةٌ في تعليل الغياب",
    "templates/behavior/pdf/student_report.html": "جملةُ مرجعٍ في تذييل التقرير السرّيّ",
    "templates/components/ministry_vision.html": "رؤيةُ الوزارة (school.vision) تبقى ظاهرة",
    "shschool/settings/base.py": "تعليقُ المفتاح",
    "core/management/commands/seed_academic_calendar.py": "تعليقٌ يصف مصدرَ تقويم الوزارة",
}
#: الوحدةُ المركزيّةُ نفسُها.
SOURCE = "core/ministry.py"

SCAN_SUFFIXES = {".py", ".html", ".txt", ".js"}
SKIP_PARTS = {
    ".git",
    ".claude",
    "node_modules",
    "staticfiles",
    "migrations",
    "tests",
    "docs",
    "AAdocs",
    "venv",
    ".venv",
}


def _sources():
    for path in ROOT.rglob("*"):
        if path.suffix not in SCAN_SUFFIXES or not path.is_file():
            continue
        if SKIP_PARTS & set(path.relative_to(ROOT).parts):
            continue
        yield path


def _render(source: str, **ctx) -> str:
    return Template("{% load ministry %}" + source).render(Context(ctx)).strip()


class _School:
    def __init__(self, name="مدرسةٌ تجريبيّة", vision="رؤيةُ المدرسة"):
        self.name = name
        self.vision = vision


# ── الحالتان على الوحدة المركزيّة ──────────────────────────────────────────


def test_the_ministry_line_is_off_by_default():
    from django.conf import settings

    assert settings.MINISTRY_AFFILIATION_VISIBLE is False
    assert ministry.ministry_name() == ""
    assert ministry.ministry_name(short=True) == ""


def test_the_ministry_line_returns_the_text_when_switched_on(settings):
    settings.MINISTRY_AFFILIATION_VISIBLE = True
    assert ministry.ministry_name() == FULL
    assert ministry.ministry_name(short=True) == SHORT


def test_ministry_line_drops_empty_parts_so_no_orphan_separator_remains(settings):
    settings.MINISTRY_AFFILIATION_VISIBLE = False
    assert ministry.ministry_line("مدرسة", ministry.ministry_name(), sep="  —  ") == "مدرسة"
    settings.MINISTRY_AFFILIATION_VISIBLE = True
    assert ministry.ministry_line("مدرسة", ministry.ministry_name(), sep=" | ") == f"مدرسة | {FULL}"


def test_the_template_tag_follows_the_switch(settings):
    settings.MINISTRY_AFFILIATION_VISIBLE = False
    assert _render("{% ministry_name %}") == ""
    settings.MINISTRY_AFFILIATION_VISIBLE = True
    assert _render("{% ministry_name %}") == FULL
    assert _render("{% ministry_name short=True %}") == SHORT


# ── القوالبُ المشتركة ──────────────────────────────────────────────────────


@pytest.mark.parametrize("visible", [False, True])
def test_the_site_footer_line_keeps_the_school_in_both_states(settings, visible):
    settings.MINISTRY_AFFILIATION_VISIBLE = visible
    html = render_to_string("components/site_footer_line.html", {"current_school": _School()})
    assert "مدرسةٌ تجريبيّة" in html
    assert (FULL in html) is visible
    if not visible:
        assert "|" not in html  # لا فاصلَ يتيماً


@pytest.mark.parametrize("visible", [False, True])
def test_the_pdf_footer_line_has_no_orphan_dash_while_frozen(settings, visible):
    settings.MINISTRY_AFFILIATION_VISIBLE = visible
    html = render_to_string("components/pdf_footer.html", {"school": _School()})
    text = " ".join(re.sub(r"<[^>]+>", "", html).split())
    assert text.startswith("مدرسةٌ تجريبيّة")
    assert (FULL in text) is visible
    assert "— —" not in text and not text.endswith("—")


@pytest.mark.parametrize("visible", [False, True])
def test_the_offline_and_error_pages_follow_the_switch(settings, visible):
    settings.MINISTRY_AFFILIATION_VISIBLE = visible
    offline = render_to_string("pwa/offline_global.html", {})
    assert (FULL in offline) is visible
    base = {
        "code": "404",
        "heading": "غير موجود",
        "desc": "x",
        "icon": "search",
        "accent": "MAROON",
        "accent_dark": "MAROON_FG",
    }
    with_header = render_to_string("errors/_error_page.html", {**base, "login_header": True})
    assert (FULL in with_header) is visible  # ترويسةُ بطاقة الدخول
    plain = render_to_string("errors/_error_page.html", base)
    assert (SHORT in plain) is visible  # التذييلُ المختصر يتبع المفتاحَ نفسَه


@pytest.mark.parametrize("visible", [False, True])
def test_the_central_print_frame_hides_the_ministry_block_while_frozen(settings, visible):
    settings.MINISTRY_AFFILIATION_VISIBLE = visible
    html = render_to_string(
        "components/print/frame_header.html",
        {
            "ministry": ministry.ministry_name(),
            "school": _School(),
            "title": "تقرير",
            "subtitle": "",
            "for_pdf": False,
            "vision": "",
        },
    )
    assert ('class="pf-ministry"' in html) is visible
    assert "مدرسةٌ تجريبيّة" in html


# ── التصدير ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("visible", [False, True])
def test_the_pdf_header_and_excel_title_drop_the_ministry_cleanly(settings, visible):
    from core.export_utils import get_pdf_header_html

    settings.MINISTRY_AFFILIATION_VISIBLE = visible
    ctx = {
        "school_name": "مدرسةٌ تجريبيّة",
        "ministry": ministry.ministry_name(),
        "title": "تقرير",
        "academic_year": "2026-2027",
    }
    html = get_pdf_header_html(ctx)
    assert "مدرسةٌ تجريبيّة" in html
    assert ('class="xp-head-ministry"' in html) is visible
    title = ministry.ministry_line(ctx["school_name"], ctx["ministry"], sep="  —  ")
    assert title == ("مدرسةٌ تجريبيّة  —  " + FULL if visible else "مدرسةٌ تجريبيّة")


# ── المصدر الواحد ─────────────────────────────────────────────────────────


def test_the_full_phrase_is_written_nowhere_but_the_central_module():
    pattern = re.compile(r"وزارة\s+التربية\s+والتعليم\s+والتعليم\s+العالي\s*—\s*دولة\s+قطر")
    offenders = []
    for path in _sources():
        rel = path.relative_to(ROOT).as_posix()
        if rel == SOURCE or rel in REFERENCE_USES:
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(rel)
    assert (
        offenders == []
    ), f"العبارةُ الحرفيّةُ خارج core/ministry.py: {offenders} — استعمل ministry_name() أو الوسم ministry_name (D-400م)"


def test_the_short_phrase_appears_only_in_the_named_reference_uses():
    offenders = []
    for path in _sources():
        rel = path.relative_to(ROOT).as_posix()
        if rel == SOURCE or rel in REFERENCE_USES:
            continue
        if SHORT in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(rel)
    assert (
        offenders == []
    ), f"صيغةٌ مختصرةٌ للعبارة خارج المواضع المسمّاة: {offenders} — إن كانت جهةً مرجعيّةً أضفها إلى REFERENCE_USES بسببها"


def test_the_reference_uses_still_exist_so_the_allow_list_does_not_rot():
    missing = [rel for rel in REFERENCE_USES if not (ROOT / rel).is_file()]
    assert missing == []
