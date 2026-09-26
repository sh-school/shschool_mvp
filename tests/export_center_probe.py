"""مشاهدُ مركز التصدير (`static/js/export-center.js`، VI-30أ) على صفحةٍ حيّةٍ بمتصفّح — بلا بياناتٍ ولا خادمِ تصدير.

يُحقَن في الصفحة رابطٌ لكلّ حالةٍ ويُعترَض طلبُه (`/__export__/…`) بجوابٍ مصنوع: ملفٌّ مباشر، ومهمّةٌ خلفيّةٌ بالعقد الجديد (202) وبالشكل القديم (200)،
واستطلاعٌ بطيءٌ يُظهر إشعارَ «جارٍ التحضير»، وخطأٌ 429، وصفحةُ HTML، وسببُ فشلٍ نصّيٌّ (503)، وانقطاعُ شبكة، ولسانٌ لـPDF. فيُقاس السلوكُ لا نصُّ السكربت.

يُستعمل من `tests/e2e/test_export_center_live.py` (صفحةُ اللوحة الحيّة) — ولا يستورد pytest ليعمل أيضاً على لقطةٍ مصيَّرةٍ خارج المجموعة.
"""

from __future__ import annotations

FILE_BYTES = b"PK\x03\x04-export-center-probe"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#: اسمٌ عربيٌّ بـ`filename*` — التنزيلُ يحمله كما هو لا `export` العامّ.
DISPOSITION = "attachment; filename*=UTF-8''%D8%AA%D9%82%D8%B1%D9%8A%D8%B1.xlsx"
BUSY = "لديك تصديرٌ قيد التحضير — انتظر اكتماله."
REASON = "تعذّر تحضير الملفّ: الخدمةُ مشغولة."

LINKS = {
    "file": "/__export__/file/",
    "job": "/__export__/job/",
    "legacy": "/__export__/legacy/",
    "busy": "/__export__/busy/",
    "html": "/__export__/html/",
    "reason": "/__export__/reason/",
    "down": "/__export__/down/",
    "pdf": "/__export__/pdf/",
}


class Server:
    """جوابُ الخادم المصنوع؛ عدّادُ الاستطلاع يُعاد لكلّ مهمّة."""

    def __init__(self) -> None:
        self.status_calls = 0
        self.seen: list[str] = []

    def __call__(self, route) -> None:
        url = route.request.url
        path = url.split("/__export__", 1)[1]
        self.seen.append(path)
        headers = route.request.headers
        if (
            not route.request.is_navigation_request()
        ):  # الانتقالُ الحقيقيُّ (مشهدُ HTML) لا يحمل الترويسة
            assert (
                headers.get("x-requested-with") == "XMLHttpRequest"
            ), f"{path}: بلا X-Requested-With"
        if path.startswith("/file/"):
            route.fulfill(
                status=200,
                body=FILE_BYTES,
                headers={"Content-Type": XLSX, "Content-Disposition": DISPOSITION},
            )
        elif path.startswith("/job/"):
            body = '{"job":"j1","status_url":"/__export__/status/j1/","poll_ms":2000}'
            route.fulfill(status=202, body=body, content_type="application/json")
        elif path.startswith("/status/j1/"):
            # 300 ثمّ 600 ثمّ 1200ms قبل الجاهزيّة: نحو ثانيتين — والإشعارُ يظهر عند 600ms ويبقى قبل الجاهزيّة.
            self.status_calls += 1
            if self.status_calls < 4:
                route.fulfill(
                    status=200,
                    body='{"status":"running","download_url":null,"error":null}',
                    content_type="application/json",
                )
            else:
                body = '{"status":"done","download_url":"/__export__/download/j1/","error":null}'
                route.fulfill(status=200, body=body, content_type="application/json")
        elif path.startswith("/download/j1/"):
            route.fulfill(
                status=200,
                body=FILE_BYTES,
                headers={"Content-Type": XLSX, "Content-Disposition": DISPOSITION},
            )
        elif path.startswith("/legacy/"):
            route.fulfill(
                status=200,
                body='{"job_id":"L1","status_url":"/__export__/legacy-status/L1/"}',
                content_type="application/json",
            )
        elif path.startswith("/legacy-status/"):
            if "format=json" in url:
                route.fulfill(status=200, body='{"status":"done"}', content_type="application/json")
            else:  # الشكلُ القديم: العنوانُ نفسُه بلا الوسيط هو الملفّ
                route.fulfill(
                    status=200,
                    body=FILE_BYTES,
                    headers={"Content-Type": XLSX, "Content-Disposition": DISPOSITION},
                )
        elif path.startswith("/busy/"):
            body = '{"error":{"code":"busy","message":"' + BUSY + '"}}'
            route.fulfill(status=429, body=body, content_type="application/json")
        elif path.startswith("/html/"):
            route.fulfill(
                status=200,
                body="<!doctype html><title>صفحةٌ لا ملفّ</title><p>صفحة</p>",
                content_type="text/html; charset=utf-8",
            )
        elif path.startswith("/reason/"):
            route.fulfill(status=503, body=REASON, content_type="text/plain; charset=utf-8")
        elif path.startswith("/down/"):
            route.abort()
        elif path.startswith("/form/"):
            if "format=xlsx" in url and "date=2026-09-22" in url:
                route.fulfill(
                    status=200,
                    body=FILE_BYTES,
                    headers={"Content-Type": XLSX, "Content-Disposition": DISPOSITION},
                )
            else:
                route.fulfill(
                    status=400, body="وسطاءُ ناقصة", content_type="text/plain; charset=utf-8"
                )
        elif path.startswith("/pdf/"):
            route.fulfill(
                status=200,
                body=b"%PDF-1.4\n%probe\n",
                headers={"Content-Type": "application/pdf", "Content-Disposition": "inline"},
            )
        else:  # pragma: no cover
            route.fulfill(status=404, body="?")


def install(page) -> Server:
    """يعترض `/__export__/**` ويُضيف رابطاً `data-app-file` لكلّ حالة إلى صفحةٍ فيها base.js ومركزُ التصدير."""
    server = Server()
    page.context.route(
        "**/__export__/**", server
    )  # على السياق لا الصفحة: اللسانُ الجديدُ لا يرث مسارَ الصفحة
    page.evaluate(
        """(links) => {
          for (const [name, href] of Object.entries(links)) {
            const a = document.createElement('a');
            a.setAttribute('data-app-file', '');
            a.id = 'probe-' + name;
            a.href = href;
            if (name === 'pdf') a.target = '_blank';
            a.textContent = name;
            document.body.appendChild(a);
          }
        }""",
        LINKS,
    )
    # زرُّ نموذجٍ (كشفا الجناح والشعبة): GET بحقلٍ مخفيٍّ وحقلٍ مطلوبٍ، وزرُّ التصدير يحمل `name=format value=xlsx`.
    page.evaluate(
        """() => {
          const form = document.createElement('form');
          form.method = 'get';
          form.action = '/__export__/form/';
          form.id = 'probe-form';
          form.innerHTML = '<input type="hidden" name="date" value="2026-09-22">' +
            '<input name="need" id="probe-need" required>' +
            '<button data-app-file type="submit" name="format" value="xlsx" id="probe-form-xlsx">x</button>';
          document.body.appendChild(form);
        }"""
    )
    assert page.evaluate(
        "typeof window.showToast === 'function'"
    ), "لا showToast: الصفحةُ بلا base.js"
    return server


def _reset(page) -> None:
    """إشعاراتُ الحالة السابقة تبقى ثوانيَ — تُمحى كي لا يطابقها انتظارُ الحالة التالية."""
    page.evaluate("document.querySelectorAll('#toast-container .toast').forEach((t) => t.remove())")


def _toast_texts(page, kind: str) -> list[str]:
    return page.locator(f"#toast-container .toast-{kind} .toast-msg").all_inner_texts()


def scenario_direct_file_is_saved_silently(page, server: Server) -> None:
    """ملفٌّ مباشرٌ سريع: يُحفظ باسم `filename*` والصفحةُ في مكانها وبلا أيّ إشعار (لا وميضَ)."""
    url = page.url
    with page.expect_download() as download:
        page.click("#probe-file")
    assert download.value.suggested_filename == "تقرير.xlsx"
    assert page.url == url, "انتقلت الصفحةُ بدل أن يُحفَظ الملفّ"
    assert not page.locator("#toast-container .toast").count(), "إشعارٌ لملفٍّ سريع"
    assert page.locator("#probe-file[aria-busy]").count() == 0, "بقي الرابطُ مشغولاً"


def scenario_background_job_shows_a_notice_then_downloads(page, server: Server) -> None:
    """202+JSON: إشعارُ «جارٍ التحضير» (بعد 600ms) ← استطلاعٌ ← تنزيلُ `download_url` ← «الملفّ جاهز»، ويُغلق الإشعارُ الأوّل."""
    server.status_calls = 0
    with page.expect_download() as download:
        page.click("#probe-job")
        page.wait_for_selector("#toast-container .toast-info", timeout=3000)
        assert "جارٍ تحضير الملفّ" in _toast_texts(page, "info")[0]
    assert download.value.suggested_filename == "تقرير.xlsx"
    page.wait_for_selector("#toast-container .toast-success", timeout=3000)
    assert "الملفّ جاهز" in _toast_texts(page, "success")[0]
    page.wait_for_function(
        "document.querySelectorAll('#toast-container .toast-info').length === 0", timeout=3000
    )
    assert server.status_calls == 4, server.status_calls
    assert "/download/j1/" in server.seen


def scenario_legacy_job_shape_still_works(page, server: Server) -> None:
    """الشكلُ القديم للجدول: 200 + JSON بـ`status_url` واستطلاعٌ بـ`?format=json` ثمّ العنوانُ نفسُه هو الملفّ."""
    with page.expect_download() as download:
        page.click("#probe-legacy")
    assert download.value.suggested_filename == "تقرير.xlsx"
    assert any(
        "/legacy-status/L1/" in seen and "format=json" in seen for seen in server.seen
    ), server.seen
    assert any(
        "/legacy-status/L1/" in seen and "format=json" not in seen for seen in server.seen
    ), "لم يُجلب الملفُّ من عنوان الحالة نفسِه"


def scenario_busy_is_an_error_toast_with_the_server_message(page, server: Server) -> None:
    """429+JSON: إشعارٌ أحمرُ بنصّ الخادم وحدَه (`role=alert`)، بلا تنزيلٍ ولا انتقال."""
    url = page.url
    page.click("#probe-busy")
    page.wait_for_selector("#toast-container .toast-danger", timeout=3000)
    assert _toast_texts(page, "danger")[0] == BUSY
    assert page.locator("#toast-container .toast-danger[role=alert]").count() == 1
    assert page.url == url


def scenario_plain_text_reason_is_read_not_hidden(page, server: Server) -> None:
    """503+text/plain (render_pdf يشرح السبب): يُقرأ ويظهر في إشعارٍ أحمر."""
    page.click("#probe-reason")
    page.wait_for_selector("#toast-container .toast-danger", timeout=3000)
    assert REASON in _toast_texts(page, "danger")


def scenario_network_failure_is_never_silent(page, server: Server) -> None:
    """انقطاعُ الشبكة: إشعارٌ أحمرُ لا صمت، ويعود الرابطُ صالحاً للمحاولة."""
    page.click("#probe-down")
    page.wait_for_selector("#toast-container .toast-danger", timeout=3000)
    assert "تعذّر" in _toast_texts(page, "danger")[-1]
    assert page.locator("#probe-down[aria-busy]").count() == 0


def scenario_form_button_sends_its_own_name_and_value(page, server: Server) -> None:
    """زرُّ نموذجٍ `data-app-file`: يُرسَل ما كان النموذجُ سيرسله (الحقلُ المخفيّ واسمُ الزرّ وقيمتُه) ويُحفظ الملفُّ بلا انتقال؛ ونموذجٌ ناقصٌ لا يُرسَل."""
    url = page.url
    calls = len(server.seen)
    page.click("#probe-form-xlsx")  # حقلٌ مطلوبٌ فارغ: لا طلبَ ولا انتقال
    page.wait_for_timeout(300)
    assert len(server.seen) == calls, "أُرسل نموذجٌ ناقص"
    page.fill("#probe-need", "x")
    with page.expect_download() as download:
        page.click("#probe-form-xlsx")
    assert download.value.suggested_filename == "تقرير.xlsx"
    assert page.url == url
    assert any(
        "/form/" in seen and "format=xlsx" in seen and "need=x" in seen for seen in server.seen
    ), server.seen


def scenario_html_is_a_page_never_a_download(page, server: Server) -> None:
    """جوابُ HTML صفحةٌ لا ملفّ: تُفتح الصفحةُ (كما كانت بالانتقال) ولا يُنزَّل HTML ملفّاً."""
    downloads = []
    page.on("download", lambda download: downloads.append(download))
    with page.expect_navigation():
        page.click("#probe-html")
    assert page.url.endswith("/__export__/html/")
    assert not downloads, "نُزِّل HTML على أنّه ملفّ"


def scenario_target_blank_links_stay_with_the_browser(page, server: Server) -> None:
    """رابطُ `target=_blank` (عرضُ PDF في لسانٍ جديد) يفتحه المتصفّحُ بنفسه: طلبٌ واحدٌ هو الانتقالُ نفسُه — لا جلبَ خلفيّاً ولا إشعارَ تحضير.

    (فتحُه من blob بعد الجلب يرثُ CSP الصفحة `object-src 'none'` فيُحجب عارضُ PDF؛ وتنزيلُه بدل عرضه يغيّر ما اعتاده المستخدم — انظر ترويسة السكربت.)
    """
    url = page.url
    before = sum("/pdf/" in seen for seen in server.seen)
    with page.context.expect_page() as popup:
        page.click("#probe-pdf")
    tab = popup.value
    tab.wait_for_timeout(1000)  # Chromium بلا واجهة ينزّل الـPDF بدل عرضه؛ والطلبُ واحدٌ في الحالتين
    assert (
        sum("/pdf/" in seen for seen in server.seen) - before == 1
    ), "طُلب الرابطُ أكثرَ من مرّةٍ (جلبٌ خلفيٌّ فوق الانتقال)"
    assert page.url == url
    assert not page.locator("#toast-container .toast").count(), "إشعارٌ لرابطٍ يتركه المركزُ للمتصفّح"
    if not tab.is_closed():
        tab.close()


#: الترتيبُ مقصود: مشهدُ HTML أخيراً لأنّه ينتقل بالصفحة.
SCENARIOS = (
    scenario_direct_file_is_saved_silently,
    scenario_background_job_shows_a_notice_then_downloads,
    scenario_legacy_job_shape_still_works,
    scenario_busy_is_an_error_toast_with_the_server_message,
    scenario_plain_text_reason_is_read_not_hidden,
    scenario_network_failure_is_never_silent,
    scenario_target_blank_links_stay_with_the_browser,
    scenario_form_button_sends_its_own_name_and_value,
    scenario_html_is_a_page_never_a_download,
)


def run_all(page) -> None:
    server = install(page)
    for scenario in SCENARIOS:
        _reset(page)
        scenario(page, server)
