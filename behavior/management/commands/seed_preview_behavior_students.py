"""يبذر طلبةً وهميّين بلا أيّ مخالفةٍ في شُعب المعاينة ليُجرَّب بحثُ لوحة السلوك وكشفُ السلوك (W-20261111-004) — تستدعيه `preview_accounts --sync`.

رفض المالكُ معاينةَ البطاقة لأنّ قاعدةَ المعاينة بلا طلبةٍ في نطاق المشرف الوهميّ فلا يجد البحثُ أحداً، ولا طالبَ بلا مخالفةٍ يُفتح ملفُّه.
فهنا: **إضافةٌ فقط** — ثلاثةٌ في كلّ شعبةٍ من أول شعبتين في جناح المشرف الوهميّ، وطالبٌ واحدٌ في شعبةٍ من جناحٍ آخرَ ليُرى أنّ البحث لا يتجاوز النطاق.
لا مخالفاتٍ تُسجَّل ولا مسَّ طالبٍ قائم، ومتساوي الأثر (`get_or_create`)، ولا يعمل إلا في المعاينة (`in_preview_environment`).
الأسماءُ بلا وسم «[وهميّ» عمداً: الوسمُ المركَّب يخصّ حساباتِ الدخول وفحصُ `--check` يعدّ كلَّ موسومٍ خارج القائمة خللاً.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import (
    ClassGroup,
    CustomUser,
    Membership,
    Role,
    School,
    StudentEnrollment,
    WingCoverage,
)
from core.preview_accounts import EMPLOYEE_NUMBERS, in_preview_environment

#: شُعبُ جناح المشرف الوهميّ المبذورةُ طلبتُها، وعددُ الطلبة في كلّ شعبة.
WING_CLASSES = 2
PER_CLASS = 3
#: بادئةُ رقم الطالب الاصطناعيّ (`PV-` كسائر بذر المعاينة، و`bs` لهذا الأمر).
ID_PREFIX = "PV-bs-"


class Command(BaseCommand):
    help = "يبذر طلبةً بلا مخالفاتٍ في شُعب المعاينة (المعاينة فقط، متساوي الأثر)."

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
        if supervisor is None:
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
        classes = ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
        inside = list(
            classes.filter(wing_id__in=wing_ids).order_by("grade", "section")[:WING_CLASSES]
        )
        outside = list(
            classes.filter(wing__isnull=False)
            .exclude(wing_id__in=wing_ids)
            .order_by("grade", "section")[:1]
        )
        role, _ = Role.objects.get_or_create(school=school, name="student")
        added = 0
        with transaction.atomic():
            for index, klass in enumerate(inside + outside):
                count = PER_CLASS if klass in inside else 1
                for number in range(1, count + 1):
                    added += self._student(school, role, klass, f"{index}{number}", klass in inside)
        return f"بُذر {added} طالباً بلا مخالفاتٍ للمعاينة" if added else ""

    def _student(self, school: School, role: Role, klass: ClassGroup, key: str, mine: bool) -> int:
        """يبذر طالباً واحداً بقيده؛ يعيد 1 إن أُنشئ و0 إن وُجد."""
        label = "جناح المشرف" if mine else "جناح آخر"
        student, created = CustomUser.objects.get_or_create(
            national_id=f"{ID_PREFIX}{key}",
            defaults={"full_name": f"طالب معاينة ({label}) {key}"},
        )
        Membership.objects.get_or_create(
            user=student, school=school, role=role, defaults={"is_active": True}
        )
        StudentEnrollment.objects.get_or_create(student=student, class_group=klass)
        return int(created)
