"""
governance/media_selectors.py — قراءةُ مالك الملف المخزَّن ومدرسته وأدوارِه (طبقة القراءة).

انتقلت من `views_media.py` (البند 9، سداد ديون): العرضُ يستقبل ويردّ، والاستعلامُ هنا.
والمرجعُ الأمنيّ في `views_media._authorize` كما كان — fail-closed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

#: (school_id، owner_user_id، الأدوار المسموحة أو None، الملفُّ ملفُّ طالب؟)
FileAccess = tuple[Any, Any, "frozenset[str] | set[str] | None", bool]


def _staff_file(obj: Any) -> FileAccess:
    """مرفقاتُ الإجازات ونموذج 03 (م-31) قد تحوي تقارير طبية حسّاسة → قيادة المدرسة فقط (عدا المالك)."""
    return (obj.school_id, obj.staff_id, {"principal", "vice_admin"}, False)


def _exception_file(obj: Any) -> FileAccess:
    """مرفقُ نموذج 03 (م-31): تقريرٌ طبيّ محتمل — لصاحبه ولقيادة المدرسة (المدير ونائبيه)."""
    from staff_affairs.models import EXCEPTION_EVIDENCE_ROLES

    return (obj.school_id, obj.staff_id, set(EXCEPTION_EVIDENCE_ROLES), False)


def resolve_file_access(name: str) -> FileAccess | None:
    """يُعيد (school_id, owner_user_id, allowed_roles, student_owned) للملف، أو None إن لم يُعرَف مالكه.

    `student_owned`: الملفُّ ملفُّ طالبٍ (`owner_user_id` هو الطالب)، فيُسأل عنه نطاقُ الجناح.
    """
    # استيراد كسول لتفادي الدورات
    from core.models import School
    from core.permissions import (
        LIBRARY_FULL,
        LIBRARY_VIEW,
        QUALITY_VIEW,
        STUDENT_AFFAIRS_VIEW,
        STUDENT_FOLLOW_UP,
        WING_DAY_RECORD,
    )
    from library.models import LibraryBook
    from operations.models import AbsenceExcuse, StudentAttendance
    from quality.models import ProcedureEvidence
    from staff_affairs.models import AttendanceException, LeaveRequest
    from student_affairs.models import StudentActivity

    resolvers: tuple[tuple[Any, str, Callable[[Any], FileAccess]], ...] = (
        # عذرُ التأخّر الصباحيّ: رصدُه من عمل المشرف (الدليل 2026 م 3.4.2.2) — لجناحه.
        (
            StudentAttendance,
            "excuse_file",
            lambda o: (o.school_id, o.student_id, STUDENT_AFFAIRS_VIEW | STUDENT_FOLLOW_UP, True),
        ),
        # مستندُ عذر الغياب: من يرصد في الأجنحة ومن يرى شؤونَ الطلبة — والطالبُ صاحبُه.
        (
            AbsenceExcuse,
            "document",
            lambda o: (o.school_id, o.student_id, STUDENT_AFFAIRS_VIEW | WING_DAY_RECORD, True),
        ),
        (LeaveRequest, "attachment", _staff_file),
        (AttendanceException, "evidence_file", _exception_file),
        (
            ProcedureEvidence,
            "file",
            lambda o: (o.procedure.school_id, o.uploaded_by_id, QUALITY_VIEW, False),
        ),
        (
            StudentActivity,
            "attachment",
            lambda o: (o.school_id, o.student_id, STUDENT_AFFAIRS_VIEW, True),
        ),
        (
            LibraryBook,
            "digital_file",
            lambda o: (o.school_id, None, LIBRARY_VIEW | LIBRARY_FULL, False),
        ),
        # الشعار: أي مستخدم مُصادَق من نفس المدرسة (allowed_roles=None)
        (School, "logo", lambda o: (o.id, None, None, False)),
    )
    for model, field, extract in resolvers:
        obj = model.objects.filter(**{field: name}).first()
        if obj is not None:
            return extract(obj)
    return None


def stored_file_named(name: str) -> Any:
    """`StoredFile` باسمه أو None."""
    from core.models import StoredFile

    return StoredFile.objects.filter(name=name).first()
