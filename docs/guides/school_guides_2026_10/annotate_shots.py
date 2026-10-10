"""يصوّر شاشاتِ دليلَي «المعلّم» و«مشرف الجناح» من الخادم التجريبيّ (`run_demo_server.py` + `seed_demo.py`)
ويرسم عليها إطاراتٍ برتقاليّةً وأرقاماً.

    python docs/guides/school_guides_2026_10/annotate_shots.py teacher
    python docs/guides/school_guides_2026_10/annotate_shots.py wing

الأرقامُ تُرسَم في الصفحة نفسِها قبل اللقطة فتتبع مواضعَ العناصر الفعليّة. وما لم يُوجَد عنصرُه يُطبَع تحذيراً ولا تُرسَم له علامة.
"""

import pathlib
import sys

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
BASE = "http://127.0.0.1:8765"
OVERLAY_JS = (HERE / "overlay.js").read_text(encoding="utf-8")
PASSWORD = "Demo-Pass-2026!"  # pragma: allowlist secret
NOW_ISO = "2026-10-05T09:20:00+03:00"  # ساعةُ المتصفّح كساعة الخادم التجريبيّ (احتساب دقائق التأخّر)
FULL_W = 1280
OUT = HERE / "shots"


def rects(page, marks):
    items = []
    for mark in marks:
        n, selector = mark[0], mark[1]
        opts = mark[2] if len(mark) > 2 else {}
        try:
            box = page.locator(selector).first.bounding_box(timeout=2500)
        except Exception:
            box = None
        if not box:
            print(f"  ⚠ لا عنصر لـ {n}: {selector}")
            continue
        items.append(
            {
                "n": n,
                "rect": {"x": box["x"], "y": box["y"], "w": box["width"], "h": box["height"]},
                **opts,
            }
        )
    return items


def shoot(page, folder, name, marks=(), clip=None, full=True):
    page.wait_for_timeout(700)
    page.evaluate(OVERLAY_JS, rects(page, list(marks)))
    path = str(OUT / folder / f"{name}.png")
    if clip:
        page.screenshot(path=path, clip=clip, full_page=True)
    else:
        page.screenshot(path=path, full_page=full)
    page.evaluate("document.querySelectorAll('.__mk').forEach(e => e.remove())")
    print("✓", folder, name)


def goto(page, path):
    page.goto(BASE + path)
    page.wait_for_load_state("networkidle")


def login(page, number):
    goto(page, "/auth/login/")
    page.fill("#id_identifier", number)
    page.fill("#id_password", PASSWORD)
    page.click("button.login-btn")
    page.wait_for_load_state("networkidle")


def nav(label):
    return f"nav .nb:has-text('{label}')"


def clip(y, height, x=0, width=FULL_W):
    return {"x": x, "y": y, "width": width, "height": height}


def main_clip(h, y=100):
    return clip(y, h)


def teacher(browser):
    folder = "teacher"
    (OUT / folder).mkdir(parents=True, exist_ok=True)
    page = browser.new_context(
        viewport={"width": FULL_W, "height": 900}, locale="ar", reduced_motion="reduce"
    ).new_page()
    page.clock.install(time=NOW_ISO)

    goto(page, "/auth/login/")
    shoot(
        page,
        folder,
        "01_login",
        [(1, "#id_identifier"), (2, "#id_password"), (3, "button.login-btn")],
        clip=None,
        full=False,
    )
    login(page, "70001")

    shoot(
        page,
        folder,
        "02_nav",
        [
            (1, nav("الرئيسية"), {"at": "bottom"}),
            (2, nav("مركز معلومات الطلبة"), {"at": "bottom"}),
            (3, nav("جدولي"), {"at": "bottom"}),
            (4, nav("الزيارات الصفية"), {"at": "bottom"}),
            (5, nav("التقييمات"), {"at": "bottom"}),
            (6, nav("التقارير"), {"at": "bottom"}),
            (7, nav("إجراءاتي"), {"at": "bottom"}),
            (8, nav("السلوك"), {"at": "bottom"}),
            (9, nav("الإدارة"), {"at": "bottom"}),
            (10, nav("رسائل المطوّر"), {"at": "bottom"}),
        ],
        clip=clip(0, 130),
    )

    goto(page, "/dashboard/")
    shoot(
        page,
        folder,
        "03_dashboard",
        [
            (1, "section.ui-section:has(h2:has-text('رصدُ الغياب'))"),
            (2, "main a:has-text('شُعبي للرصد')"),
            (3, ".action-card:has-text('تسجيل سلوك')"),
        ],
        clip=main_clip(330),
    )

    goto(page, "/teacher/classes/")
    shoot(
        page,
        folder,
        "04_classes",
        [
            (1, "section.ui-section:has(h2:has-text('شُعب إسنادك'))"),
            (2, "li.pp-class >> nth=0 >> .pp-class__info"),
            (3, "li.pp-class >> nth=0 >> button"),
        ],
        clip=main_clip(300),
    )

    class_href = (
        page.locator("li.pp-class form").first.get_attribute("action").replace("period/", "")
    )
    goto(page, class_href)
    shoot(
        page,
        folder,
        "05_picker",
        [
            (1, "nav.per-tabs"),
            (2, "button.per-tab.is-past >> nth=0"),
            (3, "button.per-tab.is-current"),
            (4, "button.per-tab.is-future >> nth=0"),
        ],
        clip=main_clip(260),
    )

    with page.expect_navigation():
        page.locator("button.per-tab.is-current").click()
    page.wait_for_load_state("networkidle")
    shoot(
        page,
        folder,
        "06_sheet",
        [
            (1, ".per-head"),
            (2, "text=الكلُّ حاضر >> nth=0"),
            (3, "text=ثبّتِ الحصّة >> nth=0"),
        ],
        clip=main_clip(660),
    )
    page.locator("label:has-text('غائب')").nth(1).click()
    page.locator("label:has-text('متأخّر')").nth(2).click()
    page.locator("button:has-text('خروج')").nth(4).click()
    page.wait_for_timeout(600)
    shoot(page, folder, "06b_states", clip=main_clip(640))
    page.keyboard.press("Escape")

    goto(page, "/teacher/schedule/")
    shoot(
        page,
        folder,
        "07_schedule",
        [
            (1, "main a:has-text('شُعبي للرصد')"),
            (2, "main input[type=date]"),
            (3, "main :text('طلبات التبديل') >> nth=0"),
        ],
        clip=main_clip(360),
    )

    goto(page, "/behavior/report/")
    shoot(
        page,
        folder,
        "08_behavior",
        [
            (1, "input[placeholder*='ابحث في المخالفات']"),
            (2, ".beh-vitem >> nth=0", {"at": "right"}),
            (3, "input[placeholder*='ابحث باسم الطالب']"),
            (4, "main select.form-control >> nth=2"),
            (5, "button:has-text('تسجيل المخالفة')"),
        ],
        clip=main_clip(740),
    )

    goto(page, "/student-info/")
    page.locator("a[href*='/student-info/section/']").first.click()
    page.wait_for_load_state("networkidle")
    shoot(page, folder, "09_section", clip=main_clip(620))
    page.locator("a[href*='/student-info/student/']").first.click()
    page.wait_for_load_state("networkidle")
    shoot(
        page,
        folder,
        "09b_student",
        [
            (1, "a:has-text('إضافة ملاحظة')"),
            (2, "a:has-text('رجوع للشعبة')"),
            (3, "section.ui-section:has(h2:has-text('ملاحظات المعلمين'))"),
        ],
        clip=main_clip(720),
    )

    goto(page, "/teacher/weekly-schedule/?view=teacher")
    shoot(page, folder, "10_weekly", clip=main_clip(420))

    for name, path, height in (
        ("11_reports", "/reports/", 420),
        ("12_procedures", "/quality/my-procedures/", 420),
        ("13_permits", "/staff-affairs/permits/mine/", 900),
        ("14_notifications", "/notifications/inbox/", 420),
        ("15_password", "/auth/change-password/", 560),
    ):
        goto(page, path)
        shoot(page, folder, name, clip=main_clip(height))

    goto(page, "/dashboard/")
    page.locator("header.site-header button:has-text('أحمد')").first.click()
    shoot(page, folder, "02b_user_menu", clip=clip(0, 330, 0, 640))


def wing(browser):
    folder = "wing"
    (OUT / folder).mkdir(parents=True, exist_ok=True)
    page = browser.new_context(
        viewport={"width": FULL_W, "height": 900}, locale="ar", reduced_motion="reduce"
    ).new_page()
    page.clock.install(time=NOW_ISO)
    login(page, "70003")

    def calm():
        page.mouse.move(640, 700)
        page.wait_for_timeout(300)

    def menu_href(label):
        """رابطُ بندٍ في القائمة المنسدلة بالنصّ بلا تشكيل (البنودُ المنسدلةُ مخفيّةٌ فلا يجدها محدِّدُ النصّ المرئيّ)."""
        return page.evaluate(
            """label => {
                const strip = t => t.normalize('NFD').replace(/[\\u064B-\\u065F\\u0670\\u0640]/g, '').replace(/\\s+/g, ' ');
                const a = [...document.querySelectorAll('a')].find(el => strip(el.textContent).includes(label));
                return a ? a.getAttribute('href') : null;
            }""",
            label,
        )

    hrefs = {
        name: menu_href(name)
        for name in (
            "بحث عن طالب",
            "لوحة سلوك الجناح",
            "غياب اليوم",
            "تحركات الطلبة",
            "التأخر الصباحي",
            "الإشعارات",
        )
    }
    print("  روابط القائمة:", hrefs)

    shoot(
        page,
        folder,
        "02_nav",
        [
            (1, nav("الرئيسية"), {"at": "bottom"}),
            (2, nav("رصد الغياب"), {"at": "bottom"}),
            (3, nav("طلبة جناحي"), {"at": "bottom"}),
            (4, nav("مركز معلومات الطلبة"), {"at": "bottom"}),
            (5, nav("أجنحة المدرسة"), {"at": "bottom"}),
            (6, nav("الإشعارات"), {"at": "bottom"}),
            (7, nav("رسائل المطوّر"), {"at": "bottom"}),
        ],
        clip=clip(0, 130),
    )
    page.locator("nav .nb:has-text('طلبة جناحي')").first.hover()
    page.wait_for_timeout(500)
    shoot(page, folder, "02b_menu", clip=clip(0, 330, 0, 900))

    goto(page, "/dashboard/")
    calm()
    shoot(
        page,
        folder,
        "03_dashboard",
        [
            (1, "main a:has-text('رصد الغياب')"),
            (2, "main a:has-text('رصد المعلّمين')"),
            (3, "main input[type=search], main input[type=text] >> nth=0"),
            (4, "main section.ui-section >> nth=0"),
            (5, "section.ui-section:has-text('ينتظرون') >> nth=0"),
            (6, "section.ui-section:has-text('عند عتبات') >> nth=0"),
        ],
        clip=main_clip(780),
    )
    page.locator("main :text('تصدير') >> nth=0").click()
    page.wait_for_timeout(500)
    shoot(page, folder, "03b_export", clip=main_clip(420))
    page.keyboard.press("Escape")

    goto(page, "/wings/record/")
    calm()
    shoot(
        page,
        folder,
        "04_record",
        [
            (1, "main input[type=date]"),
            (2, "main :text('تصدير') >> nth=0"),
            (3, "main :text('11.2') >> nth=0"),
            (4, "main :text('11.4') >> nth=0"),
        ],
        clip=main_clip(560),
    )

    page.locator("main :text('11.1') >> nth=0").click()
    page.wait_for_load_state("networkidle")
    calm()
    sheet_url = page.url
    shoot(
        page,
        folder,
        "05_sheet",
        [
            (1, ".per-head"),
            (2, "text=اعتمادُ الكلّ >> nth=0"),
            (3, "text=الكلُّ حاضر >> nth=0"),
            (4, "text=المعلّم: غائب >> nth=0"),
            (5, "text=ثبّتِ الحصّة >> nth=0"),
        ],
        clip=main_clip(900),
    )
    page.locator("button:has-text('خروج')").nth(3).click()
    page.wait_for_timeout(600)
    shoot(page, folder, "06_exit", clip=main_clip(520))
    page.keyboard.press("Escape")
    page.goto(sheet_url)
    page.wait_for_load_state("networkidle")
    page.locator("a:has-text('تصحيح')").first.click()
    page.wait_for_load_state("networkidle")
    shoot(page, folder, "06c_correct", clip=main_clip(620))

    goto(page, "/teacher/attendance/approvals/")
    calm()
    shoot(
        page,
        folder,
        "07_approvals",
        [
            (1, "main :text('اعتماد الكلّ'), main :text('اعتمادُ الكلّ') >> nth=0"),
            (2, "main button:has-text('اعتماد') >> nth=1"),
            (3, "main button:has-text('رفض') >> nth=0"),
        ],
        clip=main_clip(620),
    )

    goto(page, "/dashboard/")
    page.locator("a:has-text('ملفُّ الغياب')").first.click()
    page.wait_for_load_state("networkidle")
    calm()
    shoot(
        page,
        folder,
        "08_absence",
        [
            (1, "text=/بلا عذر/ >> nth=0"),
            (2, "text=/والد/ >> nth=0"),
            (3, "text=/غائب.? بلا عذر/ >> nth=0"),
            (4, "main details.af-act summary >> nth=1"),
            (5, "main details.af-act summary.btn-primary >> nth=1"),
        ],
        clip=main_clip(900),
    )
    page.locator("main details.af-act summary").nth(1).click()
    page.wait_for_timeout(700)
    shoot(page, folder, "08b_call", clip=main_clip(900))
    page.locator("main details.af-act summary").nth(1).click()
    page.locator("main details.af-act summary.btn-primary").nth(1).click()
    page.wait_for_timeout(700)
    shoot(page, folder, "08c_excuse", clip=main_clip(1100))

    goto(page, hrefs["بحث عن طالب"])
    shoot(page, folder, "11_find", clip=main_clip(420))
    goto(page, hrefs["غياب اليوم"])
    calm()
    shoot(page, folder, "09_daily", clip=main_clip(660))
    goto(page, hrefs["لوحة سلوك الجناح"])
    shoot(page, folder, "12_behavior", clip=main_clip(560))
    goto(page, "/notifications/inbox/")
    shoot(page, folder, "13_notifications", clip=main_clip(420))
    goto(page, "/wings/")
    calm()
    shoot(page, folder, "10_floors", clip=main_clip(640))
    goto(page, "/auth/change-password/")
    shoot(page, folder, "15_password", clip=main_clip(560))


def run():
    which = sys.argv[1] if len(sys.argv) > 1 else "teacher"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        {"teacher": teacher, "wing": wing}[which](browser)
        browser.close()


if __name__ == "__main__":
    run()
