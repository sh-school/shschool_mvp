"""تعيينُ منتسبٍ ومغادرتُه — قرارٌ يُوثَّق، لا صفٌّ يُضاف ويُحذف.

    Appointment ≠ INSERT
    Departure   ≠ DELETE

فالالتحاقُ بالمدرسة والمغادرةُ منها قراران إداريّان لكلٍّ منهما تاريخٌ ومرجع.
ولو تُركا لإدخالٍ حرٍّ لصار في السجلّ التحاقٌ بلا قرار، ومغادرةٌ تمحو تاريخَ
صاحبها: من نُقل هذا الصيف له خمسٌ وعشرون حصّةً في جدول العام الماضي، وحذفُ
عضويّته يقطع تلك الحصص عن صاحبها.

## ثلاثة قيود

    المرجعُ لازم           تعييناً كان أو مغادرة
    القسمُ لأهل التدريس    يحرسه `Membership.clean`
    الشخصُ لا يتكرّر       من كان وليَّ أمرٍ ثمّ عُيّن معلّماً حسابٌ واحدٌ بعضويّتين

والحسابُ يُفتح بلا كلمة مرورٍ صالحة: يُعرَف في النظام ولا يُدخَل به حتّى
تُصدَر له واحدة — كما في `complete_staff_record`.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import CustomUser, Membership
from core.models.access import ALL_STAFF_ROLES, DEPARTMENT_ROLES, Role


class AppointmentError(ValidationError):
    """قرارٌ لا يستقيم — رسالتُه للمستخدم لا للسجلّ."""


def _require(condition, field, message):
    if not condition:
        raise AppointmentError({field: message})


@transaction.atomic
def appoint(
    *,
    school,
    national_id,
    full_name,
    role_name,
    by,
    department=None,
    email="",
    phone="",
    employee_number="",
    joined_on=None,
    reference="",
    note="",
):
    """يُلحق شخصاً بكادر المدرسة — حساباً وعضويّةً ومرجعَ قرار.

    ومن كان في النظام بحسابٍ قائم (وليَّ أمرٍ مثلاً) لا يُنشأ له ثانٍ: تُضاف
    إليه عضويّةٌ بالدور الجديد، فيبقى للشخص حسابٌ واحدٌ وسجلٌّ واحد.
    """
    national_id = (national_id or "").strip()
    full_name = (full_name or "").strip()
    reference = (reference or "").strip()
    joined_on = joined_on or timezone.localdate()

    _require(national_id.isdigit() and 5 <= len(national_id) <= 20, "national_id", "الرقمُ الشخصيُّ أرقامٌ من 5 إلى 20 خانة.")
    _require(full_name, "full_name", "الاسمُ الكاملُ لازم.")
    _require(reference, "reference", "التعيينُ قرارٌ — ومرجعُه لازم.")
    _require(role_name in ALL_STAFF_ROLES, "role_name", "هذا الدورُ ليس من أدوار الكادر.")
    _require(
        department is None or role_name in DEPARTMENT_ROLES,
        "department",
        "القسمُ الأكاديميُّ لأهل التدريس — وهذا الدورُ ليس منهم.",
    )

    role, _ = Role.objects.get_or_create(school=school, name=role_name)
    user = CustomUser.objects.filter(national_id=national_id).first()
    if user is None:
        user = CustomUser(national_id=national_id, full_name=full_name, email=email, phone=phone)
        user.set_unusable_password()
        user.full_clean(exclude=["password", "last_login"])
        user.save()
    else:
        _require(
            not Membership.objects.filter(
                user=user, school=school, role=role, is_active=True
            ).exists(),
            "national_id",
            f"لـ{user.full_name} عضويّةٌ نشطةٌ بهذا الدور في المدرسة.",
        )

    if employee_number and hasattr(user, "employee_number") and not user.employee_number:
        user.employee_number = employee_number
        user.save(update_fields=["employee_number"])

    membership = Membership(
        user=user,
        school=school,
        role=role,
        department_obj=department,
        joined_at=joined_on,
        appointment_reference=reference,
        appointment_note=(note or "").strip(),
        is_active=True,
    )
    membership.full_clean(exclude=["user", "school", "role"])
    membership.save()
    user.invalidate_active_membership()
    return membership


@transaction.atomic
def reinstate(*, membership, by=None, note=""):
    """يُلغي مغادرةً سُجّلت بالخطأ — والتصحيحُ يُوثَّق كما وُثّق الخطأ.

    المغادرةُ قرارٌ يُسجَّل، وتسجيلُها خطأً خطأٌ يُصحَّح — ولا يُصحَّح بمحوٍ:
    يبقى في السجلّ أنّ مغادرةً كُتبت في يوم كذا ثمّ أُلغيت، فمن قرأ الملفَّ
    بعد سنةٍ لم يجد فجوةً بلا تفسير.
    """
    if membership.left_at is None and membership.is_active:
        raise AppointmentError({"__all__": "هذه العضويّةُ قائمةٌ — لا مغادرةَ تُلغى."})

    clash = (
        Membership.objects.filter(
            user=membership.user,
            school=membership.school,
            role=membership.role,
            is_active=True,
        )
        .exclude(pk=membership.pk)
        .exists()
    )
    _require(not clash, "__all__", "له عضويّةٌ نشطةٌ بهذا الدور — لا تُرجَع الثانية.")

    trail = f"أُلغيت مغادرةُ {membership.left_at} ({membership.get_departure_reason_display()}"
    trail += f" — {membership.departure_reference})" if membership.departure_reference else ")"
    if note:
        trail += f" — {note}"
    membership.appointment_note = " · ".join(filter(None, [membership.appointment_note, trail]))[
        :200
    ]
    membership.left_at = None
    membership.departure_reason = ""
    membership.departure_reference = ""
    membership.departure_note = ""
    membership.is_active = True
    membership.save(
        update_fields=[
            "left_at",
            "departure_reason",
            "departure_reference",
            "departure_note",
            "is_active",
            "appointment_note",
        ]
    )

    user = membership.user
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
    user.invalidate_active_membership()
    return membership


@transaction.atomic
def depart(*, membership, on=None, reason, reference, note="", by=None):
    """يسجّل مغادرةَ منتسبٍ — والعضويّةُ تُطفأ ولا تُمحى.

    والحسابُ يُعطَّل متى لم تبقَ له عضويّةٌ نشطةٌ في أيّ مدرسة، فلا يبقى بابٌ
    مفتوحٌ لمن غادر.
    """
    membership.record_departure(
        on=on or timezone.localdate(),
        reason=reason,
        reference=(reference or "").strip(),
        note=(note or "").strip(),
    )
    user = membership.user
    if not Membership.objects.filter(user=user, is_active=True).exists() and user.is_active:
        user.is_active = False
        user.save(update_fields=["is_active"])
    user.invalidate_active_membership()
    return membership
