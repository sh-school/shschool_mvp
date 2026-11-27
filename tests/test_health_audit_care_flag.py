"""تدقيقُ ظهور علامة «يحتاج مراعاةً» في اختيار الطالب بالعيادة (CLN-03، W-20261127-012)."""

import pytest
from django.core.cache import cache
from django.urls import reverse

from clinic.models import ClinicVisit, HealthRecord
from core.models import AuditLog

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

# كلُّ استجابةٍ تعرض العلامة: مداخلُ الاختيار، وقائمةُ الزوّار داخل صفحتَي الإدخال.
RESPONSES = [
    "quick_search",
    "quick_class",
    "quick_recent",
    "quick_pick",
    "quick_entry",
    "record_visit",
    "record_visit_student",
]


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()


@pytest.fixture
def visitor(school, nurse_user, student_user, enrolled_student):
    """طالبٌ في شعبةٍ زار العيادةَ فيظهر في المداخل كلِّها."""
    ClinicVisit.objects.create(school=school, student=student_user, nurse=nurse_user, reason="سبب")
    return student_user


def _open(client, name, student):
    group = student.enrollments.get().class_group
    params = {
        "quick_search": {"q": student.full_name},
        "quick_class": {"cls": f"{group.grade}|{group.section}"},
        "quick_pick": {"student_id": str(student.pk)},
    }.get(name, {})
    args = [student.pk] if name == "record_visit_student" else []
    response = client.get(reverse(f"clinic:{name}", args=args), params)
    assert response.status_code == 200
    assert student.full_name in response.content.decode()


def _lines(user):
    lines = AuditLog.objects.filter(user=user, action="view").order_by("timestamp")
    return [line for line in lines if (line.changes or {}).get("screen") == "علامة المراعاة"]


@pytest.mark.parametrize("name", RESPONSES)
def test_flag_shown_writes_one_line_with_ids_only(client_as, nurse_user, visitor, name):
    HealthRecord.objects.create(student=visitor, needs_care=True)
    client = client_as(nurse_user)

    for _ in range(3):
        _open(client, name, visitor)

    (line,) = _lines(nurse_user)
    assert line.changes == {"screen": "علامة المراعاة", "rows": 1, "students": [str(visitor.pk)]}
    assert visitor.full_name not in f"{line.object_repr} {line.object_id} {line.changes}"


@pytest.mark.parametrize("name", RESPONSES)
def test_no_flag_no_line(client_as, nurse_user, visitor, name):
    HealthRecord.objects.create(student=visitor, needs_care=False)

    _open(client_as(nurse_user), name, visitor)

    assert _lines(nurse_user) == []


def test_repeated_search_and_other_entries_share_one_line(client_as, nurse_user, visitor):
    HealthRecord.objects.create(student=visitor, needs_care=True)
    client = client_as(nurse_user)

    for name in ["quick_search", "quick_search", *RESPONSES]:
        _open(client, name, visitor)

    assert len(_lines(nurse_user)) == 1
