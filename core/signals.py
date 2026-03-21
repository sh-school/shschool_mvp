"""
core/signals.py
تسجيل تلقائي لكل العمليات الحساسة — PDPPL / RoPA
"""
import logging
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out

logger = logging.getLogger(__name__)


def _log(model_name, action, instance, changes=None):
    try:
        from core.models import AuditLog
        from core.middleware import get_current_user, get_current_request

        user    = get_current_user()
        request = get_current_request()
        ip = ua = ''
        if request:
            ip = request.META.get('REMOTE_ADDR', '')
            ua = request.META.get('HTTP_USER_AGENT', '')[:300]

        # Use school_id to avoid triggering CustomUser.school computed property
        # (which caches _active_membership=None before membership is created)
        if hasattr(instance, 'school_id'):
            school = instance.school
        else:
            school = None

        AuditLog.objects.create(
            user        = user,
            action      = action,
            model_name  = model_name,
            object_id   = str(instance.pk),
            object_repr = str(instance)[:300],
            changes     = changes,
            school      = school,
            ip_address  = ip or None,
            user_agent  = ua,
        )
    except Exception as e:
        logger.error("AuditLog _log failed [%s/%s]: %s", model_name, action, e, exc_info=True)


# ── السجل الصحي ────────────────────────────────────────────────────────
@receiver(post_save, sender='clinic.HealthRecord')
def audit_health_record(sender, instance, created, **kwargs):
    _log('HealthRecord', 'create' if created else 'update', instance)


# ── السلوك ─────────────────────────────────────────────────────────────
@receiver(post_save, sender='behavior.BehaviorInfraction')
def audit_behavior(sender, instance, created, **kwargs):
    _log('BehaviorInfraction', 'create' if created else 'update', instance,
         changes={'level': instance.level, 'points': instance.points_deducted})


@receiver(pre_delete, sender='behavior.BehaviorInfraction')
def audit_behavior_delete(sender, instance, **kwargs):
    _log('BehaviorInfraction', 'delete', instance)


# ── العيادة ────────────────────────────────────────────────────────────
@receiver(post_save, sender='clinic.ClinicVisit')
def audit_clinic_visit(sender, instance, created, **kwargs):
    _log('ClinicVisit', 'create' if created else 'update', instance,
         changes={'sent_home': instance.is_sent_home})


# ── ربط ولي الأمر ──────────────────────────────────────────────────────
@receiver(post_save, sender='core.ParentStudentLink')
def audit_parent_link(sender, instance, created, **kwargs):
    if created:
        _log('ParentStudentLink', 'create', instance)


@receiver(pre_delete, sender='core.ParentStudentLink')
def audit_parent_link_delete(sender, instance, **kwargs):
    _log('ParentStudentLink', 'delete', instance)


# ── المكتبة ────────────────────────────────────────────────────────────
@receiver(post_save, sender='library.BookBorrowing')
def audit_borrowing(sender, instance, created, **kwargs):
    _log('BookBorrowing', 'create' if created else 'update', instance,
         changes={'status': instance.status})


# ── الموافقة (PDPPL) ───────────────────────────────────────────────────
@receiver(post_save, sender='core.ConsentRecord')
def audit_consent_record(sender, instance, created, **kwargs):
    """PDPPL م.9: كل منح أو سحب موافقة يُسجَّل كدليل قانوني"""
    _log('ConsentRecord', 'create' if created else 'update', instance,
         changes={'data_type': instance.data_type, 'is_given': instance.is_given})


# ── الدرجات ────────────────────────────────────────────────────────────
@receiver(post_save, sender='assessments.StudentAssessmentGrade')
def audit_grade(sender, instance, created, **kwargs):
    _log('StudentAssessmentGrade', 'create' if created else 'update', instance,
         changes={'grade': str(getattr(instance, 'grade', ''))})


# ── [مهمة 9] نتائج الفصل الدراسي ──────────────────────────────────────
@receiver(post_save, sender='assessments.StudentSubjectResult')
def audit_subject_result(sender, instance, created, **kwargs):
    """تسجيل كل تحديث لنتيجة الطالب الفصلية"""
    _log('StudentSubjectResult', 'create' if created else 'update', instance,
         changes={
             'semester':       instance.semester,
             'total':          str(getattr(instance, 'total_score', '')),
             'status':         getattr(instance, 'status', ''),
         })


# ── [مهمة 9] تغيير صلاحيات المستخدم (Membership) ──────────────────────
@receiver(post_save, sender='core.Membership')
def invalidate_user_membership_cache(sender, instance, **kwargs):
    """يُبطل cache active_membership عند تغيير أي عضوية"""
    if hasattr(instance, 'user') and hasattr(instance.user, 'invalidate_active_membership'):
        instance.user.invalidate_active_membership()


@receiver(post_save, sender='core.Membership')
def audit_membership(sender, instance, created, **kwargs):
    """
    تسجيل إنشاء أو تعديل عضوية — مهم لمتطلبات PDPPL:
    من أعطى صلاحية لمن، ومتى.
    """
    _log('other', 'create' if created else 'update', instance,
         changes={
             'user':      str(instance.user),
             'role':      str(instance.role),
             'is_active': instance.is_active,
             'school':    str(instance.school),
         })


@receiver(pre_delete, sender='core.Membership')
def audit_membership_delete(sender, instance, **kwargs):
    """تسجيل سحب الصلاحية"""
    _log('other', 'delete', instance,
         changes={'user': str(instance.user), 'role': str(instance.role)})


# ── [مهمة 9] تعديل بيانات المستخدم ────────────────────────────────────
@receiver(post_save, sender='core.CustomUser')
def audit_user_change(sender, instance, created, **kwargs):
    """
    تسجيل إنشاء أو تعديل حساب مستخدم.
    لا نُسجّل كلمة المرور — فقط الحقول الوصفية.
    """
    if created:
        _log('CustomUser', 'create', instance,
             changes={'national_id': instance.national_id, 'full_name': instance.full_name})
    else:
        # تسجيل التعديل فقط إذا تغيّرت حقول حساسة
        _log('CustomUser', 'update', instance,
             changes={
                 'is_active':     instance.is_active,
                 'totp_enabled':  instance.totp_enabled,
                 'must_change_pw': instance.must_change_password,
             })


# ── تسجيل الدخول والخروج ───────────────────────────────────────────────
@receiver(user_logged_in)
def audit_login(sender, request, user, **kwargs):
    try:
        from core.models import AuditLog
        AuditLog.objects.create(
            user        = user,
            action      = 'login',
            model_name  = 'CustomUser',
            object_id   = str(user.pk),
            object_repr = str(user),
            school      = user.get_school() if hasattr(user, 'get_school') else None,
            ip_address  = request.META.get('REMOTE_ADDR'),
            user_agent  = request.META.get('HTTP_USER_AGENT', '')[:300],
        )
    except Exception as e:
        logger.error("AuditLog login failed for user %s: %s", getattr(user, 'pk', '?'), e, exc_info=True)


@receiver(user_logged_out)
def audit_logout(sender, request, user, **kwargs):
    if not user:
        return
    try:
        from core.models import AuditLog
        AuditLog.objects.create(
            user        = user,
            action      = 'logout',
            model_name  = 'CustomUser',
            object_id   = str(user.pk),
            object_repr = str(user),
            school      = user.get_school() if hasattr(user, 'get_school') else None,
            ip_address  = request.META.get('REMOTE_ADDR'),
        )
    except Exception as e:
        logger.error("AuditLog logout failed for user %s: %s", getattr(user, 'pk', '?'), e, exc_info=True)
