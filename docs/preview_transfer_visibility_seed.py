"""بذرُ معاينةٍ لظهور الطالب المنقول في شعبته القديمة (W-20261010-017، D-323م) — **للمعاينة المركزيّة 8500 وحدَها**.

يُشغَّل من جلسة المعاينة (0501/0502) داخل حاوية المعاينة، لا من جلسة التنفيذ:

    python manage.py shell < docs/preview_transfer_visibility_seed.py     # الخطّة (قراءةٌ فقط) — الافتراضيّ
    SEED_ACTION=up   python manage.py shell < docs/preview_transfer_visibility_seed.py
    SEED_ACTION=down python manage.py shell < docs/preview_transfer_visibility_seed.py

`up`: يختار طالباً بقيدٍ نشطٍ في شعبةٍ ذات جناح (ليست ESE) وشعبةً ثانيةً من الصفّ والعام والمدرسة نفسِها، فيُنقله
كما يفعل الإتمامُ الداخليّ: يُطفئ القيدَ القديم ويكتب `left_at` = يوم النقل − 1، وينشئ قيداً جديداً من يوم النقل.
يومُ النقل افتراضاً ثالثُ يوم دراسةٍ سابق (يُغيَّر بـ`SEED_MOVE=YYYY-MM-DD`). ويطبع الرابطين اللذين يُقارَنان.
`down`: يعكس ما بُذر بـ`SEED_MOVE` نفسِه (يحذف القيدَ الجديد، ويعيد القديمَ نشطاً بلا `left_at`).
"""

import datetime as dt
import os

from django.utils import timezone

from core.preview_accounts import in_preview_environment

if not in_preview_environment():
    raise SystemExit("مرفوض: هذا البذرُ للمعاينة المركزيّة وحدَها (in_preview_environment).")

ACTION = os.environ.get("SEED_ACTION", "plan")

from core.models import ClassGroup, School, StudentEnrollment  # noqa: E402
from operations.attendance_policy import is_special_education  # noqa: E402


def _move_day() -> dt.date:
    explicit = os.environ.get("SEED_MOVE")
    if explicit:
        return dt.date.fromisoformat(explicit)
    day, back = timezone.localdate(), 0
    while back < 3:
        day -= dt.timedelta(days=1)
        if day.weekday() not in (4, 5):  # الجمعة والسبت عطلة
            back += 1
    return day


school = School.objects.filter(is_active=True).order_by("code").first()
move = _move_day()
before = move - dt.timedelta(days=1)

if ACTION == "down":
    for old in StudentEnrollment.objects.filter(
        left_at=before, is_active=False, class_group__school=school
    ):
        moved = StudentEnrollment.objects.filter(
            student=old.student, is_active=True, enrolled_at=move
        ).exclude(class_group=old.class_group)
        if moved.exists():
            moved.delete()
            old.is_active, old.left_at = True, None
            old.save(update_fields=["is_active", "left_at"])
            print(f"[down] أُعيد قيدُ الطالب {old.student.pk} إلى {old.class_group}.")
    raise SystemExit(0)

enrollment = None
for candidate in (
    StudentEnrollment.objects.filter(
        is_active=True, left_at__isnull=True, class_group__school=school
    )
    .select_related("class_group", "student")
    .order_by("class_group__grade", "class_group__section", "student__full_name")
):
    klass = candidate.class_group
    if klass.wing_id is None or is_special_education(klass):
        continue
    target = (
        ClassGroup.objects.filter(
            school=school, grade=klass.grade, academic_year=klass.academic_year, is_active=True
        )
        .exclude(pk=klass.pk)
        .order_by("section")
        .first()
    )
    if target is not None:
        enrollment, destination = candidate, target
        break

if enrollment is None:
    raise SystemExit("لا طالبَ بقيدٍ نشطٍ وشعبةٍ ثانيةٍ من صفّه — لا شيءَ يُنقل.")

source = enrollment.class_group
print(f"[مدرسة] {school.code} | يوم النقل {move} | آخرُ يومٍ في القديمة {before}")
print(f"[طالب] {enrollment.student.pk} (رقمٌ داخليّ لا اسم) | من {source} إلى {destination}")
print(f"  القديمة قبل النقل: /teacher/classes/{source.pk}/grid/?date={before}   ← يظهر")
print(f"  القديمة يوم النقل: /teacher/classes/{source.pk}/grid/?date={move}   ← لا يظهر")
print(f"  الجديدة قبل النقل: /teacher/classes/{destination.pk}/grid/?date={before}   ← لا يظهر")
print(f"  الجديدة يوم النقل: /teacher/classes/{destination.pk}/grid/?date={move}   ← يظهر")

if ACTION == "up":
    if enrollment.enrolled_at > before:
        enrollment.enrolled_at = before - dt.timedelta(days=30)
    enrollment.is_active = False
    enrollment.left_at = before
    enrollment.save(update_fields=["enrolled_at", "is_active", "left_at"])
    StudentEnrollment.objects.get_or_create(
        student=enrollment.student, class_group=destination, defaults={"enrolled_at": move}
    )
    print("[تمّ] النقل بُذر.")
else:
    print("[خطّة] لم يُكتب شيء — SEED_ACTION=up للتنفيذ.")
