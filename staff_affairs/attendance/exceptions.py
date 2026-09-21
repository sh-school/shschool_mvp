"""استثناءُ التأخير الصباحيّ أو الخروج المبكر — نموذج 03.

من تفكيك ``staff_affairs/attendance.py`` (الحزمةُ تُصدّر الأسماءَ نفسَها في ``__init__``).
"""

from __future__ import annotations

from datetime import date, time
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

import staff_affairs.attendance as _pkg
from core.models.school import School
from core.models.user import CustomUser
from staff_affairs.models import (
    EXCEPTION_TYPES,
    AttendanceException,
    StaffAttendance,
)

from .context import (
    NON_STAFF_ROLES,
    PRINCIPAL,
    PolicyError,
    _audit,
    _role_of,
    _StageDay,
)
from .permits import (
    PermitService,
)
from .rules import (
    WORK_END,
    WORK_START,
)

# ══════════════════════════════════════════════════════════════════════
#  استثناءُ التأخير الصباحيّ أو الخروج المبكر — نموذج 03 (م-29 وم-31)
# ══════════════════════════════════════════════════════════════════════


class ExceptionService:
    """نموذج 03 «نموذج طلب» (م-29): خطابٌ حرٌّ موجَّهٌ إلى مدير المدرسة، يقرّره هو أو من
    ينوب عنه (م-30 وم-24) في مرحلةٍ واحدة.

    ونطاقُ هذه الموجة (م-31) طلبُ «استثناء التأخير الصباحيّ أو الخروج المبكر» وحدَه:
    النوع، ومن تاريخ إلى تاريخ، وساعةُ الحدّ، والمرفقُ الإلزاميّ — «يجب ارفاق مع طلب
    استثناء الخروج المبكر أو التأخير الصباحي ما يثبت حاجة الموظف لذلك». ولا يُشترط
    التكرار. والطلباتُ الحرّةُ الأخرى في النموذج فجوةٌ معروفة. وليس إذناً من نموذج 02:
    فلا يدخل سقفَ العشر ساعات (م-33) ولا حدَّ الثلاث ساعات ولا «مرّةً في اليوم».
    """

    #: المرفقُ صورةٌ أو PDF — وقد يكون تقريراً طبيّاً، فلا يُقبل ما يُنفَّذ في المتصفّح.
    EVIDENCE_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg")
    EVIDENCE_MAX_BYTES = 5 * 1024 * 1024

    @staticmethod
    def _check_evidence(evidence_file: Any) -> None:
        if not evidence_file:
            raise PolicyError(
                "«يجب ارفاق مع طلب استثناء الخروج المبكر أو التأخير الصباحي ما يثبت حاجة "
                "الموظف لذلك» (نموذج 03، م-31) — أرفق الملفّ."
            )
        name = str(getattr(evidence_file, "name", "")).lower()
        if not name.endswith(ExceptionService.EVIDENCE_EXTENSIONS):
            raise PolicyError("المرفقُ ملفُّ PDF أو صورة (PNG/JPG).")
        if (getattr(evidence_file, "size", 0) or 0) > ExceptionService.EVIDENCE_MAX_BYTES:
            raise PolicyError("المرفقُ أكبرُ من 5 ميغابايت.")

    @staticmethod
    @transaction.atomic
    def submit(
        *,
        school: School,
        staff: CustomUser,
        exception_type: str,
        start_date: date,
        end_date: date,
        boundary: time,
        content: str,
        evidence_file: Any,
        evidence: str = "",
        request: HttpRequest | None = None,
    ) -> AttendanceException:
        role = _role_of(staff)
        if role == PRINCIPAL:
            raise PolicyError("نموذج 03 موجَّهٌ إلى مدير المدرسة نفسِه — فلا يقدّمه (م-34).")
        if role in NON_STAFF_ROLES:
            raise PolicyError("نموذج 03 للموظّفين.")
        if exception_type not in {key for key, _label in EXCEPTION_TYPES}:
            raise PolicyError("الاستثناءُ للتأخير الصباحيّ أو الخروج المبكر (نموذج 03، م-31).")
        if not WORK_START < boundary < WORK_END:
            raise PolicyError("ساعةُ الاستثناء داخلَ الدوام الرسميّ 7:00–14:00 (البند 1.1).")
        if end_date < start_date:
            raise PolicyError("«إلى تاريخ» يجب ألّا تسبق «من تاريخ».")
        if not content.strip():
            raise PolicyError("محتوى الطلب مطلوب («استخدام الموظف»، نموذج 03).")
        ExceptionService._check_evidence(evidence_file)
        exception = AttendanceException.objects.create(
            school=school,
            staff=staff,
            exception_type=exception_type,
            start_date=start_date,
            end_date=end_date,
            boundary_time=boundary,
            content=content.strip()[:1000],
            evidence=evidence.strip()[:300],
            evidence_file=evidence_file,
            created_by=staff,
            updated_by=staff,
        )
        _audit(staff, "create", exception, {"type": exception_type, "evidence": True}, request)
        return exception

    @staticmethod
    def _deciders(school: School, applicant: Any) -> set[Any]:
        """م-30 وم-43: المديرُ، ومن كلّفه بأعباء وظيفته."""
        return PermitService._principal_side(_StageDay(school, _pkg._now()), applicant)

    @staticmethod
    @transaction.atomic
    def decide(
        exception: AttendanceException,
        *,
        actor: CustomUser,
        approve: bool,
        feedback: str = "",
        request: HttpRequest | None = None,
    ) -> AttendanceException:
        """«استخدام مدير المدرسة» (م-30): المديرُ أو من ينوب عنه، والتغذيةُ الراجعة لازمة.

        وحالةُ «معتمد / مرفوض» المرافقةُ للتغذية اختيارٌ هندسيٌّ مؤقّت. والقرارُ بالإنابة
        يُوسم (``decided_on_behalf``) مع اسم النائب في ``reviewed_by`` (م-25).
        """
        from .daily import StaffAttendanceService

        # قفلُ صفّ الموظّف (قفلُ ``reconcile`` و``PermitService.act`` نفسُه) ثمّ صفّ الطلب:
        # فالمديرُ ونائبُه في غيابه يريان الطلبَ معاً، ولا يكتب قرارٌ فوق قرار.
        CustomUser.objects.select_for_update().filter(pk=exception.staff_id).first()
        AttendanceException.objects.select_for_update().filter(pk=exception.pk).first()
        exception.refresh_from_db()
        if exception.status != "pending":
            raise PolicyError(f"الطلبُ «{exception.get_status_display()}» — لا يُراجَع ثانيةً.")
        if actor.pk == exception.staff_id:
            raise PolicyError("لا يعمل أحدٌ في طلبه هو.")
        now = _pkg._now()
        stage_day = _StageDay(exception.school, now)
        if actor.pk not in ExceptionService._deciders(exception.school, exception.staff_id):
            raise PolicyError(
                "نموذج 03 يقرّره مديرُ المدرسة («استخدام مدير المدرسة»)، أو نائبُ الشؤون "
                "الإدارية في غيابه (م-30 وم-24)."
            )
        if not feedback.strip():
            raise PolicyError("التغذيةُ الراجعة مطلوبةٌ مع القرار (نموذج 03، م-30).")
        on_behalf = _role_of(actor) != PRINCIPAL
        decided = {
            "status": "approved" if approve else "rejected",
            "feedback": feedback.strip()[:500],
            "reviewed_by": actor,
            "reviewed_at": now,
            "updated_by": actor,
            "decided_on_behalf": on_behalf,
            "updated_at": timezone.now(),
        }
        # الكتابةُ مشروطةٌ بأنّه ما زال معلَّقاً — حارسٌ ثانٍ وراء القفل.
        if not AttendanceException.objects.filter(pk=exception.pk, status="pending").update(
            **decided
        ):
            raise PolicyError("قُرّر هذا الطلبُ للتوّ من جهةٍ أخرى — أعد تحميل الطابور.")
        for key, value in decided.items():
            setattr(exception, key, value)
        changes: dict[str, Any] = {"status": exception.status}
        if on_behalf:
            changes["on_behalf_of"] = PRINCIPAL
            changes.update(stage_day.assignment_basis(actor))
        _audit(actor, "update", exception, changes, request)
        if approve:
            # م-32: عند الاعتماد تُعاد مطابقةُ أيّامه. وم-35: التغطيةُ بعد المهلة لا تُمنع —
            # تُعاد أيّامُ المدّة كلُّها وتُوسم في التقرير.
            last = min(exception.end_date, now.date())
            days = StaffAttendance.objects.filter(
                school=exception.school,
                staff_id=exception.staff_id,
                date__range=(exception.start_date, last),
            ).values_list("date", flat=True)
            for day in days:
                StaffAttendanceService.reconcile(
                    exception.school,
                    exception.staff,
                    day,
                    actor=actor,
                    request=request,
                    cause="exception_approved",
                )
        return exception

    @staticmethod
    def own(school: School, staff: CustomUser) -> QuerySet[AttendanceException]:
        return AttendanceException.objects.filter(school=school, staff=staff).order_by(
            "-start_date", "-created_at"
        )[:20]

    @staticmethod
    def awaiting(school: School, user: CustomUser) -> list[AttendanceException]:
        """طلباتُ نموذج 03 المعلّقة لمن يقرّرها الآن — المديرُ أو نائبُه في غيابه (م-30)."""
        deciders = _StageDay(school, _pkg._now())
        pending = (
            AttendanceException.objects.filter(school=school, status="pending")
            .exclude(staff=user)
            .select_related("staff")
            .order_by("start_date", "created_at")
        )
        return [
            e for e in pending if user.pk in PermitService._principal_side(deciders, e.staff_id)
        ]

    @staticmethod
    def pending_one(school: School, pk: Any) -> AttendanceException:
        return AttendanceException.objects.select_related("staff", "school").get(
            school=school, pk=pk
        )

    @staticmethod
    def approved_on(school: School, staff: CustomUser, day: date) -> list[AttendanceException]:
        return list(
            AttendanceException.objects.filter(
                school=school,
                staff=staff,
                status="approved",
                start_date__lte=day,
                end_date__gte=day,
            )
        )
