"""بذرٌ محدودٌ ومُعلَن: ستُّ حصصٍ لليوم لحساب المعلّم الوهميّ على 8500 — لقياس أساس لوحة المعلّم (W-20261003-023).

لا يُشغَّل من هنا تلقائيّاً ولا يشغّله غيرُ 0501 بعد إذن المالك. يُنفَّذ داخل حاوية ويب المعاينة بـ`manage.py shell` (stdin)
ومتغيّر البيئة `TEACHER_SEED_ACTION`:

    up    : ستُّ حصصٍ (`scheduled`) بتاريخ اليوم بتوقيت الدوحة لحساب المعلّم الوهميّ (رقمُه من `core.preview_accounts.EMPLOYEE_NUMBERS`)
            — مواقيتُها وموادُّها من **الجدول المعتمَد** (`ScheduleSlot` الفعّالة لليوم الأسبوعيّ نفسِه)؛ ولا يُرتجل وقتٌ: إن قلّت فتراتُه عن ستٍّ رُفض.
            الشعبُ ممّا لا حصّةَ لها في الوقت نفسِه (يحلّ `_solve` توزيعاً كاملاً: ستُّ فتراتٍ من فترات الجدول، وفترةُ رصد الجناح تُختار حيث تخلو شعبةُ جناح، لا فترةً ثابتة) (لا يصطدم قيدا `no_teacher_time_overlap` و`no_class_time_overlap`).
            حصّةُ رصد الجناح لشعبةٍ **في جناحٍ** وفيها طلبةٌ نشطون، والخمسُ الباقياتُ لشعبٍ بلا جناحٍ أوّلاً ثمّ بجناحٍ عند النقص (بلا تغيير مشرف أيّ جناح). وحالاتُ الرصد:
              ١ رصدُ الجناح (الوسمُ [جناح الرصد]) : طالبٌ بإدخالٍ **معتمَد** (submit_entry ثمّ decide_entry بالحاملِ الفعليّ)، وآخرُ بإدخالٍ **بانتظار الاعتماد**، والباقي فارغ.
              ٢ و٣    : رصدٌ مكتملٌ لطالبَين (حاضر ومتأخّر) فتصير الحصّةُ `completed`.
              ٤ و٥ و٦ : فارغةٌ `scheduled`.
            وكلُّ حصّةٍ موسومةٌ في `notes` بـ«[معاينة المعلّم]».
    plan  : قراءةٌ فقط **لا تكتب شيئاً**: يطبع فتراتِ الجدول وعددَ الشعب المشغولة في كلّ فترة (بالرمز لا بالأسماء) والحلَّ الكامل المقترح أو سببَ تعذّره.
    who   : قراءةٌ فقط: يطبع ما بُذر وحالةَ كلّ حصّة.
    down  : يمحو ما وُسم: صفوفَ `StudentAttendance` للحصص الموسومة، ثمّ الإدخالاتِ والقراراتِ عبر `erase_attendance_ledger`
            (المسارُ الوحيد المسموح له بالحذف من السجلّ الملحق) — **لطالبٍ كلُّ إدخالاته في حصصٍ موسومة وحدَها**؛ طالبٌ له إدخالٌ في حصّةٍ
            غيرِ موسومة يُتخطّى ويُطبع اسمُ السبب (لا يُمحى سجلُّ الحصص الحقيقيّة). ثمّ الحصصَ الموسومة. سطورُ التدقيق تبقى.

حدودٌ مقصودة: **يرفض خارج بيئة المعاينة** (`in_preview_environment()`)، ويرفض إن لم يكن حسابُ المعلّم موجوداً وموسوماً وسماً مركَّباً
(شغّل `preview_accounts --sync` أوّلاً)، ولا يغيّر مشرفَ أيّ جناحٍ ولا أيَّ حسابٍ ولا الجدولَ المعتمَد. التشغيلُ ثانيةً لـup بلا تغيير (متساوي الأثر).
نافذةُ الإدخال في `attendance_policy.can_enter` يوميّةٌ لا بالحصّة؛ فإن رُفض الإدخالُ لخروج ساعة المعاينة عن اليوم الدراسيّ طُبع السببُ ويبقى الباقي.
"""

import itertools
import os
import sys

from django.db import transaction
from django.utils import timezone

from core.models import ClassGroup, CustomUser, School, StudentEnrollment
from core.preview_accounts import EMPLOYEE_NUMBERS, in_preview_environment, is_preview_account
from operations.attendance_entries import (
    EntryError,
    decide_entry,
    erase_attendance_ledger,
    submit_entry,
)
from operations.models import AttendanceEntry, ScheduleSlot, Session, StudentAttendance

MARK = "[معاينة المعلّم]"
ACTION = os.environ.get("TEACHER_SEED_ACTION", "")
BASE = "http://localhost:8500"
SESSIONS = 6
ENTRY_TAG = "[جناح الرصد]"


def _refuse(message):
    print(f"رُفض: {message}")
    sys.exit(1)


def _teacher():
    user = CustomUser.objects.filter(employee_number=EMPLOYEE_NUMBERS["teacher"]).first()
    if user is None:
        _refuse("لا حسابَ معلّمٍ وهميٍّ بهذا الرقم — شغّل preview_accounts --sync أوّلاً")
    if not is_preview_account(user):
        _refuse("الحسابُ ليس موسوماً وسماً مركَّباً — لا أمسّ حساباً حقيقيّاً")
    return user


def _marked():
    return Session.objects.filter(notes__contains=MARK)


def _period_times(school, today):
    """كلُّ فترات الجدول المعتمَد ليومٍ أسبوعيٍّ مطابق: [(بدء، نهاية، مادّة)] مرتّبةً بالفترة."""
    day = (today.weekday() + 1) % 7  # الأحد=0 في ScheduleSlot
    if day > 4:
        day = 0
    rows = {}
    for slot in (
        ScheduleSlot.objects.filter(school=school, is_active=True, day_of_week=day)
        .select_related("subject")
        .order_by("period_number", "id")
    ):
        rows.setdefault(slot.period_number, (slot.start_time, slot.end_time, slot.subject))
    return [rows[p] for p in sorted(rows)]


def _label(group):
    return str(group.short_label)


def _groups(school):
    """(شعبُ الجناح الصالحة للرصد، شعبٌ بلا جناح) — بالرمز لا بالأسماء."""
    base = ClassGroup.objects.filter(
        school=school, is_active=True, enrollments__is_active=True
    ).distinct()
    wing = list(
        base.filter(wing__isnull=False, wing__is_active=True)
        .exclude(section__iendswith="ESE")
        .order_by("grade", "section")
    )
    plain = list(base.filter(wing__isnull=True).order_by("grade", "section"))
    return wing, plain


def _busy(today):
    """{وقتُ البدء: شعبٌ لها حصّةٌ فيه اليوم} — فيُرفض الاصطدامُ بقيد no_class_time_overlap."""
    busy = {}
    for start, group_id in Session.objects.filter(date=today).values_list(
        "start_time", "class_group_id"
    ):
        busy.setdefault(start, set()).add(group_id)
    return busy


def _solve(periods, wing, plain, busy):
    """يوزّع ستّ فتراتٍ على ستّ شعبٍ مختلفة: فترةٌ واحدةٌ لشعبةِ جناحٍ (رصد الجناح)، والباقياتُ بلا جناحٍ أوّلاً ثمّ بجناح.

    يجرّب كلَّ اختيارِ ستٍّ من الفترات المتاحة، وفي كلٍّ كلَّ فترةٍ لرصد الجناح. يعيد (التوزيع أو None، سطورُ التعليل).
    التوزيعُ: [(فترةٌ، شعبة، هل هي فترةُ رصد الجناح)].
    """
    trace = []
    for chosen in itertools.combinations(range(len(periods)), SESSIONS):
        for entry_at in chosen:
            plan = _fill(chosen, entry_at, periods, wing, plain, busy)
            if plan is not None:
                return plan, trace
    for index, (start, _end, _subject) in enumerate(periods):
        free_wing = [g for g in wing if g.id not in busy.get(start, set())]
        free_plain = [g for g in plain if g.id not in busy.get(start, set())]
        trace.append(
            f"  فترة {index + 1} ({start:%H:%M}): شعبُ جناحٍ خاليةٌ {len(free_wing)}/{len(wing)}، بلا جناحٍ خاليةٌ {len(free_plain)}/{len(plain)}"
        )
    return None, trace


def _fill(chosen, entry_at, periods, wing, plain, busy):
    """مطابقةٌ كاملةٌ فترات←شعب (مسارُ تحسينٍ لـKuhn): لا اختيارَ جشعاً يستنفد الشعبَ بلا جناحٍ في فتراتٍ يتّسع فيها الجناح.

    كلُّ فترةٍ تقبل شعبةً خاليةً في وقتها (فترةُ الرصد: شعبُ جناحٍ وحدَها)، وتُرتَّب القوائمُ بلا جناحٍ أوّلاً. مفتاحُ الشعبة لا يتكرّر.
    """
    options = {}
    for index in chosen:
        taken = busy.get(periods[index][0], set())
        pool = wing if index == entry_at else plain + wing
        options[index] = [g for g in pool if g.id not in taken]
    owner = {}  # معرّفُ الشعبة ← الفترة التي أخذتها

    def assign(index, seen):
        for group in options[index]:
            if group.id in seen:
                continue
            seen.add(group.id)
            if group.id not in owner or assign(owner[group.id], seen):
                owner[group.id] = index
                return True
        return False

    for index in sorted(chosen, key=lambda i: len(options[i])):
        if not assign(index, set()):
            return None
    by_id = {g.id: g for g in plain + wing}
    mine = {index: by_id[gid] for gid, index in owner.items()}
    return [(index, mine[index], index == entry_at) for index in chosen]


def plan():
    """قراءةٌ فقط: يطبع اختيارَ كلّ فترةٍ ولِمَ رُفض ما رُفض، ولا يكتب شيئاً."""
    if not in_preview_environment():
        _refuse("هذه ليست بيئةَ معاينة")
    teacher = _teacher()
    today = timezone.localdate()
    school_id = teacher.memberships.filter(is_active=True).values_list("school", flat=True).first()
    if school_id is None:
        _refuse("لا عضويّةَ نشطةً للمعلّم الوهميّ في مدرسة")
    school = School.objects.get(pk=school_id)
    periods = _period_times(school, today)
    wing, plain = _groups(school)
    busy = _busy(today)
    print(
        f"اليوم {today} — فتراتُ الجدول المعتمَد: {len(periods)}؛ شعبُ جناحٍ صالحةٌ {len(wing)}؛ بلا جناح {len(plain)}"
    )
    for index, (start, end, subject) in enumerate(periods):
        taken = busy.get(start, set())
        refused = [_label(g) for g in wing + plain if g.id in taken]
        print(
            f"فترة {index + 1} {start:%H:%M}–{end:%H:%M}: مشغولةٌ (لها حصّةٌ في الوقت نفسه) {len(refused)} شعبة"
        )
    chosen, trace = (
        _solve(periods, wing, plain, _busy(today)) if len(periods) >= SESSIONS else (None, [])
    )
    if chosen is None:
        print("لا حلَّ كاملاً بستّ فتراتٍ من الجدول المعتمَد — سبب الرفض:")
        for line in trace or [f"  فتراتُ الجدول {len(periods)} < {SESSIONS}"]:
            print(line)
        return
    print("الحلُّ الكامل (فترةٌ ← شعبة بالرمز):")
    for index, group, is_entry in chosen:
        start, end, subject = periods[index]
        kind = (
            "جناح — رصدُ الإدخال والاعتماد"
            if is_entry
            else ("جناح" if group.wing_id else "بلا جناح")
        )
        print(f"  فترة {index + 1} {start:%H:%M}–{end:%H:%M} ← {_label(group)} ({kind})")
    print("لا كتابةَ: هذا عرضٌ فقط.")


def _students(group, limit=3):
    return list(
        CustomUser.objects.filter(
            pk__in=StudentEnrollment.objects.filter(class_group=group, is_active=True).values(
                "student_id"
            )
        ).order_by("pk")[:limit]
    )


def _record(session, student, status, **extra):
    StudentAttendance.objects.get_or_create(
        session=session,
        student=student,
        defaults={"school": session.school, "status": status, "source": "teacher", **extra},
    )


def up():
    if not in_preview_environment():
        _refuse("هذه ليست بيئةَ معاينة")
    teacher = _teacher()
    today = timezone.localdate()
    school = teacher.memberships.filter(is_active=True).values_list("school", flat=True).first()
    if school is None:
        _refuse("لا عضويّةَ نشطةً للمعلّم الوهميّ في مدرسة")
    school = School.objects.get(pk=school)

    existing = list(_marked().filter(date=today, teacher=teacher).order_by("start_time"))
    if existing and len(existing) < SESSIONS:
        _refuse(f"حصصٌ موسومةٌ ناقصة ({len(existing)} من {SESSIONS}) — شغّل down ثمّ up")
    made = existing
    if not existing:
        periods = _period_times(school, today)
        wing, plain = _groups(school)
        chosen, trace = (
            _solve(periods, wing, plain, _busy(today)) if len(periods) >= SESSIONS else (None, [])
        )
        if chosen is None:
            _refuse("لا حلَّ كاملاً بستّ فتراتٍ — شغّل TEACHER_SEED_ACTION=plan:\n" + "\n".join(trace))
        with transaction.atomic():
            for index, group, is_entry in chosen:
                start, end, subject = periods[index]
                made.append(
                    Session.objects.create(
                        school=school,
                        class_group=group,
                        teacher=teacher,
                        subject=subject,
                        date=today,
                        start_time=start,
                        end_time=end,
                        period_number=index + 1,
                        status="scheduled",
                        notes=f"{MARK} حصّةُ معاينةٍ تُمحى بـdown"
                        + (f" {ENTRY_TAG}" if is_entry else ""),
                    )
                )
    source = "الجدول المعتمَد"

    wing_session = next((x for x in made if ENTRY_TAG in x.notes), made[0])
    others = [x for x in made if x.pk != wing_session.pk]
    holder = wing_session.class_group.wing.current_supervisor(on_date=today)
    students = _students(wing_session.class_group, 2)
    notes = []
    if len(students) < 2:
        notes.append("طلبةُ شعبة الجناح أقلُّ من اثنين — لا حالاتِ رصدٍ فيها")
    else:
        try:
            approved = submit_entry(teacher, wing_session, students[0], "present")
            if holder is not None:
                decide_entry(holder, approved, True)
            else:
                notes.append("لا حاملَ للجناح اليوم — بقي الإدخالُ الأوّلُ معلَّقاً")
            submit_entry(teacher, wing_session, students[1], "absent")
        except EntryError as error:
            notes.append(f"إدخالُ الجناح تعذّر: {error}")

    with transaction.atomic():
        for session in others[:2]:
            people = _students(session.class_group, 2)
            if len(people) == 2:
                _record(session, people[0], "present")
                _record(session, people[1], "late", late_minutes=5)
                Session.objects.filter(pk=session.pk).update(status="completed")
            else:
                notes.append(f"شعبةُ حصّة {session.period_number} بأقلّ من طالبَين — تُركت فارغة")

    print(f"مصدرُ المواقيت: {source} — اليوم {today}")
    print(
        f"المعلّم: user_id {teacher.pk} — الدخول بالرقم الوظيفيّ الوهميّ المحجوز؛ اللوحة: {BASE}/dashboard/"
    )
    for note in notes:
        print(f"تنبيه: {note}")
    who()


def who():
    today = timezone.localdate()
    print("الحصصُ الموسومة:")
    for session in _marked().order_by("date", "start_time").select_related("class_group__wing"):
        entries = AttendanceEntry.objects.filter(session=session).count()
        rows = StudentAttendance.objects.filter(session=session).count()
        wing = session.class_group.wing.code if session.class_group.wing_id else "—"
        print(
            f"  {session.date} {session.start_time:%H:%M}–{session.end_time:%H:%M} حصّة {session.period_number} "
            f"[{session.status}] جناح={wing} إدخالات={entries} رصدٌ معتمَد={rows} {BASE}/teacher/attendance/{session.id}/"
        )
    if not _marked().filter(date=today).exists():
        print("  (لا حصصَ موسومةً اليوم)")


def down():
    if not in_preview_environment():
        _refuse("هذه ليست بيئةَ معاينة")
    sessions = list(_marked())
    ids = {s.pk for s in sessions}
    removed_rows = StudentAttendance.objects.filter(session_id__in=ids).delete()[0] if ids else 0
    student_ids = set(
        AttendanceEntry.objects.filter(session_id__in=ids).values_list("student_id", flat=True)
    )
    skipped = 0
    erased = {"entries": 0, "decisions": 0}
    for student in CustomUser.objects.filter(pk__in=student_ids):
        if AttendanceEntry.objects.filter(student=student).exclude(session_id__in=ids).exists():
            skipped += 1
            continue
        counts = erase_attendance_ledger(student, school=sessions[0].school)
        for key in erased:
            erased[key] += counts.get(key, 0)
    leftover = AttendanceEntry.objects.filter(session_id__in=ids).exists()
    if not leftover:
        _marked().delete()
    print(
        f"صفوفُ رصدٍ محذوفة={removed_rows} · إدخالاتٌ {erased['entries']} وقرارات {erased['decisions']} · "
        f"طلبةٌ تُخطُّوا لوجود إدخالاتٍ في حصصٍ غير موسومة={skipped} · "
        + ("بقيت حصصٌ لبقاء إدخالاتٍ فيها" if leftover else "حُذفت الحصصُ الموسومة")
    )


{"up": up, "plan": plan, "who": who, "down": down}.get(
    ACTION, lambda: print("TEACHER_SEED_ACTION = up|plan|who|down")
)()
