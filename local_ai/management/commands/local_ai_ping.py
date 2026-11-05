"""`manage.py local_ai_ping` — هل خادمُ LM Studio يجيب؟ وما النماذجُ المحمَّلة؟ ويجرّب تضميناً ومحادثةً قصيرة."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from local_ai.client import LocalAIError, get_client


class Command(BaseCommand):
    help = "فحصُ الاتّصال بالنموذج المحلّيّ (LM Studio) والنماذج المتاحة"

    def add_arguments(self, parser):
        parser.add_argument("--full", action="store_true", help="جرّب التضمينَ والمحادثة أيضاً")

    def handle(self, *args, **options):
        client = get_client()
        self.stdout.write(f"الرابط: {client.base_url} · مفعَّل: {client.is_enabled()}")
        health = client.health()
        if not health["ok"]:
            self.stdout.write(self.style.ERROR(f"الخادم لا يجيب: {health['error']}"))
            return
        self.stdout.write(
            self.style.SUCCESS("الخادم يجيب. النماذج: " + ", ".join(health["models"]))
        )
        for name, wanted in (("المحادثة", client.chat_model), ("التضمين", client.embed_model)):
            mark = "✓" if wanted in health["models"] else "✗ (غير موجود — نزّله في LM Studio)"
            self.stdout.write(f"  نموذج {name}: {wanted} {mark}")
        if not options["full"]:
            return
        try:
            vector = client.embed(["اختبار"])[0]
            self.stdout.write(self.style.SUCCESS(f"التضمين يعمل — {len(vector)} بُعداً"))
            result = client.chat([{"role": "user", "content": "قل: جاهز"}], max_tokens=20)
            self.stdout.write(
                self.style.SUCCESS(f"المحادثة تعمل — ردّ النموذج: {result.content[:60]!r}")
            )
        except LocalAIError as exc:
            self.stdout.write(self.style.ERROR(f"فشل الاختبار الكامل: {exc}"))
