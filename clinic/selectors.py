"""
clinic/selectors.py — قراءاتُ العيادة (W-20261020-030)
"""

from __future__ import annotations


def search_students(school, term: str, limit: int) -> list:
    """طلبةُ المدرسة النشطون بالاسم (احتواء)، وصفُّ كلٍّ منهم النشط في `active_enrollments` — استعلامان لا أكثر."""
    from django.db.models import Prefetch

    from core.models import CustomUser, StudentEnrollment

    return list(
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__role__name="student",
            memberships__is_active=True,
            full_name__icontains=term,
        )
        .distinct()
        .prefetch_related(
            Prefetch(
                "enrollments",
                queryset=StudentEnrollment.objects.filter(is_active=True).select_related(
                    "class_group"
                ),
                to_attr="active_enrollments",
            )
        )
        .order_by("full_name")[:limit]
    )
