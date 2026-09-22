"""رصدُ الحضور اليوميّ وتقريرُ الشهر.

من تفكيك ``staff_affairs/attendance.py`` (الحزمةُ تُصدّر الأسماءَ نفسَها في ``__init__``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import HttpRequest
from django.utils import timezone

import staff_affairs.attendance as _pkg
from core.models.access import Membership
from core.models.school import School
from core.models.user import CustomUser
from staff_affairs.models import (
    ABSENCE_TYPES,
    AttendanceException,
    PermitRequest,
    StaffAttendance,
)

from .context import (
    LINE_MANAGER,
    NON_STAFF_ROLES,
    PRINCIPAL,
    PRINCIPAL_DELEGATE,
    RECORDERS,
    REPORT_WHOLE_SCHOOL,
    PolicyError,
    _audit,
    _audited,
    _minute,
    _role_of,
    _StageDay,
    staff_members,
)
from .exceptions import (
    ExceptionService,
)
from .exemptions import exempt_ids, recording_staff
from .permits import (
    PermitService,
)
from .rules import (
    ABSENCE_TYPE_KEYS,
    ABSENT_AFTER,
    ARRIVAL_STATUSES,
    MONTHLY_PERMIT_CAP,
    SCHOOL_WEEKDAYS,
    STATUS_LABELS,
    STATUSES,
    WORK_END,
    WORK_START,
    classify_arrival,
    coverage_deadline,
    early_leave_minutes,
    month_bounds,
)

# ══════════════════════════════════════════════════════════════════════
#  الحضور — م-1 … م-7
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class _DayCover:
    """ما يغطّي يومَ موظّفٍ معتمَداً: أذوناتُ نموذج 02 واستثناءاتُ نموذج 03."""

    permits: list[PermitRequest]
    exceptions: list[AttendanceException]

    def arrival_windows(self) -> list[tuple[time, time]]:
        """م-5 وم-32: كلُّ نافذةٍ معتمدةٍ في اليوم تغطّي لحظةَ الحضور إن وقع فيها.

        الإذنُ بنوعيه الآخرَين كالتأخير (م-5 «ولا تفرّق» بينها)، والاستثناءُ نافذةٌ من
        07:00 إلى ساعة حدّه (تأخيرٌ) أو منها إلى 14:00 (خروجٌ مبكر).
        """
        windows = [(p.start_time, p.end_time) for p in self.permits]
        windows += [
            (WORK_START, e.boundary_time)
            if e.exception_type == "late_arrival"
            else (e.boundary_time, WORK_END)
            for e in self.exceptions
        ]
        return windows

    def leave_windows(self) -> list[tuple[time, time]]:
        windows = [
            (p.start_time, p.end_time) for p in self.permits if p.permit_type != "late_arrival"
        ]
        windows += [
            (e.boundary_time, WORK_END)
            for e in self.exceptions
            if e.exception_type == "early_departure"
        ]
        return windows


class StaffAttendanceService:
    @staticmethod
    def _cover(school: School, staff: CustomUser, day: date) -> _DayCover:
        permits = list(
            PermitRequest.objects.filter(school=school, staff=staff, date=day, status="approved")
        )
        return _DayCover(permits, ExceptionService.approved_on(school, staff, day))

    @staticmethod
    def _derive(
        cover: _DayCover,
        check_in: time | None,
        check_out: time | None,
        excused: bool,
    ) -> dict[str, Any]:
        """ما يُحسب من الأوقات وما يغطّي اليوم: التصنيفُ والدقائق.

        ويومُ الغياب لا دقائقَ انصرافٍ مبكرٍ فيه (م-9): اليومُ كلُّه يُعدّ غياباً في
        التقرير، فلا يُعدّ نقصُ آخره مرّةً ثانية.
        """
        windows = cover.arrival_windows()
        derived: dict[str, Any] = {
            "status": None,
            "late_minutes": 0,
            "permit_minutes": sum(p.duration_minutes for p in cover.permits),
            "early_leave_minutes": 0,
            "excuse_used": False,
        }
        if check_in is not None:
            derived["status"], derived["late_minutes"] = classify_arrival(
                check_in, excused=excused, windows=windows
            )
            derived["excuse_used"] = (
                excused and classify_arrival(check_in, windows=windows)[0] == "absent"
            )
        if check_out is not None and derived["status"] != "absent":
            derived["early_leave_minutes"] = early_leave_minutes(check_out, cover.leave_windows())
        return derived

    @staticmethod
    def _covered_at(
        record: StaffAttendance,
        values: dict[str, Any],
        check_in: time | None,
        now: datetime,
    ) -> datetime | None:
        """م-35: متى غُطّي غيابُ هذا اليوم — ووقتُه هو ما يُقاس على المهلة في التقرير.

        «غيابٌ مغطّى» يومٌ كان الحضورُ فيه غياباً بذاته (لم يحضر، أو حضر بعد التاسعة بلا
        تغطية): غُطّي بنوعٍ من سجلّ الغياب (إجازةٌ أو مهمّة)، أو بعذرٍ مقبول أو استثناءٍ
        رفع التصنيف. والوقتُ الأوّلُ يبقى — فلا يُمحى قيدٌ بقيدٍ لاحق.
        """
        bare = classify_arrival(check_in)[0] if check_in is not None else "absent"
        if bare != "absent":
            return None
        covered = values["status"] != "absent" or bool(values["absence_type"])
        if not covered:
            return None
        return record.covered_at or now

    @staticmethod
    def _locked_record(school: School, staff: CustomUser, day: date) -> StaffAttendance | None:
        """سجلُّ اليوم مقفولاً للكتابة — مدخلٌ واحدٌ للقراءة قبل الكتابة في الخدمة كلِّها."""
        return (
            StaffAttendance.objects.select_for_update()
            .filter(school=school, staff=staff, date=day)
            .first()
        )

    @staticmethod
    def _changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        return {
            key: [_audited(key, before[key]), _audited(key, value)]
            for key, value in after.items()
            if before[key] != value
        }

    @staticmethod
    def _excuse_values(
        record: StaffAttendance | None,
        excuse: str,
        actor: CustomUser | None,
        now: datetime | None,
        on_behalf: bool | None = None,
    ) -> dict[str, Any]:
        """م-7: العذرُ ومن قبله ووقتُ القبول — قبولٌ جديدٌ بيد ``actor``، أو يبقى ما كان.

        ``actor`` فارغٌ حين لا قبولَ جديدَ (إعادةُ الحساب، أو إعادةُ الرصد بالعذر نفسِه):
        يبقى القابلُ الأوّل ووقتُه ما بقي العذرُ نفسُه. ولا يُمحى القيدُ إلّا بمحو العذر صراحةً
        في الرصد — لا بتغطيةٍ أسكنته.
        """
        if not excuse:
            return {
                "accepted_excuse": "",
                "excuse_accepted_by_id": None,
                "excuse_accepted_at": None,
                "excuse_on_behalf": False,
            }
        if actor is None:
            if record is None:
                raise PolicyError("عذرٌ بلا من يقبله (م-7).")
            return {
                "accepted_excuse": excuse,
                "excuse_accepted_by_id": record.excuse_accepted_by_id,
                "excuse_accepted_at": record.excuse_accepted_at,
                "excuse_on_behalf": record.excuse_on_behalf,
            }
        return {
            "accepted_excuse": excuse,
            "excuse_accepted_by_id": actor.pk,
            "excuse_accepted_at": now,
            "excuse_on_behalf": _role_of(actor) != PRINCIPAL if on_behalf is None else on_behalf,
        }

    @staticmethod
    @transaction.atomic
    def reconcile(
        school: School,
        staff: CustomUser,
        day: date,
        *,
        actor: CustomUser,
        request: HttpRequest | None = None,
        cause: str = "permit_approved",
    ) -> StaffAttendance | None:
        """يُعيد حسابَ سجلّ اليوم من أوقاته المرصودة وما يغطّيه معتمَداً الآن.

        يُستدعى باعتماد إذنٍ أو استثناء: فمن رُصد متأخّراً 8:15 ثمّ اعتُمد له تأخيرٌ إلى
        8:30 صار مستأذناً بلا دقائق تأخّر — لا متأخّراً ومستأذناً معاً. ومن لم يُكتب له
        وقتُ حضور (غائبٌ لم يحضر) تبقى حالتُه، وتتبدّل دقائقُ إذنه وحدَها.
        """
        record = StaffAttendanceService._locked_record(school, staff, day)
        if record is None:
            return None
        cover = StaffAttendanceService._cover(school, staff, day)
        derived = StaffAttendanceService._derive(
            cover, record.check_in, record.check_out, bool(record.accepted_excuse)
        )
        status = derived["status"] or record.status
        values = {
            "status": status,
            "late_minutes": derived["late_minutes"],
            "permit_minutes": derived["permit_minutes"],
            "early_leave_minutes": derived["early_leave_minutes"] if status != "absent" else 0,
            "absence_type": record.absence_type if status == "absent" else "",
            # م-7: العذرُ وقابلُه ووقتُ قبوله قيدٌ لا تمحوه إعادةُ الحساب — تغطيةٌ اعتُمدت بعده
            # تُسكنه (لا يُحتسب ما دامت تكفي) ولا تُسقطه، فإن زالت عاد يعمل بقبوله الأوّل.
            **StaffAttendanceService._excuse_values(record, record.accepted_excuse, None, None),
        }
        values["covered_at"] = StaffAttendanceService._covered_at(
            record, values, record.check_in, _pkg._now()
        )
        before = {key: getattr(record, key) for key in values}
        changes = StaffAttendanceService._changes(before, values)
        if not changes:
            return record
        for key, value in values.items():
            setattr(record, key, value)
        record.updated_by = actor
        record.save()
        _audit(actor, "update", record, {**changes, "cause": cause}, request)
        return record

    @staticmethod
    def can_record(school: School, user: CustomUser) -> bool:
        """أيرصد هذا المستخدمُ حضورَ الكادر الآن؟

        السكرتيرُ والمديرُ دائماً، ونائبُ الشؤون الإدارية حين يعمل بصفة المدير (م-24:
        إنابتُه «في مهامه» كلِّها، ومنها قبولُ العذر في م-7) — وإلّا فلا.
        """
        if _role_of(user) in RECORDERS:
            return True
        return user.pk in PermitService._principal_side(_StageDay(school, _pkg._now()), None)

    @staticmethod
    def manages(
        school: School, user: CustomUser, staff: CustomUser, day: _StageDay | None = None
    ) -> bool:
        """أهو المسؤولُ المباشر لـ``staff`` — النائبُ المختصّ بنصّ ترويسة بطاقته، أو من كُلّف بأعبائه؟

        قرارُ المالك 2026-09-19: يقبل العذرَ المديرُ، أو النائبُ الإداريّ للكادر الإداريّ، أو
        النائبُ الأكاديميّ للكادر الأكاديميّ — والمسؤولُ المباشرُ هو من تُرفع إليه الطلباتُ في
        اللائحة (م.76 و77). و``LINE_MANAGER`` هو سجلُّ بطاقات الوصف الوظيفيّ (م-21).
        """
        manager = LINE_MANAGER.get(_role_of(staff))
        if manager not in (PRINCIPAL_DELEGATE, "vice_academic") or user.pk == staff.pk:
            return False
        return user.pk in (day or _StageDay(school, _pkg._now())).holders(manager)

    @staticmethod
    def can_open_board(school: School, user: CustomUser) -> bool:
        """أتُفتح له لوحةُ الرصد: من يرصد، أو من هو مسؤولٌ مباشرٌ عن أحد (نائبٌ أو مكلَّفٌ بأعبائه)."""
        if StaffAttendanceService.can_record(school, user):
            return True
        day = _StageDay(school, _pkg._now())
        return user.pk in (day.holders(PRINCIPAL_DELEGATE) | day.holders("vice_academic"))

    @staticmethod
    def can_record_for(school: School, user: CustomUser, staff: CustomUser) -> bool:
        """أيرصد ``user`` حضورَ ``staff``: راصدٌ للكادر، أو مسؤولُه المباشر."""
        return StaffAttendanceService.can_record(school, user) or StaffAttendanceService.manages(
            school, user, staff
        )

    @staticmethod
    def can_decide_excuse(school: School, user: CustomUser) -> bool:
        """أيقبل هذا المستخدمُ العذرَ ويرفعه الآن؟ — المديرُ أو من ينوب عنه، أو مسؤولٌ مباشر (م-7).

        ولهم وحدَهم يُعرض حقلُ العذر ونصُّه في لوحة الرصد — والمسؤولُ المباشرُ لا يرى إلّا
        سطورَ من تحته؛ والخدمةُ تفحص ذلك ثانيةً لكلّ موظّف (``mark``).
        """
        day = _StageDay(school, _pkg._now())
        return user.pk in PermitService._principal_side(day, None) or user.pk in (
            day.holders(PRINCIPAL_DELEGATE) | day.holders("vice_academic")
        )

    @staticmethod
    def _check_input(
        school: School,
        staff: CustomUser,
        day: date,
        status: str,
        actor: CustomUser,
        check_in: time | None,
        check_out: time | None,
        absence_type: str,
        now: datetime,
    ) -> str:
        """فحوصُ مدخلات الرصد قبل القفل — الحالةُ واليومُ والراصدُ والأوقاتُ ونوعُ الغياب.

        وتُرجع نوعَ الغياب مطبَّعاً (الفارغُ غيابٌ لم يُغطَّ بعد، م-35).
        """
        if status not in STATUSES:
            raise PolicyError("حالةٌ غيرُ معروفة.")
        if day > now.date():
            raise PolicyError("لا رصدَ ليومٍ لم يأتِ بعد.")
        if actor.pk == staff.pk:
            raise PolicyError("لا يرصد أحدٌ حضورَ نفسه — السجلُّ سندُ الخصم (البند 5).")
        if not StaffAttendanceService.can_record_for(school, actor, staff):
            raise PolicyError(
                "رصدُ الحضور للسكرتارية والمدير ومن ينوب عنه بتكليفه (م-43)، وللمسؤول المباشر "
                "لمن تحته."
            )
        if not staff_members(school).filter(pk=staff.pk).exists():
            raise PolicyError("ليس من كادر هذه المدرسة.")
        if staff.pk in exempt_ids(school, day):
            raise PolicyError("الموظّفُ معفًى من الرصد اليوميّ في هذا اليوم.")
        absence_type = absence_type or ""
        if absence_type and absence_type not in ABSENCE_TYPE_KEYS:
            raise PolicyError("نوعُ غيابٍ غيرُ معروف (سجلّ الغياب).")
        if absence_type and status != "absent":
            raise PolicyError("نوعُ الغياب لا يُكتب إلّا لغائب (سجلّ الغياب).")
        if status in ARRIVAL_STATUSES and check_in is None:
            raise PolicyError(
                f"«{STATUS_LABELS[status]}» يُرصد بوقت الحضور — به تُحسب دقائقُ التأخّر "
                "(البندان 2.1 و5.2)."
            )
        if check_out is not None and (check_in is None or check_out <= check_in):
            raise PolicyError("وقتُ الانصراف يُكتب بعد وقت الحضور.")
        if day == now.date():
            # ما لم يقع لا يُرصد: الغيابُ بحضورٍ بعد 9:00 (م-4) لا يُعرف قبل أن يمضي وقتُه،
            # فلا يتجاوز حارسَ التاسعة ولا يُقيم إنابةً مبكرةً (م-25)؛ والانصرافُ قبل وقوعه
            # يمحو دقائقَ الخروج المبكر (م-8). والمقارنةُ بالدقيقة (م-2).
            moment = _minute(now.time())
            for label, value in (("الحضور", check_in), ("الانصراف", check_out)):
                if value is not None and _minute(value) > moment:
                    raise PolicyError(
                        f"وقتُ {label} {value:%H:%M} لم يأتِ بعد — لا يُرصد اليومَ إلّا ما وقع "
                        "(م-4 وم-8)."
                    )
        if (
            status == "absent"
            and check_in is None
            and not absence_type
            and day == now.date()
            and _minute(now.time()) <= ABSENT_AFTER
        ):
            raise PolicyError(
                "لا يُرصد غيابُ اليوم قبل أن تمضي التاسعة — «يعتبر الموظف غائبا إذا حضر بعد "
                "الساعة التاسعة» (البند 2.4، م-4)؛ وقبلها يُرصد الغيابُ بنوعه من سجلّ الغياب."
            )
        return absence_type

    @staticmethod
    @transaction.atomic
    def mark(
        *,
        school: School,
        staff: CustomUser,
        day: date,
        status: str,
        actor: CustomUser,
        check_in: time | None = None,
        check_out: time | None = None,
        absence_type: str = "",
        accepted_excuse: str | None = "",
        request: HttpRequest | None = None,
    ) -> StaffAttendance:
        """رصدُ حالة موظّفٍ في يوم — بنقرة، ووقتُ الحضور شاهدُها.

        * لا يرصد أحدٌ نفسَه: السجلُّ سندُ الخصم (البند 5).
        * الحاضرُ والمتأخّرُ والمستأذنُ بوقت حضورهم، فبه تُحسب دقائقُ التأخّر (م-3 وم-6)،
          ونقرةٌ تخالف تصنيفَه تُرفض باسم البند. والغائبُ بلا وقتٍ جائز.
        * ``accepted_excuse`` (م-7) لا يقبله إلّا المديرُ أو من ينوب عنه، ويُكتب لمن حضر
          بعد 9:00 بلا تغطيةٍ سارية، فيُعدّ متأخّراً بدقائقه لا غائباً. و``None`` «لم يُعرض
          الحقل»: يبقى العذرُ المحفوظ كما هو — فالراصدُ لا يرى نصَّه (قد يحمل بيانةً صحّيّة،
          PDPPL م.16) ويكتب الوقتَ في سطرٍ قُبل عذرُه دون أن يُعدّ ذلك رفعاً له.
        * ``absence_type`` نوعُ يوم الغياب من سجلّ الغياب المدرسيّ (إجازةٌ أو مهمّة)،
          والفارغُ غيابٌ لم يُغطَّ بعد (م-35).
        * ``check_out`` وقتُ الانصراف، وما بينه وبين 14:00 بلا إذنٍ يُعدّ (م-1) — إلّا في
          يوم الغياب (م-9).

        والكتابةُ تحت قفل صفّ الموظّف — القفلِ نفسِه الذي يأخذه ``PermitService.act`` —
        فلا يكتب رصدٌ فوق ما أعادت ``reconcile`` حسابَه، ولا يتسابق راصدان.
        """
        now = _pkg._now()
        absence_type = StaffAttendanceService._check_input(
            school, staff, day, status, actor, check_in, check_out, absence_type, now
        )
        CustomUser.objects.select_for_update().filter(pk=staff.pk).first()
        record = StaffAttendanceService._locked_record(school, staff, day)
        if accepted_excuse is None:
            excuse = record.accepted_excuse if record is not None else ""
        else:
            excuse = accepted_excuse.strip()[:300]
        derived = StaffAttendanceService._derive(
            StaffAttendanceService._cover(school, staff, day), check_in, check_out, bool(excuse)
        )
        if check_in is not None and derived["status"] != status:
            raise PolicyError(
                f"الحضورُ {check_in:%H:%M} يعني «{STATUS_LABELS[derived['status']]}» "
                "(البندان 2.1 و2.4) — لا يُرصد غيرُه."
            )
        # القبولُ لعذرٍ عند وقتٍ بعينه: عذرٌ جديد، أو العذرُ نفسُه عند وقت حضورٍ آخر — فلا
        # ينقل الراصدُ قبولَ المدير إلى وقتٍ لم يُعرض عليه (م-7).
        accepting = bool(excuse) and (
            record is None
            or record.accepted_excuse != excuse
            or record.check_in is None
            or check_in is None
            or _minute(record.check_in) != _minute(check_in)
        )
        # والعذرُ المقبولُ من قبلُ عند الوقت نفسِه يبقى وإن أسكنته تغطيةٌ اعتُمدت بعده (م-7:
        # قيدٌ لا يُفقد) — وإنّما يُردّ قبولٌ جديدٌ لا حاجةَ إليه.
        if accepting and not derived["excuse_used"]:
            raise PolicyError("العذرُ المقبول يُكتب لمن حضر بعد 9:00 بلا إذنٍ يغطّيه وحدَه (البند 2.4).")
        # ورفعُ عذرٍ مقبولٍ نقضٌ لقرار القبول — فهو لجهة القبول نفسِها (م-7)، لا لمن يرصد
        # الوقت: وإلّا صار اليومُ بمحوه غياباً يُخصم (البند 5.3) بيد من لا يملك القرار.
        withdrawing = record is not None and bool(record.accepted_excuse) and not excuse
        deciding = accepting or withdrawing
        stage_day = _StageDay(school, now)
        basis = stage_day.assignment_basis(actor) if deciding else {}
        if (
            deciding
            and actor.pk not in PermitService._principal_side(stage_day, staff.pk)
            and not StaffAttendanceService.manages(school, actor, staff, stage_day)
        ):
            raise PolicyError(
                "العذرُ المقبول (البند 2.4) يقبله ويرفعه مديرُ المدرسة أو من ينوب عنه (م-7 "
                "وم-43)، أو مسؤولُه المباشر (النائبُ المختصّ) — ومن رصد الحضورَ يكتب الوقتَ لا "
                "العذر؛ وتغييرُ وقت حضورٍ قُبل عذرُه يحتاج منهم قبولاً جديداً أو رفعاً للعذر."
            )
        values: dict[str, Any] = {
            "status": status,
            "check_in": check_in,
            "check_out": check_out,
            "late_minutes": derived["late_minutes"],
            "permit_minutes": derived["permit_minutes"],
            "early_leave_minutes": derived["early_leave_minutes"],
            "absence_type": absence_type,
            **StaffAttendanceService._excuse_values(
                record,
                excuse,
                actor if accepting else None,
                now,
                # بالإنابة: يقبل بصفة المدير (تكليفاً). أمّا المسؤولُ المباشر فيقبل بصفته هو.
                on_behalf=(
                    _role_of(actor) != PRINCIPAL
                    and actor.pk in PermitService._principal_side(stage_day, staff.pk)
                ),
            ),
        }
        return StaffAttendanceService._write_mark(
            school,
            staff,
            day,
            actor,
            record,
            values,
            check_in,
            now,
            status,
            basis,
            withdrawing,
            request,
        )

    @staticmethod
    def _write_mark(
        school: School,
        staff: CustomUser,
        day: date,
        actor: CustomUser,
        record: StaffAttendance | None,
        values: dict[str, Any],
        check_in: time | None,
        now: datetime,
        status: str,
        basis: dict[str, Any],
        withdrawing: bool,
        request: HttpRequest | None,
    ) -> StaffAttendance:
        """يكتب سجلَّ الرصد: إنشاءً أو تحديثاً — ولا يكتب ما لم يتغيّر — ويُدقَّق بالتغيير."""
        if record is None:
            values["covered_at"] = StaffAttendanceService._covered_at(
                StaffAttendance(), values, check_in, now
            )
            try:
                with transaction.atomic():
                    record = StaffAttendance.objects.create(
                        school=school,
                        staff=staff,
                        date=day,
                        created_by=actor,
                        updated_by=actor,
                        **values,
                    )
            except IntegrityError as exc:  # راصدٌ آخرُ سبقنا في اللحظة نفسِها
                raise PolicyError("رُصد هذا اليومُ للتوّ من جهةٍ أخرى — أعد تحميل اللوحة.") from exc
            created = {key: _audited(key, value) for key, value in values.items() if value}
            created.update(basis)
            _audit(actor, "create", record, {"status": status, **created}, request)
            return record
        values["covered_at"] = StaffAttendanceService._covered_at(record, values, check_in, now)
        before = {key: getattr(record, key) for key in values}
        changes = StaffAttendanceService._changes(before, values)
        if not changes:
            return record
        for key, value in values.items():
            setattr(record, key, value)
        record.updated_by = actor
        record.save()
        if withdrawing:
            changes["excuse_withdrawn"] = True
        changes.update(basis)
        _audit(actor, "update", record, changes, request)
        return record

    @staticmethod
    def daily_board(school: School, day: date, viewer: CustomUser | None = None) -> dict[str, Any]:
        """لوحةُ اليوم: كلُّ موظّفٍ بسجلّه إن رُصد، وعددُ كلّ حالة.

        والمسؤولُ المباشرُ الذي لا يرصد للكادر كلِّه (نائبٌ أو مكلَّفٌ) لا يرى إلّا من تحته.
        """
        staff = list(recording_staff(school, day).only("id", "full_name", "employee_number"))
        if viewer is not None and not StaffAttendanceService.can_record(school, viewer):
            stage = _StageDay(school, _pkg._now())
            roles = {
                r for r in (PRINCIPAL_DELEGATE, "vice_academic") if viewer.pk in stage.holders(r)
            }
            by_user = dict(
                Membership.objects.current()
                .filter(school=school, is_active=True, user_id__in=[s.pk for s in staff])
                .values_list("user_id", "role__name")
            )
            staff = [s for s in staff if LINE_MANAGER.get(by_user.get(s.pk, "")) in roles]
        records = {r.staff_id: r for r in StaffAttendance.objects.filter(school=school, date=day)}
        rows = [{"staff": s, "record": records.get(s.pk)} for s in staff]
        counts = dict.fromkeys(STATUSES, 0)
        for s in staff:
            if s.pk in records:
                counts[records[s.pk].status] += 1
        counts["unmarked"] = len(staff) - sum(counts.values())
        return {"rows": rows, "counts": counts}

    @staticmethod
    def board_row(school: School, staff_id: Any, day: date) -> dict[str, Any]:
        staff = staff_members(school).get(pk=staff_id)
        record = StaffAttendance.objects.filter(school=school, staff=staff, date=day).first()
        return {"staff": staff, "record": record}

    @staticmethod
    def _report_people(
        school: School, first: date, last: date, viewer: CustomUser | None
    ) -> list[CustomUser]:
        """من يدخل تقريرَ الشهر: الكادرُ النشط، ومن له سجلٌّ أو إذنٌ معتمدٌ فيه وإن غادر.

        والنائبان يريان من يتبعهما وحدَهم — والتبعيّةُ من جدول م-21 (``LINE_MANAGER``).
        """
        marked = StaffAttendance.objects.filter(school=school, date__range=(first, last)).values(
            "staff_id"
        )
        permitted = PermitRequest.objects.filter(
            school=school, status="approved", date__range=(first, last)
        ).values("staff_id")
        # المعفى الشهرَ كلَّه لا يدخل التقرير إلّا إن كان له سجلٌّ أو إذنٌ فيه.
        exempt = exempt_ids(school, first, last)
        roster = staff_members(school).exclude(pk__in=exempt).values("pk")
        people = CustomUser.objects.filter(
            Q(pk__in=roster) | Q(pk__in=marked) | Q(pk__in=permitted)
        ).order_by("full_name")
        viewer_role = _role_of(viewer) if viewer is not None else PRINCIPAL
        if viewer_role in REPORT_WHOLE_SCHOOL or viewer_role not in LINE_MANAGER.values():
            return list(people.only("id", "full_name", "employee_number"))
        roles: dict[Any, set[str]] = {}
        for user_id, role in (
            Membership.objects.filter(school=school, user__in=people)
            .exclude(role__name__in=NON_STAFF_ROLES)
            .values_list("user_id", "role__name")
        ):
            roles.setdefault(user_id, set()).add(role)
        return [
            person
            for person in people.only("id", "full_name", "employee_number")
            if any(
                LINE_MANAGER.get(role, PRINCIPAL) == viewer_role
                for role in roles.get(person.pk, ())
            )
        ]

    @staticmethod
    def monthly_report(
        school: School, year: int, month: int, viewer: CustomUser | None = None
    ) -> dict[str, Any]:
        """م-36: تقريرُ الشهر لكلّ موظّفٍ في نطاق ``viewer`` (بلا ``viewer``: المدرسةُ كلُّها).

        أيّامُ كلّ حالة ودقائقُ التأخّر (م-36) والانصراف المبكر من سجلّ اليوم، وأيّامُ
        الغياب بأنواعها وغيرُ المغطّى منها، وما غُطّي بعد مهلة يوم 14 موسوماً (م-35)،
        والإذنُ المعتمد من الأذونات نفسِها (فإذنٌ في يومٍ لم يُرصد يُحسب، م-10)،
        والمتبقّي من السقف الشهريّ (م-15)، وأيّامُ استثناء نموذج 03 المعتمد في الشهر
        مستقلّةً عن الأذونات ولا تمسّ السقف (م-33).
        """
        first, last = month_bounds(date(year, month, 1))
        deadline = coverage_deadline(first)
        after_deadline = timezone.make_aware(datetime.combine(deadline + timedelta(days=1), time()))
        attendance = {
            row["staff_id"]: row
            for row in StaffAttendance.objects.filter(school=school, date__range=(first, last))
            .values("staff_id")
            .annotate(
                **{key: Count("id", filter=Q(status=key)) for key in STATUSES},
                **{
                    f"absence_{key}": Count("id", filter=Q(status="absent", absence_type=key))
                    for key in ABSENCE_TYPE_KEYS
                },
                absent_uncovered=Count("id", filter=Q(status="absent", absence_type="")),
                covered_late=Count("id", filter=Q(covered_at__gte=after_deadline)),
                late_total=Sum("late_minutes"),
                # يومُ الغياب يُعدّ غياباً وحدَه (``_derive``) — والشرطُ هنا حارسٌ ثانٍ.
                early_total=Sum("early_leave_minutes", filter=~Q(status="absent")),
            )
        }
        permits = dict(
            PermitRequest.objects.filter(
                school=school, status="approved", date__range=(first, last)
            )
            .values("staff_id")
            .annotate(total=Sum("duration_minutes"))
            .values_list("staff_id", "total")
        )
        exception_days: dict[Any, set[date]] = {}
        for staff_id, start, end in AttendanceException.objects.filter(
            school=school, status="approved", start_date__lte=last, end_date__gte=first
        ).values_list("staff_id", "start_date", "end_date"):
            day, stop = max(start, first), min(end, last)
            while day <= stop:
                if day.weekday() in SCHOOL_WEEKDAYS:
                    exception_days.setdefault(staff_id, set()).add(day)
                day += timedelta(days=1)
        rows: list[dict[str, Any]] = []
        for person in StaffAttendanceService._report_people(school, first, last, viewer):
            counted = attendance.get(person.pk, {})
            used = permits.get(person.pk, 0)
            rows.append(
                {
                    "employee_number": person.employee_number,
                    "full_name": person.full_name,
                    **{key: counted.get(key, 0) for key in STATUSES},
                    "absent_uncovered": counted.get("absent_uncovered", 0),
                    "covered_late": counted.get("covered_late", 0),
                    **{
                        f"absence_{key}": counted.get(f"absence_{key}", 0)
                        for key in ABSENCE_TYPE_KEYS
                    },
                    "late_minutes": counted.get("late_total") or 0,
                    "early_leave_minutes": counted.get("early_total") or 0,
                    "permit_minutes": used,
                    "permit_remaining": max(0, MONTHLY_PERMIT_CAP - used),
                    "exception_days": len(exception_days.get(person.pk, ())),
                }
            )
        keys = (
            *STATUSES,
            "absent_uncovered",
            "covered_late",
            "exception_days",
            "late_minutes",
            "early_leave_minutes",
            "permit_minutes",
        )
        totals = {key: sum(r[key] for r in rows) for key in keys}
        return {
            "first": first,
            "last": last,
            "deadline": deadline,
            "rows": rows,
            "totals": totals,
        }

    @staticmethod
    def monthly_workbook(report: dict[str, Any]) -> Any:
        """ورقةُ Excel للتقرير — بالرقم الوظيفيّ، ولا رقمَ شخصيّاً فيها أصلاً."""
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = f"{report['first']:%Y-%m}"
        ws.sheet_view.rightToLeft = True
        ws.append(
            [
                "الرقم الوظيفي",
                "الاسم",
                *(STATUS_LABELS[key] for key in STATUSES),
                "غياب غير مغطّى",
                f"غياب غُطّي بعد المهلة ({report['deadline']:%d/%m})",
                *(f"غياب: {label}" for _key, label in ABSENCE_TYPES),
                "دقائق التأخّر",
                "دقائق الانصراف المبكر بلا إذن",
                "دقائق الإذن المعتمد",
                "المتبقّي من سقف الأذونات",
                "أيام الاستثناء (نموذج 03)",
            ]
        )
        for r in report["rows"]:
            ws.append(
                [
                    r["employee_number"],
                    r["full_name"],
                    *(r[key] for key in STATUSES),
                    r["absent_uncovered"],
                    r["covered_late"],
                    *(r[f"absence_{key}"] for key in ABSENCE_TYPE_KEYS),
                    r["late_minutes"],
                    r["early_leave_minutes"],
                    r["permit_minutes"],
                    r["permit_remaining"],
                    r["exception_days"],
                ]
            )
        return wb
