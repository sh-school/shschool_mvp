"""[Q-06 / K23] WCAG 2.2 على الجوال — حرّاسٌ ساكنةٌ للمعايير الخمسة وللمعيار 4.1.3.

المراجعةُ الموثَّقة في `docs/wcag22_mobile_review_2026-09.md` (ما قيس وكيف وما بقي)؛ وهذا الملفُّ يمنع
عودةَ ما أُصلح ويُسجّل ما اعتُبر مستثنىً بعلّته:

- **2.4.11 (الثابتُ لا يحجب المركَّز):** `html { scroll-padding-block }` بارتفاع الترويسة والشريط اللاصقَين
  فأعلى، والشريطِ السفليّ فأسفل (على اللمس)؛ ورأسُ الجدول اللاصق داخل حاويةٍ تُمرَّر يعالجه `focusin` في `base.js`.
- **1.4.10 (التدفّق):** لا يُمنع التكبير في وسم `viewport` (وإلّا استحال 400%)؛ والفيضُ الأفقيّ محروسٌ في `mobile_audit`.
- **1.4.12 (تباعد النصّ):** ما يقصّه `line-clamp` مقصودٌ (معاينةٌ) وقائمتُه معلومة — جديدٌ يُراجَع.
- **3.3.8 (المصادقة):** لا اختبارَ معرفيّ، والصقُ وملءُ مدير كلمات المرور مسموحان، ورمزُ التحقّق يُلصق كما يُعرَض.
- **2.5.7 (السحب):** كلُّ استعمالٍ للسحب أو التمرير باللمس له بديلٌ بنقرة؛ والجديدُ يُدرج في القائمة بعلّته.
- **4.1.3 (رسائل الحالة):** `role="alert"` للخطأ والتحذير وحدَهما، و`status` لما سواهما.
"""

import re
from pathlib import Path

from tests.css_contrast import iter_rules
from tests.css_source import read_css

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = sorted((ROOT / "templates").rglob("*.html"))
#: سكربتاتُ المنصّة نفسِها لا المكتبات (`vendor/` و`*.min.js`).
SCRIPTS = [
    p for p in sorted((ROOT / "static" / "js").glob("*.js")) if not p.name.endswith(".min.js")
]
BASE_JS = (ROOT / "static/js/base.js").read_text(encoding="utf-8")
BASE_HTML = (ROOT / "templates/base/base.html").read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _rules(selector: str):
    return [
        (decls, ctx)
        for sel, decls, ctx in iter_rules(read_css())
        if " ".join(sel.split()) == selector
    ]


def _px(selector: str, prop: str) -> int:
    for decls, _ctx in _rules(selector):
        m = re.fullmatch(r"(\d+)px", decls.get(prop, "").strip())
        if m:
            return int(m.group(1))
    raise AssertionError(f"{selector} بلا {prop} بالبكسل")


# ── 2.4.11 ────────────────────────────────────────────────────────────────


def test_scroll_padding_clears_the_sticky_header_and_nav():
    """الترويسةُ 48px وحدُّها 1px والشريطُ 42px: 91px — وإلّا بقي المركَّزُ تحتها ولم يمرّر المتصفّح."""
    header = _px(".site-header .nav-inner", "height")
    nav = _px(".nav-inner", "height")
    border = int(re.search(r"(\d+)px", _rules(".site-header")[0][0]["border-bottom"]).group(1))
    top_rules = [
        d["scroll-padding-block"] for d, _c in _rules("html") if "scroll-padding-block" in d
    ]
    assert top_rules, "html بلا scroll-padding-block"
    value = " ".join(top_rules[0].split())
    m = re.match(r"calc\(var\(--safe-top\) \+ (\d+)px\) (.+)$", value)
    assert m, value
    assert (
        int(m.group(1)) == header + border + nav
    ), f"ارتفاعُ الثابت العلويّ {header}+{border}+{nav} لا {m.group(1)} — حدِّث القاعدتَين معاً"
    assert m.group(2) == "calc(var(--dock-h) + var(--dock-pad) + var(--sp-2))", m.group(2)


def test_the_bottom_padding_is_dropped_where_the_dock_is_hidden():
    """الشريطُ السفليّ مخفيٌّ من 641px، فلا يُترك تحته حشوةُ تمريرٍ بلا سبب."""
    hidden_from = [
        c for d, c in _rules(".mobile-bottom-nav") if d.get("display", "").strip() == "none"
    ]
    assert hidden_from and any("min-width: 641px" in h for h in hidden_from[0])
    ends = [c for d, c in _rules("html") if d.get("scroll-padding-block-end", "").strip() == "0"]
    assert ends and any(
        "min-width: 641px" in h for h in ends[0]
    ), "لا إلغاءَ للحشوة السفلى عند 641px"


def test_no_scroll_margin_double_counts_the_sticky_stack():
    """`scroll-margin` يُجمع إلى `scroll-padding`: قيمةٌ كبيرةٌ تنزل بالهدف مئاتِ البكسلات (كان `.af-day` بـ140px)."""
    for sel, decls, _ctx in iter_rules(read_css()):
        for prop, value in decls.items():
            if prop.startswith("scroll-margin"):
                m = re.fullmatch(r"(\d+)px", value.strip())
                assert not m or int(m.group(1)) < 91, f"{sel} {prop}: {value}"


def test_a_sticky_table_head_inside_a_scroller_does_not_hide_the_focused_row():
    """داخل `.table-wrap-scroll` يعدّ المتصفّحُ ما تحت `th` اللاصق ظاهراً؛ فالمعالجُ في `base.js` يرفع الصفّ."""
    m = re.search(r"addEventListener\('focusin'.*?\n\}\);", BASE_JS, re.S)
    assert m, "معالجُ focusin لرأس الجدول اللاصق غيرُ موجود"
    body = m.group(0)
    assert "thead th" in body and "'sticky'" in body and "scrollTop" in body


# ── 1.4.10 / 1.4.12 ───────────────────────────────────────────────────────


def test_no_viewport_meta_blocks_zoom():
    """400% تكبيرٌ = 320px؛ ومن منع التكبير قطع الطريقَ على من يعتمد عليه (1.4.4 و1.4.10)."""
    for path in TEMPLATES:
        for tag in re.findall(
            r"<meta[^>]*name=\"viewport\"[^>]*>", path.read_text(encoding="utf-8")
        ):
            assert "user-scalable" not in tag and "maximum-scale" not in tag, f"{_rel(path)}: {tag}"


#: ما يقصّه `line-clamp` معاينةٌ مقصودةٌ نصُّها الكاملُ في الصفحة أو الرابط — ولا يفقد محتوىً بتباعد النصّ (1.4.12).
LINE_CLAMPS = {".notif-item__body", ".grid-cell__name", ".rm-clamp", ".rm-tile p.rm-clamp"}


def test_line_clamps_are_the_known_previews():
    found = {
        " ".join(sel.split())
        for sel, decls, _ctx in iter_rules(read_css())
        if "-webkit-line-clamp" in decls or "line-clamp" in decls
    }
    assert (
        found <= LINE_CLAMPS
    ), f"قصٌّ جديدٌ بـ line-clamp — راجِعه ثمّ أدرجه: {sorted(found - LINE_CLAMPS)}"


# ── 3.3.8 ─────────────────────────────────────────────────────────────────


def _input_tags(text: str):
    return re.findall(r"<input\b[^>]*>", text, re.S)


def test_every_password_field_can_be_filled_by_a_password_manager():
    for path in TEMPLATES:
        for tag in _input_tags(path.read_text(encoding="utf-8")):
            if re.search(r"type=\"password\"", tag):
                assert re.search(
                    r"autocomplete=\"(current|new)-password\"", tag
                ), f"{_rel(path)}: {tag[:90]}"


def test_the_login_form_names_its_fields_for_autofill():
    login = (ROOT / "templates/auth/login.html").read_text(encoding="utf-8")
    assert 'autocomplete="username"' in login and 'autocomplete="current-password"' in login


def test_the_verification_code_accepts_a_pasted_code_with_its_space():
    """التطبيقُ يعرض الرمزَ «123 456»؛ و`maxlength=6` كان يقصّ اللصقَ ويُفشل التحقّقَ قبل الخادم."""
    for name in ("verify_2fa", "setup_2fa", "disable_2fa"):
        text = (ROOT / f"templates/auth/{name}.html").read_text(encoding="utf-8")
        tags = [t for t in _input_tags(text) if "one-time-code" in t]
        assert len(tags) == 1, name
        assert 'maxlength="7"' in tags[0] and 'inputmode="numeric"' in tags[0], f"{name}: {tags[0]}"


def test_no_field_blocks_paste_and_no_captcha_is_used():
    pieces = [(_rel(p), p.read_text(encoding="utf-8")) for p in TEMPLATES + SCRIPTS]
    for name, text in pieces:
        assert not re.search(r"onpaste|['\"]paste['\"]", text), f"{name}: حجبُ لصقٍ"
        assert not re.search(r"re?captcha|hcaptcha|turnstile", text, re.I), f"{name}: اختبارٌ معرفيّ"
    for req in sorted(ROOT.glob("requirements*.txt")):
        assert not re.search(r"captcha|turnstile", req.read_text(encoding="utf-8"), re.I), req.name


# ── 2.5.7 ─────────────────────────────────────────────────────────────────

#: كلُّ ما في المنصّة من سحبٍ أو تمريرٍ باللمس أو مزلاج، وبديلُه بنقرةٍ واحدةٍ. جديدٌ يُدرج هنا بعلّته أو يسقط.
DRAG_MARKERS = re.compile(
    r"draggable\s*=|dragstart|dragover|ondrop|['\"]drop['\"]|touchmove|touchstart|pointermove|type=\"range\""
)
DRAG_ALTERNATIVES = {
    "templates/components/file_upload.html": "منطقةُ إسقاط الملف — زرُّ «اختر ملفًا» بجانبها",
    "static/js/app.js": "التمريرُ يساراً على إشعارٍ يعني «مقروء» — وزرُّ «مقروء» في الصفّ",
    "templates/quality/evaluation_form.html": "مزلاجٌ أصليٌّ `input[type=range]`: لوحةُ المفاتيح والنقرُ على المسار — وهو من عمل المتصفّح",
}


def test_every_drag_or_swipe_has_a_single_pointer_alternative():
    users = {
        _rel(p) for p in TEMPLATES + SCRIPTS if DRAG_MARKERS.search(p.read_text(encoding="utf-8"))
    }
    assert (
        users <= set(DRAG_ALTERNATIVES)
    ), f"سحبٌ أو تمريرٌ جديدٌ بلا بديل (WCAG 2.5.7) — أضِف بديلاً بنقرةٍ ثمّ أدرجه: {sorted(users - set(DRAG_ALTERNATIVES))}"


def test_the_known_alternatives_are_still_there():
    upload = (ROOT / "templates/components/file_upload.html").read_text(encoding="utf-8")
    assert re.search(r"<button[^>]*data-click=\"#file-input-", upload)
    item = (ROOT / "templates/notifications/partials/notif_item.html").read_text(encoding="utf-8")
    assert 'class="notif-item__read"' in item


# ── 4.1.3 ─────────────────────────────────────────────────────────────────


def test_a_floating_toast_uses_alert_only_for_errors_and_warnings():
    assert re.search(
        r"setAttribute\('role',\s*type === 'danger' \|\| type === 'warning' \? 'alert' : 'status'\)",
        BASE_JS,
    ), "دورُ الإشعار العائم يجب أن يتبع نوعَه"
    assert "setAttribute('role', 'alert')" not in BASE_JS, "alert لكلّ إشعارٍ حتى النجاح يقاطع القارئ"


def test_the_toast_container_does_not_reread_every_toast():
    """`aria-atomic=true` على حاويةٍ حيّةٍ يُعيد قراءةَ كلّ ما فيها كلَّما أُضيف إشعار."""
    tag = re.search(r"<div id=\"toast-container\"[^>]*>", BASE_HTML)
    assert tag and 'aria-atomic="false"' in tag.group(0), tag and tag.group(0)


def test_every_message_bar_has_a_status_role():
    for path in TEMPLATES:
        for tag in re.findall(
            r"<div[^>]*class=\"[^\"]*\bmsg-bar\b[^\"]*\"[^>]*>", path.read_text(encoding="utf-8")
        ):
            assert "role=" in tag, f"{_rel(path)}: رسالةٌ بلا role — {tag[:100]}"


def test_no_element_declares_alert_with_a_polite_live_region():
    """`role=alert` ضمنيُّه assertive؛ و`aria-live=polite` معه تناقضٌ يُخفّض الخطأ."""
    for path in TEMPLATES:
        for tag in re.findall(r"<[a-z][^>]*role=\"alert\"[^>]*>", path.read_text(encoding="utf-8")):
            assert 'aria-live="polite"' not in tag, f"{_rel(path)}: {tag[:100]}"
