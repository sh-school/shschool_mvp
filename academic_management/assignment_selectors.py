"""academic_management/assignment_selectors.py — قراءةُ شاشة «الإسناد»، بلا `request`.

طبقةُ قراءةٍ (selectors) لا عرض: حارسُ الطبقات (`tests/layering_ratchet.py`)
يسقف كلَّ دالّةٍ في ملفّ عروضٍ بستّين سطراً وخمسة استدعاءات ORM — وكانت
`academic_management/assignment_views.py::add_row` أثقلَ عرضٍ في المشروع
(109 استدعاءَ ORM، محسوبةً من دوالّ بناء البطاقة التي يستدعيها). فُصلت هذه
الدوالّ إلى هنا — كانت أصلاً بلا اقترانٍ بـ`request` (تأخذ `school, year,
teacher, ...` صراحةً)، فالنقل نسخٌ لا إعادةَ كتابة.

جزءٌ من الانخفاض الآخر جاء من إعادة تسمية `assignment_service.py`/
`curriculum_service.py` (مفردَين) إلى `assignment_services.py`/
`curriculum_services.py` (جمعاً) في الإيداع نفسه: حارسُ الطبقات يستثني من
العدّ ما اسمُه `services`/`selectors` أو ينتهي بـ`_services`/`_selectors`
وحدها — والاسمُ المفردُ القديم لم يكن يطابق ذلك، فتسرّبت استدعاءاتُ ORM
داخل طبقة الكتابة الموجودة أصلاً إلى حساب كلّ عرضٍ يناديها.
"""

from collections import defaultdict

from academic_management import curriculum_services as curriculum_service
from academic_management import load
from academic_management import workload_workflow as flow
from academic_management.models import (
    DRAFT,
    FROZEN_STATUSES,
    REVIEWED,
    SUBMITTED,
    CoursePreparation,
    TeacherWorkloadPlan,
    WorkloadGovernance,
)
from core import permissions as perms
from core.dept_colors import OTHER, dept_key
from core.models import ClassGroup, Department, Membership
from core.models.academic import grade_order
from operations import departments as dept_map
from operations.models import SubjectClassAssignment

#: من تُطبع له بطاقة — الأدوارُ التي تُدرّس.
TEACHING_ROLES = ("teacher", "ese_teacher", "coordinator", "e_projects_coordinator")
LEVEL_LABELS = {"prep": "إعدادي", "sec": "ثانوي"}

#: مفتاحُ من لا قسمَ مسجّلاً له — يظهر ليُصلَح لا ليُخفى.
NO_DEPARTMENT = "none"


# ══════════════════════════════════════════════════════════════════════
#  القدرة والنطاق
# ══════════════════════════════════════════════════════════════════════


def caps(user, school):
    """قدراتُ هذا المستخدم على الأنصبة — إدخالٌ ومراجعةٌ واعتماد ومفتاحُ الوقف."""
    return {
        "edit": flow.has_capability(user, school, flow.EDIT),
        "review": flow.has_capability(user, school, flow.REVIEW),
        "approve": flow.has_capability(user, school, flow.APPROVE),
        # الوقفُ قرارُ المدرسة، والمفتاحُ لثلاثةِ أدوارٍ ثابتة (لا تهيئة).
        "paused": WorkloadGovernance.for_school(school).coordinator_entry_paused,
        "toggle": bool(getattr(user, "is_superuser", False))
        or user.get_role() in perms.ASSIGNMENT_ENTRY_TOGGLE,
    }


def entry_paused_for(teacher_caps) -> bool:
    """أموقوفٌ الإسنادُ عن **هذا** المستخدم؟ — عن المنسّق وحدَه: من يراجع أو يعتمد يكتب دائماً."""
    return bool(
        teacher_caps.get("paused") and not (teacher_caps["review"] or teacher_caps["approve"])
    )


def registry_filled(school) -> bool:
    return Department.objects.filter(school=school, is_active=True).exists()


def department_key(person, school, year):
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
    return department_of(department, list(rows), registry_filled(school))[0]


# ══════════════════════════════════════════════════════════════════════
#  بناءُ البطاقة
# ══════════════════════════════════════════════════════════════════════


def teachers(school):
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


def coordinator_ids(school) -> set:
    """معرّفاتُ منسّقي التخصّص — يتقدّمون قائمةَ قسمهم ويُوسَمون بوسمٍ موحَّد."""
    return set(
        Membership.objects.filter(
            school=school, is_active=True, role__name="coordinator"
        ).values_list("user_id", flat=True)
    )


def department_of(department, rows, filled=False):
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
    if filled:
        return NO_DEPARTMENT, "بلا قسمٍ مسجَّل", (2, 0, "")
    code = dept_map.resolve_from_lessons(
        (row.subject.name_ar, row.class_group.grade, row.weekly_periods) for row in rows
    )
    info = dept_map.department_info(code)
    return f"der:{info['code']}", info["name"], (1, info["order"], info["name"])


def department_color(department, key) -> str:
    """مفتاحُ لون القسم كما في الجدول العامّ — سجلُّه إن وُجد، وإلّا كودُ الاشتقاق، وإلّا محايد."""
    if department is not None:
        return dept_key(department.code)
    if str(key).startswith("der:"):
        return dept_key(str(key)[4:])
    return OTHER


def rows_by_teacher(school, year):
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
    decorate(rows, class_peers(school, year, rows))
    for row in rows:
        out[row.teacher_id].append(row)
    return out


def class_peers(school, year, rows):
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


def decorate(rows, peers):
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


def prepared_by_teacher(school, year):
    out = defaultdict(set)
    for p in CoursePreparation.objects.live(school, year=year):
        out[p.teacher_id].add((p.grade, p.track, p.subject_id))
    return out


def classes(school, year):
    return list(
        ClassGroup.objects.filter(
            school=school, academic_year=year, is_active=True, has_own_timetable=False
        ).in_school_order()
    )


def latest_plan(school, teacher, year):
    return (
        TeacherWorkloadPlan.objects.filter(school=school, teacher=teacher, academic_year=year)
        .order_by("-plan_version")
        .first()
    )


def plans_by_teacher(school, year):
    """أحدثُ خطّةٍ لكلّ معلّم — استعلامٌ واحدٌ لا واحدٌ لكلّ بطاقة."""
    out = {}
    plans = TeacherWorkloadPlan.objects.filter(school=school, academic_year=year).order_by(
        "teacher_id", "-plan_version"
    )
    for plan in plans:
        out.setdefault(plan.teacher_id, plan)
    return out


def may_write(plan, teacher_caps):
    """هل تُحرَّر بطاقةُ هذا المعلّم الآن؟

    المسودّةُ يحرّرها كلُّ مُدخِل. وما رُفع للمراجعة لا يُعدَّل من تحت المراجع
    إلّا بيده هو — وللنائب والمدير التعديلُ في كلّ حال. والمعتمَدُ لا يُكتب
    فوقه: يُفتح بإصدارٍ جديدٍ بنقرة، فيبقى الموقَّعُ كما وُقِّع.
    """
    if plan is not None and plan.status in FROZEN_STATUSES:
        return False
    if entry_paused_for(teacher_caps):
        return False
    if plan is not None and plan.status in (SUBMITTED, REVIEWED):
        return teacher_caps["review"] or teacher_caps["approve"]
    return teacher_caps["edit"]


def card_rows(school, year, teacher, rows, prepared):
    """صفوفُ البطاقة مزيَّنةً — تُجلب إن لم تُمرَّر، وتُزيَّن إن لم تكن مزيَّنة.

    الصفحةُ كاملةً تجلب الجميعَ مرّةً وتزيّنهم في `rows_by_teacher`، وبطاقةٌ
    تُعاد وحدَها بعد حفظٍ تمرّ من هنا.
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
        decorate(rows, class_peers(school, year, rows))
    for row in rows:
        row.level_label = LEVEL_LABELS.get(row.class_group.level_type, "")
        row.prepares = (row.class_group.grade, row.class_group.track, row.subject_id) in prepared
    return rows


def card(
    school,
    year,
    teacher,
    teacher_caps,
    *,
    rows=None,
    prepared=None,
    plans=None,
    loads=None,
    classes=None,
    registry=None,
    department=None,
    coordinator=None,
    error=None,
    notes=(),
    transfer=None,
):
    """سياقُ بطاقةٍ واحدة — تُبنى للصفحة وتُعاد وحدَها بعد كلّ حفظ."""
    from academic_management import assignment_services as assignment_service

    rows = card_rows(school, year, teacher, rows, prepared)

    plan = plans.get(teacher.id) if plans is not None else latest_plan(school, teacher, year)
    status = plan.status if plan else ""
    teacher_load = (loads or {}).get(teacher.id) or load.load_for(school, year, teacher.id)

    # التفريغُ يومَ كاملٍ يضغط النصابَ ولا يُخفّفه — ومن يوقّع على ثمانيةَ عشرَ
    # حصّةً يحقّ له أن يرى أنّها في أربعة أيّام. تُحسب للمرفوع والمُراجَع وحدَهما
    # كي لا تصير الصفحةُ ثلاثةَ استعلاماتٍ في كلّ بطاقةٍ من ثلاثٍ وسبعين.
    room = flow.available_capacity(plan) if plan and status in (SUBMITTED, REVIEWED) else None

    # خطّةٌ اعتُمدت ثمّ تبدّل إسنادُها تحتَها: التوقيعُ على شيءٍ والواقعُ شيءٌ
    # آخر. تُحسب البصمةُ من الصفوف التي في اليد — بلا استعلامٍ لكلّ بطاقة.
    diverged = flow.has_diverged(plan, rows) if plan and status in FROZEN_STATUSES else None

    if coordinator is None:  # بطاقةٌ تُعاد وحدَها بعد حفظ — الصفحةُ الكاملةُ تمرّر الجوابَ جاهزاً
        coordinator = teacher.id in coordinator_ids(school)

    return {
        "teacher": teacher,
        "coordinator": coordinator,
        "rows": rows,
        "load": teacher_load,
        "plan": plan,
        "status": status,
        "status_label": plan.get_status_display() if plan else "بلا خطّة",
        "room": room,
        "diverged": diverged,
        # نقلُ معلّمٍ بين الأقسام قرارُ إدارةٍ — للنائب والمدير وحدَهما.
        "registry": registry if registry is not None else [],
        "department": department if department is not None else department_object(school, teacher),
        "writable": may_write(plan, teacher_caps),
        "classes": classes if classes is not None else globals()["classes_for"](school, year),
        "year": year,
        "error": error,
        "notes": [n for n in notes if n.level != assignment_service.BLOCK],
        # نقلُ مادّةٍ من زميلٍ — يُعرض ليُؤكَّد لا ليقع صامتاً.
        "transfer": transfer,
        # ── أزرارُ الدورة: مسودّةٌ ← رفعٌ ← مراجعةٌ ← اعتماد ──
        "can_submit": bool(plan)
        and status == DRAFT
        and teacher_caps["edit"]
        and not entry_paused_for(teacher_caps),
        "paused": entry_paused_for(teacher_caps),
        "can_review": bool(plan) and status == SUBMITTED and teacher_caps["review"],
        "can_return": bool(plan) and status in (SUBMITTED, REVIEWED) and teacher_caps["review"],
        "can_approve": bool(plan) and status == REVIEWED and teacher_caps["approve"],
        "can_revise": bool(plan) and status in FROZEN_STATUSES and teacher_caps["edit"],
    }


def department_object(school, teacher):
    membership = (
        Membership.objects.filter(user=teacher, school=school, is_active=True)
        .select_related("department_obj")
        .order_by("department_obj__sort_order")
        .first()
    )
    return membership.department_obj if membership else None


# ══════════════════════════════════════════════════════════════════════
#  الصفحة
# ══════════════════════════════════════════════════════════════════════


def assignments_subtitle(year, totals) -> str:
    """سطرُ الترويسة: العامُ وأعدادُ الشاشة، وما لم يقع لا يُذكر."""
    parts = [str(year), f"{totals['teachers']} معلّماً", f"{totals['rows']} إسناداً"]
    if totals["pending"]:
        parts.append(f"{totals['pending']} بانتظار المراجعة")
    if totals["approved"]:
        parts.append(f"{totals['approved']} معتمَداً")
    return " · ".join(parts) + " — يُحفظ كلُّ تغييرٍ في لحظته"


def coverage(school, year):
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


def classes_for(school, year):
    """اسمٌ بديلٌ لـ`classes` — يتجنّب تظليل معامل `classes=` في `card`."""
    return classes(school, year)


def assignments_page_context(school, teacher_caps, scope, year, selected):
    """سياقُ صفحة الإسناد كلِّها — بطاقاتٌ مُجمَّعةً حسب القسم مع إجماليّاتها.

    استُخرجت من `assignments` (كانت 69 سطراً، فوق سقف الستّين) — العرضُ بعد
    هذا الاستخلاص استدعاءٌ واحدٌ وتصييرٌ واحد.
    """
    classes_list = classes(school, year)
    loads = load.loads_for(school, year)
    rows_by = rows_by_teacher(school, year)
    prepared_by = prepared_by_teacher(school, year)
    plans = plans_by_teacher(school, year)
    filled = registry_filled(school)
    coordinators = coordinator_ids(school)
    registry = (
        list(Department.objects.filter(school=school, is_active=True))
        if teacher_caps["review"]
        else []
    )

    # قائمةُ الترشيح تُبنى ممّا يظهر فعلاً — فلا خيارَ بلا معلّمين، ولا معلّمَ
    # بلا خيارٍ يبلغه. وعددُ كلّ قسمٍ يُحسب من معلّميه جميعاً لا من المعروضين،
    # كي يبقى الرقمُ ظاهراً في القائمة قبل الاختيار وبعده.
    groups = {}
    for teacher, department in teachers(school):
        rows = rows_by.get(teacher.id, [])
        key, name, order = department_of(department, rows, filled)
        if scope is not None and key != scope:
            continue
        group = groups.setdefault(
            key,
            {
                "key": key,
                "name": name,
                "color": department_color(department, key),
                "order": order,
                "count": 0,
                "cards": [],
            },
        )
        group["count"] += 1
        if selected and key != selected:
            continue
        group["cards"].append(
            card(
                school,
                year,
                teacher,
                teacher_caps,
                rows=rows,
                prepared=prepared_by.get(teacher.id, set()),
                plans=plans,
                loads=loads,
                classes=classes_list,
                registry=registry,
                department=department,
                coordinator=teacher.id in coordinators,
            )
        )

    # منسّقُ التخصّص أوّلَ قائمة قسمه؛ والترتيبُ ثابتٌ فيبقى الباقون بترتيبهم (بالاسم).
    for g in groups.values():
        g["cards"].sort(key=lambda c: not c["coordinator"])
    ordered = sorted(groups.values(), key=lambda g: g["order"])
    shown = [g for g in ordered if g["cards"]]
    cards = [c for g in shown for c in g["cards"]]
    totals = {
        "teachers": len(cards),
        "rows": sum(len(c["rows"]) for c in cards),
        "pending": sum(1 for c in cards if c["status"] == SUBMITTED),
        "approved": sum(1 for c in cards if c["status"] in FROZEN_STATUSES),
    }
    return {
        "groups": shown,
        "departments": ordered,
        "registry_empty": not filled,
        "coverage": coverage(school, year),
        "totals": totals,
    }
