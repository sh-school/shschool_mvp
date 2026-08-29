"""[CURRICULUM] إنشاء شُعب عامٍ جديد من قائمةٍ تُمرَّر.

المنصّة لا تعرف كيف ينتقل الطالب من عامٍ إلى عام: لا أمرَ ترفيع، ولا شيء
يُنشئ شُعب العام الجديد. وهذه أولى الخطوات — الوعاء قبل ما يُصبّ فيه.

والقائمة أرغومنت لا جدولٌ في الملفّ: عددُ الشُّعب وتوزيعها على المسارات
يتغيّر كل عام، وما يُكتب في الشيفرة اليوم يصير كذبةً في سبتمبر القادم.

وهو مُعاوِد: تشغيلُه ثانيةً لا يُنشئ نسخةً ثانية — والقيد الفريد
`(school, grade, section, academic_year)` يمنعها أصلاً، لكنّ الأمر يجب أن
يقول ذلك بدل أن يصطدم به.
"""

import re
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from core.models import ClassGroup

#: بنية العام كما أرسلتها المدرسة — بلا شُعب دعمٍ خاصّ.
SECTIONS_2026_27 = [
    "7/1",
    "7/2",
    "7/3",
    "7/4",
    "8/1",
    "8/2",
    "8/3",
    "8/4",
    "8/5",
    "9/1",
    "9/2",
    "9/3",
    "9/4",
    "10/1",
    "10/2",
    "10/3",
    "10/4",
    "11/1=علمي",
    "11/2=آداب",
    "11/3=آداب",
    "11/4=تكنولوجي",
    "12/1=علمي",
    "12/2=آداب",
    "12/3=آداب",
    "12/4=تكنولوجي",
]


def _run(*args, **kw):
    out = StringIO()
    call_command("create_year_sections", *args, stdout=out, **kw)
    return out.getvalue()


def _sections(school, year):
    return {
        f"{g.grade[1:]}/{g.section}": g.track
        for g in ClassGroup.objects.filter(school=school, academic_year=year)
    }


# ── العرض قبل الكتابة ─────────────────────────────────────────────────


def test_without_apply_nothing_is_created(db, school):
    out = _run("--year", "2026-2027", "--sections", "7/1", "11/4=تكنولوجي")

    assert ClassGroup.objects.filter(academic_year="2026-2027").count() == 0
    assert "عرضٌ فقط" in out


def test_the_whole_year_lands_in_one_pass(db, school):
    _run("--year", "2026-2027", "--sections", *SECTIONS_2026_27, "--apply")

    made = _sections(school, "2026-2027")

    assert len(made) == 25
    assert made["8/5"] == ""
    assert made["11/1"] == "science"
    assert made["11/4"] == "technology"
    assert made["12/4"] == "technology"
    assert made["12/2"] == "humanities"


def test_running_it_twice_creates_nothing_new(db, school):
    _run("--year", "2026-2027", "--sections", *SECTIONS_2026_27, "--apply")

    out = _run("--year", "2026-2027", "--sections", *SECTIONS_2026_27, "--apply")

    assert ClassGroup.objects.filter(academic_year="2026-2027").count() == 25
    assert "أُنشئت 0" in out


def test_it_does_not_touch_another_year(db, school):
    ClassGroup.objects.create(school=school, grade="G7", section="1", academic_year="2025-2026")

    _run("--year", "2026-2027", "--sections", "7/1", "--apply")

    assert ClassGroup.objects.filter(grade="G7", section="1").count() == 2, "عامان مستقلّان"


# ── ما يُشتقّ وما يُرفض ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("spec", "grade", "level"),
    [
        ("7/1", "G7", "prep"),
        ("9/4", "G9", "prep"),
        ("10/1", "G10", "sec"),
        ("12/1=علمي", "G12", "sec"),
    ],
)
def test_the_stage_is_derived_from_the_grade(db, school, spec, grade, level):
    """المرحلة لا تُكتب في السطر — فكتابتها مرّتين تعني اختلافهما يوماً."""
    _run("--year", "2026-2027", "--sections", spec, "--apply")

    assert ClassGroup.objects.get(grade=grade, academic_year="2026-2027").level_type == level


def test_a_track_on_an_untracked_grade_is_refused(db, school):
    """العاشر ثانويٌّ بلا مسار — والنموذج يرفضه، والأمر لا يبتلع الرفض."""
    from django.core.exceptions import ValidationError

    with pytest.raises((CommandError, ValidationError)):
        _run("--year", "2026-2027", "--sections", "10/1=علمي", "--apply")

    assert ClassGroup.objects.filter(academic_year="2026-2027").count() == 0


def test_a_repeated_section_stops_the_command(db, school):
    """شعبةٌ مذكورةٌ مرّتين خطأٌ في القائمة لا نيّة."""
    with pytest.raises(CommandError, match="مكرّرة"):
        _run("--year", "2026-2027", "--sections", "7/1", "7/1")


@pytest.mark.parametrize("bad", ["7", "س/1", "11/1=رياضي"])
def test_an_unreadable_entry_stops_the_command(db, school, bad):
    with pytest.raises(CommandError):
        _run("--year", "2026-2027", "--sections", bad)


def test_the_year_structure_is_not_stored_in_the_command():
    """بنية هذا العام تُمرَّر، ولا تُخزَّن في ملفٍّ يبقى بعدها.

    و«العبرة بالتخزين لا بالذِّكر»: مثالٌ في `help` أو في التوثيق يشرح الصيغة
    ولا يقرّر شيئاً، أمّا قائمةٌ من الشُّعب في الشيفرة فتصير أمراً واقعاً
    يوم تتغيّر البنية. فالحارس يبحث عن الأخيرة وحدها.
    """
    import ast
    import pathlib

    tree = ast.parse(
        pathlib.Path("core/management/commands/create_year_sections.py").read_text(encoding="utf-8")
    )
    section = re.compile(r"^\d{1,2}/\w+")

    stored = [
        ast.unparse(n)
        for n in ast.walk(tree)
        if isinstance(n, (ast.List, ast.Tuple, ast.Set))
        and sum(
            1
            for e in n.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str) and section.match(e.value)
        )
        > 1
    ]

    assert not stored, "شعبٌ مخزَّنةٌ في الأمر:\n" + "\n".join(stored)
