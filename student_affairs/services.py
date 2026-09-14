"""
student_affairs/services.py — Business Logic لشؤون الطلاب

ثلاث طبقات خدمة:
    StudentService     — إحصائيات لوحة التحكم + إنشاء/تعديل/تعطيل
    TardinessService   — تسجيل التأخّر الصباحيّ
    TransferService    — إدارة انتقالات الطلاب (وارد/صادر)

والقراءاتُ التي تعرضها الصفحات في `selectors.py`. وكانت هنا ثلاثُ قراءاتٍ لا
يستدعيها أحد — `get_student_profile_data` و`AttendanceService.get_attendance_overview`
و`get_tardiness_report` — بنوافذ وحقولٍ غير التي تعرضها الصفحات،
نسخٌ متباعدةٌ تُضلّل من يبحث عن
الاستعلام الحيّ. فحُذفت يومَ نُقلت القراءاتُ الحيّةُ إلى `selectors.py` (2026-09-14).

القواعد:
    - كل method يُعيد dict أو QuerySet — ليس HttpResponse
    - select_related / prefetch_related لتقليل الاستعلامات
    - transaction.atomic() للعمليات الذرّية
    - لا فلاتر hardcoded — كلها parameters
"""

import logging

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.labels import class_label
from core.models.academic import ClassGroup, ParentStudentLink, StudentEnrollment, grade_order
from core.models.access import Membership, Role
from core.models.user import CustomUser, Profile

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Lazy imports — تجنّب circular imports عند التحميل الأولي
# ═══════════════════════════════════════════════════════════════════════


def _get_attendance_model():
    from operations.models import StudentAttendance

    return StudentAttendance


def _get_session_model():
    from operations.models import Session

    return Session


def _get_behavior_model():
    from behavior.models import BehaviorInfraction

    return BehaviorInfraction


def _get_clinic_model():
    from clinic.models import ClinicVisit

    return ClinicVisit


def _get_activity_model():
    from student_affairs.models import StudentActivity

    return StudentActivity


def _get_transfer_model():
    from student_affairs.models import StudentTransfer

    return StudentTransfer


# ═══════════════════════════════════════════════════════════════════════
# 1. StudentService — إحصائيات + ملف الطالب + CRUD
# ═══════════════════════════════════════════════════════════════════════


class StudentService:
    """خدمات شؤون الطلاب: لوحة تحكم، ملف شامل، إنشاء وتعطيل."""

    # ── لوحة التحكم ────────────────────────────────────────────────

    @staticmethod
    def get_dashboard_stats(school, year: str) -> dict:
        """
        إحصائيات لوحة شؤون الطلاب — يجمع KPIs من عدة تطبيقات.

        Args:
            school: كائن المدرسة
            year: العام الدراسي (مثال: "2025-2026")

        Returns:
            dict يحتوي: total_students, today_attendance, behavior_month,
                        clinic_visits, pending_transfers, activities_count,
                        grade_distribution, parent_link_count
        """
        today = timezone.now().date()
        month_start = today.replace(day=1)

        StudentAttendance = _get_attendance_model()
        BehaviorInfraction = _get_behavior_model()
        ClinicVisit = _get_clinic_model()
        StudentTransfer = _get_transfer_model()
        StudentActivity = _get_activity_model()

        # الطلاب المسجلون النشطون
        active_enrollments = StudentEnrollment.objects.filter(
            class_group__school=school,
            class_group__academic_year=year,
            is_active=True,
        )
        total_students = active_enrollments.count()

        # حضور اليوم
        today_attendance = StudentAttendance.objects.filter(
            school=school,
            session__date=today,
        ).aggregate(
            present=Count("id", filter=Q(status="present")),
            absent=Count("id", filter=Q(status="absent")),
            late=Count("id", filter=Q(status="late")),
            excused=Count("id", filter=Q(status="excused")),
            total=Count("id"),
        )

        # مخالفات سلوكية هذا الشهر
        behavior_month = BehaviorInfraction.objects.filter(
            school=school,
            date__gte=month_start,
            date__lte=today,
        ).aggregate(
            total=Count("id"),
            unresolved=Count("id", filter=Q(is_resolved=False)),
        )

        # زيارات العيادة هذا الشهر
        clinic_visits = ClinicVisit.objects.filter(
            school=school,
            visit_date__date__gte=month_start,
        ).count()

        # انتقالات قيد الانتظار
        pending_transfers = StudentTransfer.objects.filter(
            school=school,
            academic_year=year,
            status="pending",
        ).count()

        # أنشطة هذا العام
        activities_count = StudentActivity.objects.filter(
            school=school,
            academic_year=year,
        ).count()

        # توزيع الطلاب حسب الصف
        grade_distribution = (
            active_enrollments.values("class_group__grade")
            .annotate(count=Count("id"))
            .order_by(grade_order("class_group__grade"))
        )

        # عدد أولياء الأمور المرتبطين
        parent_link_count = ParentStudentLink.objects.filter(
            school=school,
        ).count()

        return {
            "total_students": total_students,
            "today_attendance": today_attendance,
            "behavior_month": behavior_month,
            "clinic_visits": clinic_visits,
            "pending_transfers": pending_transfers,
            "activities_count": activities_count,
            "grade_distribution": list(grade_distribution),
            "parent_link_count": parent_link_count,
        }

    @staticmethod
    def get_dashboard_context(school, year: str, today=None) -> dict:
        """
        السياق الكامل للوحة شؤون الطلاب — يجمع get_dashboard_stats + queries الإضافية.

        ✅ v5.4: يُحوّل 6 raw queries المتبقية في student_dashboard إلى service layer.

        Args:
            school: كائن المدرسة
            year: العام الدراسي
            today: تاريخ اليوم (افتراضي: اليوم الفعلي)

        Returns:
            dict يحتوي: جميع بيانات get_dashboard_stats +
                        clinic_today, recent_infractions, recent_transfers,
                        no_parent_count, weekly_tardiness, recent_activities
        """
        from datetime import timedelta

        from django.db.models import Exists, OuterRef

        from core.models import ParentStudentLink

        today = today or timezone.now().date()

        BehaviorInfraction = _get_behavior_model()
        ClinicVisit = _get_clinic_model()
        StudentAttendance = _get_attendance_model()
        StudentTransfer = _get_transfer_model()
        StudentActivity = _get_activity_model()

        stats = StudentService.get_dashboard_stats(school, year)

        clinic_today = ClinicVisit.objects.filter(
            school=school,
            visit_date__date=today,
        ).count()

        recent_infractions = list(
            BehaviorInfraction.objects.filter(school=school)
            .select_related("student", "violation_category")
            .order_by("-date")[:5]
        )

        recent_transfers = list(
            StudentTransfer.objects.filter(school=school)
            .select_related("student")
            .order_by("-created_at")[:5]
        )

        # طلاب بدون ولي أمر — Exists subquery بدل Python set arithmetic
        no_parent_count = (
            StudentEnrollment.objects.filter(
                class_group__school=school,
                class_group__academic_year=year,
                is_active=True,
            )
            .annotate(
                has_parent=Exists(
                    ParentStudentLink.objects.filter(
                        school=school,
                        student_id=OuterRef("student_id"),
                    )
                )
            )
            .filter(has_parent=False)
            .count()
        )

        week_start = today - timedelta(days=today.weekday())
        weekly_tardiness = StudentAttendance.objects.filter(
            school=school,
            status="late",
            session__date__gte=week_start,
            session__date__lte=today,
        ).count()

        recent_activities = list(
            StudentActivity.objects.filter(school=school, academic_year=year)
            .select_related("student")
            .order_by("-date")[:5]
        )

        # ── إحصائيات لوحة شؤون الطلاب (SOS-20260420-9A91) ─────────────
        # الجزء الأول: إحصائيات يومية ( 6 عناصر — طلب المدير )
        # الجزء الثاني: 3 قوائم — غائبون، متأخرون، مخالفون
        from django.db.models import Case, IntegerField, When

        # توزيع الطلاب حسب المرحلة الدراسية (إعدادي 7-9 / ثانوي 10-12 فقط — لا ابتدائي)
        active_enrollments = stats.get(
            "_active_enrollments_qs"
        ) or StudentEnrollment.objects.filter(
            class_group__school=school,
            class_group__academic_year=year,
            is_active=True,
        )
        stage_qs = (
            active_enrollments.annotate(
                stage=Case(
                    When(class_group__grade__in=["G7", "G8", "G9"], then=2),
                    When(class_group__grade__in=["G10", "G11", "G12"], then=3),
                    default=0,
                    output_field=IntegerField(),
                )
            )
            .values("stage")
            .annotate(count=Count("id"))
            .order_by("stage")
        )
        stage_map = {row["stage"]: row["count"] for row in stage_qs}

        # نسبة القطريين — سجل القيد الرسمي يستخدم "قطر" (اسم الدولة) لا "قطري"
        total_students = stats.get("total_students", 0)
        qatari_count = Membership.objects.filter(
            school=school,
            role__name="student",
            is_active=True,
            user__nationality__in=["قطر", "قطري"],
        ).count()
        qatari_pct = round(qatari_count * 100 / total_students) if total_students else 0

        # نسب الغياب والتأخير
        today_att = stats.get("today_attendance", {})
        absent_today_n = today_att.get("absent") or 0
        late_today_n = today_att.get("late") or 0
        absent_pct = round(absent_today_n * 100 / total_students) if total_students else 0
        late_pct = round(late_today_n * 100 / total_students) if total_students else 0

        # مخالفات اليوم
        today_behavior_count = BehaviorInfraction.objects.filter(
            school=school,
            date=today,
        ).count()

        # قائمتا الغائبين/المتأخرين: dedupe بالطالب + dicts بمفاتيح نظيفة للعرض
        def _dedupe_attendance_list(status: str):
            rows = (
                StudentAttendance.objects.filter(school=school, session__date=today, status=status)
                .select_related("student", "session__class_group")
                .values(
                    "student_id",
                    "student__full_name",
                    "session__class_group__grade",
                    "session__class_group__section",
                )
                .order_by("student__full_name")
            )
            seen = set()
            result = []
            for r in rows:
                sid = r["student_id"]
                if sid in seen:
                    continue
                seen.add(sid)
                result.append(
                    {
                        "id": sid,
                        "full_name": r["student__full_name"],
                        # بصيغة سجلّ القيد «07/2» لا الرمزِ الخامّ «G7/2».
                        "class_group": class_label(
                            r["session__class_group__grade"], r["session__class_group__section"]
                        ),
                    }
                )
                if len(result) >= 100:
                    break
            return result

        absent_list = _dedupe_attendance_list("absent")
        late_list = _dedupe_attendance_list("late")

        # قائمة المخالفين اليوم
        today_infraction_list = list(
            BehaviorInfraction.objects.filter(school=school, date=today)
            .select_related("student", "violation_category")
            .order_by("student__full_name")[:100]
        )

        return {
            **stats,
            "clinic_today": clinic_today,
            "recent_infractions": recent_infractions,
            "recent_transfers": recent_transfers,
            "no_parent_count": no_parent_count,
            "weekly_tardiness": weekly_tardiness,
            "recent_activities": recent_activities,
            # Req3 additions
            "stage_map": stage_map,
            "qatari_pct": qatari_pct,
            "absent_pct": absent_pct,
            "late_pct": late_pct,
            "today_behavior_count": today_behavior_count,
            "absent_list": absent_list,
            "late_list": late_list,
            "today_infraction_list": today_infraction_list,
        }

    # ── ملف الطالب الشامل ──────────────────────────────────────────

    # ── إنشاء طالب جديد ───────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def create_student(school, data: dict) -> CustomUser:
        """
        إنشاء طالب جديد — 4 سجلات ذرّية (User + Profile + Membership + Enrollment).

        Args:
            school: كائن المدرسة
            data: dict يحتوي:
                - national_id (str): الرقم الشخصي
                - full_name (str): الاسم الكامل
                - password (str, optional): كلمة المرور (افتراضي = national_id)
                - gender (str, optional): "M" أو "F"
                - birth_date (date, optional)
                - phone (str, optional)
                - email (str, optional)
                - nationality (str, optional): الجنسية
                - class_group_id (UUID): معرّف الفصل الدراسي

        Returns:
            CustomUser: كائن الطالب المنشأ

        Raises:
            ValueError: إذا كان national_id مكرراً أو الشعبة غير موجودة
        """
        national_id = data["national_id"]
        class_group_id = data["class_group_id"]

        # ── التحققات ──
        if CustomUser.objects.filter(national_id=national_id).exists():
            raise ValueError(f"الرقم الشخصي {national_id} مسجّل مسبقاً في النظام.")

        try:
            class_group = ClassGroup.objects.get(
                pk=class_group_id,
                school=school,
                is_active=True,
            )
        except ClassGroup.DoesNotExist:
            raise ValueError("الشعبة المحددة غير موجودة أو غير فعّالة في هذه المدرسة.")

        # ── 1. إنشاء المستخدم ──
        password = data.get("password", national_id)
        user = CustomUser.objects.create_user(
            national_id=national_id,
            full_name=data["full_name"],
            password=password,
            email=data.get("email", ""),
            phone=data.get("phone", ""),
        )
        user.must_change_password = True
        if data.get("nationality"):
            user.nationality = data["nationality"]
        user.save(update_fields=["must_change_password", "nationality"])

        # ── 2. الملف الشخصي ──
        Profile.objects.create(
            user=user,
            gender=data.get("gender", ""),
            birth_date=data.get("birth_date"),
        )

        # ── 3. العضوية (دور طالب) ──
        student_role, _ = Role.objects.get_or_create(
            school=school,
            name="student",
        )
        Membership.objects.create(
            user=user,
            school=school,
            role=student_role,
            is_active=True,
        )

        # ── 4. التسجيل في الفصل ──
        StudentEnrollment.objects.create(
            student=user,
            class_group=class_group,
            is_active=True,
        )

        logger.info(
            "تم إنشاء طالب جديد: %s (national_id=%s) في المدرسة %s",
            user.full_name,
            national_id,
            school.code,
        )
        return user

    # ── تحديث طالب موجود ──────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def update_student(student, school, data: dict) -> CustomUser:
        """
        تحديث بيانات طالب — ذرّي (User + Profile + إعادة التسجيل عند تغيّر الصف/الشعبة).

        Args:
            student: كائن الطالب (CustomUser)
            school: كائن المدرسة
            data: dict يحتوي full_name, phone, email, birth_date, notes, grade, section

        Returns:
            CustomUser: الطالب بعد التحديث

        Raises:
            ValueError: إذا طُلبت إعادة تسجيل لشعبة غير موجودة في المدرسة (يُلغى كل التحديث).
        """
        year = academic_year_for_school(school)

        # ── 1. تحديث المستخدم ──
        student.full_name = data["full_name"]
        student.phone = data.get("phone", "")
        student.email = data.get("email", "")
        student.save(update_fields=["full_name", "phone", "email"])

        # ── 2. الملف الشخصي ──
        Profile.objects.update_or_create(
            user=student,
            defaults={
                "birth_date": data.get("birth_date"),
                "notes": data.get("notes", ""),
            },
        )

        # ── 3. إعادة التسجيل عند تغيّر الصف/الشعبة (deactivate + create ذرّياً) ──
        enrollment = (
            StudentEnrollment.objects.filter(
                student=student, class_group__academic_year=year, is_active=True
            )
            .select_related("class_group")
            .first()
        )
        new_grade = data["grade"]
        new_section = data["section"]
        needs_reenroll = (
            not enrollment
            or enrollment.class_group.grade != new_grade
            or enrollment.class_group.section != new_section
        )
        if needs_reenroll:
            new_class = ClassGroup.objects.filter(
                school=school,
                grade=new_grade,
                section=new_section,
                academic_year=year,
                is_active=True,
            ).first()
            if not new_class:
                raise ValueError(f"لا توجد شعبة {new_section} في الصف {new_grade} لإعادة التسجيل.")
            if enrollment:
                enrollment.is_active = False
                enrollment.save(update_fields=["is_active"])
            StudentEnrollment.objects.create(student=student, class_group=new_class, is_active=True)

        logger.info("تم تحديث الطالب: %s (school=%s)", student.full_name, school.code)
        return student

    # ── تعطيل طالب ─────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def deactivate_student(student, school, user) -> None:
        """
        تعطيل طالب — إلغاء Membership + Enrollment.

        لا يحذف السجلات — فقط يضع is_active=False للحفاظ على السجل التاريخي.

        Args:
            student: كائن الطالب (CustomUser)
            school: كائن المدرسة
            user: المستخدم الذي ينفّذ العملية (للتدقيق)
        """
        # تعطيل العضوية
        updated_memberships = Membership.objects.filter(
            user=student,
            school=school,
            is_active=True,
        ).update(is_active=False)

        # تعطيل التسجيل
        updated_enrollments = StudentEnrollment.objects.filter(
            student=student,
            class_group__school=school,
            is_active=True,
        ).update(is_active=False)

        # إبطال cache العضوية
        student.invalidate_active_membership()

        logger.info(
            "تم تعطيل الطالب %s في المدرسة %s بواسطة %s (عضويات: %d، تسجيلات: %d)",
            student.full_name,
            school.code,
            user.full_name,
            updated_memberships,
            updated_enrollments,
        )


# ═══════════════════════════════════════════════════════════════════════
# 2. TardinessService — تسجيل التأخّر الصباحيّ
# ═══════════════════════════════════════════════════════════════════════


class TardinessService:
    """تسجيلُ التأخّر الصباحيّ — كتابةٌ ذرّيّةٌ بسجلّ تدقيقها."""

    @staticmethod
    @transaction.atomic
    def record_morning_tardiness(
        *,
        school,
        student,
        minutes: int | None,
        excuse_file,
        marked_by,
        now,
        ip_address: str | None = None,
    ):
        """يسجّل تأخّرَ الطالب في حصّة التأخّر يومَ `now` ويُرجع سجلَّ حضوره.

        الحصّةُ أوّلُ حصّةٍ لشعبته اليوم، وإلّا أوّلُ حصّةٍ في المدرسة
        (`selectors.tardiness_session`). ولا حصّةَ اليوم → `None` بلا كتابة.
        وسجلٌّ قائمٌ للطالب في الحصّة نفسِها يُحدَّث ولا يُكرَّر، والتدقيقُ
        (PDPPL) في المعاملة نفسِها: لا تأخّرَ يُكتب بلا أثره في السجلّ.
        """
        from core.models.audit import AuditLog

        from .selectors import tardiness_session

        session = tardiness_session(school, student, now.date())
        if session is None:
            return None

        fields = {
            "status": "late",
            "tardiness_minutes": minutes,
            "excuse_notes": f"إذن تأخير {minutes} دقيقة" if minutes else "",
            "tardiness_recorded_at": now,
            "marked_by": marked_by,
        }
        attendance, created = _get_attendance_model().objects.get_or_create(
            session=session, student=student, school=school, defaults=fields
        )
        if not created:
            for name, value in fields.items():
                setattr(attendance, name, value)
            attendance.save(update_fields=[*fields, "updated_at"])
        if excuse_file:
            attendance.excuse_file = excuse_file
            attendance.save(update_fields=["excuse_file"])

        AuditLog.objects.create(
            user=marked_by,
            school=school,
            action="create",
            model_name="other",
            object_id=str(attendance.pk),
            object_repr=f"تسجيل تأخير {student.full_name}",
            ip_address=ip_address,
        )
        return attendance


# ═══════════════════════════════════════════════════════════════════════
# 3. TransferService — إدارة انتقالات الطلاب
# ═══════════════════════════════════════════════════════════════════════


class TransferService:
    """خدمات إدارة انتقالات الطلاب (وارد/صادر)."""

    @staticmethod
    def get_transfers_list(
        school,
        year: str = None,
        status: str = None,
        direction: str = None,
    ):
        """
        قائمة انتقالات الطلاب مع فلترة اختيارية.

        Args:
            school: كائن المدرسة
            year: العام الدراسي (اختياري)
            status: حالة الانتقال — pending/approved/rejected/completed/cancelled
            direction: اتجاه — in/out

        Returns:
            QuerySet[StudentTransfer]
        """
        StudentTransfer = _get_transfer_model()

        qs = (
            StudentTransfer.objects.filter(school=school)
            .select_related("student", "created_by")
            .order_by("-created_at")
        )

        if year:
            qs = qs.filter(academic_year=year)
        if status:
            qs = qs.filter(status=status)
        if direction:
            qs = qs.filter(direction=direction)

        return qs

    @staticmethod
    @transaction.atomic
    def create_transfer(school, data: dict, created_by):
        """
        إنشاء طلب انتقال طالب.

        Args:
            school: كائن المدرسة
            data: dict يحتوي:
                - student_id (UUID): معرّف الطالب
                - direction (str): "in" أو "out"
                - other_school_name (str): اسم المدرسة الأخرى
                - transfer_date (date): تاريخ الانتقال
                - from_grade (str, optional): الصف الحالي
                - to_grade (str, optional): الصف المنتقل إليه
                - reason (str, optional): سبب الانتقال
                - notes (str, optional): ملاحظات
            created_by: المستخدم الذي أنشأ الطلب

        Returns:
            StudentTransfer: كائن الانتقال المنشأ

        Raises:
            CustomUser.DoesNotExist: إذا لم يُوجد الطالب
        """
        StudentTransfer = _get_transfer_model()

        student = CustomUser.objects.get(pk=data["student_id"])

        transfer = StudentTransfer.objects.create(
            school=school,
            student=student,
            direction=data["direction"],
            other_school_name=data["other_school_name"],
            transfer_date=data["transfer_date"],
            from_grade=data.get("from_grade", ""),
            to_grade=data.get("to_grade", ""),
            reason=data.get("reason", ""),
            notes=data.get("notes", ""),
            status="pending",
            academic_year=data.get("academic_year") or academic_year_for_school(school),
            created_by=created_by,
        )

        logger.info(
            "تم إنشاء طلب انتقال %s للطالب %s — %s",
            transfer.get_direction_display(),
            student.full_name,
            school.code,
        )
        return transfer

    @staticmethod
    @transaction.atomic
    def review_transfer(transfer, action: str, notes: str, reviewer) -> None:
        """
        مراجعة طلب انتقال — موافقة أو رفض أو إتمام.

        عند إتمام انتقال صادر: يتم تعطيل الطالب تلقائياً.

        Args:
            transfer: كائن StudentTransfer
            action: "approved" أو "rejected" أو "completed" أو "cancelled"
            notes: ملاحظات المراجعة
            reviewer: المستخدم المراجع

        Raises:
            ValueError: إذا كان الإجراء غير صالح أو الحالة لا تسمح بالمراجعة
        """
        valid_actions = {"approved", "rejected", "completed", "cancelled"}
        if action not in valid_actions:
            raise ValueError(
                f"إجراء غير صالح: {action}. الإجراءات المتاحة: {', '.join(valid_actions)}"
            )

        # لا يمكن المراجعة إلا إذا كان الطلب قيد الانتظار أو موافقاً عليه
        if transfer.status not in ("pending", "approved"):
            raise ValueError(
                f"لا يمكن تنفيذ الإجراء '{action}' على طلب بحالة '{transfer.get_status_display()}'."
            )

        transfer.status = action
        if notes:
            separator = "\n---\n" if transfer.notes else ""
            transfer.notes += f"{separator}[{reviewer.full_name}]: {notes}"

        transfer.updated_by = reviewer
        transfer.save(update_fields=["status", "notes", "updated_by", "updated_at"])

        # عند إتمام انتقال صادر: تعطيل الطالب
        if action == "completed" and transfer.direction == "out":
            StudentService.deactivate_student(
                student=transfer.student,
                school=transfer.school,
                user=reviewer,
            )
            logger.info(
                "تم إتمام انتقال صادر وتعطيل الطالب %s من المدرسة %s",
                transfer.student.full_name,
                transfer.school.code,
            )

        logger.info(
            "تمت مراجعة طلب انتقال #%s — الإجراء: %s بواسطة %s",
            transfer.pk,
            action,
            reviewer.full_name,
        )
