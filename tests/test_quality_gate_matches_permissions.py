"""[SECURITY] بوّابة الوحدة تسع من تسمّيه صلاحياتُها.

الوسيط يحرس `/quality/` بقائمة أدوارٍ في `quality/apps.py`، والدوالُّ
تحرس نفسها بثوابت `core/permissions.py`. والوسيط يسبق الدالّة — فدورٌ
مأذونٌ في الثانية ومحجوبٌ في الأولى يُردّ قبل أن تُقرأ صلاحيتُه.

وقد حدث: `academic_advisor` في `OBSERVATION_CREATE` — أي يُنشئ زيارةً
إشرافية — و`activities_coordinator` في `OBSERVATION_SELF_CREATE`، وكلاهما
محجوبٌ عن الوحدة كلّها. فالإذنُ مكتوبٌ ولا يُنال.
"""

import pytest

from core.module_registry import get_protected_paths
from core.permissions import (
    OBSERVATION_CREATE,
    OBSERVATION_PEER_CREATE,
    OBSERVATION_SELF_CREATE,
    OBSERVATION_VIEW_ALL,
)

GRANTED = (
    OBSERVATION_CREATE | OBSERVATION_SELF_CREATE | OBSERVATION_PEER_CREATE | OBSERVATION_VIEW_ALL
)


@pytest.fixture
def gate():
    return set(get_protected_paths()["/quality/"])


@pytest.mark.parametrize("role", sorted(GRANTED))
def test_every_granted_role_passes_the_module_gate(role, gate):
    assert role in gate, f"«{role}» مأذونٌ في الزيارات ومحجوبٌ عن الوحدة"


def test_the_gate_is_not_open_to_everyone(gate):
    """الحارسُ يوسَّع بقدر ما تسمّيه الصلاحيات، لا أكثر."""
    assert "student" not in gate
    assert "parent" not in gate
    assert "bus_supervisor" not in gate
