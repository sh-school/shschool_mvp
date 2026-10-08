"""يبني «دليل المعلّم» PDF من `content.py` وصور `shots/` — WeasyPrint بخطّ Tajawal من static/fonts.

    python docs/guides/teacher_guide_v0_1/build_guide.py            # ← teacher_guide_v0.1.pdf بجانبه

الغلافُ والفهرسُ وأرقامُ الصفحات والتذييلُ كلُّها تُولَّد هنا؛ لا برنامجَ تنضيدٍ خارجيّ.
"""

import json
import pathlib

from content import SECTIONS
from weasyprint import HTML

HERE = pathlib.Path(__file__).parent
META = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
ROOT = HERE.parent.parent.parent
VERSION = "0.1"
DATE_AR = "5 أكتوبر 2026"

CSS = (
    (HERE / "guide_style.tpl")
    .read_text(encoding="utf-8")
    .replace("@@ROOT@@", str(ROOT))
    .replace("@@VERSION@@", VERSION)
    .replace("@@DATE@@", DATE_AR)
)


def esc(s):
    return s  # المحتوى مكتوبٌ بعلاماتٍ موثوقة (b, code) من content.py


def render_block(block):
    kind = block[0]
    if kind == "p":
        return f"<p>{block[1]}</p>"
    if kind == "h3":
        return f"<h3>{block[1]}</h3>"
    if kind in ("note", "rule", "warn"):
        return f'<div class="{kind}">{block[1]}</div>'
    if kind == "bullets":
        return '<ul class="bul">' + "".join(f"<li>{i}</li>" for i in block[1]) + "</ul>"
    if kind == "steps":
        return '<ol class="steps">' + "".join(f"<li>{i}</li>" for i in block[1]) + "</ol>"
    if kind == "checklist":
        return '<ul class="check">' + "".join(f"<li>{i}</li>" for i in block[1]) + "</ul>"
    if kind == "table":
        head = "".join(f"<th>{h}</th>" for h in block[1])
        rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in block[2])
        keep = " keep" if len(block[2]) <= 9 else ""
        return f'<table class="t{keep}"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'
    if kind == "cards":
        return (
            '<div class="cards">'
            + "".join(f'<div class="card"><b>{t}</b><span>{d}</span></div>' for t, d in block[1])
            + "</div>"
        )
    if kind == "timeline":
        return (
            '<div class="timeline">'
            + "".join(
                f'<div class="tl"><span class="when">{w}</span><b class="what">{t}</b><p>{d}</p></div>'
                for w, t, d in block[1]
            )
            + "</div>"
        )
    if kind == "fig":
        _, image, legend, scale = block[:4]
        single = len(block) > 4 and block[4]
        items = "".join(
            f'<li><span class="k">{i}</span>{text}</li>' for i, text in enumerate(legend, 1)
        )
        if single and len(legend) == 1:
            items = f'<li class="flat">{legend[0]}</li>'
        cls = "legend one" if len(legend) <= 2 else "legend"
        width = int(min(scale, 1.0) * 100)
        return f'<figure class="fig"><img src="shots/{image}" class="w{width}"><ol class="{cls}">{items}</ol></figure>'
    raise ValueError(kind)


def build():
    cover = f"""
    <div class="cover"><div class="inner">
      <img class="em" src="{ROOT}/static/brand/emblem-white.svg">
      <div class="school">{META["school"]}</div>
      <div class="min">وزارة التربية والتعليم والتعليم العالي — دولة قطر</div>
      <hr>
      <div class="badge">كُتيّب تشغيل · الإصدار {VERSION} (نسخةٌ مؤقّتة)</div>
      <h1>دليلُ المعلّم</h1>
      <div class="lead">كلُّ ما تحتاجه لتشغيل عملك اليوميّ على منصّة SchoolOS: من الدخول صباحاً، إلى اختيار الشعبة والحصّة ثمّ رصد الحضور وتثبيته،
      وتسجيل المخالفة السلوكيّة، ومتابعة جدولك وطلّابك — خطوةً خطوة، بصورٍ من المنصّة نفسها وأرقامٍ تدلّك أين تضغط.</div>
      <div class="meta"><span>المنصّة: SchoolOS v5.5</span><span>العام الدراسيّ: 2026-2027</span><span>تاريخ التحديث: {DATE_AR}</span></div>
      <div class="meta soft">نسخةٌ مؤقّتةٌ على الوضع الحاليّ للمنصّة — قيد المراجعة</div>
    </div></div>
    """
    toc_items = "".join(
        f'<li><a href="#sec-{s["id"]}"><span class="n">{i}</span>{s["title"]}</a></li>'
        for i, s in enumerate(SECTIONS, 1)
    )
    toc = f'<section class="sec first"><h1 class="toc-h">المحتويات</h1><ol class="toc">{toc_items}</ol></section>'
    body = []
    for i, s in enumerate(SECTIONS, 1):
        blocks = "".join(render_block(b) for b in s["blocks"])
        body.append(
            f'<section class="sec" id="sec-{s["id"]}"><div class="sechead"><div class="nc"><span class="num">{i}</span></div>'
            f'<div class="ttl"><h2>{s["title"]}</h2><p class="sub">{s["sub"]}</p></div></div>{blocks}</section>'
        )
    doc = f"<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><title>دليل المعلّم v{VERSION}</title><style>{CSS}</style></head><body>{cover}{toc}{''.join(body)}</body></html>"
    (HERE / "guide.html").write_text(doc, encoding="utf-8")
    out = HERE / f"teacher_guide_v{VERSION}.pdf"
    HTML(string=doc, base_url=str(HERE)).write_pdf(str(out))
    print("✓", out, round(out.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    build()
