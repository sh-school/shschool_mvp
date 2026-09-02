"""[SCHEDULE] لقطةٌ لم تُجرَّب ليست لقطة.

زرُّ التوليد يُطفئ كلَّ حصّةٍ نشطةٍ للعام ثمّ يكتب مكانها، لحظةَ الضغط لا عند
الاعتماد. فخطّةُ التراجع ليست «الإخفاءُ ناعمٌ فالاسترجاعُ ممكنٌ نظريّاً» — بل
أمرٌ واحدٌ جُرّب قبل الحاجة إليه.

وهذه الاختباراتُ تُتلف الجدولَ عمداً ثمّ تُعيده، وتقارن البصمةَ قبلَ وبعد:
لا العدد وحدَه، بل (معلّم · يوم · حصّة · شعبة) لكلّ صفّ — فجدولٌ بالعدد نفسه
وترتيبٍ مختلفٍ جدولٌ آخر.
"""

import json
from datetime import time
from pathlib import Path

import pytest
from django.core.management import call_command

from operations.models import ScheduleSlot
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


@pytest.fixture
def teacher(school):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلّمُ الجدول")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def subject(school):
    from operations.models import Subject

    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


@pytest.fixture
def slots(school, teacher, subject):
    group = ClassGroupFactory(school=school, grade="G7", academic_year=YEAR)
    rows = [
        ScheduleSlot(
            school=school,
            teacher=teacher,
            class_group=group,
            subject=subject,
            day_of_week=day,
            period_number=period,
            start_time=time(7, 10),
            end_time=time(7, 55),
            academic_year=YEAR,
            is_active=True,
            notes=f"أصلٌ {day}/{period}",
        )
        for day, period in ((0, 1), (1, 2), (2, 3), (3, 4), (4, 5))
    ]
    return ScheduleSlot.objects.bulk_create(rows)


def fingerprint(school):
    """(معلّم · يوم · حصّة · شعبة) لكلّ صفٍّ نشط — لا العددُ وحدَه."""
    return sorted(
        (str(r.teacher_id), r.day_of_week, r.period_number, str(r.class_group_id), r.notes)
        for r in ScheduleSlot.objects.filter(school=school, academic_year=YEAR, is_active=True)
    )


def snapshot_path(tmp_path, school, monkeypatch):
    """تُكتب اللقطةُ في مجلّدٍ مؤقّتٍ كي لا تلمس الاختباراتُ `backups/`."""
    import operations.management.commands.schedule_snapshot as cmd

    monkeypatch.setattr(cmd, "BACKUP_DIR", Path(tmp_path) / "schedule")
    return Path(tmp_path) / "schedule"


def only_file(directory):
    files = list(directory.glob("*.json"))
    assert len(files) == 1, f"لقطةٌ واحدةٌ متوقّعة، وُجد {len(files)}"
    return files[0]


# ── الالتقاط ─────────────────────────────────────────────────────────


def test_a_snapshot_records_every_active_slot(school, slots, tmp_path, monkeypatch):
    directory = snapshot_path(tmp_path, school, monkeypatch)

    call_command("schedule_snapshot", school=school.code, year=YEAR)

    data = json.loads(only_file(directory).read_text(encoding="utf-8"))
    assert data["school_code"] == school.code and data["academic_year"] == YEAR
    assert len(data["slots"]) == 5


def test_a_snapshot_ignores_what_is_already_switched_off(school, slots, tmp_path, monkeypatch):
    """المطفأُ تاريخٌ لا جدول — ولا يُستعاد مع الحاضر."""
    directory = snapshot_path(tmp_path, school, monkeypatch)
    ScheduleSlot.objects.filter(pk=slots[0].pk).update(is_active=False)

    call_command("schedule_snapshot", school=school.code, year=YEAR)

    data = json.loads(only_file(directory).read_text(encoding="utf-8"))
    assert len(data["slots"]) == 4


def test_an_empty_year_produces_no_snapshot(school, tmp_path, monkeypatch):
    directory = snapshot_path(tmp_path, school, monkeypatch)

    call_command("schedule_snapshot", school=school.code, year=YEAR)

    assert not directory.exists() or not list(directory.glob("*.json"))


# ── الاسترجاع ────────────────────────────────────────────────────────


def test_the_schedule_comes_back_exactly_as_it_was(school, slots, tmp_path, monkeypatch):
    """الإتلافُ ثمّ الرجوع — والبصمةُ هي الحَكَم، لا العدد."""
    directory = snapshot_path(tmp_path, school, monkeypatch)
    before = fingerprint(school)
    call_command("schedule_snapshot", school=school.code, year=YEAR)
    path = only_file(directory)

    # ما يفعله زرُّ التوليد بالضبط: إطفاءُ كلّ ما هو نشط.
    ScheduleSlot.objects.filter(school=school, academic_year=YEAR, is_active=True).update(
        is_active=False
    )
    assert fingerprint(school) == []

    call_command("schedule_snapshot", restore=str(path), yes=True)

    assert fingerprint(school) == before


def test_restoring_switches_off_whatever_replaced_it(
    school, slots, teacher, subject, tmp_path, monkeypatch
):
    """الرجوعُ لا يجمع الجدولين — يُطفئ الحاضرَ ويُعيد الماضي."""
    directory = snapshot_path(tmp_path, school, monkeypatch)
    before = fingerprint(school)
    call_command("schedule_snapshot", school=school.code, year=YEAR)
    path = only_file(directory)

    ScheduleSlot.objects.filter(school=school, academic_year=YEAR, is_active=True).update(
        is_active=False
    )
    group = ClassGroupFactory(school=school, grade="G8", academic_year=YEAR)
    ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=group,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=time(7, 10),
        end_time=time(7, 55),
        academic_year=YEAR,
        is_active=True,
        notes="جدولٌ مولَّد",
    )

    call_command("schedule_snapshot", restore=str(path), yes=True)

    assert fingerprint(school) == before, "لم يبقَ من المولَّد شيءٌ نشط"
    assert (
        ScheduleSlot.objects.filter(school=school, notes="جدولٌ مولَّد", is_active=True).count() == 0
    )


def test_restoring_twice_does_not_duplicate_the_week(school, slots, tmp_path, monkeypatch):
    """رجوعٌ مرّتين لا يُنتج أسبوعين — الحاضرُ يُطفأ في كلّ مرّة."""
    directory = snapshot_path(tmp_path, school, monkeypatch)
    before = fingerprint(school)
    call_command("schedule_snapshot", school=school.code, year=YEAR)
    path = only_file(directory)

    call_command("schedule_snapshot", restore=str(path), yes=True)
    call_command("schedule_snapshot", restore=str(path), yes=True)

    assert fingerprint(school) == before


def test_a_missing_file_is_refused_clearly(tmp_path):
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("schedule_snapshot", restore=str(tmp_path / "لا-وجود-له.json"), yes=True)
