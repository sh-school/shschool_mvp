"""
tests/test_swap_rules.py
اختبارات قوانين التبديل العشرة — SwapService validation

يغطي:
  1. لا طلب مكرر لحصة معلّقة
  2. نفس الفصل فقط
  3. لا تعارض على حصة ب
  4. تخصصان مختلفان → النائب (is_cross_department)
  5. حصص مزدوجة تُبدّل كوحدة
  6. تاريخ مستقبلي + 24 ساعة + حد 14 يوم
  7. انتهاء صلاحية بعد 48 ساعة
  8a. حد 2 طلب معلّق
  8b. حد 4 تبديلات شهرياً
  9/12. إلغاء قبل رد المعلم ب
  13. سحب بعد موافقة المعلم ب
  14. إلغاء بعد الموافقة — القيادة فقط
"""

from datetime import date, time, timedelta

import pytest

from operations.models import ScheduleSlot, Subject, TeacherSwap
from operations.services import SwapService
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    UserFactory,
)

# ══════════════════════════════════════════════════
#  FACTORIES & FIXTURES
# ══════════════════════════════════════════════════


@pytest.fixture
def subject_math(db, school):
    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


@pytest.fixture
def subject_physics(db, school):
    return Subject.objects.create(school=school, name_ar="الفيزياء", code="PHY")


@pytest.fixture
def subject_art(db, school):
    return Subject.objects.create(school=school, name_ar="الفنون البصرية", code="ART")


@pytest.fixture
def class_11_4(db, school):
    return ClassGroupFactory(school=school, grade="G11", section="4")


@pytest.fixture
def class_11_3(db, school):
    return ClassGroupFactory(school=school, grade="G11", section="3")


@pytest.fixture
def teacher_a(db, school):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلم أ — سفيان")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def teacher_b(db, school):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلم ب — أحمد")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def teacher_c(db, school):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(full_name="معلم ج — مرتضى")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def coordinator_user(db, school):
    role = RoleFactory(school=school, name="coordinator")
    user = UserFactory(full_name="المنسق")
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def slot_a(db, school, class_11_4, teacher_a, subject_math):
    """حصة سفيان — الأحد ح4 — رياضيات 11/4"""
    return ScheduleSlot.objects.create(
        school=school,
        class_group=class_11_4,
        teacher=teacher_a,
        subject=subject_math,
        day_of_week=0,
        period_number=4,
        start_time=time(9, 45),
        end_time=time(10, 30),
    )


@pytest.fixture
def slot_b(db, school, class_11_4, teacher_b, subject_physics):
    """حصة أحمد — الأحد ح2 — فيزياء 11/4 (نفس الفصل)"""
    return ScheduleSlot.objects.create(
        school=school,
        class_group=class_11_4,
        teacher=teacher_b,
        subject=subject_physics,
        day_of_week=0,
        period_number=2,
        start_time=time(8, 15),
        end_time=time(9, 0),
    )


@pytest.fixture
def slot_diff_class(db, school, class_11_3, teacher_c, subject_math):
    """حصة في فصل مختلف (11/3)"""
    return ScheduleSlot.objects.create(
        school=school,
        class_group=class_11_3,
        teacher=teacher_c,
        subject=subject_math,
        day_of_week=0,
        period_number=3,
        start_time=time(9, 0),
        end_time=time(9, 45),
    )


@pytest.fixture
def future_sunday():
    """أقرب يوم أحد مستقبلي (بعد 3 أيام على الأقل)"""
    today = date.today()
    days_ahead = (6 - today.weekday()) % 7  # الأحد = 6 في Python
    if days_ahead < 3:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


# ══════════════════════════════════════════════════
#  القانون 1: لا طلب مكرر لحصة معلّقة
# ══════════════════════════════════════════════════


class TestRule01NoDuplicate:
    def test_duplicate_pending_rejected(self, school, teacher_a, slot_a, slot_b, future_sunday):
        """لا يجوز تقديم طلب تبديل لحصة عليها طلب معلّق"""
        # أنشئ طلب أول
        SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=slot_b.teacher,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        # الطلب الثاني يجب أن يُرفض
        with pytest.raises(ValueError, match="طلب تبديل معلّق"):
            SwapService.create_swap_request(
                school=school,
                teacher_a=teacher_a,
                teacher_b=slot_b.teacher,
                slot_a=slot_a,
                slot_b=slot_b,
                swap_date_a=future_sunday,
                swap_date_b=future_sunday,
            )


# ══════════════════════════════════════════════════
#  القانون 2: نفس الفصل فقط
# ══════════════════════════════════════════════════


class TestRule02SameClassOnly:
    def test_different_class_rejected(
        self, school, teacher_a, slot_a, slot_diff_class, future_sunday
    ):
        """لا يجوز التبديل مع معلم من فصل مختلف"""
        errors = SwapService.validate_swap_request(
            teacher=teacher_a,
            slot_a=slot_a,
            slot_b=slot_diff_class,
            swap_date=future_sunday,
            school=school,
        )
        assert any("نفس الفصل" in e for e in errors)

    def test_same_class_accepted(self, school, teacher_a, slot_a, slot_b, future_sunday):
        """نفس الفصل يمر بنجاح"""
        errors = SwapService.validate_swap_request(
            teacher=teacher_a,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date=future_sunday,
            school=school,
        )
        assert not any("نفس الفصل" in e for e in errors)


# ══════════════════════════════════════════════════
#  القانون 3: لا تعارض على حصة ب
# ══════════════════════════════════════════════════


class TestRule03NoPendingOnSlotB:
    def test_slot_b_with_pending_rejected(
        self, school, teacher_a, teacher_c, slot_a, slot_b, class_11_4, subject_math, future_sunday
    ):
        """لا يجوز التبديل مع حصة عليها طلب معلّق من آخر"""
        # أنشئ حصة ثالثة لمعلم ج في نفس الفصل
        slot_c = ScheduleSlot.objects.create(
            school=school,
            class_group=class_11_4,
            teacher=teacher_c,
            subject=subject_math,
            day_of_week=1,
            period_number=3,
            start_time=time(9, 0),
            end_time=time(9, 45),
        )
        # معلم ج يطلب تبديل مع حصة ب
        SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_c,
            teacher_b=slot_b.teacher,
            slot_a=slot_c,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        # الآن معلم أ يحاول التبديل مع نفس حصة ب
        errors = SwapService.validate_swap_request(
            teacher=teacher_a,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date=future_sunday,
            school=school,
        )
        assert any("طلب تبديل معلّق" in e for e in errors)


# ══════════════════════════════════════════════════
#  القانون 4: تخصصان مختلفان → النائب
# ══════════════════════════════════════════════════


class TestRule04CrossDepartment:
    def test_same_subject_not_cross(
        self, school, class_11_4, teacher_a, teacher_b, subject_math, future_sunday
    ):
        """نفس المادة → ليس cross department"""
        slot_x = ScheduleSlot.objects.create(
            school=school,
            class_group=class_11_4,
            teacher=teacher_a,
            subject=subject_math,
            day_of_week=2,
            period_number=1,
            start_time=time(7, 30),
            end_time=time(8, 15),
        )
        slot_y = ScheduleSlot.objects.create(
            school=school,
            class_group=class_11_4,
            teacher=teacher_b,
            subject=subject_math,
            day_of_week=2,
            period_number=2,
            start_time=time(8, 15),
            end_time=time(9, 0),
        )
        swap = SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_b,
            slot_a=slot_x,
            slot_b=slot_y,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        assert not swap.is_cross_department

    def test_diff_subject_is_cross(self, school, slot_a, slot_b, future_sunday):
        """مادتان مختلفتان → cross department → يحتاج النائب"""
        swap = SwapService.create_swap_request(
            school=school,
            teacher_a=slot_a.teacher,
            teacher_b=slot_b.teacher,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        assert swap.is_cross_department  # رياضيات ≠ فيزياء


# ══════════════════════════════════════════════════
#  القانون 5: حصص مزدوجة تُبدّل كوحدة
# ══════════════════════════════════════════════════


class TestRule05DoublePeriods:
    def test_double_period_must_swap_together(
        self, school, class_11_4, teacher_a, subject_art, future_sunday, slot_b
    ):
        """فنون بصرية مزدوجة — لا يُسمح بتبديل واحدة فقط"""
        art_p1 = ScheduleSlot.objects.create(
            school=school,
            class_group=class_11_4,
            teacher=teacher_a,
            subject=subject_art,
            day_of_week=3,
            period_number=3,
            start_time=time(9, 0),
            end_time=time(9, 45),
        )
        # الحصة المتتالية (مزدوجة)
        ScheduleSlot.objects.create(
            school=school,
            class_group=class_11_4,
            teacher=teacher_a,
            subject=subject_art,
            day_of_week=3,
            period_number=4,
            start_time=time(9, 45),
            end_time=time(10, 30),
        )
        errors = SwapService.validate_swap_request(
            teacher=teacher_a,
            slot_a=art_p1,
            slot_b=slot_b,
            swap_date=future_sunday,
            school=school,
        )
        assert any("مزدوجة" in e for e in errors)


# ══════════════════════════════════════════════════
#  القانون 6: تاريخ مستقبلي + 24 ساعة + 14 يوم
# ══════════════════════════════════════════════════


class TestRule06DateConstraints:
    def test_past_date_rejected(self, school, teacher_a, slot_a, slot_b):
        """لا يُقبل تاريخ ماضٍ"""
        past = date.today() - timedelta(days=3)
        errors = SwapService.validate_swap_request(
            teacher=teacher_a,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date=past,
            school=school,
        )
        assert any("ماضٍ" in e for e in errors)

    def test_far_future_rejected(self, school, teacher_a, slot_a, slot_b):
        """لا يُقبل بعد 14 يوم"""
        far = date.today() + timedelta(days=30)
        errors = SwapService.validate_swap_request(
            teacher=teacher_a,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date=far,
            school=school,
        )
        assert any("14" in e for e in errors)

    def test_valid_date_passes(self, school, teacher_a, slot_a, slot_b, future_sunday):
        """تاريخ صالح (3+ أيام مقدماً) يمر"""
        errors = SwapService.validate_swap_request(
            teacher=teacher_a,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date=future_sunday,
            school=school,
        )
        assert not any("ماضٍ" in e or "14" in e for e in errors)


# ══════════════════════════════════════════════════
#  القانون 7: انتهاء صلاحية بعد 48 ساعة
# ══════════════════════════════════════════════════


class TestRule07Expiry:
    def test_expire_stale_swaps(self, school, teacher_a, slot_a, slot_b, future_sunday):
        """الطلبات المعلّقة أكثر من 48 ساعة تُلغى تلقائياً"""
        swap = SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=slot_b.teacher,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        # حاكِ مرور 49 ساعة
        from django.utils import timezone as tz

        old_time = tz.now() - timedelta(hours=49)
        TeacherSwap.objects.filter(pk=swap.pk).update(created_at=old_time)

        count = SwapService.expire_stale_swaps()
        assert count == 1

        swap.refresh_from_db()
        assert swap.status == "cancelled"
        assert "48 ساعة" in swap.notes

    def test_fresh_swap_not_expired(self, school, teacher_a, slot_a, slot_b, future_sunday):
        """طلب حديث لا تنتهي صلاحيته"""
        SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=slot_b.teacher,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        count = SwapService.expire_stale_swaps()
        assert count == 0


# ══════════════════════════════════════════════════
#  القانون 8a: حد 2 طلب معلّق
# ══════════════════════════════════════════════════


class TestRule08aPendingLimit:
    def test_max_pending_enforced(
        self,
        school,
        teacher_a,
        class_11_4,
        teacher_b,
        teacher_c,
        subject_math,
        subject_physics,
        future_sunday,
    ):
        """لا يُسمح بأكثر من 2 طلب معلّق"""
        # أنشئ حصتين مختلفتين للمعلم أ
        s1 = ScheduleSlot.objects.create(
            school=school,
            class_group=class_11_4,
            teacher=teacher_a,
            subject=subject_math,
            day_of_week=1,
            period_number=1,
            start_time=time(7, 30),
            end_time=time(8, 15),
        )
        s2 = ScheduleSlot.objects.create(
            school=school,
            class_group=class_11_4,
            teacher=teacher_a,
            subject=subject_math,
            day_of_week=2,
            period_number=1,
            start_time=time(7, 30),
            end_time=time(8, 15),
        )
        s3 = ScheduleSlot.objects.create(
            school=school,
            class_group=class_11_4,
            teacher=teacher_a,
            subject=subject_math,
            day_of_week=3,
            period_number=1,
            start_time=time(7, 30),
            end_time=time(8, 15),
        )
        # حصص للمعلمين الآخرين
        sb1 = ScheduleSlot.objects.create(
            school=school,
            class_group=class_11_4,
            teacher=teacher_b,
            subject=subject_physics,
            day_of_week=1,
            period_number=5,
            start_time=time(11, 0),
            end_time=time(11, 45),
        )
        sb2 = ScheduleSlot.objects.create(
            school=school,
            class_group=class_11_4,
            teacher=teacher_c,
            subject=subject_physics,
            day_of_week=2,
            period_number=5,
            start_time=time(11, 0),
            end_time=time(11, 45),
        )
        sb3 = ScheduleSlot.objects.create(
            school=school,
            class_group=class_11_4,
            teacher=teacher_b,
            subject=subject_physics,
            day_of_week=3,
            period_number=5,
            start_time=time(11, 0),
            end_time=time(11, 45),
        )

        # طلب 1 و 2 ينجحان
        SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_b,
            slot_a=s1,
            slot_b=sb1,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_c,
            slot_a=s2,
            slot_b=sb2,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )

        # الطلب 3 يُرفض
        with pytest.raises(ValueError, match="الحد الأقصى"):
            SwapService.create_swap_request(
                school=school,
                teacher_a=teacher_a,
                teacher_b=teacher_b,
                slot_a=s3,
                slot_b=sb3,
                swap_date_a=future_sunday,
                swap_date_b=future_sunday,
            )


# ══════════════════════════════════════════════════
#  القانون 8b: حد 4 تبديلات شهرياً
# ══════════════════════════════════════════════════


class TestRule08bMonthlyLimit:
    def test_monthly_limit_enforced(self, school, teacher_a, slot_a, slot_b, future_sunday):
        """لا يُسمح بأكثر من 4 تبديلات شهرياً"""
        # اصنع 4 تبديلات منفّذة في نفس شهر future_sunday
        month_start = future_sunday.replace(day=1)
        for i in range(SwapService.MAX_EXECUTED_PER_MONTH):
            TeacherSwap.objects.create(
                school=school,
                teacher_a=teacher_a,
                teacher_b=slot_b.teacher,
                slot_a=slot_a,
                slot_b=slot_b,
                swap_date_a=month_start + timedelta(days=i),
                swap_date_b=month_start + timedelta(days=i),
                status="executed",
                requested_by=teacher_a,
            )

        errors = SwapService.validate_swap_request(
            teacher=teacher_a,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date=future_sunday,
            school=school,
        )
        monthly_errors = [e for e in errors if "شهر" in e or ("4" in e and "تبديل" in e)]
        assert len(monthly_errors) > 0, f"Expected monthly limit error, got: {errors}"


# ══════════════════════════════════════════════════
#  القانون 9/12: إلغاء قبل رد المعلم ب
# ══════════════════════════════════════════════════


class TestRule09Cancel:
    def test_teacher_a_can_cancel_pending_b(self, school, teacher_a, slot_a, slot_b, future_sunday):
        """المعلم أ يلغي طلبه قبل رد المعلم ب"""
        swap = SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=slot_b.teacher,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        result = SwapService.cancel_swap(swap, cancelled_by=teacher_a)
        assert result.status == "cancelled"

    def test_teacher_b_cannot_cancel_pending_b(
        self, school, teacher_a, teacher_b, slot_a, slot_b, future_sunday
    ):
        """المعلم ب لا يمكنه إلغاء طلب لم يُرد عليه بعد"""
        swap = SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_b,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        with pytest.raises(ValueError, match="صاحب الطلب"):
            SwapService.cancel_swap(swap, cancelled_by=teacher_b)


# ══════════════════════════════════════════════════
#  القانون 13: سحب بعد موافقة المعلم ب
# ══════════════════════════════════════════════════


class TestRule13Withdrawal:
    def test_either_teacher_can_withdraw_after_acceptance(
        self, school, teacher_a, teacher_b, slot_a, slot_b, future_sunday
    ):
        """بعد موافقة المعلم ب — أي طرف يسحب"""
        swap = SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_b,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        SwapService.respond_to_swap(swap, accepted=True)
        assert swap.status in ("pending_coordinator", "pending_vp")

        result = SwapService.cancel_swap(swap, cancelled_by=teacher_b)
        assert result.status == "cancelled"


# ══════════════════════════════════════════════════
#  القانون 14: إلغاء بعد الموافقة — القيادة فقط
# ══════════════════════════════════════════════════


class TestRule14ApprovedCancelLeadershipOnly:
    def test_teacher_cannot_cancel_approved(
        self, school, teacher_a, teacher_b, slot_a, slot_b, coordinator_user, future_sunday
    ):
        """بعد موافقة المنسق — المعلم لا يمكنه الإلغاء"""
        swap = SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_b,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        SwapService.respond_to_swap(swap, accepted=True)
        swap.status = "approved"
        swap.save()

        with pytest.raises(ValueError, match="المنسق أو النائب"):
            SwapService.cancel_swap(swap, cancelled_by=teacher_a)

    def test_coordinator_can_cancel_approved(
        self, school, teacher_a, teacher_b, slot_a, slot_b, coordinator_user, future_sunday
    ):
        """المنسق يمكنه إلغاء تبديل معتمد"""
        swap = SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_b,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        SwapService.respond_to_swap(swap, accepted=True)
        swap.status = "approved"
        swap.save()

        result = SwapService.cancel_swap(swap, cancelled_by=coordinator_user)
        assert result.status == "cancelled"


# ══════════════════════════════════════════════════
#  اختبار الحالة السعيدة — طلب صالح يمر بنجاح
# ══════════════════════════════════════════════════


class TestHappyPath:
    def test_valid_swap_request_succeeds(self, school, teacher_a, slot_a, slot_b, future_sunday):
        """طلب تبديل مستوفي لجميع الشروط ينجح"""
        swap = SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=slot_b.teacher,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
            reason="لدي ارتباط",
        )
        assert swap.status == "pending_b"
        assert swap.teacher_a == teacher_a
        assert swap.teacher_b == slot_b.teacher
        assert swap.reason == "لدي ارتباط"

    def test_full_lifecycle(
        self, school, teacher_a, teacher_b, slot_a, slot_b, coordinator_user, future_sunday
    ):
        """دورة حياة كاملة: طلب → قبول → موافقة → تنفيذ"""
        # 1. الطلب
        swap = SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_b,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        assert swap.status == "pending_b"

        # 2. المعلم ب يقبل
        SwapService.respond_to_swap(swap, accepted=True)
        assert swap.status in ("pending_coordinator", "pending_vp")

        # 3. المنسق يوافق → تنفيذ تلقائي
        SwapService.approve_swap(swap, approved_by=coordinator_user, approved=True)
        swap.refresh_from_db()
        assert swap.status == "executed"

        # 4. تحقق أن المعلمين تبادلوا
        slot_a.refresh_from_db()
        slot_b.refresh_from_db()
        assert slot_a.teacher == teacher_b
        assert slot_b.teacher == teacher_a


# ══════════════════════════════════════════════════
#  اختبارات Views
# ══════════════════════════════════════════════════


class TestSwapViews:
    def test_swap_list_page(self, client_as, teacher_a):
        c = client_as(teacher_a)
        resp = c.get("/teacher/schedule/swaps/")
        assert resp.status_code == 200

    def test_swap_request_page(self, client_as, teacher_a):
        c = client_as(teacher_a)
        resp = c.get("/teacher/schedule/swap/request/")
        assert resp.status_code == 200

    def test_swap_options_htmx(self, client_as, teacher_a, slot_a):
        c = client_as(teacher_a)
        resp = c.get(
            f"/teacher/schedule/swap/{slot_a.pk}/options/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert resp.status_code == 200

    def test_swap_cancel_post(self, client_as, teacher_a, school, slot_a, slot_b, future_sunday):
        swap = SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=slot_b.teacher,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        c = client_as(teacher_a)
        resp = c.post(f"/teacher/schedule/swap/{swap.pk}/cancel/")
        assert resp.status_code == 302  # redirect to swap_list
        swap.refresh_from_db()
        assert swap.status == "cancelled"

    def test_cancel_forbidden_for_wrong_user(
        self, client_as, teacher_b, school, teacher_a, slot_a, slot_b, future_sunday
    ):
        swap = SwapService.create_swap_request(
            school=school,
            teacher_a=teacher_a,
            teacher_b=teacher_b,
            slot_a=slot_a,
            slot_b=slot_b,
            swap_date_a=future_sunday,
            swap_date_b=future_sunday,
        )
        c = client_as(teacher_b)
        resp = c.post(f"/teacher/schedule/swap/{swap.pk}/cancel/")
        assert resp.status_code == 302  # redirect with error message
        swap.refresh_from_db()
        assert swap.status == "pending_b"  # لم يُلغَ
