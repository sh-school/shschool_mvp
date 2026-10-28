from django.urls import path

from . import quick_views, referral_views, supply_views, views

app_name = "clinic"

urlpatterns = [
    path("", views.clinic_dashboard, name="dashboard"),
    path("counts/", views.clinic_counts, name="counts"),
    path("student/<uuid:student_id>/record/", views.student_health_record, name="health_record"),
    path("needs-care/import/", views.needs_care_import, name="needs_care_import"),
    path("visit/new/", views.record_visit, name="record_visit"),
    path("quick/", quick_views.quick_entry, name="quick_entry"),
    path("quick/search/", quick_views.quick_search, name="quick_search"),
    path("quick/start/", quick_views.quick_start, name="quick_start"),
    path("quick/queue/", quick_views.quick_queue, name="quick_queue"),
    path("quick/<uuid:visit_id>/service/", quick_views.quick_service, name="quick_service"),
    path("quick/<uuid:visit_id>/close/", quick_views.quick_close, name="quick_close"),
    path("visit/new/<uuid:student_id>/", views.record_visit, name="record_visit_student"),
    path("visits/", views.visits_list, name="visits_list"),
    path("referrals/", referral_views.referrals_list, name="referrals"),
    path(
        "referrals/<uuid:referral_id>/close/", referral_views.referral_close, name="referral_close"
    ),
    path(
        "referrals/<uuid:referral_id>/receipt/",
        referral_views.referral_receipt,
        name="referral_receipt",
    ),
    path(
        "visit/<uuid:visit_id>/confirm-referral/",
        views.confirm_referral_notice,
        name="confirm_referral_notice",
    ),
    path("supplies/", supply_views.supplies_list, name="supplies"),
    path("supplies/add/", supply_views.supply_add, name="supply_add"),
    path("supplies/<uuid:item_id>/delete/", supply_views.supply_delete, name="supply_delete"),
    path("statistics/", views.health_statistics, name="statistics"),
    path("api/charts/", views.api_clinic_charts, name="api_clinic_charts"),
]
