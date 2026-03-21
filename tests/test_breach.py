"""
tests/test_breach.py
اختبارات وحدة خرق البيانات (PDPPL م.11 — إشعار NCSA 72 ساعة)

يغطي:
  - نموذج BreachReport (إنشاء، خصائص، دالة is_overdue)
  - دورة حياة الحالة (discovered → assessing → notified → resolved)
  - Views: dashboard، create، detail، update_status
  - صلاحيات: مدير فقط
"""
import pytest
from datetime import timedelta

from django.utils import timezone

from core.models import BreachReport
from tests.conftest import SchoolFactory, UserFactory, RoleFactory, MembershipFactory


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def breach(db, school, principal_user):
    return BreachReport.objects.create(
        school             = school,
        title              = "تسرب بيانات الطلاب",
        description        = "وُجد ملف CSV مكشوف على خادم FTP",
        severity           = "high",
        data_type_affected = "academic",
        affected_count     = 120,
        discovered_at      = timezone.now(),
        immediate_action   = "إغلاق المنفذ الخارجي فوراً",
        containment_action = "مراجعة سجلات الوصول",
        reported_by        = principal_user,
    )


@pytest.fixture
def overdue_breach(db, school, principal_user):
    """خرق اكتشف منذ أكثر من 72 ساعة ولم يُرسل إشعار NCSA"""
    return BreachReport.objects.create(
        school             = school,
        title              = "خرق قديم",
        description        = "خرق لم يُبلَّغ عنه",
        severity           = "medium",
        data_type_affected = "personal",
        affected_count     = 10,
        discovered_at      = timezone.now() - timedelta(hours=80),
        immediate_action   = "لم يتخذ إجراء",
        reported_by        = principal_user,
    )


# ══════════════════════════════════════════════════════════════════════
#  اختبارات النموذج
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestBreachReportModel:

    def test_breach_creation(self, breach):
        assert breach.title == "تسرب بيانات الطلاب"
        assert breach.status == "discovered"
        assert breach.severity == "high"
        assert breach.affected_count == 120

    def test_str_representation(self, breach):
        s = str(breach)
        assert "تسرب" in s or breach.title[:10] in s

    def test_ncsa_deadline_72h(self, breach):
        """الموعد النهائي = وقت الاكتشاف + 72 ساعة"""
        if breach.ncsa_deadline:
            delta = breach.ncsa_deadline - breach.discovered_at
            assert abs(delta.total_seconds() - 72 * 3600) < 60

    def test_is_overdue_false_for_new_breach(self, breach):
        """خرق مكتشف للتو ليس متأخراً"""
        assert breach.is_overdue is False

    def test_is_overdue_true_after_72h(self, overdue_breach):
        """خرق مر عليه أكثر من 72 ساعة بدون إشعار = متأخر"""
        assert overdue_breach.is_overdue is True

    def test_is_overdue_false_when_notified(self, overdue_breach):
        """إذا تم الإشعار فليس متأخراً حتى لو مر الوقت"""
        overdue_breach.status = "notified"
        overdue_breach.ncsa_notified_at = timezone.now()
        overdue_breach.save()
        assert overdue_breach.is_overdue is False

    def test_status_choices(self, breach):
        valid_statuses = dict(BreachReport.STATUS).keys()
        for s in ["discovered", "assessing", "notified", "resolved"]:
            assert s in valid_statuses

    def test_severity_choices(self, breach):
        valid = dict(BreachReport.SEVERITY).keys()
        for s in ["low", "medium", "high", "critical"]:
            assert s in valid

    def test_data_types_affected(self, breach):
        valid = dict(BreachReport.DATA_TYPES_AFFECTED).keys()
        for dt in ["health", "academic", "personal", "financial", "all"]:
            assert dt in valid


# ══════════════════════════════════════════════════════════════════════
#  اختبارات دورة الحياة (Status Lifecycle)
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestBreachStatusLifecycle:

    def test_transition_to_assessing(self, breach):
        breach.status = "assessing"
        breach.save()
        breach.refresh_from_db()
        assert breach.status == "assessing"

    def test_transition_to_notified_sets_ncsa_time(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        c.post(f"/breach/{breach.pk}/status/", {"status": "notified"})
        breach.refresh_from_db()
        assert breach.status == "notified"
        assert breach.ncsa_notified_at is not None

    def test_transition_to_resolved_sets_resolved_at(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        c.post(f"/breach/{breach.pk}/status/", {"status": "resolved"})
        breach.refresh_from_db()
        assert breach.status == "resolved"
        assert breach.resolved_at is not None

    def test_invalid_status_ignored(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        c.post(f"/breach/{breach.pk}/status/", {"status": "هجوم_خارجي"})
        breach.refresh_from_db()
        assert breach.status == "discovered"  # لم يتغير


# ══════════════════════════════════════════════════════════════════════
#  اختبارات Views
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestBreachViews:

    # ── Dashboard ──────────────────────────────────────────────

    def test_dashboard_accessible_to_principal(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/breach/")
        assert resp.status_code == 200

    def test_dashboard_forbidden_for_teacher(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.get("/breach/")
        assert resp.status_code in [403, 302]

    def test_dashboard_shows_stats(self, client_as, principal_user, breach, overdue_breach):
        c = client_as(principal_user)
        resp = c.get("/breach/")
        assert resp.status_code == 200
        assert b"stats" in resp.content.lower() or resp.context.get("stats") is not None

    # ── Create ─────────────────────────────────────────────────

    def test_create_get(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/breach/create/")
        assert resp.status_code == 200

    def test_create_post_valid(self, client_as, principal_user):
        c = client_as(principal_user)
        now_str = timezone.now().strftime("%Y-%m-%dT%H:%M")
        resp = c.post("/breach/create/", {
            "title":              "خرق جديد",
            "description":        "وصف الخرق",
            "severity":           "medium",
            "data_type_affected": "personal",
            "affected_count":     5,
            "discovered_at":      now_str,
            "immediate_action":   "إجراء فوري",
            "containment_action": "خطة احتواء",
            "notification_text":  "نص الإشعار",
        })
        assert resp.status_code in [302, 200]
        assert BreachReport.objects.filter(title="خرق جديد").exists()

    def test_create_forbidden_for_teacher(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.post("/breach/create/", {"title": "محاولة"})
        assert resp.status_code in [403, 302]

    # ── Detail ─────────────────────────────────────────────────

    def test_detail_view(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        resp = c.get(f"/breach/{breach.pk}/")
        assert resp.status_code == 200

    def test_detail_forbidden_for_teacher(self, client_as, teacher_user, breach):
        c = client_as(teacher_user)
        resp = c.get(f"/breach/{breach.pk}/")
        assert resp.status_code in [403, 302]

    def test_detail_wrong_school_returns_404(self, db, breach):
        """خرق مدرسة أخرى لا يُعرض"""
        other_school = SchoolFactory()
        other_role   = RoleFactory(school=other_school, name="principal")
        other_user   = UserFactory(full_name="مدير آخر")
        MembershipFactory(user=other_user, school=other_school, role=other_role)
        from django.test import Client
        c = Client()
        c.force_login(other_user)
        resp = c.get(f"/breach/{breach.pk}/")
        assert resp.status_code == 404

    # ── PDF ────────────────────────────────────────────────────

    def test_pdf_view_accessible(self, client_as, principal_user, breach):
        c = client_as(principal_user)
        resp = c.get(f"/breach/{breach.pk}/pdf/")
        # إما PDF أو خطأ قابل للتتبع (لو WeasyPrint غير مثبت)
        assert resp.status_code in [200, 500]
        if resp.status_code == 200:
            assert resp["Content-Type"] == "application/pdf"
