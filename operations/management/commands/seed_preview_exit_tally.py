"""يزرع ملخّصَ خروجٍ يوميّاً لطلبةٍ من شعبة المعلّم الوهميّ ليرى المعاينُ دائرةَ عدد الخروج في شبكة الفصل (W-20261010-041).

المعاينةُ فقط (`in_preview_environment`) ومتساوي الأثر: يُحدِّث صفَّ (الطالب، التاريخ) ولا يضاعف. ولا يمسّ `ClassExit` ولا الحضور.
أربعُ حالات بترتيب الأسماء في أوّل شعبةٍ للمعلّم: وجهةٌ واحدة، ووجهتان، وعيادةٌ «بإذن»، وطالبٌ بلا خروج (يُترك كما هو).
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import CustomUser, School, StudentEnrollment
from core.preview_accounts import EMPLOYEE_NUMBERS, in_preview_environment
from operations.models import DailyExitTally, SubjectClassAssignment

#: الجمعةُ والسبت راحةٌ في قطر (weekday(): الجمعة 4، السبت 5) — الرابطُ بلا تاريخٍ يردّ 404 فيها.
REST_WEEKDAYS = (4, 5)

#: ما يُزرع بالترتيب: (عددٌ، ثوانٍ، تفصيلُ الوجهات).
CASES = [
    (1, 300, {"restroom": {"count": 1, "seconds": 300}}),
    (3, 840, {"restroom": {"count": 2, "seconds": 540}, "admin": {"count": 1, "seconds": 300}}),
    (1, 600, {"clinic": {"count": 1, "seconds": 600}}),
]


def last_school_day(today: dt.date) -> dt.date:
    day = today
    while day.weekday() in REST_WEEKDAYS:
        day -= dt.timedelta(days=1)
    return day


class Command(BaseCommand):
    help = "يزرع ملخّصَ خروجٍ يوميّاً لطلبة شعبة المعلّم الوهميّ (المعاينة فقط، متساوي الأثر)."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="رمزُ المدرسة (الأولى النشطة إن حُذف)")
        parser.add_argument("--date", default="", help="YYYY-MM-DD (الافتراضيّ آخرُ يومِ دوام)")

    def handle(self, *args, **options):
        if not in_preview_environment():
            raise CommandError("رُفض: ليست بيئةَ معاينة")
        schools = School.objects.filter(is_active=True)
        code = options["school"]
        school = schools.filter(code=code).first() if code else schools.order_by("code").first()
        if school is None:
            raise CommandError("لا مدرسةَ نشطة")
        try:
            day = (
                dt.date.fromisoformat(options["date"])
                if options["date"]
                else last_school_day(timezone.localdate())
            )
        except ValueError as exc:
            raise CommandError("تاريخٌ غير صالح") from exc
        self.stdout.write(self.seed(school, day))

    def seed(self, school: School, day: dt.date) -> str:
        teacher = CustomUser.objects.filter(employee_number=EMPLOYEE_NUMBERS["teacher"]).first()
        if teacher is None:
            return "لا معلّمَ وهميّ"
        assignment = (
            SubjectClassAssignment.objects.filter(
                school=school,
                teacher=teacher,
                academic_year=academic_year_for_school(school),
                is_active=True,
                deleted_at__isnull=True,
            )
            .select_related("class_group")
            .order_by("class_group__grade", "class_group__section")
            .first()
        )
        if assignment is None:
            return "لا إسنادَ للمعلّم الوهميّ"
        students = [
            e.student
            for e in StudentEnrollment.objects.filter(
                class_group=assignment.class_group, is_active=True
            )
            .select_related("student")
            .order_by("student__full_name")[: len(CASES)]
        ]
        for student, (count, seconds, detail) in zip(students, CASES, strict=False):
            DailyExitTally.objects.update_or_create(
                student=student,
                date=day,
                defaults={
                    "school": school,
                    "exit_count": count,
                    "total_seconds": seconds,
                    "by_destination": detail,
                },
            )
        return f"زُرع الخروج لـ{len(students)} طالباً في {assignment.class_group.short_label} بتاريخ {day}"
