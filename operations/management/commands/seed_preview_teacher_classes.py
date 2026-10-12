"""يُسند المعلّمَ الوهميّ لحساب المعاينة إلى شُعبٍ من جناحٍ واحدٍ يغطّيه المشرفُ الوهميّ (W-20261005-005) — تستدعيه `preview_accounts --sync`.

كان المعلّمُ يُسنَد خارج الأمر إلى ثلاثة أجنحةٍ والمشرفُ لا يغطّي إلا واحداً (لا تغطيتان لحسابٍ واحد — قرارُ 2026-10-04) فيرى حصّتين من ستّ.
فهنا: **إضافةٌ فقط** لشعبةٍ فيها مادّةٌ بلا إسناد — لا نقلَ إسنادٍ قائمٍ ولا حذفَ ولا مسَّ معلّمٍ آخر، ومتساوي الأثر.
ولا يعمل إلا في المعاينة (`in_preview_environment`)، ولا يعمل إن كان للمعلّم الوهميّ إسنادٌ قائمٌ في العام، أو كان المشرفُ لا يغطّي جناحاً.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import AuditLog, ClassGroup, CustomUser, School, WingCoverage
from core.preview_accounts import EMPLOYEE_NUMBERS, in_preview_environment
from operations.attendance_policy import is_special_education
from operations.models import Subject, SubjectClassAssignment

#: شُعبٌ من جناح المشرف الوهميّ للمعلّم الوهميّ، وشعبتا تربيةٍ خاصّةٍ بلا جناحٍ للتجربة الخاصّة بها.
WING_CLASSES = 2
ESE_CLASSES = 2


class Command(BaseCommand):
    help = "يُسند المعلّمَ الوهميّ إلى شُعبٍ من جناح المشرف الوهميّ (المعاينة فقط، متساوي الأثر)."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="رمزُ المدرسة (الأولى النشطة إن حُذف)")

    def handle(self, *args, **options):
        if not in_preview_environment():
            raise CommandError("رُفض: ليست بيئةَ معاينة")
        schools = School.objects.filter(is_active=True)
        code = options["school"]
        school = schools.filter(code=code).first() if code else schools.order_by("code").first()
        if school is None:
            raise CommandError("لا مدرسةَ نشطة")
        note = self.seed(school)
        if note:
            self.stdout.write(note)

    def seed(self, school: School) -> str:
        supervisor = CustomUser.objects.filter(
            employee_number=EMPLOYEE_NUMBERS["admin_supervisor"]
        ).first()
        teacher = CustomUser.objects.filter(employee_number=EMPLOYEE_NUMBERS["teacher"]).first()
        if supervisor is None or teacher is None:
            return ""
        year = academic_year_for_school(school)
        today = timezone.localdate()
        wing_ids = list(
            WingCoverage.objects.filter(substitute=supervisor, start_date__lte=today)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
            .values_list("wing_id", flat=True)
        )
        if not wing_ids:
            return ""
        if SubjectClassAssignment.objects.filter(
            school=school,
            teacher=teacher,
            academic_year=year,
            is_active=True,
            deleted_at__isnull=True,
        ).exists():
            return ""
        classes = list(
            ClassGroup.objects.filter(
                school=school, academic_year=year, is_active=True, wing_id__in=wing_ids
            ).order_by("grade", "section")[:WING_CLASSES]
        )
        classes += [
            klass
            for klass in ClassGroup.objects.filter(
                school=school, academic_year=year, is_active=True, wing__isnull=True
            ).order_by("grade", "section")
            if is_special_education(klass)
        ][:ESE_CLASSES]
        subjects = list(Subject.objects.filter(school=school).order_by("code", "pk"))
        added = 0
        for klass in classes:
            taken = set(
                SubjectClassAssignment.objects.filter(
                    school=school, class_group=klass, academic_year=year
                ).values_list("subject_id", flat=True)
            )
            subject = next((sub for sub in subjects if sub.pk not in taken), None)
            if subject is None:
                continue
            try:
                with transaction.atomic():
                    SubjectClassAssignment.objects.create(
                        school=school,
                        class_group=klass,
                        subject=subject,
                        teacher=teacher,
                        weekly_periods=2,
                        academic_year=year,
                    )
            except IntegrityError:
                continue
            added += 1
            AuditLog.log(
                user=None,
                action="create",
                model_name="other",
                object_id=teacher.pk,
                object_repr="حسابُ معاينةٍ دائم — إسنادُ المعلّم لشعبة",
                changes={"class": klass.short_label},
                school=school,
            )
        return f"أُسند المعلّم الوهميّ إلى {added} شعبة" if added else ""
