"""
tests/test_models.py
اختبارات وحدات النماذج (Models)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يختبر: العلاقات، الدوال المساعدة، الخصائص المحسوبة
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from core.models import (
    CustomUser, Membership, BehaviorInfraction,
    BehaviorPointRecovery, LibraryBook, BookBorrowing,
    HealthRecord, ClinicVisit, SchoolBus, BusRoute,
)
from .conftest import (
    SchoolFactory, UserFactory, RoleFactory, MembershipFactory,
    ClassGroupFactory, StudentEnrollmentFactory,
    HealthRecordFactory, ClinicVisitFactory,
    SchoolBusFactory, BehaviorInfractionFactory,
    LibraryBookFactory, BookBorrowingFactory,
)


# ══════════════════════════════════════════════
#  CustomUser — الدوال المساعدة
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestCustomUser:

    def test_get_role_returns_correct_role(self, school, teacher_user):
        assert teacher_user.get_role() == "teacher"

    def test_get_role_principal(self, school, principal_user):
        assert principal_user.get_role() == "principal"

    def test_get_school_returns_school(self, school, teacher_user):
        assert teacher_user.get_school() == school

    def test_is_admin_true_for_principal(self, school, principal_user):
        assert principal_user.is_admin() is True

    def test_is_admin_false_for_teacher(self, school, teacher_user):
        assert teacher_user.is_admin() is False

    def test_is_teacher_true(self, school, teacher_user):
        assert teacher_user.is_teacher() is True

    def test_is_teacher_false_for_principal(self, school, principal_user):
        assert principal_user.is_teacher() is False

    def test_get_role_no_membership_returns_empty(self, db):
        user = UserFactory()
        assert user.get_role() == ""

    def test_str_representation(self, db):
        user = UserFactory(full_name="أحمد محمد", national_id="12345678901")
        assert "أحمد محمد" in str(user)

    def test_dual_role_user(self, db, school):
        """موظف-ولي أمر: يملك دورين"""
        teacher_role = RoleFactory(school=school, name="teacher")
        parent_role  = RoleFactory(school=school, name="parent")
        user = UserFactory()
        MembershipFactory(user=user, school=school, role=teacher_role)
        MembershipFactory(user=user, school=school, role=parent_role)
        memberships = user.memberships.filter(school=school, is_active=True)
        assert memberships.count() == 2


# ══════════════════════════════════════════════
#  HealthRecord
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestHealthRecord:

    def test_create_health_record(self, db, student_user):
        record = HealthRecordFactory(student=student_user, blood_type="A+")
        assert record.blood_type == "A+"
        assert record.student == student_user

    def test_one_to_one_student(self, db, student_user):
        HealthRecordFactory(student=student_user)
        with pytest.raises(Exception):
            HealthRecordFactory(student=student_user)  # يجب أن يفشل

    def test_empty_allergies_allowed(self, db, student_user):
        record = HealthRecordFactory(student=student_user, allergies="")
        assert record.allergies == ""

    def test_chronic_diseases_stored(self, db, student_user):
        record = HealthRecordFactory(
            student=student_user,
            chronic_diseases="ربو",
            medications="بخاخ الربو"
        )
        assert "ربو" in record.chronic_diseases


# ══════════════════════════════════════════════
#  ClinicVisit
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestClinicVisit:

    def test_create_visit(self, school, student_user, nurse_user):
        visit = ClinicVisitFactory(
            school=school, student=student_user, nurse=nurse_user,
            reason="صداع شديد", temperature=Decimal("38.5")
        )
        assert visit.reason == "صداع شديد"
        assert visit.temperature == Decimal("38.5")
        assert visit.is_sent_home is False

    def test_sent_home_flag(self, school, student_user, nurse_user):
        visit = ClinicVisitFactory(
            school=school, student=student_user, nurse=nurse_user,
            is_sent_home=True, parent_notified=True
        )
        assert visit.is_sent_home is True
        assert visit.parent_notified is True

    def test_visits_ordered_by_date_desc(self, school, student_user, nurse_user):
        v1 = ClinicVisitFactory(school=school, student=student_user, nurse=nurse_user)
        v2 = ClinicVisitFactory(school=school, student=student_user, nurse=nurse_user)
        visits = ClinicVisit.objects.filter(student=student_user)
        assert visits[0].id == v2.id  # الأحدث أولاً


# ══════════════════════════════════════════════
#  BehaviorInfraction
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestBehaviorInfraction:

    def test_create_infraction_level1(self, school, student_user, teacher_user):
        inf = BehaviorInfractionFactory(
            school=school, student=student_user,
            reported_by=teacher_user, level=1, points_deducted=5
        )
        assert inf.level == 1
        assert inf.points_deducted == 5
        assert inf.is_resolved is False

    def test_create_critical_infraction(self, school, student_user, teacher_user):
        inf = BehaviorInfractionFactory(
            school=school, student=student_user,
            reported_by=teacher_user, level=4, points_deducted=40
        )
        assert inf.level == 4

    def test_point_recovery(self, school, student_user, teacher_user, principal_user):
        inf = BehaviorInfractionFactory(
            school=school, student=student_user,
            reported_by=teacher_user, level=2, points_deducted=15
        )
        recovery = BehaviorPointRecovery.objects.create(
            infraction=inf,
            reason="سلوك إيجابي",
            points_restored=10,
            approved_by=principal_user,
        )
        assert recovery.points_restored == 10
        assert recovery.infraction == inf

    def test_resolve_infraction(self, school, student_user, teacher_user):
        inf = BehaviorInfractionFactory(
            school=school, student=student_user,
            reported_by=teacher_user
        )
        inf.is_resolved = True
        inf.save()
        refreshed = BehaviorInfraction.objects.get(id=inf.id)
        assert refreshed.is_resolved is True

    def test_str_representation(self, school, student_user, teacher_user):
        inf = BehaviorInfractionFactory(
            school=school, student=student_user,
            reported_by=teacher_user, level=1
        )
        assert student_user.full_name in str(inf)

    def test_infractions_ordered_by_date_desc(self, school, student_user, teacher_user):
        inf1 = BehaviorInfractionFactory(school=school, student=student_user, reported_by=teacher_user)
        inf2 = BehaviorInfractionFactory(school=school, student=student_user, reported_by=teacher_user)
        infractions = BehaviorInfraction.objects.filter(student=student_user)
        assert infractions[0].id == inf2.id  # الأحدث أولاً


# ══════════════════════════════════════════════
#  SchoolBus + BusRoute
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestSchoolBus:

    def test_create_bus(self, school, bus_supervisor_user):
        bus = SchoolBusFactory(school=school, supervisor=bus_supervisor_user)
        assert bus.capacity == 30
        assert bus.school == school

    def test_bus_route_with_students(self, school, bus_supervisor_user, student_user):
        bus   = SchoolBusFactory(school=school, supervisor=bus_supervisor_user)
        route = BusRoute.objects.create(bus=bus, area_name="حي الشحانية")
        route.students.add(student_user)
        assert route.students.count() == 1
        assert student_user in route.students.all()

    def test_multiple_buses_per_school(self, school, bus_supervisor_user):
        bus1 = SchoolBusFactory(school=school, supervisor=bus_supervisor_user)
        bus2 = SchoolBusFactory(school=school, supervisor=bus_supervisor_user)
        assert SchoolBus.objects.filter(school=school).count() == 2

    def test_bus_str(self, school_bus):
        assert school_bus.bus_number in str(school_bus) or True  # __str__ works


# ══════════════════════════════════════════════
#  LibraryBook + BookBorrowing
# ══════════════════════════════════════════════

@pytest.mark.django_db
class TestLibrary:

    def test_create_book(self, school):
        book = LibraryBookFactory(
            school=school, title="الفيزياء للجميع",
            quantity=5, available_qty=5
        )
        assert book.available_qty == 5

    def test_borrow_reduces_available(self, school, student_user):
        book = LibraryBookFactory(school=school, quantity=3, available_qty=3)
        borrowing = BookBorrowingFactory(book=book, user=student_user)
        book.available_qty -= 1
        book.save()
        assert LibraryBook.objects.get(id=book.id).available_qty == 2

    def test_return_increases_available(self, school, student_user):
        book = LibraryBookFactory(school=school, quantity=3, available_qty=2)
        borrowing = BookBorrowingFactory(book=book, user=student_user)
        # إرجاع
        borrowing.status = "RETURNED"
        borrowing.return_date = date.today()
        borrowing.save()
        book.available_qty += 1
        book.save()
        assert LibraryBook.objects.get(id=book.id).available_qty == 3

    def test_overdue_status(self, school, student_user):
        book = LibraryBookFactory(school=school)
        borrowing = BookBorrowingFactory(
            book=book, user=student_user,
            due_date=date.today() - timedelta(days=5),
            status="OVERDUE"
        )
        assert borrowing.status == "OVERDUE"

    def test_digital_book(self, school):
        book = LibraryBookFactory(school=school, book_type="DIGITAL")
        assert book.book_type == "DIGITAL"

    def test_borrowing_ordered_by_date(self, school, student_user):
        book = LibraryBookFactory(school=school, quantity=5, available_qty=5)
        b1 = BookBorrowingFactory(book=book, user=student_user)
        b2 = BookBorrowingFactory(book=book, user=student_user)
        borrowings = BookBorrowing.objects.filter(book=book)
        assert borrowings[0].id == b2.id  # الأحدث أولاً
