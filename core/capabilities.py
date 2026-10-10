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
from typing import Any

from django.http import HttpRequest
from django.http.response import HttpResponseBase

from core.parent_consent import holds_parent_membership
from core.permissions import expand_roles, role_required
from core.unrestricted_role import (
    DEVELOPER_EXCLUDED_CAPABILITIES,
    has_unrestricted_role,
    is_excluded_developer,
)

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


def _delegated(key: str) -> Callable:
    """منحٌ لا يقرؤه الدور: القدرةُ المفوَّضةُ باسم مستخدمٍ بمنحٍ فعّال (`core/capability_grants.py`)."""

    def check(user: Any) -> bool:
        from core.capability_grants import holds

        return holds(user, key)

    return check


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
        _cap(
            "student_affairs.view",
            "الاطّلاعُ على سجلّات الطلبة",
            P.STUDENT_REGISTER_READ,
            scope="المدرسة؛ المشرفُ الإداريُّ لشُعب جناحه (wings/scope.py)",
        ),
        _cap(
            "student_affairs.follow_up",
            "متابعةُ حضور الطلبة وتأخّرهم وسلوكهم",
            P.STUDENT_FOLLOW_UP,
            scope="المدرسةُ للقيادة؛ المشرفُ الإداريُّ لشُعب جناحه (wings/scope.py)",
            basis="الدليل التنظيميّ 2026: متابعةُ الغياب اليوميّ والتأخّر الصباحيّ؛ وقرارُ المستخدم 2026-09-14: المشرفُ لجناحه فقط",
        ),
        _cap(
            "dashboard.absence_alert_names",
            "أسماءُ تنبيهات الغياب في لوحة الإداريّين",
            P.STUDENT_FOLLOW_UP | {"admin"},
            scope="المدرسةُ للقيادة وadmin؛ المشرفُ الإداريُّ لشُعب جناحه (wings/scope.py)",
            basis=(
                "قرارُ المالك 2026-10-03 (W-20261003-030): يبقى admin يرى أسماءَ قائمة التنبيهات "
                "بقدرةٍ مخصّصةٍ لها وحدَها، لا بمنح student_affairs.follow_up الذي يفتح ملفّاتِ الطلبة "
                "وحركاتِهم وسلوكَهم وتصديرَها والوسائطَ المحمية"
            ),
        ),
        _cap(
            "student_affairs.tardiness",
            "رصدُ التأخّر الصباحيّ وإلغاؤه",
            P.STUDENT_FOLLOW_UP,
            scope="المدرسةُ للقيادة؛ المشرفُ الإداريُّ لشُعب جناحه (wings/scope.py)",
            basis="الدليل التنظيميّ 2026 م 3.4.2.2: التأخّرُ الصباحيُّ على المشرف الإداريّ من أوّل مرّة",
        ),
        _cap("student_affairs.deactivate", "إيقافُ قيد طالب", P.STUDENT_DEACTIVATE),
        _cap(
            "student_affairs.transfers",
            "انتقالاتُ الطلبة (طلبٌ ومراجعةٌ وإتمام)",
            P.STUDENT_AFFAIRS_TRANSFERS,
            basis=(
                "إتمامُ الانتقال الصادر يعطّل عضويّةَ الطالب، فلا يُمنح من يملك إدخالَ البيانات وحدَه "
                "(W-20261001-020)؛ ومنسّقُ شؤون الطلبة منهم بقرار المالك D-265م"
            ),
        ),
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
            scope="المدرسة للقيادة والجهات؛ المعلّمُ لطلبة شُعبه؛ المشرفُ الإداريُّ لشُعب جناحه",
            basis="قرارُ المستخدم: القراءةُ لكلّ من يُدرّس الطالب",
        ),
        _cap(
            "students.search",
            "البحثُ السريعُ عن الطلبة",
            # سحبٌ صريحٌ من أربعةٍ لا يبحث أحدُهم عن طالبٍ في عمله (قرارُ المالك D-192م، 2026-10-04) — والباقون كما كانوا:
            # لم نحصرها بأصحاب `reports.results` لأنّ مشرفَ الجناح ومن في حكمه يبحثون بها مقيَّدين بجناحهم (قرارُ 2026-09-15).
            P.ALL_STAFF_ROLES
            - {"messenger", "storekeeper", "lab_technician", "canteen_supervisor"},
            scope="عشرُ نتائجَ بحدٍّ أقصى",
            basis="قرارُ المالك D-192م: تُسحب من المندوب وأمين المخزن ومحضّر المختبر ومشرف المقصف",
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
            {"principal", "secretary", "vice_admin", "vice_academic"},
            scope=(
                "السكرتيرُ والمديرُ ومن كُلّف بأعباء المدير للكادر كلِّه؛ والنائبان لمن تحت "
                "مسؤوليتهما وحدَهم (النائبُ الإداريّ للإداريّين، والأكاديميّ للأكاديميّين): "
                "يرصدون ويقبلون العذر لهم لا لغيرهم — قرارُ المالك 2026-09-19"
            ),
            basis=(
                "03_job_descriptions_rbac.md:101 السكرتير «متابعة الحضور والانصراف للموظفين»؛ "
                "rbac_permissions_matrix.md:55 كتابة ATTENDANCE؛ والمديرُ مالكُ الوحدات (:45)؛ "
                "وبطاقةُ نائب الشؤون الإدارية «الإنابة عن المدير في مهامه في حال غيابه»، ومنها "
                "قبولُ العذر (م-7 وم-24 من docs/compliance/staff_attendance_spec.md)"
            ),
        ),
        _cap(
            "staff_affairs.attendance_import",
            "استيرادُ كشف البصمة اليوميّ",
            {"principal", "secretary"},
            scope=(
                "السكرتيرُ والمديرُ للكادر كلِّه: الكشفُ يحوي المدرسةَ كلَّها فلا يستورده النائبُ "
                "المحصورُ بمن تحته؛ ومن ينوب عن المدير بتكليفٍ يرصد يدويّاً من لوحة الرصد"
            ),
            basis=(
                "السكرتير «متابعة الحضور والانصراف للموظفين» (03_job_descriptions_rbac.md:101)؛ "
                "والاستيرادُ يكتب عبر StaffAttendanceService.mark نفسِها فيحمل قيودَ الرصد كلَّها؛ "
                "طلبُ المالك 2026-10-02 (W-20261002-011)"
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
            {"principal", "vice_admin", "vice_academic", "secretary", "coordinator"},
            scope=(
                "الطلباتُ في مربّع المستخدم وحدَها: السكرتاريةُ للرصيد، ومنسّقُ المادّة لإذن "
                "معلّمي قسمه قبل النائب (قرارُ المدرسة)، والنائبُ المختصُّ "
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
            "staff_affairs.assignments",
            "تكليفُ موظّفٍ بأعباء وظيفة (م-43)",
            {"principal", "vice_admin", "vice_academic"},
            scope=(
                "كلٌّ عن وظيفته وحدَها: المديرُ يكلّف نائبَيه (وغيرَهما إن غاب النائبان معاً)، "
                "والنائبُ الأكاديميّ أحدَ المنسّقين، والنائبُ الإداريّ أحدَ من تحت مسؤوليته"
            ),
            basis=(
                "النظام الوظيفيّ لموظفي المدارس (قرار مجلس الوزراء 32/2019) م-43: «يجوز لمدير "
                "المدرسة ندب الموظف للقيام مؤقتاً بأعباء وظيفة أخرى داخل المدرسة»، وقانون "
                "الموارد البشرية 15/2016 م-53؛ وقرارُ المدرسة 2026-09-19 في توزيع التكليف على "
                "النائبين (docs/compliance/staff_attendance_spec.md، م-25)"
            ),
        ),
        _cap(
            "staff_affairs.exemptions",
            "الإعفاءُ من رصد الحضور اليوميّ",
            {"principal", "vice_admin"},
            scope=(
                "المديرُ ونائبُه الإداريّ: يعفيان موظّفاً أو أكثر من الرصد اليوميّ لمدّةٍ أو بلا "
                "نهاية، فلا يدخل لوحةَ الرصد ولا تقريرَ الغياب الشهريّ ولا إخطارَ الخصم"
            ),
            basis=(
                "قرارُ المالك 2026-09-21 (docs/compliance/staff_attendance_spec.md، ق-16): "
                "موظّفٌ لا يداوم بحكم وضعه الوظيفيّ يبقى حسابُه، ولا يُرصد غائباً فيُخصم منه "
                "(سياسة الحضور ت/د 2027/01، البند 5.1). ولا يُخزَّن سببُ الإعفاء: بيانةٌ صحّيّةٌ "
                "محتملة (قانون 13/2016)"
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
            # مطوّرُ المنصّة يمارس دورَ مسؤول حماية البيانات، ويصله تنبيهُ مهلة الـ72 ساعة
            # (`_breach_inapp_recipients`) برابط الصفحة — فلا يُحجب عنها.
            {"principal", "vice_admin", "vice_academic", "admin", "platform_developer"},
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
        _cap(
            "reports.school",
            "تقاريرُ الحضور والسلوك والشهادات للشعبة",
            leadership | {"student_affairs_coordinator"},
        ),
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
            scope="قسمُ المنسّق — وكلُّ الأقسام لمُشغِّل الجدول",
            basis="افتراضٌ موصى به — تُبدّله المدرسة (WorkloadGovernance)؛ ومُشغِّلُ الجدول (`schedule.operator`) يُدخل بمنحه",
            grant=_delegated("schedule.operator"),
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
        _cap(
            "behavior.committee",
            "لجنةُ الانضباط",
            P.BEHAVIOR_COMMITTEE | {"student_affairs_coordinator"},
        ),
        _cap(
            "behavior.statistics",
            "إحصاءاتُ السلوك",
            P.BEHAVIOR_COMMITTEE
            | P.BEHAVIOR_VIEW_ALL
            | P.BEHAVIOR_STATS_TEACHING
            | {"student_affairs_coordinator"},
        ),
        _cap(
            "behavior.summon_parent",
            "استدعاءُ وليّ الأمر",
            P.BEHAVIOR_MANAGE | {"psychologist", "student_affairs_coordinator"},
        ),
        # ── العيادة والمكتبة والنقل ─────────────────────────────────
        _cap(
            "clinic.access",
            "وحدةُ العيادة (قراءة)",
            {"nurse", "principal", "vice_admin", "student_affairs_coordinator"},
        ),
        _cap(
            "clinic.write",
            "تعديلُ السجلّ الصحّيّ وتسجيلُ الزيارات",
            {"nurse", "principal", "vice_admin"},
            basis="بيانات صحّيّة لقاصرين: الكتابةُ سريريّةٌ — حكم 0104 على W-20261001-020 (المنسّقُ قراءةً فقط)",
        ),
        _cap("library.view", "المكتبةُ والكتب", P.LIBRARY_VIEW | P.LIBRARY_FULL),
        _cap("library.lend", "الإعارةُ والإرجاع", {"librarian", "principal", "vice_admin"}),
        _cap("library.borrowings_all", "سجلُّ استعارات المدرسة", P.LIBRARY_BORROWINGS_ALL),
        _cap(
            "transport.access",
            "وحدةُ النقل",
            P.TRANSPORT_FULL | P.TRANSPORT_MANAGE | {"student_affairs_coordinator"},
        ),
        # ── الأدوات التقنيّة ─────────────────────────────────────────
        _cap(
            "it_admin.reset_passwords",
            "إعادةُ تعيين كلمات مرور المستخدمين",
            {"it_technician"},
            basis="قرارُ المالك 2026-09-22",
        ),
        # ── الكنترول ────────────────────────────────────────────────
        _cap(
            "exam_control.access",
            "نظامُ الكنترول",
            P.EXAM_CONTROL_ACCESS,
            basis="افتراضُ المنصّة — والنصُّ الوزاريُّ يجعله لجنةً موقوتة (الدراسة، ملحق د)",
        ),
        _cap(
            "exam_control.report_incident",
            "تسجيلُ حادثةِ اختبارٍ ومراجعتُها",
            P.EXAM_CONTROL_REPORT_INCIDENT,
            basis="قرارُ 2026-09-15 (النطاق) وقرارُ المستخدم 2026-09-17 (لا شيءَ آخر من الكنترول)",
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
            "operations.daily_absence",
            "غيابُ اليوم (تقريرُ غياب الطلبة اليوميّ)",
            P.DAILY_STUDENT_ABSENCE_REPORT,
            basis="قرارُ المالك D-273م: إدارةُ شؤون الطلاب كاملةً لمنسّق شؤون الطلبة، دون تقارير المعلّمين",
        ),
        _cap(
            "operations.substitutes_manage",
            "تسجيلُ غياب معلّمٍ وتعيينُ بديله",
            P.OPERATIONS_SUBSTITUTES_MANAGE,
        ),
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
            "schedule.operator",
            "مُشغِّلُ الجدول العامّ — إسنادُ الموادّ وتوليدُ الجدول",
            P.SCHEDULE_ADMIN,
            scope="المدرسة (كلُّ الأقسام)",
            basis=(
                "قرارُ المالك 2026-09-25 (التذكرة SOS-20260924-1CFE): قدرةٌ مفوَّضةٌ باسم المستخدم "
                "يمنحها ويسحبها المديرُ والنائبُ الأكاديميّ ومطوّرُ المنصّة — إدخالُ الإسناد لكلّ الأقسام "
                "بلا وقفِ المنسّقين، وتوليدُ الجدول؛ لا اعتمادَ ولا مراجعةَ ولا إعداداتٍ. الأدوارُ هنا من "
                "يولّد الجدولَ اليوم (`schedule.admin`) فلا يفقد أحدٌ ما يملك"
            ),
            grant=_delegated("schedule.operator"),
        ),
        _cap(
            "schedule.approve",
            "اعتمادُ الجدول",
            P.SCHEDULE_APPROVE,
            basis=(
                "قرارُ المالك 2026-09-25 (جلسةُ الجدول): المديرُ والنائبُ الأكاديميّ، والمطوّرُ استثناءً "
                "في أيّام الدوام بسببٍ إلزاميٍّ وتدقيق — ولا النائبُ الإداريّ. تُعرَّف هنا ويربطها بواجهة "
                "الاعتماد مسارُ الجدول"
            ),
        ),
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
        _cap(
            "parents.portal",
            "بوّابةُ وليّ الأمر",
            P.PARENT_PORTAL,
            scope="أبناؤه وحدَهم",
            basis=(
                "قرارُ المالك 2026-09-16: الكادرُ الذي له عضويّةُ وليّ أمرٍ يدخل بوّابتَه "
                "ليرى أبناءه وحدَهم، بعد الموافقة على سياسة البيانات"
            ),
            grant=holds_parent_membership,
        ),
        _cap("parents.admin", "إدارةُ ربط أولياء الأمور", P.PARENT_PORTAL_ADMIN),
        # ── الأجنحة ─────────────────────────────────────────────────
        _cap(
            "wings.floors",
            "شاشةُ الأجنحة والطوابق",
            {
                "principal",
                "vice_admin",
                "vice_academic",
                "admin_supervisor",
                "platform_developer",
                "student_affairs_coordinator",  # بندٌ في قائمة إدارة شؤون الطلاب (D-273م)
            },
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
            "wings.school_wide",
            "حاصرُ الغياب العامّ — الأجنحةُ الخمسةُ كلُّها",
            P.SCHOOL_WIDE_ABSENCE_ROLES,
            scope="أجنحةُ المدرسة كلُّها، للغياب وحدَه",
            basis=(
                "قرارُ المالك 2026-10-06: موظّفٌ إداريٌّ (مشرفٌ إداريّ) يحصر الغيابَ في المدرسة كلِّها، "
                "فيرى الأجنحةَ الخمسةَ ويعتمد رصدَ المعلّمين ويصحّحه ويحوّل العذرَ بمهلته، ويرفع ملخّصَ الحصّتين "
                "الأولى والثانية للوزارة يدويّاً. قدرةٌ مفوَّضةٌ باسمه (يمنحها المديرُ أو النائبُ الأكاديميّ) "
                "لا دورٌ جديد؛ ويبقى عنه ما يُحجب عن مشرف الجناح (الدرجاتُ وملاحظاتُ الأخصائيّين وسببُ العيادة)"
            ),
            grant=_delegated("wings.school_wide"),
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
    if is_excluded_developer(user, key):
        return False
    if schedule_developer_only_blocks(user, key):
        return False
    if user.is_superuser or has_unrestricted_role(user):
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
        if key in DEVELOPER_EXCLUDED_CAPABILITIES:
            wrapped = _refuse_excluded_developer(key, wrapped)
        if key in SCHEDULE_DEVELOPER_ONLY_CAPABILITIES:
            wrapped = schedule_developer_only(key)(wrapped)
        wrapped._capability = key
        return wrapped

    return decorator


# ── حصرُ توليد الجدول واعتماده بمطوّر المنصّة (W-20261010-034، أمرُ المالك 2026-10-10) ──────────
#: القدراتُ التي تولّد الجدولَ أو تعتمده. المنفذُ الواحدُ هنا لا في كلّ عرض: `capability_required` يلفّها،
#: و`has_capability` يردّها (فتُغلق `approve_v2` والقوالبُ)، و`approve_schedule` — وقدرتُه `schedule.settings`
#: الأوسعُ من الاعتماد — يلفّه `schedule_developer_only` صراحةً. والقراءةُ (`schedule.view`) لا تمسّ.
SCHEDULE_DEVELOPER_ONLY_CAPABILITIES = frozenset(
    {"schedule.admin", "schedule.operator", "schedule.approve"}
)
SCHEDULE_DEVELOPER_ONLY_MESSAGE = (
    "توليدُ الجدول واعتمادُه محصوران الآن بمطوّر المنصّة — أمرُ المالك. ويبقى لك اطّلاعٌ على الجدول."
)


def schedule_developer_only_active() -> bool:
    """مفتاحُ `SCHEDULE_DEVELOPER_ONLY` (البيئة، الافتراضيّ مشغَّل) — إطفاؤه يعيد السلوكَ السابق بلا شيفرة."""
    from django.conf import settings

    return bool(getattr(settings, "SCHEDULE_DEVELOPER_ONLY", True))


def schedule_developer_only_blocks(user: Any, key: str) -> bool:
    """أيُحجَب هذا المستخدمُ عن هذه القدرة بالحصر؟ — لغير مطوّر المنصّة، والمفتاحُ مشغَّل."""
    if key not in SCHEDULE_DEVELOPER_ONLY_CAPABILITIES or not schedule_developer_only_active():
        return False
    return user.get_role() != "platform_developer"


def schedule_developer_only(key: str) -> Callable:
    """يلفّ عرضاً برفضٍ ظاهرِ السبب وتدقيقٍ بالدور والمسار (بلا اسم المستخدم) لغير مطوّر المنصّة."""
    from functools import wraps

    from core.permissions import _forbidden_response, log_denial

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
            user = request.user
            if user.is_authenticated and schedule_developer_only_blocks(user, key):
                from core.models import AuditLog

                role = user.get_role()
                log_denial(request, role=role, source="schedule_developer_only")
                AuditLog.log(
                    user=user,
                    action="view",
                    model_name="other",
                    object_repr="رُفض توليدُ/اعتمادُ الجدول: محصورٌ بمطوّر المنصّة",
                    changes={"role": role, "path": request.path, "capability": key},
                    school=getattr(request, "school", None),
                    request=request,
                )
                return _forbidden_response(request, SCHEDULE_DEVELOPER_ONLY_MESSAGE)
            return view_func(request, *args, **kwargs)

        for attr in ("_required_roles", "_grant"):
            if hasattr(view_func, attr):
                setattr(wrapper, attr, getattr(view_func, attr))
        return wrapper

    return decorator


def _refuse_excluded_developer(
    key: str, view_func: Callable[..., HttpResponseBase]
) -> Callable[..., HttpResponseBase]:
    """يردّ المطوّرَ عن قدرةٍ استثناها المالكُ (D-128م) قبل أيّ تحقّق آخر — ولو كان superuser."""
    from functools import wraps

    from core.permissions import _forbidden_response, log_denial

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        if is_excluded_developer(request.user, key):
            log_denial(request, role="platform_developer", source="excluded_capability")
            return _forbidden_response(request, "رصدُ الحضور ليس للمطوّر — قرارُ المالك D-128م")
        return view_func(request, *args, **kwargs)

    for attr in ("_required_roles", "_grant"):
        if hasattr(view_func, attr):
            setattr(wrapper, attr, getattr(view_func, attr))
    return wrapper


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
        if (
            user.is_superuser
            or has_unrestricted_role(user)
            or user.get_role() in expanded
            or cap.granted(user)
        ):
            return view_func(request, *args, **kwargs)
        role = user.get_role()
        log_denial(request, role=role, required=expanded)
        return _forbidden_response(request, f"ليس لديك صلاحية الوصول — دورك: {role or 'غير محدد'}")

    wrapper._required_roles = tuple(expanded)
    wrapper._grant = cap.grant
    return wrapper
