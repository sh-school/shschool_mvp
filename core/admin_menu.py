"""قائمةُ لوحة الإدارة الأفقيّة — تجميعُ النماذج المسجَّلة بأسماء أقسام المنصّة.

لا تغيّر هذه القائمةُ ما تعرضه لوحةُ الإدارة (النماذجُ المسجَّلةُ هي نفسُها) ولا تلمس المنصّةَ:
تنظّمُ الموضعَ فقط. المفتاحُ `التطبيق.النموذج`؛ وما لم يُذكر هنا يظهر تحت «أخرى» فلا يسقط شيء،
والاختبارُ (tests/test_admin_menu.py) يفشل إن سقط نموذجٌ مسجَّلٌ أو ذُكر نموذجٌ لا وجودَ له.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

from django.conf import settings

#: جدولا رموز JWT — في الإدارة فقط حين يُفتح JWT (`core/admin_hidden.py`)؛ وهو مغلقٌ فجدولاهما فارغان.
JWT_TABLES: tuple[str, ...] = (
    ("token_blacklist.OutstandingToken", "token_blacklist.BlacklistedToken")
    if settings.API_JWT_ENABLED
    else ()
)

#: (اسمُ القسم، ((عنوانٌ فرعيّ أو None، (نماذج…)), …)) — بترتيب قائمة المنصّة العلويّة.
GROUPS: tuple[tuple[str, tuple[tuple[str | None, tuple[str, ...]], ...]], ...] = (
    (
        "الشؤون الأكاديمية",
        (
            (
                "الجدول والحصص",
                (
                    "operations.Subject",
                    "operations.Session",
                    "operations.ScheduleSlot",
                    "operations.TimeSlotConfig",
                    "operations.SubjectClassAssignment",
                    "operations.SchedulingResource",
                    "operations.ScheduleConstraintOverride",
                    "operations.TeacherPreference",
                    "operations.ScheduleGeneration",
                    "operations.ScheduleBaseline",
                    "academic_management.WorkloadGovernance",
                ),
            ),
            (
                "التقييمات والدرجات",
                (
                    "assessments.SubjectClassSetup",
                    "assessments.AssessmentPackage",
                    "assessments.Assessment",
                    "assessments.StudentAssessmentGrade",
                    "assessments.StudentSubjectResult",
                    "assessments.AnnualSubjectResult",
                ),
            ),
            (
                "كنترول الاختبارات",
                (
                    "exam_control.ExamRoom",
                    "exam_control.ExamSchedule",
                    "exam_control.ExamSession",
                    "exam_control.ExamIncident",
                    "exam_control.ExamGradeSheet",
                ),
            ),
            (
                "الزيارات الصفية",
                (
                    "quality.ObservationCriterion",
                    "quality.ClassroomObservation",
                    "quality.ObservationScore",
                ),
            ),
        ),
    ),
    (
        "شؤون الموظفين",
        (
            (
                "الحضور والإجازات",
                (
                    "staff_affairs.LeaveBalance",
                    "staff_affairs.LeaveRequest",
                    "operations.TeacherAbsence",
                    "operations.SubstituteAssignment",
                ),
            ),
            (
                "التقييم والتطوير",
                (
                    "quality.EvaluationCycle",
                    "quality.RoleEvaluationTemplate",
                    "quality.EmployeeEvaluation",
                    "quality.EvaluationLevelBackup",
                ),
            ),
        ),
    ),
    (
        "شؤون الطلاب",
        (
            (
                "الطلاب وأولياء الأمور",
                (
                    "core.StudentEnrollment",
                    "core.ParentStudentLink",
                    "student_affairs.StudentTransfer",
                ),
            ),
            (
                "الحضور والغياب",
                ("operations.StudentAttendance", "operations.AbsenceAlert"),
            ),
            (
                "إدارة السلوك",
                (
                    "behavior.ViolationCategory",
                    "behavior.BehaviorInfraction",
                    "behavior.AutoInfractionNotice",
                ),
            ),
        ),
    ),
    (
        "مركز معلومات الطلبة",
        ((None, ("student_info.StudentNote", "student_affairs.StudentActivity")),),
    ),
    (
        "الجودة",
        (
            (
                "الخطة التشغيلية",
                (
                    "quality.OperationalDomain",
                    "quality.OperationalTarget",
                    "quality.OperationalIndicator",
                    "quality.OperationalProcedure",
                ),
            ),
            (
                "اللجان",
                ("quality.QualityCommitteeMember", "quality.ExecutorMapping"),
            ),
        ),
    ),
    (
        "الخدمات",
        (
            (
                "الخدمات المساندة",
                (
                    "clinic.HealthRecord",
                    "clinic.ClinicVisit",
                    "transport.SchoolBus",
                    "transport.BusRoute",
                    "library.LibraryBook",
                    "library.BookBorrowing",
                    "library.LibraryActivity",
                ),
            ),
        ),
    ),
    (
        "الإدارة",
        (
            (
                "هيكل المدرسة",
                (
                    "core.School",
                    "core.AcademicYear",
                    "core.Semester",
                    "core.CalendarEvent",
                    "core.Department",
                    "core.ClassGroup",
                    "core.Wing",
                    "core.WingCoverage",
                    "core.TimeBand",
                ),
            ),
            (
                "الإشعارات",
                (
                    "notifications.InAppNotification",
                    "notifications.NotificationDispatch",
                    "notifications.NotificationDelivery",
                    "notifications.NotificationEnqueueIntent",
                    "notifications.NotificationLog",
                    "notifications.DeadLetterMessage",
                    "notifications.PushSubscription",
                    "notifications.NotificationSettings",
                    "notifications.UserNotificationPreference",
                ),
            ),
            (
                "أدوات المطوّر",
                (
                    "developer_feedback.DeveloperMessage",
                    "developer_feedback.MessageStatusLog",
                    "developer_feedback.DeveloperMessageNotification",
                    "developer_feedback.LegalOnboardingConsent",
                    "roadmap.RoadmapItem",
                    "roadmap.RoadmapKpi",
                    "roadmap.RoadmapDecision",
                    "roadmap.RoadmapRisk",
                    "roadmap.RoadmapChecklistItem",
                    "roadmap.RoadmapMeta",
                ),
            ),
            (
                "الأمان والصلاحيات",
                (
                    "core.CustomUser",
                    "core.Role",
                    "core.Membership",
                    "auth.Group",
                    "core.CapabilityGrant",
                    "core.AuditLog",
                    "developer_feedback.AuditLog",
                    "core.ConsentRecord",
                ),
            ),
        ),
    ),
    (
        "النظام التقني",
        (
            (
                None,
                (
                    "axes.AccessAttempt",
                    "axes.AccessLog",
                    "axes.AccessFailureLog",
                    *JWT_TABLES,
                    "staging.ImportLog",
                ),
            ),
        ),
    ),
)

OTHER = "أخرى"


class Page(NamedTuple):
    """صفحةٌ ليست نموذجاً تُدرَج في القائمة إلى جانب النماذج (لا تظهر من `available_apps`)."""

    group: str
    section: str | None
    name: str
    #: نصٌّ لا `reverse()`: core لا يستورد التطبيقَ الذي فوقه؛ ويحرس صحّتَه tests/test_admin_menu.py.
    url: str
    developer_only: bool = False


PAGES: tuple[Page, ...] = (
    Page("الإدارة", "أدوات المطوّر", "مركز قيادة الجودة", "/admin/command-center/", True),
)

#: تصحيحاتٌ إملائيّةٌ لأسماء الجموع تخصّ لوحةَ الإدارة وحدَها (لا يُعدَّل نموذجٌ في المنصّة).
LABELS: Mapping[str, str] = {
    "core.StudentEnrollment": "تسجيلات الطلاب",
    "staging.ImportLog": "سجلات الاستيراد",
    "student_affairs.StudentActivity": "الأنشطة الطلابية",
    "notifications.NotificationEnqueueIntent": "نيّات الإدراج في الطابور",
}


#: أسماءُ تطبيقاتٍ من مكتباتٍ خارجيّة — عربيّةً في قالب الإدارة فقط، والاسمُ التقنيُّ بين قوسين
#: (يبقى مطابقاً لاسم التطبيق في settings.INSTALLED_APPS فيسهل البحث عنه في الكود). لا تُعدَّل
#: حزمُ الطرف الثالث نفسُها.
APP_LABELS = {
    "axes": "الحماية من محاولات الدخول (AXES)",
    "token_blacklist": "الرموزُ المُبطَلة (Token Blacklist)",
}


def mapped_keys() -> list[str]:
    return [key for _g, secs in GROUPS for _t, keys in secs for key in keys]


def _add_pages(menu: list[dict[str, Any]], path: str, developer: bool) -> None:
    """يُلحق `PAGES` بأقسامها في آخر القسم؛ ويُنشئ القسمَ أو المجموعةَ إن غابا (لا نموذجَ متاحاً فيهما)."""
    for page in PAGES:
        if page.developer_only and not developer:
            continue
        group = next((g for g in menu if g["label"] == page.group), None)
        if group is None:
            group = {"label": page.group, "sections": []}
            menu.append(group)
        section = next((s for s in group["sections"] if s["label"] == page.section), None)
        if section is None:
            section = {"label": page.section, "items": []}
            group["sections"].append(section)
        section["items"].append(
            {"name": page.name, "url": page.url, "current": path.startswith(page.url)}
        )


def build_menu(
    available_apps: Iterable[Mapping[str, Any]], path: str, *, developer: bool = False
) -> list[dict[str, Any]]:
    """يُرجع الأقسامَ للعرض: كلُّ نموذجٍ متاحٍ للمستخدم في قسمه، وما لم يُذكر تحت «أخرى».

    وصفحاتُ `PAGES` (مثل مركز قيادة الجودة) تُلحَق بأقسامها؛ ما كان منها «للمطوّر وحدَه» لا يراه غيرُه.
    """
    found: dict[str, dict[str, Any]] = {}
    for app in available_apps:
        for model in app.get("models", []):
            url = model.get("admin_url")
            if not url:
                continue
            key = f"{app['app_label']}.{model['object_name']}"
            found[key] = {
                "name": LABELS.get(key, model["name"]),
                "url": url,
                "current": path.startswith(url),
            }

    used: set[str] = set()
    menu: list[dict[str, Any]] = []
    for label, sections in GROUPS:
        out_sections = []
        for title, keys in sections:
            items = [found[k] for k in keys if k in found]
            used.update(k for k in keys if k in found)
            if items:
                out_sections.append({"label": title, "items": items})
        if out_sections:
            menu.append({"label": label, "sections": out_sections})
    _add_pages(menu, path, developer)
    rest = [found[k] for k in found if k not in used]
    if rest:
        menu.append({"label": OTHER, "sections": [{"label": None, "items": rest}]})
    for group in menu:
        group["current"] = any(i["current"] for s in group["sections"] for i in s["items"])
        group["count"] = sum(len(s["items"]) for s in group["sections"])
    return menu


def search_index(menu: list[dict[str, Any]]) -> list[dict[str, str]]:
    """فهرسُ بحثٍ مسطَّحٌ لكلّ نماذج القائمة — يُضمَّن JSON في `_nav.html` ويُصفَّى في admin_nav.js
    بلا طلبٍ إضافيّ؛ 97 نموذجاً لا يستحقّ استعلاماً منفصلاً في كلّ ضغطة مفتاح."""
    return [
        {"name": str(item["name"]), "url": item["url"], "group": str(group["label"])}
        for group in menu
        for section in group["sections"]
        for item in section["items"]
    ]
