"""[OWN-21] مسحُ الإدارة كلِّها على 375px نهاراً وليلاً — قياسٌ شاملٌ قابلٌ للإعادة لا عيّنةَ صفحات.

`test_a11y_axe_ratchet.py` يحرس صفحاتٍ منتقاةً في كلّ طلب دمج (بضع ثوانٍ). وهذا يمسح **كلَّ** `ModelAdmin` مسجَّل
(قائمتَه وصفحةَ إضافته) والفهرس — نحو 190 مساراً في وضعَين، قرابةَ 25 دقيقة — فلا يجري في CI العاديّ بل حين يُطلب:

    ADMIN_SWEEP=1 DJANGO_ALLOW_ASYNC_UNSAFE=1 pytest tests/e2e/test_admin_sweep.py -s

ما يُقاس في كلّ صفحة: تجاوزٌ أفقيٌّ (`scrollWidth` فوق العرض)، وأهدافُ لمسٍ دون 44px (تعريفُ
`test_a11y_axe_ratchet.SMALL_TARGETS_JS` نفسُه)، ومخالفاتُ axe-core (تباين، وأسماء، وروابطُ داخل نصٍّ، وترتيب)،
و`tabindex` موجب. والمسارُ الذي يردّ 403 (نموذجٌ بلا إضافة) يُقاس بصفحة الخطأ التي يعرضها — وهي جزءٌ من الإدارة تراه المطوّر.

وجد أوّلُ مسحٍ (2026-09-25) على 382 صفحة: 0 تجاوزاً و0 `tabindex`، و116 هدفَ لمسٍ دون 44px (زرُّ صفحة الخطأ 41px،
وطيّاتُ النماذج `summary` 34px، وحقلُ الملفّ 26px، ورابطُ «أظهر الكل» 12px)، و26 عقدةَ axe (نصُّ زرّ الرجوع في صفحة 403 بتباين
3.18، ورابطُ «أظهر الكل» بتباين 1.23 مع النصّ المحيط) — أُصلحت كلُّها وأُعيد المسح فصار الجميعُ صفراً.
"""

from __future__ import annotations

import json
import os
import pathlib
import time

import pytest

pytest.importorskip("axe_playwright_python")

from tests import a11y_axe_ratchet as ratchet  # noqa: E402
from tests.test_a11y_axe_ratchet import SMALL_TARGETS_JS, _login  # noqa: E402

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(not os.environ.get("ADMIN_SWEEP"), reason="مسحٌ شاملٌ طويل — ADMIN_SWEEP=1"),
]

OVERFLOW_JS = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
POSITIVE_TABINDEX_JS = "() => [...document.querySelectorAll('[tabindex]')].filter(e => Number(e.getAttribute('tabindex')) > 0).length"


def admin_paths() -> list[str]:
    """الفهرسُ وقائمةُ كلّ نموذجٍ مسجَّل في الإدارة وصفحةُ إضافته."""
    from django.contrib import admin
    from django.urls import NoReverseMatch, reverse

    paths = {"/admin/"}
    for model in admin.site._registry:
        for kind in ("changelist", "add"):
            try:
                paths.add(reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_{kind}"))
            except NoReverseMatch:
                pass
    return sorted(paths)


def _measure(page, live_server, path: str) -> dict:
    response = page.goto(f"{live_server.url}{path}")
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:  # noqa: BLE001 — اتّصالٌ طويلُ العمر لا يُنهي «الخمول»: يُقاس ما رُسم
        pass
    page.wait_for_timeout(150)
    entry: dict = {"status": response.status if response else None}
    entry["overflow_px"] = page.evaluate(OVERFLOW_JS)
    small = page.evaluate(SMALL_TARGETS_JS, 44)
    entry["small_targets"] = len(small)
    entry["small_sample"] = small[:3]
    entry["positive_tabindex"] = page.evaluate(POSITIVE_TABINDEX_JS)
    entry["axe"] = ratchet.measure_page(page)
    return entry


def test_the_whole_admin_is_clean_on_a_phone_in_both_themes(
    page, live_server, school, developer_user
):
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.save()
    page.set_viewport_size({"width": 375, "height": 812})
    _login(page, live_server, developer_user)
    paths = admin_paths()
    report: dict = {"paths": len(paths), "pages": {}}
    problems: dict[str, str] = {}
    for theme in ("light", "dark"):
        page.goto(f"{live_server.url}/admin/")
        page.evaluate(f"localStorage.setItem('theme', '{theme}')")
        for path in paths:
            started = time.time()
            key = f"{theme} {path}"
            entry = _measure(page, live_server, path)
            entry["secs"] = round(time.time() - started, 1)
            report["pages"][key] = entry
            found = []
            if entry["status"] not in (200, 403):
                found.append(f"حالةٌ {entry['status']}")
            if entry["overflow_px"] > 0:
                found.append(f"تجاوزٌ أفقيّ {entry['overflow_px']}px")
            if entry["small_targets"]:
                found.append(
                    f"{entry['small_targets']} هدفَ لمسٍ دون 44px مثل {entry['small_sample']}"
                )
            if entry["positive_tabindex"]:
                found.append("tabindex موجب")
            if entry["axe"]:
                found.append(f"axe {entry['axe']}")
            if found:
                problems[key] = "؛ ".join(found)

    out = os.environ.get("ADMIN_SWEEP_OUT")
    if out:
        pathlib.Path(out).write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    shown = "\n  ".join(f"{k}: {v}" for k, v in list(problems.items())[:25])
    assert not problems, f"{len(problems)} من {len(report['pages'])} صفحةً فيها مخالفة:\n  {shown}"
