"""
tests/test_v54_services.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
اختبارات Services الجديدة في v5.4:
  - LeaveService (create + review + race condition logic)
  - BehaviorService.create_infraction + approve_point_recovery
  - ClinicService.record_visit
  - LibraryService (borrow + return)
  - StaffService.get_staff_profile_data
"""

import pytest

from tests.conftest import (
    BehaviorInfractionFactory,
    BookBorrowingFactory,
    LibraryBookFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    UserFactory,
)

# ══════════════════════════════════════════════
#  LeaveService
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestLeaveService:
    """اختبارات LeaveService — إنشاء ومراجعة الإجازات."""

    def test_create_leave_request_basic(self):
        """create_leave_request يُنشئ LeaveRequest بالحقول الصحيحة."""
        from datetime import date

        from staff_affairs.services import LeaveService

        school = SchoolFactory()
        staff = UserFactory()
        MembershipFactory(user=staff, school=school)

        leave = LeaveService.create_leave_request(
            school=school,
            staff=staff,
            leave_type="annual",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 5),
            days_count=5,
            reason="إجازة سنوية",
            created_by=staff,
        )

        assert leave.pk is not None
        assert leave.status == "pending"
        assert leave.days_count == 5
        assert leave.staff == staff
        assert leave.school == school

    def test_create_leave_request_pending_status(self):
        """الطلب يبدأ بحالة pending دائماً."""
        from datetime import date

        from staff_affairs.services import LeaveService

        school = SchoolFactory()
        staff = UserFactory()
        leave = LeaveService.create_leave_request(
            school=school,
            staff=staff,
            leave_type="sick",
            start_date=date(2026, 4, 10),
            end_date=date(2026, 4, 12),
            days_count=3,
            reason="مرض",
        )
        assert leave.status == "pending"

    def test_review_leave_approved_updates_balance(self):
        """review_leave عند الموافقة يُضيف إلى used_days."""
        from datetime import date

        from staff_affairs.models import LeaveBalance
        from staff_affairs.services import LeaveService

        school = SchoolFactory()
        staff = UserFactory()
        reviewer = UserFactory()
        MembershipFactory(user=staff, school=school)

        leave = LeaveService.create_leave_request(
            school=school,
            staff=staff,
            leave_type="annual",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 5),
            days_count=5,
            reason="إجازة",
        )

        LeaveService.review_leave(leave=leave, action="approved", reviewer=reviewer)

        balance = LeaveBalance.objects.get(
            school=school,
            staff=staff,
            leave_type="annual",
        )
        assert balance.used_days == 5

    def test_review_leave_rejected_no_balance_change(self):
        """review_leave عند الرفض لا يُعدّل الرصيد."""
        from datetime import date

        from staff_affairs.models import LeaveBalance
        from staff_affairs.services import LeaveService

        school = SchoolFactory()
        staff = UserFactory()
        reviewer = UserFactory()

        leave = LeaveService.create_leave_request(
            school=school,
            staff=staff,
            leave_type="annual",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 3),
            days_count=3,
            reason="سبب",
        )
        LeaveService.review_leave(
            leave=leave,
            action="rejected",
            reviewer=reviewer,
            rejection_reason="لا يوجد رصيد",
        )

        assert not LeaveBalance.objects.filter(
            school=school,
            staff=staff,
            leave_type="annual",
        ).exists()

    def test_review_leave_invalid_action_raises(self):
        """review_leave يرفع ValueError على action غير صالح."""
        from datetime import date

        from staff_affairs.services import LeaveService

        school = SchoolFactory()
        staff = UserFactory()
        reviewer = UserFactory()
        leave = LeaveService.create_leave_request(
            school=school,
            staff=staff,
            leave_type="annual",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2),
            days_count=2,
            reason="x",
        )
        with pytest.raises(ValueError, match="غير صالح"):
            LeaveService.review_leave(leave=leave, action="suspend", reviewer=reviewer)

    def test_review_leave_non_pending_raises(self):
        """review_leave على طلب معالج يرفع ValueError."""
        from datetime import date

        from staff_affairs.services import LeaveService

        school = SchoolFactory()
        staff = UserFactory()
        reviewer = UserFactory()
        leave = LeaveService.create_leave_request(
            school=school,
            staff=staff,
            leave_type="sick",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 1),
            days_count=1,
            reason="x",
        )
        # نوافق مرة
        LeaveService.review_leave(leave=leave, action="approved", reviewer=reviewer)
        # نحاول ثانية — يجب أن يرفع
        with pytest.raises(ValueError, match="قيد الانتظار"):
            LeaveService.review_leave(leave=leave, action="rejected", reviewer=reviewer)


# ══════════════════════════════════════════════
#  BehaviorService
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestBehaviorServiceCreateInfraction:
    """اختبارات BehaviorService.create_infraction."""

    def test_create_infraction_basic(self):
        """create_infraction يُنشئ مخالفة بالحقول الصحيحة."""
        from behavior.services import BehaviorService

        school = SchoolFactory()
        student = UserFactory()
        reporter = UserFactory()

        infraction = BehaviorService.create_infraction(
            school=school,
            student=student,
            reporter=reporter,
            level=1,
            description="تأخر عن الحصة",
            points_deducted=5,
        )

        assert infraction.pk is not None
        assert infraction.level == 1
        assert infraction.points_deducted == 5
        assert infraction.student == student
        assert infraction.reported_by == reporter
        assert not infraction.is_resolved

    def test_create_infraction_invalid_level_raises(self):
        """create_infraction يرفع ValueError إذا كان level خارج 1-4."""
        from behavior.services import BehaviorService

        school = SchoolFactory()
        student = UserFactory()
        reporter = UserFactory()

        with pytest.raises(ValueError, match="1 و4"):
            BehaviorService.create_infraction(
                school=school,
                student=student,
                reporter=reporter,
                level=5,
                description="مخالفة",
            )

    def test_create_infraction_escalation_calculated(self):
        """create_infraction يحسب escalation_step تلقائياً."""
        from behavior.services import BehaviorService

        school = SchoolFactory()
        student = UserFactory()
        reporter = UserFactory()

        # أول مخالفة → escalation_step=1
        infraction = BehaviorService.create_infraction(
            school=school,
            student=student,
            reporter=reporter,
            level=2,
            description="مخالفة أولى",
        )
        assert infraction.escalation_step >= 1


@pytest.mark.django_db
class TestBehaviorServicePointRecovery:
    """اختبارات BehaviorService.approve_point_recovery."""

    def test_approve_point_recovery_resolves_infraction(self, db):
        """approve_point_recovery يُغلق المخالفة ويُنشئ سجل استعادة."""
        from behavior.services import BehaviorService

        school = SchoolFactory()
        student = UserFactory()
        approver = UserFactory()
        infraction = BehaviorInfractionFactory(school=school, student=student, points_deducted=10)

        recovery = BehaviorService.approve_point_recovery(
            infraction=infraction,
            approved_by=approver,
            reason="سلوك ممتاز",
            points_restored=5,
        )

        assert recovery.pk is not None
        assert recovery.points_restored == 5
        infraction.refresh_from_db()
        assert infraction.is_resolved is True

    def test_approve_point_recovery_invalid_points_raises(self):
        """approve_point_recovery يرفع ValueError على نقاط خارج النطاق."""
        from behavior.services import BehaviorService

        school = SchoolFactory()
        infraction = BehaviorInfractionFactory(school=school, points_deducted=5)

        with pytest.raises(ValueError):
            BehaviorService.approve_point_recovery(
                infraction=infraction,
                approved_by=UserFactory(),
                reason="سبب",
                points_restored=10,  # أكثر من المخصوم
            )

    def test_approve_point_recovery_double_raises(self, db):
        """approve_point_recovery لا يُطبَّق على مخالفة محلولة مسبقاً."""
        from behavior.services import BehaviorService

        school = SchoolFactory()
        infraction = BehaviorInfractionFactory(school=school, points_deducted=10)
        approver = UserFactory()

        BehaviorService.approve_point_recovery(
            infraction=infraction,
            approved_by=approver,
            reason="سبب",
            points_restored=5,
        )

        with pytest.raises(ValueError, match="معالجة مسبقاً"):
            BehaviorService.approve_point_recovery(
                infraction=infraction,
                approved_by=approver,
                reason="سبب ثانٍ",
                points_restored=3,
            )


# ══════════════════════════════════════════════
#  ClinicService
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestClinicService:
    """اختبارات ClinicService.record_visit."""

    def test_record_visit_creates_clinic_visit(self):
        """record_visit يُنشئ ClinicVisit بالحقول الصحيحة."""
        from clinic.services import ClinicService

        school = SchoolFactory()
        student = UserFactory()
        nurse = UserFactory()

        visit = ClinicService.record_visit(
            school=school,
            student=student,
            nurse=nurse,
            reason="صداع",
            symptoms="ألم في الرأس",
            is_sent_home=False,
        )

        assert visit.pk is not None
        assert visit.reason == "صداع"
        assert visit.student == student
        assert visit.nurse == nurse
        assert not visit.is_sent_home
        assert not visit.parent_notified

    def test_record_visit_sent_home_sets_flag(self):
        """record_visit مع is_sent_home=True يُسجّل الحقل بشكل صحيح."""
        from clinic.services import ClinicService

        school = SchoolFactory()
        student = UserFactory()
        nurse = UserFactory()

        visit = ClinicService.record_visit(
            school=school,
            student=student,
            nurse=nurse,
            reason="حمى",
            is_sent_home=True,
        )

        assert visit.is_sent_home is True
        # parent_notified=False لأنه لا يوجد ولي أمر مرتبط في الاختبار
        assert visit.parent_notified is False

    def test_record_visit_without_temperature(self):
        """record_visit بدون درجة حرارة يقبل None."""
        from clinic.services import ClinicService

        school = SchoolFactory()
        visit = ClinicService.record_visit(
            school=school,
            student=UserFactory(),
            nurse=UserFactory(),
            reason="كحة",
            temperature=None,
        )
        assert visit.temperature is None


# ══════════════════════════════════════════════
#  LibraryService — race condition safety
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestLibraryServiceBorrow:
    """اختبارات LibraryService — الإعارة والإرجاع."""

    def test_borrow_book_decrements_qty(self):
        """borrow_book ينقص available_qty بمقدار 1."""
        from library.services import LibraryService

        school = SchoolFactory()
        book = LibraryBookFactory(school=school, quantity=3, available_qty=3)
        user = UserFactory()

        LibraryService.borrow_book(book=book, user=user)

        book.refresh_from_db()
        assert book.available_qty == 2

    def test_borrow_book_zero_qty_raises(self):
        """borrow_book يرفع ValueError عندما لا يوجد نسخ متاحة."""
        from library.services import LibraryService

        school = SchoolFactory()
        book = LibraryBookFactory(school=school, quantity=1, available_qty=0)
        user = UserFactory()

        with pytest.raises(ValueError, match="غير متوفر"):
            LibraryService.borrow_book(book=book, user=user)

    def test_borrow_book_creates_borrowing_record(self):
        """borrow_book يُنشئ سجل BookBorrowing بحالة BORROWED."""
        from library.services import LibraryService

        school = SchoolFactory()
        book = LibraryBookFactory(school=school, quantity=2, available_qty=2)
        user = UserFactory()

        borrowing = LibraryService.borrow_book(book=book, user=user)

        assert borrowing.pk is not None
        assert borrowing.status == "BORROWED"
        assert borrowing.user == user
        assert borrowing.book == book

    def test_return_book_increments_qty(self):
        """return_book يزيد available_qty بمقدار 1."""
        from library.services import LibraryService

        school = SchoolFactory()
        book = LibraryBookFactory(school=school, quantity=2, available_qty=1)
        user = UserFactory()
        borrowing = BookBorrowingFactory(book=book, user=user, status="BORROWED")

        LibraryService.return_book(borrowing)

        book.refresh_from_db()
        assert book.available_qty == 2

    def test_return_book_updates_status(self):
        """return_book يُحدّث status إلى RETURNED."""
        from library.services import LibraryService

        school = SchoolFactory()
        book = LibraryBookFactory(school=school, quantity=1, available_qty=0)
        user = UserFactory()
        borrowing = BookBorrowingFactory(book=book, user=user, status="BORROWED")

        returned = LibraryService.return_book(borrowing)

        assert returned.status == "RETURNED"
        assert returned.return_date is not None

    def test_return_book_already_returned_raises(self):
        """return_book يرفع ValueError إذا كان الكتاب مُرجعاً مسبقاً."""
        from library.services import LibraryService

        school = SchoolFactory()
        book = LibraryBookFactory(school=school, quantity=1, available_qty=1)
        borrowing = BookBorrowingFactory(book=book, user=UserFactory(), status="RETURNED")

        with pytest.raises(ValueError, match="مُرجعة بالفعل"):
            LibraryService.return_book(borrowing)


# ══════════════════════════════════════════════
#  StaffService
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestStaffService:
    """اختبارات StaffService.get_staff_profile_data."""

    def test_get_staff_profile_data_returns_dict(self):
        """get_staff_profile_data يُعيد dict بالمفاتيح المطلوبة."""
        from staff_affairs.services import StaffService

        school = SchoolFactory()
        user = UserFactory()
        role = RoleFactory(school=school, name="teacher")
        MembershipFactory(user=user, school=school, role=role)

        data = StaffService.get_staff_profile_data(user, school, "2025-2026")

        expected_keys = {
            "membership",
            "profile",
            "absence_count",
            "absences_recent",
            "swaps_count",
            "compensatory_count",
            "evaluations",
            "leaves",
            "leave_balances",
            "weekly_slots",
        }
        assert expected_keys.issubset(data.keys())

    def test_get_staff_profile_data_zero_counts_for_new_user(self):
        """موظف جديد بلا غياب أو إجازات → counts = 0."""
        from staff_affairs.services import StaffService

        school = SchoolFactory()
        user = UserFactory()
        MembershipFactory(user=user, school=school)

        data = StaffService.get_staff_profile_data(user, school, "2025-2026")

        assert data["absence_count"] == 0
        assert data["swaps_count"] == 0
        assert data["weekly_slots"] == 0
        assert data["leaves"] == []


# ══════════════════════════════════════════════
#  ClinicService — get_health_statistics
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestClinicServiceHealthStats:
    """اختبارات ClinicService.get_health_statistics."""

    def test_get_health_statistics_returns_dict(self):
        """get_health_statistics يُعيد dict بالمفاتيح المطلوبة."""
        from clinic.services import ClinicService

        school = SchoolFactory()
        data = ClinicService.get_health_statistics(school)

        expected_keys = {
            "health_records_count",
            "allergies_count",
            "visits_count",
            "visits_this_month",
        }
        assert expected_keys == set(data.keys())

    def test_get_health_statistics_zero_for_empty_school(self):
        """مدرسة بلا بيانات → جميع الأعداد صفر."""
        from clinic.services import ClinicService

        school = SchoolFactory()
        data = ClinicService.get_health_statistics(school)

        assert data["visits_count"] == 0
        assert data["visits_this_month"] == 0


# ══════════════════════════════════════════════
#  LibraryService — get_chart_data
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestLibraryServiceCharts:
    """اختبارات LibraryService.get_chart_data."""

    def test_get_chart_data_structure(self):
        """get_chart_data يُعيد dict بـ categories و monthly."""
        from library.services import LibraryService

        school = SchoolFactory()
        data = LibraryService.get_chart_data(school)

        assert "categories" in data
        assert "monthly" in data
        assert "labels" in data["categories"]
        assert "data" in data["categories"]
        assert "labels" in data["monthly"]
        assert "data" in data["monthly"]

    def test_get_chart_data_empty_school(self):
        """مدرسة بلا كتب → lists فارغة."""
        from library.services import LibraryService

        school = SchoolFactory()
        data = LibraryService.get_chart_data(school)

        assert data["categories"]["labels"] == []
        assert data["categories"]["data"] == []
        assert data["monthly"]["labels"] == []
        assert data["monthly"]["data"] == []


# ══════════════════════════════════════════════
#  GradeService — get_chart_data
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestGradeServiceCharts:
    """اختبارات GradeService.get_chart_data."""

    def test_get_chart_data_returns_expected_keys(self):
        """get_chart_data يُعيد dict بـ 3 مقاطع رئيسية."""
        from assessments.services import GradeService

        school = SchoolFactory()
        data = GradeService.get_chart_data(school, "2025-2026")

        assert "grade_distribution" in data
        assert "class_comparison" in data
        assert "subject_comparison" in data

    def test_get_chart_data_grade_distribution_has_6_bands(self):
        """grade_distribution يحتوي دائماً على 6 bands."""
        from assessments.services import GradeService

        school = SchoolFactory()
        data = GradeService.get_chart_data(school, "2025-2026")

        assert len(data["grade_distribution"]["labels"]) == 6
        assert len(data["grade_distribution"]["data"]) == 6
        assert all(v == 0 for v in data["grade_distribution"]["data"])
