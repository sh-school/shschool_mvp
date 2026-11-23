"""حارسُ سقفِ sentry-sdk في requirements.txt (W-20261123-009).

الخلل الذي يمنعه: صدر sentry-sdk 3.0.0 فركّبه CI لأنّ القيد كان `>=2.75.0` بلا سقف،
فتكسّرت اختبارات Sentry وزادت أخطاءُ mypy. هذا الاختبار يثبّت أنّ القيد يستبعد الإصدار 3
ويقبل إصدارات 2.x، فلا يعود ترقيةٌ عابرةٌ للمحوريّة إلى CI دون قرارٍ صريح.
"""

from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"


def _sentry_specifier() -> SpecifierSet:
    """يُرجع قيدَ sentry-sdk كما هو مكتوبٌ في requirements.txt."""
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("sentry-sdk"):
            # الاسم قد يحمل أقواساً مثل [django]؛ نأخذ ما بعد الاسم والأقواس.
            spec = line.split("]", 1)[1] if "]" in line else line[len("sentry-sdk") :]
            return SpecifierSet(spec.strip())
    raise AssertionError("sentry-sdk غائبٌ من requirements.txt")


def test_sentry_sdk_excludes_major_3() -> None:
    """الإصدار 3.0.0 (الذي كسر CI) يجب أن يُستبعد صراحةً بالسقف."""
    assert not _sentry_specifier().contains(Version("3.0.0"))


def test_sentry_sdk_keeps_2x_line_allowed() -> None:
    """الحدّ الأدنى 2.75.0 وما بعده ضمن خطّ 2.x يبقى مقبولاً."""
    spec = _sentry_specifier()
    assert spec.contains(Version("2.75.0"))
    assert spec.contains(Version("2.99.0"))
