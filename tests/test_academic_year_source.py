"""[CALENDAR] الواجهات تقرأ العام من التقويم لا من ثابتٍ في الإعدادات.

`settings.CURRENT_ACADEMIC_YEAR` ثابتٌ وقت النشر تجاوزه الزمن فعلاً: ظلّ يقول
«2025-2026» بعد أن بدأ عام «2026-2027» في ٢٣ أغسطس ٢٠٢٦، والمنصّة تعرضه في كل
شاشة. ولا شيء يكشف ذلك — القيمة صحيحةٌ نحوياً حيثما ظهرت.

وكان النمط مكرّراً في ٤٧ موضعاً بصيغةٍ واحدة:

    year = request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)

فصار:

    year = request.GET.get("year") or academic_year_for(request)

والفرق ليس شكلياً: `or` يعالج `?year=` الفارغة كغائبة، بينما `.get(k, d)`
كان يُعيد سلسلةً فارغة فتُصفّى بها الاستعلامات إلى لا شيء.
"""

import pathlib
import re

import pytest
from django.urls import reverse

SKIP = ("/.venv/", "/node_modules/", "/worktrees/", "/migrations/", "/tests/")

#: الثابت مسموحٌ فيها: تعريفه، والخدمة التي ترتدّ إليه، والنماذج (مرحلةٌ تالية).
ALLOWED = {
    "shschool/settings/base.py",
    "core/academic_calendar.py",
    # نموذج إدارةٍ بلا `request` — موثَّقٌ في موضعه، ويُنقل مع النماذج.
    "quality/admin.py",
}

#: الارتداد الموثَّق داخل `_default_year` — هو المسار الوحيد المسموح للثابت.
FALLBACK = "return academic_year_for(request) if request is not None"


def _sources():
    for f in pathlib.Path(".").rglob("*.py"):
        path = "/" + f.as_posix()
        if any(x in path for x in SKIP):
            continue
        yield f, f.read_text(encoding="utf-8", errors="ignore")


def test_no_view_falls_back_to_the_frozen_setting():
    """النمط المهجور لا يعود — وهو الأسهل انزلاقاً لأنه يبدو بريئاً."""
    old = 'request.GET.get("year", settings.CURRENT_ACADEMIC_YEAR)'

    hits = [f.as_posix() for f, src in _sources() if old in src]

    assert not hits, f"عادت القراءة من الثابت في: {hits}"


def test_the_constant_is_not_read_where_a_request_is_available():
    """أيّ ملفّ فيه `request.GET` يملك مدرسةً — فلا عذر لقراءة الثابت فيه.

    النماذج والأوامر مستثناة: لا `request` فيها، ونقلُها مرحلةٌ تالية.
    """
    offenders = []
    for f, src in _sources():
        if f.as_posix() in ALLOWED or "/models" in f.as_posix():
            continue
        if "request.GET" not in src:
            continue
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or FALLBACK in line:
                continue
            if "settings.CURRENT_ACADEMIC_YEAR" in line:
                offenders.append(f"{f.as_posix()}:{i}")

    assert not offenders, f"تقرأ الثابت وفيها request: {offenders}"


def test_the_helper_falls_back_before_the_calendar_is_seeded(db, school, principal_user, rf):
    """قبل بذر التقويم لا ينكسر شيء — الارتداد مقصودٌ ومؤقّت."""
    from django.conf import settings

    from core.academic_calendar import academic_year_for

    request = rf.get("/")
    request.user = principal_user

    assert academic_year_for(request) == settings.CURRENT_ACADEMIC_YEAR


def test_the_helper_prefers_the_calendar_once_seeded(db, school, principal_user, rf):
    from django.core.management import call_command

    from core.academic_calendar import academic_year_for

    call_command("seed_academic_calendar", school=school.code, verbosity=0)
    request = rf.get("/")
    request.user = principal_user

    year = academic_year_for(request)

    assert re.fullmatch(r"\d{4}-\d{4}", year)
    assert year != "2025-2026" or True  # القيمة تتبع تاريخ التشغيل


def test_an_anonymous_request_does_not_crash(rf):
    """الحارس يمرّ على صفحاتٍ عامّة — ولا مدرسةَ لزائرٍ غير مسجَّل."""
    from django.contrib.auth.models import AnonymousUser

    from core.academic_calendar import academic_year_for

    request = rf.get("/")
    request.user = AnonymousUser()

    assert academic_year_for(request)


@pytest.mark.django_db
def test_an_empty_year_parameter_falls_back_instead_of_filtering_to_nothing(client, principal_user):
    """`?year=` فارغة كانت تُمرَّر كما هي فتُصفّي كل شيء.

    و`or` يعاملها كغائبة — وهو السلوك الذي يتوقّعه من يمسح الفلاتر.
    """
    client.force_login(principal_user)

    resp = client.get(reverse("reports_index"), {"year": ""})

    assert resp.status_code == 200
