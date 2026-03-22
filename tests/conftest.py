"""
tests/conftest.py
Factories & shared fixtures for SchoolOS test suite
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يستخدم factory_boy لتوليد بيانات اختبار واقعية
"""

from datetime import date, timedelta

import factory
import pytest

from behavior.models import BehaviorInfraction

# نماذج مُنقلة — لا تزال متاحة من core بفضل re-exports
from clinic.models import ClinicVisit, HealthRecord
from core.models import (
    ClassGroup,
    CustomUser,
    Membership,
    ParentStudentLink,
    Role,
    School,
    StudentEnrollment,
)
from library.models import BookBorrowing, LibraryBook
from transport.models import SchoolBus

# ══════════════════════════════════════════════
#  FACTORIES
# ══════════════════════════════════════════════


class SchoolFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = School

    name = factory.Sequence(lambda n: f"مدرسة الشحانية {n}")
    code = factory.Sequence(lambda n: f"SCH{n:03d}")
    is_active = True


class RoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Role
        django_get_or_create = ("school", "name")

    school = factory.SubFactory(SchoolFactory)
    name = "teacher"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomUser

    national_id = factory.Sequence(lambda n: f"2876{n:07d}")
    full_name = factory.Sequence(lambda n: f"موظف {n}")
    email = factory.Sequence(lambda n: f"user{n}@school.qa")
    phone = factory.Sequence(lambda n: f"+97466{n:06d}")
    is_active = True
    must_change_password = False

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or "testpass123")
        if create:
            obj.save()


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory(UserFactory)
    school = factory.SubFactory(SchoolFactory)
    role = factory.SubFactory(RoleFactory)
    is_active = True


# بعد التعديل (صحيح):
class ClassGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ClassGroup

    school = factory.SubFactory(SchoolFactory)
    grade = "G7"
    section = factory.Sequence(lambda n: f"أ{n}")
    level_type = "prep"
    academic_year = "2025-2026"


class StudentEnrollmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StudentEnrollment

    student = factory.SubFactory(UserFactory)
    class_group = factory.SubFactory(ClassGroupFactory)
    is_active = True


class HealthRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HealthRecord

    student = factory.SubFactory(UserFactory)
    blood_type = "O+"
    allergies = ""
    chronic_diseases = ""
    medications = ""


class ClinicVisitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ClinicVisit

    school = factory.SubFactory(SchoolFactory)
    student = factory.SubFactory(UserFactory)
    nurse = factory.SubFactory(UserFactory)
    reason = "صداع"
    is_sent_home = False
    parent_notified = False


class SchoolBusFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SchoolBus

    school = factory.SubFactory(SchoolFactory)
    bus_number = factory.Sequence(lambda n: f"B-{n:03d}")
    driver_name = factory.Sequence(lambda n: f"سائق {n}")
    driver_phone = factory.Sequence(lambda n: f"+97466{n:06d}")
    capacity = 30
    karwa_id = ""


class BehaviorInfractionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BehaviorInfraction

    school = factory.SubFactory(SchoolFactory)
    student = factory.SubFactory(UserFactory)
    reported_by = factory.SubFactory(UserFactory)
    level = 1
    description = "تأخر عن الحصة"
    points_deducted = 5
    is_resolved = False


class LibraryBookFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LibraryBook

    school = factory.SubFactory(SchoolFactory)
    title = factory.Sequence(lambda n: f"كتاب {n}")
    author = factory.Sequence(lambda n: f"مؤلف {n}")
    category = "500"
    book_type = "PRINT"
    quantity = 3
    available_qty = 3


class BookBorrowingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BookBorrowing

    book = factory.SubFactory(LibraryBookFactory)
    user = factory.SubFactory(UserFactory)
    due_date = factory.LazyFunction(lambda: date.today() + timedelta(days=14))
    status = "BORROWED"


# ══════════════════════════════════════════════
#  PYTEST FIXTURES
# ══════════════════════════════════════════════


@pytest.fixture
def school(db):
    return SchoolFactory()


@pytest.fixture
def principal_user(db, school):
    """مدير المدرسة"""
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def teacher_user(db, school):
    """معلم"""
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلم الرياضيات")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def nurse_user(db, school):
    """ممرض"""
    role = RoleFactory(school=school, name="nurse")
    user = UserFactory(full_name="ممرض المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def bus_supervisor_user(db, school):
    """مشرف الباص"""
    role = RoleFactory(school=school, name="bus_supervisor")
    user = UserFactory(full_name="مشرف النقل")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def librarian_user(db, school):
    """أمين المكتبة"""
    role = RoleFactory(school=school, name="librarian")
    user = UserFactory(full_name="أمين المكتبة")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def specialist_user(db, school):
    """أخصائي اجتماعي"""
    role = RoleFactory(school=school, name="specialist")
    user = UserFactory(full_name="الأخصائي الاجتماعي")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def student_user(db, school):
    """طالب"""
    role = RoleFactory(school=school, name="student")
    user = UserFactory(full_name="طالب 1")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def parent_user(db, school, student_user):
    """ولي أمر مرتبط بطالب"""
    role = RoleFactory(school=school, name="parent")
    user = UserFactory(full_name="ولي الأمر")
    MembershipFactory(user=user, school=school, role=role)
    ParentStudentLink.objects.create(
        parent=user,
        student=student_user,
        school=school,
        can_view_grades=True,
        can_view_attendance=True,
    )
    return user


@pytest.fixture
def class_group(db, school):
    return ClassGroupFactory(school=school)


@pytest.fixture
def enrolled_student(db, school, student_user, class_group):
    return StudentEnrollmentFactory(student=student_user, class_group=class_group)


@pytest.fixture
def health_record(db, student_user):
    return HealthRecordFactory(student=student_user)


@pytest.fixture
def clinic_visit(db, school, student_user, nurse_user):
    return ClinicVisitFactory(school=school, student=student_user, nurse=nurse_user)


@pytest.fixture
def school_bus(db, school, bus_supervisor_user):
    return SchoolBusFactory(school=school, supervisor=bus_supervisor_user)


@pytest.fixture
def behavior_infraction(db, school, student_user, teacher_user):
    return BehaviorInfractionFactory(school=school, student=student_user, reported_by=teacher_user)


@pytest.fixture
def library_book(db, school):
    return LibraryBookFactory(school=school)


@pytest.fixture
def book_borrowing(db, library_book, student_user):
    book = library_book
    book.available_qty = 2
    book.save()
    return BookBorrowingFactory(book=book, user=student_user)


# ── Client helpers ─────────────────────────────────────────


@pytest.fixture
def client_as(client):
    """يُعيد دالة لتسجيل الدخول بأي مستخدم"""

    def _login(user):
        client.force_login(user)
        return client

    return _login
