"""
library/querysets.py — Custom QuerySets للمكتبة المدرسية
==========================================================
"""

from __future__ import annotations

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Q, QuerySet
from django.utils import timezone


class BookQuerySet(QuerySet):
    """QuerySet لـ LibraryBook."""

    def available(self) -> BookQuerySet:
        """الكتب المتاحة للاستعارة."""
        return self.filter(available_quantity__gt=0)

    def not_available(self) -> BookQuerySet:
        return self.filter(available_quantity=0)

    def digital(self) -> BookQuerySet:
        return self.filter(book_type="DIGITAL")

    def print_books(self) -> BookQuerySet:
        return self.filter(book_type="PRINT")

    def periodicals(self) -> BookQuerySet:
        return self.filter(book_type="PERIODICAL")

    def by_category(self, category: str) -> BookQuerySet:
        return self.filter(category__icontains=category)

    def search(self, query: str) -> BookQuerySet:
        """Full-Text Search في عنوان الكتاب والمؤلف والوصف."""
        if not query:
            return self
        q = query.strip()[:100]
        vector = (
            SearchVector("title", weight="A", config="arabic")
            + SearchVector("author", weight="B", config="arabic")
            + SearchVector("description", weight="C", config="arabic")
            + SearchVector("isbn", weight="D")
        )
        search_query = SearchQuery(q, config="arabic", search_type="websearch")
        return (
            self.annotate(rank=SearchRank(vector, search_query))
            .filter(Q(rank__gte=0.05) | Q(title__icontains=q) | Q(author__icontains=q))
            .order_by("-rank")
        )

    def search_simple(self, query: str) -> BookQuerySet:
        if not query:
            return self
        q = query.strip()[:100]
        return self.filter(
            Q(title__icontains=q)
            | Q(author__icontains=q)
            | Q(isbn__icontains=q)
            | Q(category__icontains=q)
        )

    def low_stock(self, threshold: int = 2) -> BookQuerySet:
        return self.filter(available_quantity__lte=threshold, available_quantity__gt=0)


class BorrowingQuerySet(QuerySet):
    """QuerySet لـ BookBorrowing."""

    def active(self) -> BorrowingQuerySet:
        return self.filter(status="BORROWED")

    def returned(self) -> BorrowingQuerySet:
        return self.filter(status="RETURNED")

    def overdue(self) -> BorrowingQuerySet:
        return self.filter(status="OVERDUE")

    def lost(self) -> BorrowingQuerySet:
        return self.filter(status="LOST")

    def for_student(self, student) -> BorrowingQuerySet:
        return self.filter(student=student)

    def overdue_today(self) -> BorrowingQuerySet:
        """تجاوز تاريخ الإعادة ولم يُعاد بعد."""
        return self.filter(
            status="BORROWED",
            due_date__lt=timezone.now().date(),
        )

    def due_soon(self, days: int = 3) -> BorrowingQuerySet:
        """تنتهي مهلتها خلال n أيام."""
        today = timezone.now().date()
        deadline = today + timezone.timedelta(days=days)
        return self.filter(
            status="BORROWED",
            due_date__gte=today,
            due_date__lte=deadline,
        )

    def with_details(self) -> BorrowingQuerySet:
        return self.select_related(
            "student",
            "book",
            "librarian",
        )
