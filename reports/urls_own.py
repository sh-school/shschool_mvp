from django.urls import path

from . import views

# كشفُ الطالب لنتيجته هو — يُحمَّل بالاسم من shschool/urls.py كي لا يتتبّع mypy استيرادَ reports (W-20261027-031)
urlpatterns = [
    path("", views.my_result, name="my_result"),
]
