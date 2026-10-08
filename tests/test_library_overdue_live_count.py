"""
tests/test_library_overdue_live_count.py
الإعارات المتأخّرة تُعدّ لحظياً من التاريخ (W-20261008-001 · البند 1): لا مستدعيَ لـmark_overdue_books
فكانت لوحات المدير/التحليلات/الأمين تعرض صفراً كاذباً لإعارةٍ انقضى موعدها وحالتها BORROWED.
"""

import datetime

import pytest
from django.utils import timezone

from core.dashboard_selectors import get_director_ctx, get_service_ctx
from library.models import BookBorrowing, LibraryBook
from library.services import LibraryService


def _borrow(school, user, *, due_in_days, status="BORROWED"):
    book = LibraryBook.objects.create(school=school, title="كتاب", author="مؤلف")
    return BookBorrowing.objects.create(
        book=book,
        user=user,
        status=status,
        due_date=timezone.localdate() + datetime.timedelta(days=due_in_days),
    )


@pytest.mark.django_db
def test_late_counts_expired_borrowed_but_not_returned_or_future(school, teacher_user):
    late = _borrow(school, teacher_user, due_in_days=-3)
    _borrow(school, teacher_user, due_in_days=-3, status="RETURNED")
    _borrow(school, teacher_user, due_in_days=5)
    marked = _borrow(school, teacher_user, due_in_days=-9, status="OVERDUE")
    ids = set(BookBorrowing.objects.filter(book__school=school).late().values_list("id", flat=True))
    assert ids == {late.id, marked.id}


@pytest.mark.django_db
def test_dashboards_agree_with_library_dashboard(school, teacher_user, librarian_user):
    _borrow(school, teacher_user, due_in_days=-3)
    _borrow(school, teacher_user, due_in_days=-1)
    _borrow(school, teacher_user, due_in_days=-3, status="RETURNED")
    today = timezone.localdate()
    expected = LibraryService.get_dashboard_stats(school)["overdue"]
    assert expected == 2
    assert get_director_ctx(school, today)["library_overdue"] == expected
    assert (
        get_service_ctx(librarian_user, school, today, "librarian")["library_overdue"] == expected
    )
