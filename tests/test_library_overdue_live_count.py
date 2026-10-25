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


@pytest.mark.django_db
def test_today_is_the_doha_date_not_the_utc_date_after_midnight(school, teacher_user, monkeypatch):
    """بين 00:00 و03:00 بتوقيت الدوحة يكون تاريخ UTC ما زال أمس (W-20261010-009): إعارةٌ موعدُها أمس بالدوحة
    متأخّرةٌ، ولا يعدّها حسابُ «اليوم» بتاريخ UTC. الساعةُ تُثبَّت عند 00:30 بالدوحة (21:30 UTC)."""
    frozen = datetime.datetime(2026, 10, 10, 21, 30, tzinfo=datetime.UTC)
    monkeypatch.setattr(timezone, "now", lambda: frozen)
    assert timezone.localdate() == datetime.date(2026, 10, 11)  # الدوحة، لا 10-10 (UTC)
    book = LibraryBook.objects.create(school=school, title="كتاب", author="مؤلف")
    BookBorrowing.objects.create(
        book=book, user=teacher_user, status="BORROWED", due_date=datetime.date(2026, 10, 10)
    )

    assert BookBorrowing.objects.filter(book__school=school).late().count() == 1
    assert LibraryService.get_dashboard_stats(school)["overdue"] == 1
