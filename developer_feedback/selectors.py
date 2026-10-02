"""قراءةُ بيانات شاشة تأليف رسالة المطوّر (الاتّجاه المعاكس) — لا كتابةَ هنا."""

from __future__ import annotations

from core.models import CustomUser, Department
from core.models.access import Role
from developer_feedback.models import OutboundMessage
from developer_feedback.services.audience import STAFF_ROLES


def active_departments(school):
    """الأقسامُ النشطة مرتَّبةً كما تُعرض في المنصّة."""
    return Department.objects.filter(school=school, is_active=True).order_by("sort_order", "name")


def staff_directory(school, exclude_user):
    """[(مستخدم، تسميةُ دوره)] لكلّ موظّفي المدرسة — لا الطلبةَ ولا أولياءَ الأمور.

    «فردٌ بعينه» يعني أيَّ موظّف (قرارُ المالك 2026-10-01)، لا المعلّمين المنتمين
    لقسمٍ وحدَهم. `get_role()` نصٌّ لا حقلَ اختياراتٍ، فالتسميةُ تُحسب هنا.
    """
    role_labels = dict(Role.ROLES)
    users = (
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__is_active=True,
            memberships__role__name__in=STAFF_ROLES,
        )
        .exclude(id=exclude_user.id)
        .distinct()
        .order_by("full_name")
    )
    return [(u, role_labels.get(u.get_role(), u.get_role())) for u in users]


def broadcasts_sent_by(user):
    """سجلُّ ما بثّه المطوّر، الأحدثُ أوّلاً."""
    return OutboundMessage.objects.filter(sent_by=user).order_by("-created_at")
