"""هوامشُ الحرّاس والميزانيّات من مرجعٍ في git — قراءةٌ فقط، بلا checkout ولا خادم ولا شبكة.

    python guard_margins.py [--repo D:/shschool_mvp] [--ref origin/main] [--json]

يقرأ الثوابتَ من ملفّاتها الحيّة (لا من الوثائق ولا من الذاكرة) ويحسب الهامشَ الساكنَ لكلّ سقفٍ
وسقّاطةٍ يمكن حسابُها بلا متصفّح، ويطبع إصداراتِ الأدوات المثبَّتة في سير العمل وانجرافَها
عن requirements-dev.txt. كلُّ سطرٍ: «المفتاح = القيمة | المصدر».

ما لا يقيسه (يحتاج متصفّحاً أو قاعدة): LCP وCLS وINP، وaxe الحيّ، وسقّاطةُ الجوال، ولقطاتُ الهويّة،
والنظائرُ الليليّة (MAX_IDENTICAL_DARK_TWINS يُطبع سقفُه فقط). شغّل حارسَها نفسَه لذلك.
حجمُ CSS الخامّ هنا تقديرٌ ساكن: مجموعُ ملفّات CSS_FILES؛ والبوّابةُ تقيس ما تحمّله الصفحةُ في live_server.
ولمرجعٍ أقدمَ من VI-12 (2026-09-26) كان tailwind.min.css (≈13KB) يُحمَّل خارج CSS_FILES فيُضاف يدويّاً.
تحقّقٌ تاريخيّ: عند 40bbceee (2026-09-25) أعطى هامشَ المصغَّر 7,338 بايتاً كما سُجِّل يومَها.
ينفّذ tests/px_tokens.py من المرجع نفسِه (وحدةٌ نقيّةٌ لا تستورد إلّا re) ليعدّ بمحلّل الحارس لا بنسخةٍ ثانية.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys


def git(repo: str, *args: str, binary: bool = False):
    # كلُّ قراءةٍ عبر git نفسِه: لا تُمسّ شجرةُ العمل ولا الفهرس.
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode("utf-8")


def show(repo: str, ref: str, path: str, binary: bool = False):
    return git(repo, "show", f"{ref}:{path}", binary=binary)


def const_eval(node: ast.AST):
    # مقيِّمٌ آمنٌ لثوابت بسيطة (رقم، نصّ، قاموس، ضربٌ وجمعٌ وطرح) — لا eval عامّ.
    if isinstance(node, ast.BinOp):
        left, right = const_eval(node.left), const_eval(node.right)
        ops = {
            ast.Mult: lambda a, b: a * b,
            ast.Add: lambda a, b: a + b,
            ast.Sub: lambda a, b: a - b,
        }
        return ops[type(node.op)](left, right)
    return ast.literal_eval(node)


def constants(source: str, names: tuple[str, ...]) -> dict:
    found = {}
    for node in ast.parse(source).body:
        targets = []
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        for target in targets:
            if isinstance(target, ast.Name) and target.id in names:
                found[target.id] = const_eval(value)
    return found


def line_count(text: str) -> int:
    # يطابق عدَّ file_size_ratchet: سطرٌ أخيرٌ بلا فاصلٍ يُعدّ سطراً.
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


PIN_RE = re.compile(r"(?<![\w.-])([A-Za-z][\w.-]*(?:\[[\w,]+\])?)==([0-9][\w.]*)")
PIN_SOURCES = (
    ".github/workflows/quality-gate.yml",
    ".github/workflows/security-scan.yml",
    ".github/workflows/quality.yml",
    "requirements-mypy.txt",
)


def strip_comments(text: str) -> str:
    # إصدارٌ مذكورٌ في تعليقٍ (أداةٌ أُزيلت مثلاً) ليس تثبيتاً تحكم به البوّابة.
    return "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in text.splitlines())


def pins(repo: str, ref: str) -> tuple[dict, list]:
    # الإصدارُ الذي تحكم به البوّابةُ هو المكتوبُ في سير العمل أو في requirements-mypy.txt.
    gate: dict[str, tuple[str, str]] = {}
    for path in PIN_SOURCES:
        try:
            text = strip_comments(show(repo, ref, path))
        except subprocess.CalledProcessError:
            continue  # مصدرٌ لم يوجد بعدُ في هذا المرجع
        for name, version in PIN_RE.findall(text):
            key = re.sub(r"\[.*\]", "", name).lower()
            gate.setdefault(key, (version, path))
    dev = {}
    for name, version in PIN_RE.findall(strip_comments(show(repo, ref, "requirements-dev.txt"))):
        dev[re.sub(r"\[.*\]", "", name).lower()] = version
    drift = [
        f"{name}: البوّابة {v} ({src}) · requirements-dev {dev[name]}"
        for name, (v, src) in sorted(gate.items())
        if name in dev and dev[name] != v
    ]
    return gate, drift


def measure(repo: str, ref: str) -> dict:
    sha = git(repo, "rev-parse", "--short", ref).strip()
    when = git(repo, "log", "-1", "--format=%cI", ref).strip()
    rows: list[tuple[str, object, str]] = []

    def add(key: str, value: object, source: str) -> None:
        rows.append((key, value, source))

    def optional(key: str, source: str, fn) -> None:
        # حارسٌ لم يوجد بعدُ في مرجعٍ قديم يُذكر غائباً ولا يوقف الباقي.
        try:
            add(key, fn(), source)
        except (subprocess.CalledProcessError, KeyError) as exc:
            add(key, f"غائبٌ في هذا المرجع ({type(exc).__name__})", source)

    # ── CSS: الخامّ والمصغَّر ──
    css_mod = constants(show(repo, ref, "core/css_files.py"), ("CSS_DIR", "CSS_FILES"))
    paths = [f"static/{css_mod['CSS_DIR']}/{name}" for name in css_mod["CSS_FILES"]]
    blobs = [show(repo, ref, p, binary=True) for p in paths]
    raw = sum(len(b) for b in blobs)
    budget = constants(show(repo, ref, "tests/web_vitals.py"), ("BUDGET",))["BUDGET"]
    # css_kb = round(بايتات/1024) ثمّ يسقط إن زاد على السقف؛ فأقصى ما يمرّ (السقف + 0.5) × 1024 بايتاً
    # (round في بايثون يقرّب النصفَ إلى الزوجيّ). الهامشُ = ما يمكن إضافتُه قبل السقوط.
    raw_limit = int((budget["css_kb"] + 0.5) * 1024)
    add("budget.web_vitals", budget, "tests/web_vitals.py:BUDGET")
    add(
        "css.raw_bytes", raw, f"مجموع {len(paths)} ملفّاً من core/css_files.py:CSS_FILES (تقديرٌ ساكن)"
    )
    add(
        "css.raw_margin_bytes",
        raw_limit - raw,
        f"حتى {raw_limit} بايتاً = css_kb {budget['css_kb']} (tests/web_vitals.py)",
    )

    cap = constants(show(repo, ref, "tests/test_css_budget.py"), ("MAX_SHIPPED_BYTES",))[
        "MAX_SHIPPED_BYTES"
    ]
    add("css.shipped_cap_bytes", cap, "tests/test_css_budget.py:MAX_SHIPPED_BYTES")
    try:
        import rcssmin  # الإصدارُ المعتمَد في requirements.txt؛ غيرُه قد يعطي بايتاتٍ أخرى

        shipped = sum(len(rcssmin.cssmin(b.decode("utf-8")).encode("utf-8")) for b in blobs)
        add(
            "css.shipped_bytes",
            shipped,
            f"rcssmin {getattr(rcssmin, '__version__', '?')} كما في core/static_storage.py",
        )
        add("css.shipped_margin_bytes", cap - shipped, "السقف ناقصاً المصغَّر")
    except ImportError:
        add(
            "css.shipped_bytes",
            "لم يُقَس: rcssmin غائب",
            "pip install rcssmin بإصدار requirements.txt",
        )

    # ── قيمُ px ──
    px_ns: dict = {"__name__": "px_tokens"}
    exec(compile(show(repo, ref, "tests/px_tokens.py"), "px_tokens.py", "exec"), px_ns)
    css_text = "\n".join(b.decode("utf-8") for b in blobs)
    counts = px_ns["count_literals"](css_text)
    ceil = constants(
        show(repo, ref, "tests/test_px_tokens.py"), ("OFF_SCALE_SPACING", "OFF_SCALE_RADIUS")
    )
    add(
        "px.spacing_off_scale",
        f"{counts['spacing_off_scale']} / {ceil['OFF_SCALE_SPACING']}",
        "tests/test_px_tokens.py (يجب أن يتساويا)",
    )
    add(
        "px.radius_off_scale",
        f"{counts['radius_off_scale']} / {ceil['OFF_SCALE_RADIUS']}",
        "tests/test_px_tokens.py (يجب أن يتساويا)",
    )
    add("px.on_scale", counts["spacing_on_scale"] + counts["radius_on_scale"], "يجب أن يكون 0")
    add("px.font_size_px", px_ns["count_font_size_px"](css_text), "يجب أن يكون 0")
    optional(
        "css.dark_twins_cap",
        "tests/test_css_dead_overrides.py (العدُّ الفعليّ بالحارس نفسِه)",
        lambda: constants(
            show(repo, ref, "tests/test_css_dead_overrides.py"), ("MAX_IDENTICAL_DARK_TWINS",)
        )["MAX_IDENTICAL_DARK_TWINS"],
    )

    # ── حجمُ الملفّات: أضيقُ الهوامش ──
    def file_size() -> str:
        fs = constants(show(repo, ref, "tests/file_size_ratchet.py"), ("HARD_LIMIT", "TOLERANCE"))
        base = json.loads(show(repo, ref, "tests/file_size_baseline.json"))
        margins = sorted(
            (base[f] + fs["TOLERANCE"] - line_count(show(repo, ref, f)), f) for f in base
        )
        tightest = "، ".join(f"{f} ({m})" for m, f in margins[:3])
        return f"HARD_LIMIT={fs['HARD_LIMIT']} TOLERANCE={fs['TOLERANCE']} مسجَّلة={len(base)}؛ أضيقُها: {tightest}"

    optional(
        "file_size.margins",
        "tests/file_size_ratchet.py (المسجَّل + TOLERANCE ناقصاً الأسطر الحاليّة)",
        file_size,
    )

    # ── خطوطُ الأساس ──
    def load(path: str):
        return json.loads(show(repo, ref, path))

    def mypy_total() -> str:
        mypy = load("tests/mypy_ratchet_baseline.json")
        return f"{mypy['total']} في {len(mypy['files'])} ملفّاً"

    optional("ratchet.mypy", "tests/mypy_ratchet_baseline.json", mypy_total)
    optional(
        "ratchet.layering",
        "tests/layering_baseline.json",
        lambda: {
            k: len(v)
            for k, v in load("tests/layering_baseline.json").items()
            if isinstance(v, (dict, list))
        },
    )
    optional(
        "ratchet.page_layout",
        "tests/page_layout_baseline.json",
        lambda: len(load("tests/page_layout_baseline.json")),
    )
    optional(
        "ratchet.axe",
        "tests/a11y_axe_ratchet_baseline.json",
        lambda: len(load("tests/a11y_axe_ratchet_baseline.json")),
    )
    optional(
        "ratchet.print_frame",
        "tests/print_frame_baseline.json",
        lambda: sum(sum(v.values()) for v in load("tests/print_frame_baseline.json").values()),
    )
    optional(
        "freeze.tailwind",
        "tests/tailwind_freeze_baseline.json",
        lambda: len(load("tests/tailwind_freeze_baseline.json")),
    )
    cov = re.search(r"fail_under\s*=\s*(\d+)", show(repo, ref, "pyproject.toml"))
    add(
        "coverage.fail_under", cov.group(1) if cov else "؟", "pyproject.toml [tool.coverage.report]"
    )

    gate, drift = pins(repo, ref)
    add(
        "pins.gate",
        {k: v for k, (v, _) in sorted(gate.items())},
        "سيرُ العمل + requirements-mypy.txt",
    )
    add("pins.drift", drift or "لا انجراف", "مقارنةً بـrequirements-dev.txt")
    return {"ref": ref, "sha": sha, "committed": when, "rows": rows}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="هوامشُ الحرّاس من مرجعٍ في git (قراءةٌ فقط)")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        result = measure(args.repo, args.ref)
    except subprocess.CalledProcessError as exc:
        print(f"فشلت قراءةُ git: {exc.stderr.decode('utf-8', 'replace').strip()}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
        return 0
    print(f"# ref={result['ref']} sha={result['sha']} committed={result['committed']}")
    for key, value, source in result["rows"]:
        shown = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
        print(f"{key} = {shown} | {source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
