from django.contrib import admin
from behavior.models import BehaviorInfraction, BehaviorPointRecovery

@admin.register(BehaviorInfraction)
class BehaviorInfractionAdmin(admin.ModelAdmin):
    list_display = ('student', 'school', 'level', 'date', 'points_deducted', 'is_resolved')
    list_filter = ('school', 'level', 'is_resolved', 'date')
    search_fields = ('student__full_name', 'description')
    ordering = ('-date',)

@admin.register(BehaviorPointRecovery)
class BehaviorPointRecoveryAdmin(admin.ModelAdmin):
    list_display = ('infraction', 'points_restored', 'approved_by', 'date')
    list_filter = ('date',)
    search_fields = ('infraction__student__full_name', 'reason')
