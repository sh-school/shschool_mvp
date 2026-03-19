"""
tests/test_views_transport.py
اختبارات views النقل والمواصلات
"""
import pytest
from core.models import SchoolBus, BusRoute
from .conftest import SchoolBusFactory


@pytest.mark.django_db
class TestTransportDashboard:

    def test_dashboard_loads(self, client_as, bus_supervisor_user, school, school_bus):
        client = client_as(bus_supervisor_user)
        response = client.get("/transport/")
        assert response.status_code == 200
        assert "total_buses" in response.context
        assert "bus_data" in response.context

    def test_dashboard_shows_correct_bus_count(
        self, client_as, bus_supervisor_user, school, school_bus
    ):
        client = client_as(bus_supervisor_user)
        response = client.get("/transport/")
        assert response.context["total_buses"] >= 1


@pytest.mark.django_db
class TestBusesList:

    def test_buses_list_loads(self, client_as, bus_supervisor_user, school_bus):
        client = client_as(bus_supervisor_user)
        response = client.get("/transport/buses/")
        assert response.status_code == 200
        assert "buses" in response.context

    def test_search_by_bus_number(self, client_as, bus_supervisor_user, school_bus):
        client = client_as(bus_supervisor_user)
        response = client.get(f"/transport/buses/?search={school_bus.bus_number}")
        assert response.status_code == 200
        # الحافلة يجب أن تظهر في النتيجة
        buses = response.context["buses"]
        assert any(b.id == school_bus.id for b in buses)


@pytest.mark.django_db
class TestBusDetail:

    def test_bus_detail_loads(self, client_as, bus_supervisor_user, school_bus):
        client = client_as(bus_supervisor_user)
        response = client.get(f"/transport/bus/{school_bus.id}/")
        assert response.status_code == 200
        assert "bus" in response.context
        assert "routes" in response.context

    def test_update_bus_info(self, client_as, bus_supervisor_user, school_bus):
        client = client_as(bus_supervisor_user)
        response = client.post(f"/transport/bus/{school_bus.id}/", {
            "bus_number": "B-NEW",
            "driver_name": "سائق جديد",
            "driver_phone": "+97466123456",
            "capacity": 35,
            "karwa_id": "K12345",
            "gps_link": "",
        })
        assert response.status_code in (200, 302)
        refreshed = SchoolBus.objects.get(id=school_bus.id)
        assert refreshed.driver_name == "سائق جديد"


@pytest.mark.django_db
class TestManageRoute:

    def test_create_route_form_loads(self, client_as, bus_supervisor_user, school_bus):
        client = client_as(bus_supervisor_user)
        response = client.get(f"/transport/bus/{school_bus.id}/route/new/")
        assert response.status_code == 200
        assert "bus" in response.context
        assert "available_students" in response.context

    def test_create_route_with_students(
        self, client_as, bus_supervisor_user, school_bus, student_user, enrolled_student
    ):
        client = client_as(bus_supervisor_user)
        response = client.post(f"/transport/bus/{school_bus.id}/route/new/", {
            "area_name": "حي الشحانية",
            "students": [str(student_user.id)],
        })
        assert response.status_code in (200, 302)
        assert BusRoute.objects.filter(bus=school_bus, area_name="حي الشحانية").exists()


@pytest.mark.django_db
class TestTrackingMap:

    def test_tracking_map_without_gps(self, client_as, bus_supervisor_user, school_bus):
        school_bus.gps_link = ""
        school_bus.karwa_id = ""
        school_bus.save()
        client = client_as(bus_supervisor_user)
        response = client.get(f"/transport/bus/{school_bus.id}/tracking/")
        assert response.status_code == 200
        assert response.context["has_gps"] is False

    def test_tracking_map_with_karwa(self, client_as, bus_supervisor_user, school_bus):
        school_bus.karwa_id = "KW-001"
        school_bus.save()
        client = client_as(bus_supervisor_user)
        response = client.get(f"/transport/bus/{school_bus.id}/tracking/")
        assert response.context["has_karwa"] is True


@pytest.mark.django_db
class TestStudentAssignments:

    def test_assignments_loads(self, client_as, bus_supervisor_user, school):
        client = client_as(bus_supervisor_user)
        response = client.get("/transport/assignments/")
        assert response.status_code == 200
        assert "unassigned_students" in response.context
        assert "assigned_students" in response.context


@pytest.mark.django_db
class TestTransportStatistics:

    def test_statistics_loads(self, client_as, bus_supervisor_user, school_bus):
        client = client_as(bus_supervisor_user)
        response = client.get("/transport/statistics/")
        assert response.status_code == 200
        assert "total_buses" in response.context
        assert "utilization_rate" in response.context
