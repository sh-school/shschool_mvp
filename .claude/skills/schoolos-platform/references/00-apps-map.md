# 00 — خريطةُ التطبيقات والمسارات

> متى تقرأ هذا الملف: حين تسأل «أين يوجد X؟» أو «أيُّ تطبيقٍ يملك هذه الميزة؟» أو تحتاج مسارَ URL أو إصدارَ مكتبة.
> تحقّقتُ منه على `main@81bc4937` (2026-09-28). قبل الاعتماد على اسمٍ: `git grep -n "class <Name>" origin/main -- '*.py'`.

## الحزمة التقنيّة

| المكوّن | الإصدار | المصدر |
|---|---|---|
| Python | 3.12 | `Dockerfile` (`python:3.12-slim-bookworm`) |
| Django | 5.2.17 | `requirements.txt` |
| HTMX | 1.9.12 (ملفٌّ محلّيّ) | `static/js/htmx.min.js`، يُحمَّل في `templates/base/base.html` |
| PostgreSQL | 18 محلّيّاً (`docker-compose.yml`) والإنتاجُ 18 بتعليق `backup.yml`؛ وبوّاباتُ CI على 16 | `.github/workflows/quality-gate.yml` — انظر «يحتاج تأكيد» في CHANGES |
| ASGI | daphne 4.2.3 + channels 4.3.2 (WebSocket للإشعارات) | `requirements.txt`، `Dockerfile` CMD |
| المهامّ الخلفيّة | Celery 5.6.3 + Redis؛ beat عبر django-celery-beat | `requirements.txt`، `shschool/celery.py` |
| API | DRF 3.18.1 + simplejwt + drf-spectacular | `requirements.txt` |
| PDF / Excel | WeasyPrint 70.0 (`core/pdf_utils.py`) / openpyxl 3.1.5 | `requirements.txt` |
| أمن | django-axes 8.3.1، django-csp 4.0 (يقرأ `CONTENT_SECURITY_POLICY` وحده)، ratelimit | `shschool/settings/base.py` |

الإعدادات: `shschool/settings/{base,development,testing,preview,staging,production}.py`.

## التطبيقات (24 في `INSTALLED_APPS`) ومساراتها

| التطبيق | المسار | ما يملكه (نماذجُ مختارة) |
|---|---|---|
| `core` | `auth/` `dashboard/` `core/` `exports/` `search/` `styleguide/…` | `CustomUser` `Profile` `School` `Role` `Membership` `Department` `AcademicYear` `Semester` `CalendarEvent` `ClassGroup` `Wing` `WingCoverage` `TimeBand` `StudentEnrollment` `ParentStudentLink` `AuditLog` `ConsentRecord` `BreachReport` `ErasureRequest` `PermissionAuditLog` `CapabilityGrant` `ExportJob` `StoredFile` |
| `operations` | **`teacher/`** و`api/` | الجدول: `Subject` `ScheduleSlot` `TimeSlotConfig` `SubjectClassAssignment` `TeacherPreference` `TeacherExemption` `ScheduleBaseline` `ScheduleConstraintOverride` `ScheduleGeneration` `FreeSlotRegistry`؛ الحضور: `Session` `StudentAttendance` `AbsenceExcuse` `GuardianContact` `AbsenceAlert` `SectionDayConfirmation` `ClassExit` `PeriodConfirmation`؛ البدلاء: `TeacherAbsence` `SubstituteAssignment` `TeacherSwap` `CompensatorySession`؛ `TemporaryPermission` |
| `assessments` | `assessments/` | `SubjectClassSetup` `AssessmentPackage` `Assessment` `StudentAssessmentGrade` `StudentSubjectResult` `AnnualSubjectResult` `ExamDeprivation` `ExamMisconduct` (المرجع 02) |
| `behavior` | `behavior/` | `ViolationCategory` `BehaviorInfraction` `BehaviorPointRecovery` `AutoInfractionNotice`؛ الدليل في `conduct_2026.py` |
| `quality` | `quality/` | حزمة `quality/models/`: التشغيليّ (`OperationalDomain` … `ProcedureEvidence` `ExecutorMapping`)، وتقييمُ الأداء الموحَّد `EmployeeEvaluation` (ADR-0002)، واللجنة؛ والزيارات الصفّيّة في `observation_models.py` |
| `notifications` | `notifications/` | `NotificationLog` `NotificationSettings` `PushSubscription` `InAppNotification` `UserNotificationPreference` `NotificationDispatch` `NotificationDelivery` `NotificationEnqueueIntent` `DeadLetterMessage` |
| `exam_control` | `exam-control/` | `ExamSession` `ExamRoom` `ExamSupervisor` `ExamSchedule` `ExamIncident` `ExamEnvelope` `ExamGradeSheet` |
| `clinic` · `library` · `transport` | بأسمائها | `HealthRecord` `ClinicVisit` · `LibraryBook` `BookBorrowing` `LibraryActivity` · `SchoolBus` `BusRoute` |
| `student_affairs` | `student-affairs/` | `StudentTransfer` `StudentActivity`؛ تصديرُ قائمة الطلبة |
| `student_info` | `student-info/` | `StudentNote` (ملاحظاتُ الجهات الخمس؛ الوصولُ في `access.py`) |
| `staff_affairs` | `staff-affairs/` | `LeaveBalance` `LeaveRequest` `StaffAttendance` `PermitRequest` `AttendanceException` `StaffAssignment` `StaffAttendanceExemption`؛ حزمة `attendance/` |
| `academic_management` | **`academic/`** | `TeacherWorkloadPlan` `TeacherWorkloadAllocation` `WorkloadGovernance` `CurriculumPlan` `CoursePreparation` |
| `wings` | `wings/` | بلا نماذج؛ `scope.py` نطاقُ المشرف، و`register*.py` سجلُّ الجناح |
| `parents` | `parents/` | بوّابةُ وليّ الأمر، بلا نماذج |
| `reports` · `analytics` | بأسمائهما | `ReportDataService` `AcademicReportsService` `ExcelService` · `AnalyticsService` `KPIService` |
| `breach` | `breach/` | واجهةُ `BreachReport` (PDPPL)، بلا نماذج |
| `staging` | **`import/`** | `ImportLog` — الاستيراد، لا بيئةَ staging |
| `governance` | (`dbmedia/`) | المحوُ `erasure_service.py`، الاحتفاظ `retention.py`، وصولُ الملفّات (ADR-0004) |
| `roadmap` · `command_center` · `developer_feedback` | `roadmap/` `command-center/` `rum/` `developer-feedback/` | أدواتُ مطوّر المنصّة: الخارطةُ الحيّة، مركزُ الجودة، رسائلُ «أرسل إلى المطوّر» |

`api/` ليس تطبيقاً (لا `apps.py`): وحدةُ DRF على `api/v1/` (`views.py` `serializers.py` `urls.py` `permissions.py`). المصدر: `shschool/urls.py`، `shschool/settings/base.py`.

## أين أجد…

| أبحث عن | الموضع |
|---|---|
| أوزانُ الباقات وحدُّ النجاح والحكم | `core/domain/grades.py`؛ الحفظُ والحساب `assessments/services.py::GradeService`؛ الحكمُ `assessments/verdict_engine.py::VerdictEngine` |
| عتباتُ الغياب والأعذار والتأخّر | `operations/absence_policy.py` |
| مخالفاتُ السلوك وسلالمُها | `behavior/conduct_2026.py`؛ الاقتراحُ `BehaviorService.suggest_escalation_step` |
| من يرى أيَّ طالب | `core/permissions.py::get_teacher_student_ids`، `wings/scope.py::student_scope_for` |
| صلاحيّاتُ الأدوار / القدرات | `core/permissions.py` (مجموعات + `role_required`) / `core/capabilities.py` (`capability_required`) |
| العامُ الدراسيّ الجاري | `core/academic_calendar.py` (`academic_year_for(request)`، `academic_year_for_school`) |
| توليدُ الجدول | `operations/scheduler*.py`، `operations/services/schedule*.py`؛ الخطّة `docs/schedule_generation_remediation_plan_2026-09.md` |
| إرسالُ إشعار | `notifications/hub.py::NotificationHub.dispatch` |
| بياناتُ التقارير | `reports/services.py::ReportDataService` (`get_student_report`، `get_class_results`، `get_attendance_report`، `get_behavior_report` — بلا HTTP) و`AcademicReportsService`؛ وExcel في `ExcelService` (RTL، رأسٌ مجمَّد، مرشِّح، حمايةُ ورقة، A4 عموديّ أو A3 أفقيّ، أحمرُ لما دون 50) — معاييرُ الشكل عند web-design-mastery |
| ألوانُ الهويّة في Python (Excel/PDF) | `core/brand.py` (`MAROON`، `excel()`) |
| تصديرٌ جديد | `core/exports/registry.py` + ADR-0007 |
| مصدرُ الحقيقة الوزاريّ | `AAdocs/ministry_data/2026_2027/*.md` (الـPDF حَكَمٌ؛ مهارة schoolos-source-of-truth) |
| القراراتُ المعماريّة | `docs/adr/` (0001–0007)؛ الطبقات `docs/architecture/layering.md` |
| خريطةُ الحرّاس | `docs/governance/regression_guards.md` |
| أنماطُ تخطيط الصفحات | `docs/design/page_layouts.md` (مهارة web-design-mastery) |

## فخاخُ الأسماء
- **جداولُ `core_*` لنماذج خارج core:** `behavior` و`clinic` و`library` و`transport` نُقلت من core وأبقت جداولَها بـ`db_table` (`core_behaviorinfraction`، `core_healthrecord`، `core_librarybook`، `core_schoolbus`…). في SQL الخامّ وسياسات RLS و`core/tenancy.py` الاسمُ `core_…`. المصدر: `Meta.db_table` في نماذجها.
- **اسمان لصنفين:** `AuditLog` في `core/models/audit.py` وفي `developer_feedback/models.py`؛ و`PermissionAuditLog` في `core/models/permission_audit.py` وفي `operations/models/permissions.py`. استورد من التطبيق الصحيح صراحةً.
- **لا يوجد:** `Student`، `Teacher`، `TeacherAssignment`، `SchoolClass`. الإسنادُ `operations.SubjectClassAssignment` (للجدول) و`assessments.SubjectClassSetup` (للرصد).
- **تعليقاتٌ متقادمة في الشيفرة:** docstring `behavior/models.py` يقول «40 مخالفة» والدليلُ 41؛ وتعليقُ `Membership.role` يقول «ثمانيةٌ وعشرون دوراً» والخيارات 36. اعتمد على البيانات لا التعليق.

## أنماطٌ مضادّة
- البحثُ عن ميزةٍ بمجلّدٍ باسمها (`operations/` مساره `teacher/`، و`academic_management` مساره `academic/`) — ابدأ من `shschool/urls.py`.
- افتراضُ أنّ `staging` بيئةُ نشر؛ هو تطبيقُ الاستيراد.
- نقلُ اسمٍ من هذه الخريطة إلى الشيفرة دون `git grep` عليه.
