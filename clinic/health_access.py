"""
clinic/health_access.py — فتحُ الملفّ الصحّيّ الكامل بسببٍ مغلق (W-20261020-033)
═══════════════════════════════════════════════════════════════════════════════
الممرّضُ (قدرة `clinic.health_full`) يرى الكاملَ دائماً. والمدير والنائب يريان مختصراً بلا تشخيصٍ
ولا أدويةٍ ولا حساسيّةٍ ولا فصيلةٍ ولا جهةِ طوارئ، ولا يُفتح الكاملُ لهما إلا بسببٍ من القائمة المغلقة
يُسجَّل في التدقيق مع الحقل الحرّ الاختياريّ. الحقلُ الحرّ لا يخرج في إشعارٍ ولا يُعرض في أيّ شاشة.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.core.cache import cache
from django.http import HttpRequest
from django.utils import timezone

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
#: رمزا العذر الصحّيّ: «medical» لعذر الغياب وإذن الخروج، و«illness» لعذر الاختبار.
HEALTH_CODES = frozenset({"medical", "illness"})
#: مدّةُ حفظ من سُجِّل ظهورُه (يومٌ)؛ والمفتاحُ يحمل التاريخَ فيبدأ كلُّ يومٍ من جديد.
PRESENCE_TTL = 60 * 60 * 24


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


def audit_health_rows(
    request: HttpRequest, screen: str, rows: int, *, model_name: str, object_id: object = ""
) -> None:
    """سطرُ تدقيقٍ واحدٌ إن حوت الاستجابةُ بياناً صحّيّاً (`rows` > 0)، ولا سطرَ بدونه (CLN-03)."""
    if rows:
        audit_health_screen(request, screen, model_name=model_name, object_id=object_id, rows=rows)


def audit_health_presence(request: HttpRequest, screen: str, student_ids: Iterable[object]) -> None:
    """سطرٌ عند أوّل ظهورٍ لطالبٍ أمام المستخدم على الشاشة في اليوم (CLN-03، قرار المالك 2026-11-27).

    للشاشات الذاتيّة التحديث: التحديثُ وإعادةُ التحميل لا يكتبان ما لم يظهر طالبٌ جديد، والسطرُ
    للجدد وحدَهم بمعرّفاتهم. اليومُ بتوقيت الدوحة. من سُجِّل يُحفظ في cache بعد كتابة السطر لا
    قبلها: ففقدانُه يكرّر السطرَ ولا يضيّعه.
    """
    shown = {str(pk) for pk in student_ids}
    if not shown:
        return
    day = timezone.localdate().isoformat()
    # بلا فراغاتٍ في المفتاح: تحذّر منها طبقةُ cache.
    key = f"clinic_presence:{request.user.pk}:{screen.replace(' ', '_')}:{day}"
    seen: set[str] = set(cache.get(key) or ())
    new = sorted(shown - seen)
    if not new:
        return
    AuditLog.log(
        user=request.user,
        action="view",
        model_name="ClinicVisit",
        object_repr=f"عرض شاشة صحية — {screen}",
        changes={"screen": screen, "rows": len(new), "students": new},
        request=request,
    )
    cache.set(key, seen | set(new), PRESENCE_TTL)


def audit_care_flag(request: HttpRequest, students: Iterable[Any]) -> None:
    """علامةُ «يحتاج مراعاةً» في اختيار الطالب: من ظهرت عليه وحدَه، بالدمج اليوميّ (CLN-03).

    اسمُ شاشةٍ واحدٌ لكلّ مداخل الاختيار فلا يكرّر البحثُ ولا القائمةُ ولا التأكيدُ السطرَ، ولا يُسجَّل
    مصطلحُ البحث.
    """
    audit_health_presence(request, "علامة المراعاة", [s.id for s in students if s.needs_care])


def audit_health_export(
    user: Any, screen: str, *, model_name: str, object_id: object, rows: int
) -> None:
    """كـ`audit_health_rows` لبنّاءِ تصديرٍ لا طلبَ معه (يعمل في العامل): المستخدمُ وحدَه."""
    request = HttpRequest()
    request.user = user
    audit_health_rows(request, screen, rows, model_name=model_name, object_id=object_id)


def audit_class_grid_presence(request: HttpRequest, page: Any) -> None:
    """جدولُ الرصد: من ظهرت وجهتُه «العيادة» في «خارجون الآن» أو في تلميح دائرة الخروج (CLN-03)."""
    shown = [
        row.student.pk
        for row in page.rows
        if (row.exit and row.exit.destination == "clinic")
        # نصُّ التلميح كما يبنيه `class_grid.exit_line`.
        or any(badge and "العيادة (بإذن)" in badge.tip for _, _, badge in row.pairs)
    ]
    audit_health_presence(request, "جدول رصد المعلم", shown)


def audit_health_codes(
    request: HttpRequest,
    screen: str,
    codes: Iterable[str],
    *,
    model_name: str,
    object_id: object = "",
) -> None:
    """كـ`audit_health_rows` لشاشةٍ تعرض أنواعَ أعذارٍ أو أسبابَ خروج: يُعدّ الصحّيُّ منها وحدَه."""
    rows = sum(1 for code in codes if code in HEALTH_CODES)
    audit_health_rows(request, screen, rows, model_name=model_name, object_id=object_id)


def audit_student_events_health(
    request: HttpRequest, context: dict[str, Any], student_id: object
) -> None:
    """صفحةُ «تصحيح وعذر»: الأعذارُ المعروضة، وعذرُ سطر الغياب في صفحة السجلّ المعروضة.

    ويُسجَّل ظهورُ الطالب (بالدمج اليوميّ) إن حملت صفحةُ السجلّ وجهةَ «العيادة» أو مكانَها.
    """
    if any(
        (source == "exit" and row.destination == "clinic")
        or (source == "attendance" and row.status == "absent" and row.whereabouts == "clinic")
        for source, row in context["events_page"]
    ):
        audit_health_presence(request, "سجل أحداث الطالب", [student_id])
    codes = [excuse.kind for excuse in context["excuses"]]
    codes += [
        row.excuse_type
        for source, row in context["events_page"]
        if source == "attendance" and row.status == "absent"
    ]
    audit_health_codes(
        request, "تصحيح وعذر الطالب", codes, model_name="AbsenceExcuse", object_id=student_id
    )


def audit_absence_days_health(
    request: HttpRequest, days: Iterable[Any], student_id: object
) -> None:
    """ملفُّ الغياب: نوعُ العذر على سطر اليوم، وسببُ الرفض حين يُعرض."""
    codes: list[str] = []
    for day in days:
        if day.excuse:
            codes.append(day.excuse.kind)
        elif day.rejected and not day.waiting and day.rejected.rejection_reason:
            codes.append(day.rejected.kind)
    audit_health_codes(
        request, "ملف غياب الطالب", codes, model_name="AbsenceExcuse", object_id=student_id
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
