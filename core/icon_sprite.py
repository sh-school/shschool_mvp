"""مولّدُ ورقة الرموز — ``static/icons/sprite.svg`` من ``core/icons.py`` وحده.

الورقةُ ناتجٌ لا مصدر: تُحرَّر هنا ثمّ ``python manage.py build_icon_sprite``.
والمولّدُ حتميّ — المُدخلُ نفسُه يعطي البايتاتِ نفسَها — فالحارسُ يقارن الملفَّ
بناتجه، ويسقط إن عُدِّل باليد.

وثلاثةُ قرارات في الرسم:

* سُمكُ Hugeicons (1.5) يُنزع من الرسوم ويُترك للصنف ``icon-hg``
  (``--icon-stroke``)، فيُجرَّب 1.5 و1.75 من CSS لا بإعادة التوليد.
* الشارةُ تُقتطع من الكيان بحلقةٍ بلون ``--icon-cutout`` (السطحُ افتراضاً)؛
  وعلى خلفيّةٍ ملوّنة يُعاد تعريفُ المتغيّر في صنف تلك الخلفيّة.
* الألوانُ رموزُ المنصّة (``--status-*-fg``، ``--gold``) لا أرقامٌ سداسيّة،
  فتتبع الوضعَ الداكن وحدها.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from core.icons import BADGES, DETAILED_AT, ICONS, VIOLATION_DEGREES, symbol_id

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE = BASE_DIR / "core" / "icon_sources" / "hugeicons.json"
SPRITE = BASE_DIR / "static" / "icons" / "sprite.svg"

_STROKE_15 = re.compile(r'\s+stroke-width="1\.5"')

# ── شاراتُ الحالة: دائرةٌ نصفُ قطرها 4.7 مركزُها (3.5، 18.5) ─────────────────
_BADGE_TONE = {
    "present": "var(--status-success-fg)",
    "absent": "var(--status-danger-fg)",
    "late": "var(--status-warning-fg)",
    "leave": "var(--status-info-fg)",
    "clinic": "var(--status-info-fg)",
    "swap": "var(--status-info-fg)",
    "alert": "var(--status-warning-fg)",
    "add": "var(--maroon-fg)",
}
#: رسمُ الشارة على مربّع 10×10 — يُزاح إلى الزاوية.
_BADGE_GLYPH = {
    "present": '<path d="M2.6 5.1l1.6 1.6 3.2-3.4"/>',
    "absent": '<path d="M3 3l4 4M7 3l-4 4"/>',
    "late": '<circle cx="5" cy="5" r="2.6"/><path d="M5 3.6V5l.9.7"/>',
    # السهمُ يشير إلى اليسار: الخروجُ في الواجهة العربيّة
    "leave": '<path d="M7.2 5H3M4.4 3.3 2.7 5l1.7 1.7"/>',
    "clinic": '<path d="M5 2.6v4.8M2.6 5h4.8"/>',
    "swap": '<path d="M2.8 4h4.2L5.8 2.8M7.2 6H3l1.2 1.2"/>',
    "alert": '<path d="M5 2.8v2.6"/><circle cx="5" cy="7.1" r=".35"/>',
    "add": '<path d="M5 2.7v4.6M2.7 5h4.6"/>',
}

_SQUIRCLE = (
    "M3 11c0-3.75 0-5.625.955-6.939A5 5 0 0 1 5.06 2.955C6.375 2 8.251 2 12 2s5.625 0 "
    "6.939.955a5 5 0 0 1 1.106 1.106C21 5.375 21 7.251 21 11v2c0 3.75 0 5.625-.955 "
    "6.939a5 5 0 0 1-1.106 1.106C17.625 22 15.749 22 12 22s-5.625 0-6.939-.955a5 5 0 0 "
    "1-1.106-1.106C3 18.625 3 16.749 3 13z"
)
_ARABIC_TEXT = (
    '<text x="12" y="{y}" text-anchor="middle" font-family="Tajawal, sans-serif" '
    'font-weight="700" font-size="{size}" fill="currentColor" stroke="none">{letter}</text>'
)


@lru_cache(maxsize=1)
def library() -> dict:
    data: dict = json.loads(SOURCE.read_text(encoding="utf-8"))
    return data


def _hi(name: str) -> str:
    return _STROKE_15.sub("", library()["icons"][name])


def _badge(kind: str) -> str:
    return (
        '<g transform="translate(-1.5 13.5)">'
        '<circle cx="5" cy="5" r="5.8" fill="var(--icon-cutout, var(--surface))" stroke="none"/>'
        f'<circle cx="5" cy="5" r="4.7" fill="{_BADGE_TONE[kind]}" stroke="none"/>'
        '<g fill="none" stroke="var(--icon-cutout, var(--surface))" stroke-width="1.35" '
        f'stroke-linecap="round" stroke-linejoin="round">{_BADGE_GLYPH[kind]}</g></g>'
    )


def _violation(degree: int | None) -> str:
    """الحدُّ المسنّن في علم قطر: الأسنانُ بعدد الدرجة، ومفرَّغٌ حين لا درجة."""
    teeth = degree or 1
    top, bottom = 4, 20
    step = (bottom - top) / teeth
    points = ["7,4"]
    for i in range(teeth):
        points.append(f"10.5,{top + step * (i + 0.5):g}")
        points.append(f"7,{top + step * (i + 1):g}")
    fill = 'fill="currentColor" stroke="none"' if degree else 'fill="none" stroke="currentColor"'
    return (
        '<path d="M7 4h11a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H7" fill="none" stroke="currentColor" '
        'stroke-linejoin="round"/>'
        f'<polygon points="4,4 {" ".join(points)} 4,20" {fill} stroke-linejoin="round"/>'
    )


def _local(name: str) -> str:
    if name == "violation-degree":
        return _violation(None)
    if name == "gradebook-ar":
        return (
            f'<path d="{_SQUIRCLE}" fill="none" stroke="currentColor"/>'
            + _ARABIC_TEXT.format(y="13.4", size="9.5", letter="أ")
            + '<path d="M8 17h8" fill="none" stroke="currentColor" stroke-linecap="round"/>'
        )
    if name == "dad-letter":
        return f'<path d="{_SQUIRCLE}" fill="none" stroke="currentColor"/>' + _ARABIC_TEXT.format(
            y="15.6", size="11", letter="ض"
        )
    if name == "period-live":
        # الإطارُ الثابت — رقمُ الحصّة وقوسُ مرورها يرسمهما المتصفّحُ فوقه
        return (
            '<circle cx="12" cy="12" r="9.6" fill="none" stroke="currentColor" opacity=".35"/>'
            '<path d="M12 2.4A9.6 9.6 0 0 0 2.4 12" fill="none" stroke="currentColor" stroke-linecap="round"/>'
            '<path d="M12 7.5V12l-3 2" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    if name == "wing":
        # في القوائم نجمةٌ وحدها — المبنى داخلها لا يُقرأ في 20 بكسل
        return (
            '<g fill="none" stroke="currentColor" stroke-linejoin="round">'
            '<rect x="5" y="5" width="14" height="14" rx="1.5"/>'
            '<rect x="5" y="5" width="14" height="14" rx="1.5" transform="rotate(45 12 12)"/></g>'
            '<circle cx="12" cy="12" r="1.6" fill="var(--gold)" stroke="none"/>'
        )
    if name == "wing-lg":
        return (
            '<g fill="none" stroke="var(--gold)" stroke-width="1" stroke-linejoin="round">'
            '<rect x="4.5" y="4.5" width="15" height="15" rx="1.5"/>'
            '<rect x="4.5" y="4.5" width="15" height="15" rx="1.5" transform="rotate(45 12 12)"/></g>'
            f'<g transform="translate(6.6 6.6) scale(.45)">{_hi("school")}</g>'
        )
    raise KeyError(f"رسمٌ محلّيٌّ غيرُ معرَّف: {name}")


def glyph_body(glyph: str) -> str:
    kind, _, name = glyph.partition(":")
    if kind == "hi":
        return _hi(name)
    if kind == "cmp":
        base, badge = name.split("+")
        if badge not in BADGES:
            raise KeyError(f"شارةٌ غيرُ معرَّفة: {badge}")
        return _hi(base) + _badge(badge)
    if kind == "local":
        return _local(name)
    raise KeyError(f"نوعُ رسمٍ غيرُ معروف: {glyph}")


def _symbol(sid: str, title: str, body: str) -> str:
    return f'<symbol id="{sid}" viewBox="0 0 24 24"><title>{title}</title>{body}</symbol>'


def build_sprite() -> str:
    meta = library()
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg">',
        "<!-- مولَّدٌ من core/icons.py — لا يُحرَّر: python manage.py build_icon_sprite -->",
        f"<!-- {meta['package']}@{meta['version']} · {meta['license']} -->",
    ]
    for key in sorted(ICONS):
        icon = ICONS[key]
        parts.append(_symbol(symbol_id(key), icon.label, glyph_body(icon.glyph)))
    for key, sizes in sorted(DETAILED_AT.items()):
        icon = ICONS[key]
        parts.append(
            _symbol(symbol_id(key, size=sizes[0]), icon.label, _local(f"{icon.source}-lg"))
        )
    for degree in VIOLATION_DEGREES:
        parts.append(
            _symbol(
                symbol_id("behavior_violation", degree),
                f"مخالفة من الدرجة {degree}",
                _violation(degree),
            )
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
