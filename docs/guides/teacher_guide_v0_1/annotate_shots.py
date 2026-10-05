"""يصوّر شاشاتِ «دليل المعلّم» من الخادم التجريبيّ (`run_demo_server.py`) ويرسم عليها أرقاماً وإطاراتٍ برتقاليّة.

    python docs/guides/teacher_guide_v0_1/annotate_shots.py

الأرقامُ تُرسَم في الصفحة نفسِها قبل اللقطة (لا برنامجُ رسمٍ خارجيّ)، فتتبع مواضعَ العناصر الفعليّة. وما لم يُوجَد عنصرُه يُطبَع تحذيراً ولا تُرسَم له علامة.
"""

import pathlib
import sys

from playwright.sync_api import sync_playwright

OUT = pathlib.Path(__file__).parent / "shots"
BASE = "http://127.0.0.1:8765"
IDS = {  # من ناتج seed_demo.py
    "setup": "03620a82-2e73-4bb7-be80-305e6c0b8131",
    "quiz": "c8ae6bbc-64e6-493e-ba5b-42d0ce98eed5",
}

OVERLAY_JS = """
(items) => {
  document.querySelectorAll('.__mk').forEach(e => e.remove());
  const sx = window.scrollX, sy = window.scrollY;
  for (const it of items) {
    const r = it.rect, pad = it.pad ?? 3;
    if (!it.noframe) {
      const f = document.createElement('div'); f.className = '__mk';
      f.style.cssText = `position:absolute;z-index:99998;pointer-events:none;border:3px solid #F2A900;border-radius:8px;` +
        `left:${r.x + sx - pad}px;top:${r.y + sy - pad}px;width:${r.w + 2*pad}px;height:${r.h + 2*pad}px;box-sizing:border-box;`;
      document.body.appendChild(f);
    }
    const b = document.createElement('div'); b.className = '__mk'; b.textContent = it.n;
    let left = r.x + sx + r.w - 13, top = r.y + sy - 15;
    if (it.at === 'bottom') { left = r.x + sx + r.w / 2 - 13; top = r.y + sy + r.h + 4; }
    if (it.at === 'left') { left = r.x + sx - 16; top = r.y + sy + r.h / 2 - 13; }
    if (it.at === 'right') { left = r.x + sx + r.w - 10; top = r.y + sy + r.h / 2 - 13; }
    b.style.cssText = `position:absolute;z-index:99999;left:${left}px;top:${top}px;width:26px;height:26px;border-radius:50%;` +
      `background:#F2A900;color:#3b2a00;font:700 15px/26px Tajawal,sans-serif;text-align:center;border:2px solid #fff;` +
      `box-shadow:0 1px 4px rgba(0,0,0,.35);`;
    document.body.appendChild(b);
  }
}
"""


def rects(page, marks):
    items = []
    for mark in marks:
        n, selector = mark[0], mark[1]
        opts = mark[2] if len(mark) > 2 else {}
        loc = page.locator(selector).first
        try:
            box = loc.bounding_box(timeout=2500)
        except Exception:
            box = None
        if not box:
            print(f"  ⚠ لا عنصر لـ {n}: {selector}")
            continue
        scroll = page.evaluate("[window.scrollX, window.scrollY]")
        items.append(
            {
                "n": n,
                "rect": {
                    "x": box["x"] - scroll[0] + scroll[0],
                    "y": box["y"],
                    "w": box["width"],
                    "h": box["height"],
                },
                **opts,
            }
        )
    return items


def shoot(page, name, marks=(), clip=None, full=True, element=None):
    page.wait_for_timeout(700)
    page.evaluate(OVERLAY_JS, rects(page, list(marks)))
    path = str(OUT / f"{name}.png")
    if element:
        page.locator(element).first.screenshot(path=path)
    elif clip:
        page.screenshot(path=path, clip=clip, full_page=True)
    else:
        page.screenshot(path=path, full_page=full)
    page.evaluate("document.querySelectorAll('.__mk').forEach(e => e.remove())")
    print("✓", name)


def goto(page, path):
    page.goto(BASE + path)
    page.wait_for_load_state("networkidle")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ar",
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        page = ctx.new_page()

        # 1) الدخول
        goto(page, "/auth/login/")
        shoot(
            page,
            "01_login",
            [(1, "#id_identifier"), (2, "#id_password"), (3, "button.login-btn")],
            element="form",
        )
        page.fill("#id_identifier", "70001")
        page.fill("#id_password", "Demo-Pass-2026!")
        page.click("button.login-btn")
        page.wait_for_load_state("networkidle")

        # 2) الواجهة (الشريط العلويّ والقائمة)
        def nav(label):
            return f"nav .nb:has-text('{label}')"

        shoot(
            page,
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
                (9, nav("رسائل المطوّر"), {"at": "bottom"}),
                (10, nav("الإدارة"), {"at": "bottom"}),
            ],
            clip={"x": 0, "y": 0, "width": 1280, "height": 130},
        )

        # 3) اللوحة الرئيسية
        goto(page, "/dashboard/")
        shoot(
            page,
            "03_dashboard",
            [
                (1, "section.ui-section:has(h2:has-text('حصصي اليوم'))"),
                (2, "text=التالية", {"at": "left"}),
                (
                    3,
                    "section.ui-section:has(h2:has-text('حصصي اليوم')) a:has-text('عرض الحضور') >> nth=0",
                ),
                (4, "section.ui-section:has(h2:has-text('موادّ التقييم'))"),
                (5, ".action-card:has-text('الجدول الأسبوعي')"),
            ],
            clip={"x": 0, "y": 100, "width": 1280, "height": 700},
        )

        # 4) حصصي اليوم
        goto(page, "/teacher/schedule/")
        shoot(
            page,
            "04_schedule",
            [
                (1, "input[type=date]"),
                (2, "main a:has-text('طلبات التبديل')"),
                (3, "main a:has-text('الحصص التعويضية')"),
                (4, "section.ui-section:has(h2:has-text('الحصة القادمة'))"),
                (5, "section.ui-section:has(h2:has-text('الحصص')) table"),
            ],
            clip={"x": 0, "y": 100, "width": 1280, "height": 560},
        )

        # 5) كشف الحصة
        row = page.locator("tr", has_text="07:10").locator("a[href*='/teacher/attendance/']").first
        href = row.get_attribute("href")
        goto(page, href)
        shoot(
            page,
            "05_attendance",
            [
                (1, ".per-head >> nth=0"),
                (2, "[data-bulk=present]"),
                (3, "tr.rec-row >> nth=0"),
                (4, "[data-exit-open] >> nth=0"),
                (5, "xpath=(//*[contains(text(),'متأخّر')])[last()]/.."),
                (6, "text=ثبّتِ الحصّة"),
            ],
            clip={"x": 0, "y": 100, "width": 1280, "height": 700},
        )
        # حالاتٌ مختلفة على الكشف نفسه
        page.locator("label.rec-pick--absent").nth(1).click()
        page.locator("label.rec-pick--late").nth(2).click()
        page.locator("[data-exit-open]").nth(4).click()
        page.wait_for_timeout(500)
        shoot(
            page, "05b_attendance_states", [], clip={"x": 0, "y": 280, "width": 1280, "height": 560}
        )
        page.keyboard.press("Escape")

        # 6) التقييمات
        goto(page, "/assessments/")
        shoot(
            page,
            "06_assessments",
            [
                (1, "select"),
                (2, "input[type=search], input[type=text] >> nth=0"),
                (3, "section.ui-section a:has-text('كشف الدرجات')"),
            ],
            clip={"x": 0, "y": 100, "width": 1280, "height": 400},
        )
        goto(page, f"/assessments/setup/{IDS['setup']}/")
        shoot(
            page,
            "06b_setup",
            [
                (1, "a:has-text('كشف الدرجات') >> nth=0"),
                (2, "text=الفصل الأول (40 درجة)"),
                (3, "text=P1"),
                (4, "a:has-text('إدخال الدرجات')"),
                (5, "text=إضافة تقييم"),
            ],
            clip={"x": 0, "y": 100, "width": 1280, "height": 700},
        )
        goto(page, f"/assessments/assessment/{IDS['quiz']}/")
        inputs = page.locator("input[name=grade], input[type=number]")
        for index, value in enumerate(["18", "15", "12", "17", "20"]):
            inputs.nth(index).fill(value)
        shoot(
            page,
            "06c_grade_entry",
            [
                (1, "input[placeholder*='بحث']"),
                (2, "input[name=grade], input[type=number] >> nth=0"),
                (3, "input[type=checkbox] >> nth=0"),
                (4, "input[type=checkbox] >> nth=1"),
                (5, "button:has-text('حفظ') >> nth=0"),
                (6, "button:has-text('حفظ الكل')"),
            ],
            clip={"x": 0, "y": 100, "width": 1280, "height": 1000},
        )

        # 7) السلوك
        goto(page, "/behavior/report/")
        shoot(
            page,
            "07_behavior",
            [
                (1, "input[placeholder*='ابحث في المخالفات']"),
                (2, ".beh-vitem >> nth=0", {"at": "right"}),
                (3, "input[placeholder*='ابحث باسم الطالب']"),
                (4, "main select.form-control >> nth=2"),
                (5, "button:has-text('تسجيل المخالفة')"),
            ],
            clip={"x": 0, "y": 100, "width": 1280, "height": 740},
        )

        # 8) مركز معلومات الطلبة
        goto(page, "/student-info/")
        page.locator("a[href*='/student-info/section/']").first.click()
        page.wait_for_load_state("networkidle")
        shoot(page, "08_section", [], clip={"x": 0, "y": 100, "width": 1280, "height": 720})
        page.locator("a[href*='/student-info/student/']").first.click()
        page.wait_for_load_state("networkidle")
        shoot(
            page,
            "08b_student",
            [
                (1, "a:has-text('إضافة ملاحظة')"),
                (2, "a:has-text('رجوع للشعبة')"),
                (3, "section.ui-section:has(h2:has-text('ملاحظات المعلمين'))"),
            ],
            clip={"x": 0, "y": 100, "width": 1280, "height": 720},
        )

        # 9) جدولي
        goto(page, "/teacher/weekly-schedule/?view=teacher")
        shoot(
            page,
            "09_weekly",
            [(1, "text=الأسبوع التالي"), (2, "text=تصدير PDF"), (3, "table")],
            clip={"x": 0, "y": 100, "width": 1280, "height": 480},
        )
        goto(page, "/teacher/schedule/swaps/")
        shoot(page, "09b_swaps", [], clip={"x": 0, "y": 100, "width": 1280, "height": 480})
        goto(page, "/teacher/teacher-preferences/")
        shoot(page, "09c_prefs", [], clip={"x": 0, "y": 100, "width": 1280, "height": 760})

        # 10) باقي الشاشات
        for name, path, height in (
            ("10_reports", "/reports/", 480),
            ("11_observations", "/quality/observations/", 480),
            ("12_procedures", "/quality/my-procedures/", 480),
            ("13_permits", "/staff-affairs/permits/mine/", 1230),
            ("14_notifications", "/notifications/inbox/", 480),
            ("15_password", "/auth/change-password/", 640),
            ("16_behavior_dashboard", "/behavior/dashboard/", 620),
        ):
            goto(page, path)
            shoot(page, name, [], clip={"x": 0, "y": 100, "width": 1280, "height": height})

        # قائمة المستخدم (تغيير كلمة المرور)
        goto(page, "/dashboard/")
        page.locator("header.site-header button:has-text('أحمد')").first.click()
        shoot(page, "02b_user_menu", [], clip={"x": 0, "y": 0, "width": 640, "height": 330})
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
