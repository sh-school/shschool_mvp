"""[CD-CANARY] التحقّق البَعدي من النشر — مستقلٌّ وفاشلٌ مغلقاً.

Railway ينشر من تكامل GitHub لحظةَ وصول الـcommit إلى `main`، قبل هذا السير
بثوانٍ ومستقلاً عنه. فحين كان الـcanary يحمل `needs: [preflight, test]` كان
سقوط `pytest` — أو تجاوزُه مهلته — **يمنع التحقّق من النشر لا النشرَ نفسه**:

    push main ──> Railway ينشر            (يقع دائماً)
              └─> pytest يسقط  ──> canary لا يبدأ   (فلا أحد يتحقّق)

أي أن الضمانة الوحيدة التي تكشف نشراً ميتاً كانت تُلغى في الحالة التي يُرجَّح
فيها أن يكون النشر معطوباً.

وكانت ميزانيتها متناقضةً مع نفسها: مسارها الداخلي ≈ ١٣ د، و`timeout-minutes`
عشر — فتقتلها GitHub في المنتصف وتُسجّلها `cancelled`، وهي حالةٌ لا يقرأها أحد
فشلاً. (وهذا بعينه ما جعل بوابة الأمن تمرّ صامتةً قبل إغلاقها.)
"""

import pathlib
import re

import pytest
import yaml

WORKFLOW = pathlib.Path(".github/workflows/deploy-railway.yml")

CANARY = "post-deploy-canary"


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _canary():
    return _workflow()["jobs"][CANARY]


def _canary_script():
    steps = _canary()["steps"]
    gates = [s for s in steps if s.get("id") == "canary"]

    assert len(gates) == 1, f"خطوة الحكم ليست واحدة: {[s.get('name') for s in steps]}"

    return gates[0]["run"]


def _executed_commands():
    """الأوامر المُنفَّذة وحدها — لا نصّ الملفّ.

    البحث النصّي يلتقط التعليقات التي تشرح **لماذا** أُزيل شيء، فيقرأ الشرحَ
    عودةً للشيء نفسه. وقد أسقط هذا حرّاساً في دفعاتٍ سابقة أكثر من مرّة.
    """
    return "\n".join(
        step.get("run", "") + str(step.get("with", {}))
        for job in _workflow()["jobs"].values()
        for step in job["steps"]
    )


# ═══════════════════════════════════════════════════════════════════
#  الاستقلال — التحقّق يقع حتى حين يسقط كل ما عداه
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("upstream", ["test", "preflight"])
def test_the_canary_does_not_wait_for_ci(upstream):
    """`pytest` و`preflight` لا يحجبان التحقّق من نشرٍ وقع بالفعل."""
    assert upstream in _workflow()["jobs"], "اسم الوظيفة تغيّر — الحارس يقيس لا شيء"

    assert upstream not in _canary().get("needs", [])


def test_the_canary_depends_on_nothing_at_all():
    """أيّ `needs` جديدة تُعيد الاقتران من باب آخر."""
    assert not _canary().get("needs")


def test_the_smoke_tests_follow_the_canary():
    assert _workflow()["jobs"]["smoke-test"]["needs"] == [CANARY]


def test_a_superseded_run_gives_way_to_the_newer_head():
    """التحقّق يُثبت آخر حالة لـ`main`، لا حالةً عبَرت.

    Railway ينشر خارج Actions، فوصولُ `B` أثناء دوران canary(A) يجعله يرى
    `served=B` و`want=A` — فينتظر إصداراً لن يعود، ثم يُعلن فشل نشرٍ لم يقع.
    و`cancel-in-progress: false` كان يضمن بقاء ذلك التشغيل إلى نهايته، أي أنه
    كان يضمن البلاغ الكاذب لا يمنعه.
    """
    concurrency = _workflow()["concurrency"]

    assert concurrency["cancel-in-progress"] is True


# ═══════════════════════════════════════════════════════════════════
#  مصدر نشرٍ واحد
# ═══════════════════════════════════════════════════════════════════


def test_no_second_deploy_trigger_hides_in_the_validation_workflow():
    """النشر من تكامل GitHub وحده.

    webhook داخل سير عملٍ اسمه «تحقّق بَعدي» مصدرُ نشرٍ ثانٍ مخبّأ: بناءان
    لنفس الـcommit، وسباقٌ على أيّهما يصل أخيراً.
    """
    commands = _executed_commands()

    assert "RAILWAY_DEPLOY_WEBHOOK" not in commands
    assert "railway_response" not in commands


def test_the_canary_does_not_burn_its_budget_on_a_blind_wait():
    """الحلقة تُميّز القديم من الجديد بـ`served` مقابل `want` — فالانتظار الأعمى
    قبلها يُنفق من الميزانية على ما تفعله المقارنة مجّاناً."""
    assert "sleep 90" not in _executed_commands()


# ═══════════════════════════════════════════════════════════════════
#  الحكم — الـSHA المدفوع صار حيّاً، لا أن الخدمة تتنفّس
# ═══════════════════════════════════════════════════════════════════


def test_the_verdict_starts_closed():
    """`false` يُكتب قبل أيّ محاولة، فلا يُقلب إلى `true` إلا ببرهان.

    وأيّ خروجٍ غير متوقّع — انقطاعٌ أو قتلٌ عند المهلة — يترك المخرَج على الفشل
    بدل أن يتركه فارغاً. والفارغ ليس `false`، فتُغلق خطوةُ الشفاء الذاتي قضيةَ
    فشلٍ لم يُثبت شفاؤها.
    """
    script = _canary_script()
    first_false = script.index("canary_passed=false")
    first_loop = script.index("for attempt in")

    assert first_false < first_loop, "المخرَج لا يبدأ مغلقاً"


def test_passing_requires_the_deployed_commit_not_merely_http_200():
    """الشرط مركّب: HTTP 200 **و** الـcommit المخدوم يساوي المطلوب."""
    script = _canary_script()

    assert '"$HTTP_CODE" = "200"' in script
    assert '"$COMMIT" = "$EXPECTED"' in script


def test_a_missing_commit_field_is_unknown_not_success():
    """خدمةٌ سليمة تخدم النسخة **السابقة** تُجيب بنعم على «أتتنفّس؟» وبلا على
    «أصار الـSHA حيّاً؟» — وهي بالضبط صورةُ النشر الفاشل الذي وُضع هذا الفحص
    لالتقاطه. فالرجوع إلى فحص الصحة وحده يُعمي الفحص عن حالته الهدف.
    """
    script = _canary_script()
    empty_branch = script[script.index('if [ -z "$COMMIT" ]') : script.index("elif")]

    assert "canary_passed=true" not in empty_branch, "غياب الـcommit يُمرِّر"
    assert "PASSED=true" not in empty_branch


# ═══════════════════════════════════════════════════════════════════
#  الميزانية — المهلة تسع المسار الطبيعي
# ═══════════════════════════════════════════════════════════════════


def test_the_timeout_covers_the_polling_budget_it_declares():
    """مهلةٌ أقصر من المسار الداخلي تُنتج `cancelled` لا `failure`.

    و`cancelled` حالةٌ لا يقرأها أحد فشلاً — وهي نفسها الثغرة التي عبرت منها
    بوابة الأمن قبل إغلاقها. فالميزانية تُحسب من السكربت لا تُقدَّر.
    """
    script = _canary_script()

    attempts = int(re.search(r"seq 1 (\d+)", script).group(1))
    curl_timeout = int(re.search(r"--max-time (\d+)", script).group(1))
    interval = int(re.search(r"sleep (\d+)", script).group(1))

    budget = attempts * curl_timeout + (attempts - 1) * interval
    allowed = _canary()["timeout-minutes"] * 60

    assert allowed >= budget, f"الميزانية {budget}ث تتجاوز المهلة {allowed}ث"


# ═══════════════════════════════════════════════════════════════════
#  الإبلاغ — الفشل يُرى، والنجاح يشفي
# ═══════════════════════════════════════════════════════════════════


def _step_named(prefix):
    steps = [s for s in _canary()["steps"] if s.get("name", "").startswith(prefix)]

    assert len(steps) == 1, f"«{prefix}» ليست خطوةً واحدة"

    return steps[0]


def test_a_failed_canary_still_raises_the_production_issue():
    step = _step_named("Rollback: Open or update")

    assert step["if"] == "steps.canary.outputs.canary_passed == 'false'"
    assert "issues.create" in step["with"]["script"]


def test_a_proven_canary_closes_the_stale_failure_issue():
    """الإغلاق مشروطٌ بـ`== 'true'` لا بنفي الفشل: مخرَجٌ فارغ ليس `false`،
    فشرطٌ منفيّ يُغلق قضيةً لم يُثبت شفاؤها."""
    step = _step_named("Rollback: Close stale")

    assert step["if"] == "steps.canary.outputs.canary_passed == 'true'"
    assert "state: 'closed'" in step["with"]["script"]
