"""operations/services/compensatory.py — الحصص التعويضيّة.

الحصّةُ الفائتةُ بغياب المعلّم تُعوَّض في حصّة زميلٍ يدرّس الشعبةَ نفسها، بموافقته
(قرارُ المالك 2026-09-24): الجدولُ المعتمد ممتلئ، فلا حصّةَ فارغةً لشعبةٍ في الأسبوع
كلّه (25 شعبة، 863 خانة في قاعدة الجلسة). فالمسار:

1. المعلّمُ يختار الحصّةَ الفائتة والتاريخ، فيرى حصصَ الشعبة يومَها بجرس طابقها —
   ولكلٍّ صاحبُها، وهل يُعوَّض فيها ولماذا (`day_options`).
2. صاحبُ الحصّة يوافق أو يعتذر (`colleague_decide`).
3. المنسّقُ يعتمد (`approve_compensatory`): تصير حصّةُ الزميل ذلك اليومَ لصاحب
   التعويض بمادّته، ويبقى اسمُ الزميل في `original_teacher` كالتبديل والإشغال.

والوقتُ من جرس نطاق الشعبة ليومها. كان أوّلَ إعدادٍ «عاديّ» في المدرسة بلا نطاقٍ ولا
خميس، فيُكتب التعويضُ فوق حصّةٍ قائمةٍ بالساعة، أو يسقط الاعتمادُ بخطأ خادم.
"""

from __future__ import annotations

import logging
from datetime import date, time, timedelta
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from core.academic_calendar import (
    academic_year_for_school,
)
from operations.models import (
    CompensatorySession,
    FreeSlotRegistry,
    ScheduleSlot,
    Session,
    TeacherAbsence,
)
from operations.school_days import school_day

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import ClassGroup, CustomUser, School

#: طلبٌ ما زال يحجز حصّتَه: لا يُطلب تعويضٌ آخرُ فيها.
OPEN_STATUSES = ("colleague", "pending")

#: أبعدُ ما يقع التعويضُ بعد يوم الغياب: أسبوعُه والذي يليه (`week_offset` 0 أو 1).
MAX_GAP_DAYS = 14


class CompensatoryService:
    """خدمة الحصص التعويضية."""

    @staticmethod
    def _bell(school: School, class_group: ClassGroup, day: date) -> dict[int, tuple[time, time]]:
        """جرسُ نطاق الشعبة ليومها — ويُرفض يومٌ لا دوامَ فيه لها.

        فالسادسةُ كانت 11:35 لكلّ شعبةٍ في كلّ يوم (جرسُ الطابق الأرضيّ للأحد)، وسادسةُ
        الثانويّ يومَ الخميس 11:10 وسادسةُ الأرضيّ 11:55. والجرسُ هنا جرسُ ورقة الطباعة
        نفسُه (`period_times`)، فلا يختلف ما يُكتب عمّا يُطبع.
        """
        from operations.services.schedule import ScheduleService

        today = school_day(school, day, class_group.grade)
        if not today.is_open:
            raise ValueError(f"لا دوامَ للشعبة يومَ {day:%Y/%m/%d}: {today.closed_reason}")
        bell: dict[int, tuple[time, time]] = ScheduleService.period_times(
            school,
            class_group.academic_year,
            band=class_group.time_band_id,
            day_type=today.bell_day_type,
        )
        return bell

    @classmethod
    def _open_claims(
        cls, school: School, teacher: CustomUser, class_group: ClassGroup, day: date, exclude: Any
    ) -> tuple[set[int], list[tuple[int, time, time]]]:
        """ما حُجز يومَ `day` بطلباتٍ مفتوحة: حصصُ الشعبة المطلوبة، وطلباتُ المعلّم في شُعبٍ أخرى.

        الثانيةُ بالساعة لا بالرقم: القيدُ في القاعدة بالرقم، والانشغالُ الفعليّ بالوقت.
        وفُصلت لتبقى `day_options` تحت سقف التعقيد (Radon ≤ 30).
        """
        open_here = CompensatorySession.objects.filter(
            school=school, compensatory_date=day, status__in=OPEN_STATUSES
        ).exclude(pk=exclude)
        claimed = set(
            open_here.filter(class_group=class_group).values_list("compensatory_period", flat=True)
        )
        mine_open = [
            (c.compensatory_period, *times)
            for c in open_here.filter(teacher=teacher).select_related("class_group__time_band")
            if (times := cls._bell(school, c.class_group, day).get(c.compensatory_period))
        ]
        return claimed, mine_open

    @classmethod
    def day_options(
        cls,
        school: School,
        teacher: CustomUser,
        class_group: ClassGroup,
        day: date,
        exclude: Any = None,
    ) -> list[dict[str, Any]]:
        """حصصُ الشعبة يومَ `day` بجرس طابقها — ولكلٍّ صاحبُها، وهل يُعوَّض فيها ولماذا.

        يصلح الوقتُ إن فرغ له المعلّمُ بالساعة لا بالرقم — معلّمُ الطابقين ثالثتُه في
        الطابق الأوّل (8:45) تتداخل مع ثانيته في الأرضيّ (8:00–8:50) — وكانت حصّةُ
        الشعبة فيه لزميلٍ واحدٍ لم تُمسّ: لا تبديلَ ولا إشغالَ ولا حضورَ مرصود، ولا طلبَ
        تعويضٍ آخرَ عليها. ويُولَّد اليومُ كاملاً قبل السؤال: يومٌ لم يُولَّد يبدو فارغاً،
        وحصّةٌ مفردةٌ فيه كانت تُبقيه بحصّةٍ واحدةٍ للمدرسة كلّها («اليومُ المبتور»).
        """
        from operations.services.schedule import ScheduleService

        bell = cls._bell(school, class_group, day)
        ScheduleService.ensure_sessions_for_date(school, day)
        sessions = list(
            Session.objects.filter(school=school, date=day)
            .filter(Q(teacher=teacher) | Q(class_group=class_group))
            .select_related("teacher", "subject", "class_group")
        )
        untouched = set(
            ScheduleService._untouched(
                Session.objects.filter(pk__in=[s.pk for s in sessions])
            ).values_list("pk", flat=True)
        )
        claimed, mine_open = cls._open_claims(school, teacher, class_group, day, exclude)
        # غائبٌ ذلك اليوم: لا يُعوِّض فيه — سجلُّ غيابه يُلغي ما اعتُمد له، ولا يُطلب له جديد.
        absent = TeacherAbsence.objects.filter(school=school, teacher=teacher, date=day).exists()
        rows = []
        for period, (start, end) in sorted(bell.items()):
            during = [s for s in sessions if s.start_time < end and s.end_time > start]
            mine = [s for s in during if s.teacher_id == teacher.pk]
            # ما في الشعبة وقتَها أيّاً كان صاحبُه — والمأخوذُ حصّةُ زميلٍ مفردة.
            in_class = [s for s in during if s.class_group_id == class_group.pk]
            theirs = [s for s in in_class if s not in mine]
            lesson = theirs[0] if len(theirs) == 1 else None
            occupant = " / ".join(
                f"{s.subject.name_ar if s.subject else 'حصّة'} — {s.teacher.full_name}"
                for s in in_class
            )
            if absent:
                why = "أنت مسجَّلٌ غائباً في هذا اليوم"
            elif mine:
                busy = mine[0]
                subject = busy.subject.name_ar if busy.subject else "حصّة"
                why = f"المعلّم مشغولٌ: {subject} مع {busy.class_group.short_label}"
            elif any(p == period or (s < end and e > start) for p, s, e in mine_open):
                why = "لك طلبُ تعويضٍ آخرُ في هذا الوقت"
            elif period in claimed:
                why = "طُلبت لتعويضٍ آخر"
            elif len(theirs) > 1:
                why = "حصّتان اختياريّتان للشعبة"
            elif lesson is not None and lesson.start_time != start:
                why = "وقتُ حصّة الشعبة لا يوافق جرسها"
            elif lesson is not None and lesson.pk not in untouched:
                why = "مبدَّلةٌ أو مُشغَلةٌ أو رُصد حضورها"
            else:
                why = ""
            rows.append(
                {
                    "period": period,
                    "start": start,
                    "end": end,
                    "lesson": lesson,
                    "occupant": occupant,
                    "colleague": lesson.teacher if lesson is not None else None,
                    "ok": not why,
                    "why": why,
                }
            )
        return rows

    @classmethod
    def _option(
        cls,
        school: School,
        teacher: CustomUser,
        class_group: ClassGroup,
        day: date,
        period: int,
        exclude: Any = None,
    ) -> dict[str, Any]:
        """خيارُ الحصّة `period` يومَ `day` إن صلح للتعويض — وإلّا `ValueError` بسببه."""
        from operations.services.schedule import ScheduleService

        cls._not_past(day)
        rows = cls.day_options(school, teacher, class_group, day, exclude)
        row = next((r for r in rows if r["period"] == period), None)
        if row is None:
            name = class_group.time_band.name if class_group.time_band else "المدرسة"
            weekday = dict(ScheduleSlot.DAYS)[ScheduleService._PY_TO_QATAR[day.weekday()]]
            raise ValueError(f"لا حصّةَ {period} يومَ {weekday} في جرس «{name}»: حصصُه {len(rows)}")
        if not row["ok"]:
            raise ValueError(
                f"الحصّة {period} ({row['start']:%H:%M}–{row['end']:%H:%M}): {row['why']}"
            )
        return row

    @staticmethod
    def _not_past(day: date) -> None:
        """يومٌ مضى لا يُعوَّض فيه: طلبٌ عالقٌ كان يُعتمد بعد أسبوعين فيُسلَّم حصّةَ ماضٍ بأثرٍ رجعيّ."""
        if day < timezone.localdate():
            raise ValueError(f"مضى تاريخُ التعويض {day:%Y/%m/%d}")

    @staticmethod
    def taken_slot_ids(absence: TeacherAbsence) -> set[Any]:
        """حصصُ الغائب يومَ غيابه التي أخذها زميلٌ تعويضاً: لم تعد حصصَه ذلك اليوم.

        فلا تُعرض عليه للإشغال ولا تُحسب في تغطيته، وإلّا كتب الإشغالُ أو التبديلُ
        فوق حصّة التعويض المعتمَدة (`hand_over_session` تجد الجلسةَ نفسَها بمفتاحها)
        فيخسرها صاحبُها بلا إشعار.
        """
        taken = CompensatorySession.objects.filter(
            school=absence.school,
            colleague=absence.teacher,
            compensatory_date=absence.date,
            status__in=("approved", "completed"),
            session_created__isnull=False,
        ).select_related("session_created")
        keys = {
            (c.class_group_id, c.session_created.start_time) for c in taken if c.session_created
        }
        if not keys:
            return set()
        from operations.services.substitute import SubstituteService

        slots = ScheduleSlot.objects.live(absence.school).filter(
            teacher=absence.teacher, day_of_week=SubstituteService._date_to_day(absence.date)
        )
        return {s.id for s in slots if (s.class_group_id, s.start_time) in keys}

    @staticmethod
    def listing(
        school: School, user: CustomUser, role: str, status: str = ""
    ) -> QuerySet[CompensatorySession]:
        """طلباتُ التعويض التي يراها هذا الدور: الأحدثُ أوّلاً.

        القيادةُ تراها كلَّها، والمنسّقُ طلباتِ قسمه، والمعلّمُ طلباتِه. ولصاحب الحصّة
        (الزميل) نصيبٌ أيّاً كان دورُه: يرى ما طُلب في حصّته فيوافق أو يعتذر من القائمة.
        """
        from core.permissions import get_department_teacher_ids

        comps = CompensatorySession.objects.filter(school=school)
        if role in ("principal", "vice_academic", "vice_admin"):
            pass
        elif role == "coordinator":
            dept_teachers = get_department_teacher_ids(user) or set()
            comps = comps.filter(Q(teacher_id__in=dept_teachers) | Q(colleague=user))
        else:
            comps = comps.filter(Q(teacher=user) | Q(colleague=user))
        if status:
            comps = comps.filter(status=status)
        return comps.select_related(
            "teacher",
            "colleague",
            "original_slot__subject",
            "original_slot__class_group",
            "class_group",
            "subject",
            "session_created",
        ).order_by("-created_at")

    @staticmethod
    def get_available_compensatory_slots(
        teacher: CustomUser,
        school: School,
        target_date: date,
        academic_year: str | None = None,
    ) -> list:
        """
        الأوقات المتاحة للتعويض — حصص حرة للمعلم في اليوم المطلوب.
        يتحقق أيضاً أن الشعبة ليست مشغولة.
        """

        academic_year = academic_year or academic_year_for_school(school)
        mapping = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}
        day = mapping.get(target_date.weekday(), -1)
        if day == -1:
            return []

        # حصص المعلم الحرة في هذا اليوم
        free = FreeSlotRegistry.objects.filter(
            teacher=teacher,
            school=school,
            day_of_week=day,
            academic_year=academic_year,
            is_available=True,
        ).values_list("period_number", flat=True)

        return sorted(free)

    @staticmethod
    @transaction.atomic
    def request_compensatory(
        school: School,
        teacher: CustomUser,
        original_slot: ScheduleSlot,
        absence: TeacherAbsence,
        compensatory_date: date,
        compensatory_period: int,
        notes: str = "",
    ) -> CompensatorySession:
        """طلبُ تعويض: إلى صاحب الحصّة ليوافق، أو إلى المنسّق إن فرغت الشعبةُ في وقتها."""
        if original_slot.teacher_id != teacher.pk or absence.teacher_id != teacher.pk:
            raise ValueError("الحصّةُ الفائتةُ والغيابُ من سجلّك أنت")

        # التعويضُ بعد الغياب وبحدٍّ أقصى أسبوعان: `week_offset` 0 نفسُ الأسبوع و1 التالي.
        # وكان الشرطُ `week_offset > 1` لا يتحقّق أبداً، فيُقبل تعويضٌ قبل الغياب أو بعده بأشهر.
        diff_days = (compensatory_date - absence.date).days
        if not 1 <= diff_days <= MAX_GAP_DAYS:
            raise ValueError(f"التعويضُ بعد الغياب بيومٍ إلى {MAX_GAP_DAYS} يوماً — أسبوعُه والذي يليه")
        week_offset = 1 if diff_days > 7 else 0

        # يُعرف الرفضُ عند الطلب لا عند الاعتماد، والاعتمادُ يسأل ثانيةً — فقد يتغيّر اليوم.
        row = CompensatoryService._option(
            school, teacher, original_slot.class_group, compensatory_date, compensatory_period
        )
        colleague = row["colleague"]
        comp = CompensatorySession.objects.create(
            school=school,
            teacher=teacher,
            original_slot=original_slot,
            absence=absence,
            compensatory_date=compensatory_date,
            compensatory_period=compensatory_period,
            class_group=original_slot.class_group,
            subject=original_slot.subject,
            colleague=colleague,
            week_offset=week_offset,
            status="colleague" if colleague else "pending",
            notes=notes,
        )
        if colleague is not None:
            CompensatoryService._tell(
                comp, {colleague.pk}, f"طلبُ تعويضٍ في حصّتك من {teacher.full_name} — ينتظر موافقتك"
            )
        else:
            CompensatoryService._tell(
                comp,
                CompensatoryService._coordinators(teacher),
                f"طلب تعويض من {teacher.full_name}",
            )

        logger.info(
            "CompensatoryService: created request %s for teacher %s", comp.pk, teacher.full_name
        )
        return comp

    @staticmethod
    @transaction.atomic
    def colleague_decide(
        comp: CompensatorySession, user: CustomUser, accepted: bool, reason: str = ""
    ) -> CompensatorySession:
        """صاحبُ الحصّة يوافق فيذهب الطلبُ إلى المنسّق، أو يعتذر فيُلغى."""
        if comp.status != "colleague" or comp.colleague_id != user.pk:
            raise ValueError("الردُّ لصاحب الحصّة وحده، ما دام الطلبُ ينتظره")
        comp.colleague_responded_at = timezone.now()
        if accepted:
            CompensatoryService._not_past(comp.compensatory_date)
            comp.status = "pending"
            comp.save(update_fields=["status", "colleague_responded_at", "updated_at"])
            CompensatoryService._tell(
                comp,
                CompensatoryService._coordinators(comp.teacher) | {comp.teacher_id},
                f"وافق {user.full_name} على التعويض في حصّته — ينتظر الاعتماد",
            )
        else:
            comp.status = "cancelled"
            comp.notes = f"{comp.notes}\nاعتذر الزميل: {reason or 'بلا سبب مذكور'}".strip()
            comp.save(update_fields=["status", "colleague_responded_at", "notes", "updated_at"])
            CompensatoryService._tell(
                comp, {comp.teacher_id}, f"اعتذر {user.full_name} عن التعويض في حصّته"
            )
        return comp

    @staticmethod
    @transaction.atomic
    def approve_compensatory(
        comp: CompensatorySession,
        approved_by: CustomUser,
        approved: bool = True,
        rejection_reason: str = "",
    ) -> CompensatorySession:
        """المنسق/النائب يعتمد التعويض — فتصير حصّةُ الزميل يومَها لصاحب التعويض.

        والاعتمادُ بعد موافقة الزميل وحدَها، أمّا الرفضُ فمن أيّ حالةٍ مفتوحة: طلبٌ ينتظر
        زميلاً لا يردّ لا مخرجَ له إلّا رفضُ المنسّق. ولا يقرّر من كان طرفاً فيه، فمنسّقٌ هو
        الزميلُ نفسُه كان يوافق ثمّ يعتمد فتصير الخطوتان خطوةً واحدة، ولا من هو خارج قسم صاحبه.
        """
        from core.permissions import get_department_teacher_ids

        if comp.status not in OPEN_STATUSES or (approved and comp.status != "pending"):
            verb = "اعتماد" if approved else "رفض"
            raise ValueError(f"لا يمكن {verb} طلب بحالة: {comp.get_status_display()}")
        if approved_by.pk in {comp.teacher_id, comp.colleague_id}:
            raise ValueError("لا تُقرّر في طلبٍ أنت طرفٌ فيه — يقرّره غيرُك")
        dept = get_department_teacher_ids(approved_by)
        if dept is not None and comp.teacher_id not in dept:
            raise ValueError("هذا الطلبُ من خارج قسمك")

        comp.approved_by = approved_by
        comp.approved_at = timezone.now()

        if approved:
            row = CompensatoryService._option(
                comp.school,
                comp.teacher,
                comp.class_group,
                comp.compensatory_date,
                comp.compensatory_period,
                exclude=comp.pk,
            )
            if (row["colleague"].pk if row["colleague"] else None) != comp.colleague_id:
                raise ValueError("تغيّر صاحبُ الحصّة منذ الطلب — فليُقدَّم طلبٌ يوافق عليه صاحبُها")
            comp.status = "approved"
            comp.session_created = CompensatoryService._take(comp, row)

            # تحديث FreeSlotRegistry — حجز الحصة وربطها بالتعويض
            mapping = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}
            our_day = mapping.get(comp.compensatory_date.weekday(), -1)
            if our_day >= 0:
                FreeSlotRegistry.objects.filter(
                    teacher=comp.teacher,
                    school=comp.school,
                    day_of_week=our_day,
                    period_number=comp.compensatory_period,
                ).update(is_available=False, reserved_for=comp)
        else:
            comp.status = "cancelled"
            comp.notes = f"{comp.notes}\nسبب الرفض: {rejection_reason}".strip()

        comp.save()

        people = {comp.teacher_id} | ({comp.colleague_id} if comp.colleague_id else set())
        status_text = "تمت الموافقة" if approved else "تم الرفض"
        CompensatoryService._tell(comp, people - {approved_by.pk}, f"طلب التعويض: {status_text}")
        return comp

    @staticmethod
    @transaction.atomic
    def withdraw(comp: CompensatorySession, user: CustomUser) -> CompensatorySession:
        """صاحبُ الطلب يسحبه ما دام مفتوحاً — فتُفكّ حصّتُه لغيره."""
        if comp.teacher_id != user.pk or comp.status not in OPEN_STATUSES:
            raise ValueError("السحبُ لصاحب الطلب وحدَه، ما دام مفتوحاً")
        comp.status = "cancelled"
        comp.notes = f"{comp.notes}\nسحبه صاحبُه".strip()
        comp.save(update_fields=["status", "notes", "updated_at"])
        who = {comp.colleague_id} if comp.colleague_id else CompensatoryService._coordinators(user)
        CompensatoryService._tell(comp, who - {None}, f"سحب {user.full_name} طلبَ التعويض")
        return comp

    @classmethod
    @transaction.atomic
    def release_for_absence(cls, absence: TeacherAbsence) -> int:
        """معلّمٌ سُجّل غائباً: تُلغى تعويضاتُه ذلك اليوم وتعود الحصّةُ إلى صاحبها.

        حصّةُ التعويض ليست في خاناته الأسبوعيّة، فلا تظهر في صفحة غيابه للإشغال — فتبقى
        الشعبةُ بلا معلّمٍ ولا يعلم أحد، وقد تنازل عنها الزميلُ قبل ذلك. فالإلغاءُ آليٌّ:
        الحصّةُ لزميلها بمادّته، أو تُحذف إن كانت جديدةً، والطلبُ المفتوحُ يُلغى، ويُبلَّغ
        الزميلُ والمعلّمُ ومنسّقوه. وما رُصد حضورُه لا يُمسّ: الحصّةُ جرت. Returns: عددُ ما أُلغي.
        """
        comps = CompensatorySession.objects.filter(
            school=absence.school,
            teacher=absence.teacher,
            compensatory_date=absence.date,
            status__in=(*OPEN_STATUSES, "approved"),
        ).select_related("session_created", "colleague", "class_group")
        return sum(1 for comp in comps if cls._release(comp))

    @classmethod
    def _release(cls, comp: CompensatorySession) -> bool:
        lesson = comp.session_created if comp.status == "approved" else None
        if lesson is not None and (
            lesson.status != "scheduled"
            or lesson.attendances.exists()
            or lesson.class_exits.exists()
            or lesson.infractions.exists()
        ):
            return False  # جرت الحصّةُ: لا يُعاد شيء
        comp.session_created = None
        comp.status = "cancelled"
        comp.notes = f"{comp.notes}\nأُلغي: غاب المعلّمُ يومَ التعويض".strip()
        comp.save(update_fields=["session_created", "status", "notes", "updated_at"])
        if lesson is not None:
            cls._give_back(comp, lesson)
        FreeSlotRegistry.objects.filter(reserved_for=comp).update(
            is_available=True, reserved_for=None
        )
        people = {comp.teacher_id, comp.colleague_id} | cls._coordinators(comp.teacher)
        cls._tell(comp, people - {None}, f"أُلغي تعويضٌ لغياب {comp.teacher.full_name} يومَه")
        return True

    @staticmethod
    def _give_back(comp: CompensatorySession, lesson: Session) -> None:
        """حصّةُ التعويض بعد إلغائه: لزميلها بمادّته من خانته، أو محذوفةً إن أنشأها التعويضُ."""
        if comp.colleague_id is None or lesson.original_teacher_id != comp.colleague_id:
            lesson.delete()  # لم تكن لأحدٍ قبله: كانت الشعبةُ فارغةً في وقتها
            return
        from operations.services.substitute import SubstituteService

        subject_id = (
            ScheduleSlot.objects.live(comp.school)
            .filter(
                teacher_id=comp.colleague_id,
                class_group=comp.class_group,
                day_of_week=SubstituteService._date_to_day(comp.compensatory_date),
                start_time=lesson.start_time,
            )
            .values_list("subject_id", flat=True)
            .first()
        )
        lesson.teacher_id = comp.colleague_id
        lesson.original_teacher = None
        lesson.subject_id = subject_id or lesson.subject_id
        lesson.notes = ""
        lesson.save(update_fields=["teacher", "original_teacher", "subject", "notes"])

    @staticmethod
    def _take(comp: CompensatorySession, row: dict[str, Any]) -> Session:
        """حصّةُ التعويض: حصّةُ الزميل ذلك اليومَ تصير لصاحب التعويض بمادّته، ويبقى اسمُ
        الزميل في `original_teacher` — أو حصّةٌ جديدة إن فرغت الشعبةُ في وقتها."""
        notes = f"حصة تعويضية — أصلية: {comp.original_slot}"
        lesson: Session | None = row["lesson"]
        if lesson is None:
            return Session.objects.create(
                school=comp.school,
                teacher=comp.teacher,
                class_group=comp.class_group,
                subject=comp.subject,
                date=comp.compensatory_date,
                start_time=row["start"],
                end_time=row["end"],
                period_number=row["period"],
                status="scheduled",
                notes=notes,
            )
        lesson.original_teacher_id = lesson.teacher_id
        lesson.teacher = comp.teacher
        lesson.subject = comp.subject
        lesson.notes = notes
        lesson.save(update_fields=["teacher", "original_teacher", "subject", "notes"])
        return lesson

    @staticmethod
    @transaction.atomic
    def complete_compensatory(comp: CompensatorySession) -> CompensatorySession:
        """إكمال الحصة التعويضية بعد تسجيل الحضور."""
        if comp.status != "approved":
            raise ValueError("الحصة ليست معتمدة بعد")
        comp.status = "completed"
        comp.save(update_fields=["status", "updated_at"])
        return comp

    @staticmethod
    def expire_overdue(school: School) -> int:
        """إنهاءُ الطلبات المفتوحة التي فات وقتُها: مضى يومُ التعويض، أو مرّ عليها أكثرُ من أسبوعين.

        طلبٌ لزميلٍ لم يردّ أو لمنسّقٍ لم يعتمد يبقى معلَّقاً بعد أن يصير يومُه في الماضي، ولا يقبله أحدٌ
        (`_not_past`) — فيُعدّ انشغالاً في طلبات صاحبه المفتوحة ويسدّ خانةَ يومه في الخيارات إلى أن يُلغيه
        أحد. فيُنهيه ما تستدعيه المهمّةُ اليوميّة (`operations.expire_overdue_compensatory`). ثابتةُ التكرار:
        الطلبُ المنتهي ليس مفتوحاً فلا تمسّه الدورةُ الثانية، والمعتمَدُ والمكتمل لا يُمسّان.
        """
        today = timezone.localdate()
        cutoff = today - timedelta(days=MAX_GAP_DAYS)
        updated = CompensatorySession.objects.filter(
            Q(compensatory_date__lt=today) | Q(created_at__date__lt=cutoff),
            school=school,
            status__in=OPEN_STATUSES,
        ).update(status="expired", updated_at=timezone.now())
        if updated:
            logger.info("CompensatoryService.expire_overdue: expired %d requests", updated)
        return updated

    @staticmethod
    def session_ids(sessions: list[Session]) -> set[Any]:
        """ما كان من حصص اليوم تعويضاً — تمييزاً له عن التبديل في «حصصي اليوم».

        ثلاثتُها تكتب `original_teacher`؛ والتعويضُ يُعرف بسجلّه. استعلامٌ واحدٌ للقائمة.
        """
        moved = [s.pk for s in sessions if s.original_teacher_id]
        if not moved:
            return set()
        return set(
            CompensatorySession.objects.filter(session_created_id__in=moved).values_list(
                "session_created_id", flat=True
            )
        )

    # ── الإبلاغ ────────────────────────────────────────────────────

    @staticmethod
    def _coordinators(teacher: CustomUser) -> set[Any]:
        """منسّقو قسم المعلّم — يعتمدون تعويضَه."""
        dept = teacher.department_obj
        if not dept:
            return set()
        return set(
            dept.memberships.filter(is_active=True, role__name="coordinator").values_list(
                "user_id", flat=True
            )
        )

    @staticmethod
    def _tell(comp: CompensatorySession, user_ids: set[Any], title: str) -> None:
        """إشعارٌ بعد تثبيت المعاملة — وفشلُه لا يُسقط القرار، لكنّه يُسجَّل لا يُبتلع."""
        from core.models import CustomUser

        recipients = list(CustomUser.objects.filter(id__in=user_ids, is_active=True))
        if not recipients:
            return
        colleague = comp.colleague
        where = f" في حصّة {colleague.full_name}" if colleague else ""
        body = (
            f"{comp.teacher.full_name} يعوّض {comp.subject or 'حصّته'} للشعبة "
            f"{comp.class_group.short_label}{where}: الحصّة {comp.compensatory_period} "
            f"يوم {comp.compensatory_date:%d/%m}."
        )

        def _send() -> None:
            try:
                from notifications.hub import NotificationHub

                NotificationHub.dispatch(
                    event_type="compensatory",
                    school=comp.school,
                    recipients=recipients,
                    title=title,
                    body=body,
                    related_url="/teacher/schedule/compensatory/",
                    related_object_id=str(comp.pk),
                )
            except Exception as exc:
                logger.warning("CompensatoryService notify failed [%s]: %s", comp.pk, exc)

        transaction.on_commit(_send)
