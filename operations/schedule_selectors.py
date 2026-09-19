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

from urllib.parse import urlencode

from django.shortcuts import get_object_or_404

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

#: أحجامُ الورق واتّجاهاتُه — تُقرأ من الرابط ولا تُخمَّن من نوع العرض.
ORIENTATIONS = ("landscape", "portrait")
PAPERS = ("a4", "a3")
DEFAULT_ORIENTATION = "landscape"


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


def schedule_print_selection(school, user, get_params):
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
    }


def schedule_print_payload(school, user, get_params) -> dict:
    """سياقُ الورقة كاملاً: الاختيارُ وبياناته.

    ثلاثةُ مخارجَ تقرأ هذه الورقة — صفحةٌ في المتصفّح، وPDF، وExcel — فبناؤها
    في موضعٍ واحد يمنع أن يختلف المطبوعُ عن المعروض بعد تعديلٍ في أحدهما.
    """
    ctx = schedule_print_selection(school, user, get_params)
    school, year = ctx["school"], ctx["year"]

    # الجدولُ العام يكشف جداول المعلّمين جميعاً، ومن لا يتصفّح غيره صُرف
    # إلى جدوله في اختيار الطباعة.
    grid, matrix, matrix_totals, week, geometry = {}, [], None, None, None
    has_colored_exemptions = False
    if ctx["view_type"] == "all_teachers":
        matrix = ScheduleService.get_teachers_matrix(school, year, generation=ctx["preview"])
        matrix_totals = ScheduleService.matrix_totals(matrix, school, year)
        has_colored_exemptions = any(row.get("exempt_map") for row in matrix)
    else:
        grid = ScheduleService.get_weekly_schedule(
            school, ctx["target_teacher"], ctx["target_class"], year, generation=ctx["preview"]
        )
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
