#!/usr/bin/env python
"""
seed_quality.py — حقن الخطة التشغيلية ولجنة المراجعة الذاتية
2896 إجراء موزّعة على 7 مجالات + ربط المنفذين بالمستخدمين الحقيقيين

تشغيل:
    python manage.py seed_quality
    أو: python manage.py shell < scripts/seed_quality.py
"""

import csv
import os
import re
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.development")

import django

django.setup()

from django.db import transaction

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "data"


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def read_csv(filename):
    path = SCRIPTS_DIR / filename
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ─────────────────────────────────────────────────────────────
# خريطة المنفذين (executor_norm) → job_title_norm في الموظفين
# ─────────────────────────────────────────────────────────────
EXECUTOR_TO_JOB = {
    "منسق الكيمياء": "منسق كيمياء",
    "منسق الاحياء": "منسق الاحياء",
    "منسق الفيزياء": "منسق الفيزياء",
    "منسق التربيه البدنيه": "منسق التربيه البدنيه",
    "منسق الفنون البصريه": "منسق الفنون البصريه",
    "منسق تكنولوجيا المعلومات": "منسق تكنولوجيا المعلومات",
    "منسق الدراسات الاجتماعيه": "منسق الدراسات الاجتماعيه",
    "منسق العلوم": "منسق العلوم",
    "منسق الرياضيات": "منسق الرياضيات",
    "منسق اللغه الانجليزيه": "منسق اللغه الانجليزيه",
    "منسق اللغه العربيه": "منسق اللغه العربيه",
    "منسق التربيه الاسلاميه": "منسق التربيه الاسلاميه",
    "منسق المشاريع الالكترونيه": "منسق المشاريع الالكترونيه",
    "النائب الاكاديمي": "نائب المدير للشؤون الاكاديميه",
    "النائب الاداري": "النائب الاداري",
    "الاخصائي الاجتماعي": "الاخصائي الاجتماعي",
    "المرشد الاكاديمي": "مرشد اكاديمي",
    "اخصائي الانشطه المدرسيه": "اخصائي الانشطه المعلميه",
    "السكرتير": "السكرتير",
    "الاخصائي النفسي": "الاخصائي النفسي",
    "مدير المدرسه": "مدير المدرسه",
}

# ترتيب المجالات
DOMAIN_ORDER = {
    "التحصيل الأكاديمي": 1,
    "مشاركة الطلاب وتحفيزهم": 2,
    "فاعلية المعلم": 3,
    "تكامل التكنولوجيا": 4,
    "الثقافة المدرسية": 5,
    "المرافق والموارد": 6,
    "القيادة والإدارة": 7,
}


def run():
    from core.models import CustomUser, Membership, School
    from quality.models import (
        OperationalDomain,
        OperationalIndicator,
        OperationalProcedure,
        OperationalTarget,
        QualityCommitteeMember,
    )

    print("📋 حقن الخطة التشغيلية ولجنة الجودة...\n")

    school = School.objects.get(code="SHH")
    year = "2025-2026"

    # ── بناء خريطة المنفذين: job_title_norm → user ──
    executor_cache = {}
    all_memberships = Membership.objects.filter(school=school, is_active=True).select_related(
        "user", "role"
    )

    for mem in all_memberships:
        jt = mem.user.memberships.filter(school=school).first()
        # نبحث من الـ staff list

    # بناء خريطة أبسط: job_title_norm → user من خلال CustomUser.is_staff
    staff_users = CustomUser.objects.filter(
        memberships__school=school,
        memberships__role__name__in=[
            "principal",
            "vice_admin",
            "vice_academic",
            "coordinator",
            "teacher",
            "specialist",
            "admin",
        ],
        is_staff=True,
    ).distinct()

    # نجمع job_title_norm من ملف الموظفين
    staff_rows = read_csv("2_Normalized_Staff_List.csv")
    nat_to_job = {clean(r["national_no"]): clean(r.get("job_title_norm", "")) for r in staff_rows}
    job_to_user = {}
    for user in staff_users:
        jt = nat_to_job.get(user.national_id, "")
        if jt:
            if jt not in job_to_user:
                job_to_user[jt] = user  # أول موظف بهذا المسمى

    print(f"  موظفون محمّلون في الخريطة: {len(job_to_user)}")

    def resolve_executor(executor_norm):
        """ابحث عن user بناءً على executor_norm"""
        job = EXECUTOR_TO_JOB.get(executor_norm, "")
        return job_to_user.get(job)

    with transaction.atomic():
        # ═══════════════════════════════════════════════════
        # 1. بناء الهيكل الهرمي وحقن الإجراءات
        # ═══════════════════════════════════════════════════
        plan_rows = read_csv("1_Clean_Operational_Plan.csv")
        print(f"  إجراءات في الخطة: {len(plan_rows)}")

        domain_cache = {}  # name → OperationalDomain
        target_cache = {}  # (domain_id, number) → OperationalTarget
        indicator_cache = {}  # number → OperationalIndicator
        proc_created = 0
        proc_updated = 0

        for i, row in enumerate(plan_rows):
            domain_name = clean(row.get("rank_name", ""))
            target_no = clean(row.get("target_no", ""))
            target_text = clean(row.get("target", ""))
            indicator_no = clean(row.get("indicator_no", ""))
            indicator_txt = clean(row.get("indicator", ""))
            proc_no = clean(row.get("procedure_no", ""))
            proc_text = clean(row.get("procedure", ""))
            executor_norm = clean(row.get("executor_norm", "") or row.get("executor", ""))
            date_range = clean(row.get("date_range", ""))
            status = clean(row.get("status", "In Progress"))
            evidence_type = clean(row.get("evidence_type", ""))
            ev_employee = clean(row.get("evidence_source_employee", ""))
            ev_file = clean(row.get("evidence_source_file", ""))
            evaluation = clean(row.get("evaluation", ""))
            eval_notes = clean(row.get("evaluation_notes", ""))
            follow_up = clean(row.get("follow_up", ""))
            comments = clean(row.get("comments", ""))

            if not domain_name or not proc_text:
                continue

            # ── المجال ──
            if domain_name not in domain_cache:
                domain, _ = OperationalDomain.objects.get_or_create(
                    school=school,
                    name=domain_name,
                    academic_year=year,
                    defaults={"order": DOMAIN_ORDER.get(domain_name, 99)},
                )
                domain_cache[domain_name] = domain
            domain = domain_cache[domain_name]

            # ── الهدف ──
            t_key = (domain.id, target_no)
            if t_key not in target_cache:
                target, _ = OperationalTarget.objects.get_or_create(
                    domain=domain, number=target_no, defaults={"text": target_text}
                )
                target_cache[t_key] = target
            target = target_cache[t_key]

            # ── المؤشر ──
            if indicator_no not in indicator_cache:
                indicator, _ = OperationalIndicator.objects.get_or_create(
                    target=target, number=indicator_no, defaults={"text": indicator_txt}
                )
                indicator_cache[indicator_no] = indicator
            indicator = indicator_cache[indicator_no]

            # ── الإجراء ──
            executor_user = resolve_executor(executor_norm)

            # نستخدم (indicator, number, executor_norm) كمفتاح فريد
            proc, created = OperationalProcedure.objects.get_or_create(
                indicator=indicator,
                number=proc_no,
                executor_norm=executor_norm,
                defaults={
                    "school": school,
                    "text": proc_text,
                    "executor_user": executor_user,
                    "date_range": date_range,
                    "status": status
                    if status in ("In Progress", "Completed", "Cancelled", "Not Started")
                    else "In Progress",
                    "evidence_type": evidence_type
                    if evidence_type in ("وصفي", "كمي", "كمي/وصفي")
                    else "",
                    "evidence_source_employee": ev_employee,
                    "evidence_source_file": ev_file,
                    "evaluation": evaluation,
                    "evaluation_notes": eval_notes,
                    "follow_up": follow_up,
                    "comments": comments,
                    "academic_year": year,
                },
            )
            if created:
                proc_created += 1
            else:
                # تحديث الحالة والتقييم إذا تغيّر
                updated = False
                if proc.status != status and status:
                    proc.status = status
                    updated = True
                if proc.evaluation != evaluation and evaluation:
                    proc.evaluation = evaluation
                    updated = True
                if proc.executor_user is None and executor_user:
                    proc.executor_user = executor_user
                    updated = True
                if updated:
                    proc.save()
                    proc_updated += 1

            if (i + 1) % 500 == 0:
                print(f"  ... {i+1}/{len(plan_rows)} إجراء")

        print("\n✅ الخطة التشغيلية:")
        print(f"   مجالات:   {OperationalDomain.objects.filter(school=school).count()}")
        print(f"   أهداف:    {OperationalTarget.objects.filter(domain__school=school).count()}")
        print(
            f"   مؤشرات:   {OperationalIndicator.objects.filter(target__domain__school=school).count()}"
        )
        print(
            f"   إجراءات:  {OperationalProcedure.objects.filter(school=school).count()} ({proc_created} جديد، {proc_updated} محدَّث)"
        )

        # إحصائيات الحالات
        from django.db.models import Count

        status_stats = (
            OperationalProcedure.objects.filter(school=school)
            .values("status")
            .annotate(c=Count("id"))
        )
        for s in status_stats:
            label = {"In Progress": "قيد التنفيذ", "Completed": "مكتمل"}.get(
                s["status"], s["status"]
            )
            print(f"   {label}: {s['c']}")

        # الإجراءات المرتبطة بمستخدم
        linked = OperationalProcedure.objects.filter(
            school=school, executor_user__isnull=False
        ).count()
        total = OperationalProcedure.objects.filter(school=school).count()
        print(f"   مرتبط بمستخدم: {linked}/{total} ({round(linked/total*100) if total else 0}%)")

        # ═══════════════════════════════════════════════════
        # 2. لجنة المراجعة الذاتية
        # ═══════════════════════════════════════════════════
        quality_rows = read_csv("4_Quality_Structure_v2.csv")

        # خريطة المجال من field_norm
        domain_by_norm = {}
        for d in OperationalDomain.objects.filter(school=school, academic_year=year):
            # تطبيع بسيط
            norm = (
                d.name.replace("ة", "ه")
                .replace("ى", "ي")
                .replace("أ", "ا")
                .replace("إ", "ا")
                .lower()
            )
            domain_by_norm[norm] = d

        def find_domain(field_norm):
            if not field_norm or field_norm == "-":
                return None
            fn = field_norm.strip().lower()
            # بحث مباشر
            for key, dom in domain_by_norm.items():
                if fn in key or key in fn:
                    return dom
            return None

        # خريطة job_title → user
        job_title_map = {}
        for user in staff_users:
            jt = nat_to_job.get(user.national_id, "")
            if jt and jt not in job_title_map:
                job_title_map[jt] = user

        def find_user_by_title(title_ar):
            """ابحث عن مستخدم بمسمى وظيفي"""
            t = title_ar.strip()
            # بحث مباشر
            norm_map = {
                "مدير المدرسة": "مدير المدرسه",
                "النائب الإداري": "النائب الاداري",
                "نائب المدير للشؤون الاكاديمية": "نائب المدير للشؤون الاكاديميه",
                "منسق العلوم": "منسق العلوم",
                "منسق اللغة العربية": "منسق اللغه العربيه",
                "منسق الدراسات الاجتماعية": "منسق الدراسات الاجتماعيه",
                "منسق اللغة الانجليزية": "منسق اللغه الانجليزيه",
                "الاخصائي النفسي": "الاخصائي النفسي",
                "منسق التربية الاسلامية": "منسق التربيه الاسلاميه",
                "امين مخزن": "امين مخزن",
            }
            job_norm = norm_map.get(t)
            return job_title_map.get(job_norm) if job_norm else None

        qc_created = 0
        for row in quality_rows:
            job_title = clean(row.get("المسمى الوظيفي", ""))
            resp = clean(row.get("المسؤولية", ""))
            field_n = clean(row.get("field_norm", ""))

            if not resp:
                continue

            domain_obj = find_domain(field_n)
            user_obj = find_user_by_title(job_title) if job_title else None

            member, created = QualityCommitteeMember.objects.get_or_create(
                school=school,
                job_title=job_title or "—",
                responsibility=resp,
                academic_year=year,
                defaults={
                    "user": user_obj,
                    "domain": domain_obj,
                    "is_active": True,
                },
            )
            if not created and user_obj and not member.user:
                member.user = user_obj
                member.domain = domain_obj
                member.save(update_fields=["user", "domain"])

            if created:
                qc_created += 1
                matched = f"✓ {user_obj.full_name}" if user_obj else "· غير مرتبط"
                print(f"   {resp:<25} {job_title:<35} {matched}")

        print(
            f"\n✅ لجنة المراجعة الذاتية: {QualityCommitteeMember.objects.filter(school=school).count()} عضو ({qc_created} جديد)"
        )

    # ═══════════════════════════════════════════════════
    # ملخص نهائي
    # ═══════════════════════════════════════════════════
    print("\n" + "═" * 60)
    print("🎉 اكتمل حقن الخطة التشغيلية ولجنة الجودة!")
    print("═" * 60)
    for domain in OperationalDomain.objects.filter(school=school).order_by("order"):
        pct = domain.completion_pct
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        print(f"  {domain.name:<30} {bar} {pct}%  ({domain.total_procedures} إجراء)")
    print("═" * 60)


if __name__ == "__main__":
    run()
