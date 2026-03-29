"""
library/views.py
وحدة المكتبة المدرسية
[مهمة 8] إضافة Pagination لقائمة الكتب (25 كتاب/صفحة)
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.models import BookBorrowing, CustomUser, LibraryBook
from core.permissions import LIBRARY_FULL, LIBRARY_VIEW, librarian_required, role_required
from library.services import LibraryService


@login_required
@role_required(LIBRARY_VIEW | LIBRARY_FULL)
def library_dashboard(request):
    """لوحة تحكم المكتبة"""
    school = request.user.get_school()
    today = timezone.now().date()

    # ── Use service for rich stats ──
    stats = LibraryService.get_dashboard_stats(school)

    total_books = stats["total_books"]
    active_borrowings = stats["active_borrowings"]
    overdue_borrowings = stats["overdue"]

    recent_books = LibraryBook.objects.filter(school=school).order_by("-id")[:5]
    recent_borrowings = BookBorrowing.objects.filter(book__school=school).select_related(
        "book", "user"
    )[:10]

    # ── Category breakdown ──
    category_stats = (
        LibraryBook.objects.filter(school=school)
        .values("category")
        .annotate(count=Count("id"))
        .order_by("-count")[:8]
    )

    # ── Due soon (next 3 days) ──
    due_soon = (
        BookBorrowing.objects.filter(
            book__school=school,
            status="BORROWED",
            due_date__lte=today + timedelta(days=3),
            due_date__gte=today,
        )
        .select_related("book", "user")
        .order_by("due_date")[:10]
    )

    context = {
        "total_books": total_books,
        "active_borrowings": active_borrowings,
        "overdue_borrowings": overdue_borrowings,
        "recent_books": recent_books,
        "recent_borrowings": recent_borrowings,
        "stats": stats,
        "category_stats": category_stats,
        "due_soon": due_soon,
        "maroon_color": "#8A1538",
    }
    return render(request, "library/dashboard.html", context)


@login_required
@role_required(LIBRARY_VIEW | LIBRARY_FULL)
def book_list(request):
    """
    قائمة الكتب مع البحث
    [مهمة 8] Pagination: 25 كتاب/صفحة
    """
    query = request.GET.get("q", "").strip()
    school = request.user.get_school()

    books = LibraryBook.objects.filter(school=school).order_by("title")
    if query:
        books = books.filter(
            Q(title__icontains=query)
            | Q(author__icontains=query)
            | Q(isbn__icontains=query)
            | Q(category__icontains=query)
        )

    paginator = Paginator(books, 25)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    context = {
        "books": page_obj,
        "page_obj": page_obj,
        "query": query,
    }

    # HTMX: أعد الجزء فقط (بحث حي + ترقيم)
    if getattr(request, "htmx", None) or request.headers.get("HX-Request"):
        return render(request, "library/partials/book_rows.html", context)

    return render(request, "library/book_list.html", context)


@login_required
@librarian_required
def borrow_book(request):
    """تسجيل عملية إعارة جديدة"""
    if request.method == "POST":
        book_id = request.POST.get("book_id")
        user_id = request.POST.get("user_id")
        due_date = request.POST.get("due_date")

        book = get_object_or_404(LibraryBook, id=book_id)
        user = get_object_or_404(CustomUser, id=user_id)

        if book.available_qty > 0:
            BookBorrowing.objects.create(
                book=book, user=user, due_date=due_date, librarian=request.user
            )
            book.available_qty -= 1
            book.save()
            messages.success(request, f"تمت إعارة كتاب '{book.title}' للطالب {user.full_name}")
        else:
            messages.error(request, "عذراً، الكتاب غير متوفر حالياً للإعارة.")

        return redirect("library:dashboard")

    school = request.user.get_school()
    books = LibraryBook.objects.filter(school=school, available_qty__gt=0)
    borrowers = (
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__is_active=True,
        )
        .order_by("full_name")
        .distinct()
    )

    return render(
        request,
        "library/borrow_form.html",
        {
            "books": books,
            "borrowers": borrowers,
        },
    )


@login_required
@librarian_required
def return_book(request, borrowing_id):
    """تسجيل إرجاع كتاب"""
    school = request.user.get_school()
    borrowing = get_object_or_404(BookBorrowing, id=borrowing_id, book__school=school)
    if borrowing.status != "RETURNED":
        borrowing.status = "RETURNED"
        borrowing.return_date = timezone.now().date()
        borrowing.save()

        book = borrowing.book
        book.available_qty += 1
        book.save()

        messages.success(request, f"تم إرجاع كتاب '{book.title}' بنجاح.")

    return redirect("library:dashboard")


@login_required
@role_required(LIBRARY_VIEW | LIBRARY_FULL)
def api_library_charts(request):
    """API: بيانات الرسوم البيانية للمكتبة"""
    school = request.user.get_school()

    # Category distribution
    cats = (
        LibraryBook.objects.filter(school=school)
        .values("category")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # Monthly borrowing trend (last 6 months)
    monthly = (
        BookBorrowing.objects.filter(
            book__school=school,
            borrow_date__gte=timezone.now().date() - timedelta(days=180),
        )
        .values(month=TruncMonth("borrow_date"))
        .annotate(count=Count("id"))
        .order_by("month")
    )

    return JsonResponse(
        {
            "categories": {
                "labels": [c["category"] or "غير مصنف" for c in cats],
                "data": [c["count"] for c in cats],
            },
            "monthly": {
                "labels": [m["month"].strftime("%m/%Y") for m in monthly],
                "data": [m["count"] for m in monthly],
            },
        }
    )
