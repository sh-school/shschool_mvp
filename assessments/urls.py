from django.urls import path
from . import views

urlpatterns = [
    path("",                                    views.assessments_dashboard, name="assessments_dashboard"),
    path("setup/",                              views.setup_subject,         name="setup_subject"),
    path("setup/<uuid:setup_id>/",              views.setup_detail,          name="setup_detail"),
    path("setup/<uuid:setup_id>/gradebook/",    views.class_gradebook,       name="class_gradebook"),
    # path("setup/<uuid:setup_id>/export/",       views.export_gradebook,      name="export_gradebook"),  # TODO: Implement export_gradebook
    # path("setup/<uuid:setup_id>/recalculate/",  views.recalculate_class,     name="recalculate_class"),  # TODO: Implement recalculate_class
    path("package/<uuid:package_id>/new/",      views.create_assessment,     name="create_assessment"),
    path("assessment/<uuid:assessment_id>/",    views.grade_entry,           name="grade_entry"),
    path("assessment/<uuid:assessment_id>/save-single/", views.save_single_grade, name="save_single_grade"),
    path("assessment/<uuid:assessment_id>/save-all/",    views.save_all_grades,   name="save_all_grades"),
    path("student/<uuid:student_id>/report/",   views.student_report,        name="student_report"),
    path("failing/",                            views.failing_students,      name="failing_students"),
]
