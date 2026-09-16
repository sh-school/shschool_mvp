"""سجلُّ القدرات — «من يفعل ماذا» بالفعل لا بالدور.

كان الحارسُ يسأل «أيُّ دورٍ أنت؟»، والجوابُ مكتوبٌ في مئتي موضعٍ بصيغٍ مختلفة: مجموعةٌ
مركزيّةٌ هنا، وقائمةٌ حرفيّةٌ هناك، وديكوريتورٌ مختصرٌ في ثالث. فالقائمةُ الجانبيّةُ تَعِد بما
يردّه الحارس، والبوّابةُ لا تعرف ما يعرفه، ومراجعةُ «من يرى درجاتِ الطلبة؟» تتطلّب قراءةَ
الشيفرة كلِّها — وهكذا مرّت ثغراتُ مراجعة 2026-09-13.

والقدرةُ تسمّي **الفعل**: ``assessments.enter_grades`` لا ``{"principal", "coordinator", ...}``.
فقدرتان تحملان اليومَ الأعضاءَ أنفسَهم تبقيان اثنتين، ويفترقان متى قُرّر ذلك دون أن تمسّ
إحداهما الأخرى.

**هذه الخطوةُ الأولى:** السجلُّ وحدَه. أعضاءُ كلّ قدرةٍ هم أعضاءُ الحرّاس القائمة حرفاً — مأخوذون
من المجموعات نفسِها حيث وُجدت — ولم يُحوَّل حارسٌ واحد. و``tests/test_capabilities_registry.py``
يُثبت أنّ كلَّ حارسٍ في المنصّة يطابق قدرةً في السجلّ، فلا يُعرض سجلٌّ ناقصٌ ولا مخترَع.

**والأساس** (``basis``) يقول من أين جاءت القدرة: نصٌّ وزاريٌّ بمرجعه، أو قرارٌ مؤرَّخ، أو
«افتراضُ المنصّة» — أي أنّها كذلك في الشيفرة ولم تُراجَع بعدُ مقابل نصّ. لا يُكتب مرجعٌ غيرُ موجود.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache

from core.permissions import expand_roles, role_required

#: الأساسُ حين لا نصَّ ولا قرار — القدرةُ كما في الشيفرة، تنتظر المراجعة.
PLATFORM_ASSUMPTION = "افتراضُ المنصّة — لم يُراجَع مقابل نصّ"


@dataclass(frozen=True)
class Capability:
    key: str
    label: str
    roles: frozenset
    scope: str = "المدرسة"
    basis: str = PLATFORM_ASSUMPTION
    #: منحٌ لا يقرؤه الدور: ``grant(user) -> bool``. لقدرةٍ يملكها المستخدمُ بتكليفٍ ساري
    #: لا بمسمّاه — كبديل الجناح من ملاحظي الطلبة وعمّال الخدمات.
    grant: Callable | None = None

    @property
    def expanded_roles(self) -> frozenset:
        """الأدوارُ بعد الوراثة — ما يفحصه الحارسُ فعلاً."""
        return frozenset(expand_roles(set(self.roles)))

    def granted(self, user) -> bool:
        return self.grant is not None and bool(self.grant(user))


def _cap(
    key: str,
    label: str,
    roles: Iterable[str],
    scope: str = "المدرسة",
    basis: str = PLATFORM_ASSUMPTION,
    grant: Callable | None = None,
) -> Capability:
    return Capability(key, label, frozenset(roles), scope, basis, grant)


def _holds_a_wing(user) -> bool:
    from core.models.academic import Wing

    return Wing.is_held_by(user)


@cache
def registry() -> dict[str, Capability]:
    """السجلُّ مبنيّاً — كسولٌ لأنّ بعضَ المجموعات في تطبيقاتٍ تستورد ``core``."""
    from academic_management.workload_workflow import _DEFAULT_ROLES as WORKLOAD
    from academic_management.workload_workflow import APPROVE, EDIT, REVIEW
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول
    from core.models.academic import WingCoverage
    from student_info.access import MODULE_ROLES as STUDENT_INFO_ROLES

    leadership = P.LEADERSHIP
    caps = [
        # ── لوحة التحكّم ────────────────────────────────────────────
        _cap("dashboard.open", "فتحُ لوحة التحكّم", P.ALL_STAFF_ROLES | {"student", "parent"}),
        # ── شؤون الطلبة ─────────────────────────────────────────────
        _cap("student_affairs.manage", "إدارةُ سجلّات الطلبة", P.STUDENT_AFFAIRS_MANAGE),
        _cap("student_affairs.view", "الاطّلاعُ على سجلّات الطلبة", P.STUDENT_AFFAIRS_VIEW),
        _cap("student_affairs.deactivate", "إيقافُ قيد طالب", P.STUDENT_DEACTIVATE),
        _cap(
            "student_affairs.activities",
            "إدارةُ الأنشطة الطلابيّة",
            P.ACTIVITIES_MANAGE,
            basis="ضوابط البرامج والأنشطة ص3: الدخولُ للنائب الأكاديميّ وأخصائيّ الأنشطة",
        ),
        _cap(
            "students.import_export",
            "استيرادُ الطلبة وتصديرُهم",
            {"principal", "vice_admin", "vice_academic", "admin"},
        ),
        _cap(
            "student_info.read",
            "مركزُ معلومات الطالب",
            STUDENT_INFO_ROLES,
            scope="المدرسة للقيادة والجهات؛ المعلّمُ لطلبة شُعبه",
            basis="قرارُ المستخدم: القراءةُ لكلّ من يُدرّس الطالب",
        ),
        _cap(
            "students.search",
            "البحثُ السريعُ عن الطلبة",
            P.ALL_STAFF_ROLES,
            scope="عشرُ نتائجَ بحدٍّ أقصى",
        ),
        # ── شؤون الموظّفين والتدقيق ─────────────────────────────────
        _cap("staff_affairs.manage", "إدارةُ شؤون الموظّفين", P.STAFF_AFFAIRS_MANAGE),
        _cap(
            "staff_affairs.own_permits",
            "طلبُ إذنٍ قصيرٍ للموظّف نفسه",
            P.ALL_STAFF_ROLES,
            scope=(
                "طلباتُ المستخدم نفسِه ورصيدُه، واستثناءاتُه (نموذج 03) لغير المدير — "
                "وإذنُ المدير تُثبت السكرتاريةُ اعتمادَ رئيسه"
            ),
            basis=(
                "07_forms_catalog.md:13 (نموذج 02) و:14 (نموذج 03) — يقدّمه الموظّف ويوقّعه؛ "
                "وسجلُّ الاستئذانات المدرسيّ (07-نماذج المدرسة/07) أوّلُ صفوفه المدير (B3:C3)"
            ),
        ),
        _cap(
            "staff_affairs.attendance_record",
            "رصدُ حضور الموظّفين اليوميّ",
            {"principal", "secretary"},
            basis=(
                "03_job_descriptions_rbac.md:101 السكرتير «متابعة الحضور والانصراف للموظفين»؛ "
                "rbac_permissions_matrix.md:55 كتابة ATTENDANCE؛ والمديرُ مالكُ الوحدات (:45)"
            ),
        ),
        _cap(
            "staff_affairs.attendance_report",
            "تقريرُ حضور الموظّفين الشهريّ",
            {"principal", "vice_admin", "vice_academic", "secretary"},
            scope="المديرُ والسكرتيرُ للمدرسة؛ والنائبُ لمن يتبعه في «reports_to» وحدَهم",
            basis=(
                "السكرتير «متابعة الحضور والانصراف للموظفين» (03_job_descriptions_rbac.md:101)؛ "
                "والمديرُ رأسُ الهيكل (rbac_permissions_matrix.md:45)؛ والنائبُ الإداريّ "
                "«متابعة وتقييم أداء من يندرج تحت مسؤولياته» (:48) والأكاديميّ «تقييم "
                "المنسقين والمعلمين» (:50)"
            ),
        ),
        _cap(
            "staff_affairs.permits_review",
            "مراحلُ اعتماد الأذونات القصيرة",
            {"principal", "vice_admin", "vice_academic", "secretary"},
            scope=(
                "الطلباتُ في مربّع المستخدم وحدَها: السكرتاريةُ للرصيد، والنائبُ المختصُّ "
                "لمربّعَي المسؤول المباشر والنائب المسؤول، والمديرُ للاعتماد ولنموذج 03 — "
                "ونائبُ الشؤون الإدارية فيهما حين تقوم الإنابة بغياب المدير المرصود (م-25)"
            ),
            basis=(
                "نموذج 02 (أصل PDF ص1) بترتيب مربّعاته: السكرتارية ← المسؤول المباشر "
                "والنائب المسؤول ← الإدارة ← مدير المدرسة (م-19 من "
                "docs/compliance/staff_attendance_spec.md)؛ والمسؤولُ المباشرُ نائبُ المدير "
                "المختصُّ بنصّ ترويسة بطاقات الوصف الوظيفيّ لا منسّقُ القسم (م-21)؛ ونموذج "
                "03 «استخدام مدير المدرسة»؛ والإنابةُ «عن المدير في مهامه في حال غيابه» "
                "(بطاقة نائب الشؤون الإدارية 1034، م-24 وم-25)"
            ),
        ),
        _cap(
            "audit.permissions_log",
            "سجلُّ تغييرات الصلاحيّات",
            {"principal", "vice_admin", "vice_academic"},
        ),
        _cap(
            "breach.manage",
            "تقاريرُ خرق البيانات",
            {"principal", "vice_admin", "vice_academic", "admin"},
        ),
        # ── الإشعارات والتحليلات ────────────────────────────────────
        _cap("notifications.broadcast", "إدارةُ الإشعارات والإرسالُ الجماعيّ", leadership),
        _cap("analytics.school", "تحليلاتُ المدرسة", leadership),
        # ── التقييم والدرجات ────────────────────────────────────────
        _cap(
            "assessments.enter_grades",
            "إنشاءُ التقييمات وإدخالُ الدرجات",
            {"principal", "vice_academic", "coordinator", "teacher", "ese_teacher"},
            scope="بحسب الشُّعب والموادّ داخلَ الشاشة",
        ),
        _cap(
            "assessments.view_results",
            "لوحةُ التقييم وسجلُّ درجات الشعبة",
            {
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                "academic_advisor",
            },
        ),
        _cap("assessments.oversee", "إعدادُ الموادّ ومتابعةُ المتعثّرين", leadership),
        _cap(
            "grades.import",
            "استيرادُ الدرجات من ملفّ",
            {
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                "admin",
                "secretary",
            },
        ),
        _cap(
            "reports.results",
            "كشوفُ النتائج وشهاداتُ الطلبة",
            {"principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher"},
        ),
        _cap("reports.school", "تقاريرُ الحضور والسلوك والشهادات للشعبة", leadership),
        _cap(
            "academic.reports_school",
            "التقاريرُ الأكاديميّةُ على مستوى المدرسة",
            P.ACADEMIC_REPORTS_VIEW,
            basis="مراجعةُ الصلاحيّات 2026-09-13 (#222)",
        ),
        # ── الأنصبة — تهيّئها المدرسةُ في WorkloadGovernance ─────────
        _cap(
            "workload.edit",
            "إدخالُ خطط الأنصبة",
            WORKLOAD[EDIT],
            scope="قسمُ المنسّق",
            basis="افتراضٌ موصى به — تُبدّله المدرسة (WorkloadGovernance)",
        ),
        _cap(
            "workload.review",
            "مراجعةُ خطط الأنصبة",
            WORKLOAD[REVIEW],
            basis="افتراضٌ موصى به — تُبدّله المدرسة (WorkloadGovernance)",
        ),
        _cap(
            "workload.approve",
            "اعتمادُ خطط الأنصبة",
            WORKLOAD[APPROVE],
            basis="افتراضٌ موصى به — تُبدّله المدرسة (WorkloadGovernance)",
        ),
        # ── السلوك ──────────────────────────────────────────────────
        _cap(
            "behavior.view",
            "ملفُّ السلوك ولوحتُه",
            P.BEHAVIOR_MANAGE | P.BEHAVIOR_RECORD | P.BEHAVIOR_VIEW_ALL,
        ),
        _cap("behavior.record", "تسجيلُ مخالفةٍ وتقريرُها", P.BEHAVIOR_MANAGE | P.BEHAVIOR_RECORD),
        _cap("behavior.manage", "إدارةُ المخالفات والإجراءات", P.BEHAVIOR_MANAGE),
        _cap("behavior.committee", "لجنةُ الانضباط", P.BEHAVIOR_COMMITTEE),
        _cap(
            "behavior.statistics",
            "إحصاءاتُ السلوك",
            P.BEHAVIOR_COMMITTEE | P.BEHAVIOR_VIEW_ALL | P.BEHAVIOR_STATS_TEACHING,
        ),
        _cap("behavior.summon_parent", "استدعاءُ وليّ الأمر", P.BEHAVIOR_MANAGE | {"psychologist"}),
        # ── العيادة والمكتبة والنقل ─────────────────────────────────
        _cap("clinic.access", "وحدةُ العيادة", {"nurse", "principal", "vice_admin"}),
        _cap("library.view", "المكتبةُ والكتب", P.LIBRARY_VIEW | P.LIBRARY_FULL),
        _cap("library.lend", "الإعارةُ والإرجاع", {"librarian", "principal", "vice_admin"}),
        _cap("library.borrowings_all", "سجلُّ استعارات المدرسة", P.LIBRARY_BORROWINGS_ALL),
        _cap("transport.access", "وحدةُ النقل", P.TRANSPORT_FULL | P.TRANSPORT_MANAGE),
        # ── الكنترول ────────────────────────────────────────────────
        _cap(
            "exam_control.access",
            "نظامُ الكنترول",
            P.EXAM_CONTROL_ACCESS,
            basis="افتراضُ المنصّة — والنصُّ الوزاريُّ يجعله لجنةً موقوتة (الدراسة، ملحق د)",
        ),
        # ── الحضور والجدول ──────────────────────────────────────────
        _cap(
            "attendance.mark",
            "رصدُ حضور الحصّة",
            {
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                "admin_supervisor",
            },
        ),
        _cap("operations.reports", "تقاريرُ الجدول والحضور", P.OPERATIONS_REPORTS),
        _cap(
            "schedule.day",
            "جدولُ اليوم",
            {
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                "academic_advisor",
                "admin_supervisor",
                "student",
                "parent",
            },
            scope="جدولُ المستخدم نفسِه لغير القيادة",
        ),
        _cap(
            "schedule.weekly",
            "الجدولُ الأسبوعيّ",
            {
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "e_projects_coordinator",
                "teacher",
                "ese_teacher",
                "academic_advisor",
                "admin_supervisor",
                "admin",
            },
            scope="جدولُ المستخدم لغير من يتصفّح",
        ),
        _cap("schedule.view", "عرضُ الجدول والتبديلات", P.SCHEDULE_VIEW),
        _cap("schedule.browse", "تصفّحُ جداول الآخرين", P.SCHEDULE_BROWSE),
        _cap(
            "schedule.print",
            "طباعةُ الجدول وتصديرُه",
            P.SCHEDULE_BROWSE | {"teacher", "ese_teacher", "academic_advisor"},
            scope="جدولُ المستخدم لغير من يتصفّح",
        ),
        _cap(
            "schedule.preferences",
            "تفضيلاتُ المعلّم في الجدول",
            {
                "teacher",
                "ese_teacher",
                "coordinator",
                "activities_coordinator",
                "e_projects_coordinator",
            },
            scope="تفضيلاتُه هو",
        ),
        _cap("schedule.settings", "إعداداتُ الجدول والتفريغات", P.SCHEDULE_SETTINGS),
        _cap("schedule.admin", "إعدادُ الجدول الإداريّ", P.SCHEDULE_ADMIN),
        _cap("schedule.manage", "توزيعاتُ الموادّ", P.SCHEDULE_MANAGE),
        _cap(
            "swap.request",
            "طلبُ تبديل حصّة",
            {"teacher", "ese_teacher", "principal", "vice_academic", "vice_admin"},
        ),
        _cap(
            "swap.respond",
            "الردُّ على طلب تبديل",
            {"teacher", "ese_teacher", "coordinator", "principal", "vice_academic", "vice_admin"},
        ),
        _cap(
            "swap.approve",
            "اعتمادُ التبديل",
            {"coordinator", "principal", "vice_academic", "vice_admin", "platform_developer"},
            scope="منسّقا المادّتين",
        ),
        _cap(
            "compensatory.request",
            "طلبُ حصّةٍ تعويضيّة",
            {"teacher", "ese_teacher", "principal", "vice_academic", "vice_admin"},
        ),
        _cap(
            "compensatory.approve",
            "اعتمادُ الحصّة التعويضيّة",
            {"coordinator", "principal", "vice_academic", "vice_admin"},
        ),
        # ── الجودة ──────────────────────────────────────────────────
        _cap("quality.access", "وحدةُ الجودة", P.QUALITY_ACCESS),
        _cap("quality.manage", "إدارةُ الخطّة التشغيليّة", P.QUALITY_MANAGE),
        _cap(
            "quality.evaluations",
            "تقييمُ أداء الموظّفين",
            {"principal", "vice_admin", "vice_academic"},
            basis="افتراضُ المنصّة — والنصُّ يجعل الرئيسَ المباشرَ كاتبَ التقييم (م16)",
        ),
        _cap("observation.create", "الزيارةُ الإشرافيّة", P.OBSERVATION_CREATE),
        _cap("observation.self", "التقييمُ الذاتيّ", P.OBSERVATION_SELF_CREATE),
        _cap("observation.peer", "تبادلُ الزيارات", P.OBSERVATION_PEER_CREATE),
        # ── وليّ الأمر ──────────────────────────────────────────────
        _cap("parents.portal", "بوّابةُ وليّ الأمر", P.PARENT_PORTAL, scope="أبناؤه وحدَهم"),
        _cap("parents.admin", "إدارةُ ربط أولياء الأمور", P.PARENT_PORTAL_ADMIN),
        # ── الأجنحة ─────────────────────────────────────────────────
        _cap(
            "wings.floors",
            "شاشةُ الأجنحة والطوابق",
            {"principal", "vice_admin", "vice_academic", "admin_supervisor", "platform_developer"},
        ),
        _cap("wings.assign_cover", "تكليفُ بديلٍ لجناح", WingCoverage.ASSIGNER_ROLES),
        _cap(
            "wings.record_day",
            "رصدُ يوم الشعبة في الجناح",
            P.WING_DAY_RECORD,
            scope="أجنحةُ المشرف (أصيلاً أو بديلاً)",
            basis=(
                "قرارُ 2026-09-12: المشرفُ الإداريّ يحصر الغياب — وقرارُ المدير: البديلُ "
                "مشرفٌ إداريٌّ أو ملاحظُ طلبةٍ أو عاملُ خدمات، فيرصد بتكليفه لا بدوره"
            ),
            grant=_holds_a_wing,
        ),
        _cap(
            "wings.excuse_after_deadline",
            "قبولُ عذرِ غيابٍ بعد مهلة اليومين",
            P.EXCUSE_AFTER_DEADLINE,
            basis=(
                "الدليل التنظيميّ 2026 م 3.4.1.5: إن لم يردّ وليُّ الأمر خلال يومين حُسب "
                "الغيابُ بلا عذر — فما بعد المهلة استثناءٌ يقرّره النائبُ الإداريّ بسبب"
            ),
        ),
    ]
    out = {}
    for cap in caps:
        assert cap.key not in out, f"قدرةٌ مكرّرة: {cap.key}"
        out[cap.key] = cap
    return out


def capability(key: str) -> Capability:
    try:
        return registry()[key]
    except KeyError:
        raise KeyError(f"لا قدرةَ باسم «{key}» في core/capabilities.py") from None


def has_capability(user, key: str) -> bool:
    """أيملك هذا المستخدمُ هذه القدرة؟ — بالوراثة نفسِها التي يفحص بها الحارس."""
    if user is None or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    cap = capability(key)
    return user.get_role() in cap.expanded_roles or cap.granted(user)


def capability_required(key: str):
    """حارسُ الشاشة بالقدرة — ``role_required`` بأعضائها، ويحمل اسمَها لمن يقرأ.

    ويُسقط الخطأُ في الاسم عند الاستيراد لا عند الطلب: قدرةٌ مكتوبةٌ خطأً لا تمرّ صامتة.
    """
    cap = capability(key)

    def decorator(view_func):
        if cap.grant is None:
            wrapped = role_required(cap.roles)(view_func)
        else:
            wrapped = _roles_or_grant(cap, view_func)
        wrapped._capability = key
        return wrapped

    return decorator


def _roles_or_grant(cap: Capability, view_func):
    """``role_required`` نفسُه — ويمرّ معه من مُنح القدرةَ بتكليفه (``cap.grant``).

    والأدوارُ تبقى على الدالّة (``_required_roles``) كما هي: السجلُّ والقائمةُ وحارسُ
    «كلُّ مسارٍ محروس» تقرؤها، والمنحُ في ``_grant`` يُسأل عنه لكلّ مستخدمٍ على حدة.
    """
    from functools import wraps

    from django.shortcuts import redirect

    from core.permissions import _forbidden_response, log_denial

    expanded = cap.expanded_roles

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect("login")
        if user.is_superuser or user.get_role() in expanded or cap.granted(user):
            return view_func(request, *args, **kwargs)
        role = user.get_role()
        log_denial(request, role=role, required=expanded)
        return _forbidden_response(request, f"ليس لديك صلاحية الوصول — دورك: {role or 'غير محدد'}")

    wrapper._required_roles = tuple(expanded)
    wrapper._grant = cap.grant
    return wrapper
