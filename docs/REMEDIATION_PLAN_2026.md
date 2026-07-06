# خطة الإصلاح الشاملة لمنصة SchoolOS
## 2026-07-06 → 2026-10-06 (90 يوم)

---

## 1. ملخص تنفيذي

| المقياس | القيمة |
|---------|--------|
| عدد نقاط الضعف المكتشفة | 8 رئيسية + 7 مخاطر عملياتية |
| الأولويات P0 (حرجة) | 3 |
| الأولويات P1 (عالية) | 4 |
| الأولويات P2-P3 (متوسطة) | 8 |
| المدة الإجمالية | 90 يوم |
| الفريق المقترح | 5-6 مهندسين + 1 QA + 1 أمن |
| الميزانية المقترحة | ~250 ساعة هندسية |

**التقييم الحالي:** 75/100  
**التقييم المستهدف بعد الإصلاح:** 88-92/100

---

## 2. المرحلة الأولى: الأسبوع 1-4 (الأسبوع الأول)
### التركيز: إزالة المخاطر الحرجة

### P0.1: تسرب PII من خطأ Encryption
**الخطر:** `CustomUser.save()` قد لا تُحدّث حقول التشفير عند فشل Fernet  
**الأثر:** PII قد تبقى plaintext

#### الخطوات:
```python
# 1. إضافة validation في core/models/_crypto.py
def encrypt_field_with_fallback(value: str) -> str:
    """Fernet encryption مع guaranteed success أو استثناء"""
    if not value:
        return ""
    encrypted = encrypt_field(value)
    if not encrypted or encrypted == value:
        raise EncryptionError(f"Failed to encrypt {len(value)} bytes")
    return encrypted

# 2. تحديث CustomUser.save() بـ try/except واضح
def save(self, *args, **kwargs):
    if self.national_id:
        try:
            self.national_id_hmac = hmac_field(self.national_id)
            self.national_id_encrypted = encrypt_field_with_fallback(self.national_id)
        except EncryptionError as e:
            logger.critical(f"ENCRYPTION FAILED: user={self.id} field=national_id {e}")
            # Rollback: لا تحفظ إذا فشل التشفير
            raise  # ✅ بدل تجاهل الخطأ
    super().save(*args, **kwargs)

# 3. إضافة periodic check
# management/commands/check_unencrypted_pii.py
python manage.py check_unencrypted_pii --fix  # يُصحح missing encrypted fields

# 4. فحص في CI/CD
# .github/workflows/security-scan.yml
- name: Check for unencrypted PII
  run: python manage.py check_unencrypted_pii --fail-on-missing
```

**الملفات المتأثرة:**
- `core/models/_crypto.py` — إضافة `encrypt_field_with_fallback()`
- `core/models/user.py` — تحديث `save()` مع error handling
- `core/management/commands/check_unencrypted_pii.py` — أداة جديدة

**الاختبارات المطلوبة:**
- Test: encryption failure → raises exception
- Test: migration scenario (partial encrypted records)
- Test: periodic check finds all unencrypted fields

**مدة التنفيذ:** 4-5 ساعات  
**المسؤول:** مهندس أمن/backend  
**معيار النجاح:** ✅ كل migratio

n من unencrypted حقل يُسجَّل + يُرجع alert

---

### P0.2: RLS Middleware Context Leakage
**الخطر:** تحت high concurrency، context من user سابق قد يبقى في connection pool  
**الأثر:** data leak عابر (transient) لمستخدم آخر

#### الخطوات:
```python
# 1. تحسين core/middleware_rls.py
class RLSMiddleware:
    def __call__(self, request):
        context = self._context(request)
        self._apply(context)
        try:
            return self.get_response(request)
        finally:
            # ✅ ضمان إعادة تعيين حتى عند استثناء
            self._apply("")
            # ✅ إضافة verify قبل الخروج
            if not self._verify_reset():
                logger.error(f"RLS CONTEXT NOT RESET for {request.user}")
                raise RuntimeError("RLS safety check failed")

    def _verify_reset(self):
        """التحقق من إعادة تعيين السياق"""
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.current_school_id')")
            result = cursor.fetchone()[0]
            return result == ""

# 2. إضافة test تحت ضغط عالي
# tests/test_rls_concurrent.py
@pytest.mark.django_db
def test_rls_context_not_leaked_under_concurrency():
    # محاكاة 100 user متزامن
    # تحقق من عدم وجود تسرب contexts
    pass

# 3. إضافة monitoring
# في health check:
def rls_context_integrity_check():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM pg_stat_activity "
            "WHERE query LIKE '%app.current_school_id%' AND state='active'"
        )
    # Alert إذا كان العدد > threshold
```

**الملفات المتأثرة:**
- `core/middleware_rls.py` — تحسين reset logic + verify
- `tests/test_rls_concurrent.py` — test جديد

**مدة التنفيذ:** 3-4 ساعات  
**المسؤول:** مهندس backend/DB  
**معيار النجاح:** ✅ 1000 concurrent users بدون RLS context leak

---

### P0.3: Dead-Letter Queue للإشعارات الحرجة
**الخطر:** fail-silently في notification tasks يخفي أخطاء الشبكة  
**الأثر:** أولياء أمور لا يتلقون تنبيهات حرجة بصمت

#### الخطوات:
```python
# 1. تطبيق dead-letter queue في Celery
# shschool/celery.py
app.conf.task_routes = {
    'notifications.send_email': {'queue': 'critical', 'routing_key': 'critical'},
    'notifications.send_sms': {'queue': 'critical', 'routing_key': 'critical'},
}

# 2. تحديث send_email_task مع explicit error handling
@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def send_email_task(self, ...):
    try:
        ok, err = NotificationService.send_email(...)
        if not ok:
            # ✅ Distinguish transient vs permanent failures
            if "timeout" in err.lower() or "connection" in err.lower():
                raise self.retry(exc=Exception(err), countdown=60)  # Transient
            else:
                # Permanent: send to DLQ
                logger.error(f"PERMANENT FAILURE: {err}")
                save_to_dlq(task_id=self.request.id, error=err)
                return {"status": "dlq", "error": err}
    except Exception as e:
        logger.exception(f"Task failed: {e}")
        raise self.retry(exc=e)

# 3. نموذج DLQ جديد
class NotificationDLQ(models.Model):
    task_id = models.CharField(max_length=100)
    task_name = models.CharField(max_length=100)
    recipient = models.CharField(max_length=255)
    error_message = models.TextField()
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['created_at', 'resolved_at']),
        ]

# 4. Dashboard + Alert
# جديد: /notifications/dlq/ view
# Alert: if DLQ count > 10 في الساعة الأخيرة → Sentry alert
```

**الملفات المتأثرة:**
- `shschool/celery.py` — task routing
- `notifications/tasks.py` — improved error handling
- `notifications/models.py` — NotificationDLQ نموذج جديد
- `notifications/views.py` — DLQ dashboard

**مدة التنفيذ:** 6-7 ساعات  
**المسؤول:** مهندس backend/DevOps  
**معيار النجاح:** ✅ جميع reclassify notifications في DLQ تحت الساعة الأولى

---

## 3. المرحلة الثانية: الأسبوع 5-8
### التركيز: إصلاح المشاكل المعمارية + تحسين الجودة

### P1.1: Denormalization في BehaviorInfraction
**المشكلة:** `infraction.level` ينسخ من `violation_category.degree`، لا يُحدّث تاريخياً

#### الحل:
```python
# 1. إنشاء نموذج BehaviorEventLog جديد (Event Sourcing pattern)
class BehaviorEventLog(models.Model):
    """تاريخ كامل للمخالفة (append-only)"""
    EVENT_TYPES = [
        ('created', 'تم الإنشاء'),
        ('escalated', 'تم التصعيد'),
        ('resolved', 'تم الحل'),
        ('category_changed', 'تغيير الفئة'),
        ('reviewed', 'تم المراجعة'),
    ]
    
    infraction = models.ForeignKey(BehaviorInfraction, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    old_degree = models.IntegerField(null=True)
    new_degree = models.IntegerField(null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['timestamp']
        indexes = [models.Index(fields=['infraction', 'timestamp'])]

    def __str__(self):
        return f"{self.infraction.student} | {self.event_type} | {self.timestamp:%Y-%m-%d}"

# 2. Freeze degree عند الإنشاء (لا تسخ من category لاحقاً)
class BehaviorInfraction(models.Model):
    # ...existing...
    degree_frozen_at = models.DateTimeField(null=True, help_text="وقت تجميد الدرجة")
    
    def save(self, *args, **kwargs):
        is_new = not self.pk
        
        if is_new and self.violation_category:
            # ✅ First time: copy و freeze
            self.level = self.violation_category.degree
            
        # لا تُحدّث level لاحقاً من category!
        # إذا تطلب الأمر، استخدم management command
        
        super().save(*args, **kwargs)
        
        if is_new:
            BehaviorEventLog.objects.create(
                infraction=self,
                event_type='created',
                new_degree=self.level,
                recorded_by=self.reported_by
            )

# 3. Management command للعيب الماضي
# management/commands/fix_historical_degrees.py
def handle(self, *args, **options):
    """
    استرجاع degree التاريخي صحيح من ViolationCategory
    (Migration script، يعمل مرة واحدة فقط)
    """
    infractions = BehaviorInfraction.objects.all()
    fixed = 0
    
    for infr in infractions:
        if infr.violation_category and infr.violation_category.degree != infr.level:
            old = infr.level
            infr.level = infr.violation_category.degree
            infr.save(update_fields=['level'])
            
            BehaviorEventLog.objects.create(
                infraction=infr,
                event_type='category_changed',
                old_degree=old,
                new_degree=infr.level,
            )
            fixed += 1
    
    self.stdout.write(f"Fixed {fixed} infractions")

# 4. إضافة audit view
# behavior/views.py
def infraction_history(request, infraction_id):
    """عرض كامل تاريخ المخالفة"""
    infraction = get_object_or_404(BehaviorInfraction, id=infraction_id)
    events = BehaviorEventLog.objects.filter(infraction=infraction).order_by('timestamp')
    return render(request, 'behavior/history.html', {'events': events})
```

**الملفات المتأثرة:**
- `behavior/models.py` — freeze degree + BehaviorEventLog
- `behavior/management/commands/fix_historical_degrees.py` — أداة جديدة
- `behavior/views.py` — history endpoint

**مدة التنفيذ:** 5-6 ساعات  
**المسؤول:** مهندس backend  
**معيار النجاح:** ✅ جميع historic infractions لها correct degree في logs

---

### P1.2: IDOR في Reports Export
**المشكلة:** لا validation أن الطالب ينتمي للفصل قبل export

#### الحل:
```python
# 1. إنشاء permission decorator
# reports/permissions.py
def permission_required_student_in_class(view_func):
    """
    Decorator: verify أن student_id في URL ينتمي للفصل
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        student_id = kwargs.get('student_id')
        if not student_id:
            raise PermissionDenied("Missing student_id")
        
        school = request.user.get_school()
        student = get_object_or_404(CustomUser, id=student_id)
        
        # Check: student في school حالي
        enrollment = StudentEnrollment.objects.filter(
            student=student,
            class_group__school=school,
            is_active=True
        ).first()
        
        if not enrollment:
            logger.warning(f"IDOR attempt: user={request.user}, student={student_id}")
            raise PermissionDenied("Access denied to student data")
        
        # ✅ ADD to context
        request.student_enrollment = enrollment
        return view_func(request, *args, **kwargs)
    
    return wrapper

# 2. تطبيق على views
# reports/views.py
@login_required
@role_required("principal", "vice_academic", "teacher")
@permission_required_student_in_class
def student_result_pdf(request, student_id):
    """PDF: تقرير نتيجة طالب مفصّل"""
    enrollment = request.student_enrollment  # من decorator
    student = enrollment.student
    school = request.user.get_school()
    
    # الآن safe: student لا يملك أحد آخر
    ctx = ReportDataService.get_student_report(student, school, ...)
    ...

# 3. Test for IDOR
# tests/test_reports_idor.py
@pytest.mark.django_db
def test_reports_prevent_idor():
    teacher1 = create_user(role='teacher')
    teacher2 = create_user(role='teacher')
    
    student1 = create_student(class_=teacher1.class_group)
    student2 = create_student(class_=teacher2.class_group)
    
    # teacher1 حاول الوصول لـ student2 report
    response = teacher1_client.get(f'/reports/student/{student2.id}/pdf/')
    assert response.status_code == 403  # ✅ Denied
    
    # audit log
    audit = AuditLog.objects.filter(
        user=teacher1, action='view', model_name='StudentReport'
    ).latest('timestamp')
    assert audit.changes['denied_reason'] == 'student_not_in_class'
```

**الملفات المتأثرة:**
- `reports/permissions.py` — permission decorator جديد
- `reports/views.py` — تطبيق decorator على views
- `tests/test_reports_idor.py` — اختبار IDOR

**مدة التنفيذ:** 4-5 ساعات  
**المسؤول:** مهندس أمن/backend  
**معيار النجاح:** ✅ IDOR attempts مُحجوبة + audited

---

### P1.3: توحيد Coverage Gate
**المشكلة:** pyproject.toml يقول 60%، quality-gate.yml يقول 0 للـ CI السريع

#### الحل:
```yaml
# .github/workflows/quality-gate.yml (الجديد — موحد)
name: Quality Gate — بوابة الجودة (Unified)

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test-coverage:
    name: pytest + Coverage Gate
    runs-on: ubuntu-latest
    
    env:
      COVERAGE_THRESHOLD: 60  # Current floor
      COVERAGE_TARGET: 80     # Target for 6 months
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Run tests with coverage (parallel + incremental)
        run: |
          pytest tests/ -n auto --testmon \
            --cov=. \
            --cov-report=xml:coverage.xml \
            --cov-report=json:coverage.json \
            --cov-fail-under=${COVERAGE_THRESHOLD} \
            --junit-xml=test-results.xml
      
      - name: Enforce coverage gate
        run: |
          python3 -c "
          import json
          with open('coverage.json') as f:
              data = json.load(f)
          coverage = data['totals']['percent_covered']
          threshold = int('${{ env.COVERAGE_THRESHOLD }}')
          
          print(f'Coverage: {coverage:.1f}% (threshold: {threshold}%)')
          
          if coverage < threshold:
              print(f'::error::Coverage {coverage:.1f}% < {threshold}%')
              exit(1)
          elif coverage < 70:
              print(f'::warning::Coverage {coverage:.1f}% < target 80%')
          else:
              print('::notice::Coverage on track!')
          "
      
      - name: Upload coverage artifacts
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coverage-report
          path: |
            coverage.json
            coverage.xml
            htmlcov/

# pyproject.toml (الجديد — موحد)
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=. --cov-report=term-missing --cov-fail-under=60"

[tool.coverage.run]
branch = true
omit = [
    "*/migrations/*",
    "*/tests/*",
    "manage.py",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]
```

**وثيقة Roadmap:**
```markdown
# Coverage Improvement Roadmap

| الشهر | الهدف | الحالة |
|-------|-------|--------|
| يوليو 2026 | 60% (floor) | ✅ الحالي |
| سبتمبر 2026 | 70% | 🔄 Phase 1 |
| نوفمبر 2026 | 75% | 🔄 Phase 2 |
| ديسمبر 2026 | 80% (target) | 🎯 Final |

### Phase 1 (سبتمبر): إضافة tests لـ:
- assessments/services.py (حالياً 0%)
- exam_control/models.py (حالياً 15%)
- quality/services.py (حالياً 20%)

### Phase 2 (نوفمبر): إضافة tests لـ:
- behavior/services.py (حالياً 35%)
- reports/services.py (حالياً 40%)
- notifications/services.py (حالياً 45%)
```

**الملفات المتأثرة:**
- `.github/workflows/quality-gate.yml` — توحيد
- `pyproject.toml` — توحيد

**مدة التنفيذ:** 2-3 ساعات  
**المسؤول:** مهندس QA + lead  
**معيار النجاح:** ✅ CI موحد + roadmap واضح

---

### P1.4: Breach Reporting Status Flow
**المشكلة:** Status rollback من notified إلى assessing قد يُربك CDPP

#### الحل:
```python
# breach/models.py (محدّث)
class BreachReport(models.Model):
    STATUS = [
        ("discovered", "مكتشف"),
        ("assessing", "قيد التقييم"),
        ("notified", "تم الإشعار (NCSA 72h)"),
        ("acknowledged_by_cdpp", "تم التسليم لـ CDPP"),
        ("resolved", "محلول"),
        ("archived", "مؤرشف"),
    ]
    
    # ✅ Immutable state machine
    def can_transition_to(self, new_status):
        """التحقق من التحول القانوني"""
        valid_transitions = {
            "discovered": ["assessing"],
            "assessing": ["notified"],
            "notified": ["acknowledged_by_cdpp"],  # ✅ لا rollback
            "acknowledged_by_cdpp": ["resolved"],
            "resolved": ["archived"],
            "archived": [],  # نهائي
        }
        return new_status in valid_transitions.get(self.status, [])
    
    def transition_to(self, new_status, reason=""):
        """تحول آمن مع audit trail"""
        if not self.can_transition_to(new_status):
            raise BreachTransitionError(
                f"Cannot transition from {self.status} to {new_status}"
            )
        
        old_status = self.status
        self.status = new_status
        self.save(update_fields=['status'])
        
        # ✅ Log transition
        BreachStatusTransitionLog.objects.create(
            breach=self,
            from_status=old_status,
            to_status=new_status,
            reason=reason,
            transitioned_by=current_user,
            timestamp=timezone.now()
        )

# breach/models.py (جديد)
class BreachStatusTransitionLog(models.Model):
    """تاريخ كامل لتحولات الحالة"""
    breach = models.ForeignKey(BreachReport, on_delete=models.CASCADE, related_name='transitions')
    from_status = models.CharField(max_length=30)
    to_status = models.CharField(max_length=30)
    reason = models.TextField(blank=True)
    transitioned_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "transitions سجل"

# الـ API جديد
@require_http_methods(["POST"])
@permission_required('breach.change_breachreport')
def transition_breach_status(request, breach_id):
    """API endpoint آمن للتحول"""
    breach = get_object_or_404(BreachReport, id=breach_id)
    new_status = request.POST.get('status')
    reason = request.POST.get('reason', '')
    
    try:
        breach.transition_to(new_status, reason)
        return JsonResponse({'status': 'success', 'current': breach.status})
    except BreachTransitionError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
```

**مدة التنفيذ:** 3-4 ساعات  
**المسؤول:** مهندس backend + قانوني  
**معيار النجاح:** ✅ لا rollbacks غير مشروعة

---

## 4. المرحلة الثالثة: الأسبوع 9-13
### التركيز: تحسينات العمليات + Monitoring

### P2.1: EncryptionService Layer
```python
# core/services/encryption.py (جديد)
class EncryptionService:
    """مركز موحد لإدارة التشفير"""
    
    @staticmethod
    def encrypt_national_id(value: str) -> tuple[str, str]:
        """يُرجع (encrypted, hmac)"""
        if not value:
            return "", ""
        
        hmac = hmac_field(value)
        encrypted = encrypt_field(value)
        
        if not encrypted or encrypted == value:
            raise EncryptionFailureError("National ID encryption failed")
        
        return encrypted, hmac
    
    @staticmethod
    def encrypt_phone(value: str) -> tuple[str, str]:
        """يُرجع (encrypted, hmac)"""
        # نفس الشيء كأعلاه
        ...
    
    @staticmethod
    def verify_encryption(plaintext: str, encrypted: str, hmac: str) -> bool:
        """التحقق من سلامة التشفير"""
        expected_hmac = hmac_field(plaintext)
        decrypted = decrypt_field(encrypted)
        return (hmac == expected_hmac) and (decrypted == plaintext)
    
    @staticmethod
    def rotate_key():
        """تحديث FERNET_KEY دوري (migration script)"""
        old_key = settings.FERNET_KEY_OLD
        new_key = settings.FERNET_KEY
        
        # إعادة تشفير جميع الحقول بـ new key
        users = CustomUser.objects.exclude(national_id_encrypted="")
        for user in users:
            # Decrypt بـ old key
            plaintext = decrypt_field(user.national_id_encrypted, key=old_key)
            # Encrypt بـ new key
            user.national_id_encrypted = encrypt_field_with_fallback(plaintext)
            user.save()

# استخدام جديد:
# core/models/user.py
def save(self, *args, **kwargs):
    if self.national_id:
        try:
            enc, hmac = EncryptionService.encrypt_national_id(self.national_id)
            self.national_id_encrypted = enc
            self.national_id_hmac = hmac
        except EncryptionFailureError as e:
            logger.critical(f"Encryption failure: {e}")
            raise  # ✅ لا تحفظ بدون encryption
    super().save(*args, **kwargs)
```

**مدة التنفيذ:** 5-6 ساعات  
**معيار النجاح:** ✅ Key rotation test ناجح + لا PII leaks

---

### P2.2: Dead-Letter Queue Dashboard + Metrics
```python
# notifications/views.py
class NotificationDLQAdminView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'notifications.view_dlq'
    template_name = 'notifications/dlq_admin.html'
    paginate_by = 50
    
    def get_queryset(self):
        return NotificationDLQ.objects.filter(resolved_at__isnull=True).order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # الإحصائيات
        dlq_items = NotificationDLQ.objects.filter(resolved_at__isnull=True)
        last_hour = timezone.now() - timedelta(hours=1)
        
        ctx['stats'] = {
            'total_pending': dlq_items.count(),
            'last_hour': dlq_items.filter(created_at__gte=last_hour).count(),
            'by_task': dlq_items.values('task_name').annotate(count=Count('id')),
            'critical': dlq_items.filter(attempts__gte=3).count(),
        }
        
        return ctx

# Prometheus metrics
from django_prometheus.utils import CounterEnum

class NotificationMetrics(CounterEnum):
    failed_notifications = 'notifications_failed_total', 'Failed notifications'
    dlq_items = 'notifications_dlq_total', 'Items in DLQ'
    retry_count = 'notifications_retry_total', 'Retry attempts'
    resolution_time = 'notifications_resolution_seconds', 'Time from DLQ to resolution'

# في tasks.py
def save_to_dlq(task_id, error):
    dlq = NotificationDLQ.objects.create(...)
    NotificationMetrics.dlq_items.inc()
    
    # Alert إذا تجاوزت threshold
    if NotificationDLQ.objects.filter(resolved_at__isnull=True).count() > 10:
        send_sentry_alert("DLQ threshold exceeded")
```

**مدة التنفيذ:** 4-5 ساعات  
**معيار النجاح:** ✅ Dashboard يعرض DLQ + alerts automatic

---

## 5. المرحلة الرابعة: الأسبوع 14-18
### التركيز: Testing + Documentation

### P2.3: Comprehensive Testing Suite
```bash
# أهداف التغطية الجديدة
- core/models/: 90% (الحالي 75%)
- notifications/: 85% (الحالي 60%)
- behavior/: 80% (الحالي 50%)
- assessments/: 75% (الحالي 40%)

# مدة التنفيذ: 20-25 ساعة (5-6 أيام كاملة)
```

---

## 6. خطة المراقبة والمؤشرات

| المؤشر | الهدف | الحد الأدنى | الحد الأقصى |
|---------|-------|----------|-----------|
| PII encryption sweep failure | 0/day | 0 | 1 |
| RLS context leaks | 0/day | 0 | 0 |
| DLQ notifications | <5/day | 0 | 10 |
| IDOR attempts blocked | monitored | 0 | ∞ |
| Coverage % | 80% (هدف) | 60% | 95% |
| Breach transition violations | 0/month | 0 | 0 |

---

## 7. Matrix Feuille de Route بـ Dependencies

```
Week 1-4 (الأولويات P0):
├── P0.1: PII encryption fix
├── P0.2: RLS context reset
└── P0.3: Dead-letter queue
    ↓ (يعتمد عليهم P1.3)
Week 5-8 (الأولويات P1):
├── P1.1: BehaviorEventLog (freeze degree)
├── P1.2: IDOR permission decorator
├── P1.3: Coverage gate unification
└── P1.4: Breach status FSM
Week 9-13 (الأولويات P2):
├── P2.1: EncryptionService layer
├── P2.2: DLQ dashboard
└── P2.3: Testing suite expansion
```

---

## 8. الموارد والفريق المقترح

| الدور | العدد | الساعات/الأسبوع | الملاحظات |
|--------|-------|----------------|----------|
| Backend Engineer | 3 | 40 | focus: core fixes |
| Security Engineer | 1 | 20 | focus: encryption + IDOR |
| QA/Testing | 1 | 30 | focus: testing suite |
| DevOps/SRE | 1 | 20 | focus: monitoring + deployment |
| Lead/Architect | 1 | 10 | review + coordination |

**إجمالي الساعات:** ~210 ساعة (≈ 5-6 أسابيع عمل كامل)

---

## 9. معايير النجاح النهائي

✅ **قبل الإصدار النهائي:**

- [ ] جميع اختبارات P0 pass
- [ ] RLS test تحت 1000 concurrent users — PASS
- [ ] DLQ-free for 7 consecutive days
- [ ] ZERO uncaught IDOR attempts في last 14 days
- [ ] Coverage ≥ 70% (على الطريق للـ 80%)
- [ ] Breach transition log validated
- [ ] EncryptionService في الإنتاج
- [ ] Security audit passed
- [ ] QA sign-off for deployment

---

## 10. المخاطر والتعويضات

| المخاطر | الاحتمال | الجاهزية |
|--------|---------|---------|
| Migration failure on encryption | 10% | Rollback plan + drills الأسبوع 1 |
| Test suite explosion > 2 hours | 30% | Parallel execution + split CI jobs |
| Breach incident أثناء إصلاحات | 5% | حالات استثنائية معالجة يدوياً |

---

**الوثيقة آخر تحديث:** 2026-07-06  
**صاحب الخطة:** Lead Architect  
**آخر مراجعة:** 2026-07-06


