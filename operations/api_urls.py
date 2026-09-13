from django.urls import path

from . import api_views

#: كان هنا ``sessions/`` و``attendance/`` بـ``IsAuthenticated`` — الثاني يُخرج سجلَّ حضور
#: المدرسة كلِّها لأيّ حساب، طالباً كان. لا قالبَ ولا سكربتَ يستعملهما، ونظيراهما في
#: ``/api/v1/`` بـ``IsTeacherOrAdmin``. فحُذفا (مراجعةُ الصلاحيّات 2026-09-13، ن١).
urlpatterns = [
    path("students/search/", api_views.student_search_api, name="api_student_search"),
]
