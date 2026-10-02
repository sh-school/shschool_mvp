"""لا قارئَ للإدخال المبدئيّ خارجَ المسارات المراجَعة — كلُّ قارئٍ للرصد يقرأ المعتمَدَ وحدَه (W-20261002-020، مراجعةُ 0102).

التصميمُ: `StudentAttendance` هو الرصدُ **المعتمَد** وحدَه (لا يُكتب إلّا عند الاعتماد أو للتربية الخاصّة)، و`AttendanceEntry` سجلٌّ
مبدئيٌّ لا يُحتسب حضوراً ولا غياباً. فكلُّ قارئٍ للحضور — عتباتُ الغياب، إخطاراتُ وليّ الأمر، التقاريرُ والتصديرُ (PDF/Excel)،
الإحصاءاتُ — يقرأ `StudentAttendance` فيرى المعتمَدَ بالبناء، بلا فلترٍ ينساه أحد. والخطرُ الوحيدُ أن يقرأ أحدٌ **السجلَّ المبدئيَّ**
فيحسبه رصداً: فهذا الحارسُ يمنع أيَّ وحدةٍ في المنصّة من ذكر `AttendanceEntry` أو `AttendanceDecision` أو علاقتَيهما العكسيّتَين
خارجَ القائمة المراجَعة أدناه، وسببُ كلٍّ منها مكتوب. وقارئٌ جديدٌ يلزمه قرارٌ يُسأل عنه في المراجعة لا مرورٌ صامت.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: ما يدلّ على قراءة السجلّ المبدئيّ: صنفا النموذج وعلاقتاهما العكسيّتان على `Session`/`CustomUser`.
#: والعلاقةُ العكسيّةُ تُلتقط بنقطةٍ قبلها أو بـ`__` بعدها، لا باسم الوحدة (`from .attendance_entries import …`).
TOKENS = re.compile(
    r"\bAttendanceEntry\b|\bAttendanceDecision\b"
    r"|(?<!operations)(?<!from )\.attendance_entries\b(?! import)|\battendance_entries__"
    r"|\.attendance_decisions\b|\battendance_decisions_made\b"
)

#: الوحداتُ المراجَعةُ: لا واحدةَ منها تعدّ المبدئيَّ حضوراً أو غياباً.
ALLOWED_READERS = {
    "operations/models/attendance_ledger.py": "تعريفُ النموذجَين",
    "operations/models/__init__.py": "تصديرُ النموذجَين",
    "operations/models/attendance.py": "تعليقاتُ المصدر",
    "operations/migrations/0062_attendance_ledger.py": "الهجرةُ",
    "operations/migrations/0063_attendance_ledger_guards.py": "هجرةُ الحماية (RLS والمُشغِّل)",
    "operations/attendance_entries.py": "الإدخالُ والقرارُ والتقريرُ والمحو — صاحبُ السجلّ",
    "operations/attendance_policy.py": "أهليّةُ التصحيح (`_has_entry_in_session`) — قراءةُ وجودٍ لا حالة",
    "operations/attendance_selectors.py": "شاشاتُ المعلّم والحامل — يعرض المبدئيَّ وسماً «بانتظار الاعتماد» لا حالةً",
    "operations/services/attendance_teacher.py": "حدُّ الواجهات إلى ما سبق",
    "operations/admin.py": "عرضُ قراءةٍ فقط (`ReadOnlyAdminMixin`)",
    "operations/day_attendance.py": "دوكسترنغٌ يصف القرار",
    "governance/erasure_service.py": "محوُ الطالب (PDPPL م.18) يمحو السجلَّ ويحصي ما محا",
}

#: مواضعُ في خدمات الجداول تذكر العلاقةَ العكسيّةَ لغرضٍ غيرِ الاحتساب — كلُّ سطرٍ باسمه وسببه.
ALLOWED_LINES = {
    (
        "operations/services/schedule_sessions.py",
        "attendance_entries__isnull=True",
    ): "حصّةٌ فيها إدخالُ معلّمٍ ليست «غيرَ ملموسة» فلا تُحذف عند إعادة التوليد (M4) — شرطُ وجودٍ لا قراءةُ حالة",
}

SKIP_DIRS = {
    "tests",
    "node_modules",
    ".venv",
    "venv",
    "static",
    "staticfiles",
    "templates",
    "AAdocs",
    "docs",
    ".claude",
    ".git",
}


def _python_files():
    for path in ROOT.rglob("*.py"):
        parts = path.relative_to(ROOT).parts
        if parts[0] in SKIP_DIRS or any(part.startswith(".") for part in parts):
            continue
        yield path


def _hits():
    for path in _python_files():
        rel = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if TOKENS.search(line):
                yield rel, number, line.strip()


def test_no_module_reads_the_pending_ledger_outside_the_reviewed_list():
    stray = []
    for rel, number, line in _hits():
        if rel in ALLOWED_READERS:
            continue
        if any(rel == file and snippet in line for (file, snippet) in ALLOWED_LINES):
            continue
        stray.append(f"{rel}:{number}  {line}")
    assert not stray, (
        "وحدةٌ تقرأ الإدخالَ المبدئيَّ (`AttendanceEntry`/`AttendanceDecision`) خارجَ القائمة المراجَعة — الرصدُ المعتمَدُ "
        "في `StudentAttendance` وحدَه؛ فإن كان القارئُ تقريراً أو عتبةً أو إخطاراً فاقرأ منه:\n  "
        + "\n  ".join(stray)
    )


def test_every_reviewed_entry_still_exists():
    """مدخلٌ زال صاحبُه يُحذف — وإلّا صار بابَ مرورٍ لقارئٍ جديدٍ بالاسم نفسِه."""
    seen = {rel for rel, _number, _line in _hits()}
    stale_files = sorted(rel for rel in ALLOWED_READERS if not (ROOT / rel).exists())
    stale_lines = sorted(
        f"{file}: {snippet}"
        for (file, snippet) in ALLOWED_LINES
        if file not in seen or snippet not in (ROOT / file).read_text(encoding="utf-8")
    )
    assert not stale_files and not stale_lines, (stale_files, stale_lines)


def test_the_detector_sees_what_it_claims_to_see(tmp_path):
    assert TOKENS.search("AttendanceEntry.objects.filter(x=1)")
    assert TOKENS.search("session.attendance_entries.count()")
    assert TOKENS.search("Session.objects.filter(attendance_entries__isnull=True)")
    assert TOKENS.search("user.attendance_decisions_made.all()")
    assert TOKENS.search("school.attendance_decisions.count()")
    assert not TOKENS.search("from .attendance_entries import submit_entry")
    assert not TOKENS.search("from operations.attendance_entries import submit_entry")
    assert not TOKENS.search("StudentAttendance.objects.filter(status='absent')")
    assert not TOKENS.search("attendance_entry_count = 3")
