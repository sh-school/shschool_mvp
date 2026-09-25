"""جدولُ أسماء المعلّمين (REP-07b): يُقرأ من ملفٍّ خارج المستودع، ولا أسماءَ كاملةَ لموظّفين في الشيفرة.

كانت أداةُ استيراد الجدول تحمل في المصدر جدولاً بأسماءٍ كاملةٍ لموظّفين — بيانٌ شخصيٌّ (PDPPL) في مستودعٍ
عامّ، لم يمسكه حارسُ الأرقام لأنّها أسماءٌ لا أرقام. فصارت الأداةُ تقرؤه من ملفّ JSON خارج المستودع، وهذا الحارسُ
يمنع عودةَ أيّ جدولِ أسماءٍ عربيّةٍ كاملةٍ إلى الشيفرة.
"""

import re
from pathlib import Path

import pytest

from operations.management.commands.import_timetable_pdf import (
    TEACHER_MAP_ENV,
    load_teacher_map,
)

ROOT = Path(__file__).resolve().parents[1]

#: إدخالُ قاموسٍ عربيٌّ كاملٌ: مفتاحٌ من كلمتين فأكثر ← قيمةٌ من ثلاث كلماتٍ فأكثر، كلاهما حروفٌ عربيّةٌ وفراغات.
NAME_ENTRY = re.compile(r'^\s*"[ء-ي]+(?: [ء-ي]+)+"\s*:\s*"[ء-ي]+(?: [ء-ي]+){2,}"\s*,\s*$')
#: جداولُ المسمّيات الوظيفيّة والموادّ («منسق التربيه البدنيه» ← «منسق التربية البدنية») تشبه جدولَ الأسماء شكلاً
#: وليست بياناً شخصيّاً — فيُستثنى كلُّ سطرٍ فيه كلمةُ مسمًّى أو مادّة.
TITLE_OR_SUBJECT = re.compile(
    "منسق|معلم|مدير|نائب|رئيس|مشرف|اخصائي|أخصائي|قسم|اللغ|التربي|الدراسات|الفنون|العلوم|الرياضيات|الحاسب|الحاسوب"
    "|تكنولوجيا|المعلومات|الاسلامي|الإسلامي|البدني|الاجتماعي"
)
ENTRIES_THAT_MAKE_A_MAP = 5


def name_entries(text: str) -> int:
    """عددُ أسطر «اسمٌ مختصر ← اسمٌ كامل» في النصّ، دون جداول المسمّيات والموادّ."""
    return sum(
        1
        for line in text.splitlines()
        if NAME_ENTRY.match(line) and not TITLE_OR_SUBJECT.search(line)
    )


def test_the_map_is_read_from_the_file_named_by_the_environment(tmp_path, monkeypatch):
    file = tmp_path / "names.json"
    file.write_text('{"س ص": "س ص ع ل"}', encoding="utf-8")
    monkeypatch.setenv(TEACHER_MAP_ENV, str(file))

    assert load_teacher_map() == {"س ص": "س ص ع ل"}


def test_a_missing_file_is_an_empty_map_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setenv(TEACHER_MAP_ENV, str(tmp_path / "absent.json"))

    assert load_teacher_map() == {}


@pytest.mark.parametrize("content", ["{ليس json", "[1, 2]", '"نصّ"'])
def test_a_corrupt_or_wrongly_shaped_file_is_an_empty_map(tmp_path, monkeypatch, content):
    file = tmp_path / "names.json"
    file.write_text(content, encoding="utf-8")
    monkeypatch.setenv(TEACHER_MAP_ENV, str(file))

    assert load_teacher_map() == {}


def test_the_default_location_is_ignored_by_git():
    """الجدولُ الافتراضيّ في `data/` — وهو مُتجاهَلٌ في `.gitignore` فلا يُودَع بغلطة."""
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "data/" in [line.strip() for line in ignore]


def test_no_full_arabic_names_map_lives_in_the_source():
    """لا جدولَ أسماءٍ عربيّةٍ كاملةٍ (خمسةُ إدخالاتٍ فأكثر في ملفٍّ) في شيفرة المنصّة."""
    offenders = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if (
            rel.startswith(("tests/", ".venv/", "venv/", "node_modules/", ".claude/"))
            or "/tests/" in rel
        ):
            continue
        entries = name_entries(path.read_text(encoding="utf-8", errors="replace"))
        if entries >= ENTRIES_THAT_MAKE_A_MAP:
            offenders.append(f"{rel} ({entries} إدخالاً)")

    assert offenders == [], (
        "جدولُ أسماءٍ كاملةٍ في الشيفرة — انقله إلى ملفّ بياناتٍ خارج المستودع:\n" + "\n".join(offenders)
    )


def test_the_guard_flags_a_names_map_and_spares_a_job_title_map():
    """الحارسُ نفسُه: جدولُ أسماءٍ اصطناعيٌّ يُعَدّ، وجدولُ مسمّياتٍ وظيفيّةٍ لا يُعَدّ."""
    names = "\n".join(f'    "اسم{i} لقب{i}": "اسم{i} أب{i} جد{i} لقب{i}",' for i in "أبجدهوز")
    titles = "\n".join(f'    "منسق مادة{i}": "منسق المادة {i} في القسم",' for i in "أبجدهوز")

    assert name_entries(names) >= ENTRIES_THAT_MAKE_A_MAP
    assert name_entries(titles) == 0
