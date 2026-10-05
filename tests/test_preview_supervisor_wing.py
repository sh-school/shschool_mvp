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
