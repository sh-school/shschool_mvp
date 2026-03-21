"""
tests/test_views_library.py
اختبارات views المكتبة
"""
import pytest
from core.models import LibraryBook, BookBorrowing
from .conftest import LibraryBookFactory, BookBorrowingFactory


@pytest.mark.django_db
class TestLibraryDashboard:

    def test_dashboard_loads_for_librarian(self, client_as, librarian_user, school, library_book):
        client = client_as(librarian_user)
        response = client.get("/library/dashboard/")
        assert response.status_code == 200
        assert "total_books" in response.context
        assert "active_borrowings" in response.context
        assert "overdue_borrowings" in response.context

    def test_dashboard_shows_correct_count(self, client_as, librarian_user, school, library_book):
        client = client_as(librarian_user)
        response = client.get("/library/dashboard/")
        assert response.context["total_books"] >= 1


@pytest.mark.django_db
class TestBookList:

    def test_book_list_loads(self, client_as, teacher_user, school, library_book):
        """staff_required — المعلم يمكنه رؤية الكتب"""
        client = client_as(teacher_user)
        response = client.get("/library/books/")
        assert response.status_code == 200
        assert "books" in response.context

    def test_search_by_title(self, client_as, teacher_user, school, library_book):
        client = client_as(teacher_user)
        response = client.get(f"/library/books/?q={library_book.title}")
        assert response.status_code == 200
        books = response.context["books"]
        assert any(b.id == library_book.id for b in books)

    def test_search_no_results(self, client_as, teacher_user, school):
        client = client_as(teacher_user)
        response = client.get("/library/books/?q=XXXXXXXXX_لا_يوجد")
        assert response.status_code == 200
        assert len(response.context["books"]) == 0


@pytest.mark.django_db
class TestBorrowBook:

    def test_borrow_form_loads(self, client_as, librarian_user, school, library_book):
        client = client_as(librarian_user)
        response = client.get("/library/borrow/")
        assert response.status_code == 200
        assert "books" in response.context
        assert "borrowers" in response.context

    def test_post_creates_borrowing(
        self, client_as, librarian_user, school, library_book, student_user
    ):
        from datetime import date, timedelta
        client = client_as(librarian_user)
        count_before = BookBorrowing.objects.count()
        response = client.post("/library/borrow/", {
            "book_id": str(library_book.id),
            "user_id": str(student_user.id),
            "due_date": (date.today() + timedelta(days=14)).strftime("%Y-%m-%d"),
        })
        assert response.status_code in (200, 302)
        assert BookBorrowing.objects.count() > count_before

    def test_post_reduces_available_qty(
        self, client_as, librarian_user, school, library_book, student_user
    ):
        from datetime import date, timedelta
        initial_qty = library_book.available_qty
        client = client_as(librarian_user)
        client.post("/library/borrow/", {
            "book_id": str(library_book.id),
            "user_id": str(student_user.id),
            "due_date": (date.today() + timedelta(days=14)).strftime("%Y-%m-%d"),
        })
        refreshed = LibraryBook.objects.get(id=library_book.id)
        assert refreshed.available_qty == initial_qty - 1

    def test_unavailable_book_not_borrowed(
        self, client_as, librarian_user, school, student_user
    ):
        unavailable = LibraryBookFactory(school=school, quantity=1, available_qty=0)
        from datetime import date, timedelta
        client = client_as(librarian_user)
        count_before = BookBorrowing.objects.count()
        client.post("/library/borrow/", {
            "book_id": str(unavailable.id),
            "user_id": str(student_user.id),
            "due_date": (date.today() + timedelta(days=14)).strftime("%Y-%m-%d"),
        })
        assert BookBorrowing.objects.count() == count_before


@pytest.mark.django_db
class TestReturnBook:

    def test_return_changes_status(
        self, client_as, librarian_user, school, book_borrowing
    ):
        client = client_as(librarian_user)
        response = client.get(f"/library/return/{book_borrowing.id}/")
        assert response.status_code in (200, 302)
        refreshed = BookBorrowing.objects.get(id=book_borrowing.id)
        assert refreshed.status == "RETURNED"

    def test_return_increases_available_qty(
        self, client_as, librarian_user, school, book_borrowing
    ):
        book = book_borrowing.book
        initial_qty = book.available_qty
        client = client_as(librarian_user)
        client.get(f"/library/return/{book_borrowing.id}/")
        refreshed_book = LibraryBook.objects.get(id=book.id)
        assert refreshed_book.available_qty == initial_qty + 1
