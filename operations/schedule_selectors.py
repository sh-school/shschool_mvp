"""operations/schedule_selectors.py — قراءةُ سياق ورقة الجدول، بلا `request`.

طبقةُ قراءةٍ (selectors) لا عرض: حارسُ الطبقات (`tests/layering_ratchet.py`)
يسقف كلَّ دالّةٍ في ملفّ عروضٍ بستّين سطراً وخمسة استدعاءات ORM — وهذا هو
جوهرُ ورقة الجدول (اختيارٌ وسياقٌ كاملان)، لا العرضُ الذي يستقبل ويردّ.

وفصلُه هنا ليس تجميلاً معماريّاً وحده: البند 5 (خارطة إصلاح الباك اند
2026-09-18) نقل توليدَ PDF/Excel الثقيل إلى عاملٍ خلفيٍّ في Celery
(`operations/tasks.py::render_schedule_export_task`) — ولا `request` حقيقيّاً
هناك، فوجب أن يُبنى السياقُ من `school`/`user`/`get_params` صريحةً لا
ضمنيّاً من طلبٍ. `views_schedule.py` يستدعي الدوال هنا بمعطيات الطلب،
والعاملُ يستدعيها بمعطياتٍ أعاد بناءها من `query_string` محفوظة.
"""

from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import CustomUser, Membership
from core.permissions import SCHEDULE_BROWSE

from .models import ScheduleGeneration, ScheduleSlot
from .schedule_paper import (
    annotate_teacher_exemptions,
    bell_tables,
    grid_to_days,
    paper_geometry,
    teacher_bands_by_day,
    teacher_exemption_map,
    week_layout,
)
from .services import ScheduleService
from .services.schedule_week import KIND_LABELS

#: أحجامُ الورق واتّجاهاتُه — تُقرأ من الرابط ولا تُخمَّن من نوع العرض.
ORIENTATIONS = ("landscape", "portrait")
PAPERS = ("a4", "a3")
DEFAULT_ORIENTATION = "landscape"

#: مصدرُ الورقة: الأسبوعُ الفعليّ من حصص الأيّام، أو الخطّةُ المعتمدة. والصفحةُ تفتح على الأوّل
#: (قرارُ المالك 2026-09-25) والطباعةُ والتصديرُ على الثانية ما لم يُطلب الأوّلُ صراحةً — فالجدولُ
#: المعلَّقُ في المدرسة هو الخطّةُ لا أسبوعٌ بعينه.
SOURCES = ("actual", "plan")

#: أبعدُ ما يُتنقَّل إليه من الأسبوع الجاري: سنةٌ تقريباً. وأبعدُ منه — أو تاريخٌ معطوب — يرتدّ إليه.
MAX_WEEKS_AWAY = 60


def browse_lists(school):
    """معلّمو المدرسة وشُعبُها لقائمة الجداول — لمن يتصفّح غيره."""
    from core.models import ClassGroup

    teacher_ids = Membership.objects.filter(
        school=school,
        is_active=True,
        role__name__in=("teacher", "coordinator", "e_projects_coordinator"),
    ).values_list("user_id", flat=True)
    teachers = CustomUser.objects.filter(id__in=teacher_ids).order_by("full_name")
    classes = ClassGroup.objects.filter(
        school=school, academic_year=academic_year_for_school(school), is_active=True
    ).in_school_order()
    return teachers, classes


def _week_start(raw, today) -> date:
    """أحدُ الأسبوع المطلوب في `?week=` — والجاري إن غاب أو عُطب أو بَعُد عن مدى التنقّل."""
    this = ScheduleService._get_week_bounds(today)[0]
    try:
        asked = ScheduleService._get_week_bounds(date.fromisoformat(raw))[0]
    except (TypeError, ValueError):
        return this
    return asked if abs((asked - this).days) <= MAX_WEEKS_AWAY * 7 else this


def schedule_print_selection(school, user, get_params, default_source="plan"):
    """ما يُطبع ولمن — يشترك فيه الورقُ وصفحةُ العرض التي تحتضنه."""
    from core.models import ClassGroup

    year = get_params.get("year") or academic_year_for_school(school)
    # الورقةُ المعلّقة في المدرسة هي «الجدول العام للمعلمين»: المعلّمون
    # سطوراً والأسبوعُ عرضاً. وكان الافتراضُ `school` — خمسُ خاناتٍ تحشر
    # فيها ألفُ حصّةٍ فلا تُقرأ ولا تُطبع.
    # ثلاثةُ عروض: الجدولُ العامّ، ومعلّمٌ، وشعبة. وكان رابعٌ «جدول المدرسة
    # الكامل» — خمسُ خاناتٍ تُحشر فيها ألفُ حصّة — فأُزيل (قرار 2026-09-06)،
    # ورابطٌ قديمٌ يطلبه يُصرف إلى الجدول العامّ.
    view_type = get_params.get("view", "all_teachers")
    if view_type not in ("all_teachers", "teacher", "class"):
        view_type = "all_teachers"
    paper = get_params.get("paper") or ("a3" if view_type == "all_teachers" else "a4")
    if paper not in PAPERS:
        paper = "a4"
    # الاتّجاهُ اختيارُ الطابع لا نتيجةُ حجم الورق. وافتراضُه ما كان قبل أن
    # يصير خياراً: الجدولُ العامّ والورقةُ الكبيرةُ عرضاً، وغيرُهما طولاً —
    # فلا يتبدّل مطبوعُ أحدٍ من تحته يومَ أُضيف الخيار.
    orient = get_params.get("orient")
    if orient not in ORIENTATIONS:
        # الجدولُ المفرد صار سطراً لكلّ يومٍ وعموداً لكلّ حصّة (قرار 2026-09-08):
        # سبعةُ أعمدةٍ على A4 عموديّ أربعةٌ وعشرون ملّيمتراً للعمود، تُلَفّ فيها
        # «التربية الإسلامية» فوق اسم الشعبة فوق التوقيت. وعلى الأفقيّ ستّةٌ
        # وثلاثون — فصار الأفقيُّ افتراضَ الجميع، واختيارُ الطابع فوقه.
        orient = DEFAULT_ORIENTATION
    teacher_id = get_params.get("teacher")
    class_id = get_params.get("class")

    target_teacher = None
    target_class = None

    # المعلّم يطبع جدوله هو. وكان الاختيار يُقرأ من الرابط بلا نظرٍ إلى
    # طالبه، و`get_object_or_404(CustomUser, id=…)` بلا قيد مدرسة — أي
    # جدولُ معلّمٍ في مدرسةٍ أخرى.
    may_browse = user.is_admin() or user.get_role() in SCHEDULE_BROWSE

    if not may_browse:
        view_type = "teacher"
        target_teacher = user
    elif view_type == "teacher" and teacher_id:
        # ومن غادر يبقى جدولُ عامه منسوباً إليه — فالبحثُ في كلّ من كان منها.
        target_teacher = get_object_or_404(CustomUser.objects.ever_in_school(school), id=teacher_id)
    elif view_type == "class" and class_id:
        target_class = get_object_or_404(ClassGroup, id=class_id, school=school)

    # قائمتا الاختيار لمن يتصفّح غيره وحده: عرضُهما على المعلّم يُظهر
    # أسماء زملائه وشُعب المدرسة في أداةٍ لا تعمل له أصلاً.
    teachers, classes = browse_lists(school) if may_browse else ([], [])

    # معاينةُ مسودّةِ توليدٍ قبل اعتمادها — لمن يتصفّح الجداول وحدَه، فالمسودّةُ
    # ليست جدولَ أحدٍ بعد. ومن يعتمد جدولاً لم يرَه يعتمد رقماً لا جدولاً.
    preview = None
    generation_id = get_params.get("generation")
    if generation_id and may_browse:
        preview = get_object_or_404(
            ScheduleGeneration, id=generation_id, school=school, academic_year=year
        )

    # مسودّةُ توليدٍ ليست في حصص الأيّام بعد: تُعاين من الخطّة دائماً.
    source = get_params.get("source")
    source = "plan" if preview else source if source in SOURCES else default_source
    week_start = _week_start(get_params.get("week"), timezone.localdate())

    title = "الجدول الدراسي العام"
    if view_type == "all_teachers":
        title = "الجدول العام للمعلمين"
    elif target_teacher:
        title = f"جدول المعلم: {target_teacher.full_name}"
    elif target_class:
        title = f"جدول الفصل: {target_class.label_with_track}"

    # الاختيارُ نفسه سؤالاً في الرابط: الإطارُ وزرّا التصدير ثلاثةُ روابطَ
    # تقصد الورقة الواحدة، فبناؤها ثلاثَ مرّاتٍ في القوالب يجعل اختلافها
    # مسألةَ وقت — يُنسى معاملٌ في أحدها فيُصدَّر جدولُ غير المعروض.
    selection = {"view": view_type, "paper": paper, "orient": orient, "year": year}
    if preview:
        selection["generation"] = str(preview.id)

    picker_current = "matrix"
    if target_teacher:
        picker_current = f"teacher:{target_teacher.id}"
    elif target_class:
        picker_current = f"class:{target_class.id}"
    if target_teacher:
        selection["teacher"] = str(target_teacher.id)
    if target_class:
        selection["class"] = str(target_class.id)
    # ما تحمله روابطُ التنقّل قبل أن يُضاف إليه المصدرُ والأسبوع: كلٌّ منها يضيف ما يخصّه.
    base = dict(selection)
    # المصدرُ في الرابط دائماً: الورقةُ المستقلّةُ تُصدِّر عبر صفحة الجدول وهي تفتح على الأسبوع
    # الفعليّ، فورقةُ خطّةٍ بلا مصدرٍ في رابطها كانت تُصدَّر أسبوعاً فعليّاً غيرَ ما تعرضه.
    selection["source"] = source
    if source == "actual":
        # والأسبوعُ معه: فالإطارُ وزرّا التصدير والطباعةُ تتبعه لا الخطّةَ.
        selection["week"] = week_start.isoformat()

    return {
        "school": school,
        "year": year,
        "view_type": view_type,
        "paper": paper,
        "orient": orient,
        "target_teacher": target_teacher,
        "target_class": target_class,
        "preview": preview,
        "may_browse": may_browse,
        "picker_current": picker_current,
        "teachers": teachers,
        "classes": classes,
        "title": title,
        # عنوانُ الترويسة يُبنى هنا: المسودّةُ تُسمّى في العنوان لا في وسمٍ شرطيّ.
        "heading": f"{title} — مسودّة" if preview else title,
        "selection_query": urlencode(selection),
        "source": source,
        "week_start": week_start,
        "selection_base": base,
    }


def _read_sheet(ctx: dict, school, year) -> tuple[dict, list, Any]:
    """(شبكةُ المعلّم/الشعبة، صفوفُ الجدول العامّ، حصصُ الأسبوع) من المصدر المختار.

    الأسبوعُ الفعليّ من `Session` (`get_week_schedule`/`get_week_matrix`) والخطّةُ من `ScheduleSlot`؛
    والشكلُ واحدٌ فتقرؤه الورقةُ نفسُها بلا تفريق. والثالثُ `None` للخطّة.
    """
    actual = ctx["source"] == "actual"
    if ctx["view_type"] == "all_teachers":
        if actual:
            found = ScheduleService.get_week_matrix(school, ctx["week_start"], year)
            return {}, found["rows"], found["week"]
        return (
            {},
            ScheduleService.get_teachers_matrix(school, year, generation=ctx["preview"]),
            None,
        )
    if actual:
        found = ScheduleService.get_week_schedule(
            school, ctx["week_start"], ctx["target_teacher"], ctx["target_class"], year
        )
        return found["grid"], [], found["week"]
    return (
        ScheduleService.get_weekly_schedule(
            school, ctx["target_teacher"], ctx["target_class"], year, generation=ctx["preview"]
        ),
        [],
        None,
    )


def week_nav(ctx: dict, week_info) -> dict:
    """ما تحتاجه شريطُ التنقّل: الأسبوعُ ورابطاه والتبديلُ بين المصدرين وملاحظاتُ الأسبوع.

    الروابطُ استعلاماتٌ جاهزةٌ (`?…`) على قاعدة الاختيار الحاليّ — فيبقى المعلّمُ والشعبةُ والورقُ
    كما هي وتتبدّل المعاملاتُ الخاصّةُ به وحدَها.
    """
    start = ctx["week_start"]
    this = ScheduleService._get_week_bounds(timezone.localdate())[0]
    week = timedelta(days=7)

    def qs(**extra) -> str:
        return urlencode({**ctx["selection_base"], **extra})

    nav = {
        "start": start,
        "end": start + timedelta(days=4),
        "is_this_week": start == this,
        "prev_qs": qs(source="actual", week=(start - week).isoformat()),
        "next_qs": qs(source="actual", week=(start + week).isoformat()),
        "this_qs": qs(source="actual"),
        "actual_qs": qs(source="actual", week=start.isoformat()),
        "plan_qs": qs(source="plan"),
        "plan_days": [],
        "closed_text": "",
        "unplaced": 0,
        "kinds": [],
    }
    if week_info is not None:
        names = dict(ScheduleSlot.DAYS)
        nav["plan_days"] = [names[i] for i in sorted(week_info.plan_days)]
        nav["closed_text"] = "؛ ".join(
            f"{names[i]}: {why}" for i, why in sorted(week_info.closed.items())
        )
        nav["unplaced"] = week_info.unplaced
        present = {cell.kind for cell in week_info.lessons if cell.kind}
        nav["kinds"] = [(kind, label) for kind, label in KIND_LABELS.items() if kind in present]
    return nav


def schedule_print_payload(school, user, get_params, default_source="plan") -> dict:
    """سياقُ الورقة كاملاً: الاختيارُ وبياناته.

    ثلاثةُ مخارجَ تقرأ هذه الورقة — صفحةٌ في المتصفّح، وPDF، وExcel — فبناؤها
    في موضعٍ واحد يمنع أن يختلف المطبوعُ عن المعروض بعد تعديلٍ في أحدهما.
    و`default_source`: مصدرُ من لم يطلب مصدراً — الصفحةُ «actual» وما سواها «plan».
    """
    ctx = schedule_print_selection(school, user, get_params, default_source)
    school, year = ctx["school"], ctx["year"]

    # الجدولُ العام يكشف جداول المعلّمين جميعاً، ومن لا يتصفّح غيره صُرف
    # إلى جدوله في اختيار الطباعة.
    grid, matrix, week_info = _read_sheet(ctx, school, year)
    matrix_totals, week, geometry = None, None, None
    has_colored_exemptions = False
    if ctx["view_type"] == "all_teachers":
        matrix_totals = ScheduleService.matrix_totals(matrix, school, year)
        has_colored_exemptions = any(row.get("exempt_map") for row in matrix)
    else:
        # الفسحةُ والصلاةُ بين الحصص، والورقةُ بالملّيمتر — كورقة الصفحات سواءً.
        days = grid_to_days(grid)
        band_codes = ScheduleService._band_codes(school)
        target_class = ctx["target_class"]
        if target_class is not None:
            band = band_codes.get(target_class.time_band_id)
            bands = [[band] if band else []] * 5
        else:
            bands = teacher_bands_by_day(days, band_codes)
        week = week_layout(days, bands, bell_tables(school))
        # تلوينُ خانات التفريغ بمصدره — للمعلّم وحدَه، فالشعبةُ لا تفريغَ لها.
        if ctx["target_teacher"] is not None:
            exemption_map = teacher_exemption_map(school, ctx["target_teacher"], year)
            if exemption_map:
                annotate_teacher_exemptions(week, exemption_map)
                has_colored_exemptions = True
        geometry = paper_geometry(ctx["paper"], ctx["orient"], with_who=False)

    # أسماءُ الأيّام من `ScheduleSlot.DAYS` — مصدرٌ واحدٌ يقرؤه المولّدُ والورقة.
    days_names = list(ScheduleSlot.DAYS)
    # الورقة المطبوعة تحمل توقيت كل حصة تحت رقمها، كما في جدول المدرسة —
    # وكانت الخلايا بلا توقيتٍ أصلاً.
    times = ScheduleService.period_times(school, year)
    periods = [
        {"number": n, "start": times.get(n, (None, None))[0], "end": times.get(n, (None, None))[1]}
        for n in ScheduleSlot.PERIODS
    ]

    return {
        **ctx,
        "grid": grid,
        "week": week,
        "geo": geometry,
        "matrix": matrix,
        "matrix_totals": matrix_totals,
        "week_info": week_info,
        "nav": week_nav(ctx, week_info),
        "has_colored_exemptions": has_colored_exemptions,
        "days": days_names,
        "periods": periods,
        "period_numbers": range(1, 8),
        # داخل الإطار: الورقةُ وحدها، وأدواتُها في الصفحة الحاضنة.
        "embed": get_params.get("embed") == "1",
    }


def export_filename(ctx: dict, extension: str) -> str:
    """اسمُ الملفّ: عنوانُ الورقة وسنتُها.

    و`get_valid_filename` يُسقط ما لا يقبله اسمُ ملفٍّ ولا ترويسةُ HTTP —
    والعربيّةُ تبقى فيه حروفاً، فالاسمُ يُقرأ بعد التنزيل.
    """
    from django.utils.text import get_valid_filename

    stem = f"{ctx.get('title') or 'الجدول'} {ctx.get('year') or ''}".strip()
    return f"{get_valid_filename(stem)}.{extension}"
