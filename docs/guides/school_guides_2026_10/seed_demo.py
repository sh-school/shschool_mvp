"""بياناتٌ مستعارةٌ كلُّها لتصوير دليلَي المعلّم ومشرف الجناح — لا شخصَ حقيقيّاً ولا رقماً حقيقيّاً فيها.

يُشغَّل على قاعدةٍ فارغةٍ مهجَّرة (لا الإنتاج ولا قاعدة جلسة):

    DJANGO_SETTINGS_MODULE=shschool.settings.development DB_NAME=guide_demo python manage.py shell < docs/guides/school_guides_2026_10/seed_demo.py

الحسابات (كلمةُ المرور `Demo-Pass-2026!`): المعلّم 70001، معلّما الجناح الرابع 70002 و70005، مشرفُ الجناح الرابع 70003، النائب الإداريّ 70004.
اليومُ في الصور: الإثنين، والساعةُ 09:20 بتوقيت الدوحة (يثبّتها `run_demo_server.py`).
"""

import datetime as dt
import json
import pathlib

import django

django.setup()

from django.db import transaction  # noqa: E402

transaction.set_autocommit(False)  # أيُّ خطأ يُلغي البذرَ كلَّه فيُعاد بلا إعادة تهجير

from django.core.management import call_command  # noqa: E402

from core.academic_calendar import academic_year_for_school  # noqa: E402
from core.management.commands.seed_wings import WINGS  # noqa: E402
from core.models import AcademicYear, ClassGroup, ParentStudentLink, Wing  # noqa: E402
from operations.attendance_entries import decide_entry, submit_entry  # noqa: E402
from operations.excuses import grant_excuse  # noqa: E402
from operations.guardian_contact import log_contact  # noqa: E402
from operations.models import (
    ClassExit,
    ScheduleSlot,
    Session,
    Subject,
    SubjectClassAssignment,
    TimeSlotConfig,
)

# noqa: E402
from operations.period_register import confirm_period  # noqa: E402
from tests.conftest import (  # noqa: E402
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

META = json.loads(
    pathlib.Path("docs/guides/school_guides_2026_10/meta.json").read_text(encoding="utf-8")
)
PASSWORD = "Demo-Pass-2026!"  # pragma: allowlist secret
TODAY = dt.date.fromisoformat("2026-10-05")  # الإثنين
DOHA = dt.timezone(dt.timedelta(hours=3))


def at(day, hour, minute):
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=DOHA)


FIRST = [
    "راشد", "ناصر", "يوسف", "سلطان", "عبدالله", "مبارك", "حمد", "فيصل", "إبراهيم", "سعود",
    "بدر", "طلال", "زياد", "تميم", "جاسم", "هاشم", "خليفة", "علي", "محمد", "أحمد",
]  # fmt: skip
FAMILY = [
    "المهندي", "الهاجري", "الكبيسي", "النعيمي", "السليطي", "الدرهم", "العبدالله", "الشمري", "الأنصاري", "الرميحي",
    "الحمادي", "الجابر", "الخاطر", "المسلماني", "العطية", "الفخرو", "المري", "الكعبي", "الحيدر", "البنعلي",
]  # fmt: skip

school = SchoolFactory(name=META["school"], code="DEMO01")
AcademicYear.objects.create(
    school=school,
    name="2026-2027",
    start_date=dt.date.fromisoformat("2026-09-01"),
    end_date=dt.date.fromisoformat("2027-06-30"),
    is_current=True,
)
year = academic_year_for_school(school)
roles = {
    n: RoleFactory(school=school, name=n)
    for n in ("teacher", "admin_supervisor", "vice_admin", "student", "parent")
}


def staff(name, number, role, nid):
    user = UserFactory(full_name=name, national_id=nid, password=PASSWORD)
    user.employee_number = number
    user.save()
    MembershipFactory(user=user, school=school, role=roles[role])
    return user


t1 = staff("أحمد سالم الكعبي", "70001", "teacher", "29000000001")
t2 = staff("محمود يوسف الحيدر", "70002", "teacher", "29000000002")
t3 = staff("عمر خالد النعيمي", "70005", "teacher", "29000000005")
t4 = staff("ياسر ماجد الدوسري", "70006", "teacher", "29000000006")
t5 = staff("سالم راشد الكواري", "70007", "teacher", "29000000007")
t6 = staff("حسن علي الأنصاري", "70008", "teacher", "29000000008")
sup = staff("جابر ناصر المري", "70003", "admin_supervisor", "29000000003")
vice = staff("خالد عبدالله المهندي", "70004", "vice_admin", "29000000004")

# ── الشُّعب الخمس والعشرون والأجنحة والأجراس (الأوامرُ نفسُها المستعملة في الإنتاج) ──
for code, _name, _floor, _order, sections in WINGS:
    for grade, section in sections:
        ClassGroup.objects.create(
            school=school, grade=grade, section=section, academic_year=year,
            level_type="prep" if grade in ("G7", "G8", "G9") else "sec",
        )  # fmt: skip
call_command("seed_wings", "--assign")
call_command("seed_time_bands", "--assign")
wing4 = Wing.objects.get(school=school, code="w4")
wing4.supervisor = sup
wing4.save()

math = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
science = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


def klass(grade, section):
    return ClassGroup.objects.get(school=school, grade=grade, section=section, academic_year=year)


# ── الطلبة: ثماني طلابٍ لكلّ شعبةٍ في الجناحين 1 و4 ──
students = {}
counter = 0
for wing_code in ("w1", "w4"):
    for grade, section in next(w for w in WINGS if w[0] == wing_code)[4]:
        group = klass(grade, section)
        kids = []
        for _ in range(8):
            name = f"{FIRST[counter % 20]} {FIRST[(counter * 3 + 7) % 20]} {FAMILY[(counter * 7 + 3) % 20]}"
            counter += 1
            kid = UserFactory(full_name=name, national_id=f"291{counter:08d}")
            MembershipFactory(user=kid, school=school, role=roles["student"])
            StudentEnrollmentFactory(
                student=kid, class_group=group, enrolled_at=TODAY - dt.timedelta(days=34)
            )
            kids.append(kid)
        students[(grade, section)] = kids

# أولياء أمورٍ بهواتف (تظهر في ملفّ الغياب)
for index, kid in enumerate(students[("G10", "4")][:4] + students[("G11", "1")][:3]):
    parent = UserFactory(
        full_name=f"والد {kid.full_name.split()[0]}",
        national_id=f"292{index:08d}",
        phone=f"+9745500{index:04d}",
    )
    MembershipFactory(user=parent, school=school, role=roles["parent"])
    ParentStudentLink.objects.create(school=school, parent=parent, student=kid)

# ── إسنادُ المعلّمين (الرصدُ المؤقّت يقرأ منه) ──
for grade, section in (("G7", "1"), ("G7", "2"), ("G7", "3")):
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass(grade, section),
        subject=math,
        teacher=t1,
        weekly_periods=5,
        academic_year=year,
    )
# جدولُ المعلّم الأوّل في المنصّة (يقرؤه «مركز معلومات الطلبة» لتحديد شُعبه): 7/1 في الحصّة 3 وأخواتها في الأولى والثانية
for day, (grade, section), number, start, end in (
    (1, ("G7", "1"), 3, "08:50", "09:35"), (1, ("G7", "2"), 1, "07:10", "08:00"), (3, ("G7", "3"), 2, "08:00", "08:50"),
):  # fmt: skip
    ScheduleSlot.objects.create(
        school=school, teacher=t1, class_group=klass(grade, section), subject=math, day_of_week=day,
        period_number=number, start_time=dt.time.fromisoformat(start), end_time=dt.time.fromisoformat(end), academic_year=year,
    )  # fmt: skip
TEACHING = (
    (("G10", "4"), t4, math), (("G11", "1"), t2, math), (("G11", "2"), t3, science),
    (("G11", "3"), t5, science), (("G11", "4"), t6, math),
)  # fmt: skip
for (grade, section), teacher, subject in TEACHING:
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass(grade, section),
        subject=subject,
        teacher=teacher,
        weekly_periods=5,
        academic_year=year,
    )


# ── حصصُ اليوم لشُعب الجناح الرابع (من أجراس نطاقاتها الفعليّة) ──
def bell(group, number, day_type="regular"):
    return TimeSlotConfig.objects.get(
        school=school, band=group.time_band, day_type=day_type, period_number=number
    )


sessions = {}
for (grade, section), teacher, subject in TEACHING:
    group = klass(grade, section)
    for number in (1, 2, 3, 4):
        row = bell(group, number)
        sessions[(grade, section, number)] = Session.objects.create(
            school=school, class_group=group, teacher=teacher, subject=subject, date=TODAY,
            start_time=row.start_time, end_time=row.end_time, period_number=number, status="scheduled",
        )  # fmt: skip


def confirm(grade, section, number, marks, minutes_after_start=8):
    group = klass(grade, section)
    row = bell(group, number)
    now = at(TODAY, row.start_time.hour, row.start_time.minute) + dt.timedelta(
        minutes=minutes_after_start
    )
    confirm_period(group, TODAY, row.start_time, marks, sup, now=now)


def marks_of(kids, absent=(), late=()):
    out = {}
    for i in absent:
        out[str(kids[i].id)] = {"status": "absent"}
    for i, mins in late:
        out[str(kids[i].id)] = {"status": "late", "late_minutes": mins}
    return out


k104, k111, k112, k113, k114 = (
    students[k] for k in (("G10", "4"), ("G11", "1"), ("G11", "2"), ("G11", "3"), ("G11", "4"))
)
confirm("G10", "4", 1, marks_of(k104, absent=(0, 3)))
confirm("G10", "4", 2, marks_of(k104, absent=(0, 3), late=((5, 6),)))
confirm("G11", "1", 1, marks_of(k111, absent=(1,), late=((4, 9),)))
confirm("G11", "1", 2, marks_of(k111, absent=(1,)))
# G11/2: الحصّة 1 فاتت بلا تثبيت («لم تُرصد») — والثانية ثُبّتت متأخّرة
confirm("G11", "2", 2, marks_of(k112, absent=(2,)), minutes_after_start=70)
confirm("G11", "3", 1, marks_of(k113, absent=(6,)))
confirm("G11", "3", 2, marks_of(k113, absent=(6,), late=((1, 7),)))
confirm("G11", "4", 1, marks_of(k114, late=((0, 11),)))

# ── إدخالاتُ المعلّمين المبدئيّة بانتظار اعتماد المشرف (الحصّة 3 الجارية) ──
now_entry = at(TODAY, 9, 5)
for (grade, section), kids, teacher, picks in (
    (("G11", "1"), k111, t2, ((0, "absent", None), (3, "late", 8))),
    (("G11", "4"), k114, t6, ((2, "absent", None), (5, "late", 5))),
    (("G11", "2"), k112, t3, ((1, "absent", None),)),
):  # fmt: skip
    session = sessions[(grade, section, 3)]
    for index, status, minutes in picks:
        submit_entry(
            teacher, session, kids[index], status, now=now_entry, tardiness_minutes=minutes
        )
entry = submit_entry(t4, sessions[("G10", "4", 3)], k104[6], "absent", now=now_entry)
decide_entry(sup, entry, True, now=at(TODAY, 9, 10))

# ── خروجٌ مفتوح من الحصّة 3 ──
ClassExit.objects.create(
    school=school, session=sessions[("G10", "4", 3)], student=k104[2], destination="clinic",
    left_at=at(TODAY, 9, 2), allowed_by=t4,
)  # fmt: skip

# ── تاريخُ الغياب (لملفّ غياب الطالب وعتبات الحرمان) ──
past_days = [
    TODAY - dt.timedelta(days=n) for n in (1, 4, 5, 6, 7)
]  # أحد، خميس، أربعاء، ثلاثاء، إثنين
history = {}
for day in past_days:
    for number in (1, 2):
        row = bell(klass("G10", "4"), number)
        history[(day, number)] = Session.objects.create(
            school=school, class_group=klass("G10", "4"), teacher=t4, subject=math, date=day,
            start_time=row.start_time, end_time=row.end_time, period_number=number, status="completed",
        )  # fmt: skip
heavy, medium, excused = k104[1], k104[4], k104[7]
for index, day in enumerate(past_days):  # الثقيلُ خمسةُ أيّامٍ بلا عذر، والمتوسّطُ أربعةٌ، ويومٌ بعذرٍ مقبول
    absent = [heavy] + ([medium] if index < 4 else []) + ([excused] if index == 0 else [])
    for number in (1, 2):
        row = bell(klass("G10", "4"), number)
        marks = {str(kid.id): {"status": "absent"} for kid in absent}
        confirm_period(klass("G10", "4"), day, row.start_time, marks, sup, now=at(day, 13, 0))
grant_excuse(
    student=excused, school=school, date_from=past_days[0], date_to=past_days[0], kind="bereavement",
    notes="وفاة الجدّ — قرابةٌ من الدرجة الأولى", by=sup, today=TODAY,
)  # fmt: skip
log_contact(
    student=heavy,
    school=school,
    absence_date=past_days[0],
    outcome="no_answer",
    by=sup,
    note="",
    now=at(TODAY, 8, 30),
)
log_contact(
    student=heavy,
    school=school,
    absence_date=past_days[0],
    outcome="answered",
    by=sup,
    note="",
    now=at(TODAY, 8, 45),
)

transaction.commit()
print(
    "OK",
    school.id,
    klass("G11", "1").id,
    klass("G11", "2").id,
    klass("G10", "4").id,
    heavy.id,
    klass("G7", "1").id,
)
