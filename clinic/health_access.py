"""
clinic/health_access.py — فتحُ الملفّ الصحّيّ الكامل بسببٍ مغلق (W-20261020-033)
═══════════════════════════════════════════════════════════════════════════════
الممرّضُ (قدرة `clinic.health_full`) يرى الكاملَ دائماً. والمدير والنائب يريان مختصراً بلا تشخيصٍ
ولا أدويةٍ ولا حساسيّةٍ ولا فصيلةٍ ولا جهةِ طوارئ، ولا يُفتح الكاملُ لهما إلا بسببٍ من القائمة المغلقة
يُسجَّل في التدقيق مع الحقل الحرّ الاختياريّ. الحقلُ الحرّ لا يخرج في إشعارٍ ولا يُعرض في أيّ شاشة.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from clinic.selectors import student_clinic_data
from core.audit_repr import masked_repr
from core.models import AuditLog

OPEN_REASONS = (
    ("emergency_care", "رعاية طارئة"),
    ("chronic_followup", "متابعة مزمنة"),
    ("parent_inquiry", "استفسار رسمي من ولي الأمر"),
    ("official_report", "تقرير رسمي"),
    ("audit", "تدقيق"),
    ("other", "أخرى"),
)
_CODES = {code for code, _ in OPEN_REASONS}
NOTE_MAX = 200


def clean_reason(code: str) -> str | None:
    """رمزُ السبب إن كان من القائمة المغلقة وإلا `None`."""
    code = (code or "").strip()
    return code if code in _CODES else None


def log_full_open(request, record, student, reason: str, note: str = "") -> None:
    """يسجّل فتحَ الكامل: السببُ والملاحظةُ الحرّةُ في التدقيق وحدَه (لا نصَّ صحّيّاً)."""
    AuditLog.log(
        user=request.user,
        action="view",
        model_name="HealthRecord",
        object_id=record.pk,
        object_repr=f"فتح السجل الصحي الكامل — {masked_repr(student)}",
        changes={"screen": "السجل الصحي الكامل", "reason": reason, "note": (note or "")[:NOTE_MAX]},
        request=request,
    )


def audit_health_screen(
    request: HttpRequest,
    screen: str,
    *,
    model_name: str,
    object_id: object = "",
    rows: Any = None,
) -> None:
    """يكتب سطرَ تدقيقٍ لفتح شاشةٍ تعرض بياناً صحيّاً (PDPPL م.11 وم.13: سجلُّ الوصول).

    معرّفاتٌ فقط: نوعُ الشاشة وعددُ الصفوف ومعرّفُ السجلّ — لا اسمَ طالبٍ ولا نصَّ صحّيّاً
    (reason/treatment/تشخيص)؛ فسجلُّ التدقيق ملحقٌ لا يُعدَّل ويبقى بعد محو صاحبه.
    كلُّ شاشةٍ صحّيّةٍ جديدةٍ تستدعيه، ويفرض ذلك tests/test_clinic_audit_every_screen.py.
    """
    changes: dict[str, Any] = {"screen": screen}
    if rows is not None:
        # قائمة الاستعلام تُعدّ هنا لا في العرض فلا يزيد عدّ الطبقات فيه
        changes["rows"] = rows if isinstance(rows, int) else rows.count()
    AuditLog.log(
        user=request.user,
        action="view",
        model_name=model_name,
        object_id=object_id,
        object_repr=f"عرض شاشة صحية — {screen}",
        changes=changes,
        request=request,
    )


def student_clinic_tab(
    request: HttpRequest, school: Any, student: Any, *, summary_only: bool
) -> dict[str, Any]:
    """بياناتُ تبويب العيادة في ملفّ الطالب، ويُسجَّل سطرُ تدقيقٍ إن حوت بياناً صحّيّاً (CLN-03).

    الحارسُ (القدرةُ ونطاقُ الطالب والمدرسة) على العرض المستدعي. والقراءةُ وتقييدُ
    `summary_only` في `clinic.selectors.student_clinic_data`.
    """
    shown, record = student_clinic_data(school, student, summary_only=summary_only)
    has_health_data = bool(shown or (record and (record.needs_care or record.blood_type_encrypted)))
    if has_health_data:
        audit_health_screen(
            request,
            "تبويب العيادة في ملف الطالب",
            model_name="HealthRecord" if record else "ClinicVisit",
            object_id=student.pk,
            rows=len(shown),
        )
    return {"clinic_visits": shown, "health_record": record, "has_health_data": has_health_data}


def reveal_chronic(request, student_id) -> str:
    """اسمُ الحالة المزمنة وحدَه لصاحب الطلب، ويُسجَّل الكشف؛ و`Http404` خارج نطاقه (W-20261020-033).

    المقيَّدُ بجناحه بنطاق جناحه. لا أدويةَ ولا حساسيّةَ ولا ملاحظات. والمعلّمُ خارجُ القدرة: يرى
    «يحتاج مراعاةً» فقط بلا اسم.
    """
    from django.http import Http404

    from clinic.selectors import chronic_record
    from wings.scope import student_scope_for

    student, record = chronic_record(request.school, student_id)
    if student is None:
        raise Http404
    student_scope_for(request).require_student(student_id)
    AuditLog.log(
        user=request.user,
        action="view",
        model_name="HealthRecord",
        object_id=record.pk if record else "",
        object_repr=f"كشف اسم الحالة المزمنة — {masked_repr(student)}",
        changes={"screen": "اسم الحالة المزمنة (صفحة الطالب)"},
        request=request,
    )
    return record.chronic_diseases if record else ""
