"""بياناتٌ مستعارةٌ كلُّها لتصوير «دليل المعلّم» — لا شخصَ حقيقيّاً ولا رقماً حقيقيّاً فيها.

يُشغَّل على قاعدةٍ فارغةٍ مهجَّرة (لا على الإنتاج ولا على قاعدة جلسة):

    DJANGO_SETTINGS_MODULE=shschool.settings.development DB_NAME=guide_demo python manage.py shell < docs/guides/teacher_guide_v0_1/seed_demo.py

الدخول بعدها: الرقمُ الوظيفيّ 70001 وكلمةُ المرور `Demo-Pass-2026!`.
"""

import datetime as dt
import json
import pathlib
from decimal import Decimal

import django

django.setup()

from assessments.models import (
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    SubjectClassSetup,
)

# noqa: E402
from core.academic_calendar import academic_year_for_school  # noqa: E402
from core.models import TimeBand, Wing  # noqa: E402
from operations.models import ScheduleSlot, Session, Subject, TimeSlotConfig  # noqa: E402
from tests.conftest import (  # noqa: E402
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

PASSWORD = "Demo-Pass-2026!"  # pragma: allowlist secret
TODAY = dt.date.fromisoformat("2026-10-05")  # الإثنين
NAMES = [
    "راشد سعيد المهندي",
    "ناصر علي الهاجري",
    "يوسف حمد الكبيسي",
    "سلطان جاسم النعيمي",
    "عبدالله فهد السليطي",
    "مبارك خالد الدرهم",
    "حمد ثاني العبدالله",
    "فيصل منصور الشمري",
    "إبراهيم عيسى الأنصاري",
    "سعود ماجد الرميحي",
    "بدر محمد الحمادي",
    "طلال أحمد الجابر",
    "زياد عمر الخاطر",
    "تميم يعقوب المسلماني",
    "جاسم صالح العطية",
    "هاشم كمال الفخرو",
]

school = SchoolFactory(
    name=json.loads((pathlib.Path(__file__).parent / "meta.json").read_text(encoding="utf-8"))[
        "school"
    ],
    code="DEMO01",
)
year = academic_year_for_school(school)
teacher_role = RoleFactory(school=school, name="teacher")
teacher = UserFactory(full_name="أحمد سالم الكعبي", national_id="29000000001", password=PASSWORD)
teacher.employee_number = "70001"
teacher.save()
MembershipFactory(user=teacher, school=school, role=teacher_role)
colleague = UserFactory(full_name="محمود يوسف الحيدر", national_id="29000000002", password=PASSWORD)
colleague.employee_number = "70002"
colleague.save()
MembershipFactory(user=colleague, school=school, role=teacher_role)
holder = UserFactory(full_name="جابر ناصر المري", national_id="29000000003", password=PASSWORD)
holder.employee_number = "70003"
holder.save()
MembershipFactory(
    user=holder, school=school, role=RoleFactory(school=school, name="admin_supervisor")
)

band = TimeBand.objects.create(school=school, code="ground", name="الأرضيّ", floor="ground")
BELLS = [
    (1, dt.time(7, 10), dt.time(7, 55)),
    (2, dt.time(8, 0), dt.time(8, 45)),
    (3, dt.time(8, 50), dt.time(9, 35)),
    (4, dt.time(10, 0), dt.time(10, 45)),
    (5, dt.time(10, 50), dt.time(11, 35)),
    (6, dt.time(11, 40), dt.time(12, 25)),
    (7, dt.time(12, 45), dt.time(13, 30)),
]
for number, start, end in BELLS:
    TimeSlotConfig.objects.create(
        school=school,
        band=band,
        day_type="regular",
        period_number=number,
        start_time=start,
        end_time=end,
        is_break=False,
    )

wing = Wing.objects.create(
    school=school, code="w1", name="جناح 1", academic_year=year, supervisor=holder
)
klass = ClassGroupFactory(
    school=school, grade="G7", section="1", level_type="prep", academic_year=year, wing=wing
)
klass2 = ClassGroupFactory(
    school=school, grade="G7", section="2", level_type="prep", academic_year=year, wing=wing
)
student_role = RoleFactory(school=school, name="student")
students = []
for index, name in enumerate(NAMES):
    kid = UserFactory(full_name=name, national_id=f"290000{index + 10:05d}")
    MembershipFactory(user=kid, school=school, role=student_role)
    StudentEnrollmentFactory(
        student=kid,
        class_group=klass if index < 12 else klass2,
        enrolled_at=TODAY - dt.timedelta(days=34),
    )
    students.append(kid)

math = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
science = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
for period, subject, group in (
    (1, math, klass),
    (2, math, klass),
    (3, science, klass2),
    (5, math, klass2),
):
    start, end = BELLS[period - 1][1:]
    ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=group,
        subject=subject,
        day_of_week=1,
        period_number=period,
        start_time=start,
        end_time=end,
        academic_year=year,
    )
    Session.objects.create(
        school=school,
        class_group=group,
        teacher=teacher,
        subject=subject,
        date=TODAY,
        start_time=start,
        end_time=end,
        period_number=period,
        status="scheduled",
    )

setup = SubjectClassSetup.objects.create(
    school=school, subject=math, class_group=klass, teacher=teacher, academic_year=year
)
package = AssessmentPackage.objects.create(
    setup=setup,
    school=school,
    package_type="P1",
    semester="S1",
    weight=Decimal("37.5"),
    semester_max_grade=Decimal("40"),
)
quiz = Assessment.objects.create(
    package=package,
    school=school,
    title="اختبار قصير — الأعداد الصحيحة",
    max_grade=Decimal("20"),
    weight_in_package=Decimal("100"),
    status="published",
)
for index, kid in enumerate(students[:8]):
    StudentAssessmentGrade.objects.create(
        assessment=quiz, student=kid, school=school, grade=Decimal(str(12 + (index * 3) % 8))
    )

print("OK", school.id, klass.id, setup.id, quiz.id)
