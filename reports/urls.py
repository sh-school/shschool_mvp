from django.urls import path
from . import views

urlpatterns = [
    path("",                                           views.reports_index,           name="reports_index"),
    path("class/<uuid:class_id>/results/",             views.class_results_pdf,       name="class_results_pdf"),
    path("class/<uuid:class_id>/certificates/",        views.class_certificates_pdf,  name="class_certificates_pdf"),
    path("class/<uuid:class_id>/attendance/",          views.attendance_report_pdf,   name="attendance_report_pdf"),
    path("student/<uuid:student_id>/result/",          views.student_result_pdf,      name="student_result_pdf"),
    path("student/<uuid:student_id>/certificate/",     views.student_certificate_pdf, name="student_certificate_pdf"),
]
