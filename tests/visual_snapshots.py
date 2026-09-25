"""لقطاتُ الهويّة البصريّة الآليّة (VI-13، V-K25) — المقارنةُ والحتميّةُ بلا متصفّح.

**الغرض.** الحرّاسُ الساكنةُ تقرأ الشيفرةَ لا الشاشةَ، فتفوتها انحدراتٌ لا يراها إلّا مَن يفتح الصفحةَ: ترتيبُ طبقاتٍ يقلب لوناً، وقاعدةٌ
تُغيّر ارتفاعَ بطاقةٍ فتزحف صفحةٌ. اللقطةُ البصريّةُ تُمسك ذلك بمقارنة صورةِ الطلب بصورةِ `main` لكلّ من أهمّ الصفحات، نهاراً وليلاً،
بعرضَي الجوال وسطح المكتب.

**ما في هذا الملفّ** مقارنةُ الصور بـPillow وتعريفُ مصفوفة اللقطات وتهيئةُ الصفحة لتكون حتميّةً؛ أمّا التقاطُها فيقع في
`tests/e2e/test_visual_snapshots_live.py` (متصفّحٌ حقيقيٌّ، خارجَ المجموعة الرئيسيّة بحسب `test_nightly_isolates_browser_tests`).

**قرارات التصميم (2026-09-25، بتفويض المالك «افعل الأفضل»):**

- **لا صورَ في git** (المستودعُ عامٌّ وتاريخُه فيه حشوٌ)؛ الأساسُ artifact من تشغيلٍ على `main` يُنزَّل ويُقارَن به.
- **مرحلةٌ استشاريّة أوّلاً:** وظيفةٌ منفصلةٌ ليست في `gate-summary`، تقيس **الحتميّة** (كلُّ لقطةٍ تُلتقط مرّتين في التشغيل نفسِه ويجب أن تتطابق)
  والفرقَ عن `main`، فنضبط العتباتِ من أرقامٍ لا من تخمين ثمّ نرفعها إلى بوّابةٍ. (الحارسُ الذي لم يُقَس ثباتُه يحجب الدمجَ بلا سبب.)
- **الاعتماد:** وسمُ «تغيير-بصريّ» على الطلب (سابقةُ «نشر-عاجل»): معه لا يفشل الفرقُ بل يُنشر ملخّصٌ وصورُ الفرق؛ وبدونه يفشل فوق العتبة.
- **بياناتٌ وهميّةٌ فقط** (fixtures الاختبار): المستودعُ عامٌّ وPDPPL.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

from PIL import Image, ImageChops

from tests.mobile_audit import PROFILES

#: الصفحاتُ الخمس — نمطُ تخطيطٍ لكلٍّ منها (D-16): لوحة، سجلّ، ورقة، نموذج، صندوقٌ بلا تمرير. (الدور، اسمُ المسار كما في JOURNEYS).
SHOTS: tuple[tuple[str, str], ...] = (
    ("leadership", "dashboard"),
    ("leadership", "student_affairs:student_list"),
    ("teacher", "teacher_schedule"),
    ("nurse", "clinic:record_visit"),
    ("leadership", "notification_inbox"),
)
THEMES = ("light", "dark")
#: المِلفّان: جوالٌ 375 وسطحُ مكتبٍ 1440 (من سقّاطة الجوال نفسِها لا تعريفٌ ثانٍ).
PROFILE_NAMES = tuple(PROFILES)

#: أقصى فرقٍ في قناةٍ لونيّةٍ (0–255) يُعدّ «الصورةَ نفسَها» — مضادُّ التسنّن وتقريبُ الألوان. يُضبط من قياس CI.
PIXEL_TOLERANCE = 12
#: نسبةُ البكسلات المتغيّرة التي تُعدّ لقطتَين متطابقتَين — الحتميّة (تُلتقط اللقطةُ مرّتين في التشغيل نفسِه). تُضبط من قياس CI.
DETERMINISM_MAX = 0.0005
#: نسبةُ البكسلات المتغيّرة عن `main` التي تُعدّ تغييراً بصريّاً يحتاج اعتماداً. تُضبط من قياس CI.
CHANGE_MAX = 0.001
#: أطولُ لقطةٍ (بكسل CSS) — صفحةٌ طويلةٌ تُقصّ لئلّا يكبر الـartifact.
MAX_HEIGHT = 3200

#: عناصرُ متقلّبةٌ (وقتٌ، عدّاد) يضع عليها القالبُ السمةَ `data-visual-mask` فتُغطّى في اللقطة.
MASK_SELECTOR = "[data-visual-mask]"

#: تُحقن بعد التحميل: لا حركةَ ولا انتقالَ ولا مؤشّرَ نصّ ولا تمريرَ ناعماً — فلا تُلتقط الصفحةُ في منتصف حركة (`page-in` بـ500ms).
FREEZE_CSS = (
    "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important;"
    "scroll-behavior:auto!important}"
)

#: تُحقن قبل تحميل أيّ صفحة: الوضعُ المطلوب، وشريطُ التثبيت مُغلَق (لا يظهر فيُغيّر الارتفاع).
INIT_SCRIPT = "localStorage.setItem('theme','{theme}');localStorage.setItem('pwaDismissed','1');"


def shot_key(role: str, page: str, theme: str, profile: str) -> str:
    """مفتاحُ اللقطة — يُستعمل اسمَ ملفّ (`mobile/dark/leadership--student_affairs_student_list.png`)."""
    return f"{profile}/{theme}/{role}--{page.replace(':', '_')}.png"


def matrix() -> list[tuple[str, str, str, str]]:
    """(الدور، الصفحة، الوضع، المِلفّ) لكلّ لقطةٍ في المصفوفة."""
    return [
        (role, page, theme, profile)
        for profile in PROFILE_NAMES
        for theme in THEMES
        for role, page in SHOTS
    ]


@dataclasses.dataclass(frozen=True)
class Diff:
    ratio: float  # نسبةُ البكسلات المتغيّرة (0–1)؛ 1.0 إن اختلف المقاس
    changed: int
    total: int
    size_mismatch: bool
    bbox: tuple[int, int, int, int] | None  # أصغرُ مستطيلٍ يحوي التغيّر


def _changed_mask(a: Image.Image, b: Image.Image, tolerance: int) -> Image.Image:
    """قناعٌ أحاديُّ القناة: 255 حيث تجاوز فرقُ أيّ قناةٍ لونيّةٍ `tolerance`."""
    difference = ImageChops.difference(a, b)
    red, green, blue = difference.split()
    strongest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    return strongest.point(lambda value: 255 if value > tolerance else 0)


def compare(a: pathlib.Path, b: pathlib.Path, tolerance: int = PIXEL_TOLERANCE) -> Diff:
    """مقارنةُ صورتَين. مقاسٌ مختلفٌ = تغيّرٌ كاملٌ (زحفُ ارتفاعٍ هو التغيّرُ نفسُه)."""
    with Image.open(a) as first, Image.open(b) as second:
        image_a, image_b = first.convert("RGB"), second.convert("RGB")
    total = image_a.width * image_a.height
    if image_a.size != image_b.size:
        return Diff(1.0, total, total, True, None)
    mask = _changed_mask(image_a, image_b, tolerance)
    changed = mask.histogram()[255]
    return Diff(changed / total if total else 0.0, changed, total, False, mask.getbbox())


def save_diff(
    a: pathlib.Path, b: pathlib.Path, out: pathlib.Path, tolerance: int = PIXEL_TOLERANCE
) -> None:
    """يحفظ الصورةَ الثانية وقد لُوّن ما تغيّر عن الأولى بالأحمر — للمراجِع لا للحكم."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(a) as first, Image.open(b) as second:
        image_a, image_b = first.convert("RGB"), second.convert("RGB")
    if image_a.size != image_b.size:
        canvas = Image.new(
            "RGB",
            (max(image_a.width, image_b.width), max(image_a.height, image_b.height)),
            (255, 0, 0),
        )
        canvas.paste(image_b, (0, 0))
        canvas.save(out)
        return
    mask = _changed_mask(image_a, image_b, tolerance)
    overlay = Image.new("RGB", image_b.size, (255, 0, 0))
    Image.composite(overlay, image_b, mask).save(out)


def summary_markdown(rows: list[dict]) -> str:
    """جدولُ ملخّصٍ للتشغيل: لكلّ لقطةٍ نسبةُ الحتميّة والتغيّر عن `main` وحالتُها."""
    lines = [
        "| اللقطة | حتميّةٌ (فرقُ تشغيلَين) | التغيّرُ عن main | الحالة |",
        "|---|---|---|---|",
    ]
    for row in rows:
        change = "—" if row.get("change") is None else f"{row['change'] * 100:.3f}%"
        lines.append(
            f"| `{row['key']}` | {row['determinism'] * 100:.3f}% | {change} | {row['status']} |"
        )
    return "\n".join(lines) + "\n"


def write_summary(out: pathlib.Path, rows: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out / "summary.md").write_text(summary_markdown(rows), encoding="utf-8")
