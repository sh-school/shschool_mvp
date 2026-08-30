"""[STAFF] استكمال سجلٍّ مؤقّت ببيانات صاحبه — وحدَه دون سواه.

`create_placeholder_staff` يفتح سجلّاً بالاسم المختصر ورقمٍ مؤقّتٍ ظاهر
النقص، ليجد جدولُ الحصص معلّمَه قبل أن تصل بياناته. وهذا الأمر يُغلق تلك
الحلقة حين تصل.

وحدُّه صارم: لا يمسّ إلّا سجلّاً رقمُه مؤقّت. فمن كان رقمه الشخصيّ حقيقياً
جاءت بياناته من شؤون الموظفين، ولا تُصحَّح من سطر أوامر — ولو تسمّى باسمٍ
يشبه اسم المؤقّت.

و`الرقم الوظيفي` حقلٌ استُحدث لهذا: تعرف به الوزارةُ الموظّف، وليس رقمه
الشخصي ولا رخصته المهنية، ولم يكن له موضعٌ في المنصّة.
"""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from core.models import CustomUser

REAL = {
    "--name": "جمال صالح محمد ادم",
    "--national-id": "29273603822",
    "--employee-number": "197985",
}


def _run(*args, **kw):
    out = StringIO()
    call_command("complete_staff_record", *args, stdout=out, **kw)
    return out.getvalue()


def _args(**overrides):
    data = dict(REAL, **overrides)
    return [x for pair in data.items() for x in pair]


@pytest.fixture
def placeholder(db, school):
    call_command("create_placeholder_staff", "--name", "جمال صالح", "--apply", stdout=StringIO())
    return CustomUser.objects.get(full_name="جمال صالح")


# ── العرض قبل الكتابة ─────────────────────────────────────────────────


def test_without_apply_nothing_changes(db, placeholder):
    out = _run("--placeholder", "جمال صالح", *_args())

    placeholder.refresh_from_db()
    assert placeholder.full_name == "جمال صالح"
    assert placeholder.is_active is False
    assert "عرضٌ فقط" in out


def test_with_apply_the_record_is_completed(db, placeholder):
    _run("--placeholder", "جمال صالح", *_args(), "--apply")

    placeholder.refresh_from_db()
    assert placeholder.full_name == "جمال صالح محمد ادم"
    assert placeholder.national_id == "29273603822"
    assert placeholder.employee_number == "197985"
    assert placeholder.is_active is True


def test_the_account_still_has_no_password(db, placeholder):
    """سجلٌّ مكتملٌ لا يعني باباً مفتوحاً — الكلمة تُصدَر على حدة."""
    _run("--placeholder", "جمال صالح", *_args(), "--apply")

    placeholder.refresh_from_db()
    assert not placeholder.has_usable_password()


def test_the_national_id_is_encrypted_on_save(db, placeholder):
    """`save()` يملأ الحقلين المشفَّرين — ولا يُترك الرقم عارياً."""
    _run("--placeholder", "جمال صالح", *_args(), "--apply")

    placeholder.refresh_from_db()
    assert placeholder.national_id_hmac
    assert placeholder.national_id_encrypted


# ── ما يرفضه ──────────────────────────────────────────────────────────


def test_it_refuses_a_record_that_is_not_a_placeholder(db, school):
    """سجلٌّ حقيقيّ بياناته من شؤون الموظفين، ولا يُصحَّح من سطر أوامر."""
    CustomUser.objects.create(national_id="28912345678", full_name="جمال صالح")

    with pytest.raises(CommandError, match="سجلٌّ حقيقيٌّ"):
        _run("--placeholder", "جمال صالح", *_args(), "--apply")


def test_a_missing_name_stops_the_command(db, school):
    with pytest.raises(CommandError, match="لا سجلّ"):
        _run("--placeholder", "من لا وجود له", *_args())


def test_a_national_id_held_by_another_is_refused(db, placeholder):
    """رقمٌ يحمله غيرُه قد يكون شخصاً آخر لا خطأ إدخال."""
    CustomUser.objects.create(national_id="29273603822", full_name="آخر")

    with pytest.raises(CommandError, match="الرقم الشخصي"):
        _run("--placeholder", "جمال صالح", *_args(), "--apply")

    placeholder.refresh_from_db()
    assert placeholder.full_name == "جمال صالح", "لم يُكتب شيء"


def test_an_employee_number_held_by_another_is_refused(db, placeholder):
    CustomUser.objects.create(national_id="28900000001", full_name="آخر", employee_number="197985")

    with pytest.raises(CommandError, match="الرقم الوظيفي"):
        _run("--placeholder", "جمال صالح", *_args(), "--apply")


def test_blank_employee_numbers_do_not_collide(db, school):
    """الشرط يستثني الفراغ — وأكثرُ السجلّات بلا رقمٍ وظيفيّ بعد."""
    CustomUser.objects.create(national_id="28900000002", full_name="أ")
    CustomUser.objects.create(national_id="28900000003", full_name="ب")

    assert CustomUser.objects.filter(employee_number="").count() == 2


# ── الجدول يعرف الاسم الجديد ─────────────────────────────────────────


def test_the_timetable_knows_the_completed_name():
    """اسمُ المنصّة صار رباعياً ولا يطابق الجدول — فيُقيَّد في جدول الأسماء.

    ولولاه لسقط المعلّمان من الاستيراد التالي كما سقطا في الأوّل.
    """
    from operations.management.commands.import_timetable_pdf import TEACHER_MAP

    assert TEACHER_MAP["جمال صالح"] == "جمال صالح محمد ادم"
    assert TEACHER_MAP["علي الطيطي"] == "علي صالح اسماعيل الطيطي"
