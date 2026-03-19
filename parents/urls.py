from django.urls import path
from django.views.generic import TemplateView
from . import views

urlpatterns = [
    # بوابة ولي الأمر
    path("",                                      views.parent_dashboard,    name="parent_dashboard"),
    path("student/<uuid:student_id>/grades/",     views.student_grades,      name="parent_student_grades"),
    path("student/<uuid:student_id>/attendance/", views.student_attendance,  name="parent_student_attendance"),

    # إدارة الربط (مدير)
    path("admin/links/",                          views.manage_parent_links, name="manage_parent_links"),
    path("admin/links/add/",                      views.add_parent_link,     name="add_parent_link"),
    path("admin/links/remove/<uuid:link_id>/",    views.remove_parent_link,  name="remove_parent_link"),
    # PWA Support
    path('manifest.json',   TemplateView.as_view(template_name='parents/pwa/manifest.json',
                            content_type='application/manifest+json'), name='pwa_manifest'),
    path('sw.js',           TemplateView.as_view(template_name='parents/pwa/sw.js',
                            content_type='application/javascript'),    name='pwa_sw'),
    path('offline/',        TemplateView.as_view(template_name='parents/pwa/offline.html'), name='pwa_offline'),
    # Consent
    path('consent/',        views.consent_view,  name='parent_consent'),
]
