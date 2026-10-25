"""يزرع خروجاً (`ClassExit`) لطلبةٍ من شعبة المعلّم الوهميّ في حصص يومٍ ليرى المعاينُ دوائرَ الخروج على خلايا الحصص (W-20261010-041).

المعاينةُ فقط (`in_preview_environment`) ومتساوي الأثر (مفتاحُ الصفّ: الحصّة والطالب ووقتُ الخروج). لا يُنشئ حصصاً ولا يمسّ الحضور: يزرع في الحصص الموجودةِ للشعبة في ذلك اليوم.
حالاتٌ بترتيب الأسماء: خروجٌ واحد؛ ثلاثةُ خروجٍ بوجهتَين في حصّةٍ واحدة؛ عيادةٌ «بإذن»؛ طالبٌ خرج من حصّتَين (دائرتان)؛ ويبقى الباقون بلا خروج.
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import CustomUser, School, StudentEnrollment
from core.preview_accounts import EMPLOYEE_NUMBERS, in_preview_environment
from operations.models import ClassExit, Session, SubjectClassAssignment

#: الجمعةُ والسبت راحةٌ في قطر (weekday(): الجمعة 4، السبت 5) — الرابطُ بلا تاريخٍ يردّ 404 فيها.
REST_WEEKDAYS = (4, 5)

#: ما يُزرع بالترتيب لكلّ طالب: قائمةُ `(فهرسُ الحصّة، الوجهة، دقيقةُ الخروج بعد بدء الحصّة، المدّةُ بالدقائق)`.
CASES = [
    [(0, "restroom", 5, 5)],
    [(0, "restroom", 4, 5), (0, "restroom", 20, 4), (0, "admin", 30, 5)],
    [(0, "clinic", 10, 10)],
    [(0, "restroom", 8, 6), (1, "admin", 12, 7)],
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
        parser.add_argument(
            "--class",
            dest="class_id",
            default="",
            help="معرّفُ الشعبة (الافتراضيّ أوّلُ شعبةٍ للمعلّم فيها 4 طلبةٍ فأكثر)",
        )
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
        self.stdout.write(self.seed(school, day, options["class_id"]))

    def seed(self, school: School, day: dt.date, class_id: str = "") -> str:
        teacher = CustomUser.objects.filter(employee_number=EMPLOYEE_NUMBERS["teacher"]).first()
        if teacher is None:
            return "لا معلّمَ وهميّ"
        assignments = SubjectClassAssignment.objects.filter(
            school=school,
            teacher=teacher,
            academic_year=academic_year_for_school(school),
            is_active=True,
            deleted_at__isnull=True,
        ).select_related("class_group")
        if class_id:
            assignments = assignments.filter(class_group_id=class_id)
        students: list[CustomUser] = []
        klass = None
        # أوّلُ شعبةٍ فيها طلبةٌ يكفون للحالات الأربع (الأخيرُ بلا خروج) — الشعبةُ الصغيرةُ تُخفي الحالات.
        for assignment in assignments.order_by("class_group__grade", "class_group__section"):
            roster = [
                e.student
                for e in StudentEnrollment.objects.filter(
                    class_group=assignment.class_group, is_active=True
                )
                .select_related("student")
                .order_by("student__full_name")
            ]
            if len(roster) > len(CASES) or class_id:
                students, klass = roster[: len(CASES)], assignment.class_group
                break
        if klass is None:
            return "لا شعبةَ للمعلّم الوهميّ فيها طلبةٌ يكفون"
        sessions = list(
            Session.objects.filter(class_group=klass, date=day).order_by(
                "period_number", "start_time"
            )
        )
        if not sessions:
            return f"لا حصصَ للشعبة {klass.short_label} بتاريخ {day} — لا شيءَ يُزرع"
        seeded = 0
        for student, exits in zip(students, CASES, strict=False):
            for index, destination, offset, minutes in exits:
                session = sessions[index % len(sessions)]
                left = timezone.make_aware(
                    dt.datetime.combine(day, session.start_time)
                ) + dt.timedelta(minutes=offset)
                ClassExit.objects.update_or_create(
                    session=session,
                    student=student,
                    left_at=left,
                    defaults={
                        "school": school,
                        "destination": destination,
                        "returned_at": left + dt.timedelta(minutes=minutes),
                        "allowed_by": teacher,
                    },
                )
                seeded += 1
        return f"زُرع {seeded} خروجاً لـ{len(students)} طالباً في {klass.short_label} بتاريخ {day}"
