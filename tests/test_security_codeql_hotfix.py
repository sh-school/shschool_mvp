from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_confirm_dialog_never_interpolates_message_into_html():
    source = read("static/js/base.js")

    assert "' + msg + '" not in source
    assert "querySelector('[data-confirm-message]').textContent = msg" in source


def test_student_search_uses_dom_text_nodes_for_api_data():
    source = read("templates/reports/index.html")

    assert "res.innerHTML = data.results.map" not in source
    assert "name.textContent = String(s.full_name || '')" in source
    assert "encodeURIComponent(String(s.id || ''))" in source
    assert "var base = link.getAttribute('data-base-href');" in source
    assert "new URL(base, window.location.origin)" in source
    assert "new URL(link.getAttribute('href'), window.location.origin)" not in source


def test_schedule_controls_do_not_assign_dom_values_to_location_href():
    source = read("templates/schedule/print_schedule.html")

    assert 'onchange="location.href=this.value"' not in source
    assert "location.href='?view=" not in source
    assert "submitScheduleView(this)" in source
    assert 'onchange="this.form.submit()"' in source


def test_kpi_pdf_link_uses_allowlisted_values_and_urlsearchparams():
    source = read("templates/analytics/kpi_dashboard.html")

    assert "new URLSearchParams" in source
    assert "paperSel.value === 'A3' ? 'A3' : 'A4'" in source
    assert "/^\\d{4}-\\d{4}$/.test(year)" in source


def test_push_endpoints_do_not_return_exception_text():
    source = read("parents/views.py")

    assert 'JsonResponse({"error": str(e)' not in source
    assert '"تعذر تسجيل اشتراك الإشعارات."' in source
    assert '"تعذر إلغاء اشتراك الإشعارات."' in source
    assert 'logger.exception("فشل تسجيل اشتراك Push لولي الأمر")' not in source
    assert 'logger.exception("فشل إلغاء اشتراك Push لولي الأمر")' not in source
    assert 'logger.error("فشل تسجيل اشتراك Push لولي الأمر")' in source
    assert 'logger.error("فشل إلغاء اشتراك Push لولي الأمر")' in source


def test_notification_exception_logs_do_not_include_recipient():
    source = read("notifications/services.py")

    assert (
        'logger.exception("فشل إرسال البريد الإلكتروني إلى %s: %s", log.recipient, e)' not in source
    )
    assert 'logger.exception("فشل إرسال SMS إلى %s: %s", log.recipient, e)' not in source
    assert 'logger.exception("فشل إرسال البريد الإلكتروني")' not in source
    assert 'logger.exception("فشل إرسال SMS")' not in source
    assert 'logger.error("فشل إرسال البريد الإلكتروني")' in source
    assert 'logger.error("فشل إرسال SMS")' in source

    assert "log.error_msg = str(e)" not in source
    assert "return False, str(e)" not in source
    assert "_EMAIL_FAILURE_MESSAGE" in source
    assert "_SMS_FAILURE_MESSAGE" in source

    dashboard = read("templates/notifications/dashboard.html")
    assert 'title="{{ log.error_msg }}"' not in dashboard


def test_real_seed_requires_secret_without_printing_credentials():
    source = read("scripts/real_seed.py")

    assert 'os.environ.get("SEED_DEFAULT_PASSWORD")' in source
    assert "secrets.token_urlsafe" not in source
    assert 'print(f"  كلمة المرور الموحدة: {_SEED_PASSWORD}")' not in source
    assert 'print(f"  المدير:    {principal_user.user.national_id}")' not in source
