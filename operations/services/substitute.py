"""operations/services/substitute.py — البدلاء وإسناد الحصص عند غياب المعلّم.

منقولٌ حرفيّاً من `operations/services.py` (البند 8)؛ لا تغيير في المنطق.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date
from typing import TYPE_CHECKING

from django.db import models, transaction
from django.db.models import QuerySet

from operations.models import (
    ScheduleSlot,
    Session,
    SubjectClassAssignment,
    SubstituteAssignment,
    TeacherAbsence,
    TeacherExemption,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School

#: الكادرُ التعليميّ الذي يُسجَّل غيابُه ويُشغَل منه — قرارُ المالك 2026-09-23.
#: وكان البدلاءُ «معلّماً ومنسّقاً» وحدَهما، ويُسجَّل غيابُ الأربعة.
TEACHING_ROLES = ("teacher", "coordinator", "ese_teacher", "e_projects_coordinator")

#: حصّةٌ تصنع مع ما حولها من حصص المرشَّح هذا الطول تُنبَّه عليها.
LONG_RUN = 3


class SubstituteService:
    @staticmethod
    def get_available_teachers(
        school: School,
        date: date,
        day_of_week: int,
        period_number: int,
        exclude_teacher: CustomUser | None = None,
        subject_id: int | None = None,
        within_ids: set | None = None,
    ) -> QuerySet:
        """
        إيجاد معلمين متاحين للبدل:
        - لديهم membership نشطة في المدرسة
        - ليس لديهم حصة في نفس اليوم والحصة
        - لم يُسجَّل غيابهم في نفس اليوم

        إذا تم تمرير subject_id، يُرتَّب المعلمون بحيث يظهر
        معلمو نفس المادة أولاً ثم البقية. و`within_ids` يحصرهم في قسم المنسّق.
        """
        from core.models import Membership

        teacher_ids = set(
            Membership.objects.filter(
                school=school, is_active=True, role__name__in=TEACHING_ROLES
            ).values_list("user_id", flat=True)
        )

        if exclude_teacher:
            teacher_ids.discard(exclude_teacher.id)
        if within_ids is not None:
            teacher_ids &= within_ids

        # من لديهم حصة في نفس الوقت
        # والعامُ قيدٌ: معلّمٌ له حصّةٌ في جدول عامٍ مضى كان يُعدّ مشغولاً
        # فيُستبعد من البدلاء وهو متفرّغ.
        busy_ids = (
            ScheduleSlot.objects.live(school)
            .filter(day_of_week=day_of_week, period_number=period_number)
            .values_list("teacher_id", flat=True)
        )

        # من هم غائبون في نفس اليوم
        absent_ids = TeacherAbsence.objects.filter(school=school, date=date).values_list(
            "teacher_id", flat=True
        )

        # ومن فُرّغ في هذه الخانة بقرارٍ ملزم — وكان البديلُ يتجاهل التفريغَ كلَّه،
        # فيُقترح معلّمٌ أخرجته الوزارةُ من الحصّة. أمّا تفريغُ «لتوليد الجدول»
        # فيُوسَم ولا يمنع: صاحبُه رُتّب له جدولُه ولم يُمنَع من الحصّة.
        exempt_ids = SubstituteService.exempted_teacher_ids(school, day_of_week, period_number)

        available_ids = teacher_ids - set(busy_ids) - set(absent_ids) - exempt_ids

        from core.models import CustomUser

        qs = CustomUser.objects.filter(id__in=available_ids)

        if subject_id:
            from django.db.models import Case, IntegerField, Value, When

            same_subject_ids = set(
                SubjectClassAssignment.objects.live(school)
                .filter(subject_id=subject_id, teacher_id__in=available_ids)
                .values_list("teacher_id", flat=True)
            )
            qs = qs.annotate(
                same_subject=Case(
                    When(id__in=same_subject_ids, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("same_subject", "full_name")
        else:
            qs = qs.order_by("full_name")

        return qs

    @staticmethod
    def exempted_teacher_ids(school: School, day_of_week: int, period_number: int) -> set:
        """من لا يجوز إشغالُه في هذه الخانة بحكم تفريغٍ ملزم.

        يومٌ كاملٌ أو الحصّةُ بعينها، من عام المدرسة الجاري، وبجهةٍ تُلزم —
        فتفريغُ «لتوليد الجدول» لا يدخل هنا (`TeacherExemption.SOFT_SOURCES`).
        """
        full_day, by_period = SubstituteService._day_exemptions(school, day_of_week)
        return full_day | by_period.get(period_number, set())

    @staticmethod
    def _day_exemptions(school: School, day_of_week: int) -> tuple[set, dict[int, set]]:
        """تفريغاتُ اليوم الملزمة مرّةً: من فُرّغ يومَه كلَّه، ومن فُرّغ في كلّ حصّة."""
        from core.querysets import year_or_current

        rows = (
            TeacherExemption.objects.filter(
                school=school,
                academic_year=year_or_current(school),
                is_active=True,
                day_of_week=day_of_week,
            )
            .exclude(source__in=TeacherExemption.SOFT_SOURCES)
            .values_list("teacher_id", "exemption_type", "period_number")
        )
        full_day: set = set()
        by_period: dict[int, set] = {}
        for teacher_id, kind, period in rows:
            if kind == "full_day":
                full_day.add(teacher_id)
            elif period is not None:
                by_period.setdefault(period, set()).add(teacher_id)
        return full_day, by_period

    @staticmethod
    def coverage_candidates(
        absence: TeacherAbsence, slots: Iterable[ScheduleSlot], within_ids: set | None = None
    ) -> dict:
        """من يُشغَل في كلّ حصّةٍ من حصص الغائب، ومع كلٍّ ما يُختار به.

        أمام كلّ اسمٍ عدّادُ إشغالاته هذا العام ونصابُه المسند وحصصُه يومَها،
        وتنبيهٌ إن صارت له بالإشغال حصصٌ متلاصقةٌ طويلة — كي لا يُضغط جدولُه
        (قرارُ المالك 2026-09-23). ويُرتَّب معلّمو المادّة ثمّ الأقلُّ إشغالاً.
        والاستعلاماتُ ثابتةُ العدد مهما كثرت الحصص والمرشَّحون.
        """
        from django.db.models import Count

        from core.academic_calendar import academic_year_window
        from core.models import CustomUser, Membership

        school = absence.school
        slots = list(slots)
        day = SubstituteService._date_to_day(absence.date)

        pool = set(
            Membership.objects.filter(
                school=school,
                is_active=True,
                user__is_active=True,
                role__name__in=TEACHING_ROLES,
            ).values_list("user_id", flat=True)
        )
        pool.discard(absence.teacher_id)
        if within_ids is not None:
            pool &= set(within_ids)
        pool -= set(
            TeacherAbsence.objects.filter(school=school, date=absence.date).values_list(
                "teacher_id", flat=True
            )
        )
        if not slots or not pool:
            return {slot.id: [] for slot in slots}

        periods_of: dict = {}
        for teacher_id, period in (
            ScheduleSlot.objects.live(school)
            .filter(day_of_week=day, teacher_id__in=pool)
            .values_list("teacher_id", "period_number")
        ):
            periods_of.setdefault(teacher_id, set()).add(period)

        # `order_by()` فارغة: الترتيبُ الافتراضيّ للنموذج يدخل التجميعَ فيُفرّق العدّ.
        load = dict(
            ScheduleSlot.objects.live(school)
            .filter(teacher_id__in=pool)
            .order_by()
            .values_list("teacher_id")
            .annotate(n=Count("id"))
        )
        window = academic_year_window(school, absence.date)
        subs_qs = SubstituteAssignment.objects.filter(
            school=school, substitute_id__in=pool, status__in=("assigned", "confirmed")
        )
        if window:
            subs_qs = subs_qs.filter(absence__date__range=window)
        subs = dict(subs_qs.order_by().values_list("substitute_id").annotate(n=Count("id")))

        subject_ids = {s.subject_id for s in slots if s.subject_id}
        teaches: set = set(
            SubjectClassAssignment.objects.live(school)
            .filter(subject_id__in=subject_ids, teacher_id__in=pool)
            .values_list("subject_id", "teacher_id")
        )
        names = dict(CustomUser.objects.filter(id__in=pool).values_list("id", "full_name"))
        full_day, exempt_by_period = SubstituteService._day_exemptions(school, day)

        from operations.services.compensatory import CompensatoryService

        taken = CompensatoryService.taken_slot_ids(absence)
        result = {}
        for slot in slots:
            period = slot.period_number
            blocked = full_day | exempt_by_period.get(period, set())
            rows = []
            # حصّةٌ أخذها زميلٌ تعويضاً ليست للإشغال: لا مرشَّحَ لها.
            for teacher_id in () if slot.id in taken else pool - blocked:
                mine = periods_of.get(teacher_id, set())
                if period in mine:
                    continue
                rows.append(
                    {
                        "id": teacher_id,
                        "name": names.get(teacher_id, ""),
                        "subs": subs.get(teacher_id, 0),
                        "load": load.get(teacher_id, 0),
                        "day": len(mine),
                        "same_subject": (slot.subject_id, teacher_id) in teaches,
                        "long_run": SubstituteService._run_length(mine | {period}, period)
                        >= LONG_RUN,
                    }
                )
            rows.sort(key=lambda r: (not r["same_subject"], r["subs"], r["day"], r["name"]))
            result[slot.id] = rows
        return result

    @staticmethod
    def _run_length(periods: set, period: int) -> int:
        """طولُ سلسلة الحصص المتتالية التي تقع فيها `period`."""
        low = high = period
        while low - 1 in periods:
            low -= 1
        while high + 1 in periods:
            high += 1
        return high - low + 1

    @staticmethod
    @transaction.atomic
    def register_absence(
        school: School,
        teacher: CustomUser,
        date: date,
        reason: str,
        reason_notes: str = "",
        reported_by: CustomUser | None = None,
    ) -> TeacherAbsence:
        """تسجيل غياب معلم + إنشاء تعيينات البديل تلقائياً"""
        absence, created = TeacherAbsence.objects.get_or_create(
            school=school,
            teacher=teacher,
            date=date,
            defaults={
                "reason": reason,
                "reason_notes": reason_notes,
                "reported_by": reported_by,
                "status": "pending",
            },
        )
        return absence

    @staticmethod
    @transaction.atomic
    def assign_substitute(
        absence: TeacherAbsence,
        slot: ScheduleSlot,
        substitute: CustomUser,
        assigned_by: CustomUser | None = None,
        notes: str = "",
    ) -> SubstituteAssignment:
        """تعيينُ بديلٍ لحصّة: تكليفٌ نافذ، تُسلَّم له حصّةُ اليوم ويُبلَّغ الجميع.

        كان التعيينُ صفّاً في `SubstituteAssignment` وحدَه: لا يصل البديلَ إشعارٌ،
        ولا تظهر الحصّةُ في «حصصي اليوم» عنده — فلا يعلم أنّه كُلِّف.
        """
        assignment, created = SubstituteAssignment.objects.update_or_create(
            absence=absence,
            slot=slot,
            defaults={
                "substitute": substitute,
                "school": absence.school,
                "assigned_by": assigned_by,
                "notes": notes,
                "status": "assigned",
            },
        )
        SubstituteService.refresh_absence_status(absence)
        SubstituteService.hand_over_session(absence.school, slot, absence.date, substitute)
        transaction.on_commit(lambda: SubstituteService._notify_cover(assignment, assigned_by))
        return assignment

    @staticmethod
    def absence_slots(absence: TeacherAbsence) -> QuerySet[ScheduleSlot]:
        """حصصُ الغائب يومَ غيابه التي ما زالت عليه.

        ما أخذه زميلٌ تعويضاً لم يعد حصّتَه ذلك اليوم — فلا يُعرض للإشغال ولا يُحسب في
        التغطية، وإلّا كُتب فوق حصّة التعويض المعتمَدة فخسرها صاحبُها بلا إشعار.
        """
        from operations.services.compensatory import CompensatoryService

        return (
            ScheduleSlot.objects.live(absence.school)
            .filter(
                teacher=absence.teacher, day_of_week=SubstituteService._date_to_day(absence.date)
            )
            .exclude(id__in=CompensatoryService.taken_slot_ids(absence))
            .select_related("class_group", "subject")
        )

    @staticmethod
    def refresh_absence_status(absence: TeacherAbsence) -> None:
        """«مغطّى» حين تُغطّى كلُّ حصص الغائب يومَه — بإشغالٍ أو بتبديلٍ نُفِّذ."""
        from operations.models import TeacherSwap

        total_slots = SubstituteService.absence_slots(absence).count()
        covered = set(
            SubstituteAssignment.objects.filter(
                absence=absence, status__in=("assigned", "confirmed")
            ).values_list("slot_id", flat=True)
        ) | set(
            TeacherSwap.objects.filter(
                absence=absence, status__in=("approved", "executed")
            ).values_list("slot_a_id", flat=True)
        )
        absence.status = "covered" if total_slots > 0 and len(covered) >= total_slots else "pending"
        absence.save(update_fields=["status"])

    @staticmethod
    def hand_over_session(
        school: School, slot: ScheduleSlot, day: date, to_teacher: CustomUser
    ) -> Session:
        """يُسلّم حصّةَ ذلك اليوم لمعلّمٍ آخر، ويحفظ اسمَ صاحبها الأوّل.

        مشتركٌ بين الإشغال والتبديل: الأثرُ على `Session` ليومه لا على القالب
        الأسبوعيّ. ولو لم تُنشأ بعدُ أُنشئت من قالبها. والبحثُ بمجموعة الاختيار
        أيضاً: شعبةٌ تتفرّق بين مادّتين في التوقيت نفسه لها جلستان.

        ويُولَّد يومُها كاملاً أوّلاً: حصّةٌ مفردةٌ في يومٍ لم يُولَّد كانت تُبقيه
        للمدرسة كلّها بحصّةٍ واحدة («اليومُ المبتور»، 2026-09-24).
        """
        from operations.services.schedule import ScheduleService

        ScheduleService.ensure_sessions_for_date(school, day)
        session, _created = Session.objects.get_or_create(
            school=school,
            class_group=slot.class_group,
            date=day,
            start_time=slot.start_time,
            elective_group=slot.elective_group,
            defaults={
                "teacher": slot.teacher,
                "subject": slot.subject,
                "end_time": slot.end_time,
                "period_number": slot.period_number,
            },
        )
        # حصّةٌ أخذها زميلٌ تعويضاً لا يُكتب فوقها: يخسرها صاحبُها بلا إشعار.
        if session.compensatory_source.exists():
            raise ValueError("أخذ زميلٌ هذه الحصّةَ تعويضاً في هذا اليوم — لا تُسلَّم لغيره")
        # صاحبُها الأوّلُ يُكتب مرّةً: حصّةٌ سُلّمت مرّتين صاحبُها الأوّلُ أوّلُها.
        if session.original_teacher_id is None:
            session.original_teacher_id = session.teacher_id
        session.teacher = to_teacher
        session.save(update_fields=["teacher", "original_teacher"])
        return session

    @staticmethod
    def cover_recipients(
        absence: TeacherAbsence, substitute: CustomUser, actor: CustomUser | None = None
    ) -> list[CustomUser]:
        """من يُبلَّغ بالتغطية (قرارُ المالك 2026-09-23): المعلّمان، ومنسّقا
        قسمَيهما، والنائبُ الأكاديميّ، والمدير، والمطوّر. ومن قرّر لا يُبلَّغ بما فعل."""
        from core.developer_access import DEVELOPERS_GROUP
        from core.models import CustomUser, Membership

        school = absence.school
        people = {absence.teacher_id, substitute.id}
        for teacher in (absence.teacher, substitute):
            dept = teacher.department_obj
            if dept and dept.head_id:
                people.add(dept.head_id)
        members = Membership.objects.filter(school=school, is_active=True, user__is_active=True)
        people |= set(
            members.filter(role__name__in=("vice_academic", "principal")).values_list(
                "user_id", flat=True
            )
        )
        people |= set(
            members.filter(
                models.Q(user__is_superuser=True)
                | models.Q(user__groups__name__iexact=DEVELOPERS_GROUP)
            ).values_list("user_id", flat=True)
        )
        if actor is not None:
            people.discard(actor.id)
        return list(CustomUser.objects.filter(id__in=people, is_active=True))

    @staticmethod
    def _notify_cover(assignment: SubstituteAssignment, actor: CustomUser | None = None) -> None:
        """إشعارُ الإشغال — يفشل بصمتٍ إن تعطّل نظامُ الإشعارات، ولا يُسقط التعيين."""
        from django.utils.formats import date_format

        absence = assignment.absence
        slot = assignment.slot
        substitute = assignment.substitute
        when = date_format(absence.date, "l j F")
        title = f"إشغال: {substitute.full_name} عن {absence.teacher.full_name}"
        body = (
            f"الحصّة {slot.period_number} · {slot.subject or '—'} · {slot.class_group} — {when}. "
            f"كلّفه {assignment.assigned_by.full_name if assignment.assigned_by else 'الإدارة'}."
        )
        try:
            from notifications.hub import NotificationHub

            NotificationHub.dispatch(
                event_type="teacher_cover",
                school=absence.school,
                recipients=SubstituteService.cover_recipients(absence, substitute, actor),
                title=title,
                body=body,
                related_url=f"/teacher/absences/{absence.id}/",
                related_object_id=str(assignment.id),
                sent_by=actor,
            )
        except Exception as exc:
            logger.warning("SubstituteService._notify_cover failed [%s]: %s", assignment.pk, exc)

    @staticmethod
    def cover_session_ids(sessions: Iterable[Session]) -> set:
        """معرّفاتُ ما كان من حصص اليوم إشغالاً — تمييزاً له عن التبديل.

        كلاهما يكتب `original_teacher`، فالعلامةُ وحدَها لا تفرّق بينهما؛ والفرقُ
        في وجود تعيين بديلٍ للحصّة نفسها. استعلامٌ واحدٌ للقائمة كلّها.
        """
        moved = [s for s in sessions if s.original_teacher_id]
        if not moved:
            return set()
        keys = set(
            SubstituteAssignment.objects.filter(
                substitute_id__in={s.teacher_id for s in moved},
                absence__date__in={s.date for s in moved},
                status__in=("assigned", "confirmed"),
            ).values_list(
                "substitute_id", "absence__date", "slot__class_group_id", "slot__start_time"
            )
        )
        return {
            s.id for s in moved if (s.teacher_id, s.date, s.class_group_id, s.start_time) in keys
        }

    @staticmethod
    def moved_marks(sessions: list[Session]) -> dict[str, set]:
        """علامتا «حصصي اليوم»: ما كان إشغالاً وما كان تعويضاً — والباقي تبديل.

        ثلاثتُها تكتب `original_teacher`؛ والتعويضُ حصّةُ زميلٍ أخذها صاحبُه بموافقته
        (2026-09-24)، فيُعرف بسجلّه لا بعلامة الحصّة.
        """
        from operations.services.compensatory import CompensatoryService

        return {
            "cover_ids": SubstituteService.cover_session_ids(sessions),
            "comp_ids": CompensatoryService.session_ids(sessions),
        }

    @staticmethod
    def _date_to_day(date: date) -> int:
        mapping = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}
        return mapping.get(date.weekday(), -1)

    @staticmethod
    def get_substitute_report(school: School, date_from: date, date_to: date) -> QuerySet:
        """تقرير الحصص البديلة في فترة"""
        return (
            SubstituteAssignment.objects.filter(
                school=school, absence__date__range=(date_from, date_to)
            )
            .select_related("substitute", "absence__teacher", "slot__class_group", "slot__subject")
            .order_by("absence__date", "slot__period_number")
        )
