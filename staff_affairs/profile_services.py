"""تحريرُ ملفّ المنتسب — كلُّ حقلٍ يُعرَف من غيّره ومتى وممّا إلى ماذا.

    Save ≠ UPDATE

فملفُّ الموظّف وثيقةٌ إداريّة: رقمُه الوظيفيُّ ورخصتُه ومسمّاه وتاريخُ التحاقه
أرقامٌ تُبنى عليها قراراتٌ وتُراجَع بعد سنين. وحفظٌ لا يُعرَف صاحبُه ولا وقتُه
يجعل السجلَّ يقول «هكذا هو» ولا يقول «من قال ذلك ومتى».

فكلُّ حفظٍ هنا:

    ١. يُقارن الجديدَ بالقديم حقلاً حقلاً — ولا يكتب ما لم يتغيّر.
    ٢. يكتب في `AuditLog` ما تغيّر: من أيّ قيمةٍ إلى أيّ قيمة.
    ٣. يختم بمن حفظ ومتى ومن أيّ عنوان (يأخذها `AuditLog.log` من الطلب).

فإن لم يتغيّر شيءٌ لم يُكتب سطرٌ في السجلّ — كي يبقى السجلُّ قابلاً للقراءة.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from core.models import AuditLog, Department

#: حقولُ الشخص — تخصّ صاحبَها أينما عمل.
PERSON_FIELDS = ("full_name", "employee_number", "email", "phone", "nationality")

#: حقولُ الرخصة المهنيّة — وزاريّةٌ لها رقمٌ وتاريخُ انتهاء.
LICENSE_FIELDS = ("professional_license_number", "professional_license_expiry")

#: حقولُ العضويّة — تخصّ عملَه في هذه المدرسة بعينها.
EMPLOYMENT_FIELDS = ("job_title", "joined_at", "appointment_reference", "appointment_note")

LABELS = {
    "full_name": "الاسم الكامل",
    "employee_number": "الرقم الوظيفي",
    "email": "البريد الإلكتروني",
    "phone": "الجوال",
    "nationality": "الجنسية",
    "professional_license_number": "رقم الرخصة المهنية",
    "professional_license_expiry": "انتهاء الرخصة",
    "job_title": "المسمّى الوظيفي",
    "joined_at": "تاريخ الالتحاق",
    "appointment_reference": "مرجع التعيين",
    "appointment_note": "ملاحظة التعيين",
    "department_obj": "القسم الأكاديمي",
    "role": "الدور",
}


def _diff(instance, data, fields):
    """ما تغيّر فعلاً — {الحقل: (القديم، الجديد)}."""
    changes = {}
    for field in fields:
        if field not in data:
            continue
        before = getattr(instance, field)
        after = data[field]
        if (before or "") != (after or ""):
            changes[field] = (before, after)
    return changes


def _as_log(changes):
    return {
        LABELS.get(field, field): {"من": _text(before), "إلى": _text(after)}
        for field, (before, after) in changes.items()
    }


def _text(value):
    if value in (None, ""):
        return "—"
    return str(value)


@transaction.atomic
def save_person(*, user, data, by, request=None):
    """بياناتُ الشخص — الاسمُ والرقمُ الوظيفيُّ والبريدُ والجوّالُ والجنسيّة."""
    changes = _diff(user, data, PERSON_FIELDS + LICENSE_FIELDS)
    if not changes:
        return {}

    for field, (_before, after) in changes.items():
        setattr(user, field, after)
    user.full_clean(exclude=["password", "last_login"])
    user.save(update_fields=list(changes))

    AuditLog.log(
        user=by,
        action="update",
        model_name="CustomUser",
        object_id=user.id,
        object_repr=user.full_name,
        changes=_as_log(changes),
        request=request,
    )
    return changes


@transaction.atomic
def save_employment(*, membership, data, by, request=None):
    """بياناتُ الوظيفة — المسمّى وتاريخُ الالتحاق ومرجعُه والقسم.

    والدورُ لا يُغيَّر من هنا: تغييرُ الدور تعيينٌ جديد أو نقلٌ بين وظيفتين،
    وله بابُه. وهذه الشاشةُ تصحّح ما كُتب لا تُنشئ قراراً.
    """
    changes = _diff(membership, data, EMPLOYMENT_FIELDS)

    if "department" in data:
        before = membership.department_obj
        after = data["department"]
        if before != after:
            if after is not None and not isinstance(after, Department):
                raise ValidationError({"department": "قسمٌ غيرُ معروف."})
            changes["department_obj"] = (before, after)
            membership.department_obj = after

    if not changes:
        return {}

    for field, (_before, after) in changes.items():
        if field != "department_obj":
            setattr(membership, field, after)
    membership.full_clean(exclude=["user", "school", "role"])
    membership.save(update_fields=list(changes))

    AuditLog.log(
        user=by,
        action="update",
        model_name="Membership",
        object_id=membership.id,
        object_repr=f"{membership.user.full_name} — {membership.role.get_name_display()}",
        changes=_as_log(changes),
        school=membership.school,
        request=request,
    )
    return changes


def history(user, membership=None, limit=20):
    """سجلُّ تعديلات هذا الملفّ — أحدثُها أوّلاً، بمن حفظ ومتى وماذا.

    والسجلُّ يجمع ما كتبته هذه الشاشةُ وما كتبته إشاراتُ النظام، وشكلُهما
    مختلف: الأولى تقول «من كذا إلى كذا»، والثانيةُ تُدرج قيماً بأسماءٍ
    إنجليزيّة. فيُوحَّدان هنا سطوراً مقروءةً — والقالبُ لا يعرف الفرق.
    """
    ids = [str(user.id)]
    if membership is not None:
        ids.append(str(membership.id))
    rows = (
        AuditLog.objects.filter(object_id__in=ids)
        .select_related("user")
        .order_by("-timestamp")[:limit]
    )
    out = []
    for entry in rows:
        lines = _lines(entry.changes)
        # كلُّ حفظٍ تكتبه إشارةُ النظام مرّةً بلقطة الحقول كلِّها، فيصير لكلّ
        # تعديلٍ سطران: واحدٌ يقول ما تغيّر وآخرُ لا يقول شيئاً. يُسقَط الثاني.
        if entry.action == "update" and not lines:
            continue
        out.append(
            {
                "when": entry.timestamp,
                "who": entry.user.full_name if entry.user_id else "—",
                "what": f"{entry.get_action_display()} · {entry.get_model_name_display()}",
                "lines": lines,
            }
        )
    return out


def _lines(changes):
    """يقرأ الشكلين: {حقل: {من، إلى}} و{حقل: قيمة}."""
    if not isinstance(changes, dict):
        return []
    out = []
    for key, value in changes.items():
        label = LABELS.get(key, key)
        if isinstance(value, dict) and ("من" in value or "إلى" in value):
            out.append(f"{label}: {_text(value.get('من'))} ← {_text(value.get('إلى'))}")
        elif key in LABELS and value not in (None, "", []):
            # الحقولُ التقنيّةُ (`is_active`، `totp_enabled`…) تُسقَط من العرض:
            # الإشارةُ تلتقط لقطةَ الحقول كلِّها، والقارئُ يريد ما يخصّ الملفّ.
            out.append(f"{label}: {_text(value)}")
    return out
