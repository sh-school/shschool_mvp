from django.urls import path
from . import views

urlpatterns = [
    path("",                                           views.import_grades_select,    name="import_grades_select"),
    path("log/",                                       views.import_log_list,         name="import_log_list"),
    path("template/<uuid:assessment_id>/",             views.download_grade_template, name="download_grade_template"),
    path("upload/<uuid:assessment_id>/",               views.upload_grade_file,       name="upload_grade_file"),
]
