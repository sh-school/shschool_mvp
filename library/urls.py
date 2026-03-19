from django.urls import path
from . import views

app_name = 'library'

urlpatterns = [
    path('dashboard/', views.library_dashboard, name='dashboard'),
    path('books/', views.book_list, name='book_list'),
    path('borrow/', views.borrow_book, name='borrow_book'),
    path('return/<uuid:borrowing_id>/', views.return_book, name='return_book'),
]
