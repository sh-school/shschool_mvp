"""قسمةُ الشعبة بين معلّمَين في المادّة نفسها — الحالةُ الحيّةُ: إدارةُ الأعمال في 11/2.

الشعبةُ تُقسم نصفين يدرسان المادّةَ في التوقيت نفسه بمعلّمَين. وكان النقلُ
وحدَه ما تعرفه الخدمةُ: إسنادُ المادّة إلى ثانٍ يُسقطها عن الأوّل. فصارت
القسمةُ خياراً صريحاً (`split=True`) يُبقي السجلّين ويَسِمهما بوسم توازٍ
واحدٍ ليُجدولا في خانةٍ واحدة — فلا هجرةَ ولا لمسَ لخانات الجدول.
"""

from operations.models import SubjectClassAssignment


def _rivals(siblings, current, teacher_id):
    """السجلّاتُ الحيّةُ لمعلّمين آخرين في (الشعبة، المادّة) نفسِها."""
    return [
        r
        for r in siblings
        if r is not current and r.is_active and r.teacher_id and r.teacher_id != teacher_id
    ]


def begin_split(siblings, current, teacher, *, by):
    """يُجهّز القسمة: يُرجع `(وسم, مانع)` ويَسِم السجلَّ القائم بوسم المجموعة.

    الوسمُ فارغٌ إن لم يكن في المادّة معلّمٌ آخر (لا قسمةَ بعدُ فيُكتب إسنادٌ عاديّ).
    والمعلّمُ الذي يحمل المادّةَ أصلاً لا يُقسَم مع نفسه: يُرجع مانعَ `PARALLEL_SAME_TEACHER`.
    """
    from academic_management import assignment_services as svc

    if current is not None and current.is_active and current.teacher_id == teacher.id:
        clash = svc.Finding(
            svc.BLOCK,
            svc.PARALLEL_SAME_TEACHER,
            f"{teacher.full_name} يحمل {current.subject.name_ar} في {current.class_group} أصلاً — "
            "القسمةُ تلزمها معلّمان مختلفان.",
        )
        return "", clash

    rivals = _rivals(siblings, current, teacher.id)
    if not rivals:
        return "", None
    tag = next(((r.parallel_group or "").strip() for r in rivals if r.parallel_group), "")
    tag = tag or svc._unique_parallel_tag(rivals[0].class_group)
    for row in rivals:
        if (row.parallel_group or "").strip() == tag:
            continue
        before = svc._snapshot(row)
        row.parallel_group = tag
        row.updated_by = by
        row.save(update_fields=["parallel_group", "updated_by", "updated_at"])
        svc._audit(row, "update", before, svc._snapshot(row))
    return tag, None


def live_row(school, assignment_id):
    """الإسنادُ الحيّ في هذه المدرسة — أو 404."""
    from django.shortcuts import get_object_or_404

    return get_object_or_404(
        SubjectClassAssignment, id=assignment_id, is_active=True, school=school
    )


def options_html(school, assignment):
    """خياراتُ `<select>` المعلّم الثاني."""
    from django.utils.html import format_html_join

    return format_html_join(
        "",
        '<option value="{}">{}</option>',
        ((u.id, u.full_name) for u in split_candidates(school, assignment)),
    )


def split_with(school, assignment, data, *, by):
    """يقسم إسنادَ `assignment` مع معلّمِ `data["teacher"]` بحصصه نفسها — ويُرجع الملاحظات."""
    from uuid import UUID

    from django.core.exceptions import ValidationError

    from academic_management import assignment_services as svc
    from core.user_selectors import school_user_or_none

    second_id = data.get("teacher") or ""
    try:
        UUID(str(second_id))
    except ValueError:
        raise ValidationError("اختر المعلّمَ الثاني.") from None
    second = school_user_or_none(school, second_id)
    if second is None:
        raise ValidationError("اختر المعلّمَ الثاني.")
    _row, findings = svc.apply_assignment(
        school=school,
        academic_year=assignment.academic_year,
        class_group=assignment.class_group,
        subject=assignment.subject,
        teacher=second,
        weekly_periods=assignment.weekly_periods,
        by=by,
        requires_lab=assignment.requires_lab,
        split=True,
    )
    return findings


def split_candidates(school, assignment):
    """معلّمو المدرسة الذين يصحّ أن يشاركوا هذا الإسنادَ: لا صاحبَه ولا من يحمل المادّةَ في الشعبة."""
    from core.models import Membership
    from core.models.access import DEPARTMENT_ROLES

    taken = SubjectClassAssignment.objects.live(school, year=assignment.academic_year).filter(
        class_group=assignment.class_group, subject=assignment.subject
    )
    users = {
        m.user
        for m in Membership.objects.filter(
            school=school, is_active=True, role__name__in=DEPARTMENT_ROLES
        ).select_related("user")
    }
    held = set(taken.values_list("teacher_id", flat=True))
    return sorted((u for u in users if u.id not in held), key=lambda u: u.full_name)
