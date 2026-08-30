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
    _merge_runs,
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


def test_both_halves_of_a_split_are_kept_and_named():
    """كلا النصفين يُحقن، ولكلٍّ مجموعتُه — فيسعهما القيد.

    كانت الثانية تُفصل وتُقال ولا تُحقن، فيرى المعلّم والطالب خليّةً ناقصة.
    """
    rows = [_row(period=1), _row(period=1, subject="الفنون البصرية"), _row(period=2)]

    parallel = Command()._label_parallel_periods(rows)

    assert len(rows) == 3, "لم يُفصل شيء"
    assert len(parallel) == 1
    assert [r["subject_name"] for r in parallel[0]] == ["الكيمياء", "الفنون البصرية"]
    assert [r["elective_group"] for r in parallel[0]] == ["الكيمياء", "الفنون البصرية"]


def test_an_ordinary_period_carries_no_elective_group():
    """المجموعة فارغةٌ في حصص الشعبة كاملةً — وعليها يبقى القيد كما كان."""
    rows = [_row(period=p) for p in (1, 2, 3)]

    assert Command()._label_parallel_periods(rows) == []
    assert {r["elective_group"] for r in rows} == {""}


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


# ── ضمُّ الكلمات ───────────────────────────────────────────────────────


def _piece(text, x, y=200.0):
    return {"t": text, "x": x, "y": y, "s": 9.9}


def test_a_two_word_subject_is_joined():
    """«علوم عامة» تُرسم كلمتين، وإسنادُ كلٍّ وحدها يجعلها «علوم» —
    وهي مادّةٌ أخرى تماماً."""
    runs = _merge_runs([_piece("علوم", 500.0), _piece("عامة", 470.0)])

    assert [r["t"] for r in runs] == ["علوم عامة"]


def test_two_neighbouring_cells_of_one_subject_are_not_joined():
    """الحكمُ للمفردات لا للمسافة: جُرّب الضمُّ بالتجاور وحده فأنتج
    «رياضيات رياضيات» من خليّتين متجاورتين."""
    runs = _merge_runs([_piece("رياضيات", 500.0), _piece("رياضيات", 470.0)])

    assert [r["t"] for r in runs] == ["رياضيات", "رياضيات"]


def test_a_room_code_is_never_joined_to_a_subject():
    runs = _merge_runs([_piece("علوم", 500.0), _piece("LAB1", 470.0)])

    assert {r["t"] for r in runs} == {"علوم", "LAB1"}


def test_distant_words_are_not_joined():
    """المسافة سياجٌ احتياطيّ: كلمتان تفصلهما عرضُ عمودٍ ليستا مادّةً واحدة."""
    runs = _merge_runs([_piece("علوم", 500.0), _piece("عامة", 300.0)])

    assert len(runs) == 2


def test_a_subject_is_read_from_the_line_above_its_section():
    """المادّة والقاعة فوق اسم الشعبة دائماً، فلا يُنظر إلّا إلى ما تحتها.

    والنظر في الجهتين يجعل خليّةً تسرق مادّة جارتها: مادّةُ 8/2 كانت أقربَ
    إلى الشعبة التي فوقها (٦٦ + ٩٥) منها إلى شعبتها (٥٥ + ١٠٨)، فأخذتها
    الجارة وسقطت 8/2 بلا مادّة. وكشفه الجدولُ العام: مصدرٌ ثالث عدّ ٨٤٩
    حصة، والاستخراج ٨٤٦.
    """
    src = SOURCE.read_text(encoding="utf-8")

    assert '0 < c["y"] - i["y"] < 70' in src, "المسافة موجَّهة لا مطلقة"
    assert 'abs(c["y"] - i["y"]) < 70 and' not in src
