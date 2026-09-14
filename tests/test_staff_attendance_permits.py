"""
اختباراتُ شاملة لنموذجَي StaffAttendance و PermitRequest
موجةٌ 3G، الأجزاءُ 1.1 و 1.3

المرجعُ: وثيقةُ ت/د 2027/01 (سياسةُ الشحانية)
    - البند 1.1: الدوامُ الرسميّ من 7:00 إلى 14:00
    - البند 2.1: متأخّرٌ إن حضر بعد 7:00
    - البند 2.4: غائبٌ إن حضر بعد 9:00
    - البند 4.2: سقفُ استئذان 7 ساعات/شهر
    - البند 4.4: حدٌّ أقصى ساعتان/مرّة
"""

import pytest
from datetime import datetime, time, timedelta, date as date_type
from django.db import IntegrityError
from django.utils import timezone

from core.models import School, CustomUser
from core.models.access import Role, Membership
from staff_affairs.models import StaffAttendance, PermitRequest
from staff_affairs.services import StaffAttendanceService


@pytest.mark.django_db
class TestStaffAttendanceService:
    """اختباراتُ الخدمة الأساسيّة للحضور"""

    @pytest.fixture
    def school(self):
        """مدرسةٌ تجريبيّة"""
        return School.objects.create(
            code="TST",
            name="Test School",
        )

    @pytest.fixture
    def staff_user(self, school):
        """موظّفٌ تجريبيّ"""
        user = CustomUser.objects.create_user(
            username="teacher_test",
            email="teacher@test.qa",
            password="TempPass123!",
            full_name="معلّمٌ تجريبيّ",
        )
        # ربطُه بالمدرسة
        role = Role.objects.get_or_create(name="teacher")[0]
        Membership.objects.create(
            user=user,
            school=school,
            role=role,
            joined_at=timezone.now(),
            is_active=True,
        )
        return user

    def test_calculate_status_present_exactly_7_00(self):
        """الحاضرون: وقتُ الدخول ≤7:00 — البند 1.1"""
        status = StaffAttendanceService.calculate_status(time(7, 0))
        assert status == "present"

    def test_calculate_status_present_before_7_00(self):
        """الحاضرون: وقتُ الدخول قبل 7:00"""
        status = StaffAttendanceService.calculate_status(time(6, 30))
        assert status == "present"

    def test_calculate_status_late_7_01(self):
        """المتأخّرون: وقتُ الدخول > 7:00 — البند 2.1"""
        status = StaffAttendanceService.calculate_status(time(7, 1))
        assert status == "late"

    def test_calculate_status_late_8_59(self):
        """المتأخّرون: وقتُ الدخول < 9:00"""
        status = StaffAttendanceService.calculate_status(time(8, 59))
        assert status == "late"

    def test_calculate_status_absent_exactly_9_00(self):
        """الغائبون: وقتُ الدخول ≥9:00 — البند 2.4"""
        status = StaffAttendanceService.calculate_status(time(9, 0))
        assert status == "absent"

    def test_calculate_status_absent_after_9_00(self):
        """الغائبون: وقتُ الدخول بعد 9:00"""
        status = StaffAttendanceService.calculate_status(time(9, 5))
        assert status == "absent"

    def test_record_attendance_present(self, school, staff_user):
        """تسجيلُ حضورٍ — حالةُ حاضرٍ محسوبة تلقائياً"""
        today = timezone.localdate()
        check_in = time(6, 45)

        attendance = StaffAttendanceService.record_attendance(
            school=school,
            staff=staff_user,
            date=today,
            check_in_time=check_in,
        )

        assert attendance.status == "present"
        assert attendance.check_in_time == check_in
        assert attendance.school == school

    def test_record_attendance_late(self, school, staff_user):
        """تسجيلُ حضورٍ — حالةُ متأخّرٍ محسوبة تلقائياً"""
        today = timezone.localdate()
        check_in = time(8, 30)

        attendance = StaffAttendanceService.record_attendance(
            school=school,
            staff=staff_user,
            date=today,
            check_in_time=check_in,
        )

        assert attendance.status == "late"

    def test_record_attendance_absent(self, school, staff_user):
        """تسجيلُ حضورٍ — حالةُ غائبٍ محسوبة تلقائياً"""
        today = timezone.localdate()
        check_in = time(9, 15)

        attendance = StaffAttendanceService.record_attendance(
            school=school,
            staff=staff_user,
            date=today,
            check_in_time=check_in,
        )

        assert attendance.status == "absent"


@pytest.mark.django_db
class TestStaffAttendanceModel:
    """اختباراتُ نموذجِ StaffAttendance"""

    @pytest.fixture
    def school(self):
        return School.objects.create(
            code="TST",
            name="Test School",
        )

    @pytest.fixture
    def staff_user(self, school):
        user = CustomUser.objects.create_user(
            username="test_staff",
            email="staff@test.qa",
            password="TempPass123!",
            full_name="موظّفٌ تجريبيّ",
        )
        role = Role.objects.get_or_create(name="teacher")[0]
        Membership.objects.create(
            user=user,
            school=school,
            role=role,
            joined_at=timezone.now(),
            is_active=True,
        )
        return user

    def test_unique_attendance_per_day(self, school, staff_user):
        """لا سجلّان للحضورِ في نفسِ اليوم — قيدٌ فريد"""
        today = timezone.localdate()

        # إنشاءُ السجلِّ الأول
        StaffAttendance.objects.create(
            school=school,
            staff=staff_user,
            date=today,
            check_in_time=time(7, 0),
            status="present",
        )

        # محاولةُ إنشاءِ السجلِّ الثاني (يجب أن يرفعَ استثناءً)
        with pytest.raises(IntegrityError):
            StaffAttendance.objects.create(
                school=school,
                staff=staff_user,
                date=today,
                check_in_time=time(7, 15),
                status="present",
            )

    def test_permit_minutes_tracked(self, school, staff_user):
        """تتبّعُ دقائقِ الاستئذانِ المقبول"""
        today = timezone.localdate()

        attendance = StaffAttendance.objects.create(
            school=school,
            staff=staff_user,
            date=today,
            check_in_time=time(7, 0),
            permit_minutes=30,  # 30 دقيقةً استئذان
            status="present",
        )

        assert attendance.permit_minutes == 30


@pytest.mark.django_db
class TestPermitRequestModel:
    """اختباراتُ نموذجِ PermitRequest"""

    @pytest.fixture
    def school(self):
        return School.objects.create(
            code="TST",
            name="Test School",
        )

    @pytest.fixture
    def staff_user(self, school):
        user = CustomUser.objects.create_user(
            username="permit_test",
            email="permit@test.qa",
            password="TempPass123!",
            full_name="طالبُ إذنٍ",
        )
        role = Role.objects.get_or_create(name="teacher")[0]
        Membership.objects.create(
            user=user,
            school=school,
            role=role,
            joined_at=timezone.now(),
            is_active=True,
        )
        return user

    def test_permit_request_auto_duration(self, school, staff_user):
        """حسابُ المدّةِ التلقائيّ — البند 4.4"""
        today = timezone.localdate()

        permit = PermitRequest.objects.create(
            school=school,
            staff=staff_user,
            permit_type="permit",
            date=today,
            start_time=time(9, 0),
            end_time=time(10, 30),
            reason="مشروعٌ عائليّ",
            duration_minutes=0,  # سيُحسب في save()
        )

        # يجب أن تكونَ المدّةُ 90 دقيقة
        assert permit.duration_minutes == 90

    def test_permit_request_max_duration_validation(self, school, staff_user):
        """التحقّقُ من الحدِّ الأقصى — ساعتان — البند 4.4"""
        today = timezone.localdate()

        permit = PermitRequest(
            school=school,
            staff=staff_user,
            permit_type="permit",
            date=today,
            start_time=time(9, 0),
            end_time=time(11, 31),  # 151 دقيقة > 120
            reason="مشروعٌ طويل",
        )

        with pytest.raises(Exception):  # ValidationError
            permit.full_clean()

    def test_no_two_permits_same_day(self, school, staff_user):
        """لا إذنان مقبولان في نفسِ اليوم — البند 4.3"""
        today = timezone.localdate()

        # الإذنُ الأول
        permit1 = PermitRequest.objects.create(
            school=school,
            staff=staff_user,
            permit_type="permit",
            date=today,
            start_time=time(9, 0),
            end_time=time(10, 0),
            reason="السبب الأول",
            status="approved",
            duration_minutes=60,
        )

        # محاولةُ الإذنِ الثاني (يجب أن يرفعَ استثناءً)
        with pytest.raises(IntegrityError):
            PermitRequest.objects.create(
                school=school,
                staff=staff_user,
                permit_type="permit",
                date=today,
                start_time=time(10, 30),
                end_time=time(11, 0),
                reason="السبب الثاني",
                status="approved",
                duration_minutes=30,
            )


@pytest.mark.django_db
class TestPermitApprovalService:
    """اختباراتُ سير عملِ اعتمادِ الأذونات"""

    @pytest.fixture
    def school(self):
        return School.objects.create(
            code="TST",
            name="Test School",
        )

    @pytest.fixture
    def staff_user(self, school):
        user = CustomUser.objects.create_user(
            username="staff_user",
            email="staff@test.qa",
            password="TempPass123!",
            full_name="موظّفٌ",
        )
        role = Role.objects.get_or_create(name="teacher")[0]
        Membership.objects.create(
            user=user,
            school=school,
            role=role,
            joined_at=timezone.now(),
            is_active=True,
        )
        return user

    @pytest.fixture
    def reviewer_user(self, school):
        user = CustomUser.objects.create_user(
            username="reviewer",
            email="reviewer@test.qa",
            password="TempPass123!",
            full_name="مراجعٌ",
        )
        role = Role.objects.get_or_create(name="vice_academic")[0]
        Membership.objects.create(
            user=user,
            school=school,
            role=role,
            joined_at=timezone.now(),
            is_active=True,
        )
        return user

    def test_approve_permit_within_monthly_limit(self, school, staff_user, reviewer_user):
        """اعتمادُ إذنٍ ضمنَ السقفِ الشهريّ — 7 ساعات"""
        today = timezone.localdate()

        permit = PermitRequest.objects.create(
            school=school,
            staff=staff_user,
            permit_type="permit",
            date=today,
            start_time=time(9, 0),
            end_time=time(10, 0),  # 60 دقيقة
            reason="سبب معقول",
            status="pending",
            duration_minutes=60,
        )

        # اعتمادٌ ناجح
        approved = StaffAttendanceService.approve_permit(
            permit_request=permit,
            reviewer=reviewer_user,
        )

        assert approved.status == "approved"
        assert approved.reviewed_by == reviewer_user

    def test_reject_permit_exceeds_monthly_limit(self, school, staff_user, reviewer_user):
        """رفضُ إذنٍ يتجاوزُ السقفَ الشهريّ"""
        today = timezone.localdate()

        # إنشاءُ 6 ساعات مقبولة فعلاً
        for i in range(6):
            PermitRequest.objects.create(
                school=school,
                staff=staff_user,
                permit_type="permit",
                date=today - timedelta(days=i),
                start_time=time(9, 0),
                end_time=time(10, 0),
                reason=f"سبب {i}",
                status="approved",
                duration_minutes=60,
            )

        # محاولةُ إضافةِ ساعةٍ أخرى (ستتجاوزُ الـ 7 ساعات)
        permit_new = PermitRequest.objects.create(
            school=school,
            staff=staff_user,
            permit_type="permit",
            date=today + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),  # ساعةٌ إضافيّة
            reason="سبب إضافي",
            status="pending",
            duration_minutes=60,
        )

        with pytest.raises(ValueError):  # السقفُ متجاوز
            StaffAttendanceService.approve_permit(permit_new, reviewer_user)


@pytest.mark.django_db
class TestMonthlyReportService:
    """اختباراتُ التقريرِ الشهريّ للحضور"""

    @pytest.fixture
    def school(self):
        return School.objects.create(
            code="TST",
            name="Test School",
        )

    @pytest.fixture
    def staff_user(self, school):
        user = CustomUser.objects.create_user(
            username="report_test",
            email="report@test.qa",
            password="TempPass123!",
            full_name="موظّفٌ للتقرير",
        )
        role = Role.objects.get_or_create(name="teacher")[0]
        Membership.objects.create(
            user=user,
            school=school,
            role=role,
            joined_at=timezone.now(),
            is_active=True,
        )
        return user

    def test_monthly_report_structure(self, school, staff_user):
        """التقريرُ الشهريّ يحتويكن الحقولَ الصحيحة"""
        today = timezone.localdate()
        year = today.year
        month = today.month

        # إنشاءُ سجلّات اختبارية
        StaffAttendance.objects.create(
            school=school,
            staff=staff_user,
            date=today,
            check_in_time=time(6, 45),
            status="present",
        )

        report = StaffAttendanceService.get_monthly_report(
            school=school,
            staff=staff_user,
            year=year,
            month=month,
        )

        # التحقّقُ من البنية
        assert "days" in report
        assert "summary" in report
        assert "permit_used" in report
        assert "permit_remaining" in report
        assert report["summary"]["present"] >= 1
        assert report["permit_remaining"] <= 420  # 7 ساعات بالدقائق
