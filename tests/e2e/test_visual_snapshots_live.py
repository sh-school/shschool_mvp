"""[IDENTITY] لقطاتُ الهويّة الحيّة (VI-13) — يلتقط أهمَّ خمس صفحاتٍ نهاراً وليلاً بعرضَي الجوال وسطح المكتب ويقيس الحتميّةَ والتغيّر.

يُشغَّل من `.github/workflows/visual-snapshots.yml` وحدَه (`VISUAL_SNAPSHOTS=1`)؛ وفي وظيفة `e2e` الإلزاميّة التي تجمع `tests/e2e/` كلَّه
يتخطّى نفسَه فلا يُصيّر عشرين لقطةً بلا طلب. المنطقُ (المقارنةُ والمصفوفة) في `tests/visual_snapshots.py` ومختبَرٌ بلا متصفّح.

لكلّ لقطةٍ: تُلتقط **مرّتين** بتحميلَين متتاليَين في التشغيل نفسِه ويجب أن تتطابقا (الحتميّة — وإلّا فالفرقُ عن `main` ضجيج)، ثمّ تُقارَن الأولى بأساس
`main` إن وُجد (`VISUAL_BASELINE_DIR`). فرقٌ فوق العتبة يفشل ما لم يحمل الطلبُ وسمَ «تغيير-بصريّ» (`VISUAL_ALLOW_CHANGES=1`).

المخرَجات في `VISUAL_OUT`: `shots/` (تُرفع أساساً حين يجري التشغيلُ على main)، و`repeat/` و`diffs/` و`summary.md` و`summary.json`.
"""

from __future__ import annotations

import os
import pathlib

import pytest

pytest.importorskip("pytest_playwright")

from tests import visual_snapshots as vs  # noqa: E402
from tests.mobile_audit import PROFILES  # noqa: E402
from tests.test_a11y_live_pages import _url  # noqa: E402
from tests.test_mobile_audit import JOURNEYS, _signed_in_state  # noqa: E402

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        not os.environ.get("VISUAL_SNAPSHOTS"),
        reason="اللقطاتُ البصريّة تُشغَّل من visual-snapshots.yml وحدَه",
    ),
]

#: Chart.js يرسم على canvas بحركةٍ (≈1s) لا يعطّلها `animations="disabled"` (CSS فقط) — فتُلتقط اللوحةُ في منتصف الرسم. يُعطَّل عند تعريف المكتبة.
NO_CHART_ANIMATION = (
    "(function(){var c;Object.defineProperty(window,'Chart',{configurable:true,"
    "get:function(){return c},set:function(v){c=v;try{v.defaults.animation=false}catch(e){}}})})();"
)
LOGIN_PATH = "/auth/login/"


def _do_step(page, step: str) -> None:
    """خطوةُ رحلةٍ (Q-11) حتميّة: نقرةٌ ثمّ انتظارُ حالةٍ ظاهرةٍ في الصفحة — لا انتظارَ بالزمن."""
    if step == "menu":  # لوحةُ الهامبرغر على الجوال
        page.click("#mob-menu-btn")
        page.wait_for_selector(".nb-bar.open")
    elif step == "palette":  # لوحةُ الأوامر من زرّ الترويسة، وحقلُها مركَّز
        page.click("#nav-search-btn")
        page.wait_for_selector("#cmd-palette:not(.cmd-hidden)")
        page.wait_for_function(
            "document.activeElement && document.activeElement.id === 'cmd-input'"
        )
    else:
        raise AssertionError(f"خطوةٌ غيرُ معرَّفة: {step} (المسموح {vs.STEPS})")


def _capture(page, base: str, name: str, path: pathlib.Path, step: str = "") -> None:
    response = page.goto(f"{base}{_url(name)}", wait_until="load")
    assert response and response.ok, f"{name}: {response and response.status}"
    assert LOGIN_PATH not in page.url, f"{name}: أُحيل إلى الدخول — الجلسةُ لم تثبت"
    page.add_style_tag(content=vs.FREEZE_CSS)
    page.evaluate("document.fonts.ready.then(() => 1)")
    page.wait_for_timeout(300)
    if step:
        _do_step(page, step)
        page.wait_for_timeout(300)
    height = min(page.evaluate("document.documentElement.scrollHeight"), vs.MAX_HEIGHT)
    width = page.viewport_size["width"]
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=str(path),
        full_page=True,
        clip={"x": 0, "y": 0, "width": width, "height": height},
        animations="disabled",
        caret="hide",
        scale="css",
        mask=[page.locator(vs.MASK_SELECTOR)],
    )


def test_the_key_pages_are_deterministic_and_have_not_changed_visually(
    request, playwright, live_server, tmp_path
):
    out = pathlib.Path(os.environ.get("VISUAL_OUT") or tmp_path / "visual")
    shots, repeat, diffs = out / "shots", out / "repeat", out / "diffs"
    baseline = os.environ.get("VISUAL_BASELINE_DIR")
    baseline_dir = pathlib.Path(baseline) if baseline else None
    allow_changes = bool(os.environ.get("VISUAL_ALLOW_CHANGES"))

    rows: list[dict] = []
    browser = playwright.chromium.launch()
    try:
        plan = vs.matrix()
        for role in sorted({shot.role for shot in plan}):
            fixture, _ = JOURNEYS[role]
            state = _signed_in_state(browser, live_server.url, request.getfixturevalue(fixture))
            for profile in vs.PROFILE_NAMES:
                for theme in vs.THEMES:
                    batch = [
                        shot
                        for shot in plan
                        if (shot.role, shot.profile, shot.theme) == (role, profile, theme)
                    ]
                    if not batch:
                        continue
                    context = browser.new_context(
                        storage_state=state,
                        reduced_motion="reduce",
                        locale="ar",
                        timezone_id="Asia/Qatar",
                        **PROFILES[profile],
                    )
                    context.add_init_script(vs.INIT_SCRIPT.format(theme=theme) + NO_CHART_ANIMATION)
                    try:
                        page = context.new_page()
                        for shot in batch:
                            key = shot.key
                            _capture(page, live_server.url, shot.page, shots / key, shot.step)
                            _capture(page, live_server.url, shot.page, repeat / key, shot.step)
                            determinism = vs.compare(shots / key, repeat / key)
                            row = {
                                "key": key,
                                "determinism": determinism.ratio,
                                "change": None,
                                "status": "✓",
                            }
                            if determinism.ratio > vs.DETERMINISM_MAX:
                                vs.save_diff(
                                    shots / key, repeat / key, diffs / f"determinism--{key}"
                                )
                                row["status"] = "غيرُ حتميّة"
                            elif baseline_dir is not None and (baseline_dir / key).exists():
                                change = vs.compare(baseline_dir / key, shots / key)
                                row["change"] = change.ratio
                                if change.ratio > vs.CHANGE_MAX:
                                    vs.save_diff(baseline_dir / key, shots / key, diffs / key)
                                    row["status"] = "تغيّر (معتمَد)" if allow_changes else "تغيّر"
                            elif baseline_dir is not None:
                                row["status"] = "بلا أساس"
                            rows.append(row)
                    finally:
                        context.close()
    finally:
        browser.close()

    vs.write_summary(out, rows)
    nondeterministic = [r for r in rows if r["status"] == "غيرُ حتميّة"]
    changed = [r for r in rows if r["status"] == "تغيّر"]
    assert not nondeterministic, (
        f"{len(nondeterministic)} لقطةً غيرَ حتميّة (تتغيّر بين تحميلَين متتاليَين؛ العتبة {vs.DETERMINISM_MAX * 100:.3f}%) — "
        "الفرقُ عن main فيها ضجيج؛ غطِّ المتقلّبَ بـ`data-visual-mask` أو اثبته:\n  "
        + "\n  ".join(f"{r['key']}: {r['determinism'] * 100:.3f}%" for r in nondeterministic)
    )
    assert not changed, (
        f"{len(changed)} لقطةً تغيّرت بصريّاً عن main (العتبة {vs.CHANGE_MAX * 100:.3f}%) — إن كان مقصوداً فأضِف وسمَ «تغيير-بصريّ» للطلب وسمِّ الصفحاتِ في وصفه:\n  "
        + "\n  ".join(f"{r['key']}: {r['change'] * 100:.3f}%" for r in changed)
    )
