from django.contrib import admin
from core.models import SchoolBus, BusRoute


@admin.register(SchoolBus)
class SchoolBusAdmin(admin.ModelAdmin):
    list_display = ('bus_number', 'driver_name', 'capacity', 'school')
    list_filter = ('school', 'capacity')
    search_fields = ('bus_number', 'driver_name', 'driver_phone')
    fieldsets = (
        ('بيانات الحافلة', {'fields': ('school', 'bus_number', 'capacity')}),
        ('بيانات السائق', {'fields': ('driver_name', 'driver_phone')}),
        ('المشرف والتتبع', {'fields': ('supervisor', 'karwa_id', 'gps_link')}),
    )


@admin.register(BusRoute)
class BusRouteAdmin(admin.ModelAdmin):
    list_display = ('bus', 'area_name', 'get_students_count')
    list_filter = ('bus__school', 'area_name')
    search_fields = ('area_name', 'bus__bus_number')
    filter_horizontal = ('students',)
    
    def get_students_count(self, obj):
        return obj.students.count()
    get_students_count.short_description = 'عدد الطلاب'
