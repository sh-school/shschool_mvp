"""W-20261013-010: حارسٌ يمنع عودة نظام حسم درجات السلوك (لا أصلَ له في لوائح الوزارة).

قرارُ المالك 2026-10-13: لا نقاطَ ولا حسمَ ولا «مؤشّرَ سلوك» مشتقّاً منها. تبقى أعمدةُ
`points` و`points_deducted` و`points_restored` وجدولُ `BehaviorPointRecovery` في النماذج
والهجرات وحدَها حتى المرحلة 2 (حذفُها بقول المالك)؛ وما عداها ممنوعٌ في الشيفرة والقوالب.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_TOP = {
    ".venv",
    "venv",
    "node_modules",
    "tests",
    "docs",
    "AAdocs",
    "static",
    "staticfiles",
    ".git",
    ".claude",
    "scripts",
    "locale",
}
ALLOWED = {
    "behavior/models.py",  # الأعمدة الخاملة حتى المرحلة 2
    "core/models/__init__.py",
    "core/tenancy.py",
    "behavior/admin.py",  # عرضٌ للقراءة وحدَها للأعمدة الخاملة حتى المرحلة 2
}
FORBIDDEN = re.compile(
    r"POINTS_BY_LEVEL|points_deducted|points_restored|BehaviorPointRecovery|net_score"
    r"|_SEVERITY_PER_LEVEL|get_student_score_pdf"
    r"|حسم من درجات السلوك|يُحسم من درجة|نقاط مخصومة|combined_score"
)


#: عباراتُ نظام النقاط الملغى المرئيّةُ للمستخدم (W-20261019-015). نطاقُها مجلداتُ السلوك والأولياء
#: والإشعارات وحدَها: «من 100» مشروعةٌ في قوالب الدرجات الدراسية فلا تُفحص خارجها.
BEHAVIOR_TEXT_SCOPE = ("behavior", "parents", "notifications")
FORBIDDEN_BEHAVIOR_TEXT = re.compile(r"نقاط السلوك|مؤشر السلوك|مؤشّر السلوك|من 100")
#: سطرٌ يشرح الإلغاءَ نفسَه يُستثنى بوسم «ملغى» في السطر.
CANCELLED_MARK = "ملغى"


def _behavior_text_hits(files_text):
    """يقبل (مسارٌ نسبيّ، نصّ) ويعيد المخالفات؛ مفصولةٌ ليُختبر الحارسُ على نصٍّ مزروع."""
    hits = []
    for rel, text in files_text:
        if rel.split("/")[0] not in BEHAVIOR_TEXT_SCOPE:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if FORBIDDEN_BEHAVIOR_TEXT.search(line) and CANCELLED_MARK not in line:
                hits.append(f"{rel}:{n}: {line.strip()[:90]}")
    return hits


def _files():
    # كلُّ التطبيقات والقوالب لا مجلداتٌ مسمّاة (W-20261013-010): تطبيقٌ جديدٌ لا يفلت.
    for p in ROOT.rglob("*"):
        rel_parts = p.relative_to(ROOT).parts
        if rel_parts[0] in SKIP_TOP or "migrations" in rel_parts or "__pycache__" in rel_parts:
            continue
        if p.is_file() and p.suffix in {".py", ".html", ".txt", ".js"}:
            yield p


def test_no_points_deduction_in_code_or_templates():
    hits = []
    for p in _files():
        rel = p.relative_to(ROOT).as_posix()
        if rel in ALLOWED:
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if FORBIDDEN.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:90]}")
    assert not hits, "عاد حسمُ الدرجات (W-20261013-010):\n" + "\n".join(hits)


def test_no_behavior_points_wording_in_behavior_parents_notifications():
    files_text = (
        (p.relative_to(ROOT).as_posix(), p.read_text(encoding="utf-8", errors="ignore"))
        for p in _files()
    )
    hits = _behavior_text_hits(files_text)
    assert not hits, "عادت صياغةُ نقاط السلوك (W-20261019-015):\n" + "\n".join(hits)


def test_the_wording_guard_fails_on_planted_text_and_spares_cancelled_notes():
    planted = [
        ("behavior/templates_x.html", "<p>نقاط السلوك 90 من 100</p>"),
        ("parents/mail.txt", "مؤشر السلوك: جيد"),
        ("notifications/a.py", 'msg = "رصيدك 80 من 100"'),
    ]
    assert len(_behavior_text_hits(planted)) == 3
    assert not _behavior_text_hits([("behavior/a.py", "# نقاط السلوك ملغى بقرار 2026-10-13")])
    # قوالبُ الدرجات الدراسية خارج النطاق: «من 100» فيها مشروعة.
    assert not _behavior_text_hits([("assessments/g.html", "الدرجة من 100")])
