# RUNBOOK — SchoolOS v5.2
## دليل التشغيل والاستجابة للحوادث وخطة استمرارية الأعمال

> **الجمهور المستهدف:** مسؤول النظام / المطوّر المناوب
> **آخر تحديث:** مارس 2026
> **الإصدار:** 2.0

---

## 📞 جهات الاتصال الطارئة

| الدور | الاسم | التواصل | الأولوية |
|-------|-------|---------|----------|
| DPO / مطوّر النظام | سفيان أحمد محمد مسيف | s.mesyef0904@education.qa / 55296286 | P1 |
| مدير المدرسة | — | — | P2 |
| دعم Oracle Cloud | — | https://support.oracle.com | P3 |

### سلّم التصعيد

| المستوى | الوقت | الإجراء |
|---------|-------|---------|
| P1 — حرج | 0-15 دقيقة | اتصال مباشر بالـ DPO + مطوّر النظام |
| P2 — عالي | 15-30 دقيقة | إشعار مدير المدرسة |
| P3 — متوسط | 1-4 ساعات | تذكرة دعم + بريد إلكتروني |

---

## 🎯 أهداف الاستعادة (RTO / RPO)

| المقياس | الهدف | الحالي | الملاحظات |
|---------|-------|--------|----------|
| **RTO** (وقت الاستعادة) | ≤ 1 ساعة | ~30 دقيقة | استعادة من آخر نسخة محلية |
| **RPO** (نقطة الاستعادة) | ≤ 4 ساعات | 24 ساعة (يومي) | WAL archiving يخفضه لـ ~15 دقيقة |
| **MTTR** (وقت الإصلاح) | ≤ 2 ساعة | غير مقاس | يحتاج DR drill لقياسه |

---

## 🚦 قائمة الصحة السريعة

```bash
# 1. فحص الخدمات
docker compose -f docker-compose.prod.yml ps

# 2. فحص نقطة الصحة
curl -f http://localhost/health/ && echo "OK"

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

### أ. استعادة من آخر نسخة محلية (الأسرع — RTO: ~10 دقائق)

```bash
./scripts/restore.sh
```

### ب. استعادة من نسخة محددة

```bash
./scripts/restore.sh db_20260323_020000.sql.gz
```

### ج. استعادة من S3

```bash
./scripts/restore.sh s3
```

### د. استعادة نقطة زمنية (PITR via WAL)

```bash
# 1. أوقف PostgreSQL
docker compose -f docker-compose.prod.yml stop db

# 2. استعد آخر base backup
gunzip -c backups/db_latest.sql.gz | docker compose exec -T db psql -U $DB_USER $DB_NAME

# 3. طبّق WAL logs حتى النقطة المطلوبة
# (يتطلب recovery.conf مع recovery_target_time)
docker compose -f docker-compose.prod.yml exec db \
  pg_restore --target-time="2026-03-25 10:30:00" /backups/wal/

# 4. أعد التشغيل
docker compose -f docker-compose.prod.yml start db web
```

### يدوياً (بدون السكريبت)

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

# تحقق من النتيجة (يجب أن يظهر checksum)
ls -lh backups/ | tail -5
```

---

## 🔐 تدوير مفاتيح التشفير (Key Rotation)

```bash
# 1. أنشئ مفتاح جديد
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. في .env: انقل المفتاح القديم
#    FERNET_OLD_KEYS=المفتاح_القديم_هنا
#    FERNET_KEY=المفتاح_الجديد_هنا

# 3. أعد تشغيل التطبيق
docker compose -f docker-compose.prod.yml restart web celery_worker

# 4. شغّل أمر إعادة التشفير
docker compose -f docker-compose.prod.yml exec web \
  python manage.py rotate_fernet_key

# 5. بعد التأكد من نجاح التدوير، يمكن إزالة FERNET_OLD_KEYS
```

---

## 🛑 أشهر 10 أعطال وحلولها

### 1. الموقع لا يستجيب (502 Bad Gateway)
```bash
docker compose logs web --tail=20
docker compose restart web
docker compose exec db pg_isready
```

### 2. قاعدة البيانات لا تبدأ
```bash
docker compose logs db --tail=30
df -h
docker compose up -d db
```

### 3. Redis يرفض الاتصال
```bash
docker compose exec redis redis-cli -a $REDIS_PASSWORD ping
docker compose restart redis
```

### 4. Celery لا يعالج المهام
```bash
docker compose logs celery_worker --tail=30
docker compose restart celery_worker celery_beat
docker compose exec celery_worker celery -A shschool inspect ping
```

### 5. النسخ الاحتياطي فشل
```bash
docker compose logs backup --tail=20
docker compose exec backup sh /backup.sh
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
docker compose restart nginx
```

### 9. الذاكرة ممتلئة (OOM)
```bash
free -h
docker compose exec redis redis-cli -a $REDIS_PASSWORD info memory
docker compose restart celery_worker
docker compose restart web
```

### 10. ملفات السجل تملأ القرص
```bash
du -sh logs/
find logs/ -name "*.log" -mtime +30 -delete
```

---

## 🧪 اختبار الاستعادة الشهري (DR Drill)

### الجدول الزمني
- **التكرار:** أول أحد من كل شهر
- **المسؤول:** DPO / مطوّر النظام
- **المدة المتوقعة:** 30-60 دقيقة

### الخطوات

```bash
# 1. أنشئ بيئة اختبار منفصلة
docker compose -f docker-compose.yml up -d

# 2. استعد النسخة الأخيرة في بيئة التطوير
DB_HOST=localhost ./scripts/restore.sh backups/db_latest.sql.gz

# 3. تحقق من البيانات
python manage.py check
python manage.py shell -c "from core.models import CustomUser; print(CustomUser.objects.count(), 'مستخدم')"

# 4. تحقق من سلامة النسخة (checksum)
md5sum -c backups/db_latest.sql.gz.md5

# 5. وثّق النتيجة أدناه
```

### سجل اختبارات الاستعادة

| التاريخ | النسخة المختبرة | النتيجة | المدة | الملاحظات |
|---------|----------------|---------|-------|-----------|
| 2026-03-25 | — | لم يُختبر بعد | — | أول إعداد |

---

## 🚨 قالب الاستجابة للحوادث (Incident Response)

### عند اكتشاف حادثة:

1. **التصنيف** — حدد المستوى (P1/P2/P3)
2. **الاحتواء** — أوقف الضرر (عزل الخدمة، إيقاف الوصول)
3. **التحقيق** — اجمع السجلات والأدلة
4. **الإصلاح** — طبّق الحل
5. **التواصل** — أبلغ المعنيين حسب سلّم التصعيد
6. **المراجعة** — وثّق الدروس المستفادة

### قالب تقرير ما بعد الحادثة (Post-Mortem)

```
## تقرير حادثة: [العنوان]
- التاريخ: YYYY-MM-DD
- المستوى: P1/P2/P3
- المدة: من HH:MM إلى HH:MM
- المتأثرون: [عدد المستخدمين / الخدمات]

### ماذا حدث؟
[وصف تسلسل الأحداث]

### السبب الجذري
[التحليل الفني]

### الإجراءات المتخذة
1. [إجراء 1]
2. [إجراء 2]

### الدروس المستفادة
- [درس 1]
- [درس 2]

### إجراءات وقائية
- [ ] [إجراء وقائي 1]
- [ ] [إجراء وقائي 2]
```

---

## 🛡️ استجابة هجوم Ransomware

1. **افصل الخادم فوراً** عن الشبكة
2. **لا تدفع الفدية**
3. **أبلغ NCSA** (خلال 72 ساعة — PDPPL)
4. **استعد من آخر نسخة سليمة:**
   ```bash
   # استعد من S3 (النسخة الأحدث غير المصابة)
   ./scripts/restore.sh s3
   ```
5. **غيّر جميع المفاتيح:**
   ```bash
   # SECRET_KEY, FERNET_KEY, DB_PASSWORD, REDIS_PASSWORD
   # راجع قسم "إدارة المفاتيح السرية" أدناه
   ```
6. **وثّق الحادثة** باستخدام قالب Post-Mortem

---

## 📋 قائمة تحقق ما قبل الإنتاج

- [ ] `SECRET_KEY` و`FERNET_KEY` جديدان وسريّان
- [ ] `DEBUG=False` في `.env`
- [ ] `REDIS_PASSWORD` قوي (20+ حرف)
- [ ] HTTPS + HSTS مفعّل على Nginx
- [ ] النسخ الاحتياطي يعمل (`backup.sh` اختُبر يدوياً)
- [ ] checksum يُولّد مع كل نسخة
- [ ] S3 Bucket مضبوط ومُختبر (إذا متاح)
- [ ] WAL archiving مفعّل على PostgreSQL
- [ ] Sentry DSN مضبوط
- [ ] DPO مُعيَّن في `.env`
- [ ] DPIA مكتمل وموثَّق
- [ ] DR Drill نُفّذ مرة واحدة على الأقل

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

> **مهم:** احفظ المفاتيح في مدير كلمات مرور آمن (Bitwarden / 1Password).
> لا تحفظها في المستودع أبداً.

---

## 📝 سجل التغييرات

| التاريخ | الإصدار | التغييرات |
|---------|---------|-----------|
| 2026-03-25 | 2.0 | إضافة RTO/RPO، سلّم التصعيد، PITR، key rotation، ransomware response، post-mortem template |
| 2026-03-23 | 1.0 | الإصدار الأول |

---

*SchoolOS RUNBOOK — مدرسة الشحانية الإعدادية الثانوية للبنين | قطر*
