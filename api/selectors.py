"""قراءاتُ REST المشتركة — خارج ملفّ العروض كي لا يحمل سقفَ الطبقات (W-20261101-007)."""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404

from core.models import CustomUser


def school_student_or_404(school: Any, student_id: Any) -> CustomUser:
    """طالبٌ من عضويّة مدرسة الطلب النشطة — وإلا 404؛ فلا يُقرأ مستخدمُ مدرسةٍ أخرى بمعرّفه."""
    return get_object_or_404(
        CustomUser.objects.filter(
            memberships__school=school, memberships__is_active=True
        ).distinct(),
        id=student_id,
    )
