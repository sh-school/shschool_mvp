"""قراءةُ شاشة «إدارة الأجنحة»: لكلّ جناحٍ حاملاه اليوم والإنابةُ وسجلُّ التعيينات."""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.db.models import Prefetch

from core.models import CustomUser, Membership, Wing, WingAssignment, WingCoverage


def management_rows(school: Any, year: str, day: dt.date) -> list[dict[str, Any]]:
    """صفوفُ الأجنحة: الحاملان اليومَ، وهل يغطّيهما بديلٌ، وآخرُ ستّة تعيينات (الأحدثُ أوّلاً)."""
    wings = (
        Wing.objects.filter(school=school, academic_year=year, is_active=True)
        .prefetch_related(
            Prefetch("assignments", queryset=WingAssignment.objects.select_related("user")),
            Prefetch("coverages", queryset=WingCoverage.objects.select_related("substitute")),
        )
        .order_by("order", "code")
    )
    rows = []
    for wing in wings:
        holders = wing.holders(day)
        acting = [c for c in wing.coverages.all() if c.covers(day)]
        rows.append(
            {
                "wing": wing,
                "supervisor": holders.supervisor,
                "field": holders.field,
                "acting": acting,
                "history": sorted(wing.assignments.all(), key=lambda a: a.start_date, reverse=True)[
                    :6
                ],
            }
        )
    return rows


def eligible_people(school: Any) -> list[CustomUser]:
    """من يصلح للتعيين في المدرسة (بالدور) مرتّبين بالاسم."""
    return list(
        CustomUser.objects.filter(
            id__in=Membership.objects.filter(
                school=school, is_active=True, role__name__in=WingAssignment.ELIGIBLE_ROLES
            ).values("user_id")
        )
        .distinct()
        .order_by("full_name")
    )
