from django.apps import AppConfig


class StudentInfoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "student_info"
    verbose_name = "مركز معلومات الطلبة"

    def ready(self):
        from core.module_registry import register_module
        from student_info.access import MODULE_ROLES

        # بوّابةُ الوحدة تطابق `MODULE_ROLES` حرفياً: دورٌ مسموحٌ في
        # `access.py` ومحجوبٌ هنا يُردّ قبل أن تُقرأ صلاحيتُه أصلاً.
        register_module(
            name="student_info",
            label="مركز معلومات الطلبة",
            url_prefix="/student-info/",
            icon="bi-person-vcard",
            allowed_roles=set(MODULE_ROLES),
            sidebar_roles=set(MODULE_ROLES),
            sort_order=25,
        )
