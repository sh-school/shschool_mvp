"""
library/views.py
وحدة المكتبة المدرسية
[مهمة 8] إضافة Pagination لقائمة الكتب (25 كتاب/صفحة)
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.models import BookBorrowing, CustomUser, LibraryBook
from core.permissions import LIBRARY_FULL, LIBRARY_VIEW, librarian_required, role_required
from library.services import LibraryService


@login_required
@role_required(LIBRARY_VIEW | LIBRARY_FULL)
def library_dashboard(request):
    """لوحة تحكم المكتبة"""
    school = request.user.get_school()

    # ✅ v5.4: LibraryService.get_dashboard_context — جميع الـ queries في service layer
    context = LibraryService.get_dashboard_context(school)
    context["maroon_color"] = "#8A1538"
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

        book = get_object_or_404(LibraryBook, id=book_id)
        user = get_object_or_404(CustomUser, id=user_id)

        try:
            # ✅ v5.4: LibraryService.borrow_book — select_for_update + atomic
            # يمنع race condition عند إعارة النسخة الأخيرة من أكثر من مستخدم
            LibraryService.borrow_book(
                book=book,
                user=user,
                librarian=request.user,
            )
            messages.success(request, f"تمت إعارة كتاب '{book.title}' للطالب {user.full_name}")
        except ValueError as e:
            messages.error(request, str(e))

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

    try:
        # ✅ v5.4: LibraryService.return_book — select_for_update + atomic
        borrowing = LibraryService.return_book(borrowing)
        messages.success(request, f"تم إرجاع كتاب '{borrowing.book.title}' بنجاح.")
    except ValueError as e:
        messages.error(request, str(e))

    return redirect("library:dashboard")


@login_required
@role_required(LIBRARY_VIEW | LIBRARY_FULL)
def api_library_charts(request):
    """API: بيانات الرسوم البيانية للمكتبة"""
    school = request.user.get_school()

    # ✅ v5.4: LibraryService.get_chart_data — queries في service layer
    data = LibraryService.get_chart_data(school)
    return JsonResponse(data)
