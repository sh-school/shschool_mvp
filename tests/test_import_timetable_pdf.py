"""[CURRICULUM] استيراد الجدول: ما يُحذف، وما ينقسم، وما يُقال بدل أن يُفقد.

الأمر كان معطَّلاً بالكامل: يستورد `fitz` (PyMuPDF) وهي ليست في
`requirements.txt` — فيسقط عند الاستيراد في كل بيئة، والإنتاج منها. صار
يقرأ بـ`pypdf` المُعلَنة أصلاً.

وفيه عطبان يستيقظان عند تدوير العام:

    الحذف بلا عام    يمحو جدول العام المنقضي وتوزيعاته
    حذف المواد       يجرف `SubjectClassSetup` بالتتالي، ويفكّ الزيارات
                     الصفّية عن مادّتها

وحصّةٌ منقسمة لا يسعها `ScheduleSlot`: قيد `no_class_period_overlap` يمنع
حصّتين لشعبةٍ في التوقيت نفسه. فتُقال ولا تُبتلع.
"""

import pathlib
import re

import pytest

from operations.management.commands.import_timetable_pdf import (
    SUBJECT_CODES,
    SUBJECT_MAP,
    Command,
)

SOURCE = pathlib.Path("operations/management/commands/import_timetable_pdf.py")


def _row(cg="cg", day=0, period=1, subject="الكيمياء", teacher="t1", name="أحمد"):
    return {
        "classgroup_id": cg,
        "day_idx": day,
        "period": period,
        "subject_name": subject,
        "teacher_id": teacher,
        "pdf_name": name,
    }


# ── الحصة المنقسمة ────────────────────────────────────────────────────


def test_the_second_half_of_a_split_is_named_not_swallowed():
    """حصّتان لشعبةٍ في التوقيت نفسه: القيد يرفض الثانية، فتُقال."""
    rows = [_row(period=1), _row(period=1, subject="الفنون البصرية"), _row(period=2)]

    parallel = Command()._separate_parallel_periods(rows)

    assert len(rows) == 2, "الثانية أُخرجت من الحقن"
    assert len(parallel) == 1
    kept, dropped = parallel[0]
    assert (kept["subject_name"], dropped["subject_name"]) == ("الكيمياء", "الفنون البصرية")


def test_an_ordinary_timetable_has_nothing_parallel():
    """حارسٌ يُبلّغ دائماً لا يُبلّغ عن شيء."""
    rows = [_row(period=p) for p in (1, 2, 3)]

    assert Command()._separate_parallel_periods(rows) == []
    assert len(rows) == 3


def test_each_teacher_gets_the_subject_the_school_declared():
    """الجدول يكتب في الخلية المنقسمة مادّةً واحدة ومعلّمَين."""
    rows = [
        _row(period=1, subject="الكيمياء", teacher="t1", name="أحمد شاهين"),
        _row(period=1, subject="الكيمياء", teacher="t2", name="عبد الله الرمضان"),
    ]

    Command()._relabel_parallel_by_teacher(
        rows, {"أحمد شاهين": "الكيمياء", "عبد الله الرمضان": "الفنون البصرية"}
    )

    assert [r["subject_name"] for r in rows] == ["الكيمياء", "الفنون البصرية"]


def test_a_declaration_does_not_touch_an_ordinary_period():
    """الإعلان للمنقسمة وحدها — وإلّا أعاد تسمية نصاب المعلّم كلّه."""
    rows = [_row(period=1, name="أحمد شاهين", subject="العلوم")]

    Command()._relabel_parallel_by_teacher(rows, {"أحمد شاهين": "الكيمياء"})

    assert rows[0]["subject_name"] == "العلوم"


def test_without_a_declaration_nothing_is_guessed():
    """جُرّب الاستدلال بمادّة المعلّم الغالبة فأخطأ: معلّم كيمياء الحادي عشر
    يدرّس العلوم في العاشر، فغلبت عليه. ومن يدرّس مادّتين لا تُخمَّن مادّتُه."""
    rows = [_row(period=1, teacher="t1", name="أ"), _row(period=1, teacher="t2", name="ب")]

    Command()._relabel_parallel_by_teacher(rows, {})

    assert {r["subject_name"] for r in rows} == {"الكيمياء"}


# ── ما لا يُحذف ───────────────────────────────────────────────────────


def test_every_deletion_is_scoped_to_the_import_year():
    """حذفٌ بلا عامٍ يمحو أرشيف العام المنقضي — لا مسوّدته."""
    src = SOURCE.read_text(encoding="utf-8")
    deletes = re.findall(r"(\w+)\.objects\.filter\(\s*([^)]*?)\)\s*\.delete\(\)", src, re.S)

    assert deletes, "حارسٌ لا يجد حذفاً لا يحرس شيئاً"
    unscoped = [m for m, args in deletes if "academic_year" not in args]
    assert not unscoped, f"حذفٌ بلا عام: {unscoped}"


def test_subjects_are_never_deleted():
    """المواد مفرداتٌ مشتركة: حذفُها يجرف إعدادات التقييم بالتتالي
    (`SubjectClassSetup.subject` = CASCADE) ويفكّ الزيارات الصفّية عنها."""
    src = SOURCE.read_text(encoding="utf-8")

    assert "Subject.objects.filter(school=school).delete()" not in src
    assert "Subject.objects.get_or_create(" in src


def test_it_does_not_import_an_undeclared_library():
    """`fitz` ليست في `requirements.txt` — والأمر كان يسقط عند استيراده."""
    src = SOURCE.read_text(encoding="utf-8")
    declared = pathlib.Path("requirements.txt").read_text(encoding="utf-8").lower()

    assert "import fitz" not in src
    assert "from pypdf import PdfReader" in src
    assert "pypdf" in declared


# ── مفردات المواد ─────────────────────────────────────────────────────


@pytest.mark.parametrize("written", sorted(SUBJECT_MAP))
def test_every_written_subject_has_a_code(written):
    """مادّةٌ تُقرأ من الجدول ولا كود لها تسقط صامتةً عند الإنشاء."""
    assert SUBJECT_MAP[written] in SUBJECT_CODES


def test_the_subject_keys_read_as_arabic():
    """كانت المفاتيح بحروفٍ معكوسة («ةيمﻼسا ةيبرت») لأنّ المستخرج القديم
    يقرأ الحروف بترتيب الرسم. ومفتاحٌ لا يُقرأ لا يُصان."""
    assert "تربية اسلامية" in SUBJECT_MAP
    assert "الفنون البصرية" in SUBJECT_MAP.values()


def test_an_unmatched_teacher_is_counted_not_only_named():
    """معلّمٌ جديدٌ لم يُدخل بعدُ يعني شعباً كاملةً بلا مادّة.

    ظهر ذلك في أوّل استيراد: معلّمان جديدان («جمال صالح» للتكنولوجيا
    و«علي الطيطي» للتربية الإسلامية) سقطت معهما ٢٤ حصة — والاسم وحده في
    المخرجات لا يُنبئ عن حجم الفقد.
    """
    src = SOURCE.read_text(encoding="utf-8")

    assert src.count("حصة لن تُحقن") == 2, "كلا مسارَي عدم المطابقة يذكر عدد حصصه"
