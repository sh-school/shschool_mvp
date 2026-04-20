---
name: schoolos-platform
description: |
  خريطة مشروع SchoolOS — منصة مدرسية قطرية حكومية (Django 5 + PostgreSQL + HTMX). تحتوي: خريطة الملفات الحقيقية، أسماء Models/Views/Services الفعلية، نظام التقييم القطري (الباقات P1-P4، فصل1=40 + فصل2=60 = 100)، الأدوار (20 دور × 5 مستويات)، قواعد العمل الحقيقية، والفخاخ التي يجب تجنبها. استخدمها تلقائياً عند أي عمل على SchoolOS.
---

# SchoolOS — خريطة المشروع الحقيقية

> هذه ليست موسوعة. هذه خريطة تقول لك **أين يوجد الشيء** و**ما الفخاخ**.
> لا تحتوي كود نظري — كل اسم هنا موجود فعلاً في المشروع.

---

## 1. الهيكل — أين يوجد ماذا

```
core/models/user.py        → CustomUser (المستخدم الموحّد — طالب ومعلم ومدير)
core/models/academic.py    → AcademicYear, ClassGroup, StudentEnrollment, ParentStudentLink
core/models/access.py      → Role (20 دور), Membership (ربط مستخدم بمدرسة ودور)
core/models/base.py        → TimeStampedModel, SoftDeleteModel, SchoolScopedModel
core/models/audit.py       → AuditLog, ConsentRecord, BreachReport, ErasureRequest

operations/models.py       → Subject, Session, StudentAttendance, ScheduleSlot, TeacherAbsence, SubstituteAssignment, AbsenceAlert, TimeSlotConfig, SubjectClassAssignment
assessments/models.py      → SubjectClassSetup, AssessmentPackage, Assessment, StudentAssessmentGrade, StudentSubjectResult, AnnualSubjectResult
behavior/models.py         → ViolationCategory (40 مخالفة — لائحة الشحانية), BehaviorInfraction, BehaviorPointRecovery
quality/models.py          → OperationalDomain, OperationalTarget, OperationalIndicator, OperationalProcedure, ProcedureEvidence
notifications/models.py    → NotificationLog, NotificationSettings, PushSubscription, InAppNotification, UserNotificationPreference
clinic/models.py           → HealthRecord (مشفّر Fernet), ClinicVisit
library/models.py          → LibraryBook, BookBorrowing, LibraryActivity
exam_control/models.py     → ExamSession, ExamRoom, ExamSupervisor, ExamSchedule, ExamIncident, ExamEnvelope, ExamGradeSheet
transport/models.py        → SchoolBus, BusRoute

reports/services.py        → ReportDataService, ExcelService (توليد Excel + PDF)
analytics/services.py      → KPI وإحصائيات
notifications/services.py  → إرسال Email/SMS/Push
notifications/hub.py       → مركز الإشعارات
```

---

## 2. الفخ الأول — لا يوجد Student model

**الطلاب والمعلمون والمدراء كلهم `CustomUser`.**

```python
# ✅ صحيح — هكذا تجد الطلاب:
students = CustomUser.objects.filter(
    memberships__role__name='student',
    memberships__school=school,
    memberships__is_active=True
)

# ❌ خطأ — لا يوجد:
Student.objects.filter(...)  # هذا Model غير موجود!
Teacher.objects.filter(...)  # هذا أيضاً غير موجود!
```

**التسجيل:** `StudentEnrollment` يربط `CustomUser` بـ `ClassGroup`.
**ولي الأمر:** `ParentStudentLink` يربط parent (CustomUser) بـ student (CustomUser).
**التحقق من الدور:** `user.role` → اسم الدور، `user.has_role('teacher')` → bool.

---

## 3. نظام التقييم — الأرقام الحقيقية

### التوزيع الذي يريده المالك (المستهدف):
```
الفصل الأول (40%):
  باقة 1 — منتصف ف1:  15%
  أعمال ف1:            5%
  باقة 2 — نهاية ف1:  20%

الفصل الثاني (60%):
  باقة 3 — منتصف ف2:  15%
  أعمال ف2:            5%
  باقة 4 — نهاية ف2:  40%

= 100%    حد النجاح: 60%
```

### ما في الكود حالياً (يحتاج تحديث):
```
الفصل الأول (40 درجة):
  P1 (أعمال مستمرة): 50% × 40 = 20
  P4 (اختبار نهائي): 50% × 40 = 20

الفصل الثاني (60 درجة):
  P1 (أعمال): 16.67% × 60 ≈ 10
  P3 (نصفي): 33.33% × 60 ≈ 20
  P4 (نهائي): 50% × 60 = 30

حد النجاح في الكود: 50 (المالك يريد: 60)
```

**⚠️ فخ:** الكود والمطلوب مختلفان. عند تعديل نظام التقييم، التزم بأرقام المالك (15/5/20/15/5/40) وحد نجاح 60%.

### Models الحقيقية:
```
SubjectClassSetup  → ربط مادة + فصل + معلم
AssessmentPackage  → الباقة (P1-P4) مع weight و semester_max_grade
Assessment         → تقييم فعلي (exam/quiz/homework/project/oral/practical/participation)
                     status: draft → published → graded → closed
StudentAssessmentGrade → درجة طالب في تقييم واحد (grade, is_absent, is_excused)
StudentSubjectResult   → نتيجة طالب في مادة لفصل (p1_score...p4_score, total, semester_max)
AnnualSubjectResult    → نتيجة سنوية (s1_total + s2_total = annual_total)
                         status: pass | fail | incomplete | second_round
                         letter_grade property: A+...F
```

---

## 4. الأدوار — 20 دور في 5 مستويات

```
Tier 1 (قيادة):     principal
Tier 2 (نواب):      vice_admin, vice_academic
Tier 3 (مشرفون):    coordinator, admin_supervisor
Tier 4 (موظفون):    teacher, social_worker, psychologist, academic_advisor,
                     ese_teacher, nurse, librarian, it_technician,
                     bus_supervisor, admin, secretary
Tier 5 (مستفيدون):  student, parent
Tier 0 (نظام):      platform_developer
```

**⚠️ فخ:** الدور ليس field في CustomUser — هو عبر `Membership.role` (FK → Role).
```python
user.role           # → اسم الدور (string) من active_membership
user.has_role('teacher')  # → True/False
user.is_leadership()      # → Tier 1+2
user.is_teacher()         # → teacher أو coordinator أو ese_teacher
```

---

## 5. Multi-Tenancy — كل شيء مربوط بـ School

معظم الـ models ترث `SchoolScopedModel` → لها field اسمه `school` (FK → School).
الـ middleware `SchoolPermissionMiddleware` + `RLSMiddleware` يضمنان العزل.

**⚠️ فخ:** لا تنسَ `school=request.user.school` في كل query.

---

## 6. السلوك — 40 مخالفة × 4 درجات (لائحة الشحانية)

```
ViolationCategory → degree (1-4), code ("1-01"..."4-13"), tags (فارغة — لم يطلبها المدير)
BehaviorInfraction → student, violation_category, level (1-4), escalation_step (0-4)
                     حقول خاصة بالدرجة 3: social_media_platform, digital_evidence_notes
                     حقول خاصة بالدرجة 4: security_referral_date, security_agency
BehaviorPointRecovery → التعزيز الإيجابي (استعادة نقاط)
```

---

## 7. الحضور

```
Session → حصة يومية (class_group + teacher + subject + date + times)
StudentAttendance → student + session + status (present/absent/late/excused)
                    excuse_type: medical/family/official/other
AbsenceAlert → تنبيه الغياب المتكرر (absence_count, status: pending/notified/resolved)
```

---

## 8. الإشعارات — 5 قنوات

```
القنوات: Email + SMS (Twilio) + Browser Push (VAPID) + In-App + WhatsApp
UserNotificationPreference → تفضيلات لكل مستخدم + quiet hours
InAppNotification → الإشعارات الداخلية مع priority (low/medium/high/urgent)
NotificationSettings → إعدادات المدرسة (Twilio keys مشفرة بـ Fernet)
```

---

## 9. التقارير — كيف تُبنى

```python
# reports/services.py
ReportDataService.get_student_report(student, school, year)   # تقرير طالب
ReportDataService.get_class_results(class_group, school, year) # نتائج صف
ReportDataService.get_attendance_report(...)                    # حضور
ReportDataService.get_behavior_report(...)                     # سلوك

ExcelService  # يولّد Excel مع:
              # - ألوان: maroon #8A1538 (header), #FDF2F5 (alt rows)
              # - RTL + frozen headers + auto-filter + sheet protection
              # - conditional formatting: أحمر < 50, أخضر للنجاح
              # - A4 portrait print setup
```

---

## 10. شجرة القرار — عند بناء ميزة

```
أين أضع الكود؟
├── Model جديد → في app المناسبة (assessments/ behavior/ operations/...)
├── Business logic → services.py (ليس في views أو models)
├── API endpoint → api/views.py + api/serializers.py + api/urls.py
├── صفحة HTML → views.py في الـ app + templates/{app}/
└── خلفية (async) → tasks.py (Celery)

أي مستخدم؟
├── لا يوجد Student model → CustomUser + role='student'
├── لا يوجد Teacher model → CustomUser + role='teacher'
└── الدور عبر Membership (FK Role) — ليس field مباشر

فلترة البيانات؟
├── دائماً school=request.user.school
├── المعلم: SubjectClassSetup.teacher=user أو TeacherAssignment
├── ولي الأمر: ParentStudentLink.parent=user → student
└── الطالب: مباشرة user

نظام التقييم؟
├── الأوزان المطلوبة: 15/5/20/15/5/40 (ليس ما في الكود حالياً)
├── حد النجاح المطلوب: 60% (الكود يقول 50)
├── AssessmentPackage.weight يحدد وزن كل باقة
└── AnnualSubjectResult.letter_grade → التقدير الحرفي
```

---

## 11. الأمان — ما يجب مراعاته

- **PDPPL (قانون حماية البيانات القطري 13/2016):** ConsentRecord + ErasureRequest + BreachReport
- **التشفير:** national_id مشفّر بـ Fernet، البحث عبر HMAC
- **2FA:** TOTP (totp_secret مشفّر)
- **RLS:** PostgreSQL Row Level Security + middleware
- **Soft Delete:** SoftDeleteModel → is_deleted + deleted_at (لا حذف فعلي لبيانات الطلاب)
- **CSP:** Content Security Policy middleware
- **Audit:** AuditLog + PermissionAuditLog
