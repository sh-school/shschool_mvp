"""جلبُ مستخدمٍ بمعرّفٍ قادمٍ من الطلب — داخلَ مدرسةٍ بعينها لا في المنصّة كلِّها.

`core_customuser` عالميٌّ بالتصميم (الشخصُ قد يملك عضويّاتٍ في أكثر من مدرسة)، فلا تحميه `RLS` كجداول المدارس؛ فالحمايةُ
على الاستعلام. وكلُّ عرضٍ يجلب مستخدماً بـ`get_object_or_404(CustomUser, id=…)` يقبل مستخدماً من مدرسةٍ أخرى: كشفُ اسمٍ في القراءة، وربطُ
غريبٍ بسجلّ مدرستك في الكتابة (`docs/privacy/tenant_isolation_audit_2026-10-05.md`).

القاعدة: كلُّ معرّفِ مستخدمٍ من `request` يمرّ بهذا المنفذ مع مدرسة الطلب. و`in_school` لا `filter(memberships__school=…)`: الأخيرُ ضمٌّ يعيد
صفّين لمن له عضويّتان في المدرسة فيرفع `get()` استثناءً (`core/querysets.py`).
"""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from core.models.user import CustomUser


def _users(school: Any, ever: bool) -> QuerySet[CustomUser]:
    # `in_school`/`ever_in_school` في core/querysets.py بلا تلميحاتِ أنواع؛ تُحصَر هنا في موضعٍ واحد.
    users = (
        CustomUser.objects.ever_in_school(school)  # type: ignore[no-untyped-call]
        if ever
        else CustomUser.objects.in_school(school)  # type: ignore[no-untyped-call]
    )
    return cast("QuerySet[CustomUser]", users)


def school_user_or_404(school: Any, pk: Any, *, ever: bool = False) -> CustomUser:
    """المستخدمُ إن كان في هذه المدرسة (`ever`: ولو انتهت عضويّتُه)، وإلّا 404 — كأنّه غيرُ موجود.

    معرّفٌ ليس UUID صالحاً يُعامَل كغير موجود (404) لا خطأً 500.
    """
    users = _users(school, ever)
    try:
        return get_object_or_404(users, pk=pk)
    except (ValidationError, ValueError, TypeError):
        from django.http import Http404

        raise Http404("لا مستخدمَ بهذا المعرّف في مدرستك") from None


def school_user_or_none(school: Any, pk: Any, *, ever: bool = False) -> CustomUser | None:
    """كـ`school_user_or_404` لكن بـ`None` بدل 404 — حيث الحقلُ اختياريٌّ (معرّفٌ فارغٌ أو غريبٌ ⇐ لا أحد)."""
    if not pk:
        return None
    users = _users(school, ever)
    try:
        return users.filter(pk=pk).first()
    except (ValidationError, ValueError, TypeError):
        return None
