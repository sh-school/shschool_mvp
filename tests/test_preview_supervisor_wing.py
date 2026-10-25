"""[W-20261003-023] حسابُ المشرف الإداريّ الوهميّ يغطّي جناحاً بعد كلّ `preview_accounts --sync` (قرارُ المالك 2026-10-04: تغطيةٌ لا استبدالُ حامل).

كان بلا جناحٍ فيرى «لا جناحَ مُسنَدٌ إليك» والفهرسُ فارغٌ وطلبُ شعبةٍ 404 (`wings_of` لغير القيادة) — كأنّ رصدَ الغياب اختفى. والتغطيةُ داخل `--sync`
فلا تضيع بعد إعادة بناء قاعدة المعاينة، ولا تمسّ أصيلَ أيّ جناحٍ ولا أيَّ حسابٍ، ويبقى الأمرُ حيث يعمل وحدَه (بيئةُ المعاينة والربطُ المحلّيّ وكلمةُ البيئة).
"""

import pytest
from django.core.management import CommandError
from django.utils import timezone

from core import preview_accounts as pa
from core.models import AuditLog, CustomUser, Wing, WingCoverage
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import _staff
from tests.test_preview_accounts import PREVIEW, _sync, password, preview_env  # noqa: F401
from wings.services import wings_of

pytestmark = pytest.mark.django_db


def _supervisor():
    return CustomUser.objects.get(employee_number=pa.EMPLOYEE_NUMBERS["admin_supervisor"])


def _wing(school, year, code, order, supervisor=None):
    return Wing.objects.create(
        school=school,
        code=code,
        name=f"جناح {code}",
        academic_year=year,
        order=order,
        supervisor=supervisor,
    )


@PREVIEW
def test_sync_covers_one_wing_without_touching_its_holder(school, year, preview_env):  # noqa: F811
    real = _staff(school, "admin_supervisor", "مشرف حقيقيّ", "29000001040")
    other = _staff(school, "admin_supervisor", "مشرف آخر", "29000001042")
    first = _wing(school, year, "w1", 1, supervisor=real)
    second = _wing(school, year, "w2", 2, supervisor=other)
    _sync()
    user = _supervisor()
    assert WingCoverage.objects.filter(substitute=user).count() == 1
    cover = WingCoverage.objects.get(substitute=user)
    assert cover.wing_id == first.id and cover.end_date is None
    assert cover.covers(timezone.localdate())
    # الأصلاءُ كما هم
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.supervisor_id, second.supervisor_id) == (real.id, other.id)
    # ويحمل الجناحَ فعلاً اليوم: يراه في wings_of ويُعدّ حاملَه
    assert [w.code for w in wings_of(user, school, year)] == ["w1"]
    assert first.current_supervisor() == user


@PREVIEW
def test_a_wing_with_an_active_coverage_is_skipped(school, year, preview_env):  # noqa: F811
    real = _staff(school, "admin_supervisor", "مشرف حقيقيّ", "29000001043")
    sub = _staff(school, "admin_supervisor", "بديل حقيقيّ", "29000001044")
    busy = _wing(school, year, "w1", 1, supervisor=real)
    _wing(school, year, "w2", 2)
    WingCoverage.objects.create(
        wing=busy, substitute=sub, reason="absence", start_date=timezone.localdate()
    )
    _sync()
    assert WingCoverage.objects.get(substitute=_supervisor()).wing.code == "w2"
    assert WingCoverage.objects.get(substitute=sub).wing_id == busy.id  # لم تُمسّ


@PREVIEW
def test_coverage_is_idempotent(school, year, preview_env):  # noqa: F811
    _wing(school, year, "w1", 1)
    _wing(school, year, "w2", 2)
    _sync()
    _sync()
    assert WingCoverage.objects.filter(substitute=_supervisor()).count() == 1
    assert AuditLog.objects.filter(object_repr__contains="تغطيةُ جناح").count() == 1


@PREVIEW
def test_when_every_wing_is_already_covered_nothing_is_forced(school, year, preview_env):  # noqa: F811
    sub = _staff(school, "admin_supervisor", "بديل حقيقيّ", "29000001045")
    only = _wing(school, year, "w1", 1)
    WingCoverage.objects.create(
        wing=only, substitute=sub, reason="absence", start_date=timezone.localdate()
    )
    _sync()
    assert not WingCoverage.objects.filter(substitute=_supervisor()).exists()
    assert _supervisor().is_active  # الحسابُ يُبذر رغم ذلك


@PREVIEW
def test_a_school_without_wings_still_syncs(school, year, preview_env):  # noqa: F811
    _sync()
    assert _supervisor().is_active
    assert not WingCoverage.objects.exists()


def test_nothing_is_covered_outside_the_preview_environment(school, year, monkeypatch):
    monkeypatch.delenv("PREVIEW_DB_NAME", raising=False)
    _wing(school, year, "w1", 1)
    with pytest.raises(CommandError):
        _sync()
    assert not WingCoverage.objects.exists()


def _teacher_session_in(school, year, wing, hour):
    """حصّةٌ اليومَ للمعلّم الوهميّ في شعبةٍ تتبع `wing` (المعلّمُ يُبذر في `--sync` الأوّل)."""
    import datetime as dt

    from operations.models import Session
    from tests.conftest import ClassGroupFactory

    teacher = CustomUser.objects.get(employee_number=pa.EMPLOYEE_NUMBERS["teacher"])
    klass = ClassGroupFactory(
        school=school,
        grade="G10",
        section=f"s{hour}",
        level_type="sec",
        academic_year=year,
        wing=wing,
    )
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=timezone.localdate(),
        start_time=dt.time(hour, 10),
        end_time=dt.time(hour, 55),
        status="scheduled",
    )


@PREVIEW
def test_resync_moves_the_own_coverage_to_the_wing_of_the_preview_teachers_sessions(
    school,
    year,
    preview_env,  # noqa: F811
):
    """W-20261005-001: المنتقى «أوّلُ جناحٍ حرّ» (w1) لا جناحُ حصص المعلّم (w2) فلا يصل رصدُه المشرفَ؛ إعادةُ `--sync` بعد البذر تنقل تغطيةَ هذا الحساب نفسِه إلى w2
    (لا يحمل أحدٌ تغطيتين فلا إضافةَ؛ ونقلٌ لا حذف)، وتغطيةُ غيره لا تُمسّ."""
    other = _staff(school, "admin_supervisor", "بديل حقيقيّ", "29000001046")
    w1 = _wing(school, year, "w1", 1)
    w2 = _wing(school, year, "w2", 2)
    w3 = _wing(school, year, "w3", 3)
    WingCoverage.objects.create(
        wing=w3, substitute=other, reason="absence", start_date=timezone.localdate()
    )
    _sync()  # بلا حصصٍ بعدُ: أوّلُ جناحٍ حرّ
    user = _supervisor()
    first = WingCoverage.objects.get(substitute=user)
    assert first.wing_id == w1.id
    _teacher_session_in(school, year, w2, 8)
    _sync()
    moved = WingCoverage.objects.get(substitute=user)
    assert moved.pk == first.pk and moved.wing_id == w2.id  # نُقلت لا حُذفت ولا أُضيفت
    assert WingCoverage.objects.get(substitute=other).wing_id == w3.id  # تغطيةُ غيره لم تُمسّ
    _sync()  # متساوي الأثر
    assert WingCoverage.objects.filter(substitute=user).count() == 1
    assert WingCoverage.objects.get(substitute=user).wing_id == w2.id


@PREVIEW
def test_a_coverage_written_by_someone_else_is_never_moved(school, year, preview_env):  # noqa: F811
    w1 = _wing(school, year, "w1", 1)
    w2 = _wing(school, year, "w2", 2)
    _sync()
    user = _supervisor()
    WingCoverage.objects.filter(substitute=user).update(note="كتبها بشريّ")
    _teacher_session_in(school, year, w2, 8)
    _sync()
    assert WingCoverage.objects.get(substitute=user).wing_id == w1.id


@PREVIEW
def test_the_first_sync_already_prefers_the_teachers_wing_when_he_has_sessions(
    school,
    year,
    preview_env,  # noqa: F811
):
    _wing(school, year, "w1", 1)
    w2 = _wing(school, year, "w2", 2)
    _sync()  # يُنشئ المعلّم الوهميّ
    WingCoverage.objects.filter(substitute=_supervisor()).delete()  # كإعادة بناءٍ للتغطية وحدها
    _teacher_session_in(school, year, w2, 9)
    _sync()
    assert [c.wing.code for c in WingCoverage.objects.filter(substitute=_supervisor())] == ["w2"]


def test_the_wing_pinning_never_runs_outside_the_preview_environment(school, year, monkeypatch):
    monkeypatch.delenv("PREVIEW_DB_NAME", raising=False)
    _wing(school, year, "w1", 1)
    with pytest.raises(CommandError):
        _sync()
    assert not WingCoverage.objects.exists()


# ── المعلّم الوهميّ يُسنَد لجناحٍ واحدٍ يغطّيه المشرف (W-20261005-005) ───────────────────────────────


def _class_in(school, year, wing, section):
    from tests.conftest import ClassGroupFactory

    return ClassGroupFactory(
        school=school, grade="G10", section=section, level_type="sec", academic_year=year, wing=wing
    )


def _teacher_assignments(school):
    from operations.models import SubjectClassAssignment

    teacher = CustomUser.objects.get(employee_number=pa.EMPLOYEE_NUMBERS["teacher"])
    return SubjectClassAssignment.objects.filter(school=school, teacher=teacher)


@PREVIEW
def test_the_preview_teacher_is_assigned_only_to_the_wing_the_supervisor_covers(
    school,
    year,
    preview_env,  # noqa: F811
):
    from operations.models import Subject

    Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
    w1 = _wing(school, year, "w1", 1)
    w3 = _wing(school, year, "w3", 3)
    for i in range(3):
        _class_in(school, year, w1, f"a{i}")
        _class_in(school, year, w3, f"b{i}")
    _class_in(school, year, None, "ESE")
    _sync()
    _sync()  # متساوي الأثر
    covered = set(
        WingCoverage.objects.filter(substitute=_supervisor()).values_list("wing_id", flat=True)
    )
    assert len(covered) == 1
    rows = list(_teacher_assignments(school).select_related("class_group"))
    assert rows
    for row in rows:
        wing_id = row.class_group.wing_id
        assert wing_id in covered or wing_id is None  # الجناحُ المغطّى أو التربيةُ الخاصّة بلا جناح
    assert len(rows) == len({row.class_group_id for row in rows})  # لا تكرار
    assert sum(1 for row in rows if row.class_group.wing_id is None) <= 2


@PREVIEW
def test_an_existing_assignment_of_the_preview_teacher_is_never_touched_or_added_to(
    school,
    year,
    preview_env,  # noqa: F811
):
    from operations.models import Subject, SubjectClassAssignment

    subject = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
    w1 = _wing(school, year, "w1", 1)
    _class_in(school, year, w1, "a0")
    elsewhere = _class_in(school, year, _wing(school, year, "w3", 3), "b0")
    _sync()  # يُنشئ الحسابات
    teacher = CustomUser.objects.get(employee_number=pa.EMPLOYEE_NUMBERS["teacher"])
    SubjectClassAssignment.objects.all().delete()
    kept = SubjectClassAssignment.objects.create(
        school=school,
        class_group=elsewhere,
        subject=subject,
        teacher=teacher,
        weekly_periods=2,
        academic_year=year,
    )
    _sync()
    assert list(_teacher_assignments(school).values_list("pk", flat=True)) == [kept.pk]


@PREVIEW
def test_another_teachers_assignment_in_the_class_is_never_replaced(
    school,
    year,
    preview_env,  # noqa: F811
    teacher,
):
    from operations.models import Subject, SubjectClassAssignment

    subject = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
    w1 = _wing(school, year, "w1", 1)
    klass = _class_in(school, year, w1, "a0")
    real = SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=2,
        academic_year=year,
    )
    _sync()
    real.refresh_from_db()
    assert real.teacher_id == teacher.id
    assert not _teacher_assignments(school).exists()  # لا مادّةَ حرّةً في الشعبة فلا إسناد
