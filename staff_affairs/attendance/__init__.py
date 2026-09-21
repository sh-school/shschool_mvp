"""حضورُ الموظّفين والأذوناتُ القصيرة — القواعدُ والخدمة.

المرجعُ الحاكمُ لكلّ قاعدةٍ هنا: ``docs/compliance/staff_attendance_spec.md`` (م-1 … م-36)،
وأرقامُ «م» في التعليقات أرقامُ بنوده، وأسماءُ الرموز فيه لا أرقامُ الأسطر (ز-8).
ووراءه الأصولُ نفسُها:

* «السياسة»: ``data/2026-2027/05-السياسات الداخلية/01-2027 سياسة وضوابط الحضور
  والانصراف.pdf`` (ت/د 01/2027 بتاريخ 2026-08-23، صفحتان) — بنودُها 1.1 و2.1 و2.4
  و3.4–3.7 و4.1–4.6 و5.1–5.3.
* «ن02»: ``data/2026-2027/07-نماذج المدرسة/02) نموذج طلب تأخير - استئذان - خروج
  مبكر.pdf`` ص1 — مربّعاتُه بترتيب الورقة: بيانات الموظّف، ثمّ «استخدام السكرتارية»
  (رصيد الساعات، الاسم، توقيت تقديم)، ثمّ «استخدام المسؤول المباشر والنائب المسؤول»
  عمودين، ثمّ «استخدام الإدارة»، ثمّ «مدير المدرسة». وحاشيتُه بنصّها في ``_check_timing``.
* «ن03»: ``07-نماذج المدرسة/03) نموذج طلب.pdf`` ص1 — خطابٌ حرٌّ إلى مدير المدرسة،
  «يجب ارفاق مع طلب استثناء الخروج المبكر أو التأخير الصباحي ما يثبت حاجة الموظف
  لذلك»، و«استخدام مدير المدرسة: التغذية الراجعة … تاريخ التغذية الراجعة».
* «البطاقات»: ``02- شؤون الموظفين/05- الوصف الوظيفي/*.pdf`` — «المسؤول المباشر» في
  ترويسة كلّ بطاقة، ومنه جدولُ م-21 (``LINE_MANAGER``). وبطاقةُ نائب الشؤون الإدارية
  وحدَها فيها «الإنابة عن المدير في مهامه في حال غيابه» (م-24).
* ``AAdocs/ministry_data/2026_2027/rbac_roles.json`` — «reports_to» لكلّ مسمّى، ويوافق
  جدولَ البطاقات.

الفلسفة: **يحسب ولا ينفّذ آليّاً** — تُصنَّف الحالةُ وتُعدّ الدقائق، ولا خصمَ ولا
جزاءَ يُطلقه النظام؛ الخصمُ (البند 5) قرارٌ إداريٌّ على التقرير الشهريّ.
"""

from __future__ import annotations

from .assignments import (
    _TASKING_ROLES,
    ASSIGNMENT_MAX_DAYS,
    COORDINATOR_ROLES,
    AssignmentService,
    _holders_of,
)
from .context import (
    _REDACTED_FIELDS,
    LINE_MANAGER,
    NON_STAFF_ROLES,
    PRINCIPAL,
    PRINCIPAL_DELEGATE,
    RECORDERS,
    REPORT_WHOLE_SCHOOL,
    PolicyError,
    _active_role_holders,
    _audit,
    _audited,
    _established_absences,
    _minute,
    _now,
    _plain,
    _role_of,
    _StageDay,
    minutes_between,
    staff_members,
)
from .daily import (
    StaffAttendanceService,
    _DayCover,
)
from .exceptions import (
    ExceptionService,
)
from .permits import (
    COORDINATED_ROLES,
    PermitBalance,
    PermitService,
    can_submit_permits,
    department_coordinator,
    deputy_role_for,
)
from .rules import (
    ABSENCE_TYPE_KEYS,
    ABSENT_AFTER,
    ARRIVAL_STATUSES,
    COVERAGE_DEADLINE_DAY,
    LEAVING_PERMIT_TYPES,
    MONTHLY_PERMIT_CAP,
    PERMIT_MAX_MINUTES,
    SCHOOL_WEEKDAYS,
    STATUS_LABELS,
    STATUSES,
    WORK_END,
    WORK_START,
    _check_submission_window,
    _check_timing,
    _check_window,
    classify_arrival,
    coverage_deadline,
    early_leave_minutes,
    month_bounds,
)

__all__ = [
    "NON_STAFF_ROLES",
    "PRINCIPAL",
    "PRINCIPAL_DELEGATE",
    "REPORT_WHOLE_SCHOOL",
    "RECORDERS",
    "_now",
    "PolicyError",
    "minutes_between",
    "_minute",
    "_plain",
    "_REDACTED_FIELDS",
    "_audited",
    "_audit",
    "_role_of",
    "staff_members",
    "_active_role_holders",
    "_established_absences",
    "_StageDay",
    "LINE_MANAGER",
    "WORK_START",
    "WORK_END",
    "ABSENT_AFTER",
    "MONTHLY_PERMIT_CAP",
    "PERMIT_MAX_MINUTES",
    "COVERAGE_DEADLINE_DAY",
    "SCHOOL_WEEKDAYS",
    "STATUSES",
    "STATUS_LABELS",
    "ARRIVAL_STATUSES",
    "ABSENCE_TYPE_KEYS",
    "LEAVING_PERMIT_TYPES",
    "classify_arrival",
    "early_leave_minutes",
    "month_bounds",
    "coverage_deadline",
    "_check_submission_window",
    "_check_window",
    "_check_timing",
    "PermitBalance",
    "COORDINATED_ROLES",
    "department_coordinator",
    "can_submit_permits",
    "deputy_role_for",
    "PermitService",
    "ASSIGNMENT_MAX_DAYS",
    "COORDINATOR_ROLES",
    "_TASKING_ROLES",
    "AssignmentService",
    "_holders_of",
    "ExceptionService",
    "_DayCover",
    "StaffAttendanceService",
]
