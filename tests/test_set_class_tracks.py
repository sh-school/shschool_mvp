"""[CURRICULUM] وضعُ مسارات الشُّعب دفعةً واحدة — بعرضٍ قبل الكتابة.

شُعب الحادي عشر والثاني عشر في القاعدة مُرقَّمةٌ `1 2 3 4` لا مُسمّاةً
بمسارها. فلا يعرف النظام أيّها العلميّ وأيّها الأدبيّ، ولا تُميَّز في قائمة
ولا تقرير.

والمطابقة تُمرَّر في السطر ولا تُخبَز في الشيفرة: توزيع الشُّعب على المسارات
يتغيّر كل عام، وما يُكتب اليوم في الملفّ يصير كذبةً في العام القادم.

ولا يكتب الأمر شيئاً بلا `--apply` — والكتابة على بيانات مدرسةٍ حقيقية
تستحقّ عرضاً يسبقها.
"""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from core.management.commands.set_class_tracks import UNTRACKED_GRADE_MESSAGE
from core.models import ClassGroup


@pytest.fixture
def year(db, school):
    from core.academic_calendar import academic_year_for_school

    return academic_year_for_school(school)


@pytest.fixture
def sections(db, school, year):
    def _make(*specs):
        made = {}
        for grade, section in specs:
            made[f"{grade}/{section}"] = ClassGroup.objects.create(
                school=school,
                grade=f"G{grade}",
                section=section,
                level_type="sec",
                academic_year=year,
            )
        return made

    return _make


def _run(*args, **kw):
    out = StringIO()
    call_command("set_class_tracks", *args, stdout=out, **kw)
    return out.getvalue()


# ── العرض قبل الكتابة ─────────────────────────────────────────────────


def test_without_apply_nothing_is_written(db, school, year, sections):
    made = sections((11, "1"))

    out = _run("--year", year, "--map", "11/1=علمي")

    made["11/1"].refresh_from_db()
    assert made["11/1"].track == "", "عرضٌ فقط"
    assert "عرضٌ فقط" in out


def test_with_apply_the_track_lands(db, school, year, sections):
    made = sections((11, "1"), (11, "4"))

    _run("--year", year, "--map", "11/1=علمي", "11/4=تكنولوجي", "--apply")

    made["11/1"].refresh_from_db()
    made["11/4"].refresh_from_db()
    assert (made["11/1"].track, made["11/4"].track) == ("science", "technology")


def test_running_twice_changes_nothing_the_second_time(db, school, year, sections):
    sections((12, "1"))
    _run("--year", year, "--map", "12/1=علمي", "--apply")

    out = _run("--year", year, "--map", "12/1=علمي", "--apply")

    assert "كُتبت 0 شعبة" in out


# ── ما ترفضه ─────────────────────────────────────────────────────────


def test_a_missing_section_is_named_not_skipped(db, school, year, sections):
    """صمتٌ عن شعبةٍ غير موجودة يعني مساراً ناقصاً لا يعلمه أحد."""
    out = _run("--year", year, "--map", "11/9=علمي")

    assert "لا شعبة بهذا الاسم" in out


def test_it_refuses_to_write_a_partly_broken_mapping(db, school, year, sections):
    """نصفُ مطابقةٍ أسوأ من لا شيء — فبعض الشُّعب تحمل مسارها وبعضها لا."""
    made = sections((11, "1"))

    with pytest.raises(CommandError):
        _run("--year", year, "--map", "11/1=علمي", "11/9=تكنولوجي", "--apply")

    made["11/1"].refresh_from_db()
    assert made["11/1"].track == "", "لم يُكتب شيء"


def test_a_grade_without_tracks_is_refused(db, school, year):
    ClassGroup.objects.create(
        school=school, grade="G10", section="1", level_type="sec", academic_year=year
    )

    out = _run("--year", year, "--map", "10/1=علمي")

    assert UNTRACKED_GRADE_MESSAGE in out


@pytest.mark.parametrize("bad", ["11/1", "11/1=رياضي", "علمي"])
def test_an_unreadable_pair_stops_the_command(db, school, year, bad):
    """خطأٌ في الصيغة يُقال، ولا يُبتلع فيمضي الأمر ناقصاً."""
    with pytest.raises(CommandError):
        _run("--year", year, "--map", bad)


# ── أسماء المسارات كما يكتبها البشر ──────────────────────────────────


@pytest.mark.parametrize(
    ("written", "stored"),
    [
        ("علمي", "science"),
        ("آداب وإنسانيات", "humanities"),
        ("اداب وانسانيات", "humanities"),
        ("آداب", "humanities"),
        ("تكنولوجي", "technology"),
        ("science", "science"),
    ],
)
def test_the_arabic_names_are_accepted(db, school, year, sections, written, stored):
    """من يكتب المطابقة بشرٌ — ولا يُطالَب بمفاتيح إنجليزية."""
    made = sections((11, "1"))

    _run("--year", year, "--map", f"11/1={written}", "--apply")

    made["11/1"].refresh_from_db()
    assert made["11/1"].track == stored


def test_the_mapping_is_not_hardcoded_anywhere():
    """توزيع هذا العام لا يُخبَز في الشيفرة — فيتغيّر في القادم."""
    import pathlib

    src = pathlib.Path("core/management/commands/set_class_tracks.py").read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1]  # ما بعد التوثيق

    assert "11/2" not in body and "12/3" not in body
