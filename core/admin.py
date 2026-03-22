from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

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
    model = CustomUser
    list_display = ("national_id", "full_name", "email", "is_active", "date_joined")
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


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "city", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("school", "name", "get_name_display")
    list_filter = ("name", "school")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "role", "is_active", "joined_at")
    list_filter = ("is_active", "school", "role__name")
    search_fields = ("user__full_name", "user__national_id")
    raw_id_fields = ("user",)


@admin.register(ClassGroup)
class ClassGroupAdmin(admin.ModelAdmin):
    list_display = ("school", "grade", "section", "academic_year", "is_active")
    list_filter = ("school", "grade", "academic_year", "is_active")
    search_fields = ("section",)


@admin.register(StudentEnrollment)
class StudentEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "class_group", "is_active", "enrolled_at")
    list_filter = ("is_active", "class_group__grade")
    search_fields = ("student__full_name", "student__national_id")
    raw_id_fields = ("student",)


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
    search_fields = (
        "parent__full_name",
        "parent__national_id",
        "student__full_name",
        "student__national_id",
    )
    raw_id_fields = ("parent", "student")


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
    readonly_fields = ("given_at", "withdrawn_at")
