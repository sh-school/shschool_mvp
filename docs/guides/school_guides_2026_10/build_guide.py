"""يبني دليلَ «المعلّم» أو «مشرف الجناح» PDF من `content_<الدليل>.py` وصور `shots/` — WeasyPrint بخطّ Tajawal من static/fonts.

    python docs/guides/school_guides_2026_10/build_guide.py teacher    # ← teacher_guide_v1.0.pdf بجانبه
    python docs/guides/school_guides_2026_10/build_guide.py wing       # ← wing_supervisor_guide_v4.0.pdf

الغلافُ والفهرسُ وأرقامُ الصفحات والتذييلُ كلُّها تُولَّد هنا؛ لا برنامجَ تنضيدٍ خارجيّ. ويُكتب على الغلاف رأسُ الشيفرة التي صُوِّرت منها الشاشات.
"""

import importlib
import json
import os
import pathlib
import sys

from weasyprint import HTML

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
META = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
ROOT = HERE.parent.parent.parent
DATE_AR = "6 أكتوبر 2026"
STATUS = "(الوضع الحاليّ)"

GUIDES = {
    "teacher": {
        "module": "content_teacher",
        "version": "1.0",
        "file": "teacher_guide_v1.0.pdf",
        "title": "دليل المعلّم",
        "h1": "دليلُ المعلّم",
        "badge": "كُتيّب تشغيل · الإصدار 1.0 — الوضعُ الحاليّ",
        "lead": "كلُّ ما تحتاجه لتشغيل عملك اليوميّ على منصّة SchoolOS: من الدخول صباحاً، إلى اختيار الشعبة والحصّة ثمّ رصد الحضور وتثبيته، وتسجيل المخالفة السلوكيّة، ومتابعة طلّابك — خطوةً خطوة، بصورٍ من المنصّة نفسها وأرقامٍ تدلّك أين تضغط.",
        "soft": "على الوضع الحاليّ للمنصّة: الرصدُ بحصّةٍ مؤقّتةٍ لحين اعتماد جدول المنصّة — الدرجاتُ خارج هذه النسخة",
    },
    "wing": {
        "module": "content_wing",
        "version": "4.0",
        "file": "wing_supervisor_guide_v4.0.pdf",
        "title": "دليل مشرف الجناح",
        "h1": "دليلُ مشرف الجناح",
        "badge": "كُتيّب تشغيل · الإصدار 4.0 — الوضعُ الحاليّ",
        "lead": "كلُّ ما تحتاجه لتشغيل جناحك على منصّة SchoolOS: رصدُ الغياب بالحصّة، واعتمادُ إدخالات المعلّمين، وملفُّ الغياب والاتّصالُ بوليّ الأمر وإثباتُ الأعذار، والمتابعةُ اليوميّةُ والرفعُ للوزارة — خطوةً خطوة، بصورٍ من المنصّة وأرقامٍ تدلّك أين تضغط.",
        "soft": "يتابع الإصدار 3.0 (17 سبتمبر 2026) على الوضع الحاليّ للمنصّة",
    },
}


def base_commit():
    """رأسُ الشيفرة المصوَّرة منها الشاشات: يُمرَّر بالمتغيّر BASE_COMMIT عند البناء (لا استدعاءَ لغيت من هنا)."""
    return os.environ.get("BASE_COMMIT", "غير معروف")


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


def build(which):
    spec = GUIDES[which]
    sections = importlib.import_module(spec["module"]).SECTIONS
    css = (
        (HERE / "guide_style.tpl")
        .read_text(encoding="utf-8")
        .replace("@@ROOT@@", str(ROOT))
        .replace("@@VERSION@@", spec["version"])
        .replace("@@DATE@@", DATE_AR)
        .replace("@@TITLE@@", spec["title"])
        .replace("@@STATUS@@", STATUS)
    )
    cover = f"""
    <div class="cover"><div class="inner">
      <img class="em" src="{ROOT}/static/brand/emblem-white.svg">
      <div class="school">{META["school"]}</div>
      <div class="min">{META["ministry"]}</div>
      <hr>
      <div class="badge">{spec["badge"]}</div>
      <h1>{spec["h1"]}</h1>
      <div class="lead">{spec["lead"]}</div>
      <div class="meta"><span>المنصّة: SchoolOS v5.5</span><span>العام الدراسيّ: 2026-2027</span><span>تاريخ التحديث: {DATE_AR}</span></div>
      <div class="meta soft">{spec["soft"]}</div>
      <div class="meta soft">رأسُ الشيفرة المصوَّرة منها الشاشات: <span dir="ltr">{base_commit()}</span></div>
    </div></div>
    """
    toc_items = "".join(
        f'<li><a href="#sec-{s["id"]}"><span class="n">{i}</span>{s["title"]}</a></li>'
        for i, s in enumerate(sections, 1)
    )
    toc = f'<section class="sec first"><h1 class="toc-h">المحتويات</h1><ol class="toc">{toc_items}</ol></section>'
    body = []
    for i, s in enumerate(sections, 1):
        blocks = "".join(render_block(b) for b in s["blocks"])
        body.append(
            f'<section class="sec" id="sec-{s["id"]}"><div class="sechead"><div class="nc"><span class="num">{i}</span></div>'
            f'<div class="ttl"><h2>{s["title"]}</h2><p class="sub">{s["sub"]}</p></div></div>{blocks}</section>'
        )
    doc = (
        f"<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><title>{spec['title']} v{spec['version']}</title>"
        f"<style>{css}</style></head><body>{cover}{toc}{''.join(body)}</body></html>"
    )
    html_path = HERE / f"guide_{which}.html"
    html_path.write_text(doc, encoding="utf-8")
    out = HERE / spec["file"]
    HTML(string=doc, base_url=str(HERE)).write_pdf(str(out))
    html_path.unlink()
    print("✓", out, round(out.stat().st_size / 1024), "KB")


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "teacher"
    build(which)


if __name__ == "__main__":
    main()
