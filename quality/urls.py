from django.urls import path
from . import views

urlpatterns = [
    # الخطة التشغيلية
    path("",                                     views.plan_dashboard,          name="quality_dashboard"),
    path("domain/<uuid:domain_id>/",             views.domain_detail,           name="domain_detail"),
    path("procedure/<uuid:proc_id>/",            views.procedure_detail,        name="procedure_detail"),
    path("procedure/<uuid:proc_id>/status/",     views.update_procedure_status, name="update_proc_status"),
    path("procedure/<uuid:proc_id>/evidence/",   views.upload_evidence,         name="upload_evidence"),
    path("my-procedures/",                       views.my_procedures,           name="my_procedures"),
    path("report/",                              views.progress_report,         name="quality_report"),

    # لجنة التنفيذ
    path("committee/",                           views.quality_committee,       name="quality_committee"),
    path("committee/add/",                       views.add_committee_member,    name="add_committee_member"),
    path("committee/remove/<uuid:member_id>/",   views.remove_committee_member, name="remove_committee_member"),

    # ربط المنفذين
    path("executor-mapping/",                    views.executor_mapping,        name="executor_mapping"),
    path("executor-mapping/save/",               views.save_executor_mapping,   name="save_executor_mapping"),
    path("executor-mapping/apply-all/",          views.apply_all_mappings,      name="apply_all_mappings"),
]
