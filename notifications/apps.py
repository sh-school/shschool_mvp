from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"
    verbose_name = "الإشعارات"

    def ready(self):
        from core.models.access import ALL_STAFF_ROLES
        from core.module_registry import register_module

        register_module(
            name="notifications",
            label="الإشعارات",
            url_prefix="/notifications/",
            icon="bi-bell",
            # البوّابةُ لكلّ الكادر: الصندوقُ والعدّادُ وتعليمُ المقروء بياناتُ صاحبها وحدَه
            # (``user=request.user``)، وإدارةُ الإشعارات والإرسالُ الجماعيّ محميّان بقدرتهما
            # ``notifications.broadcast``. كانت البوّابةُ تستثني عشرةَ أدوار — الكادرَ
            # المساندَ والمطوّر — فيرون الجرسَ ويُردّون عن صندوقهم (مقارنةُ القائمة 2026-09-13).
            allowed_roles=set(ALL_STAFF_ROLES) | {"specialist"},
            # وظهورُ الوحدة في القائمة كما كان — التوسيعُ للوصول لا للعرض.
            sidebar_roles={
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                "specialist",
                "social_worker",
                "psychologist",
                "academic_advisor",
                "admin_supervisor",
                "nurse",
                "librarian",
                "bus_supervisor",
                "admin",
                "secretary",
                "it_technician",
                # v7
                "activities_coordinator",
                "e_projects_coordinator",
                "teacher_assistant",
                "ese_assistant",
                "speech_therapist",
                "occupational_therapist",
                "receptionist",
                "transport_officer",
            },
            sort_order=80,
        )
