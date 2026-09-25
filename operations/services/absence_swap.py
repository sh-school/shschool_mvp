"""operations/services/absence_swap.py — التبديلُ بسبب غياب المعلّم.

قراراتُ المالك (2026-09-23 و2026-09-24):

- التبديلُ مع معلّمي الشعبة نفسها وحدَهم: يأخذ المعلّمُ الآخرُ حصّةَ الغائب يومَ
  غيابه، ويردّ له الغائبُ حصّةً من حصصه في الشعبة يومَ عودته. فلا يزيد نصابُ أحد.
- يبدأه المنسّقُ: يوافق المعلّمُ الآخرُ أوّلاً، ثمّ يوقّع منسّقا المادّتين، ثمّ
  يعتمد النائبُ الأكاديميّ — أو من كُلِّف بأعبائه (`StaffAssignment`).
- تبدأه القيادةُ (النائبُ الأكاديميّ، أو المدير، أو المطوّر): يُنفَّذ فوراً.
- يُبلَّغ النائبُ مسبقاً، ويُبلَّغ الجميعُ بالتنفيذ أو الرفض.
- يسري من الاعتماد، ويعود الجدولُ بانتهاء الحصّة الأبعد: التبديلُ يقع على حصّة
  اليوم (`Session`) لا على قالب الأسبوع (`SwapService.execute_swap`).

والسجلُّ `TeacherSwap` نفسُه بحقل `absence`: من غاب، ومن بدّل، ومن وقّع ومتى،
ومن اعتمد — محفوظٌ للإحصاء.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from operations.models import ScheduleSlot, TeacherAbsence, TeacherSwap
from operations.services.substitute import SubstituteService
from operations.services.swap import SwapService

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School

#: مدى ردّ الحصّة: الأسبوعُ الجاري والذي يليه، كالتبديل العاديّ.
PAYBACK_WINDOW_DAYS = 14

#: من ينفّذ التبديلَ فوراً إن بدأه، ويعتمده إن بدأه المنسّق.
LEADERSHIP_ROLES = ("principal", "vice_academic")

#: حالاتُ طلبٍ ما زال يحجز حصّتَيه.
OPEN_STATUSES = ("pending_b", "accepted_b", "pending_coordinator", "pending_vp", "approved")


class AbsenceSwapService:
    @staticmethod
    def vp_approvers(school: School, day: date) -> set[Any]:
        """النائبُ الأكاديميّ ومن كُلِّف بأعبائه يومَ `day` — كلاهما يعتمد."""
        from core.models import Membership
        from staff_affairs.models import StaffAssignment

        holders = set(
            Membership.objects.filter(
                school=school, is_active=True, user__is_active=True, role__name="vice_academic"
            ).values_list("user_id", flat=True)
        )
        acting = set(
            StaffAssignment.objects.filter(
                school=school,
                acting_role="vice_academic",
                start_date__lte=day,
                end_date__gte=day,
                revoked_at__isnull=True,
            ).values_list("assignee_id", flat=True)
        )
        return holders | acting

    @staticmethod
    def is_leadership(user: CustomUser, school: School) -> bool:
        """من يُنفَّذ تبديلُه فوراً: المديرُ والنائبُ الأكاديميّ ومن كُلِّف عنه، والمطوّر."""
        from core.developer_access import is_platform_developer

        if user.role in LEADERSHIP_ROLES or is_platform_developer(user):
            return True
        return user.pk in AbsenceSwapService.vp_approvers(school, timezone.localdate())

    @staticmethod
    def can_final_approve(swap: TeacherSwap, user: CustomUser) -> bool:
        """أيعتمد هذا المستخدمُ تبديلاً ينتظر النائب؟"""
        return swap.status == "pending_vp" and AbsenceSwapService.is_leadership(user, swap.school)

    @staticmethod
    def options(absence: TeacherAbsence, slot: ScheduleSlot) -> list[dict]:
        """من يُبدَّل معه في حصّة الغائب، ومتى يردّ له الغائبُ حصّتَه.

        المرشَّحُ معلّمٌ في الشعبة نفسها، متفرّغٌ في حصّة الغائب يومَ غيابه، غيرُ
        غائبٍ ولا مفرَّغٍ فيها. ولكلّ حصّةٍ له في الشعبة يُقترح أقربُ يومٍ بعد الغياب
        يكون فيه الغائبُ متفرّغاً لها — وهو يومُ الردّ.
        """
        from operations.services.compensatory import CompensatoryService

        school = absence.school
        if slot.id in CompensatoryService.taken_slot_ids(absence):
            return []  # أخذها زميلٌ تعويضاً: ليست حصّةَ الغائب يومَه
        day_a = SubstituteService._date_to_day(absence.date)
        live = ScheduleSlot.objects.live(school)
        class_slots = [
            s
            for s in live.filter(class_group=slot.class_group)
            .exclude(teacher_id=absence.teacher_id)
            .select_related("teacher", "subject")
            if s.teacher_id
        ]
        candidates = {s.teacher_id for s in class_slots}
        busy = set(
            live.filter(
                teacher_id__in=candidates, day_of_week=day_a, period_number=slot.period_number
            ).values_list("teacher_id", flat=True)
        )
        absent_that_day = set(
            TeacherAbsence.objects.filter(school=school, date=absence.date).values_list(
                "teacher_id", flat=True
            )
        )
        exempt = SubstituteService.exempted_teacher_ids(school, day_a, slot.period_number)
        eligible = candidates - busy - absent_that_day - exempt

        absent_slots = set(
            live.filter(teacher_id=absence.teacher_id).values_list("day_of_week", "period_number")
        )
        away_days = set(
            TeacherAbsence.objects.filter(
                school=school,
                teacher_id=absence.teacher_id,
                date__gt=absence.date,
                date__lte=absence.date + timedelta(days=PAYBACK_WINDOW_DAYS),
            ).values_list("date", flat=True)
        )
        held = set(
            TeacherSwap.objects.filter(school=school, status__in=OPEN_STATUSES).values_list(
                "slot_a_id", "slot_b_id"
            )
        )
        held_slots = {slot_id for pair in held for slot_id in pair}
        if slot.id in held_slots:
            return []

        rows = []
        for other in class_slots:
            if other.teacher_id not in eligible or other.id in held_slots:
                continue
            if (other.day_of_week, other.period_number) in absent_slots:
                continue
            payback = AbsenceSwapService._next_date(absence.date, other.day_of_week, away_days)
            if payback is None:
                continue
            rows.append(
                {
                    "slot": other,
                    "date": payback,
                    "teacher": other.teacher,
                    "value": f"{other.id}|{payback.isoformat()}",
                }
            )
        rows.sort(key=lambda r: (r["teacher"].full_name, r["date"], r["slot"].period_number))
        return rows

    @staticmethod
    def _next_date(after: date, day_of_week: int, skip: set) -> date | None:
        """أقربُ تاريخٍ بعد `after` يقع في يوم القالب `day_of_week`، داخلَ المدى."""
        for offset in range(1, PAYBACK_WINDOW_DAYS + 1):
            day = after + timedelta(days=offset)
            if SubstituteService._date_to_day(day) == day_of_week and day not in skip:
                return day
        return None

    @staticmethod
    @transaction.atomic
    def request(
        absence: TeacherAbsence,
        slot_a: ScheduleSlot,
        slot_b: ScheduleSlot,
        date_b: date,
        actor: CustomUser,
    ) -> TeacherSwap:
        """ينشئ تبديلَ الغياب: القيادةُ تنفّذه فوراً، والمنسّقُ يبدأ مسارَ موافقته."""
        if slot_a.teacher_id != absence.teacher_id:
            raise ValueError("الحصّةُ ليست من حصص المعلّم الغائب")
        allowed = {
            (row["slot"].id, row["date"]) for row in AbsenceSwapService.options(absence, slot_a)
        }
        if (slot_b.id, date_b) not in allowed:
            raise ValueError("هذا التبديلُ غيرُ متاح — اختر من معلّمي الشعبة المتفرّغين")

        swap = TeacherSwap.objects.create(
            school=absence.school,
            teacher_a=absence.teacher,
            teacher_b=slot_b.teacher,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=absence.date,
            swap_date_b=date_b,
            swap_type="same_day" if absence.date == date_b else "cross_day",
            status="pending_b",
            absence=absence,
            requested_by=actor,
            reason=f"غياب {absence.teacher.full_name}",
        )
        if AbsenceSwapService.is_leadership(actor, absence.school):
            swap.status = "approved"
            swap.approved_by = actor
            swap.approved_at = timezone.now()
            swap.save(update_fields=["status", "approved_by", "approved_at"])
            SwapService.execute_swap(swap)
            SubstituteService.refresh_absence_status(absence)
            AbsenceSwapService._tell_everyone(swap, "نُفِّذ تبديلٌ بسبب غياب", actor)
            return swap

        # من يبدأه يوقّع عن جهته: بدؤه قرارُه.
        now = timezone.now()
        for side in SwapService.signable_sides(swap, actor):
            setattr(swap, f"approved_{side}_by", actor)
            setattr(swap, f"approved_{side}_at", now)
        swap.save()
        SwapService._notify(
            swap,
            swap.teacher_b,
            title=f"تبديلٌ بسبب غياب {absence.teacher.full_name} — ينتظر موافقتك",
            body=AbsenceSwapService._describe(swap),
            event_type="swap_request",
        )
        AbsenceSwapService._tell(
            swap,
            AbsenceSwapService.vp_approvers(absence.school, timezone.localdate()),
            "تبديلٌ بسبب غياب — للعلم قبل اعتمادك",
            actor,
        )
        return swap

    @staticmethod
    def to_vp_if_signed(swap: TeacherSwap) -> bool:
        """تبديلُ غيابٍ وقّعه منسّقاه وقبله المعلّم: ينتقل إلى النائب لا إلى التنفيذ."""
        if not swap.absence_id or swap.status not in ("accepted_b", "pending_coordinator"):
            return False
        if not swap.is_fully_approved:
            return False
        swap.status = "pending_vp"
        swap.save(update_fields=["status"])
        AbsenceSwapService._tell(
            swap,
            AbsenceSwapService.vp_approvers(swap.school, timezone.localdate()),
            "تبديلٌ بسبب غياب ينتظر اعتمادك",
            None,
        )
        return True

    @staticmethod
    @transaction.atomic
    def vp_decide(
        swap: TeacherSwap, user: CustomUser, approved: bool, rejection_reason: str = ""
    ) -> TeacherSwap:
        """النائبُ (أو من كُلِّف عنه) يعتمد التبديلَ فيُنفَّذ، أو يرفضه."""
        if not AbsenceSwapService.can_final_approve(swap, user):
            raise ValueError("اعتمادُ تبديل الغياب للنائب الأكاديميّ أو من كُلِّف بأعبائه")
        swap.approved_by = user
        swap.approved_at = timezone.now()
        if approved:
            swap.status = "approved"
            swap.save()
            SwapService.execute_swap(swap)
            if swap.absence is not None:
                SubstituteService.refresh_absence_status(swap.absence)
            AbsenceSwapService._tell_everyone(swap, "اعتُمد تبديلٌ بسبب غياب ونُفِّذ", user)
        else:
            swap.status = "rejected"
            swap.rejection_reason = rejection_reason
            swap.save()
            AbsenceSwapService._tell_everyone(swap, "رُفض تبديلٌ بسبب غياب", user)
        return swap

    @staticmethod
    def swaps_by_slot(absence: TeacherAbsence) -> dict:
        """تبديلاتُ هذا الغياب القائمةُ لكلّ حصّةٍ من حصصه — تقرؤها بطاقةُ الحصّة."""
        return {
            swap.slot_a_id: swap
            for swap in TeacherSwap.objects.filter(
                absence=absence, status__in=(*OPEN_STATUSES, "executed")
            ).select_related("teacher_b", "slot_b__subject")
        }

    @staticmethod
    def slot_label(swap: TeacherSwap) -> str:
        """سطرُ حال الحصّة المبدَّلة في بطاقتها. وتسميةُ «بانتظار النائب» المخزَّنة تذكر
        «تخصّصات مختلفة» — وهي هنا للغياب لا لاختلاف المادّتين."""
        if swap.status in ("approved", "executed"):
            return "مُغطّاة · تبديل"
        if swap.status == "pending_vp":
            return "تبديل · بانتظار اعتماد النائب"
        return f"تبديل · {swap.get_status_display()}"

    # ── الإبلاغ ────────────────────────────────────────────────────

    @staticmethod
    def _describe(swap: TeacherSwap) -> str:
        return (
            f"{swap.teacher_b.full_name} يأخذ الحصّة {swap.slot_a.period_number} "
            f"({swap.slot_a.subject or '—'} · {swap.slot_a.class_group}) يوم {swap.swap_date_a:%d/%m}، "
            f"ويردّها له {swap.teacher_a.full_name} الحصّة {swap.slot_b.period_number} "
            f"يوم {swap.swap_date_b:%d/%m}."
        )

    @staticmethod
    def _tell_everyone(swap: TeacherSwap, title: str, actor: CustomUser | None) -> None:
        """المعلّمان ومنسّقاهما والنائبُ والمدير والمطوّر — قرارُ المالك 2026-09-23."""
        if swap.absence is None:
            return
        people = {
            u.pk for u in SubstituteService.cover_recipients(swap.absence, swap.teacher_b, actor)
        }
        people |= AbsenceSwapService.vp_approvers(swap.school, timezone.localdate())
        if actor is not None:
            people.discard(actor.pk)
        AbsenceSwapService._tell(swap, people, title, None)

    @staticmethod
    def _tell(swap: TeacherSwap, user_ids: set, title: str, actor: CustomUser | None) -> None:
        from core.models import CustomUser

        if actor is not None:
            user_ids = user_ids - {actor.pk}
        recipients = list(CustomUser.objects.filter(id__in=user_ids, is_active=True))
        body = AbsenceSwapService._describe(swap)

        def _send() -> None:
            try:
                from notifications.hub import NotificationHub

                NotificationHub.dispatch(
                    event_type="teacher_cover",
                    school=swap.school,
                    recipients=recipients,
                    title=title,
                    body=body,
                    related_url="/teacher/schedule/swaps/",
                    related_object_id=str(swap.pk),
                )
            except Exception as exc:
                logger.warning("AbsenceSwapService notify failed [%s]: %s", swap.pk, exc)

        transaction.on_commit(_send)
