"""
tests/test_v54_features.py
اختبارات ميزات v5.4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يغطي:
  1. Readiness Probe — GET /ready/
  2. Health Liveness  — GET /health/
  3. Admin PDPPL masking — national_id مخفي في قائمة المستخدمين
  4. _axes_reset() — helper اختياري لا يكسر الكود إذا axes غير مثبت
"""

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from core.admin import CustomUserAdmin
from core.models import CustomUser
from tests.conftest import UserFactory

# ══════════════════════════════════════════════════════════════
# 1. Readiness Probe — /ready/
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestReadinessProbe:
    """اختبارات GET /ready/ — Readiness Probe الخفيف."""

    def test_ready_returns_200_when_db_ok(self, client):
        """✅ /ready/ يُعيد 200 عندما تكون DB جاهزة."""
        resp = client.get("/ready/")
        assert resp.status_code == 200

    def test_ready_response_is_json(self, client):
        """✅ /ready/ يُعيد JSON."""
        resp = client.get("/ready/")
        data = resp.json()
        assert "ready" in data
        assert "latency_ms" in data

    def test_ready_body_ready_is_true(self, client):
        """✅ ready=True عند جهوزية DB."""
        resp = client.get("/ready/")
        assert resp.json()["ready"] is True

    def test_ready_latency_is_number(self, client):
        """✅ latency_ms رقم غير سالب."""
        resp = client.get("/ready/")
        latency = resp.json()["latency_ms"]
        assert isinstance(latency, (int, float))
        assert latency >= 0

    def test_ready_not_cached(self, client):
        """✅ /ready/ لا تُخزَّن في الـ cache (Cache-Control: no-cache)."""
        resp = client.get("/ready/")
        # never_cache يضع no-cache في الرأس
        assert resp.get("Cache-Control") is not None
        assert (
            "no-cache" in resp.get("Cache-Control", "").lower() or resp.get("Pragma") == "no-cache"
        )

    def test_ready_rejects_post(self, client):
        """✅ /ready/ لا يقبل POST — يُعيد 405."""
        resp = client.post("/ready/", {})
        assert resp.status_code == 405


# ══════════════════════════════════════════════════════════════
# 2. Health Liveness — /health/
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestHealthLiveness:
    """اختبارات GET /health/ — Liveness Probe الكامل."""

    def test_health_returns_200_when_db_ok(self, client):
        """✅ /health/ يُعيد 200 أو 503 (Redis قد يغيب في الاختبارات)."""
        resp = client.get("/health/")
        assert resp.status_code in (200, 503)

    def test_health_response_has_db_key(self, client):
        """✅ /health/ يحتوي على مفتاح 'db' في الـ response."""
        resp = client.get("/health/")
        data = resp.json()
        assert "checks" in data
        assert "db" in data["checks"]

    def test_health_db_is_ok_in_tests(self, client):
        """✅ حالة DB دائماً 'ok' في بيئة الاختبار."""
        resp = client.get("/health/")
        data = resp.json()
        assert data["checks"]["db"] == "ok"

    def test_health_has_version(self, client):
        """✅ /health/ يُعيد حقل version."""
        resp = client.get("/health/")
        data = resp.json()
        assert "version" in data

    def test_health_rejects_post(self, client):
        """✅ /health/ لا يقبل POST."""
        resp = client.post("/health/", {})
        assert resp.status_code == 405


# ══════════════════════════════════════════════════════════════
# 3. Admin PDPPL — national_id مُخفًى في list_display
# ══════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAdminPDPPLMasking:
    """
    ✅ PDPPL م.8: اختبارات إخفاء الرقم الوطني في Django Admin.
    """

    def _get_admin_instance(self):
        return CustomUserAdmin(model=CustomUser, admin_site=AdminSite())

    def test_masked_national_id_hides_prefix(self):
        """✅ masked_national_id() تُخفي كل الأرقام ماعدا آخر 4."""
        user = UserFactory.build(national_id="28765432101")
        admin = self._get_admin_instance()
        result = admin.masked_national_id(user)
        # يجب أن يحتوي على آخر 4 أرقام
        assert "2101" in str(result)
        # يجب ألّا يحتوي على باقي الأرقام كاملة
        assert "28765" not in str(result)

    def test_masked_national_id_shows_stars(self):
        """✅ masked_national_id() تُظهر نجوم للمقطع المخفي."""
        user = UserFactory.build(national_id="12345678901")
        admin = self._get_admin_instance()
        result = admin.masked_national_id(user)
        assert "****" in str(result)

    def test_masked_national_id_short_id(self):
        """✅ معالجة الرقم القصير (≤4 أرقام) بأمان."""
        user = UserFactory.build(national_id="1234")
        admin = self._get_admin_instance()
        result = admin.masked_national_id(user)
        assert "****" in str(result)

    def test_masked_national_id_empty(self):
        """✅ لا استثناء عند national_id فارغ."""
        user = UserFactory.build(national_id="")
        admin = self._get_admin_instance()
        result = admin.masked_national_id(user)
        assert result == "****"

    def test_list_display_uses_masked(self):
        """✅ CustomUserAdmin.list_display يستخدم masked_national_id."""
        admin = self._get_admin_instance()
        assert "masked_national_id" in admin.list_display
        assert "national_id" not in admin.list_display

    def test_search_fields_still_has_national_id(self):
        """✅ search_fields لا تزال تبحث بـ national_id (للأداء)."""
        admin = self._get_admin_instance()
        assert "national_id" in admin.search_fields


# ══════════════════════════════════════════════════════════════
# 4. _axes_reset() — اختياري + لا يكسر الكود
# ══════════════════════════════════════════════════════════════


class TestAxesReset:
    """اختبارات _axes_reset() helper في views_auth.py."""

    def test_axes_reset_does_not_raise(self):
        """✅ _axes_reset() لا تُثير استثناء في أي حال."""
        from core.views_auth import _axes_reset

        factory = RequestFactory()
        request = factory.post("/auth/login/")
        # يجب أن تعمل بهدوء سواء كان axes مثبتاً أم لا
        try:
            _axes_reset(request, "12345678901")
        except Exception as e:  # noqa: BLE001
            pytest.fail(f"_axes_reset() رفعت استثناء غير متوقع: {e}")

    def test_axes_reset_with_empty_national_id(self):
        """✅ _axes_reset() آمنة مع رقم وطني فارغ."""
        from core.views_auth import _axes_reset

        factory = RequestFactory()
        request = factory.post("/auth/login/")
        _axes_reset(request, "")  # يجب أن لا تُثير استثناء
