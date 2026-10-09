"""[LEGAL] المطوّرُ لا يرصد حضورَ الأجنحة ولا يُدخل (D-128م، W-20261002-020).

قرارُ المالك: «المطوّرُ (`platform_developer`) لا يُدخل ولا يعتمد، ولو كان superuser». وكان `WING_DAY_RECORD` يضمّه فيكتب رصدَ المشرف
كما لو كان مشرفاً. فأُزيل من المجموعة ومن مصفوفة القدرة `wings.record_day`، و`is_recorder` لا يكفيه `is_superuser` وحدَه — فيقرأ
الدورَ بالاسم لا بصفة «المستخدم الخارق»، ولا يمرّ المطوّرُ منه ولو كان خارقاً.

حدٌّ معلَن: `capability_required` يتجاوز التحقّقَ للمستخدم الخارق في بوّابة المسارات (سلوكٌ عامٌّ قائم)؛ فهذا القرارُ يحمي دوالَّ الرصد
(`is_recorder`، `may_write`) والمجموعةَ والمصفوفة، لا بوّابةَ المسار.
"""

import pytest

from core import permissions
from core.capabilities import has_capability
from operations.day_attendance import is_recorder
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import _staff
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db


def test_the_group_no_longer_contains_the_developer():
    assert "platform_developer" not in permissions.WING_DAY_RECORD
    assert permissions.WING_DAY_RECORD == {
        "admin_supervisor",
        "vice_admin",
        "vice_academic",
        "principal",
        # منسّقُ شؤون الطلبة يرصد الغيابَ ويصحّحه كقيادته (قرارُ المالك D-266م، 2026-10-08).
        "student_affairs_coordinator",
    }


def test_the_developer_loses_the_record_capability_by_role(school):
    developer = _staff(school, "platform_developer", "المطوّر", "29000008001")
    assert not has_capability(developer, "wings.record_day")


def test_a_developer_is_not_a_recorder_even_as_a_superuser(school):
    developer = _staff(school, "platform_developer", "المطوّر", "29000008002")
    developer.is_superuser = True
    developer.save(update_fields=["is_superuser"])
    assert is_recorder(developer) is False


def test_a_non_developer_superuser_keeps_the_platforms_general_superuser_behaviour(school):
    """القاعدةُ العامّةُ في المنصّة (#781): المستخدمُ الخارقُ غيرُ المطوّر يمرّ — والاستثناءُ المسمّى هو المطوّرُ وحدَه."""
    root = UserFactory(full_name="superuser", national_id="29000008003", is_superuser=True)
    assert is_recorder(root) is True


@pytest.mark.parametrize("role", ["admin_supervisor", "vice_admin", "vice_academic", "principal"])
def test_the_legitimate_recorders_still_are(school, role):
    user = _staff(school, role, role, "29000008010")
    assert is_recorder(user) is True
