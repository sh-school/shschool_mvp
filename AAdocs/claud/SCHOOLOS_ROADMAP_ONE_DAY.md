# 🗺️ خارطة الطريق الكاملة — SchoolOS Qatar v3
## إصلاح جميع الثغرات في يوم واحد

**التاريخ:** 19 مارس 2026  
**المستوى:** تقني تنفيذي  
**الوقت الإجمالي المقدر:** 7–9 ساعات  
**المطلوب:** مطور واحد + صلاحيات Git

---

## 📋 خريطة اليوم الكاملة

| الوقت | المرحلة | الثغرات | الخطورة |
|-------|---------|---------|---------|
| 08:00–09:00 | 🔴 المرحلة 1 | بيانات Git + SECRET_KEY | حرج جداً |
| 09:00–10:00 | 🔴 المرحلة 2 | FERNET_KEY + seed تلقائي | حرج جداً |
| 10:00–11:30 | 🔴 المرحلة 3 | Logout CSRF + Race Condition + totp | حرج |
| 11:30–13:00 | 🟡 المرحلة 4 | AuditLog + Rate Limiting + CSP | مهم |
| 13:00–14:00 | استراحة | — | — |
| 14:00–15:30 | 🟡 المرحلة 5 | N+1 في Quality + NGINX | مهم |
| 15:30–17:00 | 🔵 المرحلة 6 | Consent عند أول دخول + models_new | تحسين |
| 17:00–18:00 | ✅ المرحلة 7 | اختبار شامل + checklist | تحقق |

---

---

# 🔴 المرحلة 1 — 08:00 إلى 09:00
## البيانات الحقيقية في Git + SECRET_KEY المكشوف

> **الخطورة:** انتهاك PDPPL مباشر وقابل للملاحقة. يجب إصلاحه قبل أي شيء آخر.

---

### 1.1 — حذف البيانات الحقيقية من Git نهائياً

**المشكلة:** مجلد `data/` يحتوي 742 طالباً + 126 موظفاً بأرقام وطنية حقيقية وليس موجوداً في `.gitignore`.

#### الخطوة A — أضف `data/` إلى `.gitignore` فوراً

افتح ملف `.gitignore` وأضف هذا السطر:

```gitignore
# ── بيانات حقيقية — يُمنع رفعها للـ Git ──────────────────
data/
*.csv
```

#### الخطوة B — احذف المجلد من تتبع Git (مع الاحتفاظ بالملفات محلياً)

```bash
# إخبار Git بإلغاء تتبع المجلد دون حذفه من القرص
git rm -r --cached data/

# تحقق أن الملفات لا تزال موجودة محلياً
ls data/

# commit الإزالة
git add .gitignore
git commit -m "security: remove real student/staff data from git tracking [PDPPL]"
```

#### الخطوة C — مسح البيانات من تاريخ Git كاملاً

> ⚠️ هذا يُعيد كتابة تاريخ الـ repository. أعلم فريقك أولاً.

```bash
# تثبيت الأداة
pip install git-filter-repo

# مسح المجلد من كل التاريخ
git filter-repo --path data/ --invert-paths --force

# رفع إجباري (force push)
git push origin --force --all
git push origin --force --tags
```

#### الخطوة D — تحقق أن الملفات اختفت من التاريخ

```bash
# يجب أن يعود هذا فارغاً
git log --all --full-history -- "data/*.csv"
```

---

### 1.2 — إصلاح SECRET_KEY المكشوف في docker-compose.yml

**المشكلة:** `docker-compose.yml` يكتب SECRET_KEY وDB_PASSWORD بشكل صريح داخل الملف.

#### الخطوة A — أنشئ ملف `.env` محلي

```bash
# أنشئ ملف .env من النموذج
cp .env.example .env
```

ثم عدّل `.env` وأضف قيماً حقيقية:

```bash
# .env
SECRET_KEY=أدخل-هنا-مفتاحاً-عشوائياً-طويلاً-50-حرفاً-على-الأقل
DB_PASSWORD=كلمة-مرور-قوية-للقاعدة
DEBUG=False
```

لتوليد SECRET_KEY آمن:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

#### الخطوة B — عدّل `docker-compose.yml` لاستخدام `.env`

```yaml
# docker-compose.yml — قبل الإصلاح ❌
environment:
  SECRET_KEY: "docker-dev-secret-key-shschool-2025-change-in-prod"
  DB_PASSWORD: shschool_pass
```

```yaml
# docker-compose.yml — بعد الإصلاح ✅
env_file:
  - .env
# احذف كل القيم الصريحة من environment
```

#### الخطوة C — تحقق أن `.env` في `.gitignore`

```bash
grep ".env" .gitignore
# يجب أن يظهر: .env
```

---

---

# 🔴 المرحلة 2 — 09:00 إلى 10:00
## FERNET_KEY + مشكلة Seed التلقائي في Dockerfile

---

### 2.1 — تفعيل تشفير البيانات الصحية (FERNET_KEY)

**المشكلة:** كود التشفير موجود لكنه صامت تماماً عند غياب المفتاح — البيانات الصحية تُخزَّن كنص صريح.

#### الخطوة A — توليد المفتاح وإضافته للـ `.env`

```bash
# في terminal:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# مثال على الناتج: NZhNVQG9sI4KptgMtbxBiGGCFd_lshtpsm05gSuWCmg=
```

أضف الناتج إلى `.env`:

```bash
# .env
FERNET_KEY=NZhNVQG9sI4KptgMtbxBiGGCFd_lshtpsm05gSuWCmg=
```

#### الخطوة B — اجعل التشفير إلزامياً (لا صامتاً)

افتح `core/models.py` وعدّل دالة `_get_fernet()`:

```python
# core/models.py — قبل الإصلاح ❌
def _get_fernet():
    if not _FERNET_AVAILABLE:
        return None
    key = getattr(settings, 'FERNET_KEY', None)
    if not key:
        return None  # ← يعود None بصمت — خطر!
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None
```

```python
# core/models.py — بعد الإصلاح ✅
import logging
logger = logging.getLogger(__name__)

def _get_fernet():
    """احصل على Fernet — يرمي استثناء إذا لم يكن المفتاح مضبوطاً في الإنتاج"""
    if not _FERNET_AVAILABLE:
        raise RuntimeError(
            "حزمة cryptography غير مثبتة. شغّل: pip install cryptography"
        )
    key = getattr(settings, 'FERNET_KEY', None)
    if not key:
        if settings.DEBUG:
            # في التطوير: تحذير فقط
            logger.warning(
                "⚠️ FERNET_KEY غير مضبوط — البيانات الصحية بدون تشفير. "
                "أضف FERNET_KEY إلى .env"
            )
            return None
        else:
            # في الإنتاج: خطأ صريح يوقف التطبيق
            raise ImproperlyConfigured(
                "FERNET_KEY مطلوب في بيئة الإنتاج (PDPPL). "
                "أضفه إلى .env: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        raise ImproperlyConfigured(f"FERNET_KEY غير صالح: {e}")
```

أضف الاستيراد في أعلى الملف:

```python
from django.core.exceptions import ImproperlyConfigured
```

#### الخطوة C — إعادة تشفير البيانات الموجودة (migration script)

شغّل هذا مرة واحدة فقط بعد تفعيل المفتاح:

```bash
# في shell Django
python manage.py shell
```

```python
# في Django shell
from core.models import HealthRecord, encrypt_field

records = HealthRecord.objects.all()
count = 0
for record in records:
    changed = False
    # إذا الحقل يبدأ بـ gAAAAA فهو مشفر بالفعل
    if record.allergies and not record.allergies.startswith('gAAAAA'):
        record.allergies = encrypt_field(record.allergies)
        changed = True
    if record.chronic_diseases and not record.chronic_diseases.startswith('gAAAAA'):
        record.chronic_diseases = encrypt_field(record.chronic_diseases)
        changed = True
    if record.medications and not record.medications.startswith('gAAAAA'):
        record.medications = encrypt_field(record.medications)
        changed = True
    if changed:
        record.save(update_fields=['allergies', 'chronic_diseases', 'medications'])
        count += 1

print(f"✅ تم تشفير {count} سجل صحي")
```

---

### 2.2 — إصلاح مشكلة Seed التلقائي في Dockerfile

**المشكلة:** `Dockerfile` يُشغّل `python manage.py seed` عند كل restart — يُحاول إدخال البيانات الحقيقية من CSV عند كل إعادة تشغيل.

#### الخطوة A — عدّل `Dockerfile`

```dockerfile
# Dockerfile — قبل الإصلاح ❌
CMD ["sh", "-c", "python manage.py migrate --noinput && \
                  python manage.py collectstatic --noinput && \
                  python manage.py seed && \
                  gunicorn shschool.wsgi:application --bind 0.0.0.0:8000 --workers 3"]
```

```dockerfile
# Dockerfile — بعد الإصلاح ✅
CMD ["sh", "-c", "python manage.py migrate --noinput && \
                  python manage.py collectstatic --noinput && \
                  gunicorn shschool.wsgi:application \
                    --bind 0.0.0.0:8000 \
                    --workers 3 \
                    --timeout 120"]
```

> **ملاحظة:** الـ seed يجب أن يُشغَّل يدوياً مرة واحدة فقط عبر: `docker compose exec web python manage.py full_seed`

#### الخطوة B — أضف تعليقاً في `full_seed.py` يوضح أنه يستخدم بيانات وهمية فقط

افتح `core/management/commands/full_seed.py` وعدّل التعليق في الأعلى:

```python
"""
full_seed — حقن بيانات للاختبار

⚠️  تحذير: هذا الأمر يستخدم ملفات CSV من مجلد data/
    تأكد أن data/ يحتوي على بيانات وهمية (anonymized) فقط.
    لا تُشغّل هذا الأمر في بيئة الإنتاج على بيانات حقيقية.

تشغيل يدوي فقط:
    docker compose exec web python manage.py full_seed
    python manage.py full_seed --reset
"""
```

---

---

# 🔴 المرحلة 3 — 10:00 إلى 11:30
## Logout CSRF + Race Condition + totp_secret غير مشفر

---

### 3.1 — إصلاح ثغرة Logout CSRF

**المشكلة:** `logout_view` يقبل GET requests — أي موقع خارجي يستطيع تسجيل خروج أي مستخدم.

افتح `core/views_auth.py`:

```python
# core/views_auth.py — قبل الإصلاح ❌
@login_required
def logout_view(request):
    logout(request)
    return redirect("login")
```

```python
# core/views_auth.py — بعد الإصلاح ✅
from django.views.decorators.http import require_POST

@login_required
@require_POST  # ← يرفض كل طلب ليس POST
def logout_view(request):
    """تسجيل خروج آمن — يقبل POST فقط مع CSRF token"""
    logout(request)
    return redirect("login")
```

تأكد أن قالب الخروج يستخدم form بـ POST وليس رابطاً:

```html
<!-- في أي قالب يحتوي زر خروج -->
<!-- قبل ❌ -->
<a href="{% url 'logout' %}">خروج</a>

<!-- بعد ✅ -->
<form method="post" action="{% url 'logout' %}" style="display:inline;">
    {% csrf_token %}
    <button type="submit" class="btn-logout">خروج</button>
</form>
```

---

### 3.2 — إصلاح Race Condition في عداد المحاولات الفاشلة

**المشكلة:** عند workers متعددة لـ Gunicorn، طلبان متزامنان يقرآن نفس القيمة ويفشلان في الإحصاء الصحيح — الحساب لا يُقفل كما ينبغي.

افتح `core/views_auth.py`:

```python
# core/views_auth.py — قبل الإصلاح ❌
try:
    u = CustomUser.objects.get(national_id=national_id)
    u.failed_login_attempts += 1          # ← قراءة + زيادة في Python = race condition
    if u.failed_login_attempts >= 5:
        u.locked_until = timezone.now() + timedelta(minutes=15)
        messages.error(request, "تم قفل الحساب لمدة 15 دقيقة بسبب المحاولات المتكررة.")
    else:
        remaining = 5 - u.failed_login_attempts
        messages.error(request, f"بيانات غير صحيحة. {remaining} محاولة متبقية.")
    u.save(update_fields=["failed_login_attempts", "locked_until"])
except CustomUser.DoesNotExist:
    messages.error(request, "الرقم الوطني أو كلمة المرور غير صحيحة")
```

```python
# core/views_auth.py — بعد الإصلاح ✅
from django.db.models import F
from django.db import transaction

try:
    with transaction.atomic():
        # زيادة atomic — آمنة مع workers متعددة
        updated = CustomUser.objects.filter(
            national_id=national_id
        ).update(
            failed_login_attempts=F('failed_login_attempts') + 1
        )

        if updated:
            # إعادة قراءة القيمة المحدثة
            u = CustomUser.objects.get(national_id=national_id)
            if u.failed_login_attempts >= 5:
                u.locked_until = timezone.now() + timedelta(minutes=15)
                u.save(update_fields=["locked_until"])
                messages.error(
                    request,
                    "تم قفل الحساب لمدة 15 دقيقة بسبب المحاولات المتكررة."
                )
            else:
                remaining = 5 - u.failed_login_attempts
                messages.error(
                    request,
                    f"بيانات غير صحيحة. {remaining} محاولة متبقية."
                )
except CustomUser.DoesNotExist:
    messages.error(request, "الرقم الوطني أو كلمة المرور غير صحيحة")
```

---

### 3.3 — تشفير totp_secret في قاعدة البيانات

**المشكلة:** `totp_secret` مُخزَّن كنص صريح رغم أن التعليق يقول "مُشفَّر". من يصل لقاعدة البيانات يستطيع انتحال هوية أي مدير.

افتح `core/models.py` وعدّل نموذج `CustomUser`:

```python
# core/models.py — قبل الإصلاح ❌
totp_secret = models.CharField(
    max_length=64, blank=True,
    verbose_name="مفتاح 2FA",
    help_text="مفتاح TOTP للمصادقة الثنائية — مُشفَّر"  # ← الكلام كذب!
)
```

```python
# core/models.py — بعد الإصلاح ✅
totp_secret = models.CharField(
    max_length=200, blank=True,  # ← زيادة الطول لاستيعاب التشفير
    verbose_name="مفتاح 2FA",
    help_text="مفتاح TOTP مُشفَّر بـ Fernet"
)

def get_totp_secret(self):
    """فك تشفير TOTP secret للاستخدام"""
    return decrypt_field(self.totp_secret)

def set_totp_secret(self, raw_secret):
    """تشفير TOTP secret قبل الحفظ"""
    self.totp_secret = encrypt_field(raw_secret)
```

ثم عدّل `views_auth.py` في أماكن استخدام `totp_secret`:

```python
# core/views_auth.py — عدّل دالة setup_2fa

# قبل ❌
if not user.totp_secret:
    user.totp_secret = pyotp.random_base32()
    user.save(update_fields=["totp_secret"])
totp = pyotp.TOTP(user.totp_secret)

# بعد ✅
if not user.totp_secret:
    raw_secret = pyotp.random_base32()
    user.set_totp_secret(raw_secret)
    user.save(update_fields=["totp_secret"])
totp = pyotp.TOTP(user.get_totp_secret())
```

```python
# core/views_auth.py — عدّل دالة verify_2fa

# قبل ❌
totp = pyotp.TOTP(user.totp_secret)

# بعد ✅
totp = pyotp.TOTP(user.get_totp_secret())
```

```python
# core/views_auth.py — عدّل دالة disable_2fa

# قبل ❌
if user.totp_secret:
    totp = pyotp.TOTP(user.totp_secret)

# بعد ✅
raw = user.get_totp_secret()
if raw:
    totp = pyotp.TOTP(raw)
```

#### Migration لزيادة طول الحقل

```bash
python manage.py makemigrations core --name="encrypt_totp_secret"
python manage.py migrate
```

#### Script لإعادة تشفير بيانات الـ totp الموجودة

```python
# في Django shell
from core.models import CustomUser, encrypt_field, decrypt_field

users_with_totp = CustomUser.objects.exclude(totp_secret='')
count = 0
for user in users_with_totp:
    # إذا لم يكن مشفراً بعد (لا يبدأ بـ gAAAAA)
    if not user.totp_secret.startswith('gAAAAA'):
        raw = user.totp_secret
        user.set_totp_secret(raw)
        user.save(update_fields=['totp_secret'])
        count += 1

print(f"✅ تم تشفير {count} مفتاح TOTP")
```

---

---

# 🟡 المرحلة 4 — 11:30 إلى 13:00
## AuditLog + Rate Limiting + CSP Headers

---

### 4.1 — إصلاح AuditLog: تسجيل المستخدم الفعلي في Signals

**المشكلة:** `core/signals.py` يُرسل `user=None` في كل العمليات التلقائية — نصف السجلات لا تعرف من قام بالعملية.

افتح `core/signals.py` وأضف Context Variable:

```python
# core/signals.py — بعد الإصلاح ✅
"""
core/signals.py
تسجيل تلقائي للعمليات الحساسة مع ربط المستخدم الفعلي
"""
from contextvars import ContextVar
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out

# متغير سياق — يُضبط في Middleware لكل request
_current_user: ContextVar = ContextVar('current_user', default=None)
_current_request: ContextVar = ContextVar('current_request', default=None)


def get_current_user():
    return _current_user.get(None)


def get_current_request():
    return _current_request.get(None)


def _log(model_name, action, instance, changes=None):
    try:
        from core.models import AuditLog
        user    = get_current_user()
        request = get_current_request()
        ip = ua = ''
        if request:
            ip = request.META.get('REMOTE_ADDR', '')
            ua = request.META.get('HTTP_USER_AGENT', '')[:300]

        AuditLog.objects.create(
            user=user,                                    # ✅ المستخدم الفعلي
            action=action,
            model_name=model_name,
            object_id=str(instance.pk),
            object_repr=str(instance)[:300],
            changes=changes,
            school=getattr(instance, 'school', None),
            ip_address=ip or None,
            user_agent=ua,
        )
    except Exception:
        pass


# باقي الـ receivers تبقى كما هي
@receiver(post_save, sender='core.HealthRecord')
def audit_health_record(sender, instance, created, **kwargs):
    _log('HealthRecord', 'create' if created else 'update', instance)

# ... باقي الـ receivers بدون تغيير
```

الآن أضف Middleware يضبط المستخدم الحالي:

```python
# core/middleware.py — أضف هذا الـ Middleware في نهاية الملف

class CurrentUserMiddleware:
    """يُخزّن المستخدم الحالي في Context Variable للـ AuditLog"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from core.signals import _current_user, _current_request
        token_user    = _current_user.set(
            request.user if request.user.is_authenticated else None
        )
        token_request = _current_request.set(request)
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token_user)
            _current_request.reset(token_request)
```

أضفه إلى `settings/base.py`:

```python
# shschool/settings/base.py
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SchoolPermissionMiddleware",
    "core.middleware.CurrentUserMiddleware",  # ✅ جديد — يجب أن يكون بعد AuthenticationMiddleware
]
```

---

### 4.2 — إضافة Rate Limiting

**المشكلة:** لا يوجد أي حماية من Brute Force على الـ APIs أو صفحة الدخول.

#### الخطوة A — ثبّت django-ratelimit

```bash
pip install django-ratelimit
```

أضفه إلى `requirements.txt`:

```
django-ratelimit>=4.1.0
```

#### الخطوة B — طبّقه على صفحة الدخول

```python
# core/views_auth.py
from django_ratelimit.decorators import ratelimit

@ratelimit(key='ip', rate='10/m', method='POST', block=True)
def login_view(request):
    # ... الكود الموجود بدون تغيير
```

#### الخطوة C — طبّقه على الـ API endpoints

افتح `operations/api_views.py`:

```python
# operations/api_views.py
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

@method_decorator(ratelimit(key='user', rate='60/m', block=True), name='dispatch')
class SessionListView(generics.ListAPIView):
    # ... الكود الموجود

@method_decorator(ratelimit(key='user', rate='60/m', block=True), name='dispatch')
class AttendanceListView(generics.ListAPIView):
    # ... الكود الموجود
```

#### الخطوة D — أضف Rate Limiting للـ DRF في الإعدادات

```python
# shschool/settings/base.py — عدّل REST_FRAMEWORK
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # ✅ جديد
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/minute",    # زوار غير مسجلين
        "user": "200/minute",   # مستخدمون مسجلون
    },
}
```

---

### 4.3 — إضافة Content Security Policy (CSP)

**المشكلة:** لا يوجد CSP header — النظام عُرضة لهجمات XSS.

#### الخطوة A — ثبّت django-csp

```bash
pip install django-csp
```

أضفه إلى `requirements.txt`:

```
django-csp>=3.8
```

#### الخطوة B — أضف Middleware والإعدادات

```python
# shschool/settings/base.py

MIDDLEWARE = [
    # ... الموجود
    "csp.middleware.CSPMiddleware",  # ✅ أضفه
]

# ── Content Security Policy ───────────────────────────────
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC  = (
    "'self'",
    "'unsafe-inline'",   # مطلوب لـ HTMX و Alpine.js — يمكن تضييقه لاحقاً
    "https://cdn.jsdelivr.net",
    "https://cdnjs.cloudflare.com",
)
CSP_STYLE_SRC   = (
    "'self'",
    "'unsafe-inline'",   # مطلوب للـ Tailwind الـ inline
    "https://fonts.googleapis.com",
    "https://cdn.jsdelivr.net",
)
CSP_FONT_SRC    = ("'self'", "https://fonts.gstatic.com",)
CSP_IMG_SRC     = ("'self'", "data:", "blob:",)
CSP_CONNECT_SRC = ("'self'",)
CSP_FRAME_SRC   = ("'none'",)   # لا iframes من مصادر خارجية
CSP_OBJECT_SRC  = ("'none'",)   # لا Flash أو Plugins
```

---

---

# 🟡 المرحلة 5 — 14:00 إلى 15:30
## N+1 في Quality Views + إضافة NGINX

---

### 5.1 — إصلاح N+1 في quality/views.py

**المشكلة:** حلقة مزدوجة `for target → for indicator` تولّد مئات الاستعلامات لصفحة واحدة.

افتح `quality/views.py` ودالة `domain_detail`:

```python
# quality/views.py — قبل الإصلاح ❌
targets = OperationalTarget.objects.filter(
    domain=domain
).order_by("number")

if status_filter or executor_filter:
    for target in targets:
        for indicator in target.indicators.all():  # ← N queries
            indicator._filtered_procedures = indicator.procedures.filter(...)  # ← N*M queries
```

```python
# quality/views.py — بعد الإصلاح ✅
from django.db.models import Prefetch

# بناء فلتر الإجراءات
proc_filters = {}
if status_filter:
    proc_filters['status'] = status_filter
if executor_filter:
    proc_filters['executor_norm__icontains'] = executor_filter

# prefetch كل شيء في 3 queries بدلاً من مئات
procedures_qs = OperationalProcedure.objects.filter(
    school=school, **proc_filters
).select_related('indicator')

indicators_qs = OperationalIndicator.objects.prefetch_related(
    Prefetch(
        'procedures',
        queryset=OperationalProcedure.objects.filter(
            school=school, **proc_filters
        ),
        to_attr='_filtered_procedures'
    )
)

targets = OperationalTarget.objects.filter(
    domain=domain
).prefetch_related(
    Prefetch('indicators', queryset=indicators_qs)
).order_by("number")
```

---

### 5.2 — إضافة NGINX كـ Reverse Proxy

**المشكلة:** Gunicorn مكشوف مباشرة للإنترنت — لا حماية، لا static files serving، لا SSL termination.

#### الخطوة A — أنشئ ملف `nginx.conf`

```nginx
# nginx/nginx.conf
upstream schoolos_backend {
    server web:8000;
}

server {
    listen 80;
    server_name schoolos.qa www.schoolos.qa;

    # إعادة التوجيه لـ HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name schoolos.qa www.schoolos.qa;

    # ── SSL (ضع شهاداتك هنا) ──────────────────────────────
    ssl_certificate     /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # ── Security Headers ──────────────────────────────────
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # ── Static Files ──────────────────────────────────────
    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location /media/ {
        alias /app/media/;
        expires 7d;
        # ⚠️ تأكد أن المستخدمين لا يستطيعون رفع ملفات تنفيذية
        add_header Content-Disposition "attachment";
    }

    # ── Application ───────────────────────────────────────
    location / {
        proxy_pass         http://schoolos_backend;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;

        # حماية من الطلبات الكبيرة (رفع ملفات)
        client_max_body_size 10M;
    }

    # ── Rate Limiting على صفحة الدخول ────────────────────
    location /auth/login/ {
        limit_req zone=login burst=10 nodelay;
        proxy_pass http://schoolos_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# تعريف Rate Limiting Zone
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
```

#### الخطوة B — عدّل `docker-compose.prod.yml`

```yaml
# docker-compose.prod.yml — أضف nginx service

services:
  nginx:
    image: nginx:alpine
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./staticfiles:/app/staticfiles:ro
      - ./media:/app/media:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - web
    networks:
      - external
      - internal

  # عدّل web — لا يكشف port مباشرة
  web:
    # ... نفس الإعدادات
    # احذف:  ports: ["8000:8000"]
    expose:
      - "8000"
    networks:
      - internal
```

#### الخطوة C — أضف هذا لـ settings/production.py

```python
# shschool/settings/production.py
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```

---

---

# 🔵 المرحلة 6 — 15:30 إلى 17:00
## Consent إلزامي عند أول دخول + تنظيف الكود

---

### 6.1 — جعل Consent إلزامياً عند أول دخول ولي الأمر

**المشكلة:** صفحة الموافقة موجودة لكنها اختيارية — ولي الأمر يُسجَّل ويصل للبيانات بدون موافقة.

#### الخطوة A — أضف حقل `consent_given` للمستخدم

```python
# في core/models.py — أضف لـ CustomUser
consent_given_at = models.DateTimeField(
    null=True, blank=True,
    verbose_name="تاريخ إعطاء الموافقة",
    help_text="إذا كان None، ولي الأمر لم يوافق بعد"
)
```

```bash
python manage.py makemigrations core --name="add_consent_given_at"
python manage.py migrate
```

#### الخطوة B — أضف Middleware يُجبر ولي الأمر على الموافقة

```python
# core/middleware.py — أضف هذا الـ Middleware

class ParentConsentMiddleware:
    """يُجبر ولي الأمر على إعطاء الموافقة قبل الوصول لأي صفحة"""

    EXEMPT_PATHS = [
        '/auth/',
        '/parents/consent/',
        '/static/',
        '/media/',
        '/admin/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and request.user.get_role() == 'parent'
            and request.user.consent_given_at is None
            and not any(request.path.startswith(p) for p in self.EXEMPT_PATHS)
        ):
            from django.shortcuts import redirect
            return redirect('/parents/consent/')

        return self.get_response(request)
```

أضفه للـ settings بعد `SchoolPermissionMiddleware`:

```python
MIDDLEWARE = [
    # ... الموجود
    "core.middleware.SchoolPermissionMiddleware",
    "core.middleware.CurrentUserMiddleware",
    "core.middleware.ParentConsentMiddleware",  # ✅ جديد
]
```

#### الخطوة C — عدّل `consent_view` ليُحدّث `consent_given_at`

```python
# parents/views.py — في دالة consent_view بعد حفظ الموافقة
if request.method == 'POST':
    # ... الكود الموجود لحفظ ConsentRecord ...

    # ✅ تسجيل توقيت الموافقة
    if not request.user.consent_given_at:
        request.user.consent_given_at = timezone.now()
        request.user.save(update_fields=['consent_given_at'])

    messages.success(request, "تم حفظ إعدادات الموافقة بنجاح.")
    return redirect('parent_dashboard')
```

---

### 6.2 — حذف `core/models_new.py` أو توثيقه

**المشكلة:** ملف `models_new.py` مجهول الغرض — يُسبب ارتباكاً.

```bash
# الخيار 1: احذفه إذا لم يكن ضرورياً
git rm core/models_new.py
git commit -m "cleanup: remove orphaned models_new.py"

# الخيار 2: أعد تسميته إذا كان مسودة
mv core/models_new.py core/models_draft_v4.md
# وأضف تعليقاً يوضح الغرض
```

---

### 6.3 — تصحيح ملف PROFESSIONAL_STANDARDS_REPORT.md

**المشكلة:** الملف يوصي بـ Django 6.0 وهو غير موجود (أحدث إصدار Django 5.1/5.2).

افتح الملف وعدّل الجدول:

```markdown
<!-- قبل ❌ -->
| Backend Framework | Django | 6.0+ | ✅ Async-Native |

<!-- بعد ✅ -->
| Backend Framework | Django | 5.1 LTS | ✅ مستقر للإنتاج |
```

> ملاحظة: Django 6.0 غير موجود حتى مارس 2026. الإصدار الموصى به للإنتاج هو Django 5.1 (LTS).

---

---

# ✅ المرحلة 7 — 17:00 إلى 18:00
## اختبار شامل والتحقق من كل الإصلاحات

---

### 7.1 — Checklist الاختبار اليدوي

#### 🔴 اختبارات حرجة (لا تتجاوزها)

```bash
# ١. تحقق أن data/ غير موجود في Git
git ls-files data/
# يجب أن يعود فارغاً

# ٢. تحقق أن SECRET_KEY ليس في Git
grep -r "secret-key" .git/
# يجب أن يعود فارغاً

# ٣. تحقق أن FERNET_KEY يعمل
python manage.py shell -c "
from core.models import encrypt_field, decrypt_field
v = encrypt_field('اختبار')
print('مشفر:', v[:30])
print('مفكوك:', decrypt_field(v))
"
```

#### 🔴 اختبار Logout CSRF

```bash
# هذا يجب أن يعطي 405 Method Not Allowed
curl -X GET http://localhost:8000/auth/logout/
# يجب أن يعود: 405
```

#### 🟡 اختبار Rate Limiting

```bash
# شغّل 15 طلب في ثانية — يجب أن يُوقف بعد 10
for i in $(seq 1 15); do
    curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:8000/auth/login/ \
    -d "national_id=test&password=wrong"
done
# يجب أن ترى 200 أو 302 للأوائل، ثم 429 Too Many Requests
```

#### 🟡 اختبار AuditLog

```python
# في Django shell
from core.models import AuditLog, HealthRecord

# بعد تعديل سجل صحي، تحقق أن user مسجّل
last_log = AuditLog.objects.order_by('-timestamp').first()
print("User:", last_log.user)  # يجب ألا يكون None
print("IP:", last_log.ip_address)
```

---

### 7.2 — تشغيل الاختبارات الآلية

```bash
# تشغيل جميع الاختبارات
python -m pytest tests/ -v

# تشغيل اختبارات الأمان فقط
python -m pytest tests/test_permissions.py tests/test_fixes.py -v

# تشغيل اختبارات APIs
python -m pytest tests/test_apis.py -v
```

---

### 7.3 — إضافة اختبارات للثغرات المُصلحة

أضف هذه الاختبارات إلى `tests/test_fixes.py`:

```python
# tests/test_fixes.py — اختبارات جديدة للإصلاحات

import pytest
from django.test import Client


class TestLogoutCSRF:

    def test_logout_rejects_get(self, client, teacher_user):
        """Logout يجب أن يرفض GET"""
        client.force_login(teacher_user)
        response = client.get('/auth/logout/')
        assert response.status_code == 405, "Logout يجب أن يرفض GET requests"

    def test_logout_accepts_post_with_csrf(self, client, teacher_user):
        """Logout يقبل POST مع CSRF"""
        client.force_login(teacher_user)
        response = client.post('/auth/logout/')
        assert response.status_code in (200, 302)


class TestEncryption:

    def test_fernet_key_is_configured(self):
        """FERNET_KEY يجب أن يكون مضبوطاً"""
        from django.conf import settings
        assert settings.FERNET_KEY, (
            "FERNET_KEY غير مضبوط — البيانات الصحية بدون تشفير"
        )

    def test_health_record_encryption(self, db, school):
        """البيانات الصحية يجب أن تُشفَّر"""
        from core.models import HealthRecord, CustomUser
        from tests.conftest import UserFactory, RoleFactory, MembershipFactory

        student = UserFactory()
        record = HealthRecord(student=student)
        record.save_encrypted(
            allergies="حساسية من البنسلين",
            chronic_diseases="",
            medications=""
        )

        # القيمة في DB يجب أن تكون مشفرة
        raw = HealthRecord.objects.get(pk=record.pk).allergies
        assert raw.startswith('gAAAAA'), "البيانات الصحية يجب أن تكون مشفرة في DB"

        # القيمة المُفكَّكة يجب أن تكون صحيحة
        assert record.get_allergies() == "حساسية من البنسلين"


class TestAuditLog:

    def test_audit_log_captures_user(self, client, teacher_user, school):
        """AuditLog يجب أن يُسجّل المستخدم الفعلي"""
        from core.models import AuditLog

        initial_count = AuditLog.objects.count()
        client.force_login(teacher_user)

        # أي عملية تُطلق signal
        # ...

        # تحقق أن آخر log يحتوي على user
        if AuditLog.objects.count() > initial_count:
            last = AuditLog.objects.order_by('-timestamp').first()
            assert last.user is not None, "AuditLog يجب أن يُسجّل المستخدم"


class TestRaceCondition:

    def test_failed_login_uses_atomic_update(self):
        """التحقق أن الكود يستخدم F() وليس += """
        import ast
        import inspect
        from core import views_auth

        source = inspect.getsource(views_auth.login_view)
        tree   = ast.parse(source)

        # تحقق عدم وجود += على failed_login_attempts
        for node in ast.walk(tree):
            if isinstance(node, ast.AugAssign):
                if (hasattr(node.target, 'attr') and
                    node.target.attr == 'failed_login_attempts'):
                    pytest.fail(
                        "Race condition: استخدم F('failed_login_attempts') + 1 "
                        "بدلاً من +="
                    )
```

---

### 7.4 — Checklist النهائي قبل أي نشر

```
قبل النشر — تحقق من هذه النقاط كلها:

البيانات والأسرار:
  [ ] data/ في .gitignore ولا تظهر في git ls-files
  [ ] SECRET_KEY في .env وليس في أي ملف .py أو .yml
  [ ] FERNET_KEY في .env وليس فارغاً
  [ ] DB_PASSWORD في .env وليس في docker-compose.yml

الأمان:
  [ ] logout_view يعطي 405 على GET
  [ ] failed_login_attempts يستخدم F() expression
  [ ] totp_secret يبدأ بـ gAAAAA في قاعدة البيانات
  [ ] AuditLog.user ليس None بعد العمليات الصحية
  [ ] Rate Limiting يعطي 429 بعد 10 طلبات/دقيقة

إعدادات الإنتاج:
  [ ] DEBUG = False
  [ ] ALLOWED_HOSTS = ['schoolos.qa'] فقط
  [ ] SESSION_COOKIE_SECURE = True
  [ ] CSRF_COOKIE_SECURE = True
  [ ] SECURE_HSTS_SECONDS = 31536000
  [ ] NGINX يعمل ويُعيد التوجيه لـ HTTPS

الاختبارات:
  [ ] python -m pytest tests/ يمر بدون أخطاء
  [ ] test_logout_rejects_get يمر
  [ ] test_health_record_encryption يمر
  [ ] test_fernet_key_is_configured يمر
```

---

---

## 📊 ملخص كل الإصلاحات

| # | المشكلة | الملف | وقت الإصلاح | الخطورة |
|---|---------|-------|------------|---------|
| 1 | بيانات حقيقية في Git | `.gitignore` + git history | 30 دقيقة | 🔴 حرج |
| 2 | SECRET_KEY في docker-compose | `docker-compose.yml` + `.env` | 15 دقيقة | 🔴 حرج |
| 3 | FERNET_KEY غير مضبوط | `core/models.py` + `.env` | 20 دقيقة | 🔴 حرج |
| 4 | seed يعمل عند كل restart | `Dockerfile` | 5 دقائق | 🔴 حرج |
| 5 | Logout يقبل GET (CSRF) | `core/views_auth.py` | 5 دقائق | 🔴 حرج |
| 6 | Race condition في قفل الحساب | `core/views_auth.py` | 15 دقيقة | 🔴 حرج |
| 7 | totp_secret غير مشفر | `core/models.py` + `views_auth.py` | 30 دقيقة | 🔴 حرج |
| 8 | AuditLog لا يسجل المستخدم | `core/signals.py` + `middleware.py` | 30 دقيقة | 🟡 مهم |
| 9 | لا Rate Limiting | `settings/base.py` + views | 30 دقيقة | 🟡 مهم |
| 10 | لا CSP headers | `settings/base.py` | 20 دقيقة | 🟡 مهم |
| 11 | N+1 في quality/views.py | `quality/views.py` | 20 دقيقة | 🟡 مهم |
| 12 | لا NGINX | `nginx/nginx.conf` + docker-compose | 45 دقيقة | 🟡 مهم |
| 13 | Consent غير إلزامي | `parents/views.py` + middleware | 30 دقيقة | 🔵 تحسين |
| 14 | models_new.py مجهول | حذف/توثيق | 5 دقائق | 🔵 تنظيف |
| 15 | تقرير يوصي بـ Django 6.0 | `.md` file | 5 دقائق | 🔵 توثيق |

**الوقت الإجمالي:** ~7 ساعات عمل فعلي

---

## 🚀 ما بعد اليوم — الأسابيع القادمة

### الأسبوع الثاني:
- [ ] تعيين مسؤول حماية البيانات (DPO)
- [ ] إعداد وثيقة DPIA
- [ ] اختبار اختراق شامل (Penetration Testing)

### الأسبوع الثالث:
- [ ] آلية إشعار تلقائي عند خرق البيانات (Breach Notification)
- [ ] توثيق API بـ Swagger/OpenAPI
- [ ] إضافة Celery للمهام غير المتزامنة

### الشهر الثاني:
- [ ] مراجعة أمنية خارجية
- [ ] تحسينات الأداء (Redis Caching)
- [ ] جاهز للنشر الإنتاجي الكامل ✅

---

*تم إعداد هذه الخارطة بناءً على تحليل الكود المصدري الكامل لـ SchoolOS Qatar v3*  
*التاريخ: 19 مارس 2026*
