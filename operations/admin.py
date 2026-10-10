from typing import Any

from django.contrib import admin, messages
from django.http import HttpRequest

from core.admin import SchoolScopedAdmin

from .models import (
    AbsenceAlert,
    AbsenceExcuse,
    AttendanceDecision,
    AttendanceEntry,
    ClassExit,
    CompensatorySession,
    DailyExitTally,
    FreeSlotRegistry,
    GuardianContact,
    PeriodConfirmation,
    PermissionAuditLog,
    ScheduleBaseline,
    ScheduleConstraintOverride,
    ScheduleGeneration,
    ScheduleSlot,
    SchedulingResource,
    SectionDayConfirmation,
    Session,
    StudentAttendance,
    Subject,
    SubjectClassAssignment,
    SubstituteAssignment,
    TeacherAbsence,
    TeacherExemption,
    TeacherPreference,
    TeacherSwap,
    TemporaryPermission,
    TimeSlotConfig,
)

# ── Phase 1 ──────────────────────────────────


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name_ar", "code", "pedagogy", "school")
    list_editable = ("pedagogy",)
    list_filter = ("pedagogy", "school")
    search_fields = ("name_ar", "code")


class ReadOnlyAdminMixin:
    """قراءةٌ فقط — لا إضافةَ ولا تعديلَ ولا حذفَ ولا إجراءاتٍ جماعيّة.

    الرصدُ سندُ خصمٍ وتأديب، وسلسلتُه (إدخالٌ ← قرارٌ ← رصدٌ معتمَد) تُكتب بخدماتها وحدَها بتدقيقٍ وصلاحيّة
    (W-20261002-020). فمن عدّل صفّاً من لوحة الإدارة أفلت من كلّ ذلك — وإجراءُ «حذف المحدَّد» يتجاوز
    `has_delete_permission` في بعض الإصدارات إن لم يُعطَّل، فيُعطَّل صراحةً.
    """

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        return {}

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class AttendanceInline(ReadOnlyAdminMixin, admin.TabularInline):
    model = StudentAttendance
    extra = 0
    max_num = 0
    can_delete = False
    fields = ("student", "status", "excuse_type", "marked_by", "marked_at")
    readonly_fields = fields


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("class_group", "subject", "teacher", "date", "start_time", "status")
    # الأعمدةُ و`__str__` تقرأ هذه العلاقات لكلّ صفّ — تُجلب في استعلام القائمة نفسه (كانت ~25 سؤالاً للصفحة).
    list_select_related = ("class_group", "subject", "teacher")
    list_filter = ("school", "status", "date")
    search_fields = ("teacher__full_name", "class_group__section")
    autocomplete_fields = ("teacher", "class_group", "subject")
    date_hierarchy = "date"
    inlines = [AttendanceInline]

    def get_list_display(self, request):
        """عمودُ `provisional` — حصصُ أعمدة جدول الشعبة (W-20261005-006)."""
        return (*super().get_list_display(request), "provisional")

    def get_list_filter(self, request):
        return (*super().get_list_filter(request), "provisional")


@admin.register(StudentAttendance)
class StudentAttendanceAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "student",
        "session",
        "status",
        "late_minutes",
        "tardiness_minutes",
        "marked_by",
        "marked_at",
    )
    # الأعمدةُ و`__str__` تقرأ هذه العلاقات لكلّ صفّ — تُجلب في استعلام القائمة نفسه (كانت ~25 سؤالاً للصفحة).
    list_select_related = ("student", "session__subject", "session__class_group", "marked_by")
    list_filter = ("status", "school")
    search_fields = ("student__full_name", "student__national_id")
    date_hierarchy = "marked_at"


@admin.register(AttendanceEntry)
class AttendanceEntryAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "student",
        "session",
        "status",
        "tardiness_minutes",
        "entered_by",
        "entered_at",
        "origin",
        "supersedes",
    )
    list_select_related = ("student", "session__class_group", "entered_by")
    list_filter = ("status", "origin", "school")
    date_hierarchy = "entered_at"


@admin.register(ClassExit)
class ClassExitAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """خروجُ الطلاب من الفصل (الحصّةُ والمادّةُ والوجهةُ والوقتان وهل أُغلق بالنظام) — للقراءة والتدقيق فقط."""

    list_display = (
        "student",
        "session",
        "destination",
        "left_at",
        "returned_at",
        "continued_from",
        "system_closed",
    )
    list_select_related = ("student", "session__subject", "session__class_group", "continued_from")
    list_filter = ("destination", "system_closed", "school")
    search_fields = ("student__full_name", "student__national_id")
    date_hierarchy = "left_at"


@admin.register(DailyExitTally)
class DailyExitTallyAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """ملخّصُ خروج كلّ طالبٍ في كلّ يوم: عددُ المرّات ومجموعُ الثواني والتفصيلُ بالوجهة — مشتقٌّ من «خروجٌ من الفصل»."""

    list_display = ("student", "date", "exit_count", "total_seconds", "by_destination")
    list_select_related = ("student",)
    list_filter = ("school",)
    search_fields = ("student__full_name", "student__national_id")
    date_hierarchy = "date"


@admin.register(AttendanceDecision)
class AttendanceDecisionAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("entry", "decision", "basis", "decided_by", "decided_at")
    list_select_related = ("entry", "decided_by")
    list_filter = ("decision", "basis", "school")
    date_hierarchy = "decided_at"


@admin.register(AbsenceAlert)
class AbsenceAlertAdmin(SchoolScopedAdmin):
    """تنبيهُ الغياب يُنشئه النظامُ بعتبةٍ وفترة — فلا يُضاف ولا يُحذف ولا يُعدَّل منه إلا الحلُّ (D-201م)."""

    list_display = (
        "student",
        "absence_count",
        "gate",
        "period_start",
        "period_end",
        "status",
        "created_at",
    )
    list_select_related = ("student", "resolved_by")
    list_filter = ("status", "gate", "school")
    search_fields = ("student__full_name", "student__national_id")
    autocomplete_fields = ("resolved_by",)
    #: الحلُّ وحدَه (الحالةُ ومن عالجه) قابلٌ للتعديل؛ والباقي يكتبه النظامُ.
    readonly_fields = (
        "school",
        "student",
        "absence_count",
        "gate",
        "period_start",
        "period_end",
        "created_at",
    )

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        return {}

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class SensitiveFieldsMixin:
    """حقولُ الأسباب الصحّيّة لا تُعرض إلا للمشرف الأعلى (PDPPL: بياناتٌ ذاتُ طبيعةٍ خاصّة).

    سببُ الغياب قد يكشف مرضاً (`kind` = مرضٌ بتقريرٍ طبّيّ، والبيانُ والمستندُ وسببُ القبول أو الرفض).
    فمن دخل `/admin/` بصلاحيّة عرضٍ فقط يرى الصفَّ بلا هذه الحقول، لا نصّاً ولا في القائمة ولا بالبحث.
    """

    sensitive_fields: tuple[str, ...] = ()

    def get_fields(self, request: HttpRequest, obj: Any = None) -> list[str]:
        fields = super().get_fields(request, obj)  # type: ignore[misc]
        if request.user.is_superuser:
            return list(fields)
        return [f for f in fields if f not in self.sensitive_fields]

    def get_list_display(self, request: HttpRequest) -> Any:
        columns = super().get_list_display(request)  # type: ignore[misc]
        if request.user.is_superuser:
            return columns
        return [c for c in columns if c not in self.sensitive_fields]

    def get_list_filter(self, request: HttpRequest) -> Any:
        filters = super().get_list_filter(request)  # type: ignore[misc]
        if request.user.is_superuser:
            return filters
        return [f for f in filters if f not in self.sensitive_fields]


@admin.register(AbsenceExcuse)
class AbsenceExcuseAdmin(SensitiveFieldsMixin, ReadOnlyAdminMixin, SchoolScopedAdmin):
    """عذرُ الغياب قرارٌ مسجَّلٌ بخدمته (`operations/excuses.py`) — يُقرأ هنا ولا يُكتب."""

    list_display = (
        "student",
        "kind",
        "date_from",
        "date_to",
        "status",
        "after_deadline",
        "granted_by",
    )
    list_select_related = ("student", "granted_by")
    list_filter = ("status", "kind", "after_deadline", "school")
    search_fields = ("student__full_name", "student__national_id")
    date_hierarchy = "date_from"
    sensitive_fields = ("kind", "notes", "document", "override_reason", "rejection_reason")


@admin.register(GuardianContact)
class GuardianContactAdmin(ReadOnlyAdminMixin, SchoolScopedAdmin):
    list_display = ("student", "absence_date", "outcome", "channel", "contacted_by", "contacted_at")
    list_select_related = ("student", "contacted_by")
    list_filter = ("outcome", "channel", "school")
    search_fields = ("student__full_name", "student__national_id")
    date_hierarchy = "contacted_at"


@admin.register(SectionDayConfirmation)
class SectionDayConfirmationAdmin(ReadOnlyAdminMixin, SchoolScopedAdmin):
    list_display = (
        "class_group",
        "date",
        "present_count",
        "absent_count",
        "late_count",
        "periods_written",
        "confirmed_by",
    )
    list_select_related = ("class_group", "confirmed_by")
    list_filter = ("school", "date")
    date_hierarchy = "date"


@admin.register(PeriodConfirmation)
class PeriodConfirmationAdmin(ReadOnlyAdminMixin, SchoolScopedAdmin):
    list_display = (
        "class_group",
        "date",
        "start_time",
        "end_time",
        "present_count",
        "absent_count",
        "confirmed_late",
        "confirmed_by",
    )
    list_select_related = ("class_group", "confirmed_by")
    list_filter = ("school", "confirmed_late", "date")
    date_hierarchy = "date"


# ── Phase 2 ──────────────────────────────────


@admin.register(ScheduleSlot)
class ScheduleSlotAdmin(admin.ModelAdmin):
    list_display = (
        "day_of_week",
        "period_number",
        "teacher",
        "class_group",
        "subject",
        "start_time",
        "end_time",
        "is_active",
    )
    # الأعمدةُ و`__str__` تقرأ هذه العلاقات لكلّ صفّ — تُجلب في استعلام القائمة نفسه (كانت ~25 سؤالاً للصفحة).
    list_select_related = ("teacher", "class_group", "subject")
    list_filter = ("school", "day_of_week", "is_active", "academic_year")
    search_fields = ("teacher__full_name", "class_group__section", "subject__name_ar")
    autocomplete_fields = ("teacher", "class_group", "subject")
    ordering = ("day_of_week", "period_number")


@admin.register(TeacherAbsence)
class TeacherAbsenceAdmin(admin.ModelAdmin):
    list_display = ("teacher", "date", "reason", "status", "reported_by", "created_at")
    list_filter = ("school", "status", "reason", "date")
    search_fields = ("teacher__full_name",)
    autocomplete_fields = ("teacher", "reported_by")
    ordering = ("-date",)


@admin.register(SubstituteAssignment)
class SubstituteAssignmentAdmin(admin.ModelAdmin):
    list_display = ("absence", "slot", "substitute", "status", "assigned_by", "created_at")
    list_filter = ("school", "status")
    search_fields = ("substitute__full_name", "absence__teacher__full_name")
    autocomplete_fields = ("substitute", "assigned_by", "absence", "slot")
    ordering = ("-created_at",)


# ── Phase 3 — الجدولة الذكية ──────────────


@admin.register(TimeSlotConfig)
class TimeSlotConfigAdmin(admin.ModelAdmin):
    list_display = (
        "band",
        "day_type",
        "period_number",
        "start_time",
        "end_time",
        "is_break",
        "break_label",
    )
    list_filter = ("school", "band", "day_type", "is_break")
    list_select_related = ("band",)
    ordering = ("band__order", "day_type", "period_number")


@admin.register(SubjectClassAssignment)
class SubjectClassAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "subject",
        "class_group",
        "teacher",
        "weekly_periods",
        "requires_lab",
        "double_period",
        "is_active",
    )
    # الأعمدةُ و`__str__` تقرأ هذه العلاقات لكلّ صفّ — تُجلب في استعلام القائمة نفسه (كانت ~25 سؤالاً للصفحة).
    list_select_related = ("subject", "class_group", "teacher")
    list_filter = (
        "school",
        "academic_year",
        "subject",
        "requires_lab",
        "double_period",
        "is_active",
    )
    search_fields = ("teacher__full_name", "subject__name_ar", "class_group__section")
    autocomplete_fields = ("teacher", "class_group", "subject")
    list_editable = ("weekly_periods", "requires_lab", "double_period", "is_active")


@admin.register(SchedulingResource)
class SchedulingResourceAdmin(admin.ModelAdmin):
    """المكانُ المحدود: معملان وملعبان — والسعةُ كم حصّةً تقع فيه معاً.

    ويُدار من هنا لا من سطر أوامر: عددُ المعامل شأنُ المدرسة، يتبدّل ببناءٍ
    جديدٍ أو معملٍ يُغلق، فلا يُحبس في ترحيلٍ يحتاج مبرمجاً.
    """

    list_display = ("name", "capacity", "same_level_only", "subject_names", "is_active")
    list_filter = ("school", "is_active", "same_level_only")
    search_fields = ("name", "note")
    filter_horizontal = ("subjects",)
    list_editable = ("capacity", "same_level_only", "is_active")

    @admin.display(description="المواد التي تستعمله")
    def subject_names(self, obj):
        return "، ".join(subject.name_ar for subject in obj.subjects.all()) or "—"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("subjects")


@admin.register(ScheduleConstraintOverride)
class ScheduleConstraintOverrideAdmin(admin.ModelAdmin):
    """استثناءاتُ قيود الجدول — والصفوفُ هنا انحرافٌ عن الشيفرة لا سجلٌّ لها.

    فجدولٌ فارغٌ يعني «افتراضُ الكود بالضبط»، ولا يُنشأ صفٌّ إلّا حين تقرّر
    الإدارةُ خلافَه. ورمزُ القيد يُختار من السجلّ لا يُكتب: رمزٌ لا تعرفه
    الشيفرةُ صفٌّ ميّتٌ يوهم صاحبَه أنّه غيّر شيئاً.
    """

    list_display = ("code", "constraint_title", "break_at", "weight", "academic_year", "updated_by")
    list_filter = ("school", "academic_year", "break_at")
    search_fields = ("code", "reason")
    readonly_fields = ("updated_at",)

    @admin.display(description="القيد")
    def constraint_title(self, obj):
        from .constraint_registry import spec

        found = spec(obj.code)
        return found.title if found else "— رمزٌ لا يعرفه السجلّ —"

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        from .constraint_registry import BREAK_CHOICES

        if db_field.name == "break_at":
            kwargs["choices"] = [("", "افتراضُ الكود"), *BREAK_CHOICES]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """رمزُ القيد قائمةٌ من السجلّ — وما ليس فيه لا يُكتب."""
        from django import forms

        from .constraint_registry import REGISTRY, TUNABLE_CODES

        if db_field.name == "code":
            choices = [(code, f"{code} · {REGISTRY[code].title}") for code in sorted(TUNABLE_CODES)]
            return forms.ChoiceField(choices=choices, label=db_field.verbose_name)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def _audit(self, request, obj, action, before, after):
        """كلُّ تغييرٍ في هذه الصفوف يخفّف فرضَ قيدٍ على المدرسة كلِّها، فأثرُه ثابتٌ لا يكفيه `LogEntry`
        (توصيةُ 0105 P3): رمزُ القيد والرتبةُ والوزنُ قبل وبعد ومعرّفُ الصفّ — لا اسمَ ولا سبباً حرّاً."""
        from core.models import AuditLog

        AuditLog.objects.create(
            school=obj.school,
            user=request.user,
            action=action,
            model_name="other",
            object_id=str(obj.pk),
            object_repr=f"استثناءُ قيد {obj.code} {obj.academic_year}",
            changes={
                "event": "constraint_override_changed",
                "code": obj.code,
                "before": before,
                "after": after,
            },
        )

    @staticmethod
    def _snapshot(obj):
        return {"break_at": obj.break_at, "weight": obj.weight}

    def save_model(self, request, obj, form, change):
        before = (
            {"break_at": prev[0], "weight": prev[1]}
            if change
            and (
                prev := type(obj)
                .objects.filter(pk=obj.pk)
                .values_list("break_at", "weight")
                .first()
            )
            else None
        )
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        after = self._snapshot(obj)
        if before != after:
            self._audit(request, obj, "update" if change else "create", before, after)

    def delete_model(self, request, obj):
        before = self._snapshot(obj)
        self._audit(request, obj, "delete", before, None)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self._audit(request, obj, "delete", self._snapshot(obj), None)
        super().delete_queryset(request, queryset)


@admin.register(TeacherPreference)
class TeacherPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "teacher",
        "max_daily_periods",
        "max_consecutive",
        "max_gap",
        "max_last_periods",
        "max_first_periods",
        "free_day",
        "academic_year",
    )
    list_filter = ("school", "academic_year", "free_day")
    search_fields = ("teacher__full_name",)
    autocomplete_fields = ("teacher",)

    def save_model(self, request, obj, form, change):
        """القراراتُ الإداريّة (سقفا السابعة والأولى ويومُ التفريغ) يُثبَّت أثرُها: قيمتان قبل وبعد ومعرّفُ الصفّ — لا اسمُ المعلّم.

        ثمرةُ قرار المالك D-172م، فيُراد أثرُه أبعدَ من `LogEntry` (W-20261003-035، توصيةُ 0105).
        """
        before, before_run, before_free, before_first = (
            type(obj)
            .objects.filter(pk=obj.pk)
            .values_list("max_last_periods", "max_consecutive", "free_day", "max_first_periods")
            .first()
            if change
            else None
        ) or (None, None, None, None)
        super().save_model(request, obj, form, change)
        from operations.preference_capacity import (
            exceeds_general_run_cap,
            record_free_day_change,
            record_run_cap_above_general,
        )

        if before_free != obj.free_day:
            record_free_day_change(request, obj, before_free, change)
        if before_run != obj.max_consecutive and exceeds_general_run_cap(obj.max_consecutive):
            record_run_cap_above_general(request, obj, "admin")
        if before_first != obj.max_first_periods:
            from core.models import AuditLog

            AuditLog.objects.create(
                school=obj.school,
                user=request.user,
                action="update" if change else "create",
                model_name="other",
                object_id=str(obj.pk),
                object_repr=f"سقفُ الأولى الشخصيّ {obj.academic_year}",
                changes={
                    "event": "teacher_first_period_cap_changed",
                    "before": before_first,
                    "after": obj.max_first_periods,
                },
            )
        if before != obj.max_last_periods:
            from core.models import AuditLog

            AuditLog.objects.create(
                school=obj.school,
                user=request.user,
                action="update" if change else "create",
                model_name="other",
                object_id=str(obj.pk),
                object_repr=f"سقفُ السابعة الشخصيّ {obj.academic_year}",
                changes={
                    "event": "teacher_last_period_cap_changed",
                    "before": before,
                    "after": obj.max_last_periods,
                },
            )


@admin.register(ScheduleGeneration)
class ScheduleGenerationAdmin(admin.ModelAdmin):
    list_display = (
        "academic_year",
        "status",
        "quality_score",
        "total_slots_created",
        "generated_by",
        "generated_at",
    )
    list_filter = ("school", "status", "academic_year")
    readonly_fields = (
        "generated_at",
        "quality_score",
        "hard_violations",
        "soft_violations",
        "generation_time_ms",
    )
    autocomplete_fields = ("generated_by",)

    # ── الحمايةُ في النموذج، وهذه واجهتُها: زرٌّ يختفي بدل خطأٍ يُفاجئ ──
    #
    # حذفُ توليدٍ معتمَد كان يمرّ من هنا بلا اعتراض فيفقد الجدولُ الحيّ نسبَه.
    # النموذجُ يرفض الآن (`ProtectedError`)، لكنّ لوحةَ الإدارة لا تلتقط ما يُرفع
    # من `delete()` نفسِها — فتُخفي الزرَّ عن المحميّ، وتستثنيه من حذف الدفعة.

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_protected:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        protected = [g for g in queryset if g.is_protected]
        if protected:
            self.message_user(
                request,
                f"استُثني {len(protected)} توليداً محميّاً (معتمَدٌ أو له حصصٌ حيّة) — "
                "اعتمد مسودّةً أخرى بدله.",
                level=messages.WARNING,
            )
            queryset = queryset.exclude(pk__in=[g.pk for g in protected])
        super().delete_queryset(request, queryset)


@admin.register(ScheduleBaseline)
class ScheduleBaselineAdmin(admin.ModelAdmin):
    list_display = ("label", "academic_year", "school", "created_at")
    list_filter = ("school", "academic_year")
    readonly_fields = ("metrics", "created_at")


# ── جداولٌ تكتبها خدماتُها وحدَها — تُقرأ هنا (قاعدةُ المالك: يظهر كلُّ جدول) ──


@admin.register(TeacherExemption)
class TeacherExemptionAdmin(ReadOnlyAdminMixin, SchoolScopedAdmin):
    list_display = (
        "teacher",
        "academic_year",
        "exemption_type",
        "day_of_week",
        "period_number",
        "is_active",
    )
    list_select_related = ("teacher",)
    list_filter = ("school", "exemption_type", "is_active", "academic_year")
    search_fields = ("teacher__full_name",)


@admin.register(FreeSlotRegistry)
class FreeSlotRegistryAdmin(ReadOnlyAdminMixin, SchoolScopedAdmin):
    list_display = (
        "teacher",
        "academic_year",
        "day_of_week",
        "period_number",
        "is_available",
        "reserved_for",
    )
    list_select_related = ("teacher", "reserved_for")
    list_filter = ("school", "is_available", "academic_year")
    search_fields = ("teacher__full_name",)


@admin.register(TeacherSwap)
class TeacherSwapAdmin(ReadOnlyAdminMixin, SchoolScopedAdmin):
    list_display = (
        "teacher_a",
        "teacher_b",
        "swap_type",
        "swap_date_a",
        "swap_date_b",
        "status",
        "created_at",
    )
    list_select_related = ("teacher_a", "teacher_b")
    list_filter = ("school", "status", "swap_type")
    search_fields = ("teacher_a__full_name", "teacher_b__full_name")


@admin.register(CompensatorySession)
class CompensatorySessionAdmin(ReadOnlyAdminMixin, SchoolScopedAdmin):
    list_display = (
        "teacher",
        "compensatory_date",
        "compensatory_period",
        "class_group",
        "subject",
        "status",
    )
    list_select_related = ("teacher", "class_group", "subject")
    list_filter = ("school", "status")
    search_fields = ("teacher__full_name",)


@admin.register(TemporaryPermission)
class TemporaryPermissionAdmin(ReadOnlyAdminMixin, SchoolScopedAdmin):
    list_display = (
        "teacher",
        "class_group",
        "permission_type",
        "valid_from",
        "valid_until",
        "status",
    )
    list_select_related = ("teacher", "class_group")
    list_filter = ("school", "status", "permission_type")
    search_fields = ("teacher__full_name",)


@admin.register(PermissionAuditLog)
class PermissionAuditLogAdmin(ReadOnlyAdminMixin, SchoolScopedAdmin):
    school_lookup = "temp_permission__school"
    list_display = ("temp_permission", "action", "performed_by", "performed_at")
    list_select_related = ("temp_permission__teacher", "performed_by")
    list_filter = ("action",)
