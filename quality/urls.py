"""
quality/urls.py — الإصلاح #4: إضافة مسارات لجنة المنفذين
"""
from django.urls import path
from . import views

urlpatterns = [
    # ── الخطة التشغيلية ──────────────────────────────────────
    path("",                                     views.plan_dashboard,          name="quality_dashboard"),
    path("domain/<uuid:domain_id>/",             views.domain_detail,           name="domain_detail"),
    path("procedure/<uuid:proc_id>/",            views.procedure_detail,        name="procedure_detail"),
    path("procedure/<uuid:proc_id>/status/",     views.update_procedure_status, name="update_proc_status"),
    path("procedure/<uuid:proc_id>/approve/",    views.approve_procedure,       name="approve_procedure"),
    path("procedure/<uuid:proc_id>/evidence/",   views.upload_evidence,         name="upload_evidence"),
    path("my-procedures/",                       views.my_procedures,           name="my_procedures"),
    path("report/",                              views.progress_report,         name="quality_report"),

    # ── لجنة المراجعة الذاتية ─────────────────────────────────
    path("committee/",                           views.quality_committee,       name="quality_committee"),
    path("committee/add/",                       views.add_committee_member,    name="add_committee_member"),
    path("committee/remove/<uuid:member_id>/",   views.remove_committee_member, name="remove_committee_member"),

    # ── لجنة منفذي الخطة التشغيلية (الإصلاح #4 — جديد) ───────
    path("executor-committee/",                              views.executor_committee,      name="executor_committee"),
    path("executor-committee/member/<uuid:member_id>/",      views.executor_member_detail,  name="executor_member_detail"),
    path("executor-committee/add/",                          views.add_committee_member,    name="add_executor_member"),
    path("executor-committee/remove/<uuid:member_id>/",      views.remove_committee_member, name="remove_executor_member"),

    # ── ربط المنفذين ──────────────────────────────────────────
    path("executor-mapping/",                    views.executor_mapping,        name="executor_mapping"),
    path("executor-mapping/save/",               views.save_executor_mapping,   name="save_executor_mapping"),
    path("executor-mapping/apply-all/",          views.apply_all_mappings,      name="apply_all_mappings"),

    # ── تقرير PDF ───────────────────────────────────────────────
    path("report/pdf/",                          views.progress_report_pdf,     name="quality_report_pdf"),
]
# (already imported views above)
