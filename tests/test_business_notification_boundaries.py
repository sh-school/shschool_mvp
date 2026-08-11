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

    `create_infraction` مزيَّنة بـ`@transaction.atomic` أصلاً، فتصير هنا نقطةَ
    حفظ داخلية؛ والالتزام الذي يُطلق الـcallback هو نهاية المعاملة الخارجية.
    """
    from behavior.services import BehaviorService

    school = SchoolFactory()
    student = UserFactory()
    reporter = UserFactory()

    with patch("behavior.services.BehaviorService.notify_parents") as direct:
        with pytest.raises(_SentinelError), transaction.atomic():
            BehaviorService.create_infraction(
                school=school,
                student=student,
                reporter=reporter,
                level=2,
                description="وصف",
                action_taken="إجراء",
                points_deducted=0,
            )
            _abort_the_business_transaction()

    assert not BehaviorInfraction.objects.filter(student=student).exists()
    assert not behavior_queued.called, "خرج إلى الطابور رغم التراجع"
    assert not direct.called, "أرسل مباشرةً رغم التراجع"


@pytest.mark.django_db(transaction=True)
def test_a_broker_failure_after_commit_still_reaches_the_parent():
    """
    [B4-PRE3] لم نُصلح التراجع على حساب الإتاحة القديمة.

    الارتداد المباشر انتقل خلف الالتزام كاملاً — المحاولة و`except` معاً — فلو
    بقي الـ`except` خارج الـcallback لما أمسك خطأ وسيطٍ يقع بعده، ولسقط
    الارتداد بصمت.
    """
    school = SchoolFactory()
    student = UserFactory()
    reporter = UserFactory()

    with (
        patch(
            "notifications.tasks.notify_behavior_task.delay",
            side_effect=RuntimeError("broker down"),
        ),
        patch("behavior.services.BehaviorService.notify_parents") as direct,
    ):
        infraction = _record_infraction(school, student, reporter)

    assert BehaviorInfraction.objects.filter(id=infraction.id).exists()
    assert direct.called, "سقط الارتداد المباشر بعد فشل الوسيط"


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
    first, second = _stale_swap(school, 1), _stale_swap(school, 3)
    order = [first.id, second.id]

    def _notify_but_fail_on_the_second(swap, *args, **kwargs):
        if swap.id == order[1]:
            raise _SentinelError
        return None

    with (
        patch.object(SwapService, "_notify", side_effect=_notify_but_fail_on_the_second),
        pytest.raises(_SentinelError),
    ):
        SwapService.expire_stale_swaps()

    first.refresh_from_db()
    second.refresh_from_db()

    assert first.status == "cancelled", "تراجع طلبٌ نجح بسبب فشل طلب لاحق"
    assert second.status == "pending_b", "لم يتراجع الطلب الذي فشل"
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


def test_the_boundary_scanner_can_tell_the_difference():
    """
    ماسح يقول "نعم" دائماً لا يحرس شيئاً.

    نُثبت أنه يُميّز دالّة بلا حدّ — وإلا كانت قائمة العشرة أعلاه تمرّ بلا
    معنى.
    """
    assert not _encloses_in_atomic("behavior/views.py", "behavior_dashboard")
