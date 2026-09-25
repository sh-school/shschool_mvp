"""حارسُ البيانات الشخصيّة (REP-07): منطقُه، ونطاقُه، وأنّ المستودعَ يمرّ به.

المستودعُ عامّ. وكان حارسُ البوّابة `grep` مستثنياً `tests/` كلَّها، فبقي فيها رقمٌ حقيقيٌّ لمعلّمٍ ورقمٌ
حقيقيٌّ آخر وثلاثةٌ وعشرون رقماً بهيئة الحقيقيّ، ويحكم على السطر لا على الرمز، ويطبع الأرقامَ كاملةً في سجلٍّ
عامّ. هذه الاختباراتُ تثبّت ما أُصلح — والأرقامُ المخالِفةُ هنا تُبنى بالتركيب فلا يحوي هذا الملفُّ رقماً
بهيئة الحقيقيّ (وإلّا أسقطه الحارسُ نفسُه).
"""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "quality-gate.yml"


def _guard():
    spec = importlib.util.spec_from_file_location(
        "check_personal_data", ROOT / "scripts" / "check_personal_data.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _guard()

# أرقامٌ بهيئة الحقيقيّ تُبنى بالتركيب: لا تظهر في المصدر رقماً كاملاً
LOOKS_REAL_ID = "2871" + "1223344"
LOOKS_REAL_PHONE = "+974" + "50123456"


def _violations(path, text):
    return guard.scan_text(path, text)


def test_a_real_looking_national_number_is_flagged():
    assert [v.token for v in _violations("core/x.py", f'NID = "{LOOKS_REAL_ID}"')] == [
        LOOKS_REAL_ID
    ]


def test_a_real_looking_phone_is_flagged():
    assert [v.token for v in _violations("core/x.py", f"tel: {LOOKS_REAL_PHONE}")] == [
        LOOKS_REAL_PHONE
    ]


def test_millennial_numbers_starting_with_three_are_covered():
    """البادئةُ `[23]` لا `2` وحدَها — ثغرةٌ سُدّت 2026-09-11."""
    token = "31" + "412345601"

    assert len(token) == 11
    assert [v.token for v in _violations("core/x.py", token)] == [token]


@pytest.mark.parametrize(
    "token",
    [
        "29000000031",  # أصفارٌ في الوسط — الصيغةُ الموصى بها للاختبارات
        "29000000005",  # من نطاق العيّنات المعروفة
        "29012345678",  # من القائمة المسمّاة
        "22222222222",  # ستُّ خاناتٍ متماثلة
        "+97455000005",  # من نطاق الجوّالات المعروف
        "+97450000022",  # خمسةُ أصفارٍ متتالية
        "+97455555555",  # ستُّ خاناتٍ متماثلة
    ],
)
def test_synthetic_numbers_pass(token):
    assert _violations("tests/test_x.py", f"x = '{token}'") == []


def test_the_verdict_is_per_token_not_per_line():
    """كان `grep -v` يُسقط السطرَ كلَّه إن حوى رمزاً مسموحاً، فيمرّ معه رمزٌ حقيقيٌّ في السطر نفسه."""
    line = f'pair = ("29000000031", "{LOOKS_REAL_ID}")'

    assert [v.token for v in _violations("core/x.py", line)] == [LOOKS_REAL_ID]


def test_the_tests_directory_is_scanned():
    """كانت `tests/` مستثناةً — فبقي فيها الرقمُ الحقيقيّ."""
    assert _violations("tests/test_something.py", LOOKS_REAL_ID)
    assert _violations("app/tests.py", LOOKS_REAL_ID)
    assert not guard.is_excluded("tests/test_something.py")
    assert not guard.is_excluded("app/tests.py")


@pytest.mark.parametrize(
    "path",
    ["docs/plan.md", "README.md", "static/js/x.js", "app/migrations/0001_a.py", "poetry.lock"],
)
def test_documents_and_generated_files_stay_out_of_scope(path):
    assert guard.is_excluded(path)


def test_the_output_never_prints_a_full_number():
    """سجلُّ Actions عامّ: الكشفُ نفسُه لا يكون تسريباً."""
    violation = _violations("core/x.py", LOOKS_REAL_ID)[0]

    assert LOOKS_REAL_ID not in str(violation)
    assert LOOKS_REAL_ID[3:9] not in str(violation)
    phone = _violations("core/x.py", LOOKS_REAL_PHONE)[0]
    assert LOOKS_REAL_PHONE not in str(phone)
    assert LOOKS_REAL_PHONE[6:10] not in str(phone)


def test_the_gate_step_runs_the_script_and_does_not_exclude_tests():
    """الوظيفةُ في CI تشغّل هذا الحارسَ نفسَه، ولا يعود استثناءُ `tests/` إلى الأمر."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "scripts/check_personal_data.py" in workflow
    assert ":!tests/*" not in workflow
    assert ":!*/tests/*" not in workflow


def _in_a_git_checkout():
    if shutil.which("git") is None:
        return False
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT, capture_output=True
    )
    return probe.returncode == 0


@pytest.mark.skipif(not _in_a_git_checkout(), reason="يحتاج نسخةَ git (في CI متوفّرة)")
def test_the_tracked_files_hold_no_unlisted_personal_number():
    """المستودعُ كلُّه (بما فيه tests/) خالٍ من رقمٍ بهيئة الحقيقيّ خارج السماح. RK5 = 0."""
    found = guard.scan_repo(ROOT)

    assert found == [], "أرقامٌ شخصيّةٌ بهيئة الحقيقيّة:\n" + "\n".join(str(v) for v in found[:20])
