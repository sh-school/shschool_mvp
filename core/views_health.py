"""
core/views_health.py
━━━━━━━━━━━━━━━━━━━
GET /health/ — فحص صحة كامل (DB + Redis)
GET /ready/  — Readiness Probe خفيف (DB فقط — لـ load balancer و Kubernetes)
GET /status/ — معلومات تشغيلية مفصّلة (DB + Redis + migrations + uptime + version)

الفرق:
  /health/ → Liveness: يتحقق من DB + Redis — للمراقبة والتنبيهات
  /ready/  → Readiness: يتحقق من DB فقط — لإخبار الـ load balancer إذا كان
              الـ container جاهزاً لاستقبال الطلبات (يُستخدم في rolling updates)
  /status/ → Dashboard: معلومات مفصّلة لفريق العمليات — latency, migrations, uptime
"""

import logging
import os
import time

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

# Server start time — captured at module import (first request or gunicorn fork)
_SERVER_START_TIME = time.monotonic()
_SERVER_START_TIMESTAMP = timezone.now()

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


@require_GET
@never_cache
def status_check(request):
    """
    GET /status/ — Full system status for operations dashboards.

    Returns detailed JSON with:
      - database: connected/disconnected + latency_ms
      - redis: connected/disconnected + latency_ms
      - migrations: all_applied true/false
      - version: from APP_VERSION env or PLATFORM_VERSION setting
      - uptime: seconds since server start
      - timestamp: current server time
    """
    checks = {}
    overall_healthy = True

    # ── Database ──────────────────────────────────────────────────
    db_start = time.monotonic()
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_latency = round((time.monotonic() - db_start) * 1000, 1)
        checks["database"] = {"status": "connected", "latency_ms": db_latency}
    except Exception as e:  # noqa: BLE001
        db_latency = round((time.monotonic() - db_start) * 1000, 1)
        checks["database"] = {"status": "disconnected", "latency_ms": db_latency}
        overall_healthy = False
        logger.error("status_check: DB failed: %s", e, exc_info=True)

    # ── Redis / Cache ─────────────────────────────────────────────
    redis_start = time.monotonic()
    try:
        from django.core.cache import cache

        cache.set("_status_probe", "1", timeout=5)
        result = cache.get("_status_probe")
        redis_latency = round((time.monotonic() - redis_start) * 1000, 1)
        if result == "1":
            checks["redis"] = {"status": "connected", "latency_ms": redis_latency}
        else:
            checks["redis"] = {"status": "disconnected", "latency_ms": redis_latency}
            overall_healthy = False
    except Exception as e:  # noqa: BLE001
        redis_latency = round((time.monotonic() - redis_start) * 1000, 1)
        checks["redis"] = {"status": "disconnected", "latency_ms": redis_latency}
        overall_healthy = False
        logger.error("status_check: Redis failed: %s", e, exc_info=True)

    # ── Migrations ────────────────────────────────────────────────
    try:
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        checks["migrations"] = {"all_applied": len(plan) == 0}
    except Exception as e:  # noqa: BLE001
        checks["migrations"] = {"all_applied": False}
        logger.error("status_check: Migration check failed: %s", e, exc_info=True)

    # ── Version & Uptime ──────────────────────────────────────────
    version = os.environ.get(
        "APP_VERSION",
        f"v{getattr(settings, 'PLATFORM_VERSION', '5.4')}",
    )
    uptime_seconds = round(time.monotonic() - _SERVER_START_TIME, 1)

    status_code = 200 if overall_healthy else 503
    return JsonResponse(
        {
            "status": "healthy" if overall_healthy else "unhealthy",
            "timestamp": timezone.now().isoformat(),
            "version": version,
            "uptime_seconds": uptime_seconds,
            "checks": checks,
        },
        status=status_code,
    )
