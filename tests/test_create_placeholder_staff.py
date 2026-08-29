"""[STAFF] سجلٌّ مؤقّتٌ لمعلّمٍ جديد — ناقصٌ عمداً وظاهرُ النقص.

المعلّم الجديد يظهر في جدول الحصص قبل أن يُدخل في المنصّة. وأوّل استيراد
لعام 2026-2027 أسقط أربعاً وعشرين حصة لمعلّمَين لم يُدخلا بعد، فبقيت
ثلاثُ شعبٍ بلا تربيةٍ إسلامية وستٌّ بلا تكنولوجيا.

و`national_id` هو `USERNAME_FIELD` وفريدٌ ولا يقبل الفراغ، فلا سبيل إلى
سجلٍّ بلا رقم. والرقم المختلق الذي يشبه الحقيقيّ أسوأ من نقصٍ معلَن — في
نظامٍ يخضع لقانون حماية البيانات الشخصية القطري خاصّة. فالرقم المؤقّت
عشرون خانة تبدأ بتسعاتٍ تسع: لا يشبه رقماً قطرياً (أحدَ عشر رقماً)، ولا
يُقرأ يوماً على أنّه حقيقي.

والحساب معطَّلٌ بكلمةٍ غير صالحة: سجلٌّ يُسند إليه جدولٌ، لا بابٌ يُدخل منه.
"""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from core.models import CustomUser
from core.models.access import Membership


def _run(*args, **kw):
    out = StringIO()
    call_command("create_placeholder_staff", *args, stdout=out, **kw)
    return out.getvalue()


# ── العرض قبل الكتابة ─────────────────────────────────────────────────


def test_without_apply_no_person_is_created(db, school):
    out = _run("--name", "جمال صالح")

    assert not CustomUser.objects.filter(full_name="جمال صالح").exists()
    assert "عرضٌ فقط" in out


def test_with_apply_the_record_lands(db, school):
    _run("--name", "جمال صالح", "--name", "علي الطيطي", "--apply")

    made = CustomUser.objects.filter(full_name__in=["جمال صالح", "علي الطيطي"])
    assert made.count() == 2
    assert Membership.objects.filter(user__in=made, role__name="teacher").count() == 2


def test_running_it_twice_creates_no_second_record(db, school):
    _run("--name", "جمال صالح", "--apply")

    out = _run("--name", "جمال صالح", "--apply")

    assert CustomUser.objects.filter(full_name="جمال صالح").count() == 1
    assert "قائمٌ أصلاً" in out


# ── نقصٌ ظاهر ─────────────────────────────────────────────────────────


def test_the_placeholder_id_cannot_pass_for_a_real_one(db, school):
    """الرقم القطري أحدَ عشر رقماً. وهذا عشرون تبدأ بتسعات."""
    _run("--name", "جمال صالح", "--apply")

    user = CustomUser.objects.get(full_name="جمال صالح")

    assert len(user.national_id) == 20
    assert user.national_id.startswith("999999999")


def test_the_account_cannot_be_logged_into(db, school):
    """سجلٌّ يُسند إليه جدول، لا بابٌ يُدخل منه."""
    _run("--name", "جمال صالح", "--apply")

    user = CustomUser.objects.get(full_name="جمال صالح")

    assert user.is_active is False
    assert not user.has_usable_password()
    assert user.must_change_password is True


def test_two_placeholders_do_not_collide(db, school):
    """الرقم يُقرأ من القاعدة، فلا يصطدم بسابقٍ له."""
    _run("--name", "أ", "--name", "ب", "--name", "ج", "--apply")

    ids = set(
        CustomUser.objects.filter(full_name__in=["أ", "ب", "ج"]).values_list(
            "national_id", flat=True
        )
    )

    assert len(ids) == 3


def test_it_leaves_a_real_record_alone(db, school):
    """اسمٌ قائمٌ في السجلّ لا يُنشأ له ظلّ."""
    real = CustomUser.objects.create(national_id="28912345678", full_name="جمال صالح")

    _run("--name", "جمال صالح", "--apply")

    assert CustomUser.objects.filter(full_name="جمال صالح").count() == 1
    real.refresh_from_db()
    assert real.national_id == "28912345678"


def test_an_empty_name_stops_the_command(db, school):
    with pytest.raises(CommandError):
        _run("--name", "   ")
