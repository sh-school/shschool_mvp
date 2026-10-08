"""بذرُ معاينةٍ لتنبيهات الغياب «المحجوزة» (W-20261006-003، D-257م) — **للمعاينة المركزيّة 8500 لا للإنتاج**.

يُشغَّل من جلسة المعاينة (0501) داخل حاوية المعاينة، لا من جلسة التنفيذ:

    python manage.py shell < docs/preview_held_alerts_seed.py     # الخطّة (قراءةٌ فقط) — الافتراضيّ
    SEED_ACTION=up   python manage.py shell < docs/preview_held_alerts_seed.py
    SEED_ACTION=down python manage.py shell < docs/preview_held_alerts_seed.py

ما يفعله `up`: لطالبَين من شعبةٍ ذاتِ جناحٍ (ليست ESE) في أوّل مدرسةٍ نشطة، يُنشئ **خمسةَ أيّامِ غيابٍ كاملةً** (حصّةٌ وسمُها `SEED_TAG` في كلّ يوم دراسيّ من بداية العام)
ثمّ يستدعي `AttendanceService.raise_absence_alerts` فتُنشأ التنبيهاتُ «محجوزةً» كما يفعل المسحُ تماماً (لا إدخالُ صفٍّ مصنوع). ولا يرسل شيئاً لأحد.
و`down` يمحو ما وسمه فقط: الجلساتُ الموسومةُ وحضورُها وتنبيهاتُ طالبَيها **المنشأةُ بعد أوّل جلسةٍ موسومة**؛ ولا يمسّ غيرَه. ويرفض الكلَّ خارج `in_preview_environment()`.

مسارُ الاختبار بالدور بعد `up`:
  1. حسابٌ بدور «كاتب الغياب»: مشرفٌ إداريّ (`admin_supervisor`) مع منحة `wings.school_wide` (يمنحها المديرُ من شاشة المنح)؛ يدخل
     `/wings/absence-notices/` فيرى الطالبَين بتسمية العتبة «اختبار منتصف الفصل الأول»؛ ضغطُ «إصدار الإخطار» قبل انتهاء ح4 يُرفض برسالة،
     وبعدها (أو لتنبيهِ يومٍ سابق) يُرسَل ويُوسَم «تم الإبلاغ». وإعادةُ الضغط تُرفض (لا إخطارَ مزدوج).
  2. مشرفُ جناحٍ بلا منحة، ومعلّم: `/wings/absence-notices/` ← 404.
  3. التحقّقُ من عدم الإرسال التلقائيّ: `python manage.py absence_alerts_report` — المحجوز لا يظهر في «معلَّقةٌ سيرسلها 07:00».
"""

import datetime as dt
import os

from django.utils import timezone

from core.preview_accounts import in_preview_environment

# حارسٌ أوّلَ سطرٍ ينفَّذ (ملاحظة 0104): يرفض خارجَ المعاينة المركزيّة كائناً ما كانت القاعدة، بما فيها الإنتاجُ وقواعدُ الجلسات.
if not in_preview_environment():
    raise SystemExit(
        "مرفوض: هذا البذرُ للمعاينة المركزيّة وحدَها (in_preview_environment) — لا يُشغَّل على إنتاجٍ ولا قاعدةِ جلسة"
    )

SEED_TAG = "preview-held-alerts-seed"
ACTION = os.environ.get("SEED_ACTION", "plan")
STUDENTS = 2
DAYS = 5

from core.academic_calendar import academic_year_window  # noqa: E402
from core.models import School, StudentEnrollment  # noqa: E402
from operations.attendance_policy import is_special_education  # noqa: E402
from operations.models import AbsenceAlert, Session, StudentAttendance  # noqa: E402
from operations.services import AttendanceService  # noqa: E402

school = School.objects.filter(is_active=True).order_by("code").first()
window = academic_year_window(school)
print(f"[مدرسة] {school.code} | نافذةُ العام: {window}")


def _picks():
    chosen = []
    for enrollment in (
        StudentEnrollment.objects.filter(is_active=True, class_group__school=school)
        .select_related("class_group", "student")
        .order_by("class_group__grade", "class_group__section", "student__full_name")
    ):
        klass = enrollment.class_group
        if klass.wing_id is None or is_special_education(klass):
            continue
        chosen.append(enrollment)
        if len(chosen) == STUDENTS:
            break
    return chosen


def _teacher_of(klass):
    from operations.models import SubjectClassAssignment

    link = (
        SubjectClassAssignment.objects.filter(school=school, class_group=klass)
        .select_related("teacher")
        .first()
    )
    return link.teacher if link else None


tagged = Session.objects.filter(school=school, notes=SEED_TAG)
picks = _picks()
print(
    f"[خطّة] طلابٌ مختارون: {[e.student.full_name for e in picks]} | جلساتٌ موسومةٌ قائمة: {tagged.count()}"
)

#: خاناتٌ خارجَ الدوام لا يشغلها جدولٌ عادةً؛ ويُتحقَّق مع ذلك من عدم التداخل مع جلساتِ المعلّم والشعبة القائمة قبل كلّ إنشاء.
FREE_SLOTS = (
    (dt.time(5, 0), dt.time(5, 45)),
    (dt.time(5, 50), dt.time(6, 35)),
    (dt.time(19, 0), dt.time(19, 45)),
)
SEARCH_DAYS = 120


def _free_slot(teacher, klass, day):
    """أوّلُ خانةٍ لا تتداخل مع أيّ جلسةٍ قائمةٍ لهذا المعلّم أو هذه الشعبة في اليوم، وإلا `None` (فيتخطّى البذرُ اليومَ)."""
    from django.db.models import Q

    existing = Session.objects.filter(Q(teacher=teacher) | Q(class_group=klass), date=day)
    for start_time, end_time in FREE_SLOTS:
        if not existing.filter(start_time__lt=end_time, end_time__gt=start_time).exists():
            return start_time, end_time
    return None


if ACTION == "up":
    from django.db import transaction

    from operations.school_days import is_school_day

    if tagged.exists():
        raise SystemExit("البذرُ قائمٌ — شغّل down أوّلاً")
    start = window[0]
    created = 0
    # كلُّ up معاملةٌ واحدة: أيُّ فشلٍ (قيدٌ أو نقصُ أيّام) يتراجع كلُّه فلا تبقى جلساتٌ موسومةٌ جزئيّة.
    with transaction.atomic():
        for enrollment in picks:
            klass = enrollment.class_group
            teacher = _teacher_of(klass)
            if teacher is None:
                print(f"تخطّي {klass}: لا معلّمَ مُسنَد")
                continue
            made = 0
            last_day = start
            for offset in range(SEARCH_DAYS):
                if made == DAYS:
                    break
                day = start + dt.timedelta(days=offset)
                # أيّامٌ دراسيّةٌ لا جلسةَ فيها للشعبة أصلاً: فيكتمل غيابُ اليوم (لا حصصٌ أخرى بلا رصد تُبقيه «غيرَ محسوم»)
                if (
                    not is_school_day(school, day)
                    or Session.objects.filter(class_group=klass, date=day).exists()
                ):
                    continue
                slot = _free_slot(teacher, klass, day)
                if slot is None:
                    continue
                session = Session.objects.create(
                    school=school,
                    class_group=klass,
                    teacher=teacher,
                    date=day,
                    start_time=slot[0],
                    end_time=slot[1],
                    status="completed",
                    notes=SEED_TAG,
                )
                StudentAttendance.objects.create(
                    session=session,
                    student=enrollment.student,
                    school=school,
                    status="absent",
                    excuse_type="",
                    source="teacher",
                )
                made += 1
                created += 1
                last_day = day
            if made < DAYS:
                raise SystemExit(
                    f"تعذّر إيجاد {DAYS} أيّامٍ خاليةٍ للشعبة {klass} خلال {SEARCH_DAYS} يوماً — تراجع البذرُ كلُّه"
                )
            raised = AttendanceService.raise_absence_alerts(enrollment.student, school, on=last_day)
            print(f"{enrollment.student.full_name}: تنبيهاتٌ محجوزة جديدة = {len(raised)}")
    print(f"تم: {created} جلسةً موسومة. الوقت: {timezone.now():%Y-%m-%d %H:%M}")
elif ACTION == "down":
    # نطاقُ المحو الضيّق: تنبيهاتُ طالبَي البذر **المنشأةُ منذ أوّل جلسةٍ موسومة** فقط (لا ما سبقها من تنبيهاتٍ قائمة)، ثمّ الجلساتُ الموسومةُ وحضورُها.
    first = tagged.order_by("created_at").first()
    ids = set(
        StudentAttendance.objects.filter(session__in=tagged).values_list("student_id", flat=True)
    )
    alerts = AbsenceAlert.objects.filter(
        school=school,
        student_id__in=ids,
        created_at__gte=first.created_at if first else timezone.now(),
    )
    removed_alerts = alerts.count()
    alerts.delete()
    removed = tagged.count()
    StudentAttendance.objects.filter(session__in=tagged).delete()
    tagged.delete()
    print(f"محوٌ: {removed} جلسةً موسومةً و{removed_alerts} تنبيهاً أُنشئ بعد البذر لـ{len(ids)} طالباً.")
else:
    print("الخطّةُ فقط (قراءة). للتنفيذ: SEED_ACTION=up | down")
