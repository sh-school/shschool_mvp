"""حارسُ الاستيراد: لا يمسّ استيرادُ الطلاب حسابَ موظّف (W-20261008-024).

الاستيرادُ يطابق الحسابَ بالرقم الشخصيّ ثمّ يكتب فوقه (الاسم والهاتف والبريد
وغيرها) ويُنشئ له عضويّةً. فلو وافق رقمٌ في الملف رقمَ موظّفٍ لتبدّلت بياناتُه
وأُضيفت له عضويّةُ طالب/وليّ — ثغرةُ تعديلِ حساب لا يملك المستورِدُ صلاحيّتَه.

القاعدة: يُرفض ويُتخطّى بسطر تقريرٍ، قبل أيّ كتابةٍ، كلُّ رقمٍ يطابق حساباً له
عضويّةٌ بدورٍ وظيفيّ (أيّ مدرسة، فعّالةً كانت أو لا — تحفّظٌ). ويُقبل حسابُ
طالب/وليّ أو بلا عضويّة.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db.models import Q

# كلُّ دورٍ وظيفيّ؛ و«specialist» موظّفٌ في `Role.is_staff_role` وإن لم يكن في المجموعة.
_EXTRA_STAFF_ROLES = frozenset({"specialist"})


def staff_role_names() -> frozenset[str]:
    from core.models.access import ALL_STAFF_ROLES

    return frozenset(ALL_STAFF_ROLES) | _EXTRA_STAFF_ROLES


def find_staff_nids(nids: Iterable[str]) -> set[str]:
    """الأرقامُ الشخصيّةُ من `nids` التي لأصحابها عضويّةُ موظّف، أو حسابٌ إداريّ
    (`is_superuser`/`is_staff`) ولو بلا عضويّة — استعلامان لا أكثر."""
    from core.models import CustomUser, Membership

    wanted = {n for n in nids if n}
    if not wanted:
        return set()
    by_role = set(
        Membership.objects.filter(
            user__national_id__in=wanted, role__name__in=staff_role_names()
        ).values_list("user__national_id", flat=True)
    )
    admins = set(
        CustomUser.objects.filter(national_id__in=wanted)
        .filter(Q(is_superuser=True) | Q(is_staff=True))
        .values_list("national_id", flat=True)
    )
    return by_role | admins


def mask_nid(nid: str) -> str:
    """رقمٌ شخصيّ مستور: آخرُ ثلاثِ خاناتٍ فقط."""
    nid = str(nid)
    return "*" * max(0, len(nid) - 3) + nid[-3:]


def skip_line(row_num: int, nid: str, *, as_parent: bool) -> str:
    where = "وليّ الأمر" if as_parent else "الطالب"
    tail = " — يُربَط يدويّاً إن لزم" if as_parent else " — لم يُعدَّل الحسابُ ولم تُنشأ له عضويّة"
    return f"سطر {row_num}: رقم {where} {mask_nid(nid)} لحسابِ موظّفٍ — تُخطّي{tail}"


def record_skip(stats: dict[str, Any], row_num: int, nid: str, *, as_parent: bool) -> None:
    stats["staff_skipped"] = stats.get("staff_skipped", 0) + 1
    stats["errors"].append(skip_line(row_num, nid, as_parent=as_parent))


def audit_staff_skipped(user: Any, school: Any, count: int) -> None:
    """أثرٌ بعددِ المتخطَّى فقط — لا أسماء ولا أرقام."""
    from core.models.audit import AuditLog

    AuditLog.objects.create(
        school=school,
        user=user,
        action="update",
        model_name="other",
        object_id="",
        object_repr=f"استيرادُ الطلاب: تُخطّي {count} رقماً لحساباتِ موظّفين"[:300],
        changes={"event": "import_staff_accounts_skipped", "count": count},
    )
