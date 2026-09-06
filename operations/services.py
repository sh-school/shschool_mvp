from __future__ import annotations

import logging
from collections import Counter
from datetime import date
from itertools import groupby
from typing import TYPE_CHECKING

from django.db import models, transaction
from django.db.models import Count, QuerySet

from core.academic_calendar import (
    AcademicCalendar,
    academic_year_for_school,
    academic_year_window,
)
from core.models import StudentEnrollment
from core.models.academic import grade_order
from operations.departments import (
    department_of_subject,
    derived_department,
    is_fill_subject,
    registered_departments,
)
from operations.models import (
    AbsenceAlert,
    CompensatorySession,
    FreeSlotRegistry,
    ScheduleGeneration,
    ScheduleSlot,
    Session,
    StudentAttendance,
    SubjectClassAssignment,
    SubstituteAssignment,
    TeacherAbsence,
    TeacherExemption,
    TeacherSwap,
    TimeSlotConfig,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import ClassGroup, CustomUser, School


NEWLINE = chr(10)


class AttendanceService:
    @staticmethod
    @transaction.atomic
    def mark_attendance(
        session: Session,
        student: CustomUser,
        status: str,
        excuse_type: str = "",
        excuse_notes: str = "",
        marked_by: CustomUser | None = None,
    ) -> tuple:
        att, created = StudentAttendance.objects.update_or_create(
            session=session,
            student=student,
            defaults={
                "school": session.school,
                "status": status,
                "excuse_type": excuse_type,
                "excuse_notes": excuse_notes,
                "marked_by": marked_by,
            },
        )
        # Check absence threshold
        if status == "absent":
            AttendanceService.check_absence_threshold(student, session.school)
        return att, created

    @staticmethod
    @transaction.atomic
    def bulk_mark_all_present(session: Session, marked_by: CustomUser | None = None) -> int:
        students = StudentEnrollment.objects.filter(
            class_group=session.class_group, is_active=True
        ).select_related("student")

        records = []
        for enrollment in students:
            records.append(
                StudentAttendance(
                    session=session,
                    student=enrollment.student,
                    school=session.school,
                    status="present",
                    marked_by=marked_by,
                )
            )
        StudentAttendance.objects.bulk_create(records, ignore_conflicts=True)
        session.status = "in_progress"
        session.save(update_fields=["status"])
        return len(records)

    @staticmethod
    @transaction.atomic
    def complete_session(session: Session) -> None:
        session.status = "completed"
        session.save(update_fields=["status"])

    # ── إعداد السنة الدراسية (المادة 7 من قانون 25/2001 المعدّل) ─
    # عتبةٌ تشغيلية من وضعنا، لا سندَ لها في نصٍّ رسميّ — راجع
    # `check_absence_threshold` و`absence_policy`. والوحدة هنا حصصٌ لا أيام.
    SCHOOL_YEAR_DAYS = 190
    ABSENCE_THRESHOLD_PCT = 0.10

    #: يُنذَر حين يبقى هذا العدد أو أقلّ قبل العتبة — إنذارٌ يسبق الوقوع.
    GATE_WARNING_MARGIN_DAYS = 2

    @staticmethod
    def check_absence_threshold(student: CustomUser, school: School, on=None) -> None:
        """يُنذر عند اقتراب كل عتبةٍ من عتبات «سياسة تقييم الطلبة».

        كانت هذه الدالّة تُنذر عند «10٪ من أيام الدراسة» وتنسبها إلى المادة 7
        من قانون التعليم الإلزامي 25/2001. ونصّ القانون لا يذكر نسبةً ولا عدد
        أيام. وكانت الرسالة تقول لوليّ الأمر «تجاوز ابنكم **العتبة القانونية**»
        — ادّعاءٌ يصل إلى بيتٍ حقيقيّ.

        والعتبات في الدليل الوزاريّ (القرار 22/2015): سبعةُ أيام تمدرس ثم عشرة
        ثم ثلاثة عشر ثم خمسة عشر للصفوف ٤–١١، وعشرةٌ ثم خمسة عشر للثاني عشر.

        وثلاثة فروقٍ عمليّة عن القديم:

        - تُعدّ **أيام تمدرس** لا حصصاً — والفرق سبعة أضعاف بسبع حصصٍ في اليوم.
        - تنبيهٌ **لكل عتبة**. وكان التنبيه واحداً للعام كلّه، فمن تجاوز الأولى
          لم يُنذَر عند التي بعدها قطّ.
        - **إنذارٌ قبل الوقوع** بيومين، لا إعلامٌ بعده.

        ولا تحجب هذه الدالّة شيئاً. قرار الحرمان لإدارة المدرسة.

        `on` للاختبار وللمعالجة بأثرٍ رجعيّ — لا يُمرَّر في الاستعمال العاديّ.
        """
        from core.models import StudentEnrollment
        from operations.absence_policy import gates_for
        from operations.absence_standing import standing_for

        enrollment = (
            StudentEnrollment.objects.filter(student=student, is_active=True)
            .select_related("class_group")
            .first()
        )
        grade = enrollment.class_group.grade if enrollment else None
        if not gates_for(grade):
            # الصفوف ١–٣ لها قسمٌ مستقلّ في الدليل لم يُشفَّر — فلا إنذار.
            # وطالبٌ بلا تسجيلٍ نشط يقع هنا أيضاً، فيفقد إنذاراته كلّها. وذاك
            # نقصٌ في البيانات لا حكمٌ من السياسة — فيُسجَّل كي يُرى.
            if enrollment is None:
                logger.warning(
                    "check_absence_threshold: لا تسجيل نشط للطالب %s — لا إنذار غياب",
                    student.pk,
                )
            return

        standing = standing_for(student, school, grade=grade, on=on)
        window = academic_year_window(school, on)
        if window is None:
            return
        year_start, year_end = window

        margin = AttendanceService.GATE_WARNING_MARGIN_DAYS
        due = [
            gate
            for gate in standing.gates
            if standing.unexcused_days > gate.max_days
            or gate.max_days - standing.unexcused_days <= margin
        ]

        for gate in due:
            _alert, created = AbsenceAlert.objects.get_or_create(
                school=school,
                student=student,
                gate=gate.key,
                period_start=year_start,
                period_end=year_end,
                defaults={"absence_count": standing.unexcused_days, "status": "pending"},
            )
            if not created:
                continue

            crossed = standing.unexcused_days > gate.max_days
            if crossed:
                headline = f"تجاوز حدّ الغياب لدخول {gate.label}"
                detail = (
                    f"بلغ غياب ابنكم بدون عذر {standing.unexcused_days} يوماً، "
                    f"والحدّ لدخول {gate.label} هو {gate.max_days} يوماً."
                )
            else:
                remaining = gate.max_days - standing.unexcused_days
                headline = f"اقتراب من حدّ الغياب لدخول {gate.label}"
                detail = (
                    f"بلغ غياب ابنكم بدون عذر {standing.unexcused_days} يوماً، "
                    f"ويفصله {remaining} يوماً عن حدّ {gate.max_days} "
                    f"المقرّر لدخول {gate.label}."
                )
            source = "المرجع: سياسة تقييم الطلبة — وزارة التعليم والتعليم العالي."

            try:
                from notifications.hub import NotificationHub

                NotificationHub.dispatch_to_parents(
                    event_type="absence",
                    school=school,
                    student=student,
                    title=f"⚠️ {headline} — {student.full_name}",
                    body=NEWLINE.join([detail, source, "يُرجى التواصل مع المدرسة."]),
                    context={"student": student, "absence_count": standing.unexcused_days},
                    related_url=f"/operations/attendance/student/{student.pk}/",
                )
            except Exception as exc:
                logger.warning(
                    "check_absence_threshold: Hub dispatch failed [student=%s gate=%s]: %s",
                    student.pk,
                    gate.key,
                    exc,
                )

            try:
                from core.models import Membership
                from notifications.models import InAppNotification

                sw_user_ids = list(
                    Membership.objects.filter(
                        school=school, is_active=True, role__name="social_worker"
                    ).values_list("user_id", flat=True)
                )
                for sw_id in sw_user_ids:
                    InAppNotification.objects.create(
                        user_id=sw_id,
                        school=school,
                        title=f"{headline}: {student.full_name}",
                        body=f"{detail} {source}",
                        event_type="absence",
                        priority="high" if crossed else "normal",
                        related_url=f"/student-affairs/student/{student.pk}/",
                    )
            except Exception as exc:
                logger.warning(
                    "check_absence_threshold: social worker notify failed [student=%s]: %s",
                    student.pk,
                    exc,
                )

    @staticmethod
    def get_session_summary(session: Session) -> dict:
        att = StudentAttendance.objects.filter(session=session)
        total = att.count()
        present = att.filter(status="present").count()
        absent = att.filter(status="absent").count()
        late = att.filter(status="late").count()
        excused = att.filter(status="excused").count()
        pct = round(present / total * 100) if total else 0
        return {
            "total": total,
            "present": present,
            "absent": absent,
            "late": late,
            "excused": excused,
            "percentage": pct,
        }


# ─────────────────────────────────────────────
# المرحلة 2 — الجداول الذكية + نظام البديل
# ─────────────────────────────────────────────


class ScheduleService:
    # ── الجدول الأسبوعي ──────────────────────

    @staticmethod
    def period_times(
        school: School, academic_year: str | None = None, band=None, day_type: str = "regular"
    ) -> dict:
        """توقيت كل حصة — {رقم: (بداية، نهاية)} — لنطاقٍ ونوعِ يوم.

        المصدر الأوّل `TimeSlotConfig`، فهو ما تُعلنه المدرسة: جرسُ النطاق
        ليومه، ثمّ جرسُ المدرسة الافتراضيّ (بلا نطاق) ليومه، ثمّ جرسُ
        الأحد–الأربعاء. فإن لم تُعلن المدرسةُ جرساً اشتُقّ من الحصص نفسها
        بالأكثر شيوعاً لكلّ رقمٍ في أيّام ذلك النوع — لا من رقمٍ مكتوبٍ في
        الشيفرة يصير كذبةً يوم تُغيّر المدرسة توقيتها.
        """
        from collections import Counter

        academic_year = academic_year or academic_year_for_school(school)
        candidates = [(band, day_type), (None, day_type)]
        if day_type != "regular":
            candidates += [(band, "regular"), (None, "regular")]
        seen: set = set()
        for wanted_band, kind in candidates:
            if (wanted_band, kind) in seen:
                continue
            seen.add((wanted_band, kind))
            rows = TimeSlotConfig.objects.filter(school=school, day_type=kind, is_break=False)
            rows = rows.filter(band=wanted_band) if wanted_band else rows.filter(band__isnull=True)
            times = {r.period_number: (r.start_time, r.end_time) for r in rows}
            if times:
                return times

        tally: dict[int, Counter] = {}
        slots = ScheduleSlot.objects.filter(
            school=school, academic_year=academic_year, is_active=True
        )
        slots = (
            slots.filter(day_of_week=4) if day_type == "thursday" else slots.exclude(day_of_week=4)
        )
        for period, start, end in slots.values_list("period_number", "start_time", "end_time"):
            tally.setdefault(period, Counter())[(start, end)] += 1
        return {p: c.most_common(1)[0][0] for p, c in tally.items()}

    @staticmethod
    def get_weekly_schedule(
        school: School,
        teacher: CustomUser | None = None,
        class_group: ClassGroup | None = None,
        academic_year: str | None = None,
        generation=None,
    ) -> dict:
        """إرجاع الجدول الأسبوعي مرتّباً حسب اليوم والحصة.

        الشكل واحدٌ في كل الأحوال: `{يوم: {حصة: [slot, ...]}}`.

        و`generation` يُعاين مسودّةً بعينها بدل الجدول الحيّ: حصصُها مطفأةٌ
        حتّى تُعتمد فلا يجدها فلترُ `is_active` — ومن يعتمد جدولاً لم يرَه
        يعتمد رقماً لا جدولاً.

        وكان يُعيد حصّةً مفردة مع فلتر المعلّم أو الفصل، وقائمةً بلا فلتر.
        والشعبة **تكون** في حصّتين معاً حين يتفرّق طلابها بين مادّتين
        اختياريّتين في التوقيت نفسه، فكانت الثانية تُكتب فوق الأولى في
        القاموس وتختفي صامتة.

        ونوعُ الإرجاع المتبدّل فخٌّ في ذاته: قالبٌ يقرأ `slot.subject` من
        قائمةٍ لا يُخطئ — يطبع فراغاً. فوُحِّد الشكل.
        """
        academic_year = academic_year or academic_year_for_school(school)
        qs = ScheduleSlot.objects.filter(school=school, academic_year=academic_year)
        if generation is not None:
            qs = qs.filter(generation=generation)
        else:
            qs = qs.filter(is_active=True)
        # وداخلَ الخانة الواحدة ترتيبُ المدرسة: من 7/1 إلى 12/4. فخانةُ العرض
        # العامّ تحمل شعبَ المدرسة كلَّها، وبلا ترتيبٍ صريحٍ يُخرجها المحرّك
        # كيف اتّفق — فلا يجد القارئُ شعبتَه إلّا بمسحِ خمسٍ وعشرين بطاقة.
        qs = qs.select_related("teacher", "class_group", "subject").order_by(
            grade_order("class_group__grade"), "class_group__section"
        )
        if teacher:
            qs = qs.filter(teacher=teacher)
        if class_group:
            qs = qs.filter(class_group=class_group)

        grid: dict = {d: {} for d in range(5)}  # 0=أحد … 4=خميس
        for slot in qs:
            grid[slot.day_of_week].setdefault(slot.period_number, []).append(slot)
        return grid

    @staticmethod
    def get_teachers_matrix(
        school: School, academic_year: str | None = None, generation=None
    ) -> list[dict]:
        """الجدول العام: صفٌّ لكل معلّم، وخمسةُ أيامٍ في كلٍّ منها سبعُ حصص.

        هذه صيغةُ ورقة «الجدول العام للمعلمين» التي تُعلَّق في المدرسة:
        المعلّمون سطوراً، والأسبوعُ كلُّه عرضاً، وفي الخانة رمزُ الشعبة
        وحده — لأنّ خانةً عرضُها سنتيمترٌ لا تحتمل اسم مادّةٍ ولا معلّم.

        والمعلّمُ بلا حصّةٍ لا سطر له: سطرٌ فارغٌ في ورقةٍ من ستّين سطراً
        يأكل مساحةً ولا يُفيد قارئه.

        والسطورُ مرتّبةٌ بالقسم الأكاديميّ ثمّ بالاسم — فالورقةُ تُقرأ قسماً
        قسماً، ومن أراد نصاب قسمٍ وجد معلّميه متجاورين. والقسمُ مشتقٌّ من
        الحصص نفسها، انظر `operations.departments`.

        الشكل: `[{"teacher": …, "days": [[خانة × ٧] × ٥], "total": عدد,
        "department": {رمز، اسم، ترتيب}, "dept_span": امتدادُ خانة القسم}]`
        والخانةُ قائمةٌ لا حصّةٌ مفردة — والقيدُ يمنع تعدُّدها اليوم، فإن
        رُفع غداً ظهر ما فيها بدل أن يُكتب أحدهما فوق الآخر.
        """
        academic_year = academic_year or academic_year_for_school(school)
        # و`generation` يُعاين مسودّةً بدل الجدول الحيّ — كالشبكة سواءً بسواء:
        # الصفحةُ الواحدةُ صارت تعرض الورقتين، فلا تُعاين المسودّةُ في إحداهما
        # ويُعرض الحيُّ في الأخرى باسمها.
        qs = ScheduleSlot.objects.filter(school=school, academic_year=academic_year)
        qs = (
            qs.filter(generation=generation)
            if generation is not None
            else qs.filter(is_active=True)
        )
        slots = qs.select_related("teacher", "class_group", "subject").order_by(
            "teacher__full_name", "day_of_week", "period_number"
        )

        rows: dict = {}
        for slot in slots:
            row = rows.get(slot.teacher_id)
            if row is None:
                row = rows[slot.teacher_id] = {
                    "teacher": slot.teacher,
                    "days": [[[] for _ in range(7)] for _ in range(5)],
                    "total": 0,
                    "weights": Counter(),
                    "fill_weights": Counter(),
                }

            subject_name = slot.subject.name_ar if slot.subject else ""
            code = department_of_subject(subject_name, slot.class_group.grade)
            if code:
                # المادّةُ التكميليّة في دلوٍ على حدة: تُرجَّح حين لا سواها.
                bucket = "fill_weights" if is_fill_subject(subject_name) else "weights"
                row[bucket][code] += 1
            # الحصص من ١ إلى ٧، والفهرسُ من صفر. وحصّةٌ خارج المدى بيانٌ
            # معطوب لا سببَ لإسقاط الورقة كلّها من أجله.
            if 1 <= slot.period_number <= 7 and 0 <= slot.day_of_week <= 4:
                row["days"][slot.day_of_week][slot.period_number - 1].append(slot)
                row["total"] += 1

        registry = registered_departments(school)
        for teacher_id, row in rows.items():
            weights = row.pop("weights")
            fill = row.pop("fill_weights")
            row["department"] = registry.get(str(teacher_id)) or derived_department(weights, fill)

        # الاسمُ في المفتاح لأنّ `sort_order` قد يتساوى بين قسمين، فلولاه
        # تشابكت صفوفُ القسمين وانكسر عمودُ القسم الممتدّ.
        ordered = sorted(
            rows.values(),
            key=lambda r: (
                r["department"]["order"],
                r["department"]["name"],
                r["teacher"].full_name or "",
            ),
        )

        # عمودُ القسم خانةٌ واحدةٌ ممتدّةٌ على سطور معلّميه: `dept_span` عددُ
        # السطور لأوّلِ معلّمي القسم وصفرٌ لمن بعده. والاسمُ يُكتب مرّةً لا في
        # كلِّ سطر — فتكرارُه ثلاثاً وسبعين مرّةً يأكل من عرض الورقة ولا يزيد
        # قارئها علماً. والسطورُ مرتّبةٌ بالقسم قبلَه، فالمجموعةُ متّصلة.
        for _, group in groupby(ordered, key=lambda r: r["department"]["code"]):
            members = list(group)
            members[0]["dept_span"] = len(members)
            for row in members[1:]:
                row["dept_span"] = 0

        return ordered

    @staticmethod
    def _by_period(days: list) -> list:
        """المصفوفةُ باليوم ثمّ الحصّة، والورقةُ بالحصّة ثمّ اليوم: السطرُ حصّةٌ
        والعمودُ يوم. والقلبُ هنا لا في القالب — قوالبُ Django لا تفهرس بمتغيّر."""
        return [list(cells) for cells in zip(*days, strict=False)]

    @staticmethod
    def teacher_pages(
        school: School, academic_year: str | None = None, *, department=None, teacher_id=None
    ) -> list[dict]:
        """صفحاتُ جداول المعلّمين مرتّبةً بالأقسام — صفحةٌ لكلّ معلّمٍ له حصص.

        القسمُ من السجلّ الإداريّ لا من الموادّ (`registered_departments`)،
        فالورقةُ للمنسّق ورجلٌ ينتقل من قسمٍ إلى قسمٍ لأنّ جدوله تغيّر ورقةٌ لا
        تُصدَّق. ومن لا حصّةَ له لا صفحةَ له — ورقةٌ فارغةٌ لا تنفع أحداً.
        """
        rows = ScheduleService.get_teachers_matrix(school, academic_year)
        if teacher_id:
            rows = [r for r in rows if str(r["teacher"].id) == str(teacher_id)]
        elif department:
            rows = [r for r in rows if r["department"]["code"] == department]
        for row in rows:
            row["by_period"] = ScheduleService._by_period(row["days"])
        return rows

    @staticmethod
    def department_options(school: School, academic_year: str | None = None) -> list[dict]:
        """الأقسامُ التي فيها معلّمون مجدولون — للقائمة المنسدلة، بترتيب الورقة.

        من الجدول نفسه لا من جدول الأقسام وحده: قسمٌ مسجّلٌ بلا معلّمٍ مجدولٍ
        خيارٌ يفتح ورقةً فارغة، وقسمٌ مشتقٌّ لمن لا سجلَّ له لا يظهر في السجلّ.
        """
        seen: dict[str, dict] = {}
        for row in ScheduleService.get_teachers_matrix(school, academic_year):
            info = row["department"]
            seen.setdefault(
                info["code"], {"code": info["code"], "name": info["name"], "order": info["order"]}
            )
        return sorted(seen.values(), key=lambda d: (d["order"], d["name"]))

    @staticmethod
    def class_pages(school: School, academic_year: str | None = None) -> list[dict]:
        """صفحةٌ لكلّ شعبة بترتيب المدرسة: من 7/1 إلى 12/4 — وفي الخانة المادّةُ والمعلّم."""
        academic_year = academic_year or academic_year_for_school(school)
        slots = (
            ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
            .select_related("teacher", "class_group", "subject")
            .order_by(grade_order("class_group__grade"), "class_group__section")
        )
        rows: dict = {}
        for slot in slots:
            row = rows.get(slot.class_group_id)
            if row is None:
                row = rows[slot.class_group_id] = {
                    "class_group": slot.class_group,
                    "days": [[[] for _ in range(7)] for _ in range(5)],
                    "total": 0,
                }
            if 1 <= slot.period_number <= 7 and 0 <= slot.day_of_week <= 4:
                row["days"][slot.day_of_week][slot.period_number - 1].append(slot)
                row["total"] += 1
        pages = list(rows.values())
        for row in pages:
            row["by_period"] = ScheduleService._by_period(row["days"])
        return pages

    @staticmethod
    def matrix_totals(rows: list[dict], school: School, academic_year: str | None = None) -> dict:
        """مجموعُ الحصص أسفل الجدول العام، والمخطَّطُ الذي يُقاس إليه.

        في الخانة الواحدة (يومٌ وحصّة) يُعرض عددُ الحصص المنعقدة. وإلى جانبه
        يُقاس **تغطيةُ الشُّعب** لا عددُ الحصص: كم شعبةً في درسٍ حينها من
        الشُّعب التي تُسمح لها تلك الحصّة.

        والفرقُ بين المقياسين ليس تدقيقاً لفظياً: شعبةٌ ينقسم طلابها بين
        مادّتين اختياريّتين تشغل خانتين في العمود الواحد، فتستر بزيادتها
        شعبةً أخرى بلا درس — فيخرج العمودُ خمسةً وعشرين وفيه ثقب. فقياسُ
        الشُّعب يكشفه وقياسُ الحصص يخفيه.

        والمخطَّطُ في الأسبوع = الخاناتُ المسموحة لكلّ شعبة (`get_max_periods_
        for_day`: أربعٌ وثلاثون للإعدادي وخمسٌ وثلاثون للثانوي) + زيادةُ
        التوازي **من خطّة الإسناد** (`SubjectClassAssignment.parallel_group`)
        لا من الجدول المنفَّذ — وإلّا قِيس الشيءُ بنفسه فوافق دائماً.

        دالّةٌ على المصفوفة القائمة، واستعلامٌ واحدٌ للخطّة.
        """
        from operations.scheduler_constraints import get_max_periods_for_day

        counts = [[0] * 7 for _ in range(5)]
        covered: list[list[set]] = [[set() for _ in range(7)] for _ in range(5)]
        levels: dict = {}
        for row in rows:
            for day_index, day in enumerate(row["days"]):
                for period_index, cell in enumerate(day):
                    counts[day_index][period_index] += len(cell)
                    for slot in cell:
                        levels[slot.class_group_id] = slot.class_group.level_type or ""
                        covered[day_index][period_index].add(slot.class_group_id)

        days = []
        for day_index, day_counts in enumerate(counts):
            columns = []
            for period_index, count in enumerate(day_counts):
                expected = sum(
                    1
                    for level in levels.values()
                    if period_index + 1 <= get_max_periods_for_day(day_index, level)
                )
                sections = len(covered[day_index][period_index])
                columns.append(
                    {
                        "count": count,
                        "sections": sections,
                        "expected": expected,
                        "short": sections < expected,
                    }
                )
            days.append(columns)

        planned_cells = sum(
            sum(get_max_periods_for_day(day, level) for day in range(5))
            for level in levels.values()
        )
        parallel = ScheduleService.parallel_extra(school, academic_year, set(levels))
        planned = planned_cells + parallel
        total = sum(row["total"] for row in rows)

        return {
            "days": days,
            "total": total,
            "planned": planned,
            "parallel": parallel,
            "missing": max(planned - total, 0),
            "sections": len(levels),
        }

    @staticmethod
    def parallel_extra(
        school: School, academic_year: str | None = None, class_ids: set | None = None
    ) -> int:
        """الحصصُ الزائدةُ على الخانات بحكم التوازي — من الخطّة لا من الجدول.

        مادّتان في الشعبة الواحدة تحملان وسمَ التوازي نفسه تُدرَّسان في
        التوقيت ذاته لقسمَي الطلاب: الخانةُ واحدةٌ والحصصُ اثنتان. فالزيادةُ
        في المجموعة = مجموعُ حصصها ناقصَ أطولِها.
        """
        academic_year = academic_year or academic_year_for_school(school)
        qs = SubjectClassAssignment.objects.filter(
            school=school, academic_year=academic_year, is_active=True
        ).exclude(parallel_group="")
        if class_ids is not None:
            qs = qs.filter(class_group_id__in=class_ids)

        groups: dict = {}
        for class_id, group, periods in qs.values_list(
            "class_group_id", "parallel_group", "weekly_periods"
        ):
            groups.setdefault((class_id, group), []).append(periods)

        return sum(sum(periods) - max(periods) for periods in groups.values())

    @staticmethod
    def retire_past_year_slots(school: School, on=None) -> int:
        """يُطفئ كلَّ حصّةٍ نشطةٍ خارج العام الجاري — ويُعيد عددَ ما أُطفئ.

        عامٌ جديدٌ يبدأ بتاريخٍ لا بزرّ: `AcademicCalendar` يشتقّه من تقويم
        الوزارة، فيتبدّل الجوابُ ليلةَ الأوّل من سبتمبر بلا أن يلمس أحدٌ
        شيئاً. وجدولُ العام الماضي يبقى نشطاً في القاعدة كما تركه — فتصير
        في المدرسة الواحدة جداولُ عامين نشطةً معاً.

        وقد وقع هذا فعلاً: بقيت مئتان وخمسون حصّةً من 2025-2026 نشطةً بعد
        دخول 2026-2027، وتسعةٌ من معلّميها العشرة يدرّسون في العام الجديد،
        فكانوا يُرَون مشغولين في أوقاتٍ هم فيها متفرّغون.

        وهي ثابتةُ التكرار: نداؤها مرّتين لا يُطفئ شيئاً في الثانية. ولا
        تحذف — الحذفُ قرارُ `prune_schedule_slots` بيد إنسان.
        """
        return ScheduleService._retire(ScheduleSlot, school, on, "حصّة")

    @staticmethod
    def retire_past_year_assignments(school: School, on=None) -> int:
        """يُطفئ كلَّ إسنادِ مادّةٍ نشطٍ خارج العام الجاري — ويُعيد عددَ ما أُطفئ.

        والإسنادُ أصلُ الجدول لا نتيجتُه: منه يُولَّد. فإسنادُ عامٍ مضى باقٍ
        نشطاً يُدخل شُعباً منقضيةً في مصفوفة التوليد، ويُحسب في نصاب المعلّم،
        ويُرجّح معلّماً على غيره في اقتراح البديل بحكم مادّةٍ لم يعد يدرّسها.
        """
        return ScheduleService._retire(SubjectClassAssignment, school, on, "إسناداً")

    @staticmethod
    def retire_past_year_records(school: School, on=None) -> dict[str, int]:
        """الحارسُ كاملاً: الإسنادُ ثمّ الجدول — وهذا ما تنادِيه المواضعُ الثلاثة."""
        return {
            "assignments": ScheduleService.retire_past_year_assignments(school, on),
            "slots": ScheduleService.retire_past_year_slots(school, on),
        }

    # ── النسخُ المؤرشفة ─────────────────────────────────────────────
    @staticmethod
    def retained_archived_ids(school: School, academic_year: str, keep: int | None = None) -> list:
        """معرّفاتُ التوليدات المؤرشفة التي تُبقى — الأحدثُ فالأحدث بعدد `keep`.

        مصدرٌ واحدٌ لتعريف «المُبقى» يستعمله الاعتمادُ والأمرُ معاً، فلا يحذف
        أحدُهما ما يحفظه الآخر.
        """
        from django.conf import settings

        if keep is None:
            keep = int(getattr(settings, "SCHEDULE_ARCHIVE_RETENTION", 0))
        if keep <= 0:
            return []
        return list(
            ScheduleGeneration.objects.filter(
                school=school, academic_year=academic_year, status="archived"
            )
            .order_by("-generated_at")
            .values_list("id", flat=True)[:keep]
        )

    @staticmethod
    def retain_archived_generations(
        school: School, academic_year: str, keep: int | None = None
    ) -> int:
        """يحذف التوليداتِ المؤرشفةَ الزائدةَ على `keep` — وحصصُها الميّتة معها.

        القرار (2026-09-05): جدولٌ واحدٌ فقط، الحيّ. فالافتراضُ صفر: ما يُؤرشف
        يذهب عند الاعتماد التالي. والمسودّاتُ والفاشلُ خارجَ هذا كلِّه — الأولى
        عملٌ جارٍ، والثاني سجلُّ إخفاقٍ بلا حصص.

        والحذفُ يمرّ بحارس `ScheduleGenerationQuerySet`: توليدٌ له حصّةٌ حيّةٌ لا
        يُمسّ ولو كانت حالتُه «مؤرشف» — فلا يُفقد الجدولُ الحيّ نسبَه أبداً.

        يُعيد عددَ التوليدات المحذوفة.
        """
        keep_ids = ScheduleService.retained_archived_ids(school, academic_year, keep)
        stale = (
            ScheduleGeneration.objects.filter(
                school=school, academic_year=academic_year, status="archived"
            )
            .exclude(id__in=keep_ids)
            .exclude(slots__is_active=True)
            .distinct()
        )
        count = stale.count()
        if count:
            ScheduleGeneration.objects.filter(
                id__in=list(stale.values_list("id", flat=True))
            ).delete()
            logger.info(
                "retain_archived_generations: حُذف %d توليداً مؤرشفاً في %s/%s (المُبقى %d)",
                count,
                school.code,
                academic_year,
                len(keep_ids),
            )
        return count

    @staticmethod
    def _retire(model, school: School, on, noun: str) -> int:
        """الإطفاءُ المشترك — استعلامٌ واحد: `UPDATE` يُعيد عددَ ما مسّه.

        **ولا يعمل إلّا بعامٍ من التقويم.** فـ`academic_year_for_school` ترتدّ
        إلى الثابت المجمَّد حين لا يغطّي اليومَ عامٌ مبذور — والثابتُ يتقادم
        صامتاً (هو اليوم «2025-2026»). فلو أطفأنا على ذلك الجواب لأطفأنا
        جدولَ العام الجاري كلَّه في مدرسةٍ نسيت بذرَ تقويمها. حارسٌ يخطئ
        بالسكوت خيرٌ من حارسٍ يخطئ بالفعل.

        وكان عدّاً ثمّ كتابة، وهذا يمرّ في مسار الطلب مرّةً كلَّ يومٍ لكلّ
        مدرسة — فمسحُ الجدول مرّتين ليأتيَ الجوابُ صفراً في أغلب الأيام تَرَفٌ.
        """
        year = AcademicCalendar.current(school, on).year
        if year is None:
            logger.warning(
                "retire_past_year: لا عامَ في تقويم %s يغطّي اليوم — لا يُطفأ شيء",
                school.name,
            )
            return 0

        count = (
            model.objects.past_years(school, year=year.name)
            .filter(is_active=True)
            .update(is_active=False)
        )
        if count:
            logger.info(
                "retire_past_year: أُطفئ %d %s خارج عام %s في %s",
                count,
                noun,
                year.name,
                school.name,
            )
        return count

    @staticmethod
    def detect_conflicts(school: School, academic_year: str | None = None) -> list:
        """كشف التعارضات في الجدول"""
        academic_year = academic_year or academic_year_for_school(school)
        conflicts: list = []

        # تعارض المعلم: نفس المعلم في نفس اليوم والحصة
        teacher_dups = (
            ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
            .values("teacher", "day_of_week", "period_number")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        for dup in teacher_dups:
            slots = (
                ScheduleSlot.objects.live(school, year=academic_year)
                .filter(
                    teacher_id=dup["teacher"],
                    day_of_week=dup["day_of_week"],
                    period_number=dup["period_number"],
                )
                .select_related("teacher", "class_group")
            )
            conflicts.append(
                {
                    "type": "teacher",
                    "message": f"تعارض معلم: {slots[0].teacher.full_name} — {slots[0].day_name} ح{dup['period_number']}",
                    "slots": list(slots),
                }
            )

        # تعارض الفصل: نفس الفصل في نفس اليوم والحصة
        #
        # و`elective_group` جزءٌ من المفتاح: الشعبةُ المنقسمةُ تأخذ مادّتين في
        # التوقيت نفسه لقسمَي طلابها — كالفنون والتكنولوجيا في 11/1 — وذلك
        # توازٍ لا تعارض. وبدونه كان الكشفُ يُنذر بثمانية «تعارضات» كلُّها
        # حصصٌ مقصودةٌ يحرسها القيدُ الفريدُ في القاعدة نفسِها.
        class_dups = (
            ScheduleSlot.objects.filter(school=school, academic_year=academic_year, is_active=True)
            .values("class_group", "day_of_week", "period_number", "elective_group")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        for dup in class_dups:
            slots = (
                ScheduleSlot.objects.live(school, year=academic_year)
                .filter(
                    class_group_id=dup["class_group"],
                    day_of_week=dup["day_of_week"],
                    period_number=dup["period_number"],
                    elective_group=dup["elective_group"],
                )
                .select_related("teacher", "class_group")
            )
            conflicts.append(
                {
                    "type": "class",
                    "message": f"تعارض فصل: {slots[0].class_group} — {slots[0].day_name} ح{dup['period_number']}",
                    "slots": list(slots),
                }
            )

        return conflicts

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

    @staticmethod
    def ensure_sessions_for_date(
        school: School,
        target_date: date,
        academic_year: str | None = None,
    ) -> int:
        """
        تأكد من وجود حصص لأسبوع التاريخ المطلوب — ولّدها إن لم تكن موجودة.

        - تولّد الأسبوع كامل (أحد → خميس) دفعة واحدة
        - تستخدم bulk_create(ignore_conflicts=True) للأداء
        - idempotent: آمنة للاستدعاء المتكرر بدون تكرار
        - لا تعتمد على Celery — تعمل عند الطلب

        Returns: عدد الحصص المُنشأة (0 إذا كانت موجودة مسبقاً).
        """
        academic_year = academic_year or academic_year_for_school(school)
        from datetime import timedelta

        week_sun, week_thu = ScheduleService._get_week_bounds(target_date)

        # ── فحص سريع: أي أيام في هذا الأسبوع لديها حصص؟ ──
        # جلساتُ عامٍ آخرَ لا تُعَدّ: الأسبوعُ الأوّل من 2026-2027 وُلّد على الإنتاج
        # من شُعب 2025-2026 قبل اعتماد الجدول الجديد، فرآه هذا الفحصُ «كاملاً»
        # وبقيت 845 جلسةً لعامٍ منقضٍ أسبوعاً كاملاً.
        existing_days = set(
            Session.objects.filter(
                school=school,
                date__range=(week_sun, week_thu),
                class_group__academic_year=academic_year,
            )
            .values_list("date", flat=True)
            .distinct()
        )

        # حساب الأيام الناقصة (أحد=0 … خميس=4)
        all_days = [week_sun + timedelta(days=i) for i in range(5)]
        missing_days = [d for d in all_days if d not in existing_days]

        if not missing_days:
            return 0  # الأسبوع كامل — لا شيء للفعل

        # ── جلب ScheduleSlots لكل الأيام الناقصة ──
        missing_qatar_days = []
        day_map = {}  # qatar_day → actual_date
        for d in missing_days:
            qatar_day = ScheduleService._PY_TO_QATAR.get(d.weekday(), -1)
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
                    status="scheduled",
                    elective_group=slot.elective_group,
                )
            )

        if not sessions_to_create:
            return 0

        # bulk_create مع ignore_conflicts — يتجاهل أي تكرار بسبب UniqueConstraint
        created = Session.objects.bulk_create(sessions_to_create, ignore_conflicts=True)
        count = len(created)

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
    @transaction.atomic
    def resync_sessions_for_date(
        school: School,
        target_date: date,
        academic_year: str | None = None,
    ) -> dict[str, int]:
        """مصالحةُ جلسات يومٍ مع الجدول النشط — بعد اعتماد جدولٍ جديد.

        `ensure_sessions_for_date` تملأ الفراغ ولا تصحّح: يومٌ فيه جلساتٌ من
        جدولٍ سابق (أو عامٍ سابق) يبقى كما هو. هنا:
          - تُحذف الجلساتُ التي لا تطابق حصّةً نشطة (المعلّم، الشعبة، الوقت)
            **بشرط** أنّها `scheduled` وبلا سجلّ حضور — ما مُسَّ يُبقى ويُعَدّ.
          - تُنشأ الجلساتُ الناقصة من الحصص النشطة بمجموعة الاختيار.
        Returns: {"deleted", "created", "kept"}.
        """
        from django.db.models import Count

        academic_year = academic_year or academic_year_for_school(school)
        qatar_day = ScheduleService._PY_TO_QATAR.get(target_date.weekday())
        if qatar_day is None:
            return {"deleted": 0, "created": 0, "kept": 0}

        slots = ScheduleSlot.objects.filter(
            school=school, academic_year=academic_year, day_of_week=qatar_day, is_active=True
        ).select_related("teacher", "class_group", "subject")
        wanted = {(s.teacher_id, s.class_group_id, s.start_time): s for s in slots}

        existing = list(
            Session.objects.filter(school=school, date=target_date).annotate(
                att=Count("attendances")
            )
        )
        have = {(s.teacher_id, s.class_group_id, s.start_time) for s in existing}
        stale = [
            s for s in existing if (s.teacher_id, s.class_group_id, s.start_time) not in wanted
        ]
        deletable = [s.id for s in stale if s.status == "scheduled" and s.att == 0]
        kept = len(stale) - len(deletable)
        deleted = Session.objects.filter(id__in=deletable).delete()[0] if deletable else 0

        to_create = [
            Session(
                school=school,
                teacher=slot.teacher,
                class_group=slot.class_group,
                subject=slot.subject,
                date=target_date,
                start_time=slot.start_time,
                end_time=slot.end_time,
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

    @staticmethod
    def resync_current_week(school: School, academic_year: str | None = None) -> dict[str, int]:
        """مصالحةُ أيّام الأسبوع الجاري (الأحد → الخميس) — تُستدعى عند الاعتماد."""
        from datetime import timedelta

        from django.utils import timezone

        week_sun, _ = ScheduleService._get_week_bounds(timezone.localdate())
        totals = {"deleted": 0, "created": 0, "kept": 0}
        for i in range(5):
            r = ScheduleService.resync_sessions_for_date(
                school, week_sun + timedelta(days=i), academic_year
            )
            for k in totals:
                totals[k] += r[k]
        return totals

    @staticmethod
    def ensure_sessions_for_range(
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
            week_sun, _ = ScheduleService._get_week_bounds(current)
            if week_sun not in seen_weeks:
                total += ScheduleService.ensure_sessions_for_date(school, current)
                seen_weeks.add(week_sun)
            current += timedelta(days=7)

        return total

    # Alias للتوافق مع الكود القديم
    @staticmethod
    def ensure_today_sessions(school: School) -> int:
        """Alias — يستدعي ensure_sessions_for_date لتاريخ اليوم."""
        from django.utils import timezone

        return ScheduleService.ensure_sessions_for_date(school, timezone.localdate())

    @staticmethod
    @transaction.atomic
    def create_exemption(
        school: School,
        teacher: CustomUser,
        academic_year: str,
        exemption_type: str,
        day_of_week: int,
        period_number,
        reason: str = "",
        created_by: CustomUser | None = None,
        source: str = "school",
    ):
        """
        إضافة تفريغ معلم من حصص الجدول.

        Args:
            school: كائن المدرسة
            teacher: المعلم المُفرَّغ
            academic_year: العام الدراسي
            exemption_type: نوع التفريغ (full_day / single_period)
            day_of_week: اليوم
            period_number: رقم الحصة (None لكامل اليوم)
            reason: سبب التفريغ
            created_by: المستخدم الذي أضاف التفريغ
            source: جهة القرار

        Returns:
            TeacherExemption: سجل التفريغ

        Raises:
            ValidationError: حصّةٌ بعينها بلا رقمها.

        ويُستدعى `full_clean()` هنا عمداً: `objects.create()` لا يُشغّل
        `clean()`، فلو اكتفينا به لصار في النظام بابانِ لحقيقةٍ واحدة.
        """
        exemption = TeacherExemption(
            school=school,
            teacher=teacher,
            academic_year=academic_year,
            exemption_type=exemption_type,
            day_of_week=day_of_week,
            period_number=int(period_number) if period_number else None,
            reason=reason,
            source=source,
            created_by=created_by,
        )
        exemption.full_clean(exclude=["created_by"])
        exemption.save()
        logger.info(
            "تفريغ جديد: معلم=%s نوع=%s يوم=%d بواسطة=%s",
            teacher.full_name,
            exemption_type,
            day_of_week,
            created_by.full_name if created_by else "—",
        )
        return exemption


class SubstituteService:
    @staticmethod
    def get_available_teachers(
        school: School,
        date: date,
        day_of_week: int,
        period_number: int,
        exclude_teacher: CustomUser | None = None,
        subject_id: int | None = None,
    ) -> QuerySet:
        """
        إيجاد معلمين متاحين للبدل:
        - لديهم membership نشطة في المدرسة
        - ليس لديهم حصة في نفس اليوم والحصة
        - لم يُسجَّل غيابهم في نفس اليوم

        إذا تم تمرير subject_id، يُرتَّب المعلمون بحيث يظهر
        معلمو نفس المادة أولاً ثم البقية.
        """
        from core.models import Membership

        # جميع معلمي المدرسة
        teacher_ids = Membership.objects.filter(
            school=school, is_active=True, role__name__in=("teacher", "coordinator")
        ).values_list("user_id", flat=True)

        if exclude_teacher:
            teacher_ids = [t for t in teacher_ids if t != exclude_teacher.id]

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

        available_ids = set(teacher_ids) - set(busy_ids) - set(absent_ids)

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
        """تعيين بديل لحصة محددة"""
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
        # تحديث حالة الغياب
        total_slots = (
            ScheduleSlot.objects.live(absence.school)
            .filter(
                teacher=absence.teacher,
                day_of_week=SubstituteService._date_to_day(absence.date),
            )
            .count()
        )
        covered = SubstituteAssignment.objects.filter(
            absence=absence, status__in=("assigned", "confirmed")
        ).count()
        if total_slots > 0 and covered >= total_slots:
            absence.status = "covered"
        else:
            absence.status = "pending"
        absence.save(update_fields=["status"])
        return assignment

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

    @staticmethod
    def suggest_best_substitute(
        school: School,
        target_date: date,
        day_of_week: int,
        period_number: int,
        exclude_teacher: CustomUser | None = None,
    ) -> CustomUser | None:
        """اقتراح أفضل بديل — الأقل حِملاً في البدائل هذا الأسبوع"""
        available = SubstituteService.get_available_teachers(
            school, target_date, day_of_week, period_number, exclude_teacher
        )
        if not available.exists():
            return None

        # حساب عدد بدائل كل معلم هذا الأسبوع
        from datetime import timedelta

        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)

        sub_counts = {}
        for teacher in available:
            count = SubstituteAssignment.objects.filter(
                substitute=teacher,
                absence__date__range=(week_start, week_end),
                school=school,
            ).count()
            sub_counts[teacher] = count

        # الأقل بدائل هذا الأسبوع
        return min(sub_counts, key=sub_counts.get)

    @staticmethod
    @transaction.atomic
    def assign_substitute_and_update_session(
        absence: TeacherAbsence,
        slot: ScheduleSlot,
        substitute: CustomUser,
        assigned_by: CustomUser | None = None,
        notes: str = "",
    ) -> SubstituteAssignment:
        """
        تعيين بديل + تحديث Session.teacher (الفجوة الحرجة المكتشفة).
        يضمن أن الحصة اليومية تعكس المعلم الفعلي.
        """
        assignment = SubstituteService.assign_substitute(
            absence,
            slot,
            substitute,
            assigned_by,
            notes,
        )
        # تحديث Session اليومية إذا وُجدت
        Session.objects.filter(
            school=absence.school,
            teacher=absence.teacher,
            date=absence.date,
            start_time=slot.start_time,
        ).update(teacher=substitute)
        return assignment


# ═════════════════════════════════════════════════════════════════════
# المرحلة 4 — خدمات التبديل والتعويض والحصص الحرة
# ═════════════════════════════════════════════════════════════════════


class FreeSlotService:
    """خدمة سجل الحصص الحرة — يُبنى تلقائياً من فراغات ScheduleSlot."""

    @staticmethod
    @transaction.atomic
    def build_registry(
        school: School,
        academic_year: str | None = None,
        max_periods: int = 7,
    ) -> int:
        """
        بناء/إعادة بناء سجل الحصص الحرة لكل معلمي المدرسة.
        يمسح القديم ويبني من جديد بناءً على ScheduleSlot.
        """
        academic_year = academic_year or academic_year_for_school(school)
        from core.models import Membership

        # حذف السجل القديم
        FreeSlotRegistry.objects.filter(school=school, academic_year=academic_year).delete()

        # جميع معلمي المدرسة
        teacher_ids = list(
            Membership.objects.filter(
                school=school,
                is_active=True,
                role__name__in=("teacher", "coordinator", "ese_teacher"),
            ).values_list("user_id", flat=True)
        )

        # بناء مجموعة الحصص المشغولة لكل معلم
        busy = {}
        slots = ScheduleSlot.objects.filter(
            school=school,
            academic_year=academic_year,
            is_active=True,
        ).values_list("teacher_id", "day_of_week", "period_number")

        for tid, day, period in slots:
            busy.setdefault(tid, set()).add((day, period))

        # بناء السجل
        records = []
        for tid in teacher_ids:
            teacher_busy = busy.get(tid, set())
            for day in range(5):  # 0=أحد → 4=خميس
                for period in range(1, max_periods + 1):
                    if (day, period) not in teacher_busy:
                        records.append(
                            FreeSlotRegistry(
                                teacher_id=tid,
                                school=school,
                                day_of_week=day,
                                period_number=period,
                                academic_year=academic_year,
                                is_available=True,
                            )
                        )

        FreeSlotRegistry.objects.bulk_create(records, batch_size=500)
        logger.info(
            "FreeSlotService.build_registry: created %d entries for school %s",
            len(records),
            school.code,
        )
        return len(records)

    @staticmethod
    def get_teacher_free_slots(
        teacher: CustomUser,
        school: School,
        academic_year: str | None = None,
    ) -> QuerySet:
        """حصص المعلم الفارغة — مرتبة حسب اليوم والحصة."""
        academic_year = academic_year or academic_year_for_school(school)
        return FreeSlotRegistry.objects.filter(
            teacher=teacher,
            school=school,
            academic_year=academic_year,
            is_available=True,
        ).order_by("day_of_week", "period_number")

    @staticmethod
    def get_free_teachers_at(
        school: School,
        day_of_week: int,
        period_number: int,
        academic_year: str | None = None,
        department=None,
    ) -> QuerySet:
        """
        المعلمون المتاحون في وقت معيّن.
        department: كائن Department أو اسم نصي — يُرشّح حسب القسم.
        """
        academic_year = academic_year or academic_year_for_school(school)
        from core.models import CustomUser, Membership

        qs = FreeSlotRegistry.objects.filter(
            school=school,
            day_of_week=day_of_week,
            period_number=period_number,
            academic_year=academic_year,
            is_available=True,
        ).values_list("teacher_id", flat=True)

        teachers = CustomUser.objects.filter(id__in=qs).order_by("full_name")

        if department:
            from core.models import Department

            if isinstance(department, Department):
                dept_teacher_ids = department.get_teacher_ids()
            else:
                # fallback: اسم نصي
                dept_teacher_ids = Membership.objects.filter(
                    school=school,
                    is_active=True,
                    department_obj__name=department,
                ).values_list("user_id", flat=True)
            teachers = teachers.filter(id__in=dept_teacher_ids)

        return teachers


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
            # تحديد المرحلة التالية
            if swap.is_cross_department:
                swap.status = "pending_vp"
            else:
                swap.status = "pending_coordinator"
            SwapService._notify(
                swap,
                swap.teacher_a,
                title=f"{swap.teacher_b.full_name} وافق على التبديل",
                body="بانتظار موافقة المنسق",
                event_type="swap_response",
            )
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
    @transaction.atomic
    def approve_swap(
        swap: TeacherSwap,
        approved_by: CustomUser,
        approved: bool = True,
        rejection_reason: str = "",
    ) -> TeacherSwap:
        """المنسق أو النائب يوافق/يرفض."""
        from django.utils import timezone as tz

        valid_statuses = ("pending_coordinator", "pending_vp", "accepted_b")
        if swap.status not in valid_statuses:
            raise ValueError(f"لا يمكن اعتماد طلب بحالة: {swap.get_status_display()}")

        swap.approved_by = approved_by
        swap.approved_at = tz.now()

        if approved:
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
        """تنفيذ التبديل الفعلي — تبديل المعلمين في الحصتين."""
        from django.utils import timezone as tz

        # تبديل المعلمين في ScheduleSlot
        slot_a = swap.slot_a
        slot_b = swap.slot_b
        slot_a.teacher, slot_b.teacher = slot_b.teacher, slot_a.teacher
        slot_a.save(update_fields=["teacher"])
        slot_b.save(update_fields=["teacher"])

        # تحديث Session اليومية إذا وُجدت
        Session.objects.filter(
            school=swap.school,
            teacher=swap.teacher_a,
            date=swap.swap_date_a,
            start_time=slot_a.start_time,
        ).update(teacher=swap.teacher_b)

        Session.objects.filter(
            school=swap.school,
            teacher=swap.teacher_b,
            date=swap.swap_date_b,
            start_time=slot_b.start_time,
        ).update(teacher=swap.teacher_a)

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


class CompensatoryService:
    """خدمة الحصص التعويضية."""

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
        """إنشاء طلب تعويض + إشعار المنسق."""

        # حساب week_offset
        original_date = absence.date
        diff_days = (compensatory_date - original_date).days
        week_offset = 1 if diff_days > 7 else 0

        if week_offset > 1:
            raise ValueError("الحد الأقصى للتعويض أسبوع واحد")

        comp = CompensatorySession.objects.create(
            school=school,
            teacher=teacher,
            original_slot=original_slot,
            absence=absence,
            compensatory_date=compensatory_date,
            compensatory_period=compensatory_period,
            class_group=original_slot.class_group,
            subject=original_slot.subject,
            week_offset=week_offset,
            status="pending",
            notes=notes,
        )

        # إشعار المنسق (إذا وُجد)
        try:
            from notifications.hub import NotificationHub

            dept_obj = teacher.department_obj
            if dept_obj:
                coordinators = dept_obj.memberships.filter(
                    is_active=True,
                    role__name="coordinator",
                ).values_list("user_id", flat=True)
            else:
                coordinators = []
            if coordinators:
                from core.models import CustomUser

                coord_users = list(CustomUser.objects.filter(pk__in=coordinators))
                if coord_users:
                    NotificationHub.dispatch(
                        event_type="compensatory",
                        school=school,
                        recipients=coord_users,
                        title=f"طلب تعويض من {teacher.full_name}",
                        body=f"يطلب تعويض حصة {original_slot.subject or 'مادة'} بتاريخ {compensatory_date}",
                        related_url="/teacher/schedule/compensatory/",
                    )
        except (ImportError, OSError):
            pass

        logger.info(
            "CompensatoryService: created request %s for teacher %s", comp.pk, teacher.full_name
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
        """المنسق/النائب يوافق على التعويض — ينشئ Session تلقائياً."""
        from django.utils import timezone as tz

        if comp.status != "pending":
            raise ValueError(f"لا يمكن اعتماد طلب بحالة: {comp.get_status_display()}")

        comp.approved_by = approved_by
        comp.approved_at = tz.now()

        if approved:
            comp.status = "approved"

            # إنشاء Session فعلية
            from operations.models import TimeSlotConfig

            time_config = TimeSlotConfig.objects.filter(
                school=comp.school,
                period_number=comp.compensatory_period,
                day_type="regular",
                is_break=False,
            ).first()

            if time_config:
                session, _ = Session.objects.get_or_create(
                    school=comp.school,
                    teacher=comp.teacher,
                    class_group=comp.class_group,
                    date=comp.compensatory_date,
                    start_time=time_config.start_time,
                    defaults={
                        "subject": comp.subject,
                        "end_time": time_config.end_time,
                        "status": "scheduled",
                        "notes": f"حصة تعويضية — أصلية: {comp.original_slot}",
                    },
                )
                comp.session_created = session

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

        # إشعار المعلم
        try:
            from notifications.hub import NotificationHub

            status_text = "تمت الموافقة" if approved else "تم الرفض"
            NotificationHub.dispatch(
                event_type="compensatory",
                school=comp.school,
                recipients=[comp.teacher],
                title=f"طلب التعويض: {status_text}",
                body=f"حصة {comp.subject or 'مادة'} بتاريخ {comp.compensatory_date}",
                related_url="/teacher/schedule/compensatory/",
            )
        except (ImportError, OSError, RuntimeError, ValueError):
            pass

        return comp

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
        """إلغاء الحصص التعويضية التي انتهت مهلتها (أكثر من أسبوعين)."""
        from datetime import timedelta

        cutoff = date.today() - timedelta(days=14)
        updated = CompensatorySession.objects.filter(
            school=school,
            status="pending",
            created_at__date__lt=cutoff,
        ).update(status="expired")
        if updated:
            logger.info("CompensatoryService.expire_overdue: expired %d requests", updated)
        return updated


# ─────────────────────────────────────────────────────────────────────────────


class CapacityCheckService:
    """خدمة فحص طاقة الجداول — Pre-validation قبل التوليد الذكي."""

    @staticmethod
    def slot_demand(assignments) -> int:
        """الزمنُ الذي تستهلكه هذه الإسنادات — بالخانات لا بالحصص.

            InstructionalPeriods ≠ OccupiedSlots

        فالشعبةُ المنقسمةُ تأخذ مادّتين في التوقيت نفسه: حصّتان تُدرَّسان،
        وخانةٌ واحدةٌ تُستهلك. وعدُّ الحصص هنا يُنتج إنذاراً كاذباً — «مطلوب
        37 والسعة 35» — وليس في الشعبة فائضٌ أصلاً.

        والمجموعةُ المتوازيةُ تستهلك أكبرَ نصابٍ فيها: لو كانت الفنونُ حصّتين
        والتكنولوجيا ثلاثاً، فالخاناتُ ثلاثٌ لا خمس.
        """
        from collections import defaultdict as _dd

        plain = 0
        groups: dict = _dd(int)
        for a in assignments:
            label = (a.parallel_group or "").strip()
            if label:
                groups[label] = max(groups[label], a.weekly_periods)
            else:
                plain += a.weekly_periods
        return plain + sum(groups.values())

    @staticmethod
    def get_overcapacity_classes(assignments) -> list[dict]:
        """
        يكتشف الفصول التي يتجاوز طلبها الأسبوعي طاقتها الاستيعابية.

        ✅ v5.4: ينقل capacity check من smart_schedule_view إلى service layer.

        Args:
            assignments: QuerySet من SubjectClassAssignment (يجب أن يكون محدَّداً مسبقاً)

        Returns:
            list of dict: كل عنصر يحتوي class_id, demand, capacity, overflow
        """
        from collections import defaultdict

        from operations.scheduler_constraints import get_max_periods_for_day

        class_rows: dict = defaultdict(list)
        class_levels: dict = {}
        class_names: dict = {}
        for a in assignments:
            cid = str(a.class_group_id)
            class_rows[cid].append(a)
            # التحذيرُ بلا اسمِ الشعبة لا يُصلحه أحد: «مطلوب 37» مرّتين لا
            # تقول أيَّ شعبةٍ تُراجَع.
            class_names[cid] = str(a.class_group)
            # `ClassGroup.level_type` حقلٌ قائمٌ يحمل «prep»/«sec» — يُقرأ ولا
            # يُشتقّ من `grade`. وكان هنا `_grade_to_level` وقد حُذف من المولّد
            # حين صُحّح الاشتقاقُ هناك، فبقي الاستيرادُ معلّقاً وسقطت الصفحةُ
            # كلُّها بـ`ImportError` — لا الفحصُ وحدَه.
            class_levels[cid] = a.class_group.level_type or ""

        overcapacity = []
        class_demand = {
            cid: CapacityCheckService.slot_demand(rows) for cid, rows in class_rows.items()
        }
        for cid, demand in class_demand.items():
            level = class_levels.get(cid, "")
            thu_max = get_max_periods_for_day(4, level)
            weekly_capacity = 4 * 7 + thu_max
            if demand > weekly_capacity:
                overcapacity.append(
                    {
                        "class_id": cid,
                        "class_name": class_names.get(cid, cid),
                        "demand": demand,
                        "capacity": weekly_capacity,
                        "overflow": demand - weekly_capacity,
                    }
                )
        return overcapacity


class TeacherLoadService:
    """خدمات تقرير أحمال المعلمين — ينقل business logic من teacher_load_report view."""

    @staticmethod
    def get_teacher_load_data(school: School, year: str, teachers) -> dict:
        """
        بيانات تقرير أحمال المعلمين — استعلامان بدل N+1.

        ✅ v5.4: يستبدل Counter loop في teacher_load_report view:
          - استعلام واحد لـ slot_counts بدل N استعلامات
          - استعلام واحد لـ sub_counts الشهرية
          - daily_counts يُبنى من نفس rows ScheduleSlot

        Args:
            school: كائن المدرسة
            year: العام الدراسي
            teachers: QuerySet للمعلمين المستهدفين

        Returns:
            dict يحتوي: teacher_data (list), avg_weekly (float),
                        total_teachers (int)
        """
        from collections import Counter

        slot_counts = Counter(
            ScheduleSlot.objects.filter(
                school=school, academic_year=year, is_active=True
            ).values_list("teacher_id", flat=True)
        )
        month_start = date.today().replace(day=1)
        sub_counts = Counter(
            SubstituteAssignment.objects.filter(
                school=school, absence__date__gte=month_start
            ).values_list("substitute_id", flat=True)
        )

        # بناء daily_counts من نفس ScheduleSlot QuerySet — استعلام واحد
        daily_counts: dict[tuple, int] = {}
        for slot in ScheduleSlot.objects.filter(school=school, academic_year=year, is_active=True):
            key = (str(slot.teacher_id), slot.day_of_week)
            daily_counts[key] = daily_counts.get(key, 0) + 1

        teacher_data = []
        for t in teachers:
            tid = str(t.id)
            weekly = slot_counts.get(t.id, 0)
            subs = sub_counts.get(t.id, 0)
            days = [daily_counts.get((tid, d), 0) for d in range(5)]
            teacher_data.append(
                {
                    "teacher": t,
                    "weekly": weekly,
                    "subs": subs,
                    "max_daily": max(days) if days else 0,
                    "min_daily": min(d for d in days if d > 0) if any(d > 0 for d in days) else 0,
                    "free_days": sum(1 for d in days if d == 0),
                    "days": days,
                }
            )

        teacher_data.sort(key=lambda x: -x["weekly"])
        avg_weekly = (
            sum(d["weekly"] for d in teacher_data) / len(teacher_data) if teacher_data else 0
        )

        return {
            "teacher_data": teacher_data,
            "avg_weekly": round(avg_weekly, 1),
            "total_teachers": len(teacher_data),
        }
