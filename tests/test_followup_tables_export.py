"""عقدُ التصدير لجداول المتابعة (W-20261109-006): الصفحةُ وExcel وPDF يقرؤون المحدِّدَ نفسَه، لثلاثة أدوار: مدير ومشرف جناح ومعلّم.

الجداولُ: الحضورُ والسلوكُ (نظرةٌ عامّة) والتأخّرُ والأنشطةُ والتحرّكاتُ، والتقريرُ السلوكيّ اليوميّ وإحصاءُ السلوك وملفُّ الطالب.
كلُّ جدولٍ يُقاس على: نطاقِ الدور (المشرفُ جناحَه وحدَه)، وعمودِ «م» وفرزِ الجناح، وإخفاءِ الأعمدة، وحجبِ من لا قدرةَ له.
"""

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404, QueryDict
from django.urls import reverse
from django.utils import timezone

from behavior.export_tables import (
    DAILY_TABLE,
    PROFILE_TABLE,
    STATISTICS_TABLE,
)
from core.exports import contract, registry
from core.models import Wing
from operations.models import Session, StudentAttendance
from student_affairs.followup_tables import (
    ABSENCE_TABLE,
    ACTIVITY_TABLE,
    BEHAVIOR_TABLE,
    MOVEMENT_TABLE,
    TARDINESS_TABLE,
)
from student_affairs.models import StudentActivity
from tests.conftest import (
    BehaviorInfractionFactory,
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

FIRST_WING = "طالبُ الجناح الأوّل"
SECOND_WING = "طالبُ الجناح الثاني"


def _staff(school, role, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _pupil(school, klass, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=user, class_group=klass)
    return user


def _session(school, klass, teacher, hour, minute=10):
    """حصّةُ اليوم؛ والدقيقةُ تفرّق الشعبتين لأنّ قيد «معلّمٌ واحدٌ في وقتٍ واحد» يرفض تطابقهما."""
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=timezone.localdate(),
        start_time=dt.time(hour, minute),
        end_time=dt.time(hour, minute + 30),
        period_number=1,
        status="scheduled",
    )


@pytest.fixture
def world(school, seeded_calendar, principal_user):
    """جناحان: ترتيبُ الأوّل 2 والثاني 1 — فيتقدّم الثاني في فرز الجناح. ولكلٍّ طالبٌ بكلّ أنواع البيانات."""
    supervisor = _staff(school, "admin_supervisor", "مشرف الجناح الأوّل", "29000000001")
    other_supervisor = _staff(school, "admin_supervisor", "مشرف الجناح الثاني", "29000000002")
    teacher = _staff(school, "teacher", "معلّم الحصص", "29000000003")
    idle_teacher = _staff(school, "teacher", "معلّمٌ بلا طلاب", "29000000004")
    classes = {}
    pupils = {}
    for key, grade, section, order, boss, name, nid in (
        ("first", "G7", "1", 2, supervisor, FIRST_WING, "29000000011"),
        ("second", "G8", "2", 1, other_supervisor, SECOND_WING, "29000000012"),
    ):
        klass = ClassGroupFactory(
            school=school,
            grade=grade,
            section=section,
            level_type="prep",
            academic_year=seeded_calendar,
        )
        klass.wing = Wing.objects.create(
            school=school,
            code=f"w{order}",
            name=f"جناح {order}",
            academic_year=seeded_calendar,
            supervisor=boss,
            order=order,
        )
        klass.save(update_fields=["wing"])
        classes[key] = klass
        pupils[key] = _pupil(school, klass, name, nid)

    scope = StudentActivity.SCOPE_CHOICES[0][0]
    kind = StudentActivity.TYPE_CHOICES[0][0]
    for hour, status in ((8, "absent"), (9, "late")):
        for index, (key, pupil) in enumerate(pupils.items()):
            StudentAttendance.objects.create(
                school=school,
                session=_session(school, classes[key], teacher, hour, minute=10 + index * 5),
                student=pupil,
                status=status,
                tardiness_recorded_at=timezone.now() if status == "late" else None,
            )
    for pupil in pupils.values():
        infraction = BehaviorInfractionFactory(school=school, student=pupil, reported_by=teacher)
        # `date` حقلٌ `auto_now_add` يقرأ ساعةَ النظام لا الساعةَ المثبَّتة، فنثبّت يومَ المخالفة ليوم التقرير
        type(infraction).objects.filter(pk=infraction.pk).update(date=timezone.localdate())
        StudentActivity.objects.create(
            school=school,
            student=pupil,
            activity_type=kind,
            title="نشاط اصطناعي",
            scope=scope,
            date=timezone.localdate(),
            academic_year=seeded_calendar,
            recorded_by=supervisor,
        )
    return {
        "principal": principal_user,
        "supervisor": supervisor,
        "teacher": teacher,
        "idle_teacher": idle_teacher,
        "pupils": pupils,
        "classes": classes,
    }


def _table(spec, user, query=""):
    return contract.table_rows(spec, user, QueryDict(query))


def _names(columns, rows):
    """أسماءُ الطلاب بترتيب الصفوف: عمودُ الاسم (بعد «م») مفتاحُه `full_name` أو `student`."""
    keys = [c.key for c in columns]
    index = 1 + next(keys.index(k) for k in ("full_name", "student") if k in keys)
    return [row[index] for row in rows]


#: جداولُ الطلبة بأسمائهم: (الجدول، مسارُ زرّ Excel بالمعاملات الإلزاميّة للقدرة)
NAMED_TABLES = [
    ABSENCE_TABLE,
    BEHAVIOR_TABLE,
    TARDINESS_TABLE,
    ACTIVITY_TABLE,
    MOVEMENT_TABLE,
    DAILY_TABLE,
]
STUDENT_AFFAIRS_ROUTES = {
    ABSENCE_TABLE.kind: "student_affairs:attendance_export",
    BEHAVIOR_TABLE.kind: "student_affairs:behavior_export",
    TARDINESS_TABLE.kind: "student_affairs:tardiness_export",
    ACTIVITY_TABLE.kind: "student_affairs:activities_export",
    MOVEMENT_TABLE.kind: "student_affairs:enrolment_movements_export",
}


@pytest.mark.parametrize("spec", NAMED_TABLES, ids=lambda s: s.kind)
class TestEveryNamedTableForThreeRoles:
    def test_the_manager_gets_the_whole_school_numbered_and_sorted_by_wing(self, world, spec):
        columns, rows = _table(spec, world["principal"])

        names = _names(columns, rows)
        assert {FIRST_WING, SECOND_WING} <= set(names)
        # الترقيمُ يُحسب عند الإخراج متّصلاً من 1، والجناحُ الأقلّ ترتيباً (الثاني) يسبق الأوّل.
        assert [row[0] for row in rows] == list(range(1, len(rows) + 1))
        assert names.index(SECOND_WING) < names.index(FIRST_WING)

    def test_the_wing_supervisor_gets_his_wing_alone(self, world, spec):
        if spec is MOVEMENT_TABLE:
            pytest.skip(
                "التحرّكاتُ للمدير ومنسّق الشؤون بقدرة `transfers`؛ والنطاقُ يُضيَّق بجناحه إن حُمل"
            )
        columns, rows = _table(spec, world["supervisor"])

        names = _names(columns, rows)
        assert FIRST_WING in names and SECOND_WING not in names
        assert [row[0] for row in rows] == list(range(1, len(rows) + 1))

    def test_the_teacher_is_refused_or_sees_only_his_pupils(
        self, world, spec, client_as, monkeypatch
    ):
        monkeypatch.setattr("core.tasks.run_export_job.apply_async", lambda *a, **k: None)
        if spec.kind in STUDENT_AFFAIRS_ROUTES:
            response = client_as(world["idle_teacher"]).get(
                reverse(STUDENT_AFFAIRS_ROUTES[spec.kind]), HTTP_X_REQUESTED_WITH="XMLHttpRequest"
            )
            assert response.status_code == 403
        else:
            _columns, rows = _table(spec, world["idle_teacher"])
            assert rows == []  # معلّمٌ بلا حصصٍ لا يرى مخالفةَ أحد

    def test_a_hidden_column_leaves_the_file(self, world, spec):
        hidden = spec.columns[-1]
        columns, rows = _table(spec, world["principal"], f"hide={hidden.key}")

        assert hidden.key not in [c.key for c in columns]
        assert all(len(row) == len(columns) + 1 for row in rows)


class TestTheStatisticsTable:
    def _first_section_total(self, user):
        _columns, rows = _table(STATISTICS_TABLE, user)
        return sum(row[3] for row in rows if row[1] == "التوزيع بالدرجة")

    def test_the_counts_follow_the_role(self, world):
        assert self._first_section_total(world["principal"]) == 2
        assert self._first_section_total(world["supervisor"]) == 1
        assert self._first_section_total(world["idle_teacher"]) == 0

    def test_the_rows_are_numbered_and_a_hidden_column_leaves(self, world):
        columns, rows = _table(STATISTICS_TABLE, world["principal"], "hide=section")

        assert [c.key for c in columns] == ["label", "count"]
        assert [row[0] for row in rows] == list(range(1, len(rows) + 1))


class TestTheStudentProfileTable:
    def _query(self, key, world):
        return f"student={world['pupils'][key].pk}"

    def test_the_manager_reads_any_pupil(self, world):
        for key in ("first", "second"):
            _columns, rows = _table(PROFILE_TABLE, world["principal"], self._query(key, world))
            assert len(rows) == 1 and rows[0][0] == 1

    def test_the_supervisor_reads_his_wing_and_gets_a_404_outside_it(self, world):
        _columns, rows = _table(PROFILE_TABLE, world["supervisor"], self._query("first", world))
        assert len(rows) == 1
        with pytest.raises(Http404):
            _table(PROFILE_TABLE, world["supervisor"], self._query("second", world))

    def test_a_teacher_without_the_pupil_is_refused(self, world):
        with pytest.raises((PermissionDenied, Http404)):
            _table(PROFILE_TABLE, world["idle_teacher"], self._query("first", world))

    def test_the_export_button_starts_a_job_for_a_reader(self, world, client_as, monkeypatch):
        monkeypatch.setattr("core.tasks.run_export_job.apply_async", lambda *a, **k: None)
        url = reverse("behavior:student_profile_xlsx", args=[world["pupils"]["first"].pk])

        response = client_as(world["principal"]).get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        assert response.status_code == 202


class TestThePageAndTheFileShareTheSelector:
    def test_the_activity_page_lists_the_rows_the_file_exports(self, world, client_as):
        page = client_as(world["principal"]).get(reverse("student_affairs:activity_list"))

        _columns, rows = _table(ACTIVITY_TABLE, world["principal"])
        assert [a["full_name"] for a in page.context["activities"]] == [r[1] for r in rows]

    def test_the_attendance_page_lists_the_rows_the_file_exports(self, world, client_as):
        page = client_as(world["principal"]).get(reverse("student_affairs:attendance_overview"))

        columns, rows = _table(ABSENCE_TABLE, world["principal"])
        assert [s["full_name"] for s in page.context["worst_students"]] == _names(columns, rows)

    def test_the_filter_reaches_every_result_not_the_first_page(self, world):
        klass = world["classes"]["first"]

        columns, rows = _table(TARDINESS_TABLE, world["principal"], f"grade={klass.grade}")

        assert _names(columns, rows) == [FIRST_WING]


class TestTheRegistration:
    @pytest.mark.parametrize(
        "kind",
        [s.kind for s in (*NAMED_TABLES, STATISTICS_TABLE, PROFILE_TABLE)],
    )
    def test_each_table_is_a_registered_background_kind_with_its_capability(self, kind):
        spec = registry.get(kind)

        assert spec is not None and spec.mode == "job"
        assert kind in contract.tables()
        assert spec.capability == contract.tables()[kind].capability

    @pytest.mark.parametrize(
        "kind",
        [
            "student_affairs.attendance_overview_pdf",
            "student_affairs.behavior_overview_pdf",
            "student_affairs.tardiness_pdf",
            "behavior.daily_pdf",
        ],
    )
    def test_each_pdf_is_registered_beside_its_table(self, kind):
        assert registry.get(kind) is not None
