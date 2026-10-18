from django.contrib import admin

from .models import EmploymentContract, LeaveBalance, LeaveRequest
from .probation import open_contract


@admin.register(EmploymentContract)
class EmploymentContractAdmin(admin.ModelAdmin):
    list_display = (
        "staff",
        "contract_ref",
        "contract_start",
        "probation_end",
        "extension_days",
        "result",
    )
    list_filter = ("result",)
    search_fields = ("staff__full_name", "contract_ref")
    # النهايةُ والتمديد تحسبهما خدمةُ الاختبار لا اليد
    readonly_fields = (
        "base_end",
        "probation_end",
        "extension_days",
        "result_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )

    def get_readonly_fields(self, request, obj=None):
        # المدرسةُ والموظفُ والبدايةُ والمدّةُ تحدّد الاحتسابَ، والنتيجةُ تُسجَّل بـrecord_result وحدَها؛ فلا تُعدَّل بعد الإضافة
        fields = super().get_readonly_fields(request, obj)
        if obj is not None:
            fields = (*fields, "school", "staff", "contract_start", "probation_months", "result")
        return fields

    def get_exclude(self, request, obj=None):
        # النتيجةُ تُسجَّل بخدمة الاختبار (record_result) لا من نموذج الإضافة
        return ("result",) if obj is None else None

    def save_model(self, request, obj, form, change):
        """الإضافةُ تمرّ بخدمة الاختبار لتحسب base_end وprobation_end؛ والتعديلُ يبقى كما هو."""
        if change:
            super().save_model(request, obj, form, change)
            return
        saved = open_contract(
            obj.school,
            obj.staff,
            obj.contract_start,
            obj.probation_months,
            request.user,
            contract_ref=obj.contract_ref,
        )
        # يُعاد ملءُ الكائن المُدار من النموذج ليكمل admin التسجيلَ والتحويل
        obj.__dict__.update(saved.__dict__)


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = (
        "staff",
        "leave_type",
        "total_days",
        "used_days",
        "days_left",
        "academic_year",
    )
    list_filter = ("leave_type", "academic_year")
    search_fields = ("staff__full_name", "staff__national_id")

    @admin.display(description="الأيّام المتبقّية")
    def days_left(self, obj):
        return obj.remaining_days


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        "staff",
        "leave_type",
        "start_date",
        "end_date",
        "days_count",
        "status",
        "academic_year",
    )
    list_filter = ("status", "leave_type", "academic_year")
    search_fields = ("staff__full_name", "staff__national_id")
    date_hierarchy = "start_date"
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")
