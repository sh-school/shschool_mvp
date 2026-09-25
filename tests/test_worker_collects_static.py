"""[RAILWAY] حاويةُ العامل تجمع الثابتَ قبل أن يقلع Celery — وإلّا فشل كلُّ تصديرٍ يُصيّر قالباً فيه `{% static %}` (N-042).

`collectstatic` يكتب في القرص المحلّيّ للحاوية (`STATIC_ROOT`) — كما شرح `scripts/railway-release.sh` بعد حادثة
2026-09-17 — فما كُتب في الويب أو في preDeploy لا يصل حاويةَ العامل. وكان `railway-worker.sh` لا يجمعه، فبدأ العاملُ
بمجلّدٍ فارغٍ بلا `staticfiles.json`؛ فسقط توليدُ PDF الجدول (قالبُه `print_schedule.html` يستدعي `{% static %}`) بـ
`ValueError: Missing staticfiles manifest entry` — أوّلُ حدثٍ 2026-09-23 في Sentry.

والحارسُ يقرأ السكربتَ نصّاً: السطرُ موجودٌ، وقبل `exec celery` (بعده لا يجري أبداً — `exec` يستبدل العمليّة)،
وبعد تصدير إعدادات production (فالتخزينُ المبصومُ هو الذي يكتب `staticfiles.json`)، وبالصيغة نفسها في سكربت الويب.
"""

import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
COLLECT = re.compile(r"^python manage\.py collectstatic --noinput\b")


def _lines(name: str) -> list[str]:
    return [
        line.strip()
        for line in (SCRIPTS / name).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _first(lines: list[str], pattern: str) -> int:
    for i, line in enumerate(lines):
        if re.search(pattern, line):
            return i
    raise AssertionError(f"لا سطرَ يطابق {pattern!r}")


@pytest.fixture(scope="module")
def worker() -> list[str]:
    return _lines("railway-worker.sh")


def test_the_worker_collects_static_files(worker):
    assert any(COLLECT.match(line) for line in worker), (
        "railway-worker.sh بلا `python manage.py collectstatic --noinput` — حاويةُ العامل تبدأ بلا staticfiles "
        "فيفشل تصديرُ الجدول PDF (N-042)"
    )


def test_it_runs_before_celery_takes_over(worker):
    """بعد `exec celery` لا يجري شيء: `exec` يستبدل العمليّةَ ولا يعود."""
    collect = _first(worker, COLLECT.pattern)
    celery = _first(worker, r"^exec celery\b")

    assert collect < celery, "collectstatic بعد `exec celery` — لن يُنفَّذ أبداً"


def test_it_runs_under_the_production_settings(worker):
    """التخزينُ المبصومُ (`ManifestStaticFilesStorage`) هو ما يكتب `staticfiles.json` — وهو في إعدادات production."""
    settings = _first(worker, r"^export DJANGO_SETTINGS_MODULE=shschool\.settings\.production$")
    collect = _first(worker, COLLECT.pattern)

    assert settings < collect


def test_it_uses_the_same_command_as_the_web_start_script(worker):
    web = [line for line in _lines("railway-release.sh") if COLLECT.match(line)]
    mine = [line for line in worker if COLLECT.match(line)]

    assert web and mine and mine[0] == web[0], (web, mine)


def test_the_worker_script_is_still_fail_closed_before_it_collects(worker):
    """السطرُ الجديدُ لا يُقدَّم على حارس دور القاعدة: فحصُ الدور أوّلاً ثمّ الثابت ثمّ Celery."""
    verify = _first(worker, r"^python manage\.py verify_runtime_db_role$")
    collect = _first(worker, COLLECT.pattern)

    assert verify < collect
