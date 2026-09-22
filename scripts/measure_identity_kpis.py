"""قياسُ مؤشّرات الهويّة البصريّة من الشجرة — يُعاد تشغيله عند كلّ تحديثٍ للتقرير.

    python measure_identity_kpis.py <جذر-المشروع> [--json]

يقرأ static/css/custom/*.css وtemplates/** وملفَّ خطّ أساس axe ويحسب المؤشّرات الآليّة.
المؤشّراتُ المسمّاةُ info_* معلوماتيّةٌ تملكها خطّةٌ أخرى (الجوال) ولا تُسجَّل هدفاً هنا.
المؤشّراتُ التي تحتاج متصفّحاً (أهداف اللمس، LCP/CLS/INP) لا تُقاس هنا.
"""

import glob
import json
import pathlib
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "."
files = sorted(glob.glob(f"{root}/static/css/custom/*.css"))
css = "".join(pathlib.Path(f).read_text(encoding="utf8") for f in files)

out = {}
out["info_css_source_bytes"] = len(css.encode("utf8"))
out["K02_important"] = css.count("!important")


# ── الرموز ──
def blocks(sel):
    res = {}
    for m in re.finditer(re.escape(sel) + r"\s*\{(.*?)\}", css, flags=re.S):
        for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1)):
            res[k] = v.strip()
    return res


light, dark = blocks(":root"), blocks("html.dark")
out["K03_custom_props"] = len(set(re.findall(r"(--[\w-]+)\s*:", css)))

sp = re.findall(r"(?:margin|padding|gap)(?:-[\w]+)?\s*:\s*([^;}]+)", css)
lit = sum(len(re.findall(r"\b\d+px", v)) for v in sp)
tok = sum(len(re.findall(r"var\(--sp", v)) for v in sp)
out["K04_spacing_px_literals"] = lit
out["K05_spacing_token_share_pct"] = round(100 * tok / (tok + lit), 1)
rd = re.findall(r"border-radius\s*:\s*([^;}]+)", css)
out["K06_radius_px_literals"] = sum(len(re.findall(r"\b\d+px", v)) for v in rd)
out["info_fontsize_px_literals_see_mobile_plan_K24"] = len(
    re.findall(r"font-size\s*:\s*\d+px", css)
)
out["K08_transition_all"] = len(re.findall(r"transition\s*:\s*all", css))
out["info_outline_none_guarded_by_test_focus_and_names"] = len(
    re.findall(r"outline\s*:\s*(?:none|0)\b", css)
)
out["K10_physical_props"] = (
    len(re.findall(r"\bmargin-(?:left|right)\s*:", css))
    + len(re.findall(r"\bpadding-(?:left|right)\s*:", css))
    + len(re.findall(r"text-align\s*:\s*(?:left|right)", css))
    + len(re.findall(r"border-(?:left|right)\b", css))
    + len(re.findall(r"(?<![-\w])(?:left|right)\s*:\s*[^;]", css))
    + len(re.findall(r"float\s*:\s*(?:left|right)", css))
)
themes = pathlib.Path(f"{root}/static/css/custom/40-themes.css").read_text(encoding="utf8")
out["K11_dark_rules_outside_themes"] = css.count("html.dark") - themes.count("html.dark")
out["K12_raw_brand_as_text"] = sum(
    len(re.findall(rf"(?<![-\w])color\s*:\s*var\(--{t}\)", css))
    for t in ("gold", "palm", "sea", "maroon-light")
)


# ── التباين ──
def resolve(v, env, d=0):
    m = re.fullmatch(r"var\((--[\w-]+)\)", v.strip())
    if m and d < 8 and m.group(1) in env:
        return resolve(env[m.group(1)], env, d + 1)
    return v


def rgb(h):
    h = h.strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{3,6}", h):
        return None
    h = h[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _lin(x):
    return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4


def lum(c):
    r, g, b = map(_lin, c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cr(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


TEXT_PAIRS = [
    ("text-primary", "surface"),
    ("text-primary", "page-bg"),
    ("text-secondary", "surface"),
    ("text-secondary", "page-bg"),
    ("text-muted", "surface"),
    ("text-muted", "page-bg"),
    ("maroon-fg", "surface"),
    ("maroon-fg", "page-bg"),
    ("status-danger-fg", "status-danger-bg"),
    ("status-success-fg", "status-success-bg"),
    ("status-warning-fg", "status-warning-bg"),
    ("status-info-fg", "status-info-bg"),
]
NONTEXT_PAIRS = [("control-border", "surface"), ("control-border", "page-bg")]


def worst(env, pairs):
    e = {**light, **env}
    vals = []
    for a, b in pairs:
        va, vb = e.get("--" + a), e.get("--" + b)
        ca = rgb(resolve(va, e)) if va else None
        cb = rgb(resolve(vb, e)) if vb else None
        if ca and cb:
            vals.append(cr(ca, cb))
    return round(min(vals), 2) if vals else None


out["K13_min_text_contrast_light"] = worst({}, TEXT_PAIRS)
out["K14_min_text_contrast_dark"] = worst(dark, TEXT_PAIRS)
out["K15_min_control_contrast_dark"] = worst(dark, NONTEXT_PAIRS)

# ── القوالب ──
tpl = {
    f: pathlib.Path(f).read_text(encoding="utf8", errors="ignore")
    for f in glob.glob(f"{root}/templates/**/*.html", recursive=True)
    if "pdf" not in f and "email" not in f
}
out["K16_tailwind_utility_attrs"] = sum(
    len(
        re.findall(
            r'class="[^"]*\b(?:flex|grid|p-\d|px-\d|py-\d|mt-\d|mb-\d|text-(?:xs|sm|lg|xl))\b', t
        )
    )
    for t in tpl.values()
)
out["K17_inline_scripts"] = sum(len(re.findall(r"<script(?![^>]*src)", t)) for t in tpl.values())
out["K18_buttons_without_type"] = sum(
    len([m for m in re.findall(r"<button\b[^>]*>", t) if "type=" not in m]) for t in tpl.values()
)
out["K19_img_without_dimensions"] = sum(
    len([m for m in re.findall(r"<img\b[^>]*>", t) if "width" not in m]) for t in tpl.values()
)
out["K20_inline_style_attrs_and_blocks"] = sum(
    len(re.findall(r'\sstyle="', t)) + len(re.findall(r"<style", t)) for t in tpl.values()
)
base = next(
    (v for k, v in tpl.items() if k.replace("\\", "/").endswith("templates/base/base.html")), ""
)
out["K21_css_import_chains_in_head"] = len(re.findall(r"@import\s+url", base))

# ── مسار الجوال (K26–K30) ──
out["info_K26_mobile_plan_owns_viewport_fit_cover"] = base.count("viewport-fit=cover")
out["info_K27_mobile_plan_owns_100vh_uses"] = len(re.findall(r"\b100vh\b", css))
out["info_K28_mobile_plan_owns_pointer_coarse_rules"] = css.count("pointer: coarse") + css.count(
    "pointer:coarse"
)
out["info_K29_mobile_plan_owns_safe_area_env_uses"] = css.count("env(safe-area-inset")
mqs = re.findall(r"@media\s*([^{]+)\{", css)


def _bounds(m):
    return re.findall(r"(max|min)-width:\s*(\d+)px", m)


out["info_K30_mobile_plan_owns_tablet_range_media_queries"] = len(
    [
        m
        for m in mqs
        if any(
            (k == "max" and 641 <= int(v) <= 1024) or (k == "min" and 641 <= int(v) <= 1025)
            for k, v in _bounds(m)
        )
    ]
)
out["info_phone_media_queries_le640"] = len(
    [m for m in mqs if any(k == "max" and int(v) <= 640 for k, v in _bounds(m))]
)
out["info_desktop_media_queries_ge1025"] = len(
    [m for m in mqs if any(k == "min" and int(v) >= 1025 for k, v in _bounds(m))]
)

# ── الوصولية والعلامة (A1، B1) ──
axe_path = pathlib.Path(root) / "tests" / "a11y_axe_ratchet_baseline.json"
if axe_path.exists():
    axe = json.loads(axe_path.read_text(encoding="utf8"))
    out["A1_axe_violation_nodes"] = sum(sum(rules.values()) for rules in axe.values())
brand_dir = pathlib.Path(root) / "static" / "brand"
out["B1_school_emblem_rasters_without_svg"] = len(list(brand_dir.glob("logo*.png")))

print(json.dumps(out, ensure_ascii=False, indent=2) if "--json" in sys.argv else out)
