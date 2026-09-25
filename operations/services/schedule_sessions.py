"""operations/services/schedule_sessions.py — توليدُ الجلسات من الجدول ومزامنتُها.

مقطعٌ من `ScheduleService` (البند 8، الخطوة 2): يُركَّب في `schedule.py`.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import QuerySet

from core.academic_calendar import (
    academic_year_for_school,
)
from operations.models import (
    ScheduleSlot,
    Session,
)
from operations.school_days import SchoolDays

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import School


class ScheduleSessionsMixin:
    # ──────────────────────────────────────────────────────────
    # نظام التوليد التلقائي — يعمل بدون Celery
    # ──────────────────────────────────────────────────────────

    # تحويل يوم Python → يوم المدرسة القطرية (0=أحد … 4=خميس)
    _PY_TO_QATAR = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}  # Sun=6→0, Mon=0→1 …

    @staticmethod
    def _get_week_bounds(target_date: date) -> tuple[date, date]:
        """
        حساب حدود الأسبوع المدرسي (أحد → خميس) الذي يحتوي التاريخ.

        إذا التاريخ يوم جمعة أو سبت → يرجع الأسبوع القادم.
        """
        from datetime import timedelta

        wd = target_date.weekday()  # Mon=0 … Sun=6

        if wd == 4:  # Friday → الأسبوع القادم (الأحد)
            sunday = target_date + timedelta(days=2)
        elif wd == 5:  # Saturday → الأسبوع القادم (الأحد)
            sunday = target_date + timedelta(days=1)
        else:
            # نحسب كم يوم للرجوع إلى الأحد
            # Sun=6→0, Mon=0→1, Tue=1→2, Wed=2→3, Thu=3→4
            days_since_sun = (wd - 6) % 7  # Sun=0, Mon=1, Tue=2 …
            sunday = target_date - timedelta(days=days_since_sun)

        thursday = sunday + timedelta(days=4)
        return sunday, thursday

    @classmethod
    def ensure_sessions_for_date(
        cls,
        school: School,
        target_date: date,
        academic_year: str | None = None,
    ) -> int:
        """
        تأكد من وجود حصص لأسبوع التاريخ المطلوب — ولّدها إن لم تكن موجودة.

        - تولّد أيّامَ الدراسة من الأسبوع (أحد → خميس) دفعة واحدة، وتتخطّى
          إجازاتِ الطلبة في تقويم الوزارة (`operations.school_days`)
        - تستخدم bulk_create(ignore_conflicts=True) للأداء
        - idempotent: آمنة للاستدعاء المتكرر بدون تكرار
        - لا تعتمد على Celery — تعمل عند الطلب

        Returns: عدد الحصص المُنشأة (0 إذا كانت موجودة مسبقاً).
        """
        # عامُ *التاريخ* لا عامُ اليوم: شاشةٌ فُتحت بتاريخٍ من عامٍ مضى (تقرير،
        # كشفُ حضور تاريخيّ) كانت تُولَّد له حصصٌ من جدول العام الجاري، فتظهر
        # فيه شُعبٌ ومعلّمون لا صلة لهم بذلك الأسبوع.
        academic_year = academic_year or academic_year_for_school(school, on=target_date)
        from datetime import timedelta

        from django.db.models import Count

        week_sun, week_thu = cls._get_week_bounds(target_date)

        # ── فحص سريع: أي أيام في هذا الأسبوع لديها حصص؟ ──
        # جلساتُ عامٍ آخرَ لا تُعَدّ: الأسبوعُ الأوّل من 2026-2027 وُلّد على الإنتاج
        # من شُعب 2025-2026 قبل اعتماد الجدول الجديد، فرآه هذا الفحصُ «كاملاً»
        # وبقيت 845 جلسةً لعامٍ منقضٍ أسبوعاً كاملاً.
        existing = dict(
            Session.objects.filter(
                school=school,
                date__range=(week_sun, week_thu),
                class_group__academic_year=academic_year,
            )
            .order_by()
            .values_list("date")
            .annotate(n=Count("id"))
        )

        # حساب الأيام الناقصة (أحد=0 … خميس=4)
        all_days = [week_sun + timedelta(days=i) for i in range(5)]
        missing_days = [d for d in all_days if d not in existing]

        if not missing_days:
            return 0  # الأسبوع كامل — لا شيء للفعل

        # ── «اليومُ المبتور» ──
        # يومٌ فيه حصّةٌ واحدةٌ كان يُعدّ مولَّداً: تبديلٌ أو إشغالٌ أو تعويضٌ لتاريخٍ
        # في أسبوعٍ لم يُولَّد يُنشئ حصّتَه وحدها، فيبقى اليومُ للمدرسة كلّها بحصّةٍ
        # واحدة ولا يُكمَل أبداً (ثبت بالتجربة 2026-09-24: 1 بدل 176). وحالُه أنّ
        # أسبوعَه لم يُولَّد، فبقيّةُ أيّامه فارغة — أي أنّه يقع هنا لا في الفحص السريع.
        # فأيّامُ الأسبوع التي فيها حصصٌ تُكمَل مع الفارغة من قراءة الخطّة نفسها،
        # و`ignore_conflicts` يرفض ما وُجد منها — ولو بُدّل معلّمُه. والكاتبون أنفسُهم
        # يولّدون يومَهم أوّلاً (`hand_over_session`، التعويض)، فلا يُبتَر يومٌ جديد.
        partial_days = [d for d in all_days if d in existing]

        # ── يومُ إجازةِ الطلبة ليس يومَ حصص ──
        # كانت الإجازةُ الرسميّةُ يومَ ثلاثاء تُولَّد لها حصصُ الجدول كلُّها ما دام
        # أحدٌ فتح شاشةً في أسبوعها، فتظهر للمعلّم وفي كشف الحصص حصصاً تنتظر الرصد.
        # والتقويمُ يُقرأ بعد الفحص السريع لا قبله: يومُ الإجازة لا يصير «موجوداً»،
        # فأسبوعُه وحدَه يدفع استعلاماً ثانياً — واحداً للأسبوع كلّه.
        school_days = SchoolDays(school, week_sun, week_thu)
        missing_days = [d for d in missing_days if d in school_days]
        if not missing_days:
            return 0  # أسبوعُ إجازة: لا يُقرأ الجدول أصلاً
        partial_days = [d for d in partial_days if d in school_days]

        # ── جلب ScheduleSlots لكل الأيام الناقصة ──
        missing_qatar_days = []
        day_map = {}  # qatar_day → actual_date
        for d in missing_days + partial_days:
            qatar_day = cls._PY_TO_QATAR.get(d.weekday(), -1)
            if qatar_day >= 0:
                missing_qatar_days.append(qatar_day)
                day_map[qatar_day] = d

        if not missing_qatar_days:
            return 0

        slots = ScheduleSlot.objects.filter(
            school=school,
            day_of_week__in=missing_qatar_days,
            academic_year=academic_year,
            is_active=True,
        ).select_related("teacher", "class_group", "subject")

        # ── بناء Session objects دفعة واحدة ──
        sessions_to_create = []
        for slot in slots:
            actual_date = day_map.get(slot.day_of_week)
            if not actual_date:
                continue
            sessions_to_create.append(
                Session(
                    school=school,
                    teacher=slot.teacher,
                    class_group=slot.class_group,
                    subject=slot.subject,
                    date=actual_date,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    period_number=slot.period_number,
                    status="scheduled",
                    elective_group=slot.elective_group,
                )
            )

        if not sessions_to_create:
            return 0

        # bulk_create مع ignore_conflicts — يتجاهل أي تكرار بسبب UniqueConstraint.
        # وحين يُكمَل يومٌ ناقص فالعددُ فرقُ ما قبلُ وما بعدُ: تُرفض فيه الموجودةُ
        # صامتةً، و`bulk_create` يُعيد ما أُرسل لا ما أُدرج.
        if partial_days:
            filled = Session.objects.filter(school=school, date__in=list(day_map.values()))
            before = filled.count()
            Session.objects.bulk_create(sessions_to_create, ignore_conflicts=True)
            count = filled.count() - before
        else:
            count = len(Session.objects.bulk_create(sessions_to_create, ignore_conflicts=True))

        if count > 0:
            logger.info(
                "ensure_sessions: generated %d sessions for %s (week %s → %s)",
                count,
                school.name,
                week_sun,
                week_thu,
            )
        return count

    @staticmethod
    def _untouched(sessions: QuerySet[Session]) -> QuerySet[Session]:
        """ما لم يمسّه أحدٌ من الجلسات — وحدَه يُحذف حين لا يبقى له مكان.

        مجدولةٌ بلا حضور، ولا خروجٍ منها ولا مخالفةٍ فيها، ولم يُبدَّل معلّمُها ولم
        تُنشأ تعويضاً. فحذفُ الجلسة يمحو معها سجلَّ الخروج، ويقطع المخالفةَ عن
        مادّتها، ويترك التعويضَ المعتمَدَ بلا حصّة.
        """
        return sessions.filter(
            status="scheduled",
            attendances__isnull=True,
            class_exits__isnull=True,
            infractions__isnull=True,
            original_teacher__isnull=True,
            compensatory_source__isnull=True,
        )

    @classmethod
    @transaction.atomic
    def resync_sessions_for_date(
        cls,
        school: School,
        target_date: date,
        academic_year: str | None = None,
        school_days: SchoolDays | None = None,
    ) -> dict[str, int]:
        """مصالحةُ جلسات يومٍ مع الجدول النشط — بعد اعتماد جدولٍ جديد.

        `ensure_sessions_for_date` تملأ الفراغ ولا تصحّح: يومٌ فيه جلساتٌ من
        جدولٍ سابق (أو عامٍ سابق) يبقى كما هو. هنا:
          - تُحذف الجلساتُ التي لا تطابق حصّةً نشطة (المعلّم، الشعبة، الوقت، المادّة)
            **بشرط** ألّا يكون أحدٌ قد مسّها (`_untouched`) — وما مُسَّ يُبقى ويُعَدّ.
          - تُنشأ الجلساتُ الناقصة من الحصص النشطة بمجموعة الاختيار.
          - ويومُ إجازة الطلبة لا حصّةَ نشطةً فيه: لا يُنشأ فيه شيء، وجلساتُه كلُّها
            لا تطابق.

        `school_days` لمن يصالح أيّاماً متتالية: نافذةٌ تشمل اليوم، تُقرأ إجازاتُها
        مرّةً للأيّام كلّها.
        Returns: {"deleted", "created", "kept"}.
        """
        qatar_day = cls._PY_TO_QATAR.get(target_date.weekday())
        if qatar_day is None:
            return {"deleted": 0, "created": 0, "kept": 0}
        if school_days is None:
            school_days = SchoolDays(school, target_date, target_date)

        def identity(row: Session | ScheduleSlot) -> tuple[Any, ...]:
            # المادّةُ جزءٌ من الهويّة: معلّمٌ ذاتُه في الشعبة والحصّة نفسِها تبدّلت مادّتُه بين
            # توليدَين (3 من 869 على الإنتاج 2026-09-25) كانت جلستُه «تطابق» فتبقى بمادّةٍ قديمة.
            return (row.teacher_id, row.class_group_id, row.start_time, row.subject_id)

        wanted: dict[tuple[Any, ...], ScheduleSlot] = {}
        if target_date in school_days:
            # نفسُ سبب ensure_sessions_for_date: عامُ التاريخ لا عامُ اليوم.
            academic_year = academic_year or academic_year_for_school(school, on=target_date)
            slots = ScheduleSlot.objects.filter(
                school=school, academic_year=academic_year, day_of_week=qatar_day, is_active=True
            ).select_related("teacher", "class_group", "subject")
            wanted = {identity(s): s for s in slots}

        existing = list(
            Session.objects.filter(school=school, date=target_date).only(
                "teacher_id", "class_group_id", "start_time", "subject_id"
            )
        )
        have = {identity(s) for s in existing}
        stale = [s.id for s in existing if identity(s) not in wanted]
        deletable = (
            list(cls._untouched(Session.objects.filter(id__in=stale)).values_list("id", flat=True))
            if stale
            else []
        )
        kept = len(stale) - len(deletable)
        deleted = (
            Session.objects.filter(id__in=deletable).delete()[1].get(Session._meta.label, 0)
            if deletable
            else 0
        )

        to_create = [
            Session(
                school=school,
                teacher=slot.teacher,
                class_group=slot.class_group,
                subject=slot.subject,
                date=target_date,
                start_time=slot.start_time,
                end_time=slot.end_time,
                period_number=slot.period_number,
                status="scheduled",
                elective_group=slot.elective_group,
            )
            for key, slot in wanted.items()
            if key not in have
        ]
        Session.objects.bulk_create(to_create, ignore_conflicts=True)
        if deleted or to_create:
            logger.info(
                "resync_sessions %s %s: deleted=%d created=%d kept=%d",
                school.name,
                target_date,
                deleted,
                len(to_create),
                kept,
            )
        return {"deleted": deleted, "created": len(to_create), "kept": kept}

    @classmethod
    def resync_current_week(
        cls, school: School, academic_year: str | None = None
    ) -> dict[str, int]:
        """مصالحةُ أيّام الأسبوع الجاري (الأحد → الخميس) — تُستدعى عند الاعتماد."""
        from django.utils import timezone

        week_sun, week_thu = cls._get_week_bounds(timezone.localdate())
        # كلُّ يومٍ في معاملته (`resync_sessions_for_date`) كما كان — لا معاملةٌ
        # خارجيّةٌ تزيد نقطةَ حفظٍ في مسار الاعتماد.
        return cls._resync_days(school, week_sun, week_thu, academic_year, generated=None)

    @classmethod
    def future_weeks_start(cls, today: date) -> date:
        """أحدُ الأسبوع الذي بعد ما يُصالحه الاعتمادُ في الطلب (SCH-08).

        `resync_current_week` تصالح الأحدَ إلى الخميس من `_get_week_bounds(اليوم)` — وهي تُعيد
        الأسبوعَ القادمَ يومَي الجمعة والسبت. فما بعده يبدأ من خميسه + ثلاثة أيّام: لا فجوةَ
        بين المصالحتين ولا تكرار.
        """
        from datetime import timedelta

        return cls._get_week_bounds(today)[1] + timedelta(days=3)

    @classmethod
    def resync_future_weeks(cls, school: School, academic_year: str | None = None) -> dict:
        """مصالحةُ الأسابيع المولَّدة سلفاً بعد أسبوع الاعتماد — عملُ الخلفيّة لا الطلب.

        الاعتمادُ يصالح الأسبوعَ الجاريَ وحدَه: كلفةُ اليوم نحوُ مئةٍ وستٍّ وسبعين حصّةً تُحذف
        وتُنشأ، فكلُّ أسبوعٍ إضافيٍّ يزيد زمنَ الطلب، وحارسُ عدّ الاستعلامات يُقرّ بذلك. ومن
        غير هذا تبقى أيّامُ الأسابيع القادمة المولَّدة على الجدول القديم.
        """
        from django.utils import timezone

        start = cls.future_weeks_start(timezone.localdate())
        last = (
            Session.objects.filter(school=school, date__gte=start)
            .order_by("-date")
            .values_list("date", flat=True)
            .first()
        )
        if last is None:
            return {"deleted": 0, "created": 0, "kept": 0}
        return cls.resync_sessions_for_range(school, start, last, academic_year)

    @classmethod
    @transaction.atomic
    def resync_sessions_for_range(
        cls,
        school: School,
        start: date,
        end: date,
        academic_year: str | None = None,
        generated_only: bool = True,
    ) -> dict[str, int]:
        """مصالحةُ أيّام الدراسة في [start, end] مع الخطّة النشطة — واجهةٌ عامّة.

        لمن يغيّر الخطّةَ (`ScheduleSlot`) مباشرةً بعد أن وُلّدت أيّامُها: تبديلٌ
        دائمٌ بين معلّمَين، أو تصحيحُ حصّةٍ مزدوجة. فتلك التعديلاتُ لا تمسّ حصصَ
        الأيّام المولَّدة، فتبقى على الخطّة القديمة. ولكلّ يومٍ حكمُ
        `resync_sessions_for_date`: يُحذف ما لم يعد يطابق ولم يمسّه أحد، ويُنشأ
        الناقص، ويُبقى ما فيه حضورٌ أو خروجٌ أو مخالفةٌ أو تبديلٌ أو تعويض.

        و`generated_only` (الافتراض): الأيّامُ المولَّدةُ وحدها — فيومٌ لم يُولَّد
        يُولَّد لاحقاً من الخطّة الجديدة أصلاً، ولا يُولَّد مستقبلٌ بعيدٌ هنا بلا
        داعٍ. والمعاملةُ واحدةٌ للمدى كلّه: يُصالَح كلُّه أو لا شيء منه.
        Returns: {"deleted", "created", "kept"}.
        """
        if end < start:
            raise ValueError("نهايةُ المدى قبل بدايته")
        generated = (
            set(
                Session.objects.filter(school=school, date__range=(start, end))
                .values_list("date", flat=True)
                .distinct()
            )
            if generated_only
            else None
        )
        return cls._resync_days(school, start, end, academic_year, generated)

    @classmethod
    def _resync_days(
        cls,
        school: School,
        start: date,
        end: date,
        academic_year: str | None,
        generated: set[date] | None,
    ) -> dict[str, int]:
        """حلقةُ المصالحة: أيّامُ الدراسة في المدى، أو ما في `generated` منها وحده."""
        from datetime import timedelta

        school_days = SchoolDays(school, start, end)
        totals = {"deleted": 0, "created": 0, "kept": 0}
        day = start
        while day <= end:
            if day.weekday() in cls._PY_TO_QATAR and (generated is None or day in generated):
                r = cls.resync_sessions_for_date(school, day, academic_year, school_days)
                for k in totals:
                    totals[k] += r[k]
            day += timedelta(days=1)
        return totals

    @classmethod
    def clear_holiday_sessions(cls, school: School, start: date, end: date) -> dict[str, int]:
        """جلساتُ أيّام إجازة الطلبة في [start, end]: يُحذف ما لم يُمسّ، ويُعَدّ الباقي.

        تُستدعى حين تُحفظ إجازةٌ في التقويم: الإجازةُ الطارئةُ تُعلَن بعد أن وُلّد
        أسبوعُها، والتوليدُ لا يمحو ما أنشأ. وهي مصالحةُ تلك الأيّام بجدولها الفارغ،
        فالحكمُ حكمُ `resync_sessions_for_date` لا حكمٌ ثانٍ. وأيّامُ الدراسة في المدى
        لا تُمَسّ — فإجازةُ الموظفين وحدَهم تمرّ بلا أثر.

        والإجازةُ المستقبليّةُ لا جلساتَ لها في الغالب: استعلامٌ واحدٌ يكفيها.
        Returns: {"deleted", "kept"}.
        """
        from datetime import timedelta

        totals = {"deleted": 0, "kept": 0}
        if not Session.objects.filter(school=school, date__range=(start, end)).exists():
            return totals

        school_days = SchoolDays(school, start, end)
        day = start
        with transaction.atomic():
            while day <= end:
                if day.weekday() in cls._PY_TO_QATAR and day not in school_days:
                    r = cls.resync_sessions_for_date(school, day, school_days=school_days)
                    for k in totals:
                        totals[k] += r[k]
                day += timedelta(days=1)
        if totals["deleted"] or totals["kept"]:
            logger.info(
                "clear_holiday_sessions %s %s → %s: deleted=%d kept=%d",
                school.name,
                start,
                end,
                totals["deleted"],
                totals["kept"],
            )
        return totals

    @classmethod
    def ensure_sessions_for_range(
        cls,
        school: School,
        start_date: date,
        end_date: date,
    ) -> int:
        """
        تأكد من وجود حصص لكل الأسابيع في النطاق المحدد.
        مفيد للتقارير الشهرية والتحليلات.
        """
        from datetime import timedelta

        total = 0
        seen_weeks: set[date] = set()
        current = start_date

        while current <= end_date:
            week_sun, _ = cls._get_week_bounds(current)
            if week_sun not in seen_weeks:
                total += cls.ensure_sessions_for_date(school, current)
                seen_weeks.add(week_sun)
            current += timedelta(days=7)

        return total

    # Alias للتوافق مع الكود القديم
    @classmethod
    def ensure_today_sessions(cls, school: School) -> int:
        """Alias — يستدعي ensure_sessions_for_date لتاريخ اليوم."""
        from django.utils import timezone

        return cls.ensure_sessions_for_date(school, timezone.localdate())
