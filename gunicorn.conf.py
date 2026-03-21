# gunicorn.conf.py — SchoolOS Production Config
# ════════════════════════════════════════════════════════════════
# Zero-downtime: preload + graceful timeout + max-requests cycling
# ════════════════════════════════════════════════════════════════

import multiprocessing

# ── Binding ─────────────────────────────────────────────────────
bind            = "0.0.0.0:8000"

# ── Workers ─────────────────────────────────────────────────────
# الصيغة الموصى بها: (2 × CPU cores) + 1
workers         = multiprocessing.cpu_count() * 2 + 1
worker_class    = "sync"
threads         = 1

# ── Timeouts ────────────────────────────────────────────────────
timeout         = 120       # وقت أقصى للطلب (ثانية)
graceful_timeout = 30       # وقت يُعطى للـ worker لإنهاء طلبه قبل الإيقاف
keepalive       = 5         # ثوانٍ لإبقاء الاتصال مفتوحاً

# ── Zero-Downtime: تدوير Worker تلقائي ──────────────────────────
# كل worker يُعيد تشغيل نفسه بعد N طلب — يمنع تسريب الذاكرة
# بدون توقف المنصة (الـ workers لا يُعيدون تشغيلهم في نفس اللحظة)
max_requests        = 1000
max_requests_jitter = 100   # عشوائية تمنع تزامن إعادة التشغيل

# ── Preload: تحميل الكود مرة واحدة قبل Fork ─────────────────────
# أسرع reload + اكتشاف أخطاء الكود قبل استبدال الـ workers
preload_app     = True

# ── Logging ─────────────────────────────────────────────────────
accesslog       = "/app/logs/access.log"
errorlog        = "/app/logs/error.log"
loglevel        = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(M)sms'

# ── Process Naming ───────────────────────────────────────────────
proc_name       = "schoolos"

# ── Security ─────────────────────────────────────────────────────
limit_request_line   = 4094
limit_request_fields = 100
