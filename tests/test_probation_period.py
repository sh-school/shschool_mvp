"""عقد التوظيف وفترة الاختبار (W-20261001-027) — م62 وم72 ولائحة م85 وم78.

الاختبار 6 أشهر من 2026-01-01 فنهايته الأصليّة 2026-07-01.
"""

import datetime as dt

import pytest

from staff_affairs.models import EmploymentContract, LeaveBalance, LeaveRequest
from staff_affairs.probation import open_contract, record_result
from staff_affairs.services import LeaveService
from tests.conftest import MembershipFactory, SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db

START = dt.date(2026, 1, 1)


@pytest.fixture
def setup():
    school = SchoolFactory()
    staff = UserFactory()
    MembershipFactory(user=staff, school=school)
    boss = UserFactory()
    return school, staff, boss


def _leave(school, staff, leave_type, start, end, days):
    leave = LeaveService.create_leave_request(
        school=school,
        staff=staff,
        leave_type=leave_type,
        start_date=start,
        end_date=end,
        days_count=days,
        reason="سبب",
        attachment=_pdf() if leave_type in ("maternity", "iddah") else None,
    )
    return leave


def _pdf():
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("d.pdf", b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\n", "application/pdf")


def _approve(leave, boss):
    return LeaveService.review_leave(leave, "approved", boss)


def test_contract_records_reference_and_original_end(setup):
    school, staff, boss = setup
    c = open_contract(school, staff, START, 6, boss, contract_ref="ع-2026/17")
    assert c.contract_ref == "ع-2026/17"
    assert c.base_end == dt.date(2026, 7, 1) == c.probation_end
    assert c.result == "pending" and c.extension_days == 0
    again = open_contract(school, staff, START, 6, boss, contract_ref="ع-2026/17")  # idempotent
    assert again.pk == c.pk and EmploymentContract.objects.count() == 1


@pytest.mark.parametrize("leave_type", ["annual", "spouse_companion"])
def test_annual_and_spouse_refused_under_probation(setup, leave_type):
    school, staff, boss = setup
    open_contract(school, staff, START, 6, boss)
    with pytest.raises(ValueError):
        _leave(school, staff, leave_type, dt.date(2026, 3, 1), dt.date(2026, 3, 3), 3)


def test_approval_also_refuses_if_request_predates_the_contract(setup):
    school, staff, boss = setup
    leave = _leave(school, staff, "annual", dt.date(2026, 3, 1), dt.date(2026, 3, 3), 3)
    open_contract(school, staff, START, 6, boss)
    with pytest.raises(ValueError):
        _approve(leave, boss)
    leave.refresh_from_db()
    assert leave.status == "pending"


@pytest.mark.parametrize("leave_type", ["annual", "spouse_companion"])
def test_accepted_after_passing_probation(setup, leave_type):
    school, staff, boss = setup
    c = open_contract(school, staff, START, 6, boss)
    record_result(c, "passed", boss, dt.date(2026, 7, 2))
    leave = _leave(school, staff, leave_type, dt.date(2026, 10, 4), dt.date(2026, 10, 6), 3)
    assert leave.status == "pending"


def test_failed_probation_still_blocks(setup):
    school, staff, boss = setup
    c = open_contract(school, staff, START, 6, boss)
    record_result(c, "failed", boss, dt.date(2026, 7, 2))
    with pytest.raises(ValueError):
        _leave(school, staff, "annual", dt.date(2026, 10, 4), dt.date(2026, 10, 6), 3)


def test_no_contract_means_no_restriction(setup):
    school, staff, _ = setup
    assert _leave(school, staff, "annual", dt.date(2026, 3, 1), dt.date(2026, 3, 3), 3)


def test_sick_leave_extends_probation_by_its_days_m72(setup):
    school, staff, boss = setup
    c = open_contract(school, staff, START, 6, boss)
    sick = _leave(school, staff, "sick", dt.date(2026, 3, 1), dt.date(2026, 3, 10), 8)
    _approve(sick, boss)
    c.refresh_from_db()
    assert c.extension_days == 10
    assert c.probation_end == dt.date(2026, 7, 11)
    _approve_again = LeaveRequest.objects.get(pk=sick.pk)
    from staff_affairs.probation import refresh_for_leave

    refresh_for_leave(_approve_again)  # idempotent
    c.refresh_from_db()
    assert c.extension_days == 10


def test_sick_extension_is_capped_at_probation_length(setup):
    school, staff, boss = setup
    c = open_contract(school, staff, START, 1, boss)  # شهر واحد = 31 يوماً
    sick = _leave(school, staff, "sick", dt.date(2026, 1, 5), dt.date(2026, 3, 20), 50)
    _approve(sick, boss)
    c.refresh_from_db()
    assert c.extension_days == 31


def test_maternity_is_not_counted_in_probation(setup):
    school, staff, boss = setup
    c = open_contract(school, staff, START, 6, boss)
    mat = _leave(school, staff, "maternity", dt.date(2026, 2, 1), dt.date(2026, 2, 20), 20)
    _approve(mat, boss)
    c.refresh_from_db()
    assert c.extension_days == 20


def test_result_cannot_precede_end_or_be_changed(setup):
    school, staff, boss = setup
    c = open_contract(school, staff, START, 6, boss)
    with pytest.raises(ValueError):
        record_result(c, "passed", boss, dt.date(2026, 6, 30))
    record_result(c, "passed", boss, dt.date(2026, 7, 2))
    with pytest.raises(ValueError):
        record_result(c, "failed", boss, dt.date(2026, 7, 3))


def test_annual_after_passing_is_prorated(setup):
    """سنةٌ 2025-09-01..2026-06-30 (303 يوماً): الاختبار انتهى 03-01 فبقي 120 يوماً → 30×120/303 ≈ 12."""
    school, staff, boss = setup
    c = open_contract(school, staff, dt.date(2025, 9, 1), 6, boss)
    record_result(c, "passed", boss, dt.date(2026, 3, 2))
    leave = _leave(school, staff, "annual", dt.date(2026, 4, 5), dt.date(2026, 4, 7), 3)
    _approve(leave, boss)
    bal = LeaveBalance.objects.get(staff=staff, leave_type="annual")
    assert bal.total_days == 12 and bal.used_days == 3


def test_admin_add_contract_computes_end_dates(client, setup):
    """إضافةُ عقدٍ من Django admin لا تنهار وتُحسب نهايتاه بخدمة الاختبار."""
    from django.urls import reverse

    school, staff, _ = setup
    root = UserFactory(is_staff=True, is_superuser=True)
    client.force_login(root)
    resp = client.post(
        reverse("admin:staff_affairs_employmentcontract_add"),
        {
            "school": school.pk,
            "staff": staff.pk,
            "contract_ref": "ع-2026/18",
            "contract_start": "2026-01-01",
            "probation_months": 6,
            "result": "pending",
        },
    )
    assert resp.status_code == 302, getattr(resp, "context", None) and resp.context["errors"]
    c = EmploymentContract.objects.get(school=school, staff=staff)
    assert c.contract_ref == "ع-2026/18"
    assert c.base_end == dt.date(2026, 7, 1) == c.probation_end
    assert c.extension_days == 0 and c.created_by == root


def _admin_post(client, school, staff, **extra):
    from django.urls import reverse

    data = {
        "school": school.pk,
        "staff": staff.pk,
        "contract_ref": "ع-2026/19",
        "contract_start": "2026-01-01",
        "probation_months": 6,
        **extra,
    }
    return client.post(reverse("admin:staff_affairs_employmentcontract_add"), data)


def test_admin_add_with_existing_sick_leave_extends_end(client, setup):
    school, staff, boss = setup
    _approve(_leave(school, staff, "sick", dt.date(2026, 3, 1), dt.date(2026, 3, 10), 8), boss)
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    assert _admin_post(client, school, staff).status_code == 302
    c = EmploymentContract.objects.get(school=school, staff=staff)
    assert c.base_end == dt.date(2026, 7, 1)
    assert c.extension_days == 10 and c.probation_end == dt.date(2026, 7, 11)


def test_admin_add_ignores_posted_result(client, setup):
    school, staff, _ = setup
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    assert _admin_post(client, school, staff, result="passed").status_code == 302
    c = EmploymentContract.objects.get(school=school, staff=staff)
    assert c.result == "pending" and c.result_at is None


def test_admin_change_keeps_computed_dates_and_locks_start_and_months(client, setup):
    from django.urls import reverse

    school, staff, boss = setup
    c = open_contract(school, staff, START, 6, boss)
    _approve(_leave(school, staff, "sick", dt.date(2026, 3, 1), dt.date(2026, 3, 10), 8), boss)
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    resp = client.post(
        reverse("admin:staff_affairs_employmentcontract_change", args=[c.pk]),
        {
            "school": school.pk,
            "staff": staff.pk,
            "contract_ref": "ع-معدَّل",
            "contract_start": "2026-02-01",  # يُتجاهل: للقراءة فقط
            "probation_months": 3,
            "result": "pending",
        },
    )
    assert resp.status_code == 302
    c.refresh_from_db()
    assert c.contract_ref == "ع-معدَّل"
    assert c.contract_start == START and c.probation_months == 6
    assert c.base_end == dt.date(2026, 7, 1) and c.probation_end == dt.date(2026, 7, 11)
