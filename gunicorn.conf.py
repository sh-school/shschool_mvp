# gunicorn.conf.py — SchoolOS Production Config
# ════════════════════════════════════════════════════════════════
# Zero-downtime: preload + graceful timeout + max-requests cycling
# ════════════════════════════════════════════════════════════════

import os

# ── Binding ─────────────────────────────────────────────────────
# يحترم PORT من PaaS (Railway/Heroku/Render) ويسقط على 8000 محلياً
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# ── Workers ─────────────────────────────────────────────────────
# ✅ Railway/Hobby: عدد workers ثابت (CPU count غير موثوق في الحاويات)
workers = int(os.environ.get('GUNICORN_WORKERS', '3'))
# ✅ sync worker — WSGI كافٍ حتى نضيف ASGI/WebSockets فعلياً
# للـ ASGI في المستقبل: ثبّت uvicorn ثم عيّن GUNICORN_WORKER_CLASS=uvicorn.workers.UvicornWorker
worker_class = os.environ.get('GUNICORN_WORKER_CLASS', 'sync')
threads = 1

# ── Timeouts ────────────────────────────────────────────────────
timeout = 120  # وقت أقصى للطلب (ثانية)
graceful_timeout = 30  # وقت يُعطى للـ worker لإنهاء طلبه قبل الإيقاف
keepalive = 5  # ثوانٍ لإبقاء الاتصال مفتوحاً

# ── Zero-Downtime: تدوير Worker تلقائي ──────────────────────────
# كل worker يُعيد تشغيل نفسه بعد N طلب — يمنع تسريب الذاكرة
# بدون توقف المنصة (الـ workers لا يُعيدون تشغيلهم في نفس اللحظة)
max_requests = 1000
max_requests_jitter = 100  # عشوائية تمنع تزامن إعادة التشغيل

# ── Preload: تحميل الكود مرة واحدة قبل Fork ─────────────────────
# أسرع reload + اكتشاف أخطاء الكود قبل استبدال الـ workers
preload_app = True

# ── Logging ─────────────────────────────────────────────────────
accesslog = "-"  # stdout — تلتقطه Railway/Docker logs
errorlog = "-"  # stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(M)sms'

# ── Process Naming ───────────────────────────────────────────────
proc_name = "schoolos"

# ── Security ─────────────────────────────────────────────────────
limit_request_line = 4094
limit_request_fields = 100
