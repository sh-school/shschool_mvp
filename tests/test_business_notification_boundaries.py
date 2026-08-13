"""
tests/test_business_notification_boundaries.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[B4-PRE3] الطفرة ونيّة إشعارها في حدٍّ واحد.

جردُ B4-2A وجد سبعة حدود أعمال تنادي الإشعار خارج أي معاملة. وB4-PRE2 أجّلت
الخروج الخارجي إلى ما بعد الالتزام — لكن التأجيل بلا معاملة لا يعني شيئاً: خارج
أي معاملة يُنفّذ Django الـcallback فوراً. فالحدّ هو ما يجعل التأجيل ذا أثر.

والمُثبَت هنا سلوكيّ لا نصّيّ. وجودُ `transaction.atomic` في المصدر لا يقول أين
حدّه ولا ماذا يشمل؛ الشيء الوحيد الذي يقوله فشلٌ مفروض:

    طفرة أعمال ← إشعار ← فشل
        ⇒ الطفرة تراجعت
        ⇒ إشعار المنصّة غائب
        ⇒ لا طابور ولا مزوّد
"""

from unittest.mock import patch

import pytest
from django.db import transaction

from core.models import BehaviorInfraction
from notifications.models import InAppNotification
from tests.conftest import SchoolFactory, UserFactory


class _SentinelError(Exception):
    """يُجهض المعاملة بلا أن يختلط بخطأ حقيقي."""


def _abort_the_business_transaction():
    """يُحاكي فشلاً يقع بعد الإشعار ويُجهض الطفرة.

    الرفع من دالّة لا من جسم `with` مباشرةً: محلّلات السكون لا تعرف أن
    `pytest.raises` يبتلع الاستثناء فتُبلّغ عن التأكيدات التالية كأنها غير
    قابلة للبلوغ.
    """
    raise _SentinelError


@pytest.fixture
def hub_queued():
    """يعترض طبر الـHub — القنوات الخارجية عبر NotificationHub."""
    with patch("notifications.tasks.hub_send_notification_task.delay") as mock:
        yield mock


@pytest.fixture
def behavior_queued():
    """يعترض الطبر الخام لمهمّة إشعار المخالفة."""
    with patch("notifications.tasks.notify_behavior_task.delay") as mock:
        yield mock


# ══════════════════════════════════════════════════════════════════
# السلوك — مساراً المخالفة
# ══════════════════════════════════════════════════════════════════
#
# هذان المساران لا يمرّان بالـHub، فلا يشملهما تأجيل B4-PRE2. الحدّ الجديد
# يُدخلهما فيه عبر `_notify_behavior_after_commit`.


def _record_infraction(school, student, reporter):
    """يُحاكي ما يفعله `report_infraction` داخل حدّه."""
    from behavior.services import BehaviorService
    from behavior.views import _notify_behavior_after_commit

    with transaction.atomic():
        infraction = BehaviorService.create_infraction(
            school=school,
            student=student,
            reporter=reporter,
            level=2,
            description="وصف",
            action_taken="إجراء",
            points_deducted=0,
        )
        transaction.on_commit(lambda: _notify_behavior_after_commit(infraction, school, reporter))
        return infraction


@pytest.mark.django_db(transaction=True)
def test_an_infraction_notifies_once_after_it_commits(behavior_queued):
    """المسار المشروع: تلتزم المخالفة ثم يخرج إشعارها مرّة واحدة."""
    school = SchoolFactory()
    student = UserFactory()
    reporter = UserFactory()

    infraction = _record_infraction(school, student, reporter)

    assert BehaviorInfraction.objects.filter(id=infraction.id).exists()
    assert behavior_queued.call_count == 1


@pytest.mark.django_db(transaction=True)
def test_a_failed_infraction_notifies_nobody(behavior_queued):
    """
    [B4-PRE3] الثابت الأساسي.

    يمرّ بالمسار نفسه — تسجيلَ الـcallback ضمناً — لا بإنشاء المخالفة وحده.
    صيغتُه الأولى كانت تُنشئ المخالفة ثم ترفع بلا تسجيل شيء، فكانت تبقى خضراء
    حتى لو حُذف `transaction.on_commit` من الشاشتين كلّيهما: تأكيدٌ يقول "لم
    يخرج شيء" بينما لم يكن هناك ما يخرج أصلاً.

    و`create_infraction` مزيَّنة بـ`@transaction.atomic`، فتصير نقطةَ حفظ
    داخلية؛ والالتزام الذي يُطلق الـcallback هو نهاية المعاملة الخارجية.
    """
    school = SchoolFactory()
    student = UserFactory()
    reporter = UserFactory()

    with patch("behavior.services.BehaviorService.notify_parents") as direct:
        with pytest.raises(_SentinelError), transaction.atomic():
            infraction = _record_infraction(school, student, reporter)
            assert BehaviorInfraction.objects.filter(id=infraction.id).exists()
            _abort_the_business_transaction()

    assert not BehaviorInfraction.objects.filter(id=infraction.id).exists()
    assert not behavior_queued.called, "خرج إلى الطابور رغم التراجع"
    assert not direct.called, "أرسل مباشرةً رغم التراجع"


@pytest.mark.django_db(transaction=True)
def test_a_broker_failure_after_commit_is_contained_not_compensated(caplog):
    """
    [B4-7A.3] انقلابٌ مقصود في عقد B4-PRE3.

    كان الارتداد المباشر يُعدّ حفاظاً على الإتاحة. وقد صحّ ذلك ما دام الوسيط
    غائباً أصلاً (`ALWAYS_EAGER`) فلا يقع الارتداد قطّ. أمّا مع وسيطٍ حقيقي
    فيصير مساراً حيّاً، وفيه خاصيّتان لا تُقبلان:

    **الأولى** أنه يُنفّذ نداءات مزوّد داخل طلب HTTP — عبر `notify_parents` ثم
    الـHub ثم `_send_sync` — بلا مهلة ولا إعادة ولا استئجار.

    **والثانية** أن فشل النشر **غامض**: قد يكون الوسيط قبِل الرسالة ثم انقطع
    الاتصال قبل الإقرار. فيعمل العامل والويب معاً ويصل الإشعار مرّتين.

    فنختار خسارة محاولة نادرة عند العطل على تكرارٍ يكسر الدلالة.
    """
    import logging

    school = SchoolFactory()
    student = UserFactory()
    reporter = UserFactory()

    with (
        patch(
            "notifications.tasks.notify_behavior_task.delay",
            side_effect=RuntimeError("broker down"),
        ),
        patch("behavior.services.BehaviorService.notify_parents") as direct,
        caplog.at_level(logging.ERROR, logger="behavior.views"),
    ):
        infraction = _record_infraction(school, student, reporter)

    assert BehaviorInfraction.objects.filter(id=infraction.id).exists(), "تراجعت الطفرة"
    assert not direct.called, "أرسل مباشرةً من الويب رغم الاحتواء"
    assert any(
        "broker publish failed" in record.message for record in caplog.records
    ), "فشل النشر لم يُرصد — و`ERROR` هي ما يرفعه Sentry"


# ══════════════════════════════════════════════════════════════════
# السلوك — طفرة عمليّات
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
def test_a_failed_operations_mutation_notifies_nobody(hub_queued):
    """
    نفس الثابت على مسار يمرّ بالـHub.

    وهنا يظهر أثر B4-PRE2 وB4-PRE3 معاً: التأجيل يمنع الخروج، والحدّ هو ما
    يجعل للتأجيل معنى.
    """
    from notifications.hub import NotificationHub

    school = SchoolFactory()
    teacher = UserFactory(email="t@example.com")

    with patch("notifications.hub._send_sync") as sync:
        with pytest.raises(_SentinelError), transaction.atomic():
            NotificationHub.dispatch(
                event_type="general",
                school=school,
                recipients=[teacher],
                title="عنوان",
                body="نصّ",
            )
            _abort_the_business_transaction()

    assert not InAppNotification.objects.filter(user=teacher).exists()
    assert not hub_queued.called
    assert not sync.called


# ══════════════════════════════════════════════════════════════════
# السلوك — طفرة جودة عبر الشاشة الإنتاجية
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
def test_a_failed_quality_mutation_rolls_back_and_notifies_nobody(client, hub_queued):
    """
    [B4-PRE3] ممثّل عن حدود الجودة الثلاثة — عبر الشاشة نفسها لا محاكاتها.

    الفشل يُفرَض **داخل** حدّ الشاشة: يمرّ الإشعار كاملاً — فتُكتب إشعارات
    المنصّة ويُسجَّل الـcallback — ثم يُرفع استثناء قبل أن تلتزم المعاملة. فإن
    كان الحدّ يضمّ الحفظ والإشعار معاً، تراجعا معاً ولم يخرج شيء.

    وحدُّ الشاشة هو المُختبَر لا حدّ الاختبار: لو لُفّت الشاشة من الخارج لكان
    الاختبار يُثبت معاملته هو.
    """
    from django.urls import reverse

    from notifications.hub import NotificationHub
    from tests.test_quality_models import make_committee_member, make_domain, make_procedure
    from tests.test_views_quality2 import make_admin, make_teacher

    school = SchoolFactory()
    admin = make_admin(school)
    reviewer = make_teacher(school, suffix="RV")
    make_committee_member(school, reviewer)

    procedure = make_procedure(school, make_domain(school), status="In Progress")

    real_dispatch = NotificationHub.dispatch

    def _dispatch_then_fail(*args, **kwargs):
        real_dispatch(*args, **kwargs)
        _abort_the_business_transaction()

    client.force_login(admin)

    with patch("quality.views.NotificationHub.dispatch", side_effect=_dispatch_then_fail):
        with patch("notifications.hub._send_sync") as sync, pytest.raises(_SentinelError):
            client.post(
                reverse("update_proc_status", kwargs={"proc_id": procedure.id}),
                {"status": "Pending Review"},
            )

    procedure.refresh_from_db()

    assert procedure.status == "In Progress", "بقيت الطفرة رغم فشل داخل حدّها"
    assert not InAppNotification.objects.filter(user=reviewer).exists()
    assert not hub_queued.called
    assert not sync.called


@pytest.mark.django_db(transaction=True)
def test_the_same_quality_view_does_notify_when_it_succeeds(client, hub_queued):
    """
    الاختبار السابق بلا معنى ما لم يكن الإشعار قد بُلغ فعلاً.

    لو لم تصل الشاشة إلى `NotificationHub.dispatch` — لعدم وجود مراجعين مثلاً —
    لمرّ اختبار التراجع لأن شيئاً لم يُطلب أصلاً. وهذا هو الفخّ نفسه الذي أسقط
    الصيغة الأولى لاختبار المخالفة.
    """
    from django.urls import reverse

    from tests.test_quality_models import make_committee_member, make_domain, make_procedure
    from tests.test_views_quality2 import make_admin, make_teacher

    school = SchoolFactory()
    admin = make_admin(school)
    reviewer = make_teacher(school, suffix="RW")
    make_committee_member(school, reviewer)

    procedure = make_procedure(school, make_domain(school), status="In Progress")

    client.force_login(admin)
    client.post(
        reverse("update_proc_status", kwargs={"proc_id": procedure.id}),
        {"status": "Pending Review"},
    )

    procedure.refresh_from_db()

    assert procedure.status == "Pending Review"
    assert InAppNotification.objects.filter(user=reviewer).exists()
    assert hub_queued.called


# ══════════════════════════════════════════════════════════════════
# الدفعة — تبديل الحصص
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
def test_a_failing_swap_does_not_roll_back_the_ones_before_it(hub_queued):
    """
    [B4-PRE3] معاملة لكل طلب لا للدفعة.

    حدٌّ حول الحلقة كان سيجعل فشل الطلب الثاني يُلغي إلغاء الأول ويُسقط
    إشعاره معه. الفشل هنا مفروض من خارج الإنتاج — عبر اعتراض `_notify` —
    فلا نُغيّر دلالة الاستثناءات في الشيفرة لتسهيل الاختبار.
    """
    from operations.models import TeacherSwap
    from operations.services import SwapService

    school = SchoolFactory()
    _stale_swap(school, 1)
    _stale_swap(school, 3)

    # الفشل يقع على **ثاني** طلب تصل إليه الحلقة لا على معرّف بعينه: ترتيب
    # الاستعلام غير مضمون، فتثبيت المعرّف كان يجعل الاختبار يقيس الترتيب لا
    # حدود المعاملة — وقد يفشل الطلب الأول فلا يُعالَج الآخر إطلاقاً.
    processed = []

    def _notify_but_fail_on_the_second(swap, *args, **kwargs):
        processed.append(swap.id)
        if len(processed) == 2:
            raise _SentinelError
        return None

    with (
        patch.object(SwapService, "_notify", side_effect=_notify_but_fail_on_the_second),
        pytest.raises(_SentinelError),
    ):
        SwapService.expire_stale_swaps()

    assert len(processed) == 2, "الحلقة لم تبلغ طلبين"

    committed = TeacherSwap.objects.get(id=processed[0])
    rolled_back = TeacherSwap.objects.get(id=processed[1])

    assert committed.status == "cancelled", "تراجع طلبٌ نجح بسبب فشل طلب لاحق"
    assert rolled_back.status == "pending_b", "لم يتراجع الطلب الذي فشل"
    assert TeacherSwap.objects.filter(status="cancelled").count() == 1


def _schedule_slot(school, class_group, subject, teacher, period):
    from datetime import time

    from operations.models import ScheduleSlot

    return ScheduleSlot.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher,
        subject=subject,
        day_of_week=0,
        period_number=period,
        start_time=time(8, 0),
        end_time=time(8, 45),
    )


def _stale_swap(school, period_offset):
    """طلب تبديل قديم بما يكفي ليُلغى.

    `period_offset` يُبقي حصص كل طلب متمايزة، فالجدول يمنع تكرار المعلّم في
    الحصّة نفسها.
    """
    from datetime import timedelta

    from django.utils import timezone as tz

    from operations.models import Subject, TeacherSwap
    from operations.services import SwapService
    from tests.conftest import ClassGroupFactory

    class_group = ClassGroupFactory(school=school)
    subject = Subject.objects.create(
        school=school, name_ar=f"مادة {period_offset}", code=f"S{period_offset}"
    )
    teacher_a, teacher_b = UserFactory(), UserFactory()

    swap = TeacherSwap.objects.create(
        school=school,
        teacher_a=teacher_a,
        teacher_b=teacher_b,
        slot_a=_schedule_slot(school, class_group, subject, teacher_a, period_offset),
        slot_b=_schedule_slot(school, class_group, subject, teacher_b, period_offset + 1),
        swap_date_a=tz.localdate(),
        swap_date_b=tz.localdate(),
        status="pending_b",
        reason="سبب",
    )
    TeacherSwap.objects.filter(id=swap.id).update(
        created_at=tz.now() - timedelta(hours=SwapService.EXPIRY_HOURS + 1)
    )
    swap.refresh_from_db()
    return swap


# ══════════════════════════════════════════════════════════════════
# الحدود معلَنة — فحص نحويّ مكمّل لا بديل
# ══════════════════════════════════════════════════════════════════
#
# هذا لا يُثبت التراجع؛ الاختبارات أعلاه تفعل. لكنه يمنع أن يختفي حدٌّ بصمت
# في تعديل لاحق ولا يلاحظه أحد لأن لا اختبار يمرّ بذلك الفرع بعينه.


def _encloses_in_atomic(module_path, function_name):
    """هل الدالّة مزيَّنة بـatomic أو تحتوي كتلة atomic؟"""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / module_path).read_text(encoding="utf-8"))
    source = (root / module_path).read_text(encoding="utf-8")

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name != function_name:
            continue
        for decorator in node.decorator_list:
            if getattr(decorator, "attr", getattr(decorator, "id", "")) == "atomic":
                return True
        return "transaction.atomic" in (ast.get_source_segment(source, node) or "")

    raise AssertionError(f"{module_path}::{function_name} غير موجودة")


@pytest.mark.parametrize(
    ("module_path", "function_name"),
    [
        ("behavior/views.py", "report_infraction"),
        ("behavior/views.py", "quick_log"),
        ("behavior/views.py", "summon_parent"),
        ("behavior/services.py", "apply_committee_decision"),
        ("behavior/services.py", "escalate_infraction"),
        ("behavior/services.py", "record_security_referral"),
        ("operations/services.py", "expire_stale_swaps"),
        ("quality/views.py", "update_procedure_status"),
        ("quality/views.py", "approve_procedure"),
        ("quality/views.py", "toggle_evidence_request"),
    ],
)
def test_each_business_boundary_declares_a_transaction(module_path, function_name):
    """كل حدّ من الجرد صار داخل معاملة معلَنة."""
    assert _encloses_in_atomic(module_path, function_name)


def test_the_notification_helpers_do_not_own_a_boundary():
    """
    [B4-PRE3] الحدّ عند مالك الطفرة لا عند مساعد الإشعار.

    `@transaction.atomic` على `_auto_summon_parent` أو `_notify` كان سيُنتج
    معاملةً منفصلة عن الطفرة — أي العطب نفسه بشكل يبدو مُعالَجاً.
    """
    assert not _encloses_in_atomic("behavior/services.py", "_auto_summon_parent")
    assert not _encloses_in_atomic("operations/services.py", "_notify")


def _defers_to(module_path, function_name, target_name):
    """هل تُسجّل الدالّة `transaction.on_commit` يقود إلى `target_name`؟"""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / module_path).read_text(encoding="utf-8")

    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name != function_name:
            continue

        body = ast.get_source_segment(source, node) or ""
        return "transaction.on_commit" in body and target_name in body

    raise AssertionError(f"{module_path}::{function_name} غير موجودة")


@pytest.mark.parametrize("view_name", ["report_infraction", "quick_log"])
def test_the_infraction_views_defer_their_own_enqueue(view_name):
    """
    [B4-PRE3] الشاشتان تُسجّلان التأجيل بأنفسهما.

    الاختبارات السلوكية أعلاه تمرّ بمساعدٍ يُحاكي ما تفعله الشاشتان، فحذفُ
    `transaction.on_commit` منهما لا يُسقط أيّاً منها. وهذا الفحص هو ما يُسقطه:
    بدونه يبقى الطبر الخام داخل المعاملة، ومع `ALWAYS_EAGER` يصير إرسالاً قبل
    الالتزام — العطب الذي أزالته B4-PRE2 عائداً من باب آخر.
    """
    assert _defers_to("behavior/views.py", view_name, "_notify_behavior_after_commit")


def test_the_deferred_helper_contains_its_own_failure():
    """
    المؤجَّل هو المحاولة **واحتواء فشلها** معاً.

    كان هذا الحارس يفرض بقاء الارتداد المباشر — لأن `except` خارج الـcallback
    لا يُمسك خطأ وسيطٍ يقع بعد الالتزام. والشقّ الأول ما زال صحيحاً: الـ`except`
    يجب أن يبقى داخل الـcallback.

    [B4-7A.3] لكن ما يفعله الـ`except` انقلب: كان يُعوّض بإرسالٍ متزامن، فصار
    يرصد ويصمت. والاسم تبع الوظيفة.
    """
    import inspect

    from behavior.views import _notify_behavior_after_commit

    source = inspect.getsource(_notify_behavior_after_commit)

    assert "notify_behavior_task.delay(" in source
    assert "except" in source

    # [B4-7A.3] وانقلب الشرط الثالث: كان يفرض بقاء الارتداد، فصار يمنع عودته.
    #
    # المنعُ نحويٌّ عمداً: مُعيدٌ حسن النيّة قد يُرجعه ظنّاً أنه يُصلح إتاحةً
    # ضائعة، فيُعيد معه احتمال التكرار ونداءَ المزوّد داخل الطلب.
    assert (
        "notify_parents(" not in source
    ), "عاد الارتداد المتزامن — وهو ما يُنتج إشعاراً مكرّراً عند فشل نشرٍ غامض"
    assert "logger.error(" in source, "الاحتواء بلا رصد يدفن العطل"


def test_the_boundary_scanner_can_tell_the_difference():
    """
    ماسح يقول "نعم" دائماً لا يحرس شيئاً.

    نُثبت أنه يُميّز دالّة بلا حدّ — وإلا كانت قائمة العشرة أعلاه تمرّ بلا
    معنى.
    """
    assert not _encloses_in_atomic("behavior/views.py", "behavior_dashboard")


# ═══════════════════════════════════════════════════════════════════
#  [B4-7A.3] الاحتواء — بعد الالتزام لا ينقلب شيء
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
def test_a_post_commit_failure_does_not_turn_the_response_into_a_500():
    """`robust=True` شرطٌ للاحتواء لا زينة.

    من مصدر Django (`base.py:752`): callback غير `robust` يُنفَّذ بلا حماية،
    فاستثناؤه يُرفع من `run_and_clear_commit_hooks` — **بعد** الالتزام. النتيجة
    صفوفٌ محفوظة واستجابةٌ 500، فيُعيد المستخدم التسجيل ويُنشئ مخالفةً ثانية.

    وكان الارتدادُ المحذوف هو ما يبتلع ذلك بالمصادفة، فنزعُه بلا `robust`
    يُنتج عطباً أسوأ ممّا يُعالج.
    """
    from django.db import transaction as db_transaction

    class _CallbackError(RuntimeError):
        """يُحاكي انفجاراً داخل الـcallback بعد الالتزام."""

    exploded = []

    def _explode():
        exploded.append(True)
        raise _CallbackError("post-commit boom")

    with db_transaction.atomic():
        db_transaction.on_commit(_explode, robust=True)

    assert exploded, "لم يُنفَّذ الـcallback أصلاً"


@pytest.mark.django_db(transaction=True)
def test_without_robust_the_same_failure_would_escape():
    """ضبطٌ سالب: يُثبت أن `robust=True` هو ما يمنع الخروج، لا شيء آخر."""
    from django.db import transaction as db_transaction

    class _CallbackError(RuntimeError):
        pass

    def _explode():
        raise _CallbackError("post-commit boom")

    with pytest.raises(_CallbackError):
        with db_transaction.atomic():
            db_transaction.on_commit(_explode)  # بلا robust


def test_both_behavior_registrations_are_robust():
    """كلا موضعي التسجيل — لا أحدهما.

    موضعٌ واحد بلا `robust` يكفي لإعادة العطب من الباب الآخر، والاثنان يسجّلان
    نفس الـcallback من مسارَي طلبٍ مختلفين.
    """
    import ast
    import inspect
    import pathlib

    from behavior import views as behavior_views

    source = pathlib.Path(inspect.getsourcefile(behavior_views)).read_text(encoding="utf-8")

    registrations = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "on_commit"
    ]

    assert len(registrations) == 2, f"تغيّر عدد مواضع التسجيل: {len(registrations)}"

    for call in registrations:
        robust = next((k for k in call.keywords if k.arg == "robust"), None)
        assert robust is not None, f"تسجيلٌ بلا robust عند السطر {call.lineno}"
        assert robust.value.value is True, f"robust ليست True عند السطر {call.lineno}"


@pytest.mark.django_db(transaction=True)
def test_the_type_kombu_actually_raises_is_caught(caplog):
    """[B4-7A.3] `OperationalError` — ما يرفعه الوسيط فعلاً حين يسقط.

    نسبُه `KombuError → Exception`، فهو خارج `(ImportError, OSError,
    RuntimeError)` تماماً. وقبل إضافته كان يخرج من الـcallback: لا رسالتنا
    تُكتب، ولا الاحتواء الذي بنيناه يقع — بل تلتقطه طبقة `robust` فتُسجّل نصّاً
    عامّاً من Django لا يذكر مخالفةً ولا إشعاراً.

    والفحص سلوكيّ لا نَسَبيّ: مقارنةُ الأنساب تُثبت أنه ليس منها، وهذا يُثبت
    أن الـ`except` يلتقطه فعلاً.
    """
    import logging

    from kombu.exceptions import OperationalError

    school = SchoolFactory()
    student = UserFactory()
    reporter = UserFactory()

    with (
        patch(
            "notifications.tasks.notify_behavior_task.delay",
            side_effect=OperationalError("broker unreachable"),
        ),
        patch("behavior.services.BehaviorService.notify_parents") as direct,
        caplog.at_level(logging.ERROR, logger="behavior.views"),
    ):
        infraction = _record_infraction(school, student, reporter)

    assert BehaviorInfraction.objects.filter(id=infraction.id).exists()
    assert not direct.called, "أرسل مباشرةً من الويب"
    assert any(
        "broker publish failed" in record.message for record in caplog.records
    ), "خرج OperationalError من الـcallback — رسالتنا لم تُكتب"


def test_the_caught_types_cover_what_the_broker_raises():
    """حارس: أنواع الالتقاط تُقارَن بما ترفعه المكتبة، لا بما نظنّه.

    ترقيةُ Kombu قد تُغيّر النسب — فيسقط هذا الحارس قبل أن يسقط الرصد في
    الإنتاج صامتاً.
    """
    import ast
    import inspect
    import textwrap

    from kombu.exceptions import OperationalError

    from behavior.views import _notify_behavior_after_commit

    # البحث النصّي في مصدر الدالّة لا يكفي: الاستيراد الداخلي يذكر الاسم، فيمرّ
    # الحارس ولو نُزع النوع من بند `except` نفسه — جرّبتُه فمرّ.
    tree = ast.parse(textwrap.dedent(inspect.getsource(_notify_behavior_after_commit)))

    caught = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            types = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
            caught |= {t.id for t in types if isinstance(t, ast.Name)}

    assert (
        "OperationalError" in caught
    ), f"النوع الذي يرفعه الوسيط ليس في بند except — الملتقَط: {sorted(caught)}"

    # ولو صار من نسل الثلاثة يوماً، لم يعد ذكره لازماً — لكنه لا يضرّ.
    assert not issubclass(
        OperationalError, (ImportError, OSError, RuntimeError)
    ), "تغيّر نسب OperationalError — أعد تقييم قائمة الالتقاط"
