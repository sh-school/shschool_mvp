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

from library.models import BookBorrowing, LibraryBook

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
    def get_dashboard_context(school: School) -> dict:
        """
        السياق الكامل للوحة المكتبة — يجمع get_dashboard_stats + raw queries الإضافية.

        ✅ v5.4: يُحوّل 4 raw queries المتبقية في library_dashboard إلى service layer.

        Args:
            school: كائن المدرسة

        Returns:
            dict يحتوي: total_books, active_borrowings, overdue_borrowings,
                        recent_books, recent_borrowings, category_stats,
                        due_soon, stats
        """
        from django.db.models import Count

        today = timezone.now().date()
        stats = LibraryService.get_dashboard_stats(school)

        recent_books = list(LibraryBook.objects.filter(school=school).order_by("-id")[:5])

        recent_borrowings = list(
            BookBorrowing.objects.filter(book__school=school).select_related("book", "user")[:10]
        )

        category_stats = list(
            LibraryBook.objects.filter(school=school)
            .values("category")
            .annotate(count=Count("id"))
            .order_by("-count")[:8]
        )

        due_soon = list(
            BookBorrowing.objects.filter(
                book__school=school,
                status="BORROWED",
                due_date__lte=today + timedelta(days=3),
                due_date__gte=today,
            )
            .select_related("book", "user")
            .order_by("due_date")[:10]
        )

        return {
            "total_books": stats["total_books"],
            "active_borrowings": stats["active_borrowings"],
            "overdue_borrowings": stats["overdue"],
            "recent_books": recent_books,
            "recent_borrowings": recent_borrowings,
            "stats": stats,
            "category_stats": category_stats,
            "due_soon": due_soon,
        }

    @staticmethod
    def get_chart_data(school: School) -> dict:
        """
        بيانات الرسوم البيانية للمكتبة — توزيع الفئات + اتجاه الإعارة الشهري.

        ✅ v5.4: ينقل queries الـ api_library_charts إلى service layer.

        Args:
            school: كائن المدرسة

        Returns:
            dict يحتوي: categories (labels + data), monthly (labels + data)
        """
        from django.db.models import Count
        from django.db.models.functions import TruncMonth

        cats = list(
            LibraryBook.objects.filter(school=school)
            .values("category")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        monthly = list(
            BookBorrowing.objects.filter(
                book__school=school,
                borrow_date__gte=timezone.now().date() - timedelta(days=180),
            )
            .values(month=TruncMonth("borrow_date"))
            .annotate(count=Count("id"))
            .order_by("month")
        )

        return {
            "categories": {
                "labels": [c["category"] or "غير مصنف" for c in cats],
                "data": [c["count"] for c in cats],
            },
            "monthly": {
                "labels": [m["month"].strftime("%m/%Y") for m in monthly],
                "data": [m["count"] for m in monthly],
            },
        }

    @staticmethod
    def search_books(school: School, query: str) -> models.QuerySet:
        """بحث في كتب المدرسة."""
        return LibraryBook.objects.filter(school=school).search(query)
