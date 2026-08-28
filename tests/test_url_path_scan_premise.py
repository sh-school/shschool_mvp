"""[PRIVACY] المقدّمة التي بُني عليها إعفاء `url_path` من فحص الكلمات.

نموذج مراسلة المطوّر يخزّن `url_path` مع الشكوى. وفيه مرشِّحان: أحدهما يقتطع
سلسلة الاستعلام، والآخر يُسقط أيّ حقلٍ حوت قيمتُه «token» أو «session» أو
أخواتها.

وبعد الاقتطاع صار الفحص على `url_path` كلَّه إيجابياتٍ كاذبة: السرّ يسكن
سلسلة الاستعلام وقد حُذفت، والسرّ حين يقع في مسارٍ يكون **قيمةً معتِمة** لا
الكلمة الإنجليزية — حتى مسار استعادة كلمة المرور في جانغو يُرسم
`/reset/<uidb64>/<token>/` فيُطبع رمزاً لا كلمة. بينما `/exam_control/session/12/`
مسارٌ بريء كان يُلقى بأكمله، فتصل شكوى المستخدم بلا موضعٍ يدلّ عليها.

فأُعفي `url_path` من الفحص. والقرار قام على فحصٍ لمسارات المنصّة كلّها:
كلّ ما يحمل إحدى الكلمات يحمل بعدها `<uuid:…>` أو `<int:…>` أو لا شيء.

وهذا الملفّ يحوّل ذلك الفحص من واقعةٍ إلى شرط. فإن أُضيف يوماً مسارٌ مثل
`auth/session/<str:key>/` سقط الاختبار، وعاد الإعفاء إلى المراجعة قبل أن
يُسرَّب شيء.
"""

import pathlib
import re

#: الكلمات التي يفحصها النموذج.
BLOCKED = ("token", "password", "secret", "jwt", "cookie", "session")

#: أنماط الالتقاط التي لا تحمل سرّاً — معرّفاتٌ لا مفاتيح.
OPAQUE_SAFE = ("uuid:", "int:", "pk")

SKIP = ("/.venv/", "/node_modules/", "/.claude/", "/.mypy_cache/")

ROUTE = re.compile(r"""(?:re_)?path\(\s*["']([^"']*)["']""")
CAPTURE = re.compile(r"<([^>]+)>")


def _routes():
    for f in sorted(pathlib.Path(".").rglob("urls.py")):
        if any(x in "/" + f.as_posix() for x in SKIP):
            continue
        src = f.read_text(encoding="utf-8", errors="ignore")
        for m in ROUTE.finditer(src):
            yield f.as_posix(), m.group(1)


def test_the_sweep_finds_the_routes():
    """حارسٌ يمسح لا شيء يمرّ دائماً."""
    routes = list(_routes())

    assert len(routes) > 100
    assert any("session" in r for _, r in routes), "المسارات التي أثارت السؤال"


def test_no_route_puts_a_secret_after_a_blocked_word():
    """المقدّمة: ما يلي كلمةً محجوبة معرّفٌ معتِم لا مفتاح.

    فلو ظهر `auth/session/<str:key>/` لصار الفحص المُلغى ذا قيمة، ووجب
    إعادة النظر في الإعفاء.
    """
    risky = []
    for where, route in _routes():
        low = route.lower()
        if not any(b in low for b in BLOCKED):
            continue
        for cap in CAPTURE.findall(route):
            if not any(cap.startswith(s) or cap == s for s in OPAQUE_SAFE):
                risky.append(f"{where}  {route}  <{cap}>")

    assert not risky, "مسارٌ يحمل قيمةً غير معتِمة بعد كلمةٍ محجوبة:\n" + "\n".join(risky)


def test_the_form_still_scans_every_field_but_the_path():
    """الإعفاء خاصٌّ بـ`url_path` — ولم يُلغَ الفحص عن سائر الحقول."""
    import json

    from developer_feedback.forms import DeveloperMessageForm

    data = {
        "message_type": "bug",
        "priority": "normal",
        "subject": "اختبار عنوان صالح",
        "body": "وصف طويل كفاية لاختبار النموذج.",
        "consent_privacy": True,
        "context_json_raw": json.dumps(
            {"url_path": "/exam_control/session/12/", "view_name": "auth:password_reset"}
        ),
    }

    form = DeveloperMessageForm(data=data)
    form.is_valid()
    ctx = form.cleaned_data["context_json_raw"]

    assert ctx["url_path"] == "/exam_control/session/12/", "المسار ينجو"
    assert "view_name" not in ctx, "وغيره ما زال يُفحص"


def test_the_query_string_is_still_removed_before_anything_is_kept():
    """الإعفاء يقوم على الاقتطاع — فلو سقط الاقتطاع سقط مبرّره."""
    import json

    from developer_feedback.forms import DeveloperMessageForm

    form = DeveloperMessageForm(
        data={
            "message_type": "bug",
            "priority": "normal",
            "subject": "اختبار عنوان صالح",
            "body": "وصف طويل كفاية لاختبار النموذج.",
            "consent_privacy": True,
            "context_json_raw": json.dumps({"url_path": "/p?token=SECRETVALUE&sid=x"}),
        }
    )
    form.is_valid()
    ctx = form.cleaned_data["context_json_raw"]

    assert ctx["url_path"] == "/p"
    assert "SECRETVALUE" not in json.dumps(ctx, ensure_ascii=False)
