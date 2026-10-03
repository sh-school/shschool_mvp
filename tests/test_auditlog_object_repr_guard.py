"""[W-20261003-019] حارسٌ: لا اسمَ شخصيّاً في `object_repr` سجلّ التدقيق (سقّاطة).

سجلُّ التدقيق ملحقٌ لا يُعدَّل بعد الكتابة، فالاسمُ يبقى بعد محو صاحبه. هذا الحارسُ يمسح
بالشجرة النحويّة كلَّ نداءٍ يمرّ به `object_repr=` (AuditLog.log وAuditLog.objects.create
وlog_export…) ويفشل عند:
- حقلٍ هويّيٍّ في التعبير: full_name وfirst_name وlast_name وdisplay_name وstudent_name
  وparent_name وemail وphone وnational_id؛
- أو `str(<كائن>)` لمتغيّرٍ بشريّ/عامّ: user وstudent وinstance وobj وtarget وactor وteacher
  (CustomUser.__str__ يُرجع الاسمَ الكامل).

والبديلُ الإلزاميّ: `core.audit_repr.masked_repr(كائن)`.

وهو سقّاطة: ما بقي من مواضعَ قديمةٍ مسجَّلٌ في BASELINE بعددٍ لكلّ ملفّ لا يزيد؛ وكلُّ إصلاحٍ
يُنزل العدّادَ (والنقصُ غيرُ المسجَّل يُسقط الاختبارَ حتى لا يُنفَق ثانيةً).
"""

import ast
import pathlib
import re
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIPPED = {"tests", "migrations", "scripts", "node_modules", "worktrees", "staticfiles"}
IDENTITY = re.compile(
    r"(full_name|first_name|last_name|display_name|student_name|parent_name|"
    r"\bemail\b|\bphone\b|national_id)"
)
HUMAN_STR = re.compile(
    r"\bstr\(\s*(request\.user|user|student|instance|obj|target|actor|teacher)\s*\)"
    # f"{student}" منفردةً — نمطٌ أضافه حكمُ 0105 على الإيداع 2:
    r"|\{\s*(request\.user|user|student|instance|obj|target|actor|teacher)\s*(![rsa])?\s*\}"
)

#: مواضعُ قديمةٌ لم تُصلَح بعد (ملفٌّ ← عددُ نداءاتٍ مخالفة). لا تُضِف هنا: أصلِح الموضع.
BASELINE: dict[str, int] = {}


def _violations() -> Counter[str]:
    found: Counter[str] = Counter()
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if SKIPPED & set(rel.parts) or any(part.startswith(".") for part in rel.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "object_repr":
                    continue
                text = ast.get_source_segment(source, keyword.value) or ""
                text = text.replace("mask_national_id(", "masked_id(")  # رقمٌ مقنَّعٌ عمداً
                if "masked_repr(" in text and not (IDENTITY.search(text) or HUMAN_STR.search(text)):
                    continue
                if IDENTITY.search(text) or HUMAN_STR.search(text):
                    found[rel.as_posix()] += 1
    return found


def test_no_new_personal_name_in_object_repr():
    current = _violations()
    worse = {f: n for f, n in current.items() if n > BASELINE.get(f, 0)}

    assert not worse, (
        "اسمٌ شخصيّ أو str(كائنٍ بشريّ) في object_repr — استعمل core.audit_repr.masked_repr: "
        f"{worse}"
    )


def test_fixed_sites_are_recorded_so_they_cannot_regress():
    current = _violations()
    stale = {f: (n, current.get(f, 0)) for f, n in BASELINE.items() if current.get(f, 0) < n}

    assert not stale, f"نقصت مخالفاتٌ ولم يُنزَل السقفُ في BASELINE — حدّثه: {stale}"


def test_the_scanner_catches_a_planted_leak(tmp_path):
    """ضبطٌ موجب: حارسٌ لا يلتقط تسريباً مزروعاً لا يحرس شيئاً."""
    planted = 'AuditLog.log(object_repr=f"عرض — {student.full_name}")\n'
    ok = 'AuditLog.log(object_repr=f"عرض — {masked_repr(student)}")\n'

    def hits(code: str) -> int:
        tree = ast.parse(code)
        total = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "object_repr":
                        seg = ast.get_source_segment(code, kw.value) or ""
                        total += bool(IDENTITY.search(seg) or HUMAN_STR.search(seg))
        return total

    bare = 'AuditLog.log(object_repr=f"عرض — {student}")'

    assert (hits(planted), hits(ok), hits(bare)) == (1, 0, 1)
