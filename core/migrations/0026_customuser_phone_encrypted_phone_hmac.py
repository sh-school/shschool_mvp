"""
Migration 0026: إضافة حقلَي تشفير رقم الهاتف (PDPPL Article 8)
────────────────────────────────────────────────────────────────
phone_encrypted  — Fernet-encrypted phone number
phone_hmac       — HMAC-SHA256 for searchable lookup (db_index=True)

بعد تطبيق هذه الـ migration، شغّل:
  python manage.py populate_phone_encryption
لملء الحقلين من بيانات phone الموجودة.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_add_academic_year_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="phone_encrypted",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="الجوال (مشفّر)",
            ),
        ),
        migrations.AddField(
            model_name="customuser",
            name="phone_hmac",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=64,
                verbose_name="HMAC الجوال",
            ),
        ),
    ]
