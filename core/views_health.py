"""
core/views/health.py
━━━━━━━━━━━━━━━━━━━
GET /health/ — فحص صحة كامل (DB + Redis)
GET /ready/  — Readiness Probe خفيف (DB فقط — لـ load balancer و Kubernetes)

الفرق:
  /health/ → Liveness: يتحقق من DB + Redis — للمراقبة والتنبيهات
  /ready/  → Readiness: يتحقق من DB فقط — لإخبار الـ load balancer إذا كان
              الـ container جاهزاً لاستقبال الطلبات (يُستخدم في rolling updates)
"""

import logging
import time

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


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
    except Exception as e:  # noqa: BLE001 — broad catch intentional: health check must report any failure
        checks["db"] = f"error: {type(e).__name__}"
        logger.error("health_check: DB فشل: %s", e, exc_info=True)

    # ── فحص Redis / Cache ───────────────────────────────────────
    try:
        from django.core.cache import cache

        cache.set("_health", "1", timeout=5)
        checks["cache"] = "ok" if cache.get("_health") == "1" else "error: read failed"
    except Exception as e:  # noqa: BLE001 — broad catch intentional: health check must report any failure
        checks["cache"] = f"error: {type(e).__name__}"
        logger.error("health_check: Cache فشل: %s", e, exc_info=True)

    # ── الحالة الإجمالية ────────────────────────────────────────
    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503

    if not all_ok:
        logger.warning("health_check degraded: %s", checks)

    from django.conf import settings

    return JsonResponse(
        {
            "status": "ok" if all_ok else "degraded",
            # ✅ v5.4: يسحب الإصدار من PLATFORM_VERSION بدل hardcoded string
            "version": f"v{getattr(settings, 'PLATFORM_VERSION', '5.4')}",
            "checks": checks,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
        },
        status=status_code,
    )


@require_GET
@never_cache
def readiness_check(request):
    """
    GET /ready/ — Readiness Probe خفيف للـ load balancer.

    يتحقق من DB فقط (أخف وأسرع من /health/).
    يُعيد 200 إذا كان الـ container جاهزاً، 503 إذا لم يكن.

    الفرق عن /health/:
      - لا يفحص Redis (قد يكون Redis بطيئاً مؤقتاً دون أن يمنع الخدمة)
      - مُصمَّم للـ rolling deployments: يمنع إرسال طلبات للـ container قبل جهوزيته
    """
    start = time.monotonic()

    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception as e:  # noqa: BLE001
        db_ok = False
        logger.error("readiness_check: DB فشل: %s", e)

    status_code = 200 if db_ok else 503
    return JsonResponse(
        {
            "ready": db_ok,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
        },
        status=status_code,
    )
