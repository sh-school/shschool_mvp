"""
quality/observation_selectors.py — قراءاتُ الإشراف على أداء المعلّم.

طبقةُ القراءة (Skinny Views / Fat Selectors): كلُّ استعلامٍ يبني سياقَ
الاستمارة أو صفَّ الجدول اليوميّ هنا — لا في `observation_views.py`، الذي
يستدعي هذه الدوالَّ استدعاءً واحداً بلا تكرارِ منطقِها (`tests/layering_ratchet.py`
يحسب استدعاءاتِ ORM داخل ملفّات العروض؛ الاستدعاءُ من طبقةٍ كهذه لا يُحسَب
تضخيماً على العارض).
"""

from __future__ import annotations

import datetime as dt

from core.academic_calendar import academic_year_for_school
from core.dept_colors import OTHER, dept_key
from core.models import CustomUser
from operations.school_days import is_school_day

from .observation_models import MAX_SELF_BACKDATE_DAYS, OBSERVATION_DOMAINS
from .observation_services import ObservationService

#: أدوارٌ تُعَدّ «معلّماً» عند بناء قوائم الاستمارة (اختيار المعلّم/الزميل).
TEACHER_ROLES = [
    "teacher",
    "ese_teacher",
    "coordinator",
    "activities_coordinator",
    "e_projects_coordinator",
]


def grouped_criteria(school):
    """[(domain_label, [criterion, ...])] مرتّبة حسب المجال ثم الترتيب."""
    crits = list(ObservationService.criteria_for(school))
    groups = []
    for domain, label in OBSERVATION_DOMAINS:
        items = [c for c in crits if c.domain == domain]
        if items:
            groups.append((label, items))
    return groups


def groups_with_scores(obs):
    scores = {str(s.criterion_id): s for s in obs.scores.select_related("criterion")}
    return [
        (label, [(c, scores.get(str(c.id))) for c in items])
        for label, items in grouped_criteria(obs.school)
    ]


def teacher_picker_groups(school, teachers):
    """قائمةُ المعلّمين مُجمَّعةً حسب القسم الأكاديميّ — المنسّقُ أوّلاً في كلِّ
    قسم (طلب المالك 2026-09-22: القسمُ ظاهرٌ بلونه كالجدول العامّ المطبوع،
    والمنسّقُ مُميَّزٌ في رأس مجموعته). ثمّ صار اللونُ خلفيّةَ بطاقة القسم
    كلِّها (2026-09-23) — ولرموز `--dept-*` نظيرٌ ليليّ فيبقى التباينُ سليماً.

    مصدرٌ واحد: `core/dept_colors.py` — كودُ القسم إلى لونه كما في مصفوفة الجدول
    المطبوعة (`templates/schedule/print_schedule.html`)، لا نسخةَ ثانية من الخريطة هنا.
    """
    from core.models.department import Department

    by_id = {t.id: t for t in teachers}
    depts = (
        Department.objects.filter(school=school, is_active=True)
        .select_related("head")
        .order_by("sort_order", "name")
    )
    groups = []
    grouped_ids: set = set()
    for dept in depts:
        dept_teacher_ids = dept.get_teacher_ids() & by_id.keys()
        if not dept_teacher_ids:
            continue
        grouped_ids |= dept_teacher_ids
        # المنسّقُ يظهر مرّةً واحدةً بجانب اسم القسم لا داخل قائمة معلّميه —
        # طلب المالك 2026-09-22.
        head = by_id.get(dept.head_id) if dept.head_id in dept_teacher_ids else None
        rest_ids = dept_teacher_ids - ({dept.head_id} if head else set())
        members = sorted((by_id[tid] for tid in rest_ids), key=lambda t: t.full_name)
        groups.append(
            {
                "name": dept.name,
                "css_class": dept_key(dept.code),
                "head": head,
                "teachers": members,
            }
        )
    rest = sorted((t for t in teachers if t.id not in grouped_ids), key=lambda t: t.full_name)
    if rest:
        groups.append({"name": "بلا قسم مسجَّل", "css_class": OTHER, "head": None, "teachers": rest})
    return groups


def form_lists(school):
    from core.models.academic import ClassGroup
    from operations.models import Subject

    teachers = list(
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__role__name__in=TEACHER_ROLES,
            memberships__is_active=True,
        ).distinct()
    )
    return {
        "teachers": sorted(teachers, key=lambda t: t.full_name),
        "teacher_groups": teacher_picker_groups(school, teachers),
        "subjects": Subject.objects.filter(school=school).order_by("name_ar"),
        "class_groups": ClassGroup.objects.filter(
            school=school, academic_year=academic_year_for_school(school)
        ).in_school_order(),
    }


def default_observation_date(school):
    """أقربُ يومِ دراسةٍ للخلف من اليوم — لا اليوم حرفيّاً: لو صادف الجمعةَ أو
    السبتَ أو إجازةً كان تاريخُ الاستمارة الافتراضيُّ يوماً بلا حصصٍ أصلاً."""
    from datetime import timedelta

    from django.utils import timezone

    day = timezone.localdate()
    for _ in range(14):
        if is_school_day(school, day):
            return day
        day -= timedelta(days=1)
    return timezone.localdate()


# ══════════════════════════ نافذة التقييم الذاتي وتحقّقه الخادميّ ═════
def self_date_error(selected_date: dt.date, today: dt.date | None = None) -> str:
    """رسالةُ خطأ إن كان تاريخُ التقييم الذاتي مستقبلاً أو أقدمَ من النافذة، وإلا نصٌّ فارغ (D-417م).

    النافذةُ [اليوم − MAX_SELF_BACKDATE_DAYS ، اليوم]: لا يُقيِّم المعلّمُ حصّةً لم تقع بعد، ولا حصّةً
    مضى عليها أسبوعٌ فأكثر (يُنسى فيها الأدلّةُ فيفقد التقييمُ الذاتيُّ معناه).
    """
    from django.utils import timezone

    today = today or timezone.localdate()
    if selected_date > today:
        return "لا يُقيَّم يومٌ لم يأتِ بعد — اختر اليومَ أو يوماً سابقاً."
    if (today - selected_date).days > MAX_SELF_BACKDATE_DAYS:
        return f"التقييمُ الذاتيّ لحصّةٍ لا يتجاوز {MAX_SELF_BACKDATE_DAYS} أيّامٍ إلى الوراء."
    return ""


def self_slot_error(school, teacher, header: dict, *, outside_schedule: bool) -> str:
    """تحقّقُ الخادم من رأس التقييم الذاتي قبل الحفظ — لا يُعتمد على ما رسمه المتصفّح.

    المعلّمُ هنا هو المستخدم الحاليّ دائماً (لا يُقرأ من الطلب). والنافذةُ تُفحص أوّلاً حتى لا يُستدعى
    `ensure_sessions_for_date` لتاريخٍ خارجها. ثمّ، ما لم يكن «خارج جدولي»، يجب أن تكون الحصّةُ
    (المادّة، الشعبة، رقم الحصّة) بين حصص هذا المعلّم في ذلك اليوم من المصدر نفسه الذي يعرضه الصفّ (لا نسخة ثانية).
    """
    from django.utils import timezone

    raw = header.get("observation_date") or timezone.localdate()
    try:
        selected = raw if isinstance(raw, dt.date) else dt.date.fromisoformat(str(raw))
    except ValueError:
        return "تاريخٌ غير صالح."
    window_error = self_date_error(selected)
    if window_error:
        return window_error
    if outside_schedule:
        return ""
    ctx = teacher_schedule_context(school, teacher.id, selected, self_mode=True)
    wanted = (
        str(header.get("subject_id") or ""),
        str(header.get("class_group_id") or ""),
        str(header.get("period") or ""),
    )
    for slot in ctx["periods"]:
        s = slot["session"]
        if (str(s.subject_id or ""), str(s.class_group_id), str(slot["number"])) == wanted:
            return ""
    return "الحصّةُ المختارة ليست في جدولك ذلك اليوم — اخترها من جدولك أو فعّل «حصّة خارج جدولي»."


# ══════════════════════════ جدول المعلّم عند إنشاء الزيارة ═══════════
def teacher_schedule_context(school, teacher_id, raw_date, *, self_mode: bool = False) -> dict:
    """SOS-20260915: صفٌّ واحد من حصص المعلّم في التاريخ المختار — يُختار
    منه بنقرة بدل إدخال المادّة والشعبة يدويّاً عن ظهر قلب. المصدر Session
    نفسه الذي يقرأه جدولُ المعلّم اليوميّ (`operations.views_attendance.schedule`)
    لا نسخةٌ ثانية قد تختلف عنه.

    مصدرٌ واحد لاستعلام الجدول: تستدعيه هذه الدالّة عند فتح الاستمارة
    للتعديل (تعرِض حصص تاريخ الزيارة المحفوظ من أوّل تحميل) وview الـHTMX
    عند تغيير المعلّم أو التاريخ (`observation_teacher_schedule`).
    """
    from operations.models import ScheduleSlot, Session
    from operations.services import ScheduleService

    teacher_id = teacher_id or ""
    raw_date = raw_date or ""
    periods: list[dict] = []
    error = ""
    if teacher_id and raw_date:
        try:
            selected_date = (
                raw_date if isinstance(raw_date, dt.date) else dt.date.fromisoformat(raw_date)
            )
        except ValueError:
            selected_date = None
        if selected_date is None:
            error = "تاريخٌ غير صالح."
        elif self_mode and self_date_error(selected_date):
            # الوضعُ الذاتيّ: خارج النافذة لا يُستعلَم ولا يُولَّد `Session` لتاريخٍ قديمٍ أو مستقبليّ.
            error = self_date_error(selected_date)
        elif not is_school_day(school, selected_date):
            # الجمعة والسبت والإجازاتُ من تقويم الوزارة: لا حصصَ فيها أصلاً،
            # فرسالةٌ صريحة بدل صفٍّ فارغٍ صامت (كان المستخدم يظنّه عطلاً).
            error = "ليس يومَ دراسةٍ — عطلةٌ أسبوعيّة أو إجازةٌ في تقويم المدرسة."
        else:
            ScheduleService.ensure_sessions_for_date(school, selected_date)
            sessions = list(
                Session.objects.filter(school=school, teacher_id=teacher_id, date=selected_date)
                .exclude(status="cancelled")
                .select_related("subject", "class_group")
                .order_by("start_time")
            )
            # رقمُ الحصّة الحقيقيّ من ScheduleSlot لا من ترتيب حصص المعلّم في
            # يومه: معلّمٌ حصصه الثلاث اليوم في ح2/ح4/ح6 كان يظهر ح1/ح2/ح3
            # بالعدّ البسيط — فيُسجَّل رقمُ حصّةٍ خاطئٌ في محضر الزيارة نفسه.
            # المطابقةُ بـ(الشعبة، وقت البدء) لا المعلّم وحده: التبديلُ يُكتب
            # في Session لا في القالب الأسبوعيّ (راجع Session.original_teacher).
            qatar_day = (selected_date.weekday() + 1) % 7
            period_by_slot = {
                (class_group_id, start_time): period_number
                for class_group_id, start_time, period_number in (
                    ScheduleSlot.objects.live(school, on=selected_date)
                    .filter(
                        day_of_week=qatar_day,
                        class_group_id__in={s.class_group_id for s in sessions},
                    )
                    .values_list("class_group_id", "start_time", "period_number")
                )
            }
            periods = [
                {
                    "number": period_by_slot.get((s.class_group_id, s.start_time), i),
                    "session": s,
                }
                for i, s in enumerate(sessions, start=1)
            ]
    return {"periods": periods, "error": error, "has_query": bool(teacher_id and raw_date)}
