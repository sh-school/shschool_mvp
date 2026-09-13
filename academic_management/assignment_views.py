"""شاشةُ «الإسناد» الواحدة — بطاقةٌ لكلّ معلّم، والحفظُ في لحظته.

قرارُ الإدارة 2026-09-06: تبسيطٌ إلى أقصاه. كانت صفحتان — «توزيعات المواد على
الشُّعب» تكتب ولا تُري الصورة، و«إسناد الأنصبة» تُري الصورة ولا تكتب — وبينهما
محرّرُ خطّةٍ بسبعة أقسامٍ ومراجعَ ورموزِ سياسات. فصارت بطاقةً واحدةً لكلّ معلّم:

    المعلّم · نصابُه · [المرحلة · الشعبة · المادّة · الحصص · يحضّر ✓] …

لا تخفيضَ ولا مرجعَ ولا رمزَ سياسة. الشعبةُ تُختار فتظهر موادُّ خطّتها
الوزاريّة، والمادّةُ تُختار فتُملأ الحصصُ من الخطّة وتُحفظ من فورها (HTMX)،
وعبءُ التحضير حصّتان لكلّ مقرّر (قرارُ 2026-09-05).

## من يفعل ماذا

المنسّقُ يُدخل لمعلّمي قسمه — من سجلّ العضويّات — ثمّ يرفع. والنائبُ الأكاديميُّ
يراجع، والمديرُ يعتمد؛ ولهما معاً كلُّ الأقسام وكلُّ التعديل. وهذه القدراتُ
تُقرأ من `workload_workflow` لا تُكتب هنا، فتبقى بوّابةُ الاعتماد وختمُه كما هي.

والكتابةُ كلُّها تمرّ بـ`assignment_service` فتُفحص وتُدقَّق كما كانت.
"""

from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from academic_management import assignment_service, curriculum_service, load
from academic_management import workload_workflow as flow
from academic_management.models import (
    DRAFT,
    FROZEN_STATUSES,
    REVIEWED,
    SUBMITTED,
    CoursePreparation,
    TeacherWorkloadPlan,
)
from core.academic_calendar import academic_year_for
from core.models import ClassGroup, CustomUser, Department, Membership
from core.models.academic import grade_order
from core.models.access import DEPARTMENT_ROLES
from operations import departments as dept_map
from operations.models import Subject, SubjectClassAssignment

MODULE_NAME = "إدارة الشؤون الأكاديمية"
#: من تُطبع له بطاقة — الأدوارُ التي تُدرّس.
TEACHING_ROLES = ("teacher", "ese_teacher", "coordinator", "e_projects_coordinator")
LEVEL_LABELS = {"prep": "إعدادي", "sec": "ثانوي"}


# ══════════════════════════════════════════════════════════════════════
#  القدرة والنطاق
# ══════════════════════════════════════════════════════════════════════


def _caps(user, school):
    """قدراتُ هذا المستخدم على الأنصبة — إدخالٌ ومراجعةٌ واعتماد."""
    return {
        "edit": flow.has_capability(user, school, flow.EDIT),
        "review": flow.has_capability(user, school, flow.REVIEW),
        "approve": flow.has_capability(user, school, flow.APPROVE),
    }


def _registry_filled(school) -> bool:
    return Department.objects.filter(school=school, is_active=True).exists()


def _department_key(person, school, year):
    """مفتاحُ قسم شخصٍ واحد — سجلُّه، وإلّا الغالبُ على حصصه.

    وتُقدَّم عضويّةُ التدريس: من كان معلّماً وله عضويّةٌ ثانيةٌ بدورٍ إداريّ
    لا قسمَ لها، فلولا الترتيبُ لقُرئ بلا قسم.
    """
    membership = (
        Membership.objects.filter(user=person, school=school, is_active=True)
        .select_related("department_obj")
        .order_by("department_obj__sort_order")
        .first()
    )
    rows = (
        SubjectClassAssignment.objects.live(school, year=year)
        .filter(teacher=person)
        .select_related("class_group", "subject")
    )
    department = membership.department_obj if membership else None
    return _department_of(department, list(rows), _registry_filled(school))[0]


def _guard(request, teacher=None):
    """يرفض من لا قدرةَ له، ومن يمدّ يدَه إلى معلّمٍ خارج قسمه.

    تُعيد (المدرسة، القدرات، مفتاحَ نطاق المستخدم، العام). والنطاقُ `None`
    للنائب والمدير: قسمٌ واحدٌ لا يحدّهما.
    """
    school = request.user.get_school()
    caps = _caps(request.user, school)
    if not (caps["edit"] or caps["review"] or caps["approve"]):
        raise PermissionDenied("شاشةُ الإسناد للمنسّق والنائب الأكاديميّ والمدير.")
    year = request.POST.get("year") or request.GET.get("year") or academic_year_for(request)

    unbounded = caps["review"] or caps["approve"] or getattr(request.user, "is_superuser", False)
    scope = None if unbounded else _department_key(request.user, school, year)
    if teacher is not None and scope is not None:
        if _department_key(teacher, school, year) != scope:
            raise PermissionDenied("هذا المعلّمُ خارج قسمك.")
    return school, caps, scope, year


# ══════════════════════════════════════════════════════════════════════
#  بناءُ البطاقة
# ══════════════════════════════════════════════════════════════════════


def _teachers(school):
    """معلّمو المدرسة وقسمُ كلٍّ منهم في السجلّ — أو `None` لمن لم يُسجَّل."""
    memberships = (
        Membership.objects.filter(school=school, is_active=True, role__name__in=TEACHING_ROLES)
        .select_related("user", "department_obj")
        .order_by("department_obj__sort_order", "department_obj__name", "user__full_name")
    )
    seen, out = set(), []
    for m in memberships:
        if m.user_id in seen:
            continue
        seen.add(m.user_id)
        out.append((m.user, m.department_obj))
    return out


#: مفتاحُ من لا قسمَ مسجّلاً له — يظهر ليُصلَح لا ليُخفى.
NO_DEPARTMENT = "none"


def _department_of(department, rows, registry_filled=False):
    """قسمُ المعلّم: السجلُّ إن سُجّل، وإلّا فالغالبُ على حصصه.

    سجلُّ الأقسام هو المصدر متى مُلئ. وهو فارغٌ في قاعدة التطوير — ولو تُرك
    الأمرُ له لظهر المعلّمون جميعاً تحت «بلا قسم» وخلت قائمةُ الترشيح من كلّ
    خيار. فيُشتقّ القسمُ حينئذٍ من الحصص كما تفعل ورقةُ الجدول العام، ويبقى
    السجلُّ متقدّماً متى وُجد.

    تُعيد (المفتاح، الاسم، ترتيبَ العرض).
    """
    if department is not None:
        return (
            f"reg:{department.id}",
            department.name,
            (0, department.sort_order or 0, department.name),
        )
    # متى سُجّلت أقسامُ المدرسة صار غيابُ القسم نقصاً يُعالَج، لا سؤالاً
    # يُجاب عنه بالاشتقاق: من نُقل أو عُيّن حديثاً يظهر هنا حتّى يُسنَد قسمُه.
    if registry_filled:
        return NO_DEPARTMENT, "بلا قسمٍ مسجَّل", (2, 0, "")
    code = dept_map.resolve_from_lessons(
        (row.subject.name_ar, row.class_group.grade, row.weekly_periods) for row in rows
    )
    info = dept_map.department_info(code)
    return f"der:{info['code']}", info["name"], (1, info["order"], info["name"])


def _rows_by_teacher(school, year):
    """كلُّ إسنادات المدرسة مرّةً واحدة — لا استعلامَ لكلّ بطاقة.

    ويُوسَم اليتيمُ في المرور نفسِه: وسمُ توازٍ لا شريكَ له في الشعبة. فمن
    حذف الكيمياءَ من 11/4 بقيت الفنّيّةُ موسومةً وحدَها — ومجموعةٌ بعضوٍ
    واحدٍ ليست توازياً، بل أثرٌ من حذفٍ لم يُنظَّف.
    """
    out = defaultdict(list)
    rows = list(
        SubjectClassAssignment.objects.live(school, year=year)
        .filter(teacher__isnull=False)
        .select_related("class_group", "subject")
        .order_by(grade_order("class_group__grade"), "class_group__section", "subject__name_ar")
    )
    _decorate(rows, _class_peers(school, year, rows))
    for row in rows:
        out[row.teacher_id].append(row)
    return out


def _class_peers(school, year, rows):
    """كلُّ إسنادات الشُّعب التي تخصّ هذه الصفوف — منها الشركاءُ وحكمُ اليتيم.

    والبطاقةُ الواحدةُ تُعاد بصفوف معلّمها وحدَه، فلو قُرئ الشركاءُ منها لخلت
    قائمةُ التوازي إلّا من «لا توازي» — وهو ما رآه المستخدم. فالشعبةُ تُقرأ
    كاملةً ولو كانت موادُّها لمعلّمين آخرين: التوازي بين مادّتين في شعبة، لا
    بين حصّتَي معلّم.
    """
    ids = {row.class_group_id for row in rows}
    if not ids:
        return {}
    peers = defaultdict(list)
    for row in (
        SubjectClassAssignment.objects.live(school, year=year)
        .filter(class_group_id__in=ids)
        .select_related("class_group", "subject")
        .order_by("subject__name_ar")
    ):
        peers[row.class_group_id].append(row)
    return peers


def _decorate(rows, peers):
    """سماتُ العرض التي لا تُحفظ: الشركاءُ واليتيمُ والازدواجُ والتباعدُ الفعليّان."""
    for row in rows:
        tag = (row.parallel_group or "").strip()
        family = peers.get(row.class_group_id, [])
        row.parallel_orphan = (
            bool(tag) and sum(1 for r in family if (r.parallel_group or "").strip() == tag) < 2
        )
        #: ما يقرؤه المولّدُ فعلاً: قرارُ الشعبة إن كُتب، وإلّا إعدادُ المادّة.
        row.double_effective = (
            row.double_period
            if row.double_period is not None
            else row.subject.requires_double_period
        )
        siblings = [r for r in family if r.id != row.id]
        row.parallel_options = siblings
        row.parallel_partner = next(
            (r for r in siblings if tag and (r.parallel_group or "").strip() == tag), None
        )
    return rows


def _prepared_by_teacher(school, year):
    out = defaultdict(set)
    for p in CoursePreparation.objects.live(school, year=year):
        out[p.teacher_id].add((p.grade, p.track, p.subject_id))
    return out


def _classes(school, year):
    return list(
        ClassGroup.objects.filter(
            school=school, academic_year=year, is_active=True, has_own_timetable=False
        ).in_school_order()
    )


def _latest_plan(school, teacher, year):
    return (
        TeacherWorkloadPlan.objects.filter(school=school, teacher=teacher, academic_year=year)
        .order_by("-plan_version")
        .first()
    )


def _plans_by_teacher(school, year):
    """أحدثُ خطّةٍ لكلّ معلّم — استعلامٌ واحدٌ لا واحدٌ لكلّ بطاقة."""
    out = {}
    plans = TeacherWorkloadPlan.objects.filter(school=school, academic_year=year).order_by(
        "teacher_id", "-plan_version"
    )
    for plan in plans:
        out.setdefault(plan.teacher_id, plan)
    return out


def _may_write(plan, caps):
    """هل تُحرَّر بطاقةُ هذا المعلّم الآن؟

    المسودّةُ يحرّرها كلُّ مُدخِل. وما رُفع للمراجعة لا يُعدَّل من تحت المراجع
    إلّا بيده هو — وللنائب والمدير التعديلُ في كلّ حال. والمعتمَدُ لا يُكتب
    فوقه: يُفتح بإصدارٍ جديدٍ بنقرة، فيبقى الموقَّعُ كما وُقِّع.
    """
    if plan is not None and plan.status in FROZEN_STATUSES:
        return False
    if plan is not None and plan.status in (SUBMITTED, REVIEWED):
        return caps["review"] or caps["approve"]
    return caps["edit"]


def _card_rows(school, year, teacher, rows, prepared):
    """صفوفُ البطاقة مزيَّنةً — تُجلب إن لم تُمرَّر، وتُزيَّن إن لم تكن مزيَّنة.

    الصفحةُ كاملةً تجلب الجميعَ مرّةً وتزيّنهم في `_rows_by_teacher`، وبطاقةٌ
    تُعاد وحدَها بعد حفظٍ تمرّ من هنا. وفصلُها عن `_card` ليس ترتيباً: تلك
    بلغت تعقيداً تردّه بوّابةُ الجودة (CC ≥ 31).
    """
    if rows is None:
        rows = list(
            SubjectClassAssignment.objects.live(school, year=year)
            .filter(teacher=teacher)
            .select_related("class_group", "subject")
            .order_by(grade_order("class_group__grade"), "class_group__section", "subject__name_ar")
        )
    if prepared is None:
        prepared = {
            (p.grade, p.track, p.subject_id)
            for p in CoursePreparation.objects.live(school, year=year).filter(teacher=teacher)
        }
    if rows and not hasattr(rows[0], "parallel_options"):
        _decorate(rows, _class_peers(school, year, rows))
    for row in rows:
        row.level_label = LEVEL_LABELS.get(row.class_group.level_type, "")
        row.prepares = (row.class_group.grade, row.class_group.track, row.subject_id) in prepared
    return rows


def _card(
    school,
    year,
    teacher,
    caps,
    *,
    rows=None,
    prepared=None,
    plans=None,
    loads=None,
    classes=None,
    registry=None,
    department=None,
    error=None,
    notes=(),
    transfer=None,
):
    """سياقُ بطاقةٍ واحدة — تُبنى للصفحة وتُعاد وحدَها بعد كلّ حفظ."""
    rows = _card_rows(school, year, teacher, rows, prepared)

    plan = plans.get(teacher.id) if plans is not None else _latest_plan(school, teacher, year)
    status = plan.status if plan else ""
    teacher_load = (loads or {}).get(teacher.id) or load.load_for(school, year, teacher.id)

    # التفريغُ يومَ كاملٍ يضغط النصابَ ولا يُخفّفه — ومن يوقّع على ثمانيةَ عشرَ
    # حصّةً يحقّ له أن يرى أنّها في أربعة أيّام. تُحسب للمرفوع والمُراجَع وحدَهما
    # كي لا تصير الصفحةُ ثلاثةَ استعلاماتٍ في كلّ بطاقةٍ من ثلاثٍ وسبعين.
    room = flow.available_capacity(plan) if plan and status in (SUBMITTED, REVIEWED) else None

    # خطّةٌ اعتُمدت ثمّ تبدّل إسنادُها تحتَها: التوقيعُ على شيءٍ والواقعُ شيءٌ
    # آخر. تُحسب البصمةُ من الصفوف التي في اليد — بلا استعلامٍ لكلّ بطاقة.
    diverged = flow.has_diverged(plan, rows) if plan and status in FROZEN_STATUSES else None

    return {
        "teacher": teacher,
        "rows": rows,
        "load": teacher_load,
        "plan": plan,
        "status": status,
        "status_label": plan.get_status_display() if plan else "بلا خطّة",
        "room": room,
        "diverged": diverged,
        # نقلُ معلّمٍ بين الأقسام قرارُ إدارةٍ — للنائب والمدير وحدَهما.
        "registry": registry if registry is not None else [],
        "department": department if department is not None else _department_object(school, teacher),
        "writable": _may_write(plan, caps),
        "classes": classes if classes is not None else _classes(school, year),
        "year": year,
        "error": error,
        "notes": [n for n in notes if n.level != assignment_service.BLOCK],
        # نقلُ مادّةٍ من زميلٍ — يُعرض ليُؤكَّد لا ليقع صامتاً.
        "transfer": transfer,
        # ── أزرارُ الدورة: مسودّةٌ ← رفعٌ ← مراجعةٌ ← اعتماد ──
        "can_submit": bool(plan) and status == DRAFT and caps["edit"],
        "can_review": bool(plan) and status == SUBMITTED and caps["review"],
        "can_return": bool(plan) and status in (SUBMITTED, REVIEWED) and caps["review"],
        "can_approve": bool(plan) and status == REVIEWED and caps["approve"],
        "can_revise": bool(plan) and status in FROZEN_STATUSES and caps["edit"],
    }


def _department_object(school, teacher):
    membership = (
        Membership.objects.filter(user=teacher, school=school, is_active=True)
        .select_related("department_obj")
        .order_by("department_obj__sort_order")
        .first()
    )
    return membership.department_obj if membership else None


#: قالبُ البطاقة — يُصيَّر مرّتين حين يلزم تحديثُ بطاقتين معاً.
CARD_TEMPLATE = "academic_management/partials/assignment_teacher.html"


def _render_card(request, school, year, teacher, caps, **extra):
    """بطاقةُ معلّمٍ تُعاد — في موضعها هي، ومعها بطاقةُ من طلبها إن اختلفا.

    الصفحةُ تُحدَّث بطاقةً بطاقة، فتبقى بطاقاتُ الزملاء على حالها. فمن ضغط ✕
    أو عدّل حصصاً في بطاقةٍ قديمةٍ بعد أن انتقلت المادّةُ إلى زميل، كان الجوابُ
    **بطاقةَ الزميل تحلّ في موضع البطاقة القديمة**: فيظهر المعلّمُ نفسُه مرّتين
    ويختفي غيرُه — وهو ما رآه المستخدم (2026-09-06).

    فصار الجوابُ يقصد عنصرَه بمعرّفه (`HX-Retarget`)، وتُرسَل معه بطاقةُ العنصر
    الذي طلب (`hx-swap-oob`) محدَّثةً — فتُصحَّح الشاشتان معاً ولا يبقى قديم.
    """
    from django.template.loader import render_to_string

    if "registry" not in extra and caps["review"]:
        extra["registry"] = list(Department.objects.filter(school=school, is_active=True))

    html = render_to_string(
        CARD_TEMPLATE,
        {"card": _card(school, year, teacher, caps, **extra)},
        request=request,
    )
    html += _stale_card_html(request, school, year, caps, teacher)

    response = HttpResponse(html)
    response["HX-Retarget"] = f"#teacher-{teacher.id}"
    response["HX-Reswap"] = "outerHTML"
    return response


def _stale_card_html(request, school, year, caps, rendered_teacher):
    """بطاقةُ العنصر الذي أرسل الطلبَ حين لا تكون بطاقةَ من رُدّ عليه."""
    from django.template.loader import render_to_string

    target = (request.headers.get("HX-Target") or "").removeprefix("teacher-")
    if not target or target == str(rendered_teacher.id):
        return ""
    other = CustomUser.objects.filter(id=target).first() if _is_uuid(target) else None
    if other is None:
        return ""
    return render_to_string(
        CARD_TEMPLATE,
        {"card": _card(school, year, other, caps), "oob": True},
        request=request,
    )


def _is_uuid(value: str) -> bool:
    from uuid import UUID

    try:
        UUID(value)
    except ValueError:
        return False
    return True


# ══════════════════════════════════════════════════════════════════════
#  الصفحة
# ══════════════════════════════════════════════════════════════════════


@login_required
def assignments(request):
    school, caps, scope, year = _guard(request)
    selected = request.GET.get("dept") or ""
    classes = _classes(school, year)
    loads = load.loads_for(school, year)
    rows_by = _rows_by_teacher(school, year)
    prepared_by = _prepared_by_teacher(school, year)
    plans = _plans_by_teacher(school, year)
    registry_filled = _registry_filled(school)
    registry = (
        list(Department.objects.filter(school=school, is_active=True)) if caps["review"] else []
    )

    # قائمةُ الترشيح تُبنى ممّا يظهر فعلاً — فلا خيارَ بلا معلّمين، ولا معلّمَ
    # بلا خيارٍ يبلغه. وعددُ كلّ قسمٍ يُحسب من معلّميه جميعاً لا من المعروضين،
    # كي يبقى الرقمُ ظاهراً في القائمة قبل الاختيار وبعده.
    groups = {}
    for teacher, department in _teachers(school):
        rows = rows_by.get(teacher.id, [])
        key, name, order = _department_of(department, rows, registry_filled)
        if scope is not None and key != scope:
            continue
        group = groups.setdefault(
            key, {"key": key, "name": name, "order": order, "count": 0, "cards": []}
        )
        group["count"] += 1
        if selected and key != selected:
            continue
        group["cards"].append(
            _card(
                school,
                year,
                teacher,
                caps,
                rows=rows,
                prepared=prepared_by.get(teacher.id, set()),
                plans=plans,
                loads=loads,
                classes=classes,
                registry=registry,
                department=department,
            )
        )

    ordered = sorted(groups.values(), key=lambda g: g["order"])
    shown = [g for g in ordered if g["cards"]]
    cards = [c for g in shown for c in g["cards"]]
    return render(
        request,
        "academic_management/assignments.html",
        {
            "page_title": "الإسناد",
            "module_name": MODULE_NAME,
            "year": year,
            "groups": shown,
            "departments": ordered,
            "selected_dept": selected,
            "registry_empty": not registry_filled,
            "coverage": _coverage(school, year),
            "totals": {
                "teachers": len(cards),
                "rows": sum(len(c["rows"]) for c in cards),
                "pending": sum(1 for c in cards if c["status"] == SUBMITTED),
                "approved": sum(1 for c in cards if c["status"] in FROZEN_STATUSES),
            },
        },
    )


def _coverage(school, year):
    """حارسُ المدرسة: هل يساوي المُسنَدُ ما تطلبه الخطّةُ تماماً؟

    الحملُ الفرديُّ يقول «فلانٌ على ثمانيةَ عشرَ»، ولا يقول إنّ شعبةً بلا معلّم
    رياضيات. فهذا الحارسُ يقيس المدرسةَ كلَّها خليّةً خليّة (شعبة × مادّة):
    كم تطلب الخطّةُ، وكم أُسنِد، وأين الفرق. ومن يعتمد يحتاج الرقمين معاً.
    """
    rows = curriculum_service.plan_rows(school, year)
    if not rows:
        return None
    cells = curriculum_service.coverage(school, year, rows)
    planned = sum(c["planned"] for c in cells)
    assigned = sum(c["assigned"] for c in cells)
    problems = [c for c in cells if c["status"] in curriculum_service.PROBLEM_STATUSES]
    return {
        "planned": planned,
        "assigned": assigned,
        "delta": assigned - planned,
        # القسمةُ تُجبَر إلى أسفل: 866 من 870 تُقرَّب إلى مئةٍ فتقول الشاشةُ
        # «غيرُ مكتملٍ — 100%» في سطرٍ واحد. والمئةُ لا تُقال إلّا عند التطابق.
        "percent": (100 if assigned == planned else min(99, assigned * 100 // planned))
        if planned
        else 0,
        "complete": assigned == planned and not problems,
        "problems": problems[:60],
        "problem_count": len(problems),
        "summary": curriculum_service.coverage_summary(cells),
    }


# ══════════════════════════════════════════════════════════════════════
#  الكتابةُ في مكانها
# ══════════════════════════════════════════════════════════════════════


def _locked_card(request, school, year, teacher, caps):
    """بطاقةُ خطأٍ حين تكون مقفلةً — بدل تجاهلٍ صامتٍ للنقرة."""
    plan = _latest_plan(school, teacher, year)
    if _may_write(plan, caps):
        return None
    reason = (
        "هذه الخطّةُ معتمَدةٌ — افتح إصداراً جديداً للتعديل."
        if plan and plan.status in FROZEN_STATUSES
        else "الخطّةُ مرفوعةٌ للمراجعة — لا تُعدَّل حتّى تُردَّ إليك."
    )
    return _render_card(request, school, year, teacher, caps, error=reason)


@login_required
@require_GET
def subject_options(request):
    """موادُّ خطّة الشعبة المختارة — بحصصها ومن يحملها الآن إن كان أحد."""
    school, _caps_, _scope, year = _guard(request)
    class_id = request.GET.get("class_group")
    if not class_id:
        return render(request, "academic_management/partials/assignment_subject_options.html", {})
    group = get_object_or_404(ClassGroup, id=class_id, school=school)
    holders = {
        a.subject_id: a.teacher
        for a in SubjectClassAssignment.objects.live(school, year=year)
        .filter(class_group=group)
        .select_related("teacher")
    }
    options = [
        {"row": row, "holder": holders.get(row.subject_id)}
        for row in curriculum_service.demand_for(group)
    ]
    return render(
        request,
        "academic_management/partials/assignment_subject_options.html",
        {"options": options},
    )


@login_required
@require_POST
def add_row(request, teacher_id):
    """إسنادٌ جديد: الشعبةُ والمادّة — والحصصُ من الخطّة الوزاريّة."""
    teacher = get_object_or_404(CustomUser, id=teacher_id)
    school, caps, _scope, year = _guard(request, teacher)
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked

    group = get_object_or_404(ClassGroup, id=request.POST.get("class_group"), school=school)
    subject = get_object_or_404(Subject, id=request.POST.get("subject"), school=school)
    planned = next(
        (r for r in curriculum_service.demand_for(group) if r.subject_id == subject.id), None
    )
    if planned is None:
        return _render_card(
            request,
            school,
            year,
            teacher,
            caps,
            error="لا خطّةَ دراسيّةً لهذه المادّة في هذه الشعبة.",
        )

    try:
        _row, findings = assignment_service.apply_assignment(
            school=school,
            academic_year=year,
            class_group=group,
            subject=subject,
            teacher=teacher,
            weekly_periods=planned.weekly_periods,
            by=request.user,
            confirm_transfer=bool(request.POST.get("confirm_transfer")),
        )
    except assignment_service.AssignmentError as exc:
        codes = {f.code for f in exc.findings if f.blocks}
        if codes == {assignment_service.SUBJECT_HELD_BY_OTHER}:
            # مانعٌ واحدٌ وهو النقل: تُعرض الحقيقةُ ويُطلب التأكيدُ بدل الرفض.
            holder = (
                SubjectClassAssignment.objects.live(school, year=year)
                .filter(class_group=group, subject=subject)
                .select_related("teacher")
                .first()
            )
            return _render_card(
                request,
                school,
                year,
                teacher,
                caps,
                transfer={
                    "class_group": group,
                    "subject": subject,
                    "holder": holder.teacher if holder else None,
                    # خطّةُ صاحب المادّة إن كانت معتمَدةً: النقلُ يُخرجها عمّا
                    # وُقّع عليه، فيُقال ذلك قبل الضغط لا بعده.
                    "holder_approved": bool(
                        holder
                        and (_latest_plan(school, holder.teacher, year) or None)
                        and _latest_plan(school, holder.teacher, year).status in FROZEN_STATUSES
                    ),
                    "prepares": bool(request.POST.get("prepares")),
                    "year": year,
                },
            )
        return _render_card(request, school, year, teacher, caps, error=_message(exc))
    except ValidationError as exc:
        return _render_card(request, school, year, teacher, caps, error=_message(exc))

    if request.POST.get("prepares"):
        try:
            assignment_service.apply_preparation(
                school=school,
                academic_year=year,
                grade=group.grade,
                track=group.track,
                subject=subject,
                teacher=teacher,
                by=request.user,
            )
        except (assignment_service.AssignmentError, ValidationError) as exc:
            return _render_card(
                request, school, year, teacher, caps, error=_message(exc), notes=findings
            )
    return _render_card(request, school, year, teacher, caps, notes=findings)


@login_required
@require_POST
def update_periods(request, assignment_id):
    """تعديلُ الحصص في مكانها — وما خالف الخطّةَ يُكتب سببُه."""
    obj = get_object_or_404(SubjectClassAssignment, id=assignment_id, is_active=True)
    teacher = obj.teacher
    school, caps, _scope, _year = _guard(request, teacher)
    year = obj.academic_year
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked

    try:
        periods = int(request.POST.get("weekly_periods") or 0)
    except ValueError:
        return HttpResponseBadRequest("عددُ الحصص رقم")
    try:
        _row, findings = assignment_service.apply_assignment(
            school=school,
            academic_year=year,
            class_group=obj.class_group,
            subject=obj.subject,
            teacher=teacher,
            weekly_periods=periods,
            by=request.user,
            override_reason=(request.POST.get("reason") or "").strip(),
            #: الوسمُ يُحمَل معه لا يُترك لافتراضه.
            #:
            #: `apply_assignment` تكتب `parallel_group = tag` دائماً، وافتراضُها
            #: فراغ. فكلُّ تعديلٍ لعدد الحصص كان **يمحو التوازيَ صامتاً**:
            #: يُعدَّل نصابُ الفنّيّة في 12/1 فتفقد شراكتَها مع التكنولوجيا،
            #: ويصير المولّدُ يطلب لهما خانتين بعد أن كانتا في خانة.
            parallel_group=obj.parallel_group,
            requires_lab=obj.requires_lab,
            expected_updated_at=obj.updated_at,
        )
    except (
        assignment_service.AssignmentError,
        assignment_service.StaleWriteError,
        ValidationError,
    ) as exc:
        return _render_card(request, school, year, teacher, caps, error=_message(exc))
    return _render_card(request, school, year, teacher, caps, notes=findings)


@login_required
@require_POST
def cancel_transfer(request, teacher_id):
    """صرفُ النظر عن نقلٍ لم يُؤكَّد — تُعاد البطاقةُ كما كانت."""
    teacher = get_object_or_404(CustomUser, id=teacher_id)
    school, caps, _scope, year = _guard(request, teacher)
    return _render_card(request, school, year, teacher, caps)


@login_required
@require_POST
def remove_row(request, assignment_id):
    obj = get_object_or_404(SubjectClassAssignment, id=assignment_id, is_active=True)
    teacher = obj.teacher
    school, caps, _scope, _year = _guard(request, teacher)
    year = obj.academic_year
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked
    assignment_service.remove_assignment(
        assignment=obj, by=request.user, reason="حُذف من شاشة الإسناد"
    )
    return _render_card(request, school, year, teacher, caps)


@login_required
@require_POST
def set_parallel(request, assignment_id):
    """ربطُ مادّتين في الشعبة توازياً — أو فكُّ الربط.

    التوازي صفةُ **الإسناد** لا الجدول: مادّتان في الشعبة الواحدة تُدرَّسان في
    التوقيت نفسه لقسمَي الطلاب — الفنّيّةُ والتكنولوجيا في 11/1، والفنّيّةُ
    والكيمياء في 11/4. فالمولّدُ يجمعهما في مهمّةٍ واحدةٍ بساكنَين، وبلا الوسم
    يطلب لهما خانتين ويقع في «شعبةٌ بمادّتين».

    ## ولماذا شريكةٌ تُختار لا مربّعٌ يُشعَل

    المربّعُ يوسم مادّةً واحدة، فيُنشئ اليتيمَ بأوّل نقرة: مجموعةٌ بعضوٍ واحدٍ
    ليست توازياً، والمولّدُ لا يخصمها فيظهر «مطلوب 37 والسعة 35» وليس في
    الشعبة فائضٌ أصلاً. فالربطُ هنا ثنائيٌّ في فعلٍ واحد: تُختار الشريكةُ
    فيُوسَم الطرفان معاً، ويُفكّ الوسمُ عنهما معاً — فلا يُولَد يتيمٌ من هذا
    الباب.

    والوسمُ يُشتقّ من الشعبة ولا يُكتب نصّاً، فلا يُطلب من أحدٍ أن يتذكّر
    حروفاً يطابقها.
    """
    obj = get_object_or_404(SubjectClassAssignment, id=assignment_id, is_active=True)
    teacher = obj.teacher
    school, caps, _scope, _year = _guard(request, teacher)
    year = obj.academic_year
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked

    raw = (request.POST.get("partner") or "").strip()
    partner = None
    if raw:
        partner = (
            SubjectClassAssignment.objects.live(school, year=year)
            .filter(pk=raw, class_group_id=obj.class_group_id)
            .exclude(pk=obj.pk)
            .first()
        )
        if partner is None:
            return _render_card(
                request, school, year, teacher, caps, error="الشريكةُ ليست من موادّ هذه الشعبة."
            )

    old_tag = (obj.parallel_group or "").strip()
    with transaction.atomic():
        if partner is None:
            #: فكُّ الربط يرفع الوسمَ عن الطرفين — وإلّا بقي الآخرُ يتيماً.
            if old_tag:
                SubjectClassAssignment.objects.filter(
                    class_group_id=obj.class_group_id, parallel_group=old_tag, is_active=True
                ).update(parallel_group="", updated_by=request.user)
            else:
                obj.parallel_group = ""
                obj.updated_by = request.user
                obj.save(update_fields=["parallel_group", "updated_by", "updated_at"])
        else:
            tag = f"par-{obj.class_group.short_code}"[:40]
            for row in (obj, partner):
                row.parallel_group = tag
                row.updated_by = request.user
                row.save(update_fields=["parallel_group", "updated_by", "updated_at"])
    return _render_card(request, school, year, teacher, caps)


@login_required
@require_POST
def toggle_double(request, assignment_id):
    """مربّعُ «مزدوجة» — حصّتان متلاصقتان لهذه المادّة في هذه الشعبة.

    والقرارُ هنا لا في جدول الموادّ: الازدواجُ ليس صفةَ المادّة بإطلاق بل صفةَ
    تدريسها في صفٍّ بعينه — التكنولوجيا متباعدةٌ من السابع إلى العاشر ومزدوجةٌ
    في الحادي عشر/1 حيث هي نصفُ زوجٍ متوازٍ مع الفنّيّة. و`double_period` على
    الإسناد يعلو `Subject.requires_double_period`، فهذا المربّعُ هو الكلمةُ
    الأخيرة.

    ويُكتب صريحاً — `True` أو `False` — لا يُترك `None` («اتبع المادّة»):
    المستخدمُ يرى مربّعاً مشعلاً أو مطفأً، فيجب أن يكون ما يراه هو ما يُقرأ.
    """
    obj = get_object_or_404(SubjectClassAssignment, id=assignment_id, is_active=True)
    teacher = obj.teacher
    school, caps, _scope, _year = _guard(request, teacher)
    year = obj.academic_year
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked

    obj.double_period = bool(request.POST.get("double"))
    obj.updated_by = request.user
    obj.save(update_fields=["double_period", "updated_by", "updated_at"])
    return _render_card(request, school, year, teacher, caps)


@login_required
@require_POST
def toggle_preparation(request, teacher_id):
    """مربّعُ «يحضّر» — تعيينُ مسؤوليّة تحضير المقرّر أو إسقاطُها."""
    teacher = get_object_or_404(CustomUser, id=teacher_id)
    school, caps, _scope, year = _guard(request, teacher)
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked

    grade = request.POST.get("grade") or ""
    track = request.POST.get("track") or ""
    subject = get_object_or_404(Subject, id=request.POST.get("subject"), school=school)
    try:
        if request.POST.get("prepares"):
            assignment_service.apply_preparation(
                school=school,
                academic_year=year,
                grade=grade,
                track=track,
                subject=subject,
                teacher=teacher,
                by=request.user,
            )
        else:
            current = (
                CoursePreparation.objects.live(school, year=year)
                .filter(grade=grade, track=track, subject=subject, teacher=teacher)
                .first()
            )
            if current:
                assignment_service.remove_preparation(
                    preparation=current, by=request.user, reason="أُسقط من شاشة الإسناد"
                )
    except (assignment_service.AssignmentError, ValidationError) as exc:
        return _render_card(request, school, year, teacher, caps, error=_message(exc))
    return _render_card(request, school, year, teacher, caps)


@login_required
@require_POST
def set_load(request, teacher_id):
    """النصابُ رقمٌ واحد — يُفتح له مسودّةٌ إن لم تكن، ويُحدَّث إن كانت."""
    teacher = get_object_or_404(CustomUser, id=teacher_id)
    school, caps, _scope, year = _guard(request, teacher)
    locked = _locked_card(request, school, year, teacher, caps)
    if locked is not None:
        return locked

    try:
        periods = int(request.POST.get("required_weekly_periods") or 0)
    except ValueError:
        return HttpResponseBadRequest("النصابُ رقم")
    if not 0 <= periods <= 40:
        return _render_card(
            request, school, year, teacher, caps, error="النصابُ بين صفرٍ وأربعين حصّة."
        )

    plan = _latest_plan(school, teacher, year)
    try:
        if plan is None:
            flow.open_draft(
                school,
                teacher,
                year,
                by=request.user,
                required_weekly_periods=periods,
                required_source_kind="manual",
                required_source_reference="شاشة الإسناد",
            )
        else:
            plan.required_weekly_periods = periods
            plan.required_source_kind = "manual"
            plan.required_source_reference = "شاشة الإسناد"
            plan.updated_by = request.user
            plan.full_clean(exclude=["created_by", "updated_by"])
            plan.save()
    except (ValidationError, PermissionDenied) as exc:
        return _render_card(request, school, year, teacher, caps, error=_message(exc))
    return _render_card(request, school, year, teacher, caps)


@login_required
@require_POST
def set_department(request, teacher_id):
    """نقلُ معلّمٍ إلى قسمٍ — للنائب والمدير وحدَهما.

    الانتماءُ يُكتب على عضويّة التدريس لا على المستخدم، ولا يُقبل لدورٍ غير
    تدريسيّ (يحرسه `Membership.clean`). وبهذا يجد المعيَّنُ حديثاً والمنقولُ
    بابَه في المنصّة، بلا لوحةِ إدارة.
    """
    teacher = get_object_or_404(CustomUser, id=teacher_id)
    school, caps, _scope, year = _guard(request, teacher)
    if not (caps["review"] or caps["approve"]):
        raise PermissionDenied("نقلُ المعلّم بين الأقسام للنائب الأكاديميّ والمدير.")

    raw = request.POST.get("department") or ""
    department = (
        get_object_or_404(Department, id=raw, school=school, is_active=True) if raw else None
    )
    memberships = Membership.objects.filter(
        user=teacher, school=school, is_active=True, role__name__in=DEPARTMENT_ROLES
    ).select_related("role")
    if not memberships:
        return _render_card(
            request,
            school,
            year,
            teacher,
            caps,
            error="لا عضويّةَ تدريسٍ لهذا الشخص — والقسمُ الأكاديميُّ لأهل التدريس.",
        )
    try:
        for membership in memberships:
            membership.department_obj = department
            membership.full_clean(exclude=["user", "school", "role"])
            membership.save(update_fields=["department_obj"])
    except ValidationError as exc:
        return _render_card(request, school, year, teacher, caps, error=_message(exc))
    return _render_card(request, school, year, teacher, caps, department=department)


# ══════════════════════════════════════════════════════════════════════
#  الدورة: رفعٌ ← مراجعةٌ ← اعتماد
# ══════════════════════════════════════════════════════════════════════


@login_required
@require_POST
def move(request, teacher_id, action):
    """نقلةٌ واحدةٌ في دورة الخطّة — والبوّابةُ والختمُ في `workload_workflow`."""
    teacher = get_object_or_404(CustomUser, id=teacher_id)
    school, caps, _scope, year = _guard(request, teacher)
    plan = _latest_plan(school, teacher, year)
    if plan is None:
        return _render_card(
            request,
            school,
            year,
            teacher,
            caps,
            error="لا خطّةَ لهذا المعلّم — اكتب نصابَه أوّلاً.",
        )

    comment = (request.POST.get("comment") or "").strip()
    handlers = {
        "submit": lambda: flow.submit_for_review(plan, by=request.user),
        "review": lambda: flow.record_review(plan, by=request.user, comment=comment),
        "return": lambda: flow.return_to_draft(plan, by=request.user, comment=comment),
        "approve": lambda: flow.approve(plan, by=request.user),
        "revise": lambda: flow.new_version_from(plan, by=request.user),
    }
    if action not in handlers:
        return HttpResponseBadRequest("نقلةٌ غيرُ معروفة")
    try:
        handlers[action]()
    except (flow.WorkflowError, ValidationError, PermissionDenied) as exc:
        return _render_card(request, school, year, teacher, caps, error=_message(exc))
    return _render_card(request, school, year, teacher, caps)


def _message(exc) -> str:
    if isinstance(exc, assignment_service.AssignmentError):
        return "؛ ".join(f.message for f in exc.findings if f.blocks) or str(exc)
    if isinstance(exc, assignment_service.StaleWriteError):
        return "عُدّل هذا السطرُ من جهازٍ آخر — أعِد تحميل الصفحة."
    if isinstance(exc, ValidationError):
        return "؛ ".join(
            m for msgs in getattr(exc, "message_dict", {"": exc.messages}).values() for m in msgs
        )
    return str(exc)
