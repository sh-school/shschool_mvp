"""سياسةُ رصد المعلّم الفعليّ واعتمادِه — دوالُّ قرارٍ بلا تخزين (W-20261002-020).

قراراتُ المالك (D-125م وD-126م وD-128م وD-129م):

- المعلّمُ الفعليّ للحصّة هو `Session.teacher` وحدَه — لا حقلَ آخر — فيُدخل رصداً **مبدئيّاً** لطلبة
  حصّته من بدئها حتّى نهاية اليوم الدراسيّ. والتبديلُ والتغطيةُ والتعويضُ كلُّها تكتب هذا الحقلَ
  عند التنفيذ، فيرثه الجديدُ ويفقده الأصليُّ دون أيّ استثناءٍ هنا.
- يعتمده **حاملُ جناح الشعبة يومَ الحصّة** (`Wing.current_supervisor` على تاريخ الحصّة لا يومِ
  الاعتماد)، والقيادةُ حين لا حاملَ فقط. لا المعلّمُ ولا من أدخل، ولا المطوّرُ ولو كان superuser.
- شعبةُ التربية الخاصّة (جناحٌ فارغٌ **و**شعبةُ ESE معاً): الرصدُ نهائيٌّ بلا اعتماد. والجناحُ
  الفارغُ وحدَه لا يكفي — شعبةٌ عاديّةٌ بجناحٍ لم يُسند خطأً تبقى مبدئيّةً (لا يفشل الفحصُ مفتوحاً).

**لا يُقرأ هنا `is_superuser` ولا `is_leadership()`** — كلاهما يمنح المطوّرَ والمستخدمَ الخارقَ ما حُجب
عنهما بقرار. تُقرأ العضويّاتُ النشطةُ في مدرسة الحصّة بأسماء الأدوار وحدَها.

الوقتُ بتوقيت الدوحة (`TIME_ZONE`): المقارنةُ بين لحظتين واعيتين بالمنطقة لا بين تاريخَين،
فـ21:30 UTC من الأحد = 00:30 من الاثنين بالدوحة مرفوضٌ.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db.models import Max, Min
from django.utils import timezone

from core.models import StudentEnrollment
from core.preview_accounts import in_preview_environment

from .bells import day_type_for
from .models import AttendanceEntry, Session, TimeSlotConfig

if TYPE_CHECKING:
    from core.models import ClassGroup, CustomUser, School, TimeBand

DEVELOPER_ROLE = "platform_developer"

#: القيادةُ التي تعتمد حين لا يوجد حاملٌ للجناح — بالدور لا بـ`is_leadership()`.
LEADERSHIP_ROLES = ("principal", "vice_admin", "vice_academic")

#: لاحقةُ شعبة التربية الخاصّة في `ClassGroup.section` («8/ESE»، «07/ESE»).
SPECIAL_EDUCATION_SECTION = "ESE"


@dataclass(frozen=True)
class Verdict:
    """جوابُ السياسة: أُذن أم لا، وبرمزٍ مختصرٍ للسبب يُعرض ويُختبر."""

    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed


def is_developer(user: CustomUser) -> bool:
    """أللمستخدم عضويّةٌ نشطةٌ بدور المطوّر (في أيّ مدرسة)؟ — فشلٌ مغلقٌ أوسعُ من المطلوب، مقبول.

    استعلامٌ مباشرٌ على العضويّات لا `user.has_role` (دالّةٌ بلا أنواعٍ تُحمَّل على سقّاطة mypy)، والمعنى نفسُه.
    """
    return bool(user.memberships.filter(is_active=True, role__name=DEVELOPER_ROLE).exists())


def _allow() -> Verdict:
    return Verdict(True)


def _deny(reason: str) -> Verdict:
    return Verdict(False, reason)


def school_day_end(school: School, day: dt.date, band: TimeBand | None = None) -> dt.time | None:
    """نهايةُ اليوم الدراسيّ: آخرُ خانةٍ في جرس المدرسة لهذا النوع من الأيّام — وهي دالّةٌ واحدة.

    بإعداد المدرسة (`TimeSlotConfig`) لا بثابت. و`band` يحصر الحسابَ بجرس الشعبة إن كان له خاناتٌ في
    اليوم، وإلّا فآخرُ خانةٍ بين أجراس المدرسة. و`None` ليومٍ لا دراسةَ فيه أو مدرسةٍ بلا جرسٍ مضبوط.
    """
    day_type = day_type_for(day)
    if not day_type:
        return None
    rows = TimeSlotConfig.objects.filter(school=school, day_type=day_type, band__isnull=False)
    if band is not None:
        scoped = rows.filter(band=band)
        if scoped.exists():
            rows = scoped
    last: dt.time | None = rows.aggregate(last=Max("end_time"))["last"]
    return last


def _first_slot_start(session: Session) -> dt.time | None:
    """بدءُ أوّل خانةٍ (غيرِ استراحةٍ) في جرس **شعبة** الحصّة لنوع يومها — لا جرسِ جناحها كلِّه (جناحٌ يعبر جرسين لكلّ شعبةٍ جرسُها)؛ `None` بلا جرسٍ مضبوط."""
    day_type = day_type_for(session.date)
    band = session.class_group.time_band
    if not day_type or band is None:
        return None
    first: dt.time | None = TimeSlotConfig.objects.filter(
        school=session.school, day_type=day_type, band=band, is_break=False
    ).aggregate(first=Min("start_time"))["first"]
    return first


def entry_window(session: Session) -> tuple[dt.datetime, dt.datetime]:
    """نافذةُ إدخال المعلّم: من بدء الحصّة إلى نهاية اليوم الدراسيّ، لحظتان واعيتان بتوقيت الدوحة.

    وحيث لا جرسَ مضبوطاً تضيق النافذةُ إلى نهاية الحصّة نفسِها — الأضيقُ لا ثابتٌ مخترَع. ولا تُقصَّر
    أبداً عن نهاية الحصّة (جرسٌ مضبوطٌ خطأً لا يغلق حصّةً جارية).
    """
    start = timezone.make_aware(dt.datetime.combine(session.date, session.start_time))
    day_end = school_day_end(session.school, session.date, band=session.class_group.time_band)
    last = max(day_end, session.end_time) if day_end else session.end_time
    if session.provisional:
        # الحصّةُ **المؤقّتة** وحدَها (W-20261005-006، D-232م): فعّالةٌ للإدخال من بدء **أوّل حصّةٍ في جرس الشعبة** إلى نهاية الدوام لا من بدء حصّتها،
        # فلا يُقيَّد معلّمٌ يرصد ح5 قبل وقتها. والحقيقيّةُ (D-128م) تبقى من بدء حصّتها كما هي.
        first = _first_slot_start(session)
        if first is not None:
            start = timezone.make_aware(dt.datetime.combine(session.date, first))
    if in_preview_environment():
        # المعاينةُ وحدَها (قرارُ المالك 2026-10-04): النافذةُ مفتوحةٌ من أوّل اليوم إلى آخره ليرى الأزرارَ في أيّ ساعةٍ
        # (فجراً قبل الحصّة وبعد الدوام)؛ والإنتاجُ بنافذته كما هي.
        start = timezone.make_aware(dt.datetime.combine(session.date, dt.time.min))
        last = dt.time(23, 59, 59)
    return start, timezone.make_aware(dt.datetime.combine(session.date, last))


def is_special_education(class_group: ClassGroup) -> bool:
    """شعبةُ تربيةٍ خاصّة: بلا جناحٍ **و**شعبةُ ESE — العلامتان معاً، فالفراغُ وحدَه لا يكفي."""
    if class_group.wing_id is not None:
        return False
    return bool(class_group.section.rsplit("/", 1)[-1].strip().upper() == SPECIAL_EDUCATION_SECTION)


def needs_approval(session: Session) -> bool:
    """أيحتاج رصدُ هذه الحصّة اعتماداً؟ — كلُّ الشُّعب إلّا التربية الخاصّة (D-126م)."""
    return not is_special_education(session.class_group)


def _raw_holder(session: Session) -> CustomUser | None:
    wing = session.class_group.wing
    if wing is None or not wing.is_active:
        return None
    holder: CustomUser | None = wing.current_supervisor(on_date=session.date)  # type: ignore[no-untyped-call]
    return holder


def holder_gap(session: Session) -> str | None:
    """لِمَ لا حاملَ فعليّاً لجناح هذه الحصّة؟ — `None` إن وُجد حاملٌ يصلح، وإلّا السببُ (حكمُ 0105 P1/P2):

    - `no_holder`: لا جناحَ أو جناحٌ غيرُ نشطٍ أو بلا مشرفٍ ولا تغطية.
    - `holder_is_teacher`: حاملُ الجناح هو معلّمُ الحصّة نفسُه — لا يعتمد رصدَ حصّته (`own_session`)، فلو بقي حاملاً
      لجمد الاعتمادُ ولم تعتمد القيادة.
    - `holder_inactive`: حاملٌ بلا عضويّةٍ نشطةٍ في مدرسة الحصّة (غادر أو أُوقفت عضويّتُه) — اسمٌ لا يستطيع القرار.
    """
    holder = _raw_holder(session)
    if holder is None:
        return "no_holder"
    if holder.id == session.teacher_id:
        return "holder_is_teacher"
    if not _roles_in_school(holder, session.school_id):
        return "holder_inactive"
    return None


def approval_holder(session: Session) -> CustomUser | None:
    """من يحمل جناحَ شعبة الحصّة **يومَ الحصّة** حاملاً **فعليّاً**: بديلُ التغطية الساريةِ بتاريخها وإلّا الأصيل.

    و`None` إن لم يكن للشعبة جناحٌ أو كان غيرَ نشطٍ أو بلا مشرفٍ ولا تغطية، أو كان الحاملُ لا يصلح (معلّمَ الحصّة
    نفسَه أو بلا عضويّةٍ نشطة — `holder_gap`) فيُعامَل الجناحُ كأنّه بلا حاملٍ وتعتمد القيادةُ. و`Wing.is_held_by`
    الخامّ لا يصلح هنا: يجيب أيحمل المستخدمُ أيَّ جناحٍ لا جناحَ هذه الشعبة.
    """
    return _raw_holder(session) if holder_gap(session) is None else None


def approval_evidence(session: Session) -> dict[str, str | None]:
    """دليلُ الصلاحيّة وقتَ القرار: الجناحُ والتغطيةُ والحامل — يُحفظ مع القرار فلا يُعاد حسابُه بعد تغيّر التغطية."""
    wing = session.class_group.wing
    if wing is None:
        return {"wing_id": None, "coverage_id": None, "holder_id": None}
    if not wing.is_active:
        return {"wing_id": str(wing.pk), "coverage_id": None, "holder_id": None}
    cover = wing.active_coverage(on_date=session.date)  # type: ignore[no-untyped-call]
    holder = cover.substitute if cover else wing.supervisor
    return {
        "wing_id": str(wing.pk),
        "coverage_id": str(cover.pk) if cover else None,
        "holder_id": str(holder.pk) if holder else None,
    }


def _roles_in_school(user: CustomUser, school_id: Any) -> set[str]:
    return set(
        user.memberships.filter(is_active=True, school_id=school_id).values_list(
            "role__name", flat=True
        )
    )


def tap_window(session: Session) -> tuple[dt.datetime, dt.datetime]:
    """نافذةُ نقرة «دخل متأخّراً» (D-136م): الحصّةُ نفسُها، من بدئها إلى نهايتها — لا إلى نهاية اليوم (لحظتان واعيتان بالدوحة)."""
    start = timezone.make_aware(dt.datetime.combine(session.date, session.start_time))
    end = timezone.make_aware(dt.datetime.combine(session.date, session.end_time))
    return start, end


def _teacher_write_verdict(
    user: CustomUser,
    session: Session,
    student: CustomUser,
    window: tuple[dt.datetime, dt.datetime],
    now: dt.datetime | None,
) -> Verdict:
    """الفحصُ المشترك لكلّ كتابةٍ يجريها معلّمُ الحصّة الفعليّ: من هو، وفي أيّ حصّةٍ، ولأيّ طالبٍ، وضمن أيّ نافذة."""
    if not getattr(user, "is_authenticated", False):
        return _deny("anonymous")
    if is_developer(user):
        return _deny("developer")

    roles = _roles_in_school(user, session.school_id)
    if not roles:
        return _deny("other_school")
    if user.id != session.teacher_id:
        return _deny("not_teacher")
    if session.status == "cancelled":
        return _deny("cancelled")
    if not (_is_enrolled(student, session) or _has_entry_in_session(student, session)):
        return _deny("not_enrolled")

    moment = now or timezone.now()
    opens, closes = window
    if moment < opens:
        return _deny("before_start")
    if moment > closes:
        return _deny("after_window")
    return _allow()


def can_enter(
    user: CustomUser, session: Session, student: CustomUser, *, now: dt.datetime | None = None
) -> Verdict:
    """هل يُدخل هذا المستخدمُ رصداً مبدئيّاً لهذا الطالب في هذه الحصّة الآن؟ (نافذةُ اليوم الدراسيّ.)

    وبها أيضاً «خرج بإذن» (`teacher_out`، G4): معلّمُ الحصّة وحدَه بنافذة اليوم.
    """
    return _teacher_write_verdict(user, session, student, entry_window(session), now)


def can_tap_late(
    user: CustomUser, session: Session, student: CustomUser, *, now: dt.datetime | None = None
) -> Verdict:
    """هل ينقر هذا المستخدمُ «دخل متأخّراً» لهذا الطالب الآن؟ — معلّمُ الحصّة وحدَه، **بنافذة الحصّة نفسِها** (D-136م)."""
    return _teacher_write_verdict(user, session, student, tap_window(session), now)


def _is_enrolled(student: CustomUser, session: Session) -> bool:
    """قيدٌ نشطٌ في شعبة الحصّة بدأ في تاريخها أو قبله — فطالبٌ قُيّد بعدها لا تُرصد له."""
    return bool(
        StudentEnrollment.objects.filter(
            student=student,
            class_group_id=session.class_group_id,
            is_active=True,
            enrolled_at__lte=session.date,
        ).exists()
    )


def holds_leadership_role(user: CustomUser, school_id: Any) -> bool:
    """أللمستخدم دورُ قيادةٍ (مديرٌ أو نائب) نشطٌ في هذه المدرسة؟ — بالدور لا بـ`is_superuser`، ولا مطوّر."""
    if not getattr(user, "is_authenticated", False) or is_developer(user):
        return False
    return bool(_roles_in_school(user, school_id) & set(LEADERSHIP_ROLES))


def can_correct(user: CustomUser, session: Session) -> Verdict:
    """هل يصحّح هذا المستخدمُ رصداً لم يشاهده (A: تصحيحُ المشرف)؟ — لمن له الاعتمادُ على هذه الحصّة وحدَه.

    حاملُ الجناح الفعليّ يومَ الحصّة، أو القيادةُ حين لا حاملَ فعليّاً؛ لا معلّمُ الحصّة ولا المطوّر.
    """
    return can_approve(user, session)


def _has_entry_in_session(student: CustomUser, session: Session) -> bool:
    """أُدخل لهذا الطالب رصدٌ في هذه الحصّة نفسِها وهو في شعبتها (حكمُ 0105 P3).

    فمن نُقل بعد الحصّة وقبل أن يصحّح المعلّمُ يُصحَّح له في النافذة: الرصدُ حدثٌ وقع في الحصّة لا حالةُ قيدٍ اليوم.
    ولا يفتح البابَ لأوّل إدخالٍ (يلزمه القيدُ النشط) ولا لحصّةٍ أخرى.
    """
    return bool(AttendanceEntry.objects.filter(session=session, student=student).exists())


#: مصدرُ إدخالات جدول الشعبة — لها وحدَها اعتمادُ حاملِ الجناح الذاتيّ (D-239م).
GRID_ORIGINS = frozenset({"grid", "grid_default"})


def grid_holder_approves(user: CustomUser, session: Session, entry_origin: str) -> bool:
    """أحاملُ جناح الشعبةِ يومَ الحصّة هو هذا المستخدمُ، والإدخالُ من جدول الشعبة، والمفتاحُ مشغَّل؟ (قرارُ المالك D-239م: يعتمد ما كتبه بنفسه بتدقيق.)

    في مسار الجدول وحدَه: يُستثنى `own_entry` و`own_session` و`holder_gap` عن الحامل الفعليّ؛ والقيادةُ (مديرٌ ونائبٌ ومشرفٌ إداريّ) لا تعتمد ما كتبته.
    والمفتاحُ مطفأً ← المنعُ القائمُ كما هو حرفاً (لا إدخالَ جدولٍ يُنشأ أصلاً، وهنا يُقفل المسارُ بالمفتاح أيضاً).
    """
    from django.conf import settings

    if entry_origin not in GRID_ORIGINS or not getattr(settings, "PROVISIONAL_GRID_ENABLED", False):
        return False
    holder = _wing_holder_on(session.class_group, session.date)
    return holder is not None and holder.id == user.id


def can_approve(
    user: CustomUser,
    session: Session,
    *,
    entered_by: CustomUser | None = None,
    entry_origin: str = "",
) -> Verdict:
    """هل يعتمد هذا المستخدمُ رصدَ هذه الحصّة (أو يرفضه)؟

    لا يقرأ وقتَ الاعتماد: الحاملُ هو من حمل الجناحَ يومَ الحصّة. و`entered_by` صاحبُ الإدخال المعلَّق
    فلا يعتمد أحدٌ ما أدخله بنفسه.
    """
    if not getattr(user, "is_authenticated", False):
        return _deny("anonymous")
    if is_developer(user):
        return _deny("developer")

    roles = _roles_in_school(user, session.school_id)
    if not roles:
        return _deny("other_school")
    if not needs_approval(session):
        return _deny("final_entry")
    # قبل حاملِ الجناح: لو عُيّن المنسّقُ حاملَ جناحٍ لا يتجاوز المنع (D-266م؛ الاعتمادُ ملغى بـD-245م).
    if "student_affairs_coordinator" in roles:
        return _deny("not_approver")
    if grid_holder_approves(user, session, entry_origin):
        return _allow()
    if user.id == session.teacher_id:
        return _deny("own_session")
    if entered_by is not None and user.id == entered_by.id:
        return _deny("own_entry")

    from wings.services import holds_school_wide

    # حاصرُ الغياب العامّ معتمِدٌ ثانٍ بجانب حامل الجناح دائماً (قرارُ المالك 2026-10-06): لا ما أدخله بنفسه
    # ولا رصدَ التربية الخاصّة (النهائيّ) — وقد رُدّا أعلاه.
    if holds_school_wide(user):
        return _allow()
    holder = approval_holder(session)
    if holder is not None:
        return _allow() if user.id == holder.id else _deny("not_holder")
    if roles & set(LEADERSHIP_ROLES):
        return _allow()
    return _deny("not_holder")


# ══════════════════════════════════════════════════════════════════
# جدولُ الشعبة العموديّ (W-20261006-005، قرارا المالك D-238م–D-240م)
# ══════════════════════════════════════════════════════════════════
#
# حكمٌ **منفصلٌ** عن `can_enter`/`can_correct`/`can_approve` العامّة (لا تُخفَّف): الصلاحيةُ هنا تُشتقّ من إسناد المعلّم للشعبة ومن حمل الجناح
# ومن الدور، لا من `Session.teacher` ولا من الطلب. وغيرُ المخوَّل يُردّ بـ404 في الواجهة (رمزُ `not_found`) فلا يُعرف أنّ الشعبة موجودة.

#: القيادةُ الإداريّةُ التي تكتب على كلّ الأعمدة (D-240م) — بالدور لا بـ`is_leadership()`؛ والنائبُ الأكاديميّ يراقب فقط (D-239م).
GRID_WRITER_ROLES = frozenset(
    {"principal", "vice_admin", "admin_supervisor", "student_affairs_coordinator"}
)
GRID_READER_ROLES = GRID_WRITER_ROLES | {"vice_academic"}

GRID_TEACHER = "teacher"
GRID_HOLDER = "holder"
GRID_LEADERSHIP = "leadership"
GRID_READER = "reader"


def _clock(raw: str, fallback: dt.time) -> dt.time:
    try:
        hour, minute = (int(part) for part in str(raw).split(":", 1))
        return dt.time(hour, minute)
    except (TypeError, ValueError):
        return fallback


def grid_now(now: dt.datetime | None = None) -> dt.datetime:
    """لحظةُ الجدول بتوقيت الدوحة: الممرَّرةُ، وإلّا الآن. و**للمعاينة وحدَها** (`DEBUG` مشغَّلٌ) يُقدِّم `ATTENDANCE_GRID_FAKE_TIME` («07:11») ساعةَ اليوم لتجربة الكتابة ليلاً (أمرُ المالك).

    الإنتاجُ بـ`DEBUG` مطفأٍ فلا أثرَ للمتغيّر فيه ولو ضُبط خطأً — كشرط `in_preview_environment`: لا مفتاحَ زمنٍ يعمل خارجَ بيئةِ التطوير.
    """
    from django.conf import settings

    if now is not None:
        return timezone.localtime(now)
    fake = str(getattr(settings, "ATTENDANCE_GRID_FAKE_TIME", "") or "")
    if fake and settings.DEBUG:
        return timezone.make_aware(
            dt.datetime.combine(timezone.localdate(), _clock(fake, dt.time(7, 11)))
        )
    return timezone.localtime()


def grid_window(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """نافذةُ كتابة المعلّم في الجدول (D-237م): من إعدادٍ مركزيٍّ واحد (07:10–14:00 افتراضاً) بتوقيت الدوحة.

    وفي المعاينة وحدَها اليومُ كلُّه (قرارُ المالك 2026-10-04) كما في `entry_window`.
    """
    from django.conf import settings

    opens = _clock(getattr(settings, "ATTENDANCE_GRID_OPENS", "07:10"), dt.time(7, 10))
    closes = _clock(getattr(settings, "ATTENDANCE_GRID_CLOSES", "14:00"), dt.time(14, 0))
    if in_preview_environment():
        opens, closes = dt.time.min, dt.time(23, 59, 59)
    return (
        timezone.make_aware(dt.datetime.combine(day, opens)),
        timezone.make_aware(dt.datetime.combine(day, closes)),
    )


def is_class_assigned(user: CustomUser, class_group: ClassGroup) -> bool:
    """أمُسنَدٌ هذا المعلّمُ إلى الشعبة (أيَّ مادّة)؟ — بشروط إسناد المعلّم للحصّة المؤقّتة نفسِها: فعّالٌ، عامُ المدرسة، غيرُ محذوف."""
    from core.academic_calendar import academic_year_for_school

    from .models import SubjectClassAssignment

    return bool(
        SubjectClassAssignment.objects.filter(
            school_id=class_group.school_id,
            teacher=user,
            class_group=class_group,
            is_active=True,
            deleted_at__isnull=True,
            academic_year=academic_year_for_school(class_group.school),
        ).exists()
    )


def _wing_holder_on(class_group: ClassGroup, day: dt.date) -> CustomUser | None:
    wing = class_group.wing
    if wing is None or not wing.is_active:
        return None
    holder: CustomUser | None = wing.current_supervisor(on_date=day)  # type: ignore[no-untyped-call]
    return holder


def grid_roles(user: CustomUser, class_group: ClassGroup, day: dt.date) -> frozenset[str]:
    """أدوارُ المستخدم في هذه الشعبة لهذا اليوم: `teacher` (إسنادٌ) و`holder` (حاملُ جناحها) و`leadership` (قيادةٌ إداريّةٌ أو حاصرُ الغياب العامّ) و`reader` (نائبٌ أكاديميّ).

    فارغةٌ لغير المخوَّل (مطوّرٌ، مدرسةٌ أخرى، معلّمٌ لشعبةٍ غيرِ شعبته) — يُردّ 404.
    """
    if not getattr(user, "is_authenticated", False) or is_developer(user):
        return frozenset()
    school_roles = _roles_in_school(user, class_group.school_id)
    if not school_roles:
        return frozenset()
    from wings.services import holds_school_wide

    found: set[str] = set()
    if school_roles & GRID_WRITER_ROLES or holds_school_wide(user):
        found.add(GRID_LEADERSHIP)
    holder = _wing_holder_on(class_group, day)
    if holder is not None and holder.id == user.id:
        found.add(GRID_HOLDER)
    if is_class_assigned(user, class_group):
        found.add(GRID_TEACHER)
    if "vice_academic" in school_roles:
        found.add(GRID_READER)
    return frozenset(found)


def can_read_grid(
    user: CustomUser,
    class_group: ClassGroup,
    day: dt.date,
    *,
    roles: frozenset[str] | None = None,
) -> Verdict:
    """هل يقرأ هذا المستخدمُ جدولَ هذه الشعبة؟ — كلُّ دورٍ في `grid_roles`. و`roles` محسوبةٌ سلفاً تُجنّب إعادةَ الاستعلام لكلّ عمود."""
    found = grid_roles(user, class_group, day) if roles is None else roles
    return _allow() if found else _deny("not_found")


def can_write_grid(
    user: CustomUser,
    class_group: ClassGroup,
    day: dt.date,
    *,
    period_start: dt.time | None = None,
    now: dt.datetime | None = None,
    roles: frozenset[str] | None = None,
) -> Verdict:
    """هل يكتب هذا المستخدمُ رصداً في عمودٍ من جدول الشعبة الآن؟ — معلّمو الإسناد وحاملُ الجناح والقيادةُ الإداريّةُ على كلّ الأعمدة.

    الوقتُ يُقرأ هنا لحظةَ الكتابة بتوقيت المدرسة لا عند عرض الصفحة: اليومُ هو اليومُ الجاري وحدَه (لا ماضيَ ولا مستقبلَ)، ومن فتح النافذة
    (07:10) إلى إغلاقها (14:00)؛ وعمودٌ لم تبدأ حصّتُه (`period_start`) يُرفض لكلّ كاتب (`before_start`) فلا يملأ معلّمٌ ح1–ح7 في 07:10.
    وبعد الإغلاق يُقفل الكلُّ هنا ويصحّح المشرفُ بسببٍ عبر `can_correct_grid`.
    """
    roles = grid_roles(user, class_group, day) if roles is None else roles
    if not roles:
        return _deny("not_found")
    if not roles & {GRID_TEACHER, GRID_HOLDER, GRID_LEADERSHIP}:
        return _deny("read_only")
    if class_group.is_active is False:
        return _deny("inactive_class")
    moment = grid_now(now)
    if moment.date() != day:
        return _deny("not_today")
    opens, closes = grid_window(day)
    if moment < opens:
        return _deny("before_window")
    if moment > closes:
        return _deny("after_window")
    if period_start is not None and moment < timezone.make_aware(
        dt.datetime.combine(day, period_start)
    ):
        return _deny("before_start")
    return _allow()


def can_correct_grid(
    user: CustomUser,
    class_group: ClassGroup,
    day: dt.date,
    *,
    now: dt.datetime | None = None,
) -> Verdict:
    """التصحيحُ بعد إغلاق النافذة (14:00) — لحاملِ الجناح والقيادةِ الإداريّة وحدَهم، بسببٍ إلزاميٍّ تفرضه الخدمة؛ لا المعلّمُ ولا النائبُ الأكاديميّ.

    في اليوم نفسِه وحدَه (لا ماضيَ يُصحَّح من هنا، D-215م). وقبل الإغلاق تكفي `can_write_grid`.
    """
    roles = grid_roles(user, class_group, day)
    if not roles & {GRID_HOLDER, GRID_LEADERSHIP}:
        return _deny("not_found" if not roles else "not_corrector")
    moment = grid_now(now)
    if moment.date() != day:
        return _deny("not_today")
    return _allow()
