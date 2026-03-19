from django.contrib import admin
from core.models import LibraryBook, BookBorrowing, LibraryActivity

@admin.register(LibraryBook)
class LibraryBookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'book_type', 'available_qty', 'location')
    list_filter = ('school', 'book_type', 'category')
    search_fields = ('title', 'author', 'isbn')

@admin.register(BookBorrowing)
class BookBorrowingAdmin(admin.ModelAdmin):
    list_display = ('book', 'user', 'borrow_date', 'due_date', 'status')
    list_filter = ('status', 'borrow_date', 'due_date')
    search_fields = ('book__title', 'user__full_name')

@admin.register(LibraryActivity)
class LibraryActivityAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'school')
    list_filter = ('date', 'school')
    search_fields = ('title', 'description')
