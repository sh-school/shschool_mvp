from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html

from .models import (
    ClassGroup,
    CustomUser,
    Membership,
    ParentStudentLink,
    Profile,
    Role,
    School,
    StudentEnrollment,
)


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 1
    fields = ("school", "role", "is_active", "joined_at")


class ProfileInline(admin.StackedInline):
    model = Profile
    extra = 0
    fields = ("gender", "birth_date", "notes")


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """
    ✅ v5.4 PDPPL م.8: الرقم الوطني مُخفًى في قائمة المستخدمين (آخر 4 أرقام فقط).
    يظهر كاملاً في نموذج التعديل للمسؤول المعتمد فقط.
    """

    model = CustomUser
    # ── PDPPL: نستخدم masked_national_id بدل national_id في القائمة ──
    list_display = ("masked_national_id", "full_name", "email", "is_active", "date_joined")
    list_filter = ("is_active", "is_staff", "memberships__role__name")
    search_fields = ("national_id", "full_name", "email")
    ordering = ("full_name",)
    inlines = [ProfileInline, MembershipInline]
    fieldsets = (
        (None, {"fields": ("national_id", "password")}),
        ("المعلومات", {"fields": ("full_name", "email", "phone")}),
        (
            "الصلاحيات",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("التواريخ", {"fields": ("date_joined",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("national_id", "full_name", "password1", "password2"),
            },
        ),
    )

    @admin.display(description="الرقم الوطني", ordering="national_id")
    def masked_national_id(self, obj: CustomUser) -> str:
        """
        PDPPL م.8 — يعرض آخر 4 أرقام فقط في قائمة المستخدمين.
        الرقم الكامل متاح في نموذج التعديل للمسؤول المعتمد.
        """
        nid = obj.national_id or ""
        if len(nid) <= 4:
            return "****"
        suffix = nid[-4:]
        return format_html(
            '<span title="الرقم الوطني — مخفي (PDPPL م.8)" style="font-family:monospace">****{}</span>',
            suffix,
        )


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "abbreviation",
        "city",
        "school_type",
        "education_level",
        "principal",
        "is_active",
    )
    list_filter = ("is_active", "school_type", "education_level", "city")
    search_fields = ("name", "code", "abbreviation", "ministry_code")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("principal",)

    fieldsets = (
        (
            "المعلومات الأساسية",
            {
                "fields": (
                    "name",
                    "code",
                    "abbreviation",
                    "ministry_code",
                    "school_type",
                    "education_level",
                    "established_year",
                ),
            },
        ),
        (
            "الاتصال",
            {
                "fields": ("phone", "fax", "email", "website"),
            },
        ),
        (
            "العنوان",
            {
                "fields": ("city", "zone", "address", "po_box"),
            },
        ),
        (
            "الإدارة",
            {
                "fields": ("principal",),
            },
        ),
        (
            "الهوية البصرية",
            {
                "fields": ("logo",),
                "classes": ("collapse",),
            },
        ),
        (
            "النظام",
            {
                "fields": ("is_active", "created_at"),
            },
        ),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("school", "name", "get_name_display")
    list_filter = ("name", "school")
    search_fields = ("name",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "role", "is_active", "joined_at")
    list_filter = ("is_active", "school", "role__name")
    list_select_related = ("user", "school", "role")
    search_fields = ("user__full_name", "user__national_id")
    autocomplete_fields = ("user",)


@admin.register(ClassGroup)
class ClassGroupAdmin(admin.ModelAdmin):
    list_display = ("school", "grade", "section", "academic_year", "is_active")
    list_filter = ("school", "grade", "academic_year", "is_active")
    search_fields = ("grade", "section")
    autocomplete_fields = ("supervisor",)


@admin.register(StudentEnrollment)
class StudentEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "class_group", "is_active", "enrolled_at")
    list_filter = ("is_active", "class_group__grade")
    list_select_related = ("student", "class_group__school")
    search_fields = ("student__full_name", "student__national_id")
    autocomplete_fields = ("student", "class_group")


admin.site.site_header = "SchoolOS — مدرسة الشحانية"
admin.site.site_title = "SchoolOS Admin"
admin.site.index_title = "لوحة إدارة النظام"


@admin.register(ParentStudentLink)
class ParentStudentLinkAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "parent",
        "relationship",
        "school",
        "can_view_grades",
        "can_view_attendance",
    )
    list_filter = ("school", "relationship", "can_view_grades", "can_view_attendance")
    list_select_related = ("student", "parent", "school")
    search_fields = (
        "parent__full_name",
        "parent__national_id",
        "student__full_name",
        "student__national_id",
    )
    autocomplete_fields = ("parent", "student")


# ── AuditLog Admin ─────────────────────────────────────────────
from core.models import AuditLog, ConsentRecord


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "user",
        "action",
        "model_name",
        "object_repr",
        "ip_address",
        "school",
    )
    list_filter = ("action", "model_name", "school")
    list_select_related = ("user", "school")
    search_fields = ("user__full_name", "object_repr", "ip_address")
    readonly_fields = (
        "id",
        "timestamp",
        "user",
        "action",
        "model_name",
        "object_id",
        "object_repr",
        "changes",
        "ip_address",
        "user_agent",
        "school",
    )
    autocomplete_fields = ("user",)
    ordering = ("-timestamp",)
    date_hierarchy = "timestamp"

    def has_add_permission(self, request):
        return False  # لا يمكن إنشاء سجلات يدوياً

    def has_change_permission(self, request, obj=None):
        return False  # للقراءة فقط

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = (
        "parent",
        "student",
        "data_type",
        "is_given",
        "method",
        "given_at",
        "withdrawn_at",
    )
    list_filter = ("data_type", "is_given", "method", "school")
    search_fields = ("parent__full_name", "student__full_name")
    autocomplete_fields = ("parent", "student", "recorded_by")
    readonly_fields = ("given_at", "withdrawn_at")
