"""الارتدادُ إلى الثابت المجمَّد عَرَضٌ يُبلَّغ — لا سلوكٌ يُسكَت عنه.

`CURRENT_ACADEMIC_YEAR` ثابتٌ يتقادم صامتاً، والغايةُ حذفُه. لكنّ الحذفَ قبل
أن نعرف من يرتدّ إليه على الإنتاج يكسر مساراً خفيّاً. فهذه المرحلةُ تجعل كلَّ
ارتدادٍ مرئيّاً بثلاث: عدّادٌ، وسجلّ، وحدثُ Sentry واحدٌ لكلّ سبب.
"""

import logging

import pytest

from core import academic_calendar as cal


@pytest.fixture(autouse=True)
def _fresh_reporting():
    cal._REPORTED.clear()
    yield
    cal._REPORTED.clear()


def _count(reason: str) -> float:
    return cal.FROZEN_FALLBACKS.labels(reason=reason)._value.get()


def test_a_school_without_calendar_is_counted_logged_and_reported(school, caplog, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "sentry_sdk.capture_message", lambda msg, level=None: sent.append((msg, level))
    )
    reason = f"school-without-calendar:{school.code}"
    before = _count(reason)

    with caplog.at_level(logging.WARNING, logger="core.academic_calendar"):
        year = cal.academic_year_for_school(school)

    from django.conf import settings

    assert year == settings.CURRENT_ACADEMIC_YEAR, "الارتدادُ يُعيد الثابت — الإبلاغُ لا يغيّر الجواب"
    assert _count(reason) == before + 1
    assert any(reason in r.getMessage() for r in caplog.records), "السببُ في السجلّ"
    assert sent == [(f"academic_calendar: frozen-year fallback ({reason})", "warning")]


def test_sentry_hears_each_reason_once_per_process(school, monkeypatch):
    sent = []
    monkeypatch.setattr("sentry_sdk.capture_message", lambda msg, level=None: sent.append(msg))

    cal.academic_year_for_school(school)
    cal.academic_year_for_school(school)
    cal.academic_year_for_school(school)

    assert len(sent) == 1, "حدثٌ واحدٌ لا سيل"


def test_a_seeded_calendar_never_falls_back(seeded_calendar, school, caplog):
    with caplog.at_level(logging.WARNING, logger="core.academic_calendar"):
        year = cal.academic_year_for_school(school)

    assert year == seeded_calendar
    assert not [r for r in caplog.records if "الثابت المجمَّد" in r.getMessage()]


def test_the_request_without_user_has_its_own_reason(rf, caplog):
    request = rf.get("/")
    request.user = None
    before = _count("request-without-user")

    with caplog.at_level(logging.WARNING, logger="core.academic_calendar"):
        cal.academic_year_for(request)

    assert _count("request-without-user") == before + 1
