"""بذرٌ محدودٌ ومُعلَن: يُسنِد حصصَ جناحٍ واحدٍ القائمةَ لليوم إلى حساب المعلّم الوهميّ على 8500 (W-20261003-023، W-20261005-005).

لا يُشغَّل من هنا تلقائيّاً ولا يشغّله غيرُ 0501 بعد إذن المالك. يُنفَّذ داخل حاوية ويب المعاينة بـ`manage.py shell` (stdin)
ومتغيّر البيئة `TEACHER_SEED_ACTION`:

    up    : **تبديلُ المعلّم** على حصصٍ **قائمةٍ** اليومَ بدل إنشاء حصصٍ جديدة (التي كانت تصطدم بـ`no_class_time_overlap` لأنّ شعب الجناح
            مشغولةٌ في معظم الفترات): حتى أربعِ حصصٍ في فتراتٍ مختلفةٍ لشعب جناحٍ واحدٍ — `w3` (`TEACHER_SEED_WING` يبدّله) — وحصّتَين من التربية الخاصّة
            (`…/ESE`، بلا جناح) إن وُجدتا، فيرى مشرفُ الجناح المغطّي له كلَّ ما يدخله المعلّمُ الوهميّ ويظهر «اعتماد الكلّ» والطابورُ كاملاً.
            المتاحُ هو ما يُسنَد: لا يُشترط العددُ، والحدُّ الأدنى حصّتان في الجناح وإلا رُفض.
            الحصّةُ المرشَّحةُ **لم يمسّها أحد**: مجدولةٌ بلا حضورٍ ولا إدخالٍ ولا خروجٍ ولا مخالفةٍ ولا تبديلٍ سابق (كما تعرّف `ScheduleService._untouched`)،
            وشعبتُها فيها طلبةٌ نشطون، ولا حصّةَ للمعلّم الوهميّ في وقتها (قيدُ `no_teacher_time_overlap`). والتبديلُ بكتابة `original_teacher`
            وهو **ما يقول إنّ الحصّةَ مبدَّلة** في الجدول، فتحميها إعادةُ التوليد من الحذف؛ وتُوسَم في `notes` بـ«[معاينة المعلّم]» لـ`down`.
            وحالاتُ الرصد على حصصٍ مُسنَدة:
              ١ رصدُ الجناح (الوسمُ [جناح الرصد]، أبكرُ حصّةٍ في الجناح) : طالبٌ بإدخالٍ **معتمَد** (submit_entry ثمّ decide_entry بالحاملِ الفعليّ)،
                وآخرُ بإدخالٍ **بانتظار الاعتماد**، والباقي فارغ.
              ٢ و٣    : رصدٌ مكتملٌ لطالبَين (حاضر ومتأخّر) فتصير الحصّةُ `completed`.
              والباقيةُ فارغةٌ `scheduled`.
    plan  : قراءةٌ فقط **لا تكتب شيئاً**: يعرض أوّلاً الحصصَ الموسومةَ القائمةَ (جناحُها وإدخالاتُها ونوعُها) وهل يرفضها up، ثمّ يطبع لكلّ فترةٍ عددَ حصص الجناح والتربية الخاصّة المرشَّحة (بالرمز لا بالأسماء) والإسنادَ المقترح.
    ملاحظة: بقايا إصدارٍ سابقٍ (حصصٌ **أنشأها** بذرٌ قديمٌ أو في جناحٍ غيرِ المختار) يرفضها `up` بسببٍ مكتوبٍ ويطلب `down` أوّلاً بدل إعادة استعمالها بصمت
            (واقعةُ 8500 في 2026-10-05: plan قدّر حصّتين وup أبلغ ستّاً من بقايا تشغيلٍ سابق، وإدخالٌ معتمَدٌ سلفاً منع ظهور «بانتظار الاعتماد»).
    who   : قراءةٌ فقط: يطبع ما أُسنِد وحالةَ كلّ حصّة.
    down  : يعيد المعلّمَ الأصليّ للحصص المُسنَدة (ويُصفّر `original_teacher` ويُزيل الوسم)، ويمحو ما وُسم: صفوفَ `StudentAttendance` للحصص الموسومة،
            ثمّ الإدخالاتِ والقراراتِ عبر `erase_attendance_ledger` (المسارُ الوحيد المسموح له بالحذف من السجلّ الملحق) — **لطالبٍ كلُّ إدخالاته
            في حصصٍ موسومة وحدَها**؛ طالبٌ له إدخالٌ في حصّةٍ غيرِ موسومة يُتخطّى. وما أنشأه إصدارٌ سابقٌ من هذا السكربت من حصصٍ جديدةٍ
            (موسومةٍ بلا `original_teacher`) تُحذف. سطورُ التدقيق تبقى.

حدودٌ مقصودة: **يرفض خارج بيئة المعاينة** (`in_preview_environment()`)، ويرفض إن لم يكن حسابُ المعلّم موجوداً وموسوماً وسماً مركَّباً
(شغّل `preview_accounts --sync` أوّلاً)، ولا يغيّر مشرفَ أيّ جناحٍ ولا أيَّ تغطيةٍ ولا الجدولَ المعتمَد. التشغيلُ ثانيةً لـup بلا تغيير (متساوي الأثر).
نافذةُ الإدخال في `attendance_policy.can_enter` يوميّةٌ لا بالحصّة؛ فإن رُفض الإدخالُ لخروج ساعة المعاينة عن اليوم الدراسيّ طُبع السببُ ويبقى الباقي.
البذرُ مؤقّتٌ للمعاينة؛ وقرارُ المالك أنّ «شعبَ المعلّم مفتوحةٌ له كلَّ يومٍ دراسيّ» سيصير ميزةً دائمةً (حصّةٌ عند الطلب) لا بذراً.
"""

import os
import sys

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from core.models import CustomUser, School, StudentEnrollment
from core.preview_accounts import EMPLOYEE_NUMBERS, in_preview_environment, is_preview_account
from operations.attendance_entries import (
    EntryError,
    decide_entry,
    erase_attendance_ledger,
    submit_entry,
)
from operations.models import AttendanceEntry, Session, StudentAttendance

MARK = "[معاينة المعلّم]"
ACTION = os.environ.get("TEACHER_SEED_ACTION", "")
BASE = "http://localhost:8500"
#: حصصُ المعلّم الوهميّ: حتى أربعٍ في جناحٍ واحد وحتى حصّتين للتربية الخاصّة، والحدُّ الأدنى للجناح حصّتان.
WING_SESSIONS = 4
SPECIAL_SESSIONS = 2
MIN_WING_SESSIONS = 2
WING_CODE = os.environ.get("TEACHER_SEED_WING", "w3")
ENTRY_TAG = "[جناح الرصد]"
ASSIGNED_NOTE = f"{MARK} حصّةٌ مُسنَدةٌ للمعاينة تُعاد بـdown"


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


def _school(teacher):
    school_id = teacher.memberships.filter(is_active=True).values_list("school", flat=True).first()
    if school_id is None:
        _refuse("لا عضويّةَ نشطةً للمعلّم الوهميّ في مدرسة")
    return School.objects.get(pk=school_id)


def _marked():
    return Session.objects.filter(notes__contains=MARK)


def _untouched(queryset):
    """ما لم يمسّه أحد — التعريفُ نفسُه في `ScheduleService._untouched` (يُكرَّر هنا لأنّ السكربتَ لا يستورد خدمةَ الجدول)."""
    return queryset.filter(
        status="scheduled",
        attendances__isnull=True,
        attendance_entries__isnull=True,
        class_exits__isnull=True,
        infractions__isnull=True,
        original_teacher__isnull=True,
        compensatory_source__isnull=True,
    )


def _candidates(school, today, teacher):
    """(حصصُ الجناح المرشَّحة، حصصُ التربية الخاصّة المرشَّحة) مرتّبةً بالوقت — لشعبٍ فيها طلبةٌ نشطون، وبلا حصّةٍ للمعلّم الوهميّ في وقتها."""
    base = (
        _untouched(
            Session.objects.filter(school=school, date=today, class_group__is_active=True)
            .exclude(teacher=teacher)
            .annotate(
                students=Count(
                    "class_group__enrollments",
                    filter=Q(class_group__enrollments__is_active=True),
                    distinct=True,
                )
            )
            .filter(students__gt=0)
        )
        .select_related("class_group__wing")
        .order_by("start_time", "class_group__grade", "class_group__section", "id")
    )
    busy = set(
        Session.objects.filter(date=today, teacher=teacher).values_list("start_time", flat=True)
    )
    wing = [
        s
        for s in base.filter(
            class_group__wing__code=WING_CODE, class_group__wing__is_active=True
        ).exclude(class_group__section__iendswith="ESE")
        if s.start_time not in busy
    ]
    special = [
        s
        for s in base.filter(class_group__wing__isnull=True, class_group__section__iendswith="ESE")
        if s.start_time not in busy
    ]
    return wing, special


def _pick(candidates, limit, taken):
    """حصّةٌ واحدةٌ لكلّ وقتِ بدءٍ (قيدُ `no_teacher_time_overlap`) بعيداً عمّا اختير سلفاً، حتى `limit`."""
    chosen = []
    for session in candidates:
        if len(chosen) >= limit:
            break
        if session.start_time in taken:
            continue
        taken.add(session.start_time)
        chosen.append(session)
    return chosen


def _label(session):
    return str(session.class_group.short_label)


def _plan(school, today, teacher):
    wing, special = _candidates(school, today, teacher)
    taken: set = set()
    picked_wing = _pick(wing, WING_SESSIONS, taken)
    picked_special = _pick(special, SPECIAL_SESSIONS, taken)
    return wing, special, picked_wing, picked_special


def plan():
    """قراءةٌ فقط: يطبع المرشَّحَ لكلّ فترةٍ والإسنادَ المقترح، ولا يكتب شيئاً."""
    if not in_preview_environment():
        _refuse("هذه ليست بيئةَ معاينة")
    teacher = _teacher()
    today = timezone.localdate()
    school = _school(teacher)
    wing, special, picked_wing, picked_special = _plan(school, today, teacher)
    existing = _mine(today, teacher)
    if existing:
        # ما وُسم سلفاً يُعرض أوّلاً: `up` يعيد استعمالَه ولا يُسنِد جديداً (وكان plan يسكت عنه فيبدو الحالُ غيرَ ما سيقع).
        print(f"حصصٌ موسومةٌ قائمةٌ اليوم: {len(existing)} (يعيد up استعمالَها ولا يُسنِد جديداً):")
        for session in existing:
            wing_code = session.class_group.wing.code if session.class_group.wing_id else "—"
            entries = AttendanceEntry.objects.filter(session=session).count()
            kind = "مُسنَدة" if session.original_teacher_id else "أنشأها إصدارٌ سابق"
            print(
                f"  {session.start_time:%H:%M} جناح={wing_code} [{kind}] إدخالات={entries} [{session.status}]"
            )
        if reason := _stale_reason(existing):
            print(f"لا تصلح لإعادة الاستعمال: {reason} — سيرفض up ويطلب down أوّلاً.")
    print(
        f"اليوم {today} — حصصٌ مرشَّحةٌ لجناح {WING_CODE}: {len(wing)}؛ للتربية الخاصّة: {len(special)}"
    )
    by_time: dict = {}
    for session in wing:
        by_time.setdefault(session.start_time, [0, 0])[0] += 1
    for session in special:
        by_time.setdefault(session.start_time, [0, 0])[1] += 1
    for start in sorted(by_time):
        in_wing, in_special = by_time[start]
        print(f"  {start:%H:%M}: حصصُ {WING_CODE} {in_wing}، تربيةٌ خاصّةٌ {in_special}")
    if len(picked_wing) < MIN_WING_SESSIONS:
        print(
            f"لا يكفي الجناحُ {WING_CODE}: {len(picked_wing)} حصّةً مرشَّحةً في فتراتٍ مختلفة "
            f"(الحدُّ الأدنى {MIN_WING_SESSIONS}) — لن يُسنَد شيء."
        )
        return
    print("الإسنادُ المقترح (فترةٌ ← شعبة بالرمز):")
    for index, session in enumerate(picked_wing):
        kind = "جناح — رصدُ الإدخال والاعتماد" if index == 0 else "جناح"
        print(f"  {session.start_time:%H:%M} ← {_label(session)} ({kind})")
    for session in picked_special:
        print(f"  {session.start_time:%H:%M} ← {_label(session)} (تربيةٌ خاصّة)")
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


def _assign(session, teacher, entry):
    """تبديلُ معلّم حصّةٍ قائمة: `original_teacher` يحفظ صاحبَها فيُعاد بـdown."""
    Session.objects.filter(pk=session.pk).update(
        original_teacher_id=session.teacher_id,
        teacher=teacher,
        notes=(f"{session.notes} " if session.notes else "")
        + ASSIGNED_NOTE
        + (f" {ENTRY_TAG}" if entry else ""),
    )


def _mine(today, teacher):
    return list(
        _marked()
        .filter(date=today, teacher=teacher)
        .select_related("class_group__wing")
        .order_by("start_time")
    )


def _stale_reason(made):
    """سببُ أنّ الموسومةَ القائمةَ لا تصلح لإعادة الاستعمال، أو `""` — فلا يُخفي `up` بقايا إصدارٍ سابقٍ بصمت (واقعةُ 8500 في 2026-10-05).

    بقايا إصدارٍ سابقٍ: حصصٌ **أُنشئت** (بلا `original_teacher`) لا حصصٌ مُسنَدة، أو حصّةُ جناحٍ غيرِ المختار. وفي الحالين التشغيلُ الصحيحُ `down` ثمّ `up`.
    """
    created = [s for s in made if not s.original_teacher_id]
    if created:
        return f"{len(created)} حصّةً أنشأها إصدارٌ سابقٌ من البذر (لا مُسنَدة)"
    off_wing = [s for s in made if s.class_group.wing_id and s.class_group.wing.code != WING_CODE]
    if off_wing:
        codes = sorted({s.class_group.wing.code for s in off_wing})
        return f"حصصٌ موسومةٌ في جناحٍ غيرِ {WING_CODE}: {', '.join(codes)}"
    return ""


def up():
    if not in_preview_environment():
        _refuse("هذه ليست بيئةَ معاينة")
    teacher = _teacher()
    today = timezone.localdate()
    school = _school(teacher)

    made = _mine(today, teacher)
    if made and (reason := _stale_reason(made)):
        _refuse(
            f"حصصٌ موسومةٌ قائمةٌ لا تصلح لإعادة الاستعمال — {reason}. شغّل `TEACHER_SEED_ACTION=who` لتراها، "
            "ثمّ `down` (يمحو إدخالاتِ الحصص الموسومة وحدَها) ثمّ `up` — ولا يُشغَّل down إلا بإذن المالك."
        )
    if not made:
        _wing, _special, picked_wing, picked_special = _plan(school, today, teacher)
        if len(picked_wing) < MIN_WING_SESSIONS:
            _refuse(
                f"حصصُ الجناح {WING_CODE} المرشَّحةُ أقلُّ من {MIN_WING_SESSIONS} — شغّل TEACHER_SEED_ACTION=plan"
            )
        with transaction.atomic():
            for index, session in enumerate(picked_wing + picked_special):
                _assign(session, teacher, entry=index == 0)
        made = _mine(today, teacher)

    wing_session = next((x for x in made if ENTRY_TAG in x.notes), made[0])
    others = [x for x in made if x.pk != wing_session.pk]
    holder = wing_session.class_group.wing.current_supervisor(on_date=today)
    students = _students(wing_session.class_group, 2)
    notes = []
    if AttendanceEntry.objects.filter(session=wing_session).exists():
        notes.append(
            "حصّةُ رصد الجناح لها إدخالاتٌ سلفاً — لم تُضَف حالاتٌ جديدة (الإدخالُ المعتمَدُ يمنع ظهورَ «بانتظار الاعتماد»)"
        )
    elif len(students) < 2:
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
                notes.append(f"شعبةُ حصّة {session.start_time:%H:%M} بأقلّ من طالبَين — تُركت فارغة")

    print(f"مصدرُ الحصص: حصصٌ قائمةٌ مُسنَدةٌ (تبديلُ المعلّم) — اليوم {today}")
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
            f"  {session.date} {session.start_time:%H:%M}–{session.end_time:%H:%M} "
            f"[{session.status}] جناح={wing} إدخالات={entries} رصدٌ معتمَد={rows} {BASE}/teacher/attendance/{session.id}/"
        )
    if not _marked().filter(date=today).exists():
        print("  (لا حصصَ موسومةً اليوم)")


def down():
    if not in_preview_environment():
        _refuse("هذه ليست بيئةَ معاينة")
    sessions = list(_marked())
    if not sessions:
        print("لا حصصَ موسومة — لا شيءَ يُعاد")
        return
    ids = {s.pk for s in sessions}
    removed_rows = StudentAttendance.objects.filter(session_id__in=ids).delete()[0]
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
    leftover = set(
        AttendanceEntry.objects.filter(session_id__in=ids).values_list("session_id", flat=True)
    )
    restored = deleted = 0
    for session in sessions:
        if session.pk in leftover:
            continue
        if session.original_teacher_id:
            # حصّةٌ قائمةٌ بُدِّل معلّمُها: يعود صاحبُها وتعود مجدولةً كما كانت (لم تكن مرصودةً قبل البذر)
            Session.objects.filter(pk=session.pk).update(
                teacher_id=session.original_teacher_id,
                original_teacher=None,
                status="scheduled",
                notes=session.notes.replace(f" {ENTRY_TAG}", "").replace(ASSIGNED_NOTE, "").strip(),
            )
            restored += 1
        else:
            session.delete()
            deleted += 1
    print(
        f"صفوفُ رصدٍ محذوفة={removed_rows} · إدخالاتٌ {erased['entries']} وقرارات {erased['decisions']} · "
        f"طلبةٌ تُخطُّوا لوجود إدخالاتٍ في حصصٍ غير موسومة={skipped} · "
        f"حصصٌ أُعيد معلّمُها={restored} وحُذفت (أنشأها إصدارٌ سابق)={deleted}"
        + (f" · بقيت {len(leftover)} حصّةً لبقاء إدخالاتٍ فيها" if leftover else "")
    )


{"up": up, "plan": plan, "who": who, "down": down}.get(
    ACTION, lambda: print("TEACHER_SEED_ACTION = up|plan|who|down")
)()
