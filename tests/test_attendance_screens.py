"""شاشاتُ رصد المعلّم واعتمادِه: إدخالٌ وطابورٌ وقرارٌ وتقرير، والظهورُ V1–V3 (W-20261002-020).

القاعدةُ في `attendance_policy` وقد اختُبرت بدوالّها؛ وهنا اختبارُ **الواجهات**: من يصل إلى ماذا، وما يُعرض، وأن لا استعلامَ يقفز
على مدرسةٍ أو شعبةٍ (IDOR)، وأنّ المعلَّق لا يظهر حضوراً ولا غياباً.
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.attendance_entries import submit_entry
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import at

pytestmark = pytest.mark.django_db


@pytest.fixture
def now_0730(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


@pytest.fixture
def now_1500(monkeypatch):
    """بعد نهاية الدوام (13:30) — خارجَ نافذة الإدخال."""
    monkeypatch.setattr(timezone, "now", lambda: at(15, 0))


def _enter_url(session):
    return reverse("attendance_entry", args=[session.id])


def _post_entry(client_as, user, session, kid, status="absent", **extra):
    return client_as(user).post(
        _enter_url(session), {"student_id": str(kid.id), "status": status, **extra}
    )


def _entry(teacher, session, kid, status="absent"):
    return submit_entry(teacher, session, kid, status, now=at(7, 30))


# ══════════════════════════════════════════════════════════════════
# إدخال المعلّم
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# V1–V3: الظهور
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# طابور الاعتماد والقرار
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# تقرير «غيرُ معتمَد بعد X ساعة»
# ══════════════════════════════════════════════════════════════════
