"""كشفُ الكادر العربيُّ 2026-2027 — ورقتان تُدمجان، والوزاريّةُ تحكم."""

import pytest
from django.core.management import call_command

from core.management.commands.import_staff_register import (
    EXCLUDED_EMPLOYEE_NUMBERS,
    Command,
    _local_phone,
    normalize_title,
    role_for,
)

pytestmark = pytest.mark.django_db


def _book(tmp_path, ministry_rows, school_rows):
    """ملفٌّ بورقتين كالكشف الحقيقيّ: الوزاريّةُ رؤوسُها في السطر الأوّل،
    والمدرسيّةُ في الثاني تحت عنوانٍ مدموج."""
    import openpyxl

    book = openpyxl.Workbook()
    ministry = book.active
    ministry.title = "الوزارية"
    ministry.append(["م", "الرقم الشخصى", "الاسم", "رقم الموظف", "مسمى الوظيفة", "رقم الجوال"])
    for index, row in enumerate(ministry_rows, 1):
        ministry.append([index, *row])

    school = book.create_sheet("المدرسية")
    school.append(["كشف المدرسة", "", "", "", "", "", "", ""])
    school.append(
        [
            "م",
            "الاسم",
            "المسمى الوظيفي",
            "الرقم الوظيفي",
            "الرقم الشخصي",
            "السكن",
            "البريد الالكتروني",
            "رقم الهاتف",
        ]
    )
    for index, row in enumerate(school_rows, 1):
        school.append([index, *row])

    path = tmp_path / "كشف.xlsx"
    book.save(path)
    return str(path)


class TestTitles:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("مدير مدرسة", "principal"),
            ("مدير معلمة", "principal"),
            ("أخصائي اجتماعي", "social_worker"),
            ("الاخصائي الاجتماعي", "social_worker"),
            ("نائب المدير للشؤون الأكاديمية", "vice_academic"),
            ("نائب المدير للشؤون الإدارية وشؤون الطلاب", "vice_admin"),
            ("محضر مختبر", "lab_technician"),
            ("محضر مختبر كيمياء", "lab_technician"),
            ("معلم إدارة أعمال", "teacher"),
            ("منسق الفيزياء", "coordinator"),
        ],
    )
    def test_every_written_form_finds_its_role(self, title, expected):
        assert role_for(title) == expected

    def test_normalization_ignores_hamza_and_the_article(self):
        assert normalize_title("الأخصائي النفسى") == normalize_title("اخصائي نفسي")

    def test_an_unknown_title_stays_unknown(self):
        """التخمينُ ممنوع: دورٌ خاطئٌ يفتح شاشاتٍ لا تخصّ صاحبَها."""
        assert role_for("رائد فضاء") is None


class TestPhone:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("97455512345", "55512345"), ("55512345", "55512345"), ("974-5551 2345", "55512345")],
    )
    def test_the_country_code_is_dropped(self, raw, expected):
        assert _local_phone(raw) == expected

    def test_an_eight_digit_number_starting_with_974_survives(self):
        assert _local_phone("97412345") == "97412345"


class TestMerge:
    def test_the_ministry_governs_and_the_school_completes(self, tmp_path):
        path = _book(
            tmp_path,
            [["28100000001", "سالم الأول", "111111", "مدير مدرسة", "97455500001"]],
            [["سالم الاول", "مدير معلمة", "111111", "28100000001", "الريان", "s@x.qa", "55500001"]],
        )
        rows = Command()._read(path, "")

        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "سالم الأول"  # الوزاريّة
        assert row["title"] == "مدير مدرسة"  # لا «مدير معلمة»
        assert row["phone"] == "55500001"  # بلا 974
        assert row["email"] == "s@x.qa"  # المدرسيّة
        assert row["residence_area"] == "الريان"  # المدرسيّة

    def test_whoever_is_in_one_sheet_only_is_still_read(self, tmp_path):
        path = _book(
            tmp_path,
            [["28100000002", "وزاريٌّ وحدَه", "222222", "امين مخزن", "97455500002"]],
            [["مدرسيٌّ وحدَه", "ملاحظ طلبه", "333333", "28100000003", "دخان", "m@x.qa", "55500003"]],
        )
        rows = {r["national_id"]: r for r in Command()._read(path, "")}

        assert set(rows) == {"28100000002", "28100000003"}
        assert rows["28100000002"]["email"] == ""  # لا بريدَ له — والفراغُ أصل
        assert rows["28100000003"]["title"] == "ملاحظ طلبه"

    def test_a_row_without_a_numeric_identifier_is_dropped(self, tmp_path):
        path = _book(
            tmp_path,
            [["", "بلا رقم", "444444", "محاسب", "97455500004"]],
            [],
        )
        assert Command()._read(path, "") == []


class TestExclusion:
    def test_the_list_carries_a_reason_with_every_number(self):
        """قائمةٌ بلا أسبابٍ تصير بعد سنةٍ لغزاً لا يجرؤ أحدٌ على حذف سطرٍ منه."""
        assert EXCLUDED_EMPLOYEE_NUMBERS
        for employee_number, reason in EXCLUDED_EMPLOYEE_NUMBERS.items():
            assert employee_number.isdigit()
            assert len(reason) > 20

    def test_the_key_is_never_a_national_id(self):
        """المستودعُ عامّ — والرقمُ الشخصيُّ لا يُكتب في شيفرةٍ يقرؤها الناس.

        والقطريُّ منه إحدى عشرة خانة، والوظيفيُّ خمسٌ أو ستّ.
        """
        for employee_number in EXCLUDED_EMPLOYEE_NUMBERS:
            assert len(employee_number) <= 8

    def test_the_excluded_person_is_named_in_the_report(self, tmp_path, school, capsys):
        employee_number, reason = next(iter(EXCLUDED_EMPLOYEE_NUMBERS.items()))
        path = _book(
            tmp_path,
            [["29900000009", "المستثنى", employee_number, "امين مخزن", "97455500009"]],
            [],
        )
        call_command("import_staff_register", file=path)
        out = capsys.readouterr().out

        assert "المستثنى" in out
        assert reason[:30] in out
        assert "الكشف: 0 سطراً" in out
