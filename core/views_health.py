"""
core/views/health.py
━━━━━━━━━━━━━━━━━━━
GET /health/ — فحص صحة المنصة
يُستخدم من:
  - Docker healthcheck
  - GitHub Actions (smoke test بعد النشر)
  - أدوات المراقبة الخارجية
"""
import time
from django.http import JsonResponse
from django.db import connection
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
@never_cache
def health_check(request):
    start = time.monotonic()
    checks = {}

    # ── فحص قاعدة البيانات ─────────────────────────────────────
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"error: {type(e).__name__}"

    # ── فحص Redis / Cache ───────────────────────────────────────
    try:
        from django.core.cache import cache
        cache.set("_health", "1", timeout=5)
        checks["cache"] = "ok" if cache.get("_health") == "1" else "error: read failed"
    except Exception as e:
        checks["cache"] = f"error: {type(e).__name__}"

    # ── الحالة الإجمالية ────────────────────────────────────────
    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503

    return JsonResponse({
        "status":   "ok" if all_ok else "degraded",
        "version":  "v1.0",
        "checks":   checks,
        "latency_ms": round((time.monotonic() - start) * 1000, 1),
    }, status=status_code)
