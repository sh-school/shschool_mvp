"""لوحةُ السكرتير (الشريطان 1 و2، قرارُ المالك 2026-10-02) — حضورُ اليوم وما ينتظر السكرتير.

النواةُ لا تستورد وحدةً نازلة، فاللوحةُ تأتي عبر سجلّ المزوِّدين (`core/dashboard_registry.py`) تسجّلها
`staff_affairs` عند الإقلاع. والأرقامُ من الخدمات القائمة؛ والبدلاءُ والتبديلاتُ ليست هنا (شأنُ النائب).
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from core.dashboard_registry import role_dashboard_provider
from core.models import AuditLog
from staff_affairs import attendance as attendance_module
from staff_affairs import dashboard as secretary_dashboard
from staff_affairs.attendance import StaffAttendanceService
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


def _person(school, number, role="teacher"):
    user = UserFactory(full_name=f"موظف اصطناعي {number}", employee_number=str(number))
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def secretary(school):
    return _person(school, 90001, "secretary")


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    """ساعةُ الرصد مثبَّتةٌ على 09:30 من «اليوم» الحقيقيّ.

    الاختبارُ يرصد حضوراً بـ06:30 «اليوم»، والسياسةُ ترفض ما لم يقع بعدُ — فكان يسقط
    كلَّ ليلةٍ من منتصف الليل حتى 06:30 بتوقيت الدوحة (W-20261002-045). و`localdate`
    يبقى الحقيقيَّ فيتّفق «اليومُ» في الاختبار وفي لوحة السكرتير.
    """
    now = datetime.combine(timezone.localdate(), time(9, 30), tzinfo=ZoneInfo("Asia/Qatar"))
    monkeypatch.setattr(attendance_module, "_now", lambda: now, raising=False)


@pytest.fixture
def every_day_is_a_school_day(monkeypatch):
    monkeypatch.setattr(secretary_dashboard, "SCHOOL_WEEKDAYS", frozenset(range(7)))


def _page(client_as, user):
    return client_as(user).get(reverse("dashboard"))


class TestRegistry:
    def test_staff_affairs_registers_the_secretary_dashboard(self):
        assert role_dashboard_provider("secretary") is secretary_dashboard.secretary_context

    def test_roles_without_a_provider_keep_the_shared_dashboard(self):
        assert role_dashboard_provider("receptionist") is None


class TestSecretaryDashboard:
    def test_secretary_gets_her_own_dashboard(self, client_as, secretary):
        response = _page(client_as, secretary)
        assert response.context["view_type"] == "secretary"
        html = response.content.decode()
        assert "لوحة السكرتير" in html and "ينتظرني" in html and "حضورُ اليوم" in html

    def test_other_administrative_roles_keep_admin_ops(self, client_as, school):
        for role in ("admin", "receptionist"):
            assert (
                _page(client_as, _person(school, 91000 + len(role), role)).context["view_type"]
                == "admin_ops"
            )

    def test_no_student_alerts_substitutes_or_swaps_on_it(self, client_as, secretary):
        html = _page(client_as, secretary).content.decode()
        for absent in ("تنبيهات الغياب المعلّقة", "طلبات تبديلٍ معلّقة", "حصصٌ تعويضيّةٌ معلّقة"):
            assert absent not in html

    def test_import_button_leads_the_page(self, client_as, secretary):
        html = _page(client_as, secretary).content.decode()
        assert reverse("staff_affairs:attendance_import") in html

    def test_counts_come_from_todays_attendance(
        self, client_as, school, secretary, every_day_is_a_school_day
    ):
        today = timezone.localdate()
        for number, check_in in ((92001, time(6, 30)), (92002, time(7, 30))):
            StaffAttendanceService.mark(
                school=school, staff=_person(school, number), day=today,
                status="present" if check_in < time(7, 0) else "late",
                actor=secretary, check_in=check_in,
            )  # fmt: skip
        values = {k["label"]: k["value"] for k in _page(client_as, secretary).context["attendance"]}
        assert values["حاضر"] == 1 and values["متأخّر"] == 1
        assert values["لم يُرصد"] >= 1

    def test_unmarked_is_not_presented_as_absent(self, client_as, secretary):
        items = {k["label"]: k for k in _page(client_as, secretary).context["attendance"]}
        assert items["لم يُرصد"]["tone"] != items["غائب"]["tone"]
        assert "ليس غياباً" in items["لم يُرصد"]["title"]

    def test_each_number_links_to_the_filtered_board(self, client_as, secretary):
        items = _page(client_as, secretary).context["attendance"]
        hrefs = " ".join(k["href"] for k in items)
        for state in ("present", "late", "absent", "permitted", "unmarked"):
            assert f"status={state}" in hrefs

    def test_exempt_staff_are_not_counted(self, client_as, school, secretary):
        from staff_affairs.models import StaffAttendanceExemption

        staff = _person(school, 92100)
        before = _page(client_as, secretary).context["attendance_total"]
        StaffAttendanceExemption.objects.create(
            school=school, staff=staff, start_date=timezone.localdate(), created_by=secretary
        )
        assert _page(client_as, secretary).context["attendance_total"] == before - 1


class TestImportStatus:
    def _log(self, school, secretary, text, written=7):
        AuditLog.log(  # type: ignore[no-untyped-call]
            user=secretary, action="create", model_name="other",
            object_repr=f"BiometricImport {text}", changes={"written": written}, school=school,
        )  # fmt: skip

    def test_no_import_yet_says_so(self, client_as, secretary, every_day_is_a_school_day):
        assert "لم يُستورد كشفُ بصمةٍ بعد" in _page(client_as, secretary).content.decode()

    def test_import_for_today_is_acknowledged(
        self, client_as, school, secretary, every_day_is_a_school_day
    ):
        self._log(school, secretary, timezone.localdate().isoformat(), written=7)
        html = _page(client_as, secretary).content.decode()
        assert "استُورد كشفُ اليوم" in html and "رُصد 7 موظّفاً" in html

    def test_old_import_does_not_count_as_todays(
        self, client_as, school, secretary, every_day_is_a_school_day
    ):
        self._log(school, secretary, "2020-01-01")
        assert "لم يُستورد كشفُ اليوم بعد" in _page(client_as, secretary).content.decode()

    def test_non_school_day_is_not_nagged(self, client_as, secretary, monkeypatch):
        monkeypatch.setattr(secretary_dashboard, "SCHOOL_WEEKDAYS", frozenset())
        html = _page(client_as, secretary).content.decode()
        assert "ليس يومَ دوامٍ" in html and "لم يُستورد" not in html


class TestRegistryGuards:
    """مراجعةُ 0105 (P3): لا فوزَ صامتاً لتسجيلٍ مكرَّر، ولا كتابةَ فوق مفاتيح النواة، وحارسٌ لمجموعة الأدوار المسجَّلة."""

    def test_registered_roles_are_exactly_the_secretary(self):
        from core.dashboard_registry import registered_roles

        assert registered_roles() == {"secretary"}

    def test_duplicate_registration_by_another_provider_is_refused(self):
        from django.core.exceptions import ImproperlyConfigured

        from core.dashboard_registry import register_role_dashboard

        with pytest.raises(ImproperlyConfigured):
            register_role_dashboard("secretary", lambda user, school, today: {})

    def test_registering_the_same_provider_again_is_harmless(self):
        from core.dashboard_registry import register_role_dashboard

        register_role_dashboard("secretary", secretary_dashboard.secretary_context)

    def test_provider_cannot_overwrite_core_context_keys(self, client_as, secretary, monkeypatch):
        from django.core.exceptions import ImproperlyConfigured

        from core import dashboard_registry

        monkeypatch.setitem(
            dashboard_registry._PROVIDERS,
            "secretary",
            lambda user, school, today: {"view_type": "secretary", "school": None},
        )
        with pytest.raises(ImproperlyConfigured):
            _page(client_as, secretary)
