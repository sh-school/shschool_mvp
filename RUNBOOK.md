# RUNBOOK — SchoolOS v5.1
## دليل التشغيل والاستجابة للحوادث

> **الجمهور المستهدف:** مسؤول النظام / المطوّر المناوب
> **آخر تحديث:** مارس 2026

---

## 📞 جهات الاتصال الطارئة

| الدور | الاسم | التواصل |
|-------|-------|---------|
| DPO / مطوّر النظام | سفيان أحمد محمد مسيف | s.mesyef0904@education.qa / 55296286 |
| مدير المدرسة | — | — |
| دعم Oracle Cloud | — | https://support.oracle.com |

---

## 🚦 قائمة الصحة السريعة

```bash
# 1. فحص الخدمات
docker compose -f docker-compose.prod.yml ps

# 2. فحص نقطة الصحة
curl -f http://localhost/health/ && echo "✅ OK"

# 3. سجلات آخر 50 سطر
docker compose -f docker-compose.prod.yml logs --tail=50 web
docker compose -f docker-compose.prod.yml logs --tail=50 celery_worker

# 4. حالة قاعدة البيانات
docker compose -f docker-compose.prod.yml exec db pg_isready -U $DB_USER

# 5. حالة Redis
docker compose -f docker-compose.prod.yml exec redis redis-cli -a $REDIS_PASSWORD ping
```

---

## 🔄 استعادة قاعدة البيانات

### أ. استعادة من آخر نسخة محلية (الأسرع)

```bash
# داخل مجلد المشروع
./scripts/restore.sh
```

### ب. استعادة من نسخة محددة

```bash
./scripts/restore.sh db_20260323_020000.sql.gz
```

### ج. استعادة من S3

```bash
# تأكد من ضبط AWS_BACKUP_BUCKET في .env
./scripts/restore.sh s3
```

### يدويًا (بدون السكريبت)

```bash
# 1. أوقف التطبيق
docker compose -f docker-compose.prod.yml stop web

# 2. استعد
gunzip -c backups/db_YYYYMMDD_HHMMSS.sql.gz \
    | docker compose -f docker-compose.prod.yml exec -T db \
      psql -U $DB_USER $DB_NAME

# 3. أعد التشغيل
docker compose -f docker-compose.prod.yml start web
```

---

## 🔑 نسخة احتياطية يدوية فورية

```bash
# نسخة فورية خارج الجدول
docker compose -f docker-compose.prod.yml exec backup sh /backup.sh

# تحقق من النتيجة
ls -lh backups/ | tail -5
```

---

## 🛑 أشهر 10 أعطال وحلولها

### 1. الموقع لا يستجيب (502 Bad Gateway)

```bash
# تحقق من حالة web
docker compose logs web --tail=20
# أعد تشغيله
docker compose restart web
# تحقق من صحة DB
docker compose exec db pg_isready
```

### 2. قاعدة البيانات لا تبدأ

```bash
docker compose logs db --tail=30
# فحص المساحة
df -h
# بدء يدوي
docker compose up -d db
```

### 3. Redis يرفض الاتصال

```bash
# تحقق من كلمة المرور
docker compose exec redis redis-cli -a $REDIS_PASSWORD ping
# أعد التشغيل
docker compose restart redis
```

### 4. Celery لا يعالج المهام

```bash
docker compose logs celery_worker --tail=30
docker compose restart celery_worker celery_beat
# تحقق من الاتصال بـ Redis
docker compose exec celery_worker celery -A shschool inspect ping
```

### 5. النسخ الاحتياطي فشل

```bash
# راجع سجل backup
docker compose logs backup --tail=20
# شغّل يدويًا للتأكد
docker compose exec backup sh /backup.sh
# تحقق من مساحة القرص
df -h /
du -sh backups/
```

### 6. الهجرات فشلت عند البدء

```bash
docker compose exec web python manage.py showmigrations | grep "\[ \]"
docker compose exec web python manage.py migrate --run-syncdb
```

### 7. ملفات الـ Static لا تظهر

```bash
docker compose exec web python manage.py collectstatic --noinput
docker compose restart nginx
```

### 8. فشل شهادة SSL

```bash
ls -la nginx/ssl/
# تجديد يدوي إذا انتهت صلاحيتها
# certbot renew (إذا مستخدم)
docker compose restart nginx
```

### 9. الذاكرة ممتلئة (OOM)

```bash
free -h
# تحقق من حجم Redis
docker compose exec redis redis-cli -a $REDIS_PASSWORD info memory
# أعد تشغيل الخدمات تدريجياً
docker compose restart celery_worker
docker compose restart web
```

### 10. ملفات السجل تملأ القرص

```bash
du -sh logs/
# احذف السجلات القديمة
find logs/ -name "*.log" -mtime +30 -delete
# أو اضغطها
gzip logs/*.log
```

---

## 🧪 اختبار الاستعادة الشهري (DR Drill)

```bash
# 1. أنشئ بيئة اختبار منفصلة
docker compose -f docker-compose.yml up -d  # بيئة التطوير

# 2. استعد النسخة الأخيرة في بيئة التطوير
DB_HOST=localhost ./scripts/restore.sh backups/db_latest.sql.gz

# 3. تحقق من البيانات
python manage.py check
python manage.py shell -c "from core.models import CustomUser; print(CustomUser.objects.count(), 'مستخدم')"

# 4. وثّق النتيجة في قسم سجل DR أدناه
```

### سجل اختبارات الاستعادة

| التاريخ | النسخة المختبرة | النتيجة | المدة | الملاحظات |
|---------|----------------|---------|-------|-----------|
| 2026-03-23 | — | لم يُختبر بعد | — | أول إعداد |

---

## 📋 قائمة تحقق ما قبل الإنتاج

- [ ] `SECRET_KEY` و`FERNET_KEY` جديدان وسريّان
- [ ] `DEBUG=False` في `.env`
- [ ] `REDIS_PASSWORD` قوي (≥20 حرف)
- [ ] HTTPS + HSTS مفعّل على Nginx
- [ ] النسخ الاحتياطي يعمل (`backup.sh` اختُبر يدوياً)
- [ ] S3 Bucket مضبوط ومُختبر (إذا متاح)
- [ ] Sentry DSN مضبوط
- [ ] DPO مُعيَّن في `.env`
- [ ] DPIA مكتمل وموثَّق

---

## 🔐 إدارة المفاتيح السرية

```bash
# توليد SECRET_KEY جديد
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# توليد FERNET_KEY جديد
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# توليد REDIS_PASSWORD قوي
openssl rand -base64 32
```

> **⚠ مهم:** احفظ المفاتيح في مدير كلمات مرور آمن (مثل Bitwarden أو 1Password).
> لا تحفظها في المستودع أبدًا.

---

*SchoolOS RUNBOOK — مدرسة الشحانية الإعدادية الثانوية للبنين | قطر*
