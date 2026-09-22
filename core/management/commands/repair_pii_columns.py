"""
repair_pii_columns — يُعيد بناء الأعمدة المشفَّرة والبصمات من الصريح بالمفتاح الحاليّ
════════════════════════════════════════════════════════════════════════════════════
قياسٌ على الإنتاج (2026-09-19): 823 من 1570 مستخدماً رقمُهم الشخصيّ المشفَّر وبصمتُه (HMAC) لا
يطابقان مفاتيح اليوم، و130 من 686 جوّالاً مشفَّراً لا يُفكّ — كلُّها صفوفٌ أُنشئت في 2026-03
بمفتاحٍ دُوِّر لاحقاً دون إضافته إلى `FERNET_OLD_KEYS`. والصريحُ موجودٌ لكلّ الصفوف، فلا فقدان
اليوم؛ لكنّ حذف العمود الصريح (البند 13) أو تدويرَ المفتاح (البند 3) قبل الإصلاح يُفقد الأرقام.

الإصلاح لا يحتاج المفتاحَ القديم (المسرَّب في التاريخ): الصريحُ هو المصدر، فيُعاد التشفيرُ
والبصمةُ منه بالمفتاح الحاليّ.

الاستخدام (لا يطبع قيماً — أعداداً فقط):
  python manage.py repair_pii_columns            # معاينة: لا يكتب شيئاً
  python manage.py repair_pii_columns --apply    # الكتابة، ثمّ إعادة القياس (يفشل إن بقي شيء)
  python manage.py repair_pii_columns --check    # يفشل (رمز خروج ≠ 0) إن وُجد صفٌّ معطوب

متكرّر بلا أثر: تشغيلٌ ثانٍ بعد الإصلاح لا يمسّ شيئاً. ولا يمسّ صفّاً سليماً (لا يُعيد تشفيره).
والصفُّ الذي فيه مشفَّرٌ بلا صريح («يتيم») يُبلَّغ عنه ولا يُلمس: لا مصدرَ يُعاد البناءُ منه.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from core.models import CustomUser, _crypto

# `_crypto` غيرُ مُعلَّمة بعد؛ يُسند إلى `Any` كي لا تُحسب أخطاءَ نوعٍ على هذا الملفّ الجديد.
_decrypt: Any = _crypto.decrypt_field
_encrypt: Any = _crypto.encrypt_field
_hmac: Any = _crypto.hmac_field

#: (الصريح، المشفَّر، البصمة)
FIELDS: tuple[tuple[str, str, str], ...] = (
    ("national_id", "national_id_encrypted", "national_id_hmac"),
    ("phone", "phone_encrypted", "phone_hmac"),
)


def is_stale(plain: str, encrypted: str, mac: str) -> bool:
    """أيُعاد بناءُ هذا الحقل؟ — الصريحُ موجودٌ ولا يطابقه مشفَّرُه أو بصمتُه بمفاتيح اليوم."""
    if not plain:
        return False
    if _hmac(plain) != mac:
        return True
    if not encrypted:
        return True
    decrypted = _decrypt(encrypted)
    return not (decrypted and decrypted != encrypted and decrypted == plain)


def is_orphan(plain: str, encrypted: str) -> bool:
    return not plain and bool(encrypted)


def scan() -> dict[str, Any]:
    """يقيس كلَّ الصفوف: من يحتاج إصلاحاً لكلّ حقل، والأيتام. لا يكتب ولا يعرض قيماً."""
    stale: dict[str, list[Any]] = {plain: [] for plain, _, _ in FIELDS}
    orphans: dict[str, int] = {plain: 0 for plain, _, _ in FIELDS}
    columns = [name for triple in FIELDS for name in triple]
    total = 0
    for pk, *values in CustomUser.objects.values_list("pk", *columns).iterator(chunk_size=500):
        total += 1
        row = dict(zip(columns, values, strict=True))
        for plain, encrypted, mac in FIELDS:
            if is_stale(row[plain], row[encrypted], row[mac]):
                stale[plain].append(pk)
            elif is_orphan(row[plain], row[encrypted]):
                orphans[plain] += 1
    return {"total": total, "stale": stale, "orphans": orphans}


def repair(report: dict[str, Any], batch_size: int = 200) -> int:
    """يعيد بناء المشفَّر والبصمة للصفوف المعطوبة من صريحها. يُعيد عدد الصفوف المعدَّلة."""
    by_user: dict[Any, list[tuple[str, str, str]]] = {}
    for triple in FIELDS:
        for pk in report["stale"][triple[0]]:
            by_user.setdefault(pk, []).append(triple)

    pks = list(by_user)
    touched = 0
    for start in range(0, len(pks), batch_size):
        chunk = pks[start : start + batch_size]
        users = list(CustomUser.objects.filter(pk__in=chunk))
        update_fields: set[str] = set()
        for user in users:
            for plain, encrypted, mac in by_user[user.pk]:
                value = getattr(user, plain)
                setattr(user, encrypted, _encrypt(value))
                setattr(user, mac, _hmac(value))
                update_fields.update((encrypted, mac))
        if users:
            with transaction.atomic():
                CustomUser.objects.bulk_update(users, sorted(update_fields))
            touched += len(users)
    return touched


class Command(BaseCommand):
    help = "إعادةُ بناء الأعمدة المشفَّرة والبصمات (الرقم الشخصيّ والجوّال) من الصريح بالمفتاح الحاليّ"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--apply", action="store_true", help="اكتب الإصلاح (الافتراضيّ معاينة)")
        parser.add_argument(
            "--check",
            action="store_true",
            help="لا يكتب؛ يفشل برمز خروج ≠ 0 إن وُجد صفٌّ معطوب",
        )
        parser.add_argument("--batch-size", type=int, default=200, help="حجم الدفعة (200)")

    def _print(self, label: str, report: dict[str, Any]) -> int:
        stale_counts = {plain: len(pks) for plain, pks in report["stale"].items()}
        self.stdout.write(f"{label}: مستخدمون {report['total']}")
        for plain, _, _ in FIELDS:
            self.stdout.write(
                f"  {plain}: معطوب {stale_counts[plain]} | يتيم (مشفَّر بلا صريح) "
                f"{report['orphans'][plain]}"
            )
        return sum(stale_counts.values())

    def handle(self, *args: Any, **options: Any) -> None:
        report = scan()
        broken = self._print("القياس", report)

        if options["check"]:
            if broken:
                raise CommandError(f"{broken} حقلٍ معطوب — شغّل --apply بعد نسخةٍ احتياطيّة")
            self.stdout.write(self.style.SUCCESS("سليم: لا حقلَ معطوب"))
            return

        if not options["apply"]:
            note = "معاينة — لم يُكتب شيء. --apply للكتابة" if broken else "لا شيء يحتاج إصلاحاً"
            self.stdout.write(self.style.WARNING(note))
            return

        touched = repair(report, batch_size=options["batch_size"])
        self.stdout.write(f"عُدِّل {touched} مستخدماً")

        remaining = self._print("إعادة القياس", scan())
        if remaining:
            raise CommandError(f"بقي {remaining} حقلٍ معطوباً بعد الإصلاح")
        self.stdout.write(self.style.SUCCESS("اكتمل: لا حقلَ معطوب"))
