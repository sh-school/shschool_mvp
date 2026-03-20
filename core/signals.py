"""
core/signals.py
تسجيل تلقائي لكل العمليات الحساسة — PDPPL / RoPA
"""
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out


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

        AuditLog.objects.create(
            user=user,
            action=action,
            model_name=model_name,
            object_id=str(instance.pk),
            object_repr=str(instance)[:300],
            changes=changes,
            school=getattr(instance, 'school', None),
            ip_address=ip or None,
            user_agent=ua,
        )
    except Exception:
        pass


@receiver(post_save, sender='core.HealthRecord')
def audit_health_record(sender, instance, created, **kwargs):
    _log('HealthRecord', 'create' if created else 'update', instance)


@receiver(post_save, sender='core.BehaviorInfraction')
def audit_behavior(sender, instance, created, **kwargs):
    _log('BehaviorInfraction', 'create' if created else 'update', instance,
         changes={'level': instance.level, 'points': instance.points_deducted})


@receiver(pre_delete, sender='core.BehaviorInfraction')
def audit_behavior_delete(sender, instance, **kwargs):
    _log('BehaviorInfraction', 'delete', instance)


@receiver(post_save, sender='core.ClinicVisit')
def audit_clinic_visit(sender, instance, created, **kwargs):
    _log('ClinicVisit', 'create' if created else 'update', instance,
         changes={'sent_home': instance.is_sent_home})


@receiver(post_save, sender='core.ParentStudentLink')
def audit_parent_link(sender, instance, created, **kwargs):
    if created:
        _log('ParentStudentLink', 'create', instance)


@receiver(pre_delete, sender='core.ParentStudentLink')
def audit_parent_link_delete(sender, instance, **kwargs):
    _log('ParentStudentLink', 'delete', instance)


@receiver(post_save, sender='core.BookBorrowing')
def audit_borrowing(sender, instance, created, **kwargs):
    _log('BookBorrowing', 'create' if created else 'update', instance,
         changes={'status': instance.status})


@receiver(user_logged_in)
def audit_login(sender, request, user, **kwargs):
    try:
        from core.models import AuditLog
        AuditLog.objects.create(
            user=user, action='login', model_name='CustomUser',
            object_id=str(user.pk), object_repr=str(user),
            school=user.get_school() if hasattr(user, 'get_school') else None,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:300],
        )
    except Exception:
        pass


@receiver(post_save, sender='core.ConsentRecord')
def audit_consent_record(sender, instance, created, **kwargs):
    """PDPPL م.9: كل منح أو سحب موافقة يُسجَّل كدليل قانوني"""
    _log('ConsentRecord', 'create' if created else 'update', instance,
         changes={'data_type': instance.data_type, 'is_given': instance.is_given})


@receiver(post_save, sender='assessments.StudentAssessmentGrade')
def audit_grade(sender, instance, created, **kwargs):
    _log('StudentAssessmentGrade', 'create' if created else 'update', instance,
         changes={'grade': str(getattr(instance, 'score', ''))})


@receiver(user_logged_out)
def audit_logout(sender, request, user, **kwargs):
    if not user:
        return
    try:
        from core.models import AuditLog
        AuditLog.objects.create(
            user=user, action='logout', model_name='CustomUser',
            object_id=str(user.pk), object_repr=str(user),
            school=user.get_school() if hasattr(user, 'get_school') else None,
            ip_address=request.META.get('REMOTE_ADDR'),
        )
    except Exception:
        pass
