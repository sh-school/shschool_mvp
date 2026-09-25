"""operations/services/swap.py — مبادلات الحصص بين المعلّمين.

منقولٌ حرفيّاً من `operations/services.py` (البند 8)؛ لا تغيير في المنطق.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from django.db import models, transaction

from operations.models import (
    ScheduleSlot,
    TeacherAbsence,
    TeacherSwap,
    TimeSlotConfig,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School
from operations.services.substitute import SubstituteService


class SwapService:
    """خدمة تبديل الحصص بين المعلمين."""

    # ── ثوابت القوانين ────────────────────────────────────────────
    MIN_ADVANCE_HOURS = 24  # القانون 6: حد أدنى 24 ساعة مسبقاً
    MAX_ADVANCE_DAYS = 14  # القانون 8: حد أقصى 14 يوم مسبقاً
    EXPIRY_HOURS = 48  # القانون 7: انتهاء صلاحية بعد 48 ساعة
    MAX_PENDING_PER_TEACHER = 2  # القانون 8: حد أقصى طلبين معلّقين
    MAX_EXECUTED_PER_MONTH = 4  # القانون 8: حد أقصى 4 تبديلات شهرياً
    # مواد تُعامل كحصص مزدوجة (SC7)
    DOUBLE_PERIOD_SUBJECTS = {
        "فنون بصرية",
        "الفنون البصرية",
        "تكنولوجيا",
        "التكنولوجيا",
        "تكنولوجيا المعلومات",
    }

    # ── التحقق الشامل من قوانين التبديل ───────────────────────────

    @staticmethod
    def validate_swap_request(
        teacher: CustomUser,
        slot_a: ScheduleSlot,
        slot_b: ScheduleSlot,
        swap_date: date,
        school: School,
    ) -> list[str]:
        """
        يتحقق من جميع قوانين التبديل — يعيد قائمة أخطاء (فارغة = صالح).

        القوانين:
        1. لا طلب مكرر لنفس الحصة المعلّقة
        2. نفس الفصل فقط
        3. لا تعارض مع طلبات معلّقة على حصة ب
        6. تاريخ مستقبلي + 24 ساعة على الأقل
        7. (تلقائي — cron/management command)
        8a. حد الطلبات المعلّقة (2)
        8b. حد التبديلات الشهرية (4)
        5. حصص مزدوجة تُبدّل كوحدة
        """
        from datetime import datetime, timedelta

        from django.utils import timezone as tz

        errors = []
        now = tz.now()
        today = now.date()

        # ── القانون 2: نفس الفصل ──────────────────────────────────
        if slot_a.class_group_id != slot_b.class_group_id:
            errors.append("التبديل مسموح فقط مع معلمي نفس الفصل")

        # ── القانون 9: لا تبديلَ إلى خانةٍ مفرَّغةٍ بقرارٍ ملزم ─────────────
        # كلٌّ من المعلّمَين يأخذ خانةَ الآخر؛ فإن كان أحدُهما مفرَّغاً فيها
        # بقرار وزارةٍ أو إدارةٍ أو قسمٍ رُفض التبديل — وكان لا يُفحص أصلاً.
        # أمّا تفريغُ «لتوليد الجدول» فيُوسَم ولا يمنع (قرار 2026-09-11).
        for mover, target in ((teacher, slot_b), (slot_b.teacher, slot_a)):
            if mover and mover.id in SubstituteService.exempted_teacher_ids(
                school, target.day_of_week, target.period_number
            ):
                errors.append(f"{mover.full_name} مفرَّغٌ في هذه الخانة بقرارٍ ملزم — لا يُبدَّل إليها")

        # ── القانون 6: تاريخ مستقبلي + 24 ساعة ────────────────────
        if swap_date < today:
            errors.append("لا يمكن التبديل في تاريخ ماضٍ")
        else:
            # حساب 24 ساعة من الآن
            swap_datetime = datetime.combine(swap_date, slot_a.start_time)
            swap_datetime = (
                tz.make_aware(swap_datetime) if tz.is_naive(swap_datetime) else swap_datetime
            )
            if swap_datetime - now < timedelta(hours=SwapService.MIN_ADVANCE_HOURS):
                errors.append("يجب تقديم الطلب قبل 24 ساعة على الأقل من موعد الحصة")

        # ── القانون 6b: حد أقصى 14 يوم ────────────────────────────
        if swap_date > today + timedelta(days=SwapService.MAX_ADVANCE_DAYS):
            errors.append(f"لا يمكن حجز تبديل بعد أكثر من {SwapService.MAX_ADVANCE_DAYS} يوماً")

        # ── القانون 1: لا طلب مكرر لنفس الحصة ─────────────────────
        pending_on_a = TeacherSwap.objects.filter(
            slot_a=slot_a,
            status__in=("pending_b", "accepted_b", "pending_coordinator", "pending_vp"),
        ).exists()
        if pending_on_a:
            errors.append("يوجد طلب تبديل معلّق على هذه الحصة بالفعل")

        # ── القانون 3: لا طلب معلّق على حصة ب ─────────────────────
        pending_on_b = (
            TeacherSwap.objects.filter(
                status__in=("pending_b", "accepted_b", "pending_coordinator", "pending_vp"),
            )
            .filter(models.Q(slot_a=slot_b) | models.Q(slot_b=slot_b))
            .exists()
        )
        if pending_on_b:
            errors.append("حصة المعلم الآخر عليها طلب تبديل معلّق")

        # ── القانون 8a: حد الطلبات المعلّقة (2) ───────────────────
        pending_count = TeacherSwap.objects.filter(
            teacher_a=teacher,
            status__in=("pending_b", "accepted_b", "pending_coordinator", "pending_vp"),
        ).count()
        if pending_count >= SwapService.MAX_PENDING_PER_TEACHER:
            errors.append(
                f"لديك {pending_count} طلبات معلّقة — الحد الأقصى {SwapService.MAX_PENDING_PER_TEACHER}"
            )

        # ── القانون 8b: حد التبديلات الشهرية (4) ──────────────────
        month_start = swap_date.replace(day=1)
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        executed_this_month = TeacherSwap.objects.filter(
            teacher_a=teacher,
            status="executed",
            swap_date_a__gte=month_start,
            swap_date_a__lt=next_month,
        ).count()
        if executed_this_month >= SwapService.MAX_EXECUTED_PER_MONTH:
            errors.append(
                f"وصلت للحد الأقصى ({SwapService.MAX_EXECUTED_PER_MONTH} تبديلات) هذا الشهر"
            )

        # ── القانون 5: حصص مزدوجة تُبدّل كوحدة ───────────────────
        subj_name = slot_a.subject.name_ar if slot_a.subject else ""
        if subj_name in SwapService.DOUBLE_PERIOD_SUBJECTS:
            # ابحث عن الحصة المتتالية لنفس المعلم/الفصل/المادة/اليوم
            adjacent = (
                ScheduleSlot.objects.live(school, year=slot_a.academic_year)
                .filter(
                    teacher=slot_a.teacher,
                    class_group=slot_a.class_group,
                    subject=slot_a.subject,
                    day_of_week=slot_a.day_of_week,
                    period_number__in=(slot_a.period_number - 1, slot_a.period_number + 1),
                )
                .first()
            )
            if adjacent:
                # تأكد أنه لا يوجد استراحة بينهما
                between_min = min(slot_a.period_number, adjacent.period_number)
                between_max = max(slot_a.period_number, adjacent.period_number)
                has_break_between = TimeSlotConfig.objects.filter(
                    school=school,
                    is_break=True,
                    period_number__gt=between_min,
                    period_number__lt=between_max,
                ).exists()
                if not has_break_between:
                    errors.append(
                        f"هذه حصة مزدوجة ({subj_name}) — يجب تبديل الحصتين معاً (ح{adjacent.period_number} أيضاً)"
                    )

        return errors

    @staticmethod
    def get_swap_options(
        teacher: CustomUser,
        slot: ScheduleSlot,
        school: School,
    ) -> list:
        """
        معلمي نفس الفصل المتاحين للتبديل مع حصة معيّنة.
        القيد: التبديل مع معلمي نفس الفصل فقط.
        """
        same_class_slots = (
            ScheduleSlot.objects.live(school, year=slot.academic_year)
            .filter(class_group=slot.class_group)
            .exclude(
                teacher=teacher,
            )
            .select_related("teacher", "class_group", "subject")
        )

        # تصفية: المعلم ب يجب أن يكون فارغاً في وقت الحصة أ
        options = []
        for candidate_slot in same_class_slots:
            # هل المعلم ب فارغ في وقت حصة أ؟
            b_busy_at_a = (
                ScheduleSlot.objects.live(school, year=slot.academic_year)
                .filter(
                    teacher=candidate_slot.teacher,
                    day_of_week=slot.day_of_week,
                    period_number=slot.period_number,
                )
                .exists()
            )
            # هل المعلم أ فارغ في وقت حصة ب؟
            a_busy_at_b = (
                ScheduleSlot.objects.live(school, year=slot.academic_year)
                .filter(
                    teacher=teacher,
                    day_of_week=candidate_slot.day_of_week,
                    period_number=candidate_slot.period_number,
                )
                .exists()
            )

            if not b_busy_at_a and not a_busy_at_b:
                options.append(
                    {
                        "teacher": candidate_slot.teacher,
                        "slot": candidate_slot,
                        "same_subject": candidate_slot.subject == slot.subject,
                    }
                )
        return options

    @staticmethod
    @transaction.atomic
    def create_swap_request(
        school: School,
        teacher_a: CustomUser,
        teacher_b: CustomUser,
        slot_a: ScheduleSlot,
        slot_b: ScheduleSlot,
        swap_date_a: date,
        swap_date_b: date,
        reason: str = "",
        requested_by: CustomUser | None = None,
    ) -> TeacherSwap:
        """إنشاء طلب تبديل + التحقق من القوانين + إرسال إشعار للمعلم ب."""
        # ── التحقق من القوانين ─────────────────────────────────
        errors = SwapService.validate_swap_request(
            teacher=teacher_a,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date=swap_date_a,
            school=school,
        )
        if errors:
            raise ValueError(" | ".join(errors))

        swap_type = "same_day" if swap_date_a == swap_date_b else "cross_day"
        swap = TeacherSwap.objects.create(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_b,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=swap_date_a,
            swap_date_b=swap_date_b,
            swap_type=swap_type,
            status="pending_b",
            requested_by=requested_by or teacher_a,
            reason=reason,
        )
        # إشعار المعلم ب
        SwapService._notify(
            swap,
            teacher_b,
            title=f"طلب تبديل حصة من {teacher_a.full_name}",
            body=f"يطلب منك تبديل حصته ({slot_a.subject or 'حصة'}) بحصتك ({slot_b.subject or 'حصة'})",
            event_type="swap_request",
        )
        logger.info(
            "SwapService: created swap %s (%s <-> %s)",
            swap.pk,
            teacher_a.full_name,
            teacher_b.full_name,
        )
        return swap

    @staticmethod
    @transaction.atomic
    def respond_to_swap(
        swap: TeacherSwap, accepted: bool, rejection_reason: str = ""
    ) -> TeacherSwap:
        """المعلم ب يقبل أو يرفض."""
        from django.utils import timezone as tz

        if swap.status != "pending_b":
            raise ValueError(f"لا يمكن الرد على طلب بحالة: {swap.get_status_display()}")

        swap.b_responded_at = tz.now()
        if accepted:
            # والجهةُ التاليةُ المنسّقون دائماً — لا النائبُ عند اختلاف
            # المادّتين. فاختلافُهما يعني منسّقَين لا مرجعاً أعلى.
            swap.status = "pending_coordinator"
            waiting = "منسّق المادّة" if swap.needs_one_signature() else "منسّقَي المادّتين"
            SwapService._notify(
                swap,
                swap.teacher_a,
                title=f"{swap.teacher_b.full_name} وافق على التبديل",
                body=f"بانتظار موافقة {waiting}",
                event_type="swap_response",
            )
            if swap.absence_id:
                # تبديلُ غيابٍ وقّعه منسّقاه حين بدأه: ينتقل إلى النائب بعد القبول.
                from operations.services.absence_swap import AbsenceSwapService

                swap.save()
                AbsenceSwapService.to_vp_if_signed(swap)
                return swap
        else:
            swap.status = "rejected_b"
            swap.rejection_reason = rejection_reason
            SwapService._notify(
                swap,
                swap.teacher_a,
                title=f"{swap.teacher_b.full_name} رفض التبديل",
                body=rejection_reason or "يمكنك اختيار معلم آخر",
                event_type="swap_response",
            )
        swap.save()
        return swap

    @staticmethod
    def signable_sides(swap: TeacherSwap, user: CustomUser) -> tuple[str, ...]:
        """الجهاتُ التي يملك هذا المستخدمُ التوقيعَ عنها الآن.

        منسّقُ الجهةِ يوقّع عنها. والنائبُ الأكاديميُّ (والمديرُ) بديلٌ عن
        الغائب لا متجاوزٌ عليه: يوقّع عن جهةٍ لا منسّقَ لها، أو منسّقُها
        غائبٌ اليوم، أو منسّقُها طرفٌ في التبديل — فلا يحكم في أمرِ نفسه.
        """
        role = user.get_role()
        deputy = role in ("principal", "vice_academic")
        parties = {swap.teacher_a_id, swap.teacher_b_id}
        sides = []
        for side in swap.awaiting_sides:
            head = swap.coordinator_for(side)
            if head is not None and head.pk == user.pk:
                sides.append(side)
            elif deputy and (
                head is None
                or head.pk in parties
                or SwapService._is_absent_today(swap.school, head)
            ):
                sides.append(side)
        return tuple(sides)

    @staticmethod
    def _is_absent_today(school, teacher) -> bool:
        from django.utils import timezone as tz

        return (
            TeacherAbsence.objects.filter(school=school, teacher=teacher, date=tz.localdate())
            .exclude(status="rejected")
            .exists()
        )

    @staticmethod
    @transaction.atomic
    def approve_swap(
        swap: TeacherSwap,
        approved_by: CustomUser,
        approved: bool = True,
        rejection_reason: str = "",
    ) -> TeacherSwap:
        """منسّقُ المادّة يوقّع عن جهته — ولا يُنفَّذ حتّى تُوقَّع الجهتان.

        وتبديلُ الغياب بعد التوقيعين ينتظر النائبَ الأكاديميّ (قرارُ المالك 2026-09-23).
        """
        from django.utils import timezone as tz

        from operations.services.absence_swap import AbsenceSwapService

        if swap.status == "pending_vp":
            return AbsenceSwapService.vp_decide(swap, approved_by, approved, rejection_reason)

        valid_statuses = ("pending_coordinator", "pending_vp", "accepted_b")
        if swap.status not in valid_statuses:
            raise ValueError(f"لا يمكن اعتماد طلب بحالة: {swap.get_status_display()}")

        swap.approved_by = approved_by
        swap.approved_at = tz.now()

        if approved:
            sides = SwapService.signable_sides(swap, approved_by)
            if not sides:
                raise ValueError(
                    "لا تملك التوقيعَ عن جهةٍ في هذا الطلب — "
                    "التوقيعُ لمنسّق المادّة، وللنائب عن الغائب منهما."
                )
            for side in sides:
                setattr(swap, f"approved_{side}_by", approved_by)
                setattr(swap, f"approved_{side}_at", tz.now())
                head = swap.coordinator_for(side)
                setattr(
                    swap,
                    f"approved_{side}_by_substitute",
                    head is None or head.pk != approved_by.pk,
                )
            if not swap.is_fully_approved:
                swap.save()
                SwapService._notify(
                    swap,
                    swap.teacher_a,
                    title="وُقّعت جهةٌ من التبديل",
                    body="بانتظار توقيع منسّق المادّة الأخرى",
                    event_type="swap_response",
                )
                return swap
            if swap.absence_id:
                swap.save()
                AbsenceSwapService.to_vp_if_signed(swap)
                return swap
            swap.status = "approved"
            # تنفيذ تلقائي
            SwapService.execute_swap(swap)
        else:
            swap.status = "rejected"
            swap.rejection_reason = rejection_reason
            # إشعار الطرفين
            for t in (swap.teacher_a, swap.teacher_b):
                SwapService._notify(
                    swap,
                    t,
                    title="تم رفض طلب التبديل",
                    body=rejection_reason or "تم رفض الطلب من الإدارة",
                    event_type="swap_response",
                )
        swap.save()
        return swap

    @staticmethod
    @transaction.atomic
    def execute_swap(swap: TeacherSwap) -> None:
        """تنفيذُ التبديل — في يومَيه وحدَهما لا في قالب الأسبوع.

        كان يبدّل المعلّمَين في `ScheduleSlot`، وهو قالبُ الأسبوع كلِّه: فتبديلُ
        حصّةِ يومٍ واحدٍ كان يُبدّلها كلَّ أسبوعٍ إلى الأبد، ولا يعود الجدولُ
        كما كان أبداً. والتبديلُ مؤقّتٌ بطبعه (قرارُ المستخدم 2026-09-11):
        ينقضي بانتهاء الحصّة الأبعد، ويعود الجدولُ من نفسه.

        فالأثرُ يقع على حصّة اليوم `Session`. ولو لم تكن مُنشأةً بعد أُنشئت من
        قالبها: القالبُ يقول إنّ هذه الحصّة قائمةٌ في ذلك اليوم، والتبديلُ
        يحتاج صفّاً يحمل أثرَه. و`original_teacher` هو ما يُلوّن الخانةَ لاحقاً
        ويقول لمن كانت.
        """
        from django.utils import timezone as tz

        SwapService._move_session(swap, swap.slot_a, swap.swap_date_a, swap.teacher_b)
        SwapService._move_session(swap, swap.slot_b, swap.swap_date_b, swap.teacher_a)

        swap.status = "executed"
        swap.executed_at = tz.now()
        swap.save(update_fields=["status", "executed_at"])

        # إشعار الطرفين
        for t in (swap.teacher_a, swap.teacher_b):
            SwapService._notify(
                swap,
                t,
                title="تم تنفيذ التبديل بنجاح",
                body=f"التبديل بين {swap.teacher_a.full_name} و {swap.teacher_b.full_name} تم",
                event_type="swap_approved",
            )
        logger.info("SwapService: executed swap %s", swap.pk)

    @staticmethod
    def _move_session(swap: TeacherSwap, slot, day, to_teacher) -> None:
        """يُسلّم حصّةَ ذلك اليوم لمعلّمٍ آخر — والتسليمُ نفسُه مشتركٌ مع الإشغال."""
        SubstituteService.hand_over_session(swap.school, slot, day, to_teacher)

    @staticmethod
    @transaction.atomic
    def force_swap(
        school: School,
        teacher_a: CustomUser,
        teacher_b: CustomUser,
        slot_a: ScheduleSlot,
        slot_b: ScheduleSlot,
        swap_date_a: date,
        swap_date_b: date,
        forced_by: CustomUser,
        reason: str = "",
    ) -> TeacherSwap:
        """نائب/مدير ينشئ وينفذ تبديل مباشرة بدون مسار موافقة."""
        swap_type = "same_day" if swap_date_a == swap_date_b else "cross_day"
        swap = TeacherSwap.objects.create(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_b,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=swap_date_a,
            swap_date_b=swap_date_b,
            swap_type=swap_type,
            status="approved",
            requested_by=forced_by,
            approved_by=forced_by,
            reason=reason,
        )
        SwapService.execute_swap(swap)
        return swap

    # ── إلغاء الطلب (القانون 9 / 12-14) ─────────────────────────

    @staticmethod
    @transaction.atomic
    def cancel_swap(swap: TeacherSwap, cancelled_by: CustomUser) -> TeacherSwap:
        """
        إلغاء طلب تبديل:
        - قبل رد المعلم ب → المعلم أ يلغي بحرية
        - بعد رد المعلم ب وقبل المنسق → أي طرف يطلب سحب
        - بعد موافقة المنسق → المنسق/النائب/المدير فقط
        """
        role = cancelled_by.get_role()
        is_leadership = role in ("coordinator", "principal", "vice_academic", "vice_admin")

        if swap.status == "pending_b":
            # القانون 12: المعلم أ يلغي بحرية
            if cancelled_by != swap.teacher_a and not is_leadership:
                raise ValueError("فقط المعلم صاحب الطلب يمكنه الإلغاء في هذه المرحلة")
        elif swap.status in ("accepted_b", "pending_coordinator", "pending_vp"):
            # القانون 13: أي طرف أو القيادة
            if cancelled_by not in (swap.teacher_a, swap.teacher_b) and not is_leadership:
                raise ValueError("فقط أحد المعلمين أو القيادة يمكنهم السحب")
        elif swap.status == "approved":
            # القانون 14: القيادة فقط
            if not is_leadership:
                raise ValueError("بعد الموافقة — فقط المنسق أو النائب أو المدير يمكنه الإلغاء")
        else:
            raise ValueError(f"لا يمكن إلغاء طلب بحالة: {swap.get_status_display()}")

        swap.status = "cancelled"
        swap.notes = f"ألغاه: {cancelled_by.full_name}"
        swap.save(update_fields=["status", "notes", "updated_at"])

        # إشعار الطرفين
        for t in (swap.teacher_a, swap.teacher_b):
            if t != cancelled_by:
                SwapService._notify(
                    swap,
                    t,
                    title="تم إلغاء طلب التبديل",
                    body=f"قام {cancelled_by.full_name} بإلغاء الطلب",
                    event_type="swap_cancelled",
                )
        logger.info("SwapService: cancelled swap %s by %s", swap.pk, cancelled_by.full_name)
        return swap

    # ── انتهاء صلاحية الطلبات المعلّقة (القانون 7) ────────────────

    @staticmethod
    def expire_stale_swaps() -> int:
        """
        يُنفّذ دورياً (cron/management command) —
        يُلغي الطلبات المعلّقة أكثر من 48 ساعة بدون رد من المعلم ب.
        """
        from datetime import timedelta

        from django.utils import timezone as tz

        cutoff = tz.now() - timedelta(hours=SwapService.EXPIRY_HOURS)
        stale = TeacherSwap.objects.filter(
            status="pending_b",
            created_at__lt=cutoff,
        )
        count = stale.count()
        for swap in stale:
            # [B4-PRE3] معاملة لكل طلب لا للدفعة كلّها.
            #
            # حدٌّ حول الحلقة كان سيجعل فشلاً في الطلب الأربعين يُلغي تسعةً
            # وثلاثين إلغاءً ناجحاً، ويُؤجّل إشعاراتها جميعاً إلى التزام واحد
            # في النهاية فتسقط معه. وهذا توسيعُ نطاق تراجع لم يكن في العقد.
            #
            # وبفضل B4-PRE2 يصير الخروج الخارجي الذي يُسجّله `_notify` مؤجّلاً
            # إلى التزام هذا الطلب وحده.
            with transaction.atomic():
                swap.status = "cancelled"
                swap.notes = "انتهت صلاحية الطلب — لم يرد المعلم خلال 48 ساعة"
                swap.save(update_fields=["status", "notes", "updated_at"])
                SwapService._notify(
                    swap,
                    swap.teacher_a,
                    title="انتهت صلاحية طلب التبديل",
                    body=f"لم يرد {swap.teacher_b.full_name} خلال 48 ساعة — يمكنك تقديم طلب جديد",
                    event_type="swap_expired",
                )
        if count:
            logger.info("SwapService: expired %d stale swaps", count)
        return count

    @staticmethod
    def _notify(swap: TeacherSwap, recipient: CustomUser, title: str, body: str, event_type: str):
        """إرسال إشعار — يفشل بصمت إذا نظام الإشعارات غير متاح."""
        try:
            from notifications.hub import NotificationHub

            NotificationHub.dispatch(
                event_type=event_type,
                school=swap.school,
                recipients=[recipient],
                title=title,
                body=body,
                related_url="/teacher/schedule/swaps/",
            )
        except Exception as exc:
            logger.warning("SwapService._notify failed [swap=%s]: %s", swap.pk, exc)
