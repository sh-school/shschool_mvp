#!/usr/bin/env python3
"""تقريرُ التزام الهويّة الشهريّ الآليّ (W-20261016-017) — أربعةُ أرقامٍ مع الاتجاه، معلوماتيٌّ لا يحجب.

    python scripts/identity_monthly_report.py [--out docs/identity] [--visual-gate N] [--no-write]

الأرقام الأربعة (تُقاس بعدّادات المنصّة القائمة لا بعدٍّ جديد):
  ١. ألوانٌ سداسيّةٌ/حرفيّةٌ خارج الرموز: في القوالب (`tests.design_ratchet`) + داخل قواعد CSS (`css_literals`).
  ٢. `!important` في ملفّات custom.css — عدٌّ خام (16 يوم القياس الأوّل)، وبجانبه ما تعدّه السقّاطة فعلاً (6).
  ٣. `style=` في القوالب، عدٌّ خام مع عدد القوالب (110 في 19)، وبجانبه ما تعدّه السقّاطة فعلاً (0: متغيّراتٌ مخصَّصة فقط).
  ٤. مخالفاتُ visual_gate: أداةٌ تفتح الصفحاتِ في متصفّحٍ وتكتب أدلّةً لكلّ بطاقة، فلا تُقاس في هذا العمل؛ تُمرَّر `--visual-gate N`
     من الأدلّة وإلا «غير مقيس» (لا صفرٌ مُصطنع).

الاتجاه: مقارنةٌ بآخر تقريرٍ محفوظ `monthly_report.json` في مجلّد الإخراج؛ وأوّلُ تقريرٍ بلا اتجاه («أوّل قياس»).
لا يفشل العملُ بسبب رقم (الخروج 0 دائماً ما لم يتعذّر الكتابة): ارتفاعُ رقمٍ يظهر سهماً في التقرير ولا يحجب شيئاً.
ولا يعدّل حارساً ولا سقّاطة: يقرأ فقط.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UNMEASURED = "غير مقيس"
STYLE_ATTR = re.compile(r'\sstyle="')  # كما في measure_identity_kpis (K20)
METRICS = (
    ("hex_outside_tokens", "ألوانٌ حرفيّةٌ خارج الرموز", "قيمةُ لونٍ مكتوبةٌ بيدٍ في قالبٍ أو قاعدة CSS بدل رمزٍ يتبع الوضع الداكن."),
    ("important", "‎!important في CSS", "فرضٌ للأولويّة يصعّب تعديلَ التنسيق لاحقاً."),
    ("inline_style", "تنسيقٌ داخل الوسم (style=)", "تنسيقٌ مكتوبٌ في القالب نفسِه خارج ملفّات التنسيق المركزيّة."),
    ("visual_gate", "مخالفاتُ visual_gate", "مخالفاتٌ التقطتها البوّابةُ البصريّة في متصفّحٍ حقيقيّ (مسافات، تداخل، خطٌّ صغير)."),
)


def raw_counts() -> tuple[int, int, int]:
    """(`!important` في custom.css، `style=` في القوالب، عدد القوالب الحاملة له) — عدٌّ خامٌّ بلا استثناء."""
    important = sum(p.read_text(encoding="utf-8").count("!important") for p in (ROOT / "static/css/custom").rglob("*.css"))
    inline = templates = 0
    for path in (ROOT / "templates").rglob("*.html"):
        found = len(STYLE_ATTR.findall(path.read_text(encoding="utf-8")))
        inline += found
        templates += bool(found)
    return important, inline, templates


def measure(visual_gate: int | None = None) -> dict:
    """الأرقام الأربعة؛ ما تعذّر قياسُه نصُّ «غير مقيس» لا صفر."""
    result: dict = {"inline_templates": UNMEASURED}
    try:
        from tests import design_ratchet as dr

        counts = dr.measure()
        tmpl_hex = sum(counts["hex_colour"].values())
        # الرأسُ: العدُّ الخام (كقياس K02 و«110 في 19 قالباً» المسجَّلين)؛ والتفصيلُ: ما تعدّه السقّاطة فعلاً (بلا سياقات الطباعة/الحركة
        # المسموحة ولا `style="--x:…"` الحاملِ لمتغيّر).
        raw_important, raw_inline, raw_templates = raw_counts()
        result["important"] = raw_important
        result["inline_style"] = raw_inline
        result["inline_templates"] = raw_templates
        result["effective"] = {
            "important": sum(counts["important"].values()),
            "inline_style": sum(counts["inline_style"].values()),
        }
    except Exception:  # الاستيراد أو القراءة تعذّر: لا قياس
        tmpl_hex = None
        result["important"] = result["inline_style"] = UNMEASURED
    try:
        from tests.css_source import read_css
        from tests.test_css_colours_are_tokens import css_literals

        css_hex = len(css_literals(read_css()))
    except Exception:
        css_hex = None
    result["hex_outside_tokens"] = UNMEASURED if tmpl_hex is None or css_hex is None else tmpl_hex + css_hex
    result.setdefault("effective", {})
    result["hex_detail"] = {"templates": tmpl_hex, "css_rules": css_hex}
    result["visual_gate"] = UNMEASURED if visual_gate is None else visual_gate
    return result


def trend(now: object, before: object) -> str:
    """سهمُ الاتجاه: ▲ ارتفع (تراجع للهويّة) ▼ انخفض (تحسّن) ═ ثابت؛ وغيرُ رقميٍّ أو بلا سابق = لا اتجاه."""
    if not isinstance(now, int) or not isinstance(before, int):
        return "—"
    if now > before:
        return f"▲ +{now - before}"
    if now < before:
        return f"▼ {now - before}"
    return "═ 0"


def build(current: dict, previous: dict | None, today: dt.date) -> dict:
    prev_values = (previous or {}).get("values", {})
    rows = []
    for key, label, meaning in METRICS:
        before = prev_values.get(key)
        rows.append(
            {
                "key": key,
                "label": label,
                "meaning": meaning,
                "value": current[key],
                "previous": before,
                "trend": trend(current[key], before) if previous else "أوّل قياس — بلا اتجاه",
            }
        )
    return {
        "date": today.isoformat(),
        "previous_date": (previous or {}).get("date"),
        "values": {k: current[k] for k, _l, _m in METRICS},
        "inline_templates": current["inline_templates"],
        "hex_detail": current["hex_detail"],
        "effective": current.get("effective", {}),
        "rows": rows,
    }


def render_markdown(report: dict) -> str:
    lines = [
        f"# تقريرُ التزام الهويّة — {report['date']}",
        "",
        "تقريرٌ معلوماتيٌّ يُولَّد آلياً؛ لا يحجب شيئاً ولا يفشل بسبب رقم. الاتجاه عن "
        + (report["previous_date"] or "— (أوّل قياس)")
        + ".",
        "",
        "| المؤشّر | القيمة | السابق | الاتجاه | ما يعنيه |",
        "|---|---|---|---|---|",
    ]
    for r in report["rows"]:
        prev = "—" if r["previous"] is None else r["previous"]
        lines.append(f"| {r['label']} | {r['value']} | {prev} | {r['trend']} | {r['meaning']} |")
    lines += [
        "",
        f"القوالب المعنيّة بتنسيق `style=`: {report['inline_templates']}.",
        "ما تعدّه سقّاطةُ الهويّة فعلاً (بلا سياقات الطباعة/الحركة المسموحة ولا التنسيق الحامل لمتغيّرٍ مخصَّص فقط): "
        f"`!important` {report['effective'].get('important', UNMEASURED)}، `style=` {report['effective'].get('inline_style', UNMEASURED)}.",
        f"تفصيل الألوان الحرفيّة: القوالب {report['hex_detail']['templates']}، قواعد CSS {report['hex_detail']['css_rules']}.",
        "",
        "سهم ▲ = ارتفاعُ مخالفاتٍ (تراجع)، ▼ = انخفاض (تحسّن). «غير مقيس» = لم يُقَس في هذا التشغيل، وليس صفراً.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "docs" / "identity"))
    ap.add_argument("--visual-gate", type=int, default=None)
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)
    out = pathlib.Path(args.out)
    json_path = out / "monthly_report.json"
    previous = None
    if json_path.exists():
        try:
            previous = json.loads(json_path.read_text(encoding="utf-8"))
        except ValueError:
            previous = None
    report = build(measure(args.visual_gate), previous, dt.date.today())
    text = render_markdown(report)
    print(text)
    if not args.no_write:
        out.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "monthly_report.md").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
