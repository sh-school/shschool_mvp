"""
tests/test_db_storage.py
اختبارات تخزين الملفات في قاعدة البيانات (DatabaseStorage) — تدوم على Railway.
"""

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from core.models import StoredFile


@pytest.mark.django_db
def test_storage_saves_to_db_not_filesystem():
    name = default_storage.save("t/a.txt", ContentFile(b"hi"))
    assert StoredFile.objects.filter(name=name).exists()
    assert default_storage.open(name).read() == b"hi"
    assert default_storage.size(name) == 2
    assert default_storage.exists(name) is True
    default_storage.delete(name)
    assert not StoredFile.objects.filter(name=name).exists()


@pytest.mark.django_db
def test_storage_handles_arabic_path_and_unicode_content():
    payload = "محتوى عربي".encode()
    name = default_storage.save("t/أعذار/x.txt", ContentFile(payload))
    assert default_storage.open(name).read() == payload
    default_storage.delete(name)


@pytest.mark.django_db
def test_unique_names_do_not_collide():
    # رفع ملفين بنفس المسار يُنتج اسمين مختلفين (لا فقدان)
    n1 = default_storage.save("t/dup.txt", ContentFile(b"one"))
    n2 = default_storage.save("t/dup.txt", ContentFile(b"two"))
    assert n1 != n2
    assert default_storage.open(n1).read() == b"one"
    assert default_storage.open(n2).read() == b"two"
    default_storage.delete(n1)
    default_storage.delete(n2)
