from django.urls import path

from core.views_students import (
    student_export_excel,
    student_import_export,
    student_import_template,
)

urlpatterns = [
    path("", student_import_export, name="student_import_export"),
    path("export/", student_export_excel, name="student_export_excel"),
    path("template/", student_import_template, name="student_import_template"),
]
