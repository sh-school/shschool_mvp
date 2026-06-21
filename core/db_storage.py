"""
core/db_storage.py
Storage backend يحفظ الملفات المرفوعة في قاعدة البيانات (StoredFile) بدل نظام
الملفات. يدوم على Railway (لا قرص دائم للويب) ويُنسَخ احتياطياً مع القاعدة.

يُفعَّل عبر STORAGES["default"] في الإعدادات. حقول FileField/ImageField لا تتغيّر —
تستخدم التخزين الافتراضي تلقائياً.
"""

import mimetypes

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.urls import reverse
from django.utils.deconstruct import deconstructible


@deconstructible
class DatabaseStorage(Storage):
    @staticmethod
    def _model():
        # استيراد كسول لتفادي مشاكل تحميل التطبيقات
        from core.models import StoredFile

        return StoredFile

    def _open(self, name, mode="rb"):
        sf = self._model().objects.get(name=name)
        return ContentFile(bytes(sf.content), name=name)

    def _save(self, name, content):
        content.seek(0)
        data = content.read()
        ct = getattr(content, "content_type", "") or mimetypes.guess_type(name)[0] or ""
        self._model().objects.update_or_create(
            name=name,
            defaults={"content": data, "size": len(data), "content_type": ct},
        )
        return name

    def exists(self, name):
        return self._model().objects.filter(name=name).exists()

    def delete(self, name):
        self._model().objects.filter(name=name).delete()

    def size(self, name):
        return self._model().objects.get(name=name).size

    def url(self, name):
        return reverse("serve_db_file", kwargs={"name": name})
