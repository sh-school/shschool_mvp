"""إعادةُ ضبط المصادقة الثنائيّة لحسابٍ محبوس.

يقع الحبسُ حين لا يُقرأ سرُّ TOTP بمفتاح هذه البيئة (تدويرُ مفتاح لم يشمل الحقل،
أو قاعدةٌ منسوخةٌ من بيئةٍ أخرى): لا رمزَ يطابقه، وصفحةُ التحقّق تقول ذلك وتُحيل
إلى هذا الأمر. يُمحى السرُّ ويُطفأ التفعيل، فيُعاد الإعدادُ عند الدخول التالي
(الإلزامُ للكادر يفرضه). كلُّ إعادة ضبطٍ تُكتب في سجلّ التدقيق.

    python manage.py reset_2fa --employee 12345
    python manage.py reset_2fa --national-id 999...   (رقمٌ شخصيّ)
    python manage.py reset_2fa --unreadable            (كلُّ من لا يُقرأ سرُّه)
"""

from django.core.management.base import BaseCommand, CommandError

from core.models import AuditLog, CustomUser
from core.views_auth import usable_totp_secret


class Command(BaseCommand):
    help = "يمحو سرَّ TOTP ويُطفئ التفعيل لحسابٍ محبوسٍ خارج المصادقة الثنائيّة"

    def add_arguments(self, parser):
        parser.add_argument("--national-id", dest="national_id")
        parser.add_argument("--employee", dest="employee_number")
        parser.add_argument(
            "--unreadable",
            action="store_true",
            help="كلُّ حسابٍ سرُّه لا يُقرأ بمفتاح هذه البيئة",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if options["national_id"]:
            users = CustomUser.objects.filter(national_id=options["national_id"])
        elif options["employee_number"]:
            users = CustomUser.objects.filter(employee_number=options["employee_number"])
        elif options["unreadable"]:
            users = [
                u
                for u in CustomUser.objects.exclude(totp_secret="")
                if usable_totp_secret(u) is None
            ]
        else:
            raise CommandError("حدّد --national-id أو --employee أو --unreadable")

        users = list(users)
        if not users:
            raise CommandError("لا حسابَ يطابق")
        for user in users:
            state = "مفعَّل" if user.totp_enabled else "غيرُ مفعَّل"
            self.stdout.write(f"{user.pk}: {state} — {'سيُمحى' if options['dry_run'] else 'يُمحى'}")
            if options["dry_run"]:
                continue
            user.totp_secret = ""
            user.totp_enabled = False
            user.save(update_fields=["totp_secret", "totp_enabled"])
            AuditLog.log(
                user=None,
                action="update",
                model_name="CustomUser",
                object_id=str(user.pk),
                object_repr=str(user),
                changes={"totp": "reset by management command reset_2fa"},
            )
        self.stdout.write(self.style.SUCCESS(f"{len(users)} حساباً"))
