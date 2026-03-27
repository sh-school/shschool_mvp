"""
library/services.py — خدمات المكتبة المدرسية
═══════════════════════════════════════════════
Business logic للإعارة والإرجاع والإحصائيات.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import models, transaction
from django.utils import timezone

from library.models import BookBorrowing, LibraryActivity, LibraryBook

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School


class LibraryService:
    """خدمات المكتبة — الإعارة والإرجاع والإحصائيات."""

    DEFAULT_BORROW_DAYS = 14  # مدة الإعارة الافتراضية

    @staticmethod
    @transaction.atomic
    def borrow_book(
        book: LibraryBook,
        user: CustomUser,
        librarian: CustomUser | None = None,
        days: int = 14,
    ) -> BookBorrowing:
        """
        إعارة كتاب — ينقص available_qty ويُنشئ سجل إعارة.
        يرفع ValueError إذا لم يتوفر نسخ.
        """
        # قفل الصف لمنع race condition
        book = LibraryBook.objects.select_for_update().get(pk=book.pk)
        if book.available_qty <= 0:
            raise ValueError(f"الكتاب '{book.title}' غير متوفر للإعارة")

        due_date = timezone.now().date() + timedelta(days=days)
        borrowing = BookBorrowing.objects.create(
            book=book,
            user=user,
            due_date=due_date,
            status="BORROWED",
            librarian=librarian,
        )
        book.available_qty -= 1
        book.save(update_fields=["available_qty"])
        return borrowing

    @staticmethod
    @transaction.atomic
    def return_book(borrowing: BookBorrowing) -> BookBorrowing:
        """
        إرجاع كتاب — يزيد available_qty ويحدّث حالة الإعارة.
        """
        if borrowing.status in ("RETURNED",):
            raise ValueError("هذه الإعارة مُرجعة بالفعل")

        borrowing = BookBorrowing.objects.select_for_update().get(pk=borrowing.pk)
        book = LibraryBook.objects.select_for_update().get(pk=borrowing.book_id)

        borrowing.status = "RETURNED"
        borrowing.return_date = timezone.now().date()
        borrowing.save(update_fields=["status", "return_date"])

        book.available_qty = min(book.available_qty + 1, book.quantity)
        book.save(update_fields=["available_qty"])
        return borrowing

    @staticmethod
    @transaction.atomic
    def mark_lost(borrowing: BookBorrowing) -> BookBorrowing:
        """تسجيل كتاب كمفقود — لا يُعاد المتاح."""
        borrowing.status = "LOST"
        borrowing.save(update_fields=["status"])
        return borrowing

    @staticmethod
    def mark_overdue_books() -> int:
        """
        تحديث حالة الكتب المتأخرة — يُشغّل يومياً (Celery beat).
        يُعيد عدد السجلات المحدّثة.
        """
        today = timezone.now().date()
        return BookBorrowing.objects.filter(
            status="BORROWED",
            due_date__lt=today,
        ).update(status="OVERDUE")

    @staticmethod
    def get_student_borrowings(user: CustomUser) -> models.QuerySet:
        """إعارات الطالب الحالية والسابقة."""
        return (
            BookBorrowing.objects.filter(user=user)
            .select_related("book", "librarian")
            .order_by("-borrow_date")
        )

    @staticmethod
    def get_dashboard_stats(school: School) -> dict:
        """إحصائيات لوحة المكتبة."""
        books = LibraryBook.objects.filter(school=school)
        borrowings = BookBorrowing.objects.filter(book__school=school)
        today = timezone.now().date()

        total_books = books.count()
        total_copies = books.aggregate(s=models.Sum("quantity"))["s"] or 0
        available = books.aggregate(s=models.Sum("available_qty"))["s"] or 0
        active_borrowings = borrowings.filter(status="BORROWED").count()
        overdue = borrowings.filter(status="BORROWED", due_date__lt=today).count()
        lost = borrowings.filter(status="LOST").count()

        # الأكثر إعارة (top 5)
        popular = (
            borrowings.values("book__title")
            .annotate(count=models.Count("id"))
            .order_by("-count")[:5]
        )

        return {
            "total_books": total_books,
            "total_copies": total_copies,
            "available_copies": available,
            "active_borrowings": active_borrowings,
            "overdue": overdue,
            "lost": lost,
            "popular_books": list(popular),
        }

    @staticmethod
    def search_books(school: School, query: str) -> models.QuerySet:
        """بحث في كتب المدرسة."""
        return LibraryBook.objects.filter(school=school).search(query)
