from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from core.models import BusRoute, CustomUser, SchoolBus
from core.permissions import bus_supervisor_required


@login_required
@bus_supervisor_required
def transport_dashboard(request):
    """لوحة تحكم النقل والمواصلات"""
    school = request.user.school

    # إحصائيات الحافلات
    buses = SchoolBus.objects.filter(school=school).select_related("supervisor").prefetch_related("routes__students")
    total_buses = buses.count()
    total_capacity = sum(bus.capacity for bus in buses)

    # عدد الطلاب المسجلين
    total_students = CustomUser.objects.filter(bus_routes__bus__school=school).distinct().count()

    # الحافلات والطلاب
    bus_data = []
    for bus in buses:
        students_count = bus.routes.values_list("students", flat=True).distinct().count()
        bus_data.append(
            {
                "bus": bus,
                "students_count": students_count,
                "occupancy_rate": (students_count / bus.capacity * 100) if bus.capacity > 0 else 0,
            }
        )

    context = {
        "total_buses": total_buses,
        "total_capacity": total_capacity,
        "total_students": total_students,
        "bus_data": bus_data,
    }
    return render(request, "transport/dashboard.html", context)


@login_required
@bus_supervisor_required
def buses_list(request):
    """قائمة الحافلات المدرسية"""
    school = request.user.school
    buses = SchoolBus.objects.filter(school=school).select_related("supervisor")

    # تصفية حسب رقم الحافلة
    search = request.GET.get("search")
    if search:
        buses = buses.filter(Q(bus_number__icontains=search) | Q(driver_name__icontains=search))

    context = {
        "buses": buses,
        "search": search,
    }
    return render(request, "transport/buses_list.html", context)


@login_required
@bus_supervisor_required
@require_http_methods(["GET", "POST"])
def bus_detail(request, bus_id):
    """تفاصيل الحافلة وإدارة الطلاب"""
    school = request.user.school
    bus = get_object_or_404(SchoolBus, id=bus_id, school=school)

    if request.method == "POST":
        # تحديث بيانات الحافلة
        bus.bus_number = request.POST.get("bus_number", bus.bus_number)
        bus.driver_name = request.POST.get("driver_name", bus.driver_name)
        bus.driver_phone = request.POST.get("driver_phone", bus.driver_phone)
        bus.capacity = int(request.POST.get("capacity", bus.capacity))
        bus.karwa_id = request.POST.get("karwa_id", bus.karwa_id)
        bus.gps_link = request.POST.get("gps_link", bus.gps_link)
        bus.save()

        if request.headers.get("HX-Request"):
            return render(request, "transport/bus_info.html", {"bus": bus})

        return redirect("transport:bus_detail", bus_id=bus_id)

    # الطلاب المسجلين
    routes = bus.routes.all()
    students = CustomUser.objects.filter(bus_routes__bus=bus).distinct()

    context = {
        "bus": bus,
        "routes": routes,
        "students": students,
        "occupancy_rate": (students.count() / bus.capacity * 100) if bus.capacity > 0 else 0,
    }
    return render(request, "transport/bus_detail.html", context)


@login_required
@bus_supervisor_required
@require_http_methods(["GET", "POST"])
def manage_route(request, bus_id, route_id=None):
    """إدارة خطوط السير"""
    school = request.user.school
    bus = get_object_or_404(SchoolBus, id=bus_id, school=school)

    if route_id:
        route = get_object_or_404(BusRoute, id=route_id, bus=bus)
    else:
        route = None

    if request.method == "POST":
        area_name = request.POST.get("area_name")

        if route:
            route.area_name = area_name
            route.save()
        else:
            route = BusRoute.objects.create(bus=bus, area_name=area_name)

        # إضافة الطلاب للمسار
        student_ids = request.POST.getlist("students")
        route.students.set(student_ids)

        if request.headers.get("HX-Request"):
            return render(request, "transport/route_card.html", {"route": route})

        return redirect("transport:bus_detail", bus_id=bus_id)

    # الطلاب المتاحين
    available_students = CustomUser.objects.filter(
        memberships__school=school, memberships__role__name="student", memberships__is_active=True
    ).distinct()

    context = {
        "bus": bus,
        "route": route,
        "available_students": available_students,
    }
    return render(request, "transport/manage_route.html", context)


@login_required
@bus_supervisor_required
def tracking_map(request, bus_id):
    """خريطة تتبع الحافلة (تكامل كروة و GPS)"""
    school = request.user.school
    bus = get_object_or_404(SchoolBus, id=bus_id, school=school)

    context = {
        "bus": bus,
        "has_karwa": bool(bus.karwa_id),
        "has_gps": bool(bus.gps_link),
    }
    return render(request, "transport/tracking_map.html", context)


@login_required
@bus_supervisor_required
def student_assignments(request):
    """إسناد الطلاب للحافلات"""
    school = request.user.school

    # الطلاب غير المسندين
    unassigned_students = (
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__role__name="student",
            memberships__is_active=True,
        )
        .exclude(bus_routes__isnull=False)
        .distinct()
    )

    # الطلاب المسندين
    assigned_students = CustomUser.objects.filter(bus_routes__bus__school=school).distinct()

    context = {
        "unassigned_students": unassigned_students,
        "assigned_students": assigned_students,
    }
    return render(request, "transport/student_assignments.html", context)


@login_required
@bus_supervisor_required
def transport_statistics(request):
    """إحصائيات النقل والمواصلات"""
    school = request.user.school

    buses = SchoolBus.objects.filter(school=school).select_related("supervisor")
    total_buses = buses.count()
    total_capacity = sum(bus.capacity for bus in buses)

    students_count = CustomUser.objects.filter(bus_routes__bus__school=school).distinct().count()

    utilization_rate = (students_count / total_capacity * 100) if total_capacity > 0 else 0

    context = {
        "total_buses": total_buses,
        "total_capacity": total_capacity,
        "students_count": students_count,
        "utilization_rate": utilization_rate,
        "buses": buses,
    }
    return render(request, "transport/statistics.html", context)
